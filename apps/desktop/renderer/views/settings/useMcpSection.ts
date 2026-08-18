import { useCallback, useEffect, useState } from "react";
import type { McpServerPublic } from "../../lib/types";

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

export function useMcpSection() {
  const api = typeof window !== "undefined" ? window.cyberguard : undefined;

  const [servers, setServers] = useState<McpServerPublic[]>([]);
  const [edit, setEdit] = useState<McpServerPublic & { secret?: string }>(
    emptyMcp()
  );
  const [argsText, setArgsText] = useState("");
  const [mcpMsg, setMcpMsg] = useState<string | null>(null);
  const [mcpBusy, setMcpBusy] = useState(false);
  const [discoverMsg, setDiscoverMsg] = useState<string | null>(null);

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
    void loadMcp();
  }, [loadMcp]);

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

  return {
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
  };
}
