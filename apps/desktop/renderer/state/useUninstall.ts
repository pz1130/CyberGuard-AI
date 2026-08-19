import { useCallback, useMemo, useState } from "react";
import { useI18n } from "../i18n/I18nProvider";

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
 * Render uninstall inventory as readable text.
 *
 * External evidence that will NOT be deleted must be listed explicitly:
 * evidence may live outside data_root; users need to know uninstall will
 * not take it away.
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
  const { t } = useI18n();
  const [uninstallPreview, setUninstallPreview] = useState<string | null>(null);
  const [uninstallBusy, setUninstallBusy] = useState(false);

  const api = typeof window !== "undefined" ? window.cyberguard : undefined;

  const inventory = useCallback(async () => {
    if (!api?.uninstallInventory) {
      setUninstallPreview(t("uninstall.apiUnavailable"));
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
  }, [api, t]);

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
        setUninstallPreview(t("uninstall.canceled"));
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
  }, [api, onUninstalled, t]);

  return useMemo(
    () => ({ uninstallBusy, uninstallPreview, inventory, dryRun, execute }),
    [uninstallBusy, uninstallPreview, inventory, dryRun, execute]
  );
}
