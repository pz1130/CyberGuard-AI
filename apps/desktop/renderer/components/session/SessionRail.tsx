import { useRun, useSessions } from "../../state";
import { Button, ListRow, Panel, Timestamp } from "../../ui";
import "./SessionRail.css";

export const SAMPLE_TASKS: Array<{ id: string; label: string; text: string }> = [
  {
    id: "triage",
    label: "告警分诊",
    text: "分诊当前 high/critical 告警，给出优先级与建议动作",
  },
  {
    id: "cve",
    label: "CVE 影响面",
    text: "评估 CVE-2024-3094 在本机环境的影响面与缓解措施",
  },
  {
    id: "alerts",
    label: "读本地告警",
    text: "读取本地告警数据源，总结最近 24 小时的异常模式",
  },
];

export function SessionRail() {
  const { sessions, sessionId, select, create, remove } = useSessions();
  const { setTask, running } = useRun();

  return (
    <Panel
      className="wb-rail sessionrail"
      tone="sunken"
      title="调查"
      actions={
        <Button size="sm" variant="ghost" onClick={create}>
          + 新建
        </Button>
      }
    >
      {sessions.length === 0 ? (
        <div className="sessionrail-empty">
          <p className="sessionrail-empty-hint">还没有调查记录。挑一个开始：</p>
          <div className="sessionrail-samples">
            {SAMPLE_TASKS.map((s) => (
              <button
                key={s.id}
                type="button"
                className="sessionrail-sample"
                disabled={running}
                onClick={() => setTask(s.text)}
              >
                {s.label}
              </button>
            ))}
          </div>
        </div>
      ) : (
        <div className="sessionrail-list">
          {sessions.map((s) => (
            <ListRow
              key={s.session_id}
              active={s.session_id === sessionId}
              title={s.title || "未命名调查"}
              meta={<Timestamp value={s.updated_at} />}
              onClick={() => void select(s.session_id)}
              actions={
                <Button
                  size="sm"
                  variant="ghost"
                  aria-label={`删除 ${s.title}`}
                  onClick={() => void remove(s.session_id)}
                >
                  ✕
                </Button>
              }
            />
          ))}
        </div>
      )}
    </Panel>
  );
}
