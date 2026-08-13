import { useCallback, useMemo, useState } from "react";

export type ExportSlice = {
  exportPass: string;
  setExportPass: (v: string) => void;
  exportBusy: boolean;
  exportMsg: string | null;
  exportAvailable: boolean;
  runExport: () => Promise<void>;
};

/** 口令下限，与 sidecar 侧保持一致 */
export const MIN_PASSPHRASE = 8;

type ExportResult = {
  ok?: boolean;
  canceled?: boolean;
  method?: string;
  dest?: string;
  path?: string;
  sha256?: string;
  plaintext_sha256?: string;
  error?: string;
};

/** 把导出结果格式化成就地显示的一行（不做 toast，结果需可追溯） */
export function formatExportResult(r: ExportResult): string {
  if (r?.canceled) return "已取消";
  if (r?.ok === false) return String(r.error || "导出失败");
  const dest = r.dest || r.path || "file";
  const hash = r.plaintext_sha256 || r.sha256;
  return (
    `已导出（${r.method || "encrypted"}）→ ${dest}` +
    (hash ? ` · sha256 ${String(hash).slice(0, 12)}…` : "")
  );
}

export function useExport(): ExportSlice {
  const [exportPass, setExportPass] = useState("");
  const [exportBusy, setExportBusy] = useState(false);
  const [exportMsg, setExportMsg] = useState<string | null>(null);

  const api = typeof window !== "undefined" ? window.cyberguard : undefined;

  const runExport = useCallback(async () => {
    if (!api?.exportEncrypted) {
      setExportMsg("导出 API 不可用（请在 Electron 中打开）");
      return;
    }
    if (exportPass.trim().length < MIN_PASSPHRASE) {
      setExportMsg(`口令至少 ${MIN_PASSPHRASE} 位`);
      return;
    }
    setExportBusy(true);
    setExportMsg(null);
    try {
      const r = await api.exportEncrypted(exportPass);
      setExportMsg(formatExportResult(r));
      if (!r?.canceled && r?.ok !== false) setExportPass("");
    } catch (e) {
      setExportMsg(String(e));
    } finally {
      setExportBusy(false);
    }
  }, [api, exportPass]);

  return useMemo(
    () => ({
      exportPass,
      setExportPass,
      exportBusy,
      exportMsg,
      exportAvailable: Boolean(api?.exportEncrypted),
      runExport,
    }),
    [exportPass, exportBusy, exportMsg, api, runExport]
  );
}
