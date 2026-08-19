import type { Ev } from "../../../lib/types";
import { useI18n } from "../../../i18n/I18nProvider";
import { Markdown } from "../../Markdown";
import { Button, Card } from "../../../ui";
import "./events.css";

export function MessageEvent({
  ev,
  onViewEvidence,
}: {
  ev: Ev;
  onViewEvidence?: (id?: string) => void;
}) {
  const { t } = useI18n();

  if (ev.type === "user_task") {
    return (
      <div className="ev2-user">
        <span className="ev2-user-label">{t("event.user")}</span>
        <p className="ev2-user-text">{String(ev.task || "")}</p>
      </div>
    );
  }

  if (ev.type === "evidence_register" || ev.type === "evidence_registered") {
    const id = typeof ev.evidence_id === "string" ? ev.evidence_id : undefined;
    return (
      <Card tone="info" className="ev2">
        <div className="ev2-head">
          <span className="ev2-kind">{t("event.evidence")}</span>
          <code className="ev2-name">{String(ev.name || id || "—")}</code>
        </div>
        {typeof ev.sha256 === "string" ? (
          <p className="ev2-hash">sha256 {ev.sha256.slice(0, 16)}…</p>
        ) : null}
        {onViewEvidence ? (
          <Button size="sm" variant="ghost" onClick={() => onViewEvidence(id)}>
            {t("event.evidence.view")}
          </Button>
        ) : null}
      </Card>
    );
  }

  if (ev.type === "error") {
    return (
      <Card tone="danger" className="ev2">
        <div className="ev2-head">
          <span className="ev2-kind">{t("event.error")}</span>
        </div>
        <p className="ev2-summary">
          {String(ev.error || t("event.error.unknown"))}
        </p>
      </Card>
    );
  }

  // answer_ready：报告正文，用 Markdown 排版
  const text =
    (typeof ev.text === "string" && ev.text) ||
    (typeof ev.candidate_text === "string" && ev.candidate_text) ||
    "";
  return (
    <Card tone="default" className="ev2 ev2--report">
      <div className="ev2-head">
        <span className="ev2-kind">{t("event.report")}</span>
      </div>
      <Markdown text={text} />
    </Card>
  );
}
