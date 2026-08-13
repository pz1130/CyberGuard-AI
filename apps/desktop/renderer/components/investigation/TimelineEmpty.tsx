import { SAMPLE_TASKS } from "../../lib/sampleTasks";
import { useEnvironment, useRun } from "../../state";
import "./TimelineEmpty.css";

/**
 * 中间栏空态。
 *
 * 中间栏是视线落点，空着等于首屏什么都没说。这里承担三件事：
 * 说明这个工作台是干什么的、把未就绪的前置条件摆出来、给一个能点的起点。
 *
 * 示例任务放这里而不是左栏：中间栏有横向空间展示完整任务描述，
 * 左栏窄条只能放标签。左栏空态因此收敛成一句提示，不再重复按钮。
 */
export function TimelineEmpty() {
  const { setTask, running } = useRun();
  const { providerMode, mcpTools, pingOk } = useEnvironment();

  const notReady: string[] = [];
  if (pingOk === false) notReady.push("sidecar 未连接");
  if (providerMode !== "live") notReady.push("模型为 mock");
  if (mcpTools.length === 0) notReady.push("未接入数据源（可选）");

  return (
    <div className="tlempty">
      <div className="tlempty-intro">
        <h2 className="tlempty-title">开始一次调查</h2>
        <p className="tlempty-sub">
          描述你要查的事，agent 会自己拟计划、调工具、留证据。
          计划在执行前会给你过目。
        </p>
      </div>

      <div className="tlempty-samples">
        {SAMPLE_TASKS.map((s) => (
          <button
            key={s.id}
            type="button"
            className="tlempty-card"
            disabled={running}
            onClick={() => setTask(s.text)}
          >
            <span className="tlempty-card-label">{s.label}</span>
            <span className="tlempty-card-blurb">{s.blurb}</span>
          </button>
        ))}
      </div>

      {notReady.length > 0 ? (
        <p className="tlempty-notready">
          <span className="tlempty-notready-k">当前状态</span>
          {notReady.join(" · ")}
        </p>
      ) : null}
    </div>
  );
}
