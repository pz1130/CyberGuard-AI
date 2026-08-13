import { useCallback, useMemo, useState } from "react";

export type UninstallSlice = {
  uninstallBusy: boolean;
  uninstallPreview: string | null;
  inventory: () => Promise<void>;
  dryRun: () => Promise<void>;
  execute: () => Promise<void>;
};

type Inventory = {
  data_root?: string;
  will_delete?: Array<{ name: string; approx_bytes?: number }>;
  will_not_delete?: { evidence_outside_data_root?: string[] };
  manual_steps?: Array<{ item: string; action: string }>;
};

/**
 * 把卸载清单渲染成可读文本。
 *
 * 「不会删的外部证据」必须显式列出：证据可能落在 data_root 之外，
 * 用户需要知道卸载不会带走它们，否则会误以为已清理干净。
 */
export function formatInventory(inv: Inventory): string {
  const del = (inv.will_delete || [])
    .map((c) => `  - ${c.name} (${c.approx_bytes ?? "?"} B)`)
    .join("\n");
  const keep = (inv.will_not_delete?.evidence_outside_data_root || []).join(
    "\n  - "
  );
  const manual = (inv.manual_steps || [])
    .map((m) => `  - ${m.item}: ${m.action}`)
    .join("\n");
  return (
    `data_root: ${inv.data_root || "?"}\n` +
    `will delete:\n${del || "  (empty)"}\n` +
    `will NOT delete (external evidence):\n  - ${keep || "(none)"}\n` +
    `manual steps:\n${manual || "  (none)"}`
  );
}

export function useUninstall(onUninstalled?: () => void): UninstallSlice {
  const [uninstallPreview, setUninstallPreview] = useState<string | null>(null);
  const [uninstallBusy, setUninstallBusy] = useState(false);

  const api = typeof window !== "undefined" ? window.cyberguard : undefined;

  const inventory = useCallback(async () => {
    if (!api?.uninstallInventory) {
      setUninstallPreview("卸载 API 不可用");
      return;
    }
    setUninstallBusy(true);
    try {
      setUninstallPreview(formatInventory(await api.uninstallInventory()));
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

  return useMemo(
    () => ({ uninstallBusy, uninstallPreview, inventory, dryRun, execute }),
    [uninstallBusy, uninstallPreview, inventory, dryRun, execute]
  );
}
