import { useI18n } from "../../i18n/I18nProvider";
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
  const { t } = useI18n();

  const notReady: string[] = [];
  if (pingOk === false) notReady.push(t("empty.notReady.sidecar"));
  if (providerMode !== "live") notReady.push(t("empty.notReady.mock"));
  if (mcpTools.length === 0) notReady.push(t("empty.notReady.mcp"));

  return (
    <div className="tlempty">
      <div className="tlempty-intro">
        <h2 className="tlempty-title">{t("empty.title")}</h2>
        <p className="tlempty-sub">{t("empty.sub")}</p>
      </div>

      <div className="tlempty-samples">
        {SAMPLE_TASKS.map((s) => (
          <button
            key={s.id}
            type="button"
            className="tlempty-card"
            disabled={running}
            onClick={() => setTask(t(s.textKey))}
          >
            <span className="tlempty-card-label">{t(s.labelKey)}</span>
            <span className="tlempty-card-blurb">{t(s.blurbKey)}</span>
          </button>
        ))}
      </div>

      {notReady.length > 0 ? (
        <p className="tlempty-notready">
          <span className="tlempty-notready-k">{t("empty.status")}</span>
          {notReady.join(" · ")}
        </p>
      ) : null}
    </div>
  );
}
