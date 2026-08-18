import type { ReactElement } from "react";
import {
  LLM_PRESETS,
  PRESET_GROUPS,
  matchPresetByBaseUrl,
} from "../../lib/llmPresets";
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
      <div className="settings-card">
        <h3>模式</h3>
        <p className="data-hint">
          mock 不连网；live 使用 OpenAI 兼容 Chat Completions。本地模型通常无需
          API key。
        </p>
        <label className="field-label">
          运行模式
          <select
            value={mode}
            onChange={(e) => setMode(e.target.value)}
            disabled={llmBusy}
          >
            <option value="mock">mock（演示）</option>
            <option value="live">live（云 / 本地）</option>
          </select>
        </label>
      </div>

      <div className="settings-card">
        <h3>供应商预设</h3>
        <p className="data-hint">
          点选后自动填入 Base URL 与推荐模型，仍可手动改。
        </p>
        {PRESET_GROUPS.map((g) => (
          <div key={g.id} className="preset-group">
            <div className="preset-group-label">{g.label}</div>
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
          </div>
        ))}
      </div>

      <div className="settings-card">
        <h3>连接参数</h3>
        {preset?.hint ? (
          <p className="data-hint">{preset.hint}</p>
        ) : null}
        <label className="field-label">
          Base URL
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
        </label>
        <label className="field-label">
          Model
          {preset && preset.models.length > 0 ? (
            <select
              value={
                preset.models.includes(model) ? model : "__custom__"
              }
              onChange={(e) => {
                if (e.target.value !== "__custom__") {
                  setModel(e.target.value);
                }
              }}
              disabled={llmBusy || mode === "mock"}
            >
              {preset.models.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
              <option value="__custom__">自定义…</option>
            </select>
          ) : null}
          <input
            className="data-input"
            value={model}
            onChange={(e) => setModel(e.target.value)}
            disabled={llmBusy || mode === "mock"}
            placeholder="模型名"
          />
        </label>
        <label className="field-label">
          Temperature
          <input
            className="data-input"
            value={temperature}
            onChange={(e) => setTemperature(e.target.value)}
            disabled={llmBusy || mode === "mock"}
          />
        </label>
        <label className="field-label">
          API key{" "}
          {!requiresKey ? (
            <span className="pill accent">本地可选</span>
          ) : hasKey ? (
            <span className="pill ok">已配置</span>
          ) : (
            <span className="pill warn">未配置</span>
          )}
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
        </label>
        <div className="empty-actions mt-10">
          <button
            type="button"
            className="primary"
            onClick={() => void onSaveLlm()}
            disabled={llmBusy}
          >
            {llmBusy ? "…" : "保存"}
          </button>
          <button
            type="button"
            className="secondary"
            onClick={() => void onTestLlm()}
            disabled={llmBusy || mode === "mock"}
          >
            测试连通
          </button>
        </div>
        {llmMsg && <pre className="data-msg">{llmMsg}</pre>}
      </div>
    </div>
  );
}
