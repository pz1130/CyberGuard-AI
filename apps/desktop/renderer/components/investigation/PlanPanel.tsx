import { usePlan } from "../../state";
import { Button } from "../../ui";
import "./PlanPanel.css";

export function PlanPanel() {
  const { pendingPlan, planEdit, setPlanEdit, approve, reject } = usePlan();
  if (!pendingPlan) return null;

  const steps = pendingPlan.plan?.steps || [];
  const localOnly = pendingPlan.approval_type === "self";

  return (
    <div className="planpanel" role="dialog" aria-label="计划审阅">
      <div className="planpanel-head">
        <span className="planpanel-label">{pendingPlan.ui_label || "计划待批"}</span>
        {/* 本地确认 ≠ 职责分离审批，必须显式标注（INV-38） */}
        {localOnly ? (
          <span className="planpanel-self">approval_type: self · 本地自批准</span>
        ) : null}
        {pendingPlan.timeout_seconds ? (
          <span className="planpanel-timeout">
            超时 {pendingPlan.timeout_seconds}s = 拒绝
          </span>
        ) : null}
      </div>

      <textarea
        className="planpanel-edit"
        value={planEdit}
        onChange={(e) => setPlanEdit(e.target.value)}
        rows={3}
        aria-label="计划摘要（可修改）"
      />

      {steps.length > 0 ? (
        <ol className="planpanel-steps">
          {steps.map((s, i) => (
            <li key={i}>{s}</li>
          ))}
        </ol>
      ) : null}

      <div className="planpanel-actions">
        <Button
          variant="primary"
          size="sm"
          onClick={() => void approve()}
          disabled={pendingPlan.local_approve_allowed === false}
        >
          批准
        </Button>
        <Button variant="danger" size="sm" onClick={() => void reject()}>
          拒绝
        </Button>
      </div>
    </div>
  );
}
