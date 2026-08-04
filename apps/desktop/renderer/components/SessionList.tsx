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
        <h2>Sessions</h2>
        <button type="button" className="col-head-action" onClick={onNew}>
          + New
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
                <span>{s.event_count} ev</span>
                <span className="session-dot">·</span>
                <span>{s.tier}</span>
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
                title="Delete (crypto-shred)"
                onClick={(e) => {
                  e.stopPropagation();
                  if (
                    window.confirm(
                      "Delete this session? Body will be crypto-shredded."
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
          <p className="muted-copy session-empty">
            No sessions yet. Type a task and Run.
          </p>
        )}
      </div>
    </div>
  );
}
