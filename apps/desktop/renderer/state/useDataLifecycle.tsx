import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

export type DataLifecycleValue = {
  exportPass: string;
  setExportPass: (v: string) => void;
  exportBusy: boolean;
  exportMsg: string | null;
  exportAvailable: boolean;
  runExport: () => Promise<void>;
  uninstallBusy: boolean;
  uninstallPreview: string | null;
  inventory: () => Promise<void>;
  dryRun: () => Promise<void>;
  execute: () => Promise<void>;
};

const DataLifecycleContext = createContext<DataLifecycleValue | null>(null);

export function DataLifecycleProvider({
  children,
  onUninstalled,
}: {
  children: ReactNode;
  /** 真实卸载执行成功后清空会话状态 */
  onUninstalled?: () => void;
}) {
  const [exportPass, setExportPass] = useState("");
  const [exportBusy, setExportBusy] = useState(false);
  const [exportMsg, setExportMsg] = useState<string | null>(null);
  const [uninstallPreview, setUninstallPreview] = useState<string | null>(null);
  const [uninstallBusy, setUninstallBusy] = useState(false);

  const api = typeof window !== "undefined" ? window.cyberguard : undefined;

  const runExport = useCallback(async () => {
    if (!api?.exportEncrypted) {
      setExportMsg("导出 API 不可用（请在 Electron 中打开）");
      return;
    }
    if (exportPass.trim().length < 8) {
      setExportMsg("口令至少 8 位");
      return;
    }
    setExportBusy(true);
    setExportMsg(null);
    try {
      const r = await api.exportEncrypted(exportPass);
      if (r?.canceled) {
        setExportMsg("已取消");
      } else if (r?.ok === false) {
        setExportMsg(String(r.error || "导出失败"));
      } else {
        const dest = r.dest || r.path || "file";
        const hash = r.plaintext_sha256 || r.sha256;
        setExportMsg(
          `已导出（${r.method || "encrypted"}）→ ${dest}` +
            (hash ? ` · sha256 ${String(hash).slice(0, 12)}…` : "")
        );
        setExportPass("");
      }
    } catch (e) {
      setExportMsg(String(e));
    } finally {
      setExportBusy(false);
    }
  }, [api, exportPass]);

  const inventory = useCallback(async () => {
    if (!api?.uninstallInventory) {
      setUninstallPreview("卸载 API 不可用");
      return;
    }
    setUninstallBusy(true);
    try {
      const inv = await api.uninstallInventory();
      const del = (inv.will_delete || [])
        .map((c) => `  - ${c.name} (${c.approx_bytes ?? "?"} B)`)
        .join("\n");
      const keep = (inv.will_not_delete?.evidence_outside_data_root || []).join(
        "\n  - "
      );
      const manual = (inv.manual_steps || [])
        .map((m) => `  - ${m.item}: ${m.action}`)
        .join("\n");
      setUninstallPreview(
        `data_root: ${inv.data_root || "?"}\n` +
          `will delete:\n${del || "  (empty)"}\n` +
          `will NOT delete (external evidence):\n  - ${keep || "(none)"}\n` +
          `manual steps:\n${manual || "  (none)"}`
      );
    } catch (e) {
      setUninstallPreview(String(e));
    } finally {
      setUninstallBusy(false);
    }
  }, [api]);

  const dryRun = useCallback(async () => {
    if (!api?.uninstallExecute) return;
    setUninstallBusy(true);
    try {
      const r = await api.uninstallExecute({ confirm: true, dryRun: true });
      setUninstallPreview(
        (prev) =>
          (prev ? prev + "\n\n" : "") +
          `dry_run result: executed=${String(r.executed)} ok=${String(r.ok)}`
      );
    } catch (e) {
      setUninstallPreview(String(e));
    } finally {
      setUninstallBusy(false);
    }
  }, [api]);

  const execute = useCallback(async () => {
    if (!api?.uninstallExecute) return;
    setUninstallBusy(true);
    try {
      const r = await api.uninstallExecute({ confirm: true, dryRun: false });
      if (r?.canceled) {
        setUninstallPreview("已取消");
      } else {
        setUninstallPreview(
          `executed=${String(r.executed)} deleted=${
            (r.deleted || []).join(", ") || "—"
          }`
        );
        if (r.executed) onUninstalled?.();
      }
    } catch (e) {
      setUninstallPreview(String(e));
    } finally {
      setUninstallBusy(false);
    }
  }, [api, onUninstalled]);

  const value = useMemo<DataLifecycleValue>(
    () => ({
      exportPass,
      setExportPass,
      exportBusy,
      exportMsg,
      exportAvailable: Boolean(api?.exportEncrypted),
      runExport,
      uninstallBusy,
      uninstallPreview,
      inventory,
      dryRun,
      execute,
    }),
    [
      exportPass,
      exportBusy,
      exportMsg,
      api,
      runExport,
      uninstallBusy,
      uninstallPreview,
      inventory,
      dryRun,
      execute,
    ]
  );

  return (
    <DataLifecycleContext.Provider value={value}>
      {children}
    </DataLifecycleContext.Provider>
  );
}

export function useDataLifecycle(): DataLifecycleValue {
  const ctx = useContext(DataLifecycleContext);
  if (!ctx)
    throw new Error(
      "useDataLifecycle must be used within DataLifecycleProvider"
    );
  return ctx;
}
