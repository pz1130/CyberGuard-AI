import type { ReactNode } from "react";
import "./Prose.css";

export function Prose({ children }: { children: ReactNode }) {
  return <div className="ui-prose">{children}</div>;
}
