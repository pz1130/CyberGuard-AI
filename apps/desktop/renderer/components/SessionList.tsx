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
  return t.length > 48 ? `${t.slice(0, 46)}…` : t;
}

export function SessionList({
  sessions,
  sessionId,
  onSelect,
  onNew,
  onDelete,
}: Props) {
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
          <div
            key={s.session_id}
            className={`session-row${sessionId === s.session_id ? " active" : ""}`}
          >
            <button
              type="button"
              className="session-main"
              onClick={() => onSelect(s.session_id)}
            >
              {displayTitle(s)}
              <div className="session-meta">
                {s.event_count} events · {s.tier}
              </div>
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
                      "Delete this session? Body will be crypto-shredded and cannot be recovered."
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
          <p className="muted-copy">
            No local sessions yet. Type a task below and click Run.
          </p>
        )}
      </div>
    </div>
  );
}
