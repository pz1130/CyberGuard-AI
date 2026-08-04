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
      <h3>开始一次调查</h3>
      <ol>
        <li>配置 LLM（Settings → Provider）</li>
        <li>可选：添加 MCP 数据源</li>
        <li>在下方输入任务，或填入示例后点 Run</li>
      </ol>
      <div className="empty-actions">
        <button type="button" className="secondary" onClick={onOpenSettingsLlm}>
          Open Settings · LLM
        </button>
        <button type="button" className="secondary" onClick={onOpenSettingsMcp}>
          Open Settings · MCP
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
