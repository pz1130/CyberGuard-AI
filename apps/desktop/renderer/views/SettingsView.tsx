import { useCallback, useEffect, useState } from "react";
import { DataPanel } from "../components/DataPanel";
import type { FontSize } from "../hooks/useUiPrefs";
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
  // data panel (export/uninstall)
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

  const [mode, setMode] = useState("mock");
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

  useEffect(() => {
    void loadProvider();
    void loadMcp();
  }, [loadProvider, loadMcp]);

  useEffect(() => {
    if (!focusSection) return;
    const id = `settings-${focusSection}`;
    requestAnimationFrame(() => {
      document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }, [focusSection]);

  const onSaveLlm = async () => {
    if (!api?.providerSet) {
      setLlmMsg("provider API unavailable (open via Electron)");
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
      } = {
        mode,
        base_url: baseUrl,
        model,
        temperature: Number(temperature) || 0.3,
      };
      if (apiKey.trim()) payload.api_key = apiKey.trim();
      const r = await api.providerSet(payload);
      setHasKey(Boolean(r.has_api_key));
      setApiKey("");
      setLlmMsg(
        r.ok === false
          ? "save failed"
          : `Saved · mode=${r.mode} · key ${r.has_api_key ? "configured" : "missing"}`
      );
      onProviderSaved?.(r.mode || mode);
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
      const r = await api.providerTest();
      if (r.ok) {
        setLlmMsg(
          `OK · ${r.mode || "?"} · ${r.latency_ms ?? "?"}ms` +
            (r.message ? ` · ${r.message}` : "")
        );
      } else {
        setLlmMsg(`FAIL · ${r.error || "unknown"}`);
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
      setEdit((e) => ({ ...e, secret: "", has_secret: Boolean(r.server?.has_secret || e.has_secret || edit.secret) }));
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

  const onThemeSelect = async (next: ThemeMode) => {
    onSetTheme(next);
    try {
      await api?.prefsSet?.({ theme: next });
    } catch {
      /* localStorage still holds theme via useTheme */
    }
  };

  const onFontSelect = async (next: FontSize) => {
    onSetFontSize(next);
    try {
      await api?.prefsSet?.({ font_size: next });
    } catch {
      /* localStorage fallback */
    }
  };

  return (
    <div className="view-pane view-enter">
      <h1>Settings</h1>
      <p className="lede">
        配置 LLM 与 MCP（Keychain 存密钥，界面不回显）。当前 runtime mode:{" "}
        <strong>{providerMode}</strong>
      </p>
      <div className="settings-grid">
        <div className="settings-card" id="settings-llm">
          <h3>LLM Provider</h3>
          <p className="data-hint">
            API key 写入 Keychain / secrets store；provider.json 不存明文 key。
          </p>
          <label className="field-label">
            Mode
            <select
              value={mode}
              onChange={(e) => setMode(e.target.value)}
              disabled={llmBusy}
            >
              <option value="mock">mock</option>
              <option value="live">live</option>
            </select>
          </label>
          <label className="field-label">
            Base URL
            <input
              className="data-input"
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              disabled={llmBusy || mode === "mock"}
            />
          </label>
          <label className="field-label">
            Model
            <input
              className="data-input"
              value={model}
              onChange={(e) => setModel(e.target.value)}
              disabled={llmBusy}
            />
          </label>
          <label className="field-label">
            Temperature
            <input
              className="data-input"
              value={temperature}
              onChange={(e) => setTemperature(e.target.value)}
              disabled={llmBusy}
            />
          </label>
          <label className="field-label">
            API key{" "}
            {hasKey ? (
              <span className="pill ok">key configured</span>
            ) : (
              <span className="pill warn">no key</span>
            )}
            <input
              className="data-input"
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder={hasKey ? "••••••••  (leave blank to keep)" : "sk-…"}
              autoComplete="off"
              disabled={llmBusy}
            />
          </label>
          <div className="empty-actions mt-10">
            <button
              type="button"
              className="primary"
              onClick={() => void onSaveLlm()}
              disabled={llmBusy}
            >
              {llmBusy ? "…" : "Save"}
            </button>
            <button
              type="button"
              className="secondary"
              onClick={() => void onTestLlm()}
              disabled={llmBusy}
            >
              Test
            </button>
          </div>
          {llmMsg && <pre className="data-msg">{llmMsg}</pre>}
          <p className="muted-copy mt-8">
            data_root: <code className="mono mono-sm">{dataRoot || "—"}</code>
          </p>
        </div>

        <div className="settings-card" id="settings-mcp">
          <h3>MCP Servers</h3>
          <p className="data-hint">
            列表不含 secret 明文。slot 按 server id 隔离（Keychain）。
          </p>
          <div className="mcp-list">
            {servers.length === 0 && (
              <p className="muted-copy">No servers yet.</p>
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
              + New
            </button>
            <button
              type="button"
              className="secondary"
              onClick={() => void onDiscover()}
            >
              Discover tools
            </button>
          </div>
          {discoverMsg && <pre className="data-msg">{discoverMsg}</pre>}

          <div className="mcp-editor mt-12">
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
              Args (one per line)
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
                <span className="pill ok">slot set</span>
              ) : (
                <span className="pill warn">no slot</span>
              )}
              <input
                className="data-input"
                type="password"
                value={edit.secret || ""}
                onChange={(e) => setEdit({ ...edit, secret: e.target.value })}
                placeholder="leave blank to keep"
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
                Save server
              </button>
              <button
                type="button"
                className="btn-reject"
                onClick={() => void onDeleteMcp()}
                disabled={mcpBusy || !edit.id}
              >
                Delete
              </button>
            </div>
            {mcpMsg && <pre className="data-msg">{mcpMsg}</pre>}
          </div>
        </div>

        <div className="settings-card" id="settings-appearance">
          <h3>Appearance</h3>
          <p>
            Theme: <strong>{theme}</strong> (resolved{" "}
            <strong>{resolved}</strong>) · Font: <strong>{fontSize}</strong>
          </p>
          <label className="field-label">
            Theme
            <select
              value={theme}
              onChange={(e) => void onThemeSelect(e.target.value as ThemeMode)}
            >
              <option value="dark">dark (default)</option>
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
              <option value="small">small (13px)</option>
              <option value="medium">medium (14px)</option>
              <option value="large">large (16px)</option>
            </select>
          </label>
          <div className="empty-actions mt-10">
            <button type="button" className="secondary" onClick={onCycleTheme}>
              Cycle theme
            </button>
          </div>
          <p className="muted-copy mt-10">
            Shortcuts: ⌘1 Workbench · ⌘2 Evidence · ⌘, Settings · ⌘N New ·
            ⌘Enter Run
          </p>
        </div>

        <div className="settings-card" id="settings-data">
          <h3>Data &amp; Security</h3>
          <p>加密导出与卸载（M7）。</p>
          <DataPanel
            open={showDataPanel}
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

        <div className="settings-card" id="settings-about">
          <h3>About</h3>
          <p>
            CyberGuard Desktop · development build · not notarized · not for
            distribution. Local hash chain ≠ WORM. 自批准 ≠ 职责分离审批.
          </p>
        </div>
      </div>
    </div>
  );
}
