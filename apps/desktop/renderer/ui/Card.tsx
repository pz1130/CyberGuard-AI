import type { ReactNode } from "react";
import "./Card.css";

export type CardTone = "default" | "ok" | "warn" | "danger" | "info" | "plan";

export type CardProps = {
  tone?: CardTone;
  className?: string;
  children: ReactNode;
};

export function Card({ tone = "default", className = "", children }: CardProps) {
  return (
    <div className={`ui-card ui-card--${tone} ${className}`.trim()}>
      {children}
    </div>
  );
}
