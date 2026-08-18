import type { ReactElement } from "react";
import type { McpSectionModel } from "./useMcpSection";

export type McpSectionProps = McpSectionModel;

export function McpSection({
  servers,
  edit,
  setEdit,
  argsText,
  setArgsText,
  mcpMsg,
  mcpBusy,
  discoverMsg,
  onSelectServer,
  onNewServer,
  onSaveMcp,
  onDeleteMcp,
  onBrowseCommand,
  onDiscover,
  onInstallDemo,
  onInstallFileAlerts,
}: McpSectionProps): ReactElement {
  return (
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
  );
}
