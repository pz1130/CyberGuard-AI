import type { SessionRow } from "../lib/types";

type Props = {
  sessions: SessionRow[];
  sessionId: string | null;
  onSelect: (sessionId: string) => void;
  onNew: () => void;
  onDelete?: (sessionId: string) => void;
};

function displayTitle(s: SessionRow): string {
  const t = (s.title || "").trim();
  if (!t || t.startsWith("enc1:") || t === "[encrypted title]") {
    return `Session ${s.session_id.slice(0, 8)}`;
  }
  // One line, short
  const one = t.replace(/\s+/g, " ");
  return one.length > 42 ? `${one.slice(0, 40)}…` : one;
}

function relativeTime(ts: number): string {
  if (!ts) return "";
  const sec = Math.max(0, Math.floor(Date.now() / 1000 - ts));
  if (sec < 60) return "just now";
  if (sec < 3600) return `${Math.floor(sec / 60)}m`;
  if (sec < 86400) return `${Math.floor(sec / 3600)}h`;
  return `${Math.floor(sec / 86400)}d`;
}

export function SessionList({
  sessions,
  sessionId,
  onSelect,
  onNew,
  onDelete,
}: Props) {
  return (
    <div className="col col-sessions">
      <div className="col-head">
        <h2>会话</h2>
        <button type="button" className="col-head-action" onClick={onNew}>
          + 新建
        </button>
      </div>
      <div className="col-body session-list">
        {sessions.map((s) => (
          <div
            key={s.session_id}
            className={`session-row${sessionId === s.session_id ? " active" : ""}`}
          >
            <button
              type="button"
              className="session-main"
              onClick={() => onSelect(s.session_id)}
              title={s.title || s.session_id}
            >
              <span className="session-title">{displayTitle(s)}</span>
              <span className="session-meta">
                <span>{s.event_count} 事件</span>
                <span className="session-dot">·</span>
                <span>{s.tier === "readonly" ? "只读" : s.tier}</span>
                {s.updated_at ? (
                  <>
                    <span className="session-dot">·</span>
                    <span>{relativeTime(s.updated_at)}</span>
                  </>
                ) : null}
              </span>
            </button>
            {onDelete ? (
              <button
                type="button"
                className="session-del"
                title="删除会话（crypto-shred）"
                onClick={(e) => {
                  e.stopPropagation();
                  if (
                    window.confirm(
                      "删除此会话？正文将 crypto-shred，不可恢复。"
                    )
                  ) {
                    onDelete(s.session_id);
                  }
                }}
              >
                ×
              </button>
            ) : null}
          </div>
        ))}
        {sessions.length === 0 && (
          <div className="session-empty-card">
            <p className="session-empty-title">还没有会话</p>
            <p className="muted-copy session-empty">
              在中间填任务并 Run，会自动创建一条调查会话。
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
