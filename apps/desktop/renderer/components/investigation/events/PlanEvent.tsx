import type { Ev } from "../../../lib/types";
import { useI18n } from "../../../i18n/I18nProvider";
import { Card } from "../../../ui";
import "./events.css";

export function PlanEvent({
  ev,
}: {
  ev: Ev;
  onViewEvidence?: (id?: string) => void;
}) {
  const { t } = useI18n();
  const kind = ev.type;
  const plan = (ev.plan || {}) as { summary?: string; steps?: string[] };
  const steps = Array.isArray(plan.steps) ? plan.steps : [];
  const summary =
    plan.summary ||
    (typeof ev.plan_summary === "string" ? ev.plan_summary : "");
  const reason = typeof ev.reason === "string" ? ev.reason : "";

  const decided =
    kind === "plan_approved" ||
    kind === "plan_rejected" ||
    kind === "privilege_decided";
  const rejected =
    kind === "plan_rejected" ||
    (kind === "privilege_decided" && String(ev.status || "") !== "approved");

  const label =
    kind === "plan_ready"
      ? t("event.plan")
      : kind === "privilege_required"
        ? t("event.privilege")
        : rejected
          ? t("event.plan.rejected")
          : t("event.plan.approved");

  return (
    <Card tone={rejected ? "danger" : decided ? "ok" : "plan"} className="ev2">
      <div className="ev2-head">
        <span className="ev2-kind">{label}</span>
        {/* approval_type 必须原样展示：standalone 的 self 不得与职责分离审批混同（INV-38） */}
        {ev.approval_type ? (
          <span className="ev2-approval">
            approval_type: {String(ev.approval_type)}
          </span>
        ) : null}
      </div>

      {summary ? <p className="ev2-summary">{summary}</p> : null}
      {reason ? <p className="ev2-summary">{reason}</p> : null}

      {steps.length > 0 ? (
        <ol className="ev2-steps">
          {steps.map((s, i) => (
            <li key={i} className="ev2-step">
              <span className="ev2-step-n">{i + 1}</span>
              <span className="ev2-step-t">{s}</span>
            </li>
          ))}
        </ol>
      ) : null}
    </Card>
  );
}
