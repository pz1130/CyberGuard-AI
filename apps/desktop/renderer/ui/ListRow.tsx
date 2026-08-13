import type { ReactNode } from "react";
import "./ListRow.css";

export type ListRowProps = {
  active?: boolean;
  title: ReactNode;
  meta?: ReactNode;
  onClick?: () => void;
  actions?: ReactNode;
};

export function ListRow({ active, title, meta, onClick, actions }: ListRowProps) {
  return (
    <div className={`ui-listrow${active ? " ui-listrow--active" : ""}`}>
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
