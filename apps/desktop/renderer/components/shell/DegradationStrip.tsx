import { useState } from "react";
import { useEnvironment } from "../../state";
import { useI18n } from "../../i18n/I18nProvider";
import "./DegradationStrip.css";

export function DegradationStrip() {
  const { t } = useI18n();
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
          <span className="degstrip-label">{t(d.labelKey)}</span>
          {d.detailText || d.detailKey ? (
            <span className="degstrip-detail">
              · {d.detailText ?? t(d.detailKey)}
            </span>
          ) : null}
          <button
            type="button"
            className="degstrip-dismiss"
            onClick={() => setDismissed((prev) => [...prev, d.id])}
          >
            {t("degradation.dismiss")}
          </button>
        </div>
      ))}
    </div>
  );
}
