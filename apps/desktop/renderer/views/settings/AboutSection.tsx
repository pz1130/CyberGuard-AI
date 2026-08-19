import type { ReactElement } from "react";
import { useI18n } from "../../i18n/I18nProvider";
import { useEnvironment } from "../../state";
import { Card } from "../../ui";

export function AboutSection(): ReactElement {
  const { t } = useI18n();
  const { providerMode, dataRoot } = useEnvironment();

  return (
    <div className="settings-detail">
      <Card>
        <h3 className="settings-card-title">{t("settings.about.title")}</h3>
        <p className="settings-hint">
          {t("settings.about.build")}{" "}
          <strong>{t("settings.about.notary")}</strong>.
        </p>
        <p className="settings-hint">
          {t("settings.about.llmMode")}
          <strong>{providerMode || "—"}</strong>
          {" · "}
          data_root:{" "}
          <code className="mono mono-sm">{dataRoot || "—"}</code>
        </p>
        <p className="settings-hint">{t("settings.about.policy")}</p>
      </Card>
    </div>
  );
}
