import { useRun } from "../../state";
import { StatusDot } from "../../ui";
import "./InvestigationHeader.css";

const STATUS_TEXT: Record<string, string> = {
  idle: "空闲",
  running: "运行中",
  paused: "已暂停",
  done: "已完成",
  failed: "失败",
};

export function InvestigationHeader({ title }: { title: string }) {
  const { status, running, resume, paused, pausedRunId } = useRun();

  return (
    <header className="invhead">
      <div className="invhead-row">
        <h1 className="invhead-title">{title}</h1>
        <span className="invhead-status">
          <StatusDot
            level={
              status === "running"
                ? "info"
                : status === "failed"
                  ? "danger"
                  : status === "paused"
                    ? "warn"
                    : status === "done"
                      ? "ok"
                      : "idle"
            }
            pulse={running}
            label={STATUS_TEXT[status] || status}
          />
        </span>
      </div>

      {paused ? (
        <div className="invhead-paused">
          <span>
            已暂停{pausedRunId ? ` · ${pausedRunId.slice(0, 8)}` : ""}
          </span>
          <button type="button" className="invhead-resume" onClick={() => void resume()}>
            继续
          </button>
        </div>
      ) : null}

      <div className={`invhead-bar${running ? " is-active" : ""}`} aria-hidden />
    </header>
  );
}
