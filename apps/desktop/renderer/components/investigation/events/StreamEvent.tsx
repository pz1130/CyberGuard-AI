import { useStream } from "../../../state";
import { Markdown } from "../../Markdown";
import { Card } from "../../../ui";
import "./events.css";

/** 唯一消费流式 context 的组件 —— 高频重渲染被隔离在这里 */
export function StreamEvent() {
  const { streamText, streaming } = useStream();
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
