const SAMPLE_TASK =
  "这批告警里哪些值得优先处理？给出理由、建议动作，以及需要我确认的假设。";

type Props = {
  onOpenSettingsLlm: () => void;
  onOpenSettingsMcp: () => void;
  onFillSample: (text: string) => void;
};

export function EmptyState({
  onOpenSettingsLlm,
  onOpenSettingsMcp,
  onFillSample,
}: Props) {
  return (
    <div className="empty-hero">
      <div className="empty-kicker">Workbench · ready</div>
      <h3>开始一次调查</h3>
      <ol>
        <li>
          <strong>LLM</strong> — Settings 配置 live key（密钥不回显）
        </li>
        <li>
          <strong>数据</strong> — Install file alerts MCP 或导入 JSON/CSV
        </li>
        <li>
          <strong>任务</strong> — 下方输入，或一键填入示例后 Run
        </li>
      </ol>
      <div className="empty-actions">
        <button type="button" className="secondary" onClick={onOpenSettingsLlm}>
          Configure LLM
        </button>
        <button type="button" className="secondary" onClick={onOpenSettingsMcp}>
          Add data source
        </button>
        <button
          type="button"
          className="primary"
          onClick={() => onFillSample(SAMPLE_TASK)}
        >
          Fill sample task
        </button>
      </div>
    </div>
  );
}

export { SAMPLE_TASK };
