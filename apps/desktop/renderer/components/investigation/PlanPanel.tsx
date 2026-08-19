import { useI18n } from "../../i18n/I18nProvider";
import { usePlan } from "../../state";
import { Button } from "../../ui";
import "./PlanPanel.css";

export function PlanPanel() {
  const { pendingPlan, planEdit, setPlanEdit, approve, reject } = usePlan();
  const { t } = useI18n();
  if (!pendingPlan) return null;

  const steps = pendingPlan.plan?.steps || [];
  const localOnly = pendingPlan.approval_type === "self";

  return (
    <div className="planpanel" role="dialog" aria-label={t("plan.aria")}>
      <div className="planpanel-head">
        <span className="planpanel-label">
          {pendingPlan.ui_label || t("plan.pending")}
        </span>
        {/* 本地确认 ≠ 职责分离审批，必须显式标注（INV-38） */}
        {localOnly ? (
          <span className="planpanel-self">{t("plan.self")}</span>
        ) : null}
        {pendingPlan.timeout_seconds ? (
          <span className="planpanel-timeout">
            {t("plan.timeout", { seconds: pendingPlan.timeout_seconds })}
          </span>
        ) : null}
      </div>

      <textarea
        className="planpanel-edit"
        value={planEdit}
        onChange={(e) => setPlanEdit(e.target.value)}
        rows={3}
        aria-label={t("plan.summary.aria")}
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
          variant="secondary"
          size="sm"
          onClick={() => void approve()}
          disabled={pendingPlan.local_approve_allowed === false}
        >
          {t("plan.approve")}
        </Button>
        <Button variant="danger" size="sm" onClick={() => void reject()}>
          {t("plan.reject")}
        </Button>
      </div>
    </div>
  );
}
