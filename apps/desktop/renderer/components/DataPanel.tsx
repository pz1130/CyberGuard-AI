type Props = {
  open: boolean;
  onToggle: () => void;
  exportPass: string;
  onExportPass: (v: string) => void;
  exportBusy: boolean;
  exportMsg: string | null;
  onExport: () => void;
  exportAvailable: boolean;
  uninstallBusy: boolean;
  uninstallPreview: string | null;
  onInventory: () => void;
  onDryRun: () => void;
  onExecute: () => void;
};

export function DataPanel({
  open,
  onToggle,
  exportPass,
  onExportPass,
  exportBusy,
  exportMsg,
  onExport,
  exportAvailable,
  uninstallBusy,
  uninstallPreview,
  onInventory,
  onDryRun,
  onExecute,
}: Props) {
  return (
    <div className="data-panel">
      <button
        type="button"
        className="secondary data-panel-toggle"
        onClick={onToggle}
      >
        {open ? "▾" : "▸"} Data · Export / Uninstall (M7)
      </button>
      {open && (
        <div className="data-panel-body">
          <div className="data-section">
            <div className="data-section-title">Encrypted export</div>
            <p className="data-hint">
              Sessions / audit / evidence index / episodic. Keys not included.
              Prefer age when installed; else CGX1 (PBKDF2+Fernet).
            </p>
            <input
              type="password"
              className="data-input"
              value={exportPass}
              onChange={(e) => onExportPass(e.target.value)}
              placeholder="passphrase (≥8)"
              autoComplete="new-password"
              disabled={exportBusy}
            />
            <button
              type="button"
              className="secondary"
              onClick={onExport}
              disabled={exportBusy || !exportAvailable}
            >
              {exportBusy ? "Exporting…" : "Export…"}
            </button>
            {exportMsg && <pre className="data-msg">{exportMsg}</pre>}
          </div>
          <div className="data-section">
            <div className="data-section-title">Uninstall local data</div>
            <p className="data-hint">
              Crypto-shred keys + delete data_root. External evidence listed only.
              TCC must be removed manually.
            </p>
            <div className="row data-actions">
              <button
                type="button"
                className="secondary"
                onClick={onInventory}
                disabled={uninstallBusy}
              >
                Inventory
              </button>
              <button
                type="button"
                className="secondary"
                onClick={onDryRun}
                disabled={uninstallBusy}
              >
                Dry-run
              </button>
              <button
                type="button"
                className="btn-reject"
                onClick={onExecute}
                disabled={uninstallBusy}
              >
                Delete data…
              </button>
            </div>
            {uninstallPreview && (
              <pre className="data-msg">{uninstallPreview}</pre>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
