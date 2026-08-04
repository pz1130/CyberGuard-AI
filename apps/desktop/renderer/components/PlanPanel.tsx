import type { PendingPlan } from "../lib/types";

type Props = {
  pendingPlan: PendingPlan;
  planEdit: string;
  onPlanEdit: (value: string) => void;
  onApprove: () => void;
  onReject: () => void;
};

export function PlanPanel({
  pendingPlan,
  planEdit,
  onPlanEdit,
  onApprove,
  onReject,
}: Props) {
  return (
    <div className="plan-panel">
      <div className="plan-panel-header">
        <strong>Plan Mode · {pendingPlan.ui_label || "自批准"}</strong>
        <span className="ev-meta">
          {pendingPlan.local_approve_allowed
            ? `超时 ${pendingPlan.timeout_seconds ?? 300}s → 拒绝`
            : "本机无批准按钮（职责分离 — 须服务端审批）"}
        </span>
      </div>
      <div className="ev-meta">
        risk={String(pendingPlan.plan?.risk_level || "?")} · {pendingPlan.plan_id}
      </div>
      <textarea
        className="plan-edit"
        value={planEdit}
        onChange={(e) => onPlanEdit(e.target.value)}
        rows={8}
        disabled={!pendingPlan.local_approve_allowed}
        aria-label="execution plan"
      />
      <div className="plan-actions">
        {pendingPlan.local_approve_allowed ? (
          <>
            <button type="button" className="btn-approve" onClick={onApprove}>
              自批准并执行
            </button>
            <button type="button" className="btn-reject" onClick={onReject}>
              拒绝
            </button>
          </>
        ) : (
          <span className="ev-meta">等待服务端审批…</span>
        )}
      </div>
    </div>
  );
}
