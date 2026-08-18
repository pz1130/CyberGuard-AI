import type { ReactElement } from "react";
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
  return (
    <div className="settings-detail">
      <Card>
        <h3 className="settings-card-title">模式</h3>
        <p className="settings-hint">
          mock 不连网；live 使用 OpenAI 兼容 Chat Completions。本地模型通常无需
          API key。
        </p>
        <Field label="运行模式">
          <Select
            ariaLabel="运行模式"
            value={mode as "mock" | "live"}
            onChange={setMode}
            disabled={llmBusy}
            options={[
              { value: "mock", label: "mock（演示）" },
              { value: "live", label: "live（云 / 本地）" },
            ]}
          />
        </Field>
      </Card>

      <Card>
        <h3 className="settings-card-title">供应商预设</h3>
        <p className="settings-hint">
          点选后自动填入 Base URL 与推荐模型，仍可手动改。
        </p>
        {PRESET_GROUPS.map((g, i) => (
          <Disclosure key={g.id} summary={g.label} defaultOpen={i === 0}>
            <div className="preset-grid">
              {LLM_PRESETS.filter((p) => p.group === g.id).map((p) => (
                <button
                  key={p.id}
                  type="button"
                  className={`preset-chip${presetId === p.id ? " active" : ""}`}
                  onClick={() => applyPreset(p)}
                  disabled={llmBusy || mode === "mock"}
                >
                  {p.label}
                  {!p.requiresKey ? (
                    <span className="preset-tag">无 key</span>
                  ) : null}
                </button>
              ))}
            </div>
          </Disclosure>
        ))}
      </Card>

      <Card>
        <h3 className="settings-card-title">连接参数</h3>
        {preset?.hint ? <p className="settings-hint">{preset.hint}</p> : null}
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
            placeholder="https://api.openai.com/v1 或 http://127.0.0.1:11434/v1"
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
                { value: "__custom__", label: "自定义…" },
              ]}
            />
          ) : null}
          <input
            className="data-input"
            value={model}
            onChange={(e) => setModel(e.target.value)}
            disabled={llmBusy || mode === "mock"}
            placeholder="模型名"
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
              ? "本地可选"
              : hasKey
                ? "已配置（留空保留原 key）"
                : "未配置"
          }
        >
          <input
            className="data-input"
            type="password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder={
              !requiresKey
                ? "本地一般可留空"
                : hasKey
                  ? "••••••••  （留空保留原 key）"
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
            {llmBusy ? "…" : "保存"}
          </Button>
          <Button
            variant="secondary"
            onClick={() => void onTestLlm()}
            disabled={llmBusy || mode === "mock"}
          >
            测试连通
          </Button>
        </div>
        {llmMsg && <pre className="settings-msg">{llmMsg}</pre>}
      </Card>
    </div>
  );
}
