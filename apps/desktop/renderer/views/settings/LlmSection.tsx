import type { ReactElement } from "react";
import { useI18n } from "../../i18n/I18nProvider";
import {
  LLM_PRESETS,
  PRESET_GROUPS,
  matchPresetByBaseUrl,
} from "../../lib/llmPresets";
import { Button, Card, Disclosure, Field, Select } from "../../ui";
import type { LlmSectionModel } from "./useLlmSection";

export type LlmSectionProps = LlmSectionModel;

export function LlmSection({
  mode,
  setMode,
  presetId,
  setPresetId,
  baseUrl,
  setBaseUrl,
  model,
  setModel,
  temperature,
  setTemperature,
  apiKey,
  setApiKey,
  hasKey,
  llmMsg,
  llmBusy,
  preset,
  requiresKey,
  applyPreset,
  onSaveLlm,
  onTestLlm,
}: LlmSectionProps): ReactElement {
  const { t } = useI18n();

  return (
    <div className="settings-detail">
      <Card>
        <h3 className="settings-card-title">{t("settings.llm.modeTitle")}</h3>
        <p className="settings-hint">{t("settings.llm.modeHint")}</p>
        <Field label={t("settings.llm.modeLabel")}>
          <Select
            ariaLabel={t("settings.llm.modeLabel")}
            value={mode as "mock" | "live"}
            onChange={setMode}
            disabled={llmBusy}
            options={[
              { value: "mock", label: t("settings.llm.modeMock") },
              { value: "live", label: t("settings.llm.modeLive") },
            ]}
          />
        </Field>
      </Card>

      <Card>
        <h3 className="settings-card-title">{t("settings.llm.presetTitle")}</h3>
        <p className="settings-hint">{t("settings.llm.presetHint")}</p>
        {PRESET_GROUPS.map((g, i) => (
          <Disclosure key={g.id} summary={t(g.labelKey)} defaultOpen={i === 0}>
            <div className="preset-grid">
              {LLM_PRESETS.filter((p) => p.group === g.id).map((p) => (
                <button
                  key={p.id}
                  type="button"
                  className={`preset-chip${presetId === p.id ? " active" : ""}`}
                  onClick={() => applyPreset(p)}
                  disabled={llmBusy || mode === "mock"}
                >
                  {t(p.labelKey)}
                  {!p.requiresKey ? (
                    <span className="preset-tag">{t("settings.llm.noKey")}</span>
                  ) : null}
                </button>
              ))}
            </div>
          </Disclosure>
        ))}
      </Card>

      <Card>
        <h3 className="settings-card-title">{t("settings.llm.connTitle")}</h3>
        {preset?.hintKey ? (
          <p className="settings-hint">{t(preset.hintKey)}</p>
        ) : null}
        <Field label="Base URL">
          <input
            className="data-input"
            value={baseUrl}
            onChange={(e) => {
              setBaseUrl(e.target.value);
              setPresetId(
                matchPresetByBaseUrl(e.target.value)?.id || "custom"
              );
            }}
            disabled={llmBusy || mode === "mock"}
            placeholder={t("settings.llm.baseUrlPh")}
          />
        </Field>
        <Field label="Model">
          {preset && preset.models.length > 0 ? (
            <Select
              ariaLabel="Model preset"
              value={
                (preset.models.includes(model) ? model : "__custom__") as string
              }
              onChange={(v) => {
                if (v !== "__custom__") setModel(v);
              }}
              disabled={llmBusy || mode === "mock"}
              options={[
                ...preset.models.map((m) => ({ value: m, label: m })),
                { value: "__custom__", label: t("settings.llm.customModel") },
              ]}
            />
          ) : null}
          <input
            className="data-input"
            value={model}
            onChange={(e) => setModel(e.target.value)}
            disabled={llmBusy || mode === "mock"}
            placeholder={t("settings.llm.modelPh")}
            style={{ marginTop: preset && preset.models.length > 0 ? 8 : 0 }}
          />
        </Field>
        <Field label="Temperature">
          <input
            className="data-input"
            value={temperature}
            onChange={(e) => setTemperature(e.target.value)}
            disabled={llmBusy || mode === "mock"}
          />
        </Field>
        <Field
          label="API key"
          hint={
            !requiresKey
              ? t("settings.llm.keyLocalOpt")
              : hasKey
                ? t("settings.llm.keyConfigured")
                : t("settings.llm.keyMissing")
          }
        >
          <input
            className="data-input"
            type="password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder={
              !requiresKey
                ? t("settings.llm.keyLocalPh")
                : hasKey
                  ? t("settings.llm.keyKeepPh")
                  : "sk-…"
            }
            autoComplete="off"
            disabled={llmBusy || mode === "mock"}
          />
        </Field>
        <div className="settings-actions">
          <Button
            variant="primary"
            onClick={() => void onSaveLlm()}
            disabled={llmBusy}
          >
            {llmBusy ? "…" : t("settings.llm.save")}
          </Button>
          <Button
            variant="secondary"
            onClick={() => void onTestLlm()}
            disabled={llmBusy || mode === "mock"}
          >
            {t("settings.llm.test")}
          </Button>
        </div>
        {llmMsg && <pre className="settings-msg">{llmMsg}</pre>}
      </Card>
    </div>
  );
}
