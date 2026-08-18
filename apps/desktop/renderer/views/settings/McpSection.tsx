import type { ReactElement } from "react";
import { Button, Card, Field } from "../../ui";
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
      <Card>
        <h3 className="settings-card-title">快捷安装</h3>
        <div className="settings-actions" style={{ marginTop: 0 }}>
          <Button
            variant="secondary"
            onClick={() => void onInstallFileAlerts(false)}
            disabled={mcpBusy}
          >
            文件告警 MCP（样例）
          </Button>
          <Button
            variant="ghost"
            onClick={() => void onInstallFileAlerts(true)}
            disabled={mcpBusy}
          >
            从 JSON/CSV 安装…
          </Button>
          <Button
            variant="ghost"
            onClick={() => void onInstallDemo()}
            disabled={mcpBusy}
          >
            Echo 演示
          </Button>
          <Button variant="ghost" onClick={() => void onDiscover()}>
            发现工具
          </Button>
        </div>
        {discoverMsg && <pre className="settings-msg">{discoverMsg}</pre>}
      </Card>

      <Card>
        <h3 className="settings-card-title">已配置服务器</h3>
        <div className="settings-list">
          {servers.length === 0 && (
            <p className="settings-hint">尚未配置 MCP</p>
          )}
          {servers.map((s) => (
            <button
              key={s.id}
              type="button"
              className={`mcp-list-item${edit.id === s.id ? " active" : ""}`}
              onClick={() => onSelectServer(s)}
            >
              <strong>{s.id}</strong>
              <span className="settings-hint" style={{ margin: 0 }}>
                {s.enabled ? "on" : "off"} · {s.readonly ? "ro" : "rw"}
                {s.has_secret ? " · secret" : ""}
              </span>
              <div className="mono-xs">{s.command}</div>
            </button>
          ))}
        </div>
        <div className="settings-actions">
          <Button variant="secondary" onClick={onNewServer}>
            + 新建
          </Button>
        </div>
      </Card>

      <Card>
        <h3 className="settings-card-title">编辑</h3>
        <Field label="ID">
          <input
            className="data-input"
            value={edit.id}
            onChange={(e) => setEdit({ ...edit, id: e.target.value })}
            disabled={mcpBusy}
          />
        </Field>
        <Field label="Command">
          <div className="settings-row-pair">
            <input
              className="data-input"
              style={{ marginBottom: 0, flex: 1 }}
              value={edit.command}
              onChange={(e) =>
                setEdit({ ...edit, command: e.target.value })
              }
              disabled={mcpBusy}
            />
            <Button
              variant="ghost"
              onClick={() => void onBrowseCommand()}
            >
              Browse…
            </Button>
          </div>
        </Field>
        <Field label="Args（每行一个）">
          <textarea
            className="plan-edit"
            rows={4}
            value={argsText}
            onChange={(e) => setArgsText(e.target.value)}
            disabled={mcpBusy}
          />
        </Field>
        <Field label="Description">
          <input
            className="data-input"
            value={edit.description || ""}
            onChange={(e) =>
              setEdit({ ...edit, description: e.target.value })
            }
            disabled={mcpBusy}
          />
        </Field>
        <Field
          label="Secret"
          hint={edit.has_secret ? "已配置" : "无"}
        >
          <input
            className="data-input"
            type="password"
            value={edit.secret || ""}
            onChange={(e) => setEdit({ ...edit, secret: e.target.value })}
            placeholder="留空保留"
            autoComplete="off"
            disabled={mcpBusy}
          />
        </Field>
        <div className="check-row">
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
        <div className="settings-actions">
          <Button
            variant="primary"
            onClick={() => void onSaveMcp()}
            disabled={mcpBusy}
          >
            保存
          </Button>
          <Button
            variant="danger"
            onClick={() => void onDeleteMcp()}
            disabled={mcpBusy || !edit.id}
          >
            删除
          </Button>
        </div>
        {mcpMsg && <pre className="settings-msg">{mcpMsg}</pre>}
      </Card>
    </div>
  );
}
