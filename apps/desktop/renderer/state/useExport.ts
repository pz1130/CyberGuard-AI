import { useCallback, useMemo, useState } from "react";
import { useI18n, type TFunc } from "../i18n/I18nProvider";

export type ExportSlice = {
  exportPass: string;
  setExportPass: (v: string) => void;
  exportBusy: boolean;
  exportMsg: string | null;
  exportAvailable: boolean;
  runExport: () => Promise<void>;
};

/** Passphrase floor; keep in sync with sidecar */
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

/** Format export result as one in-place line (no toast; must stay auditable) */
export function formatExportResult(r: ExportResult, t: TFunc): string {
  if (r?.canceled) return t("export.canceled");
  if (r?.ok === false) return String(r.error || t("export.failed"));
  const dest = r.dest || r.path || "file";
  const hash = r.plaintext_sha256 || r.sha256;
  return (
    t("export.done", { method: r.method || "encrypted", dest }) +
    (hash ? ` · sha256 ${String(hash).slice(0, 12)}…` : "")
  );
}

export function useExport(): ExportSlice {
  const { t } = useI18n();
  const [exportPass, setExportPass] = useState("");
  const [exportBusy, setExportBusy] = useState(false);
  const [exportMsg, setExportMsg] = useState<string | null>(null);

  const api = typeof window !== "undefined" ? window.cyberguard : undefined;

  const runExport = useCallback(async () => {
    if (!api?.exportEncrypted) {
      setExportMsg(t("export.apiUnavailable"));
      return;
    }
    if (exportPass.trim().length < MIN_PASSPHRASE) {
      setExportMsg(t("export.passphraseMin", { n: MIN_PASSPHRASE }));
      return;
    }
    setExportBusy(true);
    setExportMsg(null);
    try {
      const r = await api.exportEncrypted(exportPass);
      setExportMsg(formatExportResult(r, t));
      if (!r?.canceled && r?.ok !== false) setExportPass("");
    } catch (e) {
      setExportMsg(String(e));
    } finally {
      setExportBusy(false);
    }
  }, [api, exportPass, t]);

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
