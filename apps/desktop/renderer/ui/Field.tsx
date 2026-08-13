import type { ReactNode } from "react";
import "./Field.css";

export type FieldProps = {
  label: string;
  hint?: string;
  error?: string;
  htmlFor?: string;
  children: ReactNode;
};

export function Field({ label, hint, error, htmlFor, children }: FieldProps) {
  return (
    <div className={`ui-field${error ? " ui-field--error" : ""}`}>
      <label className="ui-field-label" htmlFor={htmlFor}>
        {label}
      </label>
      <div className="ui-field-control">{children}</div>
      {error ? (
        <p className="ui-field-msg ui-field-msg--error" role="alert">
          {error}
        </p>
      ) : hint ? (
        <p className="ui-field-msg">{hint}</p>
      ) : null}
    </div>
  );
}
