import { useState, type ReactNode, type ToggleEvent } from "react";
import "./Disclosure.css";

export type DisclosureProps = {
  summary: ReactNode;
  defaultOpen?: boolean;
  className?: string;
  children: ReactNode;
};

/** React has no defaultOpen on <details>; local state keeps it toggleable. */
export function Disclosure({
  summary,
  defaultOpen = false,
  className = "",
  children,
}: DisclosureProps) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <details
      className={`ui-disclosure ${className}`.trim()}
      open={open}
      onToggle={(e: ToggleEvent<HTMLDetailsElement>) => {
        setOpen(e.currentTarget.open);
      }}
    >
      <summary className="ui-disclosure-summary">
        <span className="ui-disclosure-caret" aria-hidden>
          ▸
        </span>
        <span className="ui-disclosure-label">{summary}</span>
      </summary>
      <div className="ui-disclosure-body">{children}</div>
    </details>
  );
}
