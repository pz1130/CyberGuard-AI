import type { ReactNode } from "react";
import "./ListRow.css";

export type ListRowVariant = "default" | "nav";

export type ListRowProps = {
  active?: boolean;
  title: ReactNode;
  meta?: ReactNode;
  onClick?: () => void;
  actions?: ReactNode;
  variant?: ListRowVariant;
};

export function ListRow({
  active,
  title,
  meta,
  onClick,
  actions,
  variant = "default",
}: ListRowProps) {
  const cls = [
    "ui-listrow",
    variant !== "default" ? `ui-listrow--${variant}` : "",
    active ? "ui-listrow--active" : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div className={cls}>
      <button
        type="button"
        className="ui-listrow-main"
        onClick={onClick}
        aria-current={active || undefined}
      >
        <span className="ui-listrow-title">{title}</span>
        {meta ? <span className="ui-listrow-meta">{meta}</span> : null}
      </button>
      {actions ? <div className="ui-listrow-actions">{actions}</div> : null}
    </div>
  );
}
