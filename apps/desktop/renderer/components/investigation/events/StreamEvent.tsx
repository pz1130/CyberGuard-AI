import { useI18n } from "../../../i18n/I18nProvider";
import { useStreamFlag, useStreamText } from "../../../state";
import { Markdown } from "../../Markdown";
import { Card } from "../../../ui";
import "./events.css";

/** 唯一订阅流式正文的组件 —— 每 token 的重渲染被隔离在这里 */
export function StreamEvent() {
  const streamText = useStreamText();
  const streaming = useStreamFlag();
  const { t } = useI18n();
  if (!streaming && !streamText) return null;

  return (
    <Card tone="info" className="ev2 ev2--report">
      <div className="ev2-head">
        <span className="ev2-kind">
          {streaming ? t("event.streaming") : t("event.draft")}
        </span>
        {streaming ? (
          <span className="ev2-cursor" aria-hidden>
            ▍
          </span>
        ) : null}
      </div>
      {streamText ? <Markdown text={streamText} /> : <SkeletonLines />}
    </Card>
  );
}

/** 首包之前的三条脉冲骨架 */
export function SkeletonLines() {
  const { t } = useI18n();
  return (
    <div className="ev2-skeleton" aria-label={t("event.waitingFirst")}>
      <span className="ev2-skel-line" />
      <span className="ev2-skel-line" />
      <span className="ev2-skel-line" />
    </div>
  );
}
