import { useCallback, useEffect, useMemo, useState } from "react";
import { DataPanel } from "../components/DataPanel";
import type { FontSize } from "../hooks/useUiPrefs";
import {
  LLM_PRESETS,
  PRESET_GROUPS,
  findPreset,
  isLocalBaseUrl,
  matchPresetByBaseUrl,
  type LlmPreset,
} from "../lib/llmPresets";
import type {
  McpServerPublic,
  ProviderPublic,
  SettingsSection,
  ThemeMode,
} from "../lib/types";

type Props = {
  theme: ThemeMode;
  resolved: "dark" | "light";
  fontSize: FontSize;
  providerMode: string;
  dataRoot: string;
  onCycleTheme: () => void;
  onSetTheme: (mode: ThemeMode) => void;
  onSetFontSize: (size: FontSize) => void;
  focusSection?: SettingsSection;
  onProviderSaved?: (mode: string) => void;
  showDataPanel: boolean;
  onToggleDataPanel: () => void;
  exportPass: string;
  onExportPass: (v: string) => void;
  exportBusy: boolean;
  exportMsg: string | null;
  onExport: () => void;
  exportAvailable: boolean;
  uninstallBusy: boolean;
  uninstallPreview: string | null;
  onUninstallInventory: () => void;
  onUninstallDryRun: () => void;
  onUninstallExecute: () => void;
};

const emptyMcp = (): McpServerPublic & { secret?: string } => ({
  id: "",
  command: "",
  args: [],
  readonly: true,
  enabled: true,
  description: "",
  secret_env: "CYBERGUARD_MCP_SECRET",
  secret: "",
});

const HUB_TILES: {
  id: Exclude<SettingsSection, "hub">;
  title: string;
  desc: string;
  badge?: string;
}[] = [
  {
    id: "llm",
    title: "语言模型",
    desc: "云厂商 / 本地 Ollama · LM Studio · vLLM",
    badge: "LLM",
  },
  {
    id: "mcp",
    title: "数据源 MCP",
    desc: "告警 JSON/CSV、stdio 连接器",
    badge: "MCP",
  },
  {
    id: "skills",
    title: "技能 SOP",
    desc: "内置分诊 / CVE / 取证 等 catalog",
    badge: "Skills",
  },
  {
    id: "appearance",
    title: "外观",
    desc: "主题与字号",
    badge: "UI",
  },
  {
    id: "data",
    title: "数据与安全",
    desc: "加密导出 · 卸载",
    badge: "Data",
  },
  {
    id: "about",
    title: "关于",
    desc: "版本与开发版声明",
    badge: "Info",
  },
];

export function SettingsView({
  theme,
  resolved,
  fontSize,
  providerMode,
  dataRoot,
  onCycleTheme,
  onSetTheme,
  onSetFontSize,
  focusSection,
  onProviderSaved,
  showDataPanel,
  onToggleDataPanel,
  exportPass,
  onExportPass,
  exportBusy,
  exportMsg,
  onExport,
  exportAvailable,
  uninstallBusy,
  uninstallPreview,
  onUninstallInventory,
  onUninstallDryRun,
  onUninstallExecute,
}: Props) {
  const api = typeof window !== "undefined" ? window.cyberguard : undefined;

  const [section, setSection] = useState<SettingsSection>(
    focusSection && focusSection !== "hub" ? focusSection : "hub"
  );

  const [mode, setMode] = useState("mock");
  const [presetId, setPresetId] = useState("openai");
  const [baseUrl, setBaseUrl] = useState("https://api.openai.com/v1");
  const [model, setModel] = useState("gpt-4o-mini");
  const [temperature, setTemperature] = useState("0.3");
  const [apiKey, setApiKey] = useState("");
  const [hasKey, setHasKey] = useState(false);
  const [llmMsg, setLlmMsg] = useState<string | null>(null);
  const [llmBusy, setLlmBusy] = useState(false);

  const [servers, setServers] = useState<McpServerPublic[]>([]);
  const [edit, setEdit] = useState<McpServerPublic & { secret?: string }>(
    emptyMcp()
  );
  const [argsText, setArgsText] = useState("");
  const [mcpMsg, setMcpMsg] = useState<string | null>(null);
  const [mcpBusy, setMcpBusy] = useState(false);
  const [discoverMsg, setDiscoverMsg] = useState<string | null>(null);
  const [skills, setSkills] = useState<
    Array<{ name: string; description: string; version?: string; source?: string }>
  >([]);

  const preset = useMemo(() => findPreset(presetId), [presetId]);
  const requiresKey = useMemo(() => {
    if (isLocalBaseUrl(baseUrl)) return false;
    if (preset) return preset.requiresKey;
    return true;
  }, [baseUrl, preset]);

  useEffect(() => {
    if (focusSection) {
      setSection(focusSection);
    }
  }, [focusSection]);

  const loadProvider = useCallback(async () => {
    if (!api?.providerGet) return;
    try {
      const p: ProviderPublic = await api.providerGet();
      setMode(p.mode || "mock");
      setBaseUrl(p.base_url || "https://api.openai.com/v1");
      setModel(p.model || "gpt-4o-mini");
      setTemperature(String(p.temperature ?? 0.3));
      setHasKey(Boolean(p.has_api_key));
      setApiKey("");
      const pid =
        p.preset_id ||
        matchPresetByBaseUrl(p.base_url || "")?.id ||
        "custom";
      setPresetId(pid);
    } catch (e) {
      setLlmMsg(String(e));
    }
  }, [api]);

  const loadMcp = useCallback(async () => {
    if (!api?.mcpConfigList) return;
    try {
      const r = await api.mcpConfigList();
      setServers(r.servers || []);
    } catch (e) {
      setMcpMsg(String(e));
    }
  }, [api]);

  const loadSkills = useCallback(async () => {
    if (!api?.skillsList) return;
    try {
      const r = await api.skillsList();
      setSkills(r.skills || []);
    } catch {
      setSkills([]);
    }
  }, [api]);

  useEffect(() => {
    void loadProvider();
    void loadMcp();
    void loadSkills();
  }, [loadProvider, loadMcp, loadSkills]);

  const applyPreset = (p: LlmPreset) => {
    setPresetId(p.id);
    setBaseUrl(p.baseUrl);
    if (p.models.length) {
      setModel(p.models[0]);
    }
    if (p.id !== "mock") {
      // Selecting a real preset implies live (user can still switch to mock)
      if (mode === "mock") setMode("live");
    }
  };

  const onSaveLlm = async () => {
    if (!api?.providerSet) {
      setLlmMsg("provider API unavailable (open via Electron)");
      return;
    }
    if (mode === "live" && requiresKey && !hasKey && !apiKey.trim()) {
      setLlmMsg("该供应商需要 API key，请先填写");
      return;
    }
    setLlmBusy(true);
    setLlmMsg(null);
    try {
      const payload: {
        mode: string;
        base_url: string;
        model: string;
        temperature: number;
        api_key?: string;
        preset_id?: string;
      } = {
        mode,
        base_url: baseUrl,
        model,
        temperature: Number(temperature) || 0.3,
        preset_id: presetId,
      };
      if (apiKey.trim()) payload.api_key = apiKey.trim();
      const r = await api.providerSet(payload);
      setHasKey(Boolean(r.has_api_key));
      setApiKey("");
      const eff = r.effective?.mode || r.mode || mode;
      setLlmMsg(
        r.ok === false
          ? "save failed"
          : `已保存 · ${eff}${r.local ? " · 本地" : ""}${r.has_api_key ? " · key ✓" : requiresKey ? " · 无 key" : " · 无需 key"}`
      );
      onProviderSaved?.(String(eff));
    } catch (e) {
      setLlmMsg(String(e));
    } finally {
      setLlmBusy(false);
    }
  };

  const onTestLlm = async () => {
    if (!api?.providerTest) {
      setLlmMsg("provider test unavailable");
      return;
    }
    setLlmBusy(true);
    setLlmMsg(null);
    try {
      // Ensure latest form is saved-ish: test uses server-side config
      await onSaveLlm();
      const r = await api.providerTest();
      if (r.ok) {
        setLlmMsg(
          `连通 OK · ${r.mode || "?"} · ${r.latency_ms ?? "?"}ms` +
            (r.message ? ` · ${r.message}` : "")
        );
      } else {
        setLlmMsg(`连通失败 · ${r.error || "unknown"}`);
      }
    } catch (e) {
      setLlmMsg(String(e));
    } finally {
      setLlmBusy(false);
    }
  };

  const onSelectServer = (s: McpServerPublic) => {
    setEdit({ ...s, secret: "" });
    setArgsText((s.args || []).join("\n"));
    setMcpMsg(null);
  };

  const onNewServer = () => {
    setEdit(emptyMcp());
    setArgsText("");
    setMcpMsg(null);
  };

  const onSaveMcp = async () => {
    if (!api?.mcpConfigUpsert) {
      setMcpMsg("mcp config API unavailable");
      return;
    }
    if (!edit.id.trim() || !edit.command.trim()) {
      setMcpMsg("id and command required");
      return;
    }
    setMcpBusy(true);
    setMcpMsg(null);
    try {
      const args = argsText
        .split("\n")
        .map((l) => l.trim())
        .filter(Boolean);
      const payload: Record<string, unknown> = {
        id: edit.id.trim(),
        command: edit.command.trim(),
        args,
        readonly: edit.readonly,
        enabled: edit.enabled,
        description: edit.description || "",
        secret_env: edit.secret_env || "CYBERGUARD_MCP_SECRET",
        timeout_seconds: edit.timeout_seconds ?? 30,
      };
      if (edit.secret?.trim()) payload.secret = edit.secret.trim();
      const r = await api.mcpConfigUpsert(payload);
      setMcpMsg(r.ok === false ? "upsert failed" : `Saved ${edit.id}`);
      setEdit((e) => ({
        ...e,
        secret: "",
        has_secret: Boolean(r.server?.has_secret || e.has_secret || edit.secret),
      }));
      await loadMcp();
    } catch (e) {
      setMcpMsg(String(e));
    } finally {
      setMcpBusy(false);
    }
  };

  const onDeleteMcp = async () => {
    if (!api?.mcpConfigDelete || !edit.id.trim()) return;
    setMcpBusy(true);
    try {
      await api.mcpConfigDelete(edit.id.trim());
      setMcpMsg(`Deleted ${edit.id}`);
      onNewServer();
      await loadMcp();
    } catch (e) {
      setMcpMsg(String(e));
    } finally {
      setMcpBusy(false);
    }
  };

  const onBrowseCommand = async () => {
    if (!api?.pickFile) {
      setMcpMsg("file picker unavailable");
      return;
    }
    const r = await api.pickFile({ title: "Select MCP command binary" });
    if (r?.path) setEdit((e) => ({ ...e, command: r.path! }));
  };

  const onDiscover = async () => {
    if (!api?.mcpDiscover) {
      setDiscoverMsg("discover unavailable");
      return;
    }
    setDiscoverMsg("discovering…");
    try {
      const r = await api.mcpDiscover("readonly");
      const tools = (r.tools || []).map((t) => t.name).join(", ") || "(none)";
      setDiscoverMsg(
        `servers: ${(r.servers || []).join(", ") || "—"} · tools: ${tools}`
      );
    } catch (e) {
      setDiscoverMsg(String(e));
    }
  };

  const onInstallDemo = async () => {
    if (!api?.mcpConfigInstallDemo) {
      setMcpMsg("install demo API unavailable");
      return;
    }
    setMcpBusy(true);
    setMcpMsg(null);
    try {
      const r = await api.mcpConfigInstallDemo();
      setMcpMsg(
        r.ok === false ? "install demo failed" : "已安装 echo 演示 MCP"
      );
      await loadMcp();
      if (r.server) onSelectServer(r.server);
    } catch (e) {
      setMcpMsg(String(e));
    } finally {
      setMcpBusy(false);
    }
  };

  const onInstallFileAlerts = async (pickPath: boolean) => {
    if (!api?.mcpConfigInstallFileAlerts) {
      setMcpMsg("install file-alerts API unavailable");
      return;
    }
    setMcpBusy(true);
    setMcpMsg(null);
    try {
      let path: string | undefined;
      if (pickPath && api.pickFile) {
        const picked = await api.pickFile({
          title: "Select alerts JSON or CSV",
          properties: ["openFile"],
        });
        if (!picked?.path || picked.canceled) {
          setMcpMsg("canceled");
          return;
        }
        path = picked.path;
      }
      const r = await api.mcpConfigInstallFileAlerts(path);
      setMcpMsg(
        r.ok === false
          ? "install file-alerts failed"
          : `已安装 file-alerts · ${r.server?.description || "sample"}`
      );
      await loadMcp();
      if (r.server) onSelectServer(r.server);
    } catch (e) {
      setMcpMsg(String(e));
    } finally {
      setMcpBusy(false);
    }
  };

  const onThemeSelect = async (next: ThemeMode) => {
    onSetTheme(next);
    try {
      await api?.prefsSet?.({ theme: next });
    } catch {
      /* ignore */
    }
  };

  const onFontSelect = async (next: FontSize) => {
    onSetFontSize(next);
    try {
      await api?.prefsSet?.({ font_size: next });
    } catch {
      /* ignore */
    }
  };

  const header =
    section === "hub" ? (
      <>
        <h1>设置</h1>
        <p className="lede">
          选择一项进行配置。当前 LLM：<strong>{providerMode}</strong>
        </p>
      </>
    ) : (
      <div className="settings-detail-head">
        <button
          type="button"
          className="ghost-btn settings-back"
          onClick={() => setSection("hub")}
        >
          ← 全部设置
        </button>
        <h1>
          {HUB_TILES.find((t) => t.id === section)?.title || "设置"}
        </h1>
      </div>
    );

  return (
    <div className="view-pane view-enter settings-view">
      {header}

      {section === "hub" && (
        <div className="settings-hub">
          {HUB_TILES.map((t) => (
            <button
              key={t.id}
              type="button"
              className="settings-tile"
              onClick={() => setSection(t.id)}
            >
              <span className="settings-tile-badge">{t.badge}</span>
              <span className="settings-tile-title">{t.title}</span>
              <span className="settings-tile-desc">{t.desc}</span>
            </button>
          ))}
        </div>
      )}

      {section === "llm" && (
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
      )}

      {section === "mcp" && (
        <div className="settings-detail">
          <div className="settings-card">
            <h3>快捷安装</h3>
            <div className="empty-actions">
              <button
                type="button"
                className="primary"
                onClick={() => void onInstallFileAlerts(false)}
                disabled={mcpBusy}
              >
                文件告警 MCP（样例）
              </button>
              <button
                type="button"
                className="secondary"
                onClick={() => void onInstallFileAlerts(true)}
                disabled={mcpBusy}
              >
                从 JSON/CSV 安装…
              </button>
              <button
                type="button"
                className="secondary"
                onClick={() => void onInstallDemo()}
                disabled={mcpBusy}
              >
                Echo 演示
              </button>
              <button
                type="button"
                className="secondary"
                onClick={() => void onDiscover()}
              >
                发现工具
              </button>
            </div>
            {discoverMsg && <pre className="data-msg">{discoverMsg}</pre>}
          </div>

          <div className="settings-card">
            <h3>已配置服务器</h3>
            <div className="mcp-list">
              {servers.length === 0 && (
                <p className="muted-copy">尚未配置 MCP</p>
              )}
              {servers.map((s) => (
                <button
                  key={s.id}
                  type="button"
                  className={`mcp-list-item${edit.id === s.id ? " active" : ""}`}
                  onClick={() => onSelectServer(s)}
                >
                  <strong>{s.id}</strong>
                  <span className="muted-copy">
                    {s.enabled ? "on" : "off"} · {s.readonly ? "ro" : "rw"}
                    {s.has_secret ? " · secret" : ""}
                  </span>
                  <div className="mono-xs">{s.command}</div>
                </button>
              ))}
            </div>
            <div className="empty-actions mt-10">
              <button type="button" className="secondary" onClick={onNewServer}>
                + 新建
              </button>
            </div>
          </div>

          <div className="settings-card">
            <h3>编辑</h3>
            <label className="field-label">
              ID
              <input
                className="data-input"
                value={edit.id}
                onChange={(e) => setEdit({ ...edit, id: e.target.value })}
                disabled={mcpBusy}
              />
            </label>
            <label className="field-label">
              Command
              <div className="row">
                <input
                  className="data-input"
                  style={{ marginBottom: 0, flex: 1 }}
                  value={edit.command}
                  onChange={(e) =>
                    setEdit({ ...edit, command: e.target.value })
                  }
                  disabled={mcpBusy}
                />
                <button
                  type="button"
                  className="secondary"
                  onClick={() => void onBrowseCommand()}
                >
                  Browse…
                </button>
              </div>
            </label>
            <label className="field-label">
              Args（每行一个）
              <textarea
                className="plan-edit"
                rows={4}
                value={argsText}
                onChange={(e) => setArgsText(e.target.value)}
                disabled={mcpBusy}
              />
            </label>
            <label className="field-label">
              Description
              <input
                className="data-input"
                value={edit.description || ""}
                onChange={(e) =>
                  setEdit({ ...edit, description: e.target.value })
                }
                disabled={mcpBusy}
              />
            </label>
            <label className="field-label">
              Secret{" "}
              {edit.has_secret ? (
                <span className="pill ok">已配置</span>
              ) : (
                <span className="pill warn">无</span>
              )}
              <input
                className="data-input"
                type="password"
                value={edit.secret || ""}
                onChange={(e) => setEdit({ ...edit, secret: e.target.value })}
                placeholder="留空保留"
                autoComplete="off"
                disabled={mcpBusy}
              />
            </label>
            <div className="row mt-8">
              <label className="check-label">
                <input
                  type="checkbox"
                  checked={edit.enabled}
                  onChange={(e) =>
                    setEdit({ ...edit, enabled: e.target.checked })
                  }
                />{" "}
                enabled
              </label>
              <label className="check-label">
                <input
                  type="checkbox"
                  checked={edit.readonly}
                  onChange={(e) =>
                    setEdit({ ...edit, readonly: e.target.checked })
                  }
                />{" "}
                readonly
              </label>
            </div>
            <div className="empty-actions mt-10">
              <button
                type="button"
                className="primary"
                onClick={() => void onSaveMcp()}
                disabled={mcpBusy}
              >
                保存
              </button>
              <button
                type="button"
                className="btn-reject"
                onClick={() => void onDeleteMcp()}
                disabled={mcpBusy || !edit.id}
              >
                删除
              </button>
            </div>
            {mcpMsg && <pre className="data-msg">{mcpMsg}</pre>}
          </div>
        </div>
      )}

      {section === "skills" && (
        <div className="settings-detail">
          <div className="settings-card">
            <h3>内置技能</h3>
            <p className="data-hint">
              仅 catalog（name + description）。正文经{" "}
              <code className="mono">load_skill</code> 按需加载。
            </p>
            {skills.length === 0 ? (
              <p className="muted-copy">暂无（sidecar 离线？）</p>
            ) : (
              <ul className="skill-catalog">
                {skills.map((s) => (
                  <li key={s.name}>
                    <strong>{s.name}</strong>
                    {s.version ? <span className="pill">v{s.version}</span> : null}
                    {s.source ? (
                      <span className="pill accent">{s.source}</span>
                    ) : null}
                    <div className="muted-copy">{s.description}</div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}

      {section === "appearance" && (
        <div className="settings-detail">
          <div className="settings-card">
            <h3>主题与字号</h3>
            <label className="field-label">
              Theme
              <select
                value={theme}
                onChange={(e) => void onThemeSelect(e.target.value as ThemeMode)}
              >
                <option value="dark">dark</option>
                <option value="light">light</option>
                <option value="system">system</option>
              </select>
            </label>
            <label className="field-label">
              Font size
              <select
                value={fontSize}
                onChange={(e) => void onFontSelect(e.target.value as FontSize)}
              >
                <option value="small">small</option>
                <option value="medium">medium</option>
                <option value="large">large</option>
              </select>
            </label>
            <div className="empty-actions mt-10">
              <button type="button" className="secondary" onClick={onCycleTheme}>
                循环主题
              </button>
            </div>
            <p className="muted-copy mt-10">
              resolved: {resolved} · ⌘1 Workbench · ⌘2 Evidence · ⌘, Settings
            </p>
          </div>
        </div>
      )}

      {section === "data" && (
        <div className="settings-detail">
          <div className="settings-card">
            <h3>数据与安全</h3>
            <p className="data-hint">
              data_root:{" "}
              <code className="mono mono-sm">{dataRoot || "—"}</code>
            </p>
            <DataPanel
              open={showDataPanel || true}
              onToggle={onToggleDataPanel}
              exportPass={exportPass}
              onExportPass={onExportPass}
              exportBusy={exportBusy}
              exportMsg={exportMsg}
              onExport={onExport}
              exportAvailable={exportAvailable}
              uninstallBusy={uninstallBusy}
              uninstallPreview={uninstallPreview}
              onInventory={onUninstallInventory}
              onDryRun={onUninstallDryRun}
              onExecute={onUninstallExecute}
            />
          </div>
        </div>
      )}

      {section === "about" && (
        <div className="settings-detail">
          <div className="settings-card">
            <h3>关于</h3>
            <p>
              CyberGuard Desktop · development build ·{" "}
              <strong>not notarized · not for distribution</strong>.
            </p>
            <p className="muted-copy mt-10">
              Plan Mode 为自批准（approval_type=self），超时=拒绝。本地哈希链 ≠
              WORM。单兵工具，不做 Web 21 Tab 后台。
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
