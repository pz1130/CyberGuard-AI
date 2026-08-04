import type { ThemeMode } from "../lib/types";

type Props = {
  theme: ThemeMode;
  resolved: "dark" | "light";
  providerMode: string;
  dataRoot: string;
  onCycleTheme: () => void;
  onOpenDataPanel: () => void;
};

export function SettingsView({
  theme,
  resolved,
  providerMode,
  dataRoot,
  onCycleTheme,
  onOpenDataPanel,
}: Props) {
  return (
    <div className="view-pane view-enter">
      <h1>Settings</h1>
      <p className="lede">
        完整 LLM / MCP GUI 在 P1。下方为当前状态与数据安全（导出/卸载）。
      </p>
      <div className="settings-grid">
        <div className="settings-card" id="settings-llm">
          <h3>LLM Provider</h3>
          <p>
            Mode: <strong>{providerMode}</strong> · data_root:{" "}
            <code className="mono mono-sm">{dataRoot || "—"}</code>
          </p>
          <p className="mt-8">
            配置文件：
            <code className="mono">provider.json</code> / Keychain。P1
            将提供表单与连通测试。
          </p>
        </div>
        <div className="settings-card" id="settings-mcp">
          <h3>MCP Servers</h3>
          <p>
            配置文件：
            <code className="mono">mcp_servers.json</code>
            。Secrets 进 Keychain slot。P1 将提供列表与编辑器。
          </p>
        </div>
        <div className="settings-card" id="settings-appearance">
          <h3>Appearance</h3>
          <p>
            Theme: <strong>{theme}</strong> (resolved <strong>{resolved}</strong>
            )
          </p>
          <div className="empty-actions mt-10">
            <button type="button" className="secondary" onClick={onCycleTheme}>
              Cycle theme (dark → light → system)
            </button>
          </div>
        </div>
        <div className="settings-card" id="settings-data">
          <h3>Data &amp; Security</h3>
          <p>加密导出与卸载（M7）。</p>
          <div className="empty-actions mt-10">
            <button
              type="button"
              className="secondary"
              onClick={onOpenDataPanel}
            >
              Open Export / Uninstall panel
            </button>
          </div>
        </div>
        <div className="settings-card">
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
