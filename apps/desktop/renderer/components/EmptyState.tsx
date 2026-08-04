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
    <div className="empty-hero empty-hero-compact">
      <div className="empty-hero-top">
        <div>
          <div className="empty-kicker">Ready</div>
          <h3>调查从这里开始</h3>
        </div>
        <p className="empty-blurb">
          配好 LLM 与告警数据源后，在下方输入任务即可。
        </p>
      </div>
      <div className="empty-actions">
        <button type="button" className="secondary" onClick={onOpenSettingsLlm}>
          1 · LLM
        </button>
        <button type="button" className="secondary" onClick={onOpenSettingsMcp}>
          2 · 数据源
        </button>
        <button
          type="button"
          className="primary"
          onClick={() => onFillSample(SAMPLE_TASK)}
        >
          3 · 示例任务
        </button>
      </div>
    </div>
  );
}

export { SAMPLE_TASK };
