import { useState } from "react";
import { useEnvironment } from "../../state";
import "./DegradationStrip.css";

export function DegradationStrip() {
  const { securityDegradations } = useEnvironment();
  const [dismissed, setDismissed] = useState<string[]>([]);

  const visible = securityDegradations.filter((d) => !dismissed.includes(d.id));
  if (visible.length === 0) return null;

  return (
    <div className="degstrip" role="alert">
      {visible.map((d) => (
        <div key={d.id} className={`degstrip-item degstrip-item--${d.level}`}>
          <span className="degstrip-lock" aria-hidden>
            🔒
          </span>
          <span className="degstrip-label">{d.label}</span>
          {d.detail ? (
            <span className="degstrip-detail">· {d.detail}</span>
          ) : null}
          <button
            type="button"
            className="degstrip-dismiss"
            onClick={() => setDismissed((prev) => [...prev, d.id])}
          >
            收起
          </button>
        </div>
      ))}
    </div>
  );
}
