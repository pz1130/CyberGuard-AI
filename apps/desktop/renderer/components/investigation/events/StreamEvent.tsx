import { useStreamFlag, useStreamText } from "../../../state";
import { Markdown } from "../../Markdown";
import { Card } from "../../../ui";
import "./events.css";

/** 唯一订阅流式正文的组件 —— 每 token 的重渲染被隔离在这里 */
export function StreamEvent() {
  const streamText = useStreamText();
  const streaming = useStreamFlag();
  if (!streaming && !streamText) return null;

  return (
    <Card tone="info" className="ev2 ev2--report">
      <div className="ev2-head">
        <span className="ev2-kind">{streaming ? "生成中" : "草稿"}</span>
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
  return (
    <div className="ev2-skeleton" aria-label="等待模型首包">
      <span className="ev2-skel-line" />
      <span className="ev2-skel-line" />
      <span className="ev2-skel-line" />
    </div>
  );
}
