import type { ReactNode } from "react";
import "./Panel.css";

export type PanelProps = {
  title?: ReactNode;
  actions?: ReactNode;
  tone?: "sunken" | "raised";
  footer?: ReactNode;
  className?: string;
  children: ReactNode;
};

export function Panel({
  title,
  actions,
  tone = "sunken",
  footer,
  className = "",
  children,
}: PanelProps) {
  return (
    <section className={`ui-panel ui-panel--${tone} ${className}`.trim()}>
      {title || actions ? (
        <header className="ui-panel-head">
          {title ? <h2 className="ui-panel-title">{title}</h2> : <span />}
          {actions ? <div className="ui-panel-actions">{actions}</div> : null}
        </header>
      ) : null}
      <div className="ui-panel-body">{children}</div>
      {footer ? <footer className="ui-panel-foot">{footer}</footer> : null}
    </section>
  );
}
