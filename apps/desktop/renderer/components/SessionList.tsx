import type { SessionRow } from "../lib/types";

type Props = {
  sessions: SessionRow[];
  sessionId: string | null;
  onSelect: (sessionId: string) => void;
  onNew: () => void;
};

export function SessionList({ sessions, sessionId, onSelect, onNew }: Props) {
  return (
    <div className="col">
      <h2>Sessions</h2>
      <div className="col-body session-list">
        <button
          type="button"
          className={!sessionId ? "active" : ""}
          onClick={onNew}
        >
          + New investigation
        </button>
        {sessions.map((s) => (
          <button
            key={s.session_id}
            type="button"
            className={sessionId === s.session_id ? "active" : ""}
            onClick={() => onSelect(s.session_id)}
          >
            {s.title || s.session_id.slice(0, 8)}
            <div className="session-meta">
              {s.event_count} events · {s.tier}
            </div>
          </button>
        ))}
        {sessions.length === 0 && (
          <p className="muted-copy">
            No local sessions yet. Type a task below and click Run.
          </p>
        )}
      </div>
    </div>
  );
}
