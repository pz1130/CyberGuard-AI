export const SAMPLE_TASKS = [
  {
    id: "triage",
    label: "告警分诊",
    text: "这批告警里哪些值得优先处理？给出理由、建议动作，以及需要我确认的假设。",
  },
  {
    id: "cve",
    label: "CVE 影响",
    text: "评估最近相关 CVE 对本环境的潜在影响，列出需要优先关注的资产与下一步。",
  },
  {
    id: "file-alerts",
    label: "读本地告警",
    text: "用 file-alerts（或已配置的 MCP）列出 high/critical 告警，聚类后给出 Top 3 与处置建议。",
  },
] as const;

export const SAMPLE_TASK = SAMPLE_TASKS[0].text;

type Props = {
  onOpenSettingsLlm: () => void;
  onOpenSettingsMcp: () => void;
  onFillSample: (text: string) => void;
  providerMode?: string;
  mcpToolCount?: number;
};

export function EmptyState({
  onOpenSettingsLlm,
  onOpenSettingsMcp,
  onFillSample,
  providerMode = "mock",
  mcpToolCount = 0,
}: Props) {
  const llmLive = providerMode === "live";
  const hasMcp = mcpToolCount > 0;
  const ready = llmLive; // MCP optional for mock demo

  return (
    <div className="empty-hero empty-hero-demo">
      <div className="empty-hero-top">
        <div className="empty-kicker">演示路径</div>
        <h3>三步开始一次调查</h3>
        <p className="empty-blurb">
          单兵桌面：配好模型与数据源，输入任务后 Run。Plan Mode
          为自批准；证据只读哈希，不把正文塞进模型。
        </p>
      </div>

      <ol className="demo-checklist">
        <li className={llmLive ? "done" : "todo"}>
          <button type="button" className="demo-check-btn" onClick={onOpenSettingsLlm}>
            <span className="demo-check-mark" aria-hidden>
              {llmLive ? "✓" : "1"}
            </span>
            <span className="demo-check-body">
              <strong>语言模型</strong>
              <span>
                {llmLive
                  ? "live 已就绪（云或本地 Ollama 等）"
                  : "当前 mock · 点此切换 live / 填 key"}
              </span>
            </span>
            <span className="demo-check-go">›</span>
          </button>
        </li>
        <li className={hasMcp ? "done" : "todo"}>
          <button type="button" className="demo-check-btn" onClick={onOpenSettingsMcp}>
            <span className="demo-check-mark" aria-hidden>
              {hasMcp ? "✓" : "2"}
            </span>
            <span className="demo-check-body">
              <strong>数据源 MCP</strong>
              <span>
                {hasMcp
                  ? `${mcpToolCount} 个工具已发现`
                  : "可选 · 安装 file-alerts 样例告警"}
              </span>
            </span>
            <span className="demo-check-go">›</span>
          </button>
        </li>
        <li className={ready ? "done" : "todo"}>
          <div className="demo-check-static">
            <span className="demo-check-mark" aria-hidden>
              3
            </span>
            <span className="demo-check-body">
              <strong>示例任务 + Run</strong>
              <span>点下方芯片填入任务，⌘↵ 运行</span>
            </span>
          </div>
        </li>
      </ol>

      <div className="sample-chips">
        {SAMPLE_TASKS.map((s) => (
          <button
            key={s.id}
            type="button"
            className="sample-chip"
            onClick={() => onFillSample(s.text)}
          >
            {s.label}
          </button>
        ))}
      </div>
    </div>
  );
}
