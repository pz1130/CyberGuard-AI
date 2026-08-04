type Props = {
  evidenceHint: string;
  onBackToWorkbench: () => void;
};

export function EvidenceView({ evidenceHint, onBackToWorkbench }: Props) {
  return (
    <div className="view-pane view-enter">
      <h1>Evidence</h1>
      <p className="lede">
        只读证据库（sha256 + mount: read-only）。完整 GUI 注册/校验在 P2；
        当前可在工作台任务中通过 sidecar 注册，计数见状态栏。
      </p>
      <div className="settings-card">
        <h3>Catalog</h3>
        <p>
          Status: <span className="pill accent">{evidenceHint}</span>
        </p>
        <p className="mt-10">
          Use RPC <code className="mono">evidence.register</code> /{" "}
          <code className="mono">evidence.verify</code> via agent tools, or wait
          for the P2 file picker UI.
        </p>
        <div className="empty-actions mt-12">
          <button
            type="button"
            className="primary"
            onClick={onBackToWorkbench}
          >
            Back to Workbench
          </button>
        </div>
      </div>
    </div>
  );
}
