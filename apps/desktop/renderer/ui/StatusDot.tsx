import "./StatusDot.css";

export type StatusLevel = "ok" | "warn" | "danger" | "info" | "idle";

export type StatusDotProps = {
  level: StatusLevel;
  pulse?: boolean;
  label?: string;
  title?: string;
};

export function StatusDot({ level, pulse, label, title }: StatusDotProps) {
  return (
    <span className="ui-dot-wrap" title={title}>
      <span
        className={`ui-dot ui-dot--${level}${pulse ? " ui-dot--pulse" : ""}`}
        aria-hidden
      />
      {label ? <span className="ui-dot-label">{label}</span> : null}
    </span>
  );
}
