const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("cyberguard", {
  ping: () => ipcRenderer.invoke("sidecar:ping"),
  capabilities: (tier) => ipcRenderer.invoke("sidecar:capabilities", tier),
  run: (task, tier, sessionId) =>
    ipcRenderer.invoke("sidecar:run", { task, tier, sessionId }),
  abort: (runId) => ipcRenderer.invoke("sidecar:abort", runId),
  steer: (runId, message) =>
    ipcRenderer.invoke("sidecar:steer", { runId, message }),
  listSessions: () => ipcRenderer.invoke("sidecar:sessions:list"),
  createSession: (title, tier) =>
    ipcRenderer.invoke("sidecar:sessions:create", { title, tier }),
  sessionEvents: (sessionId) =>
    ipcRenderer.invoke("sidecar:sessions:events", sessionId),
  deleteSession: (sessionId) =>
    ipcRenderer.invoke("sidecar:sessions:delete", { sessionId }),
  skillsList: () => ipcRenderer.invoke("sidecar:skills:list"),
  skillsGet: (name, source) =>
    ipcRenderer.invoke("sidecar:skills:get", { name, source }),
  skillsSaveDraft: (params) =>
    ipcRenderer.invoke("sidecar:skills:save-draft", params || {}),
  skillsImport: (params) =>
    ipcRenderer.invoke("sidecar:skills:import", params || {}),
  skillsApprove: (name) =>
    ipcRenderer.invoke("sidecar:skills:approve", { name }),
  skillsDelete: (name, source) =>
    ipcRenderer.invoke("sidecar:skills:delete", { name, source }),
  skillsFork: (name) => ipcRenderer.invoke("sidecar:skills:fork", { name }),
  resume: (runId) => ipcRenderer.invoke("sidecar:resume", { runId }),
  planApprove: (planId, revisedPlan) =>
    ipcRenderer.invoke("sidecar:plan:approve", { planId, revisedPlan }),
  planReject: (planId, reason) =>
    ipcRenderer.invoke("sidecar:plan:reject", { planId, reason }),
  planList: () => ipcRenderer.invoke("sidecar:plan:list"),
  // P1 settings
  providerGet: () => ipcRenderer.invoke("sidecar:provider:get"),
  providerSet: (params) => ipcRenderer.invoke("sidecar:provider:set", params || {}),
  providerTest: () => ipcRenderer.invoke("sidecar:provider:test"),
  prefsGet: () => ipcRenderer.invoke("sidecar:prefs:get"),
  prefsSet: (params) => ipcRenderer.invoke("sidecar:prefs:set", params || {}),
  mcpConfigList: () => ipcRenderer.invoke("sidecar:mcp-config:list"),
  mcpConfigUpsert: (params) =>
    ipcRenderer.invoke("sidecar:mcp-config:upsert", params || {}),
  mcpConfigDelete: (id) =>
    ipcRenderer.invoke("sidecar:mcp-config:delete", { id }),
  mcpConfigInstallDemo: () =>
    ipcRenderer.invoke("sidecar:mcp-config:install-demo"),
  mcpConfigInstallFileAlerts: (path) =>
    ipcRenderer.invoke("sidecar:mcp-config:install-file-alerts", { path }),
  mcpDiscover: (tier) => ipcRenderer.invoke("sidecar:mcp:discover", { tier }),
  pickFile: (opts) => ipcRenderer.invoke("dialog:pick-file", opts || {}),
  showItemInFolder: (path) =>
    ipcRenderer.invoke("shell:show-item-in-folder", { path }),
  // P2 evidence
  evidenceList: (limit) =>
    ipcRenderer.invoke("sidecar:evidence:list", { limit }),
  evidenceRegister: (path, note) =>
    ipcRenderer.invoke("sidecar:evidence:register", { path, note }),
  evidenceVerify: (evidenceId) =>
    ipcRenderer.invoke("sidecar:evidence:verify", { evidenceId }),
  // M7 delivery
  exportEncrypted: (passphrase) =>
    ipcRenderer.invoke("sidecar:export:encrypted", { passphrase }),
  uninstallInventory: () => ipcRenderer.invoke("sidecar:uninstall:inventory"),
  uninstallExecute: (opts) =>
    ipcRenderer.invoke("sidecar:uninstall:execute", opts || {}),
  onEvent: (handler) => {
    const listener = (_event, payload) => handler(payload);
    ipcRenderer.on("sidecar:event", listener);
    return () => ipcRenderer.removeListener("sidecar:event", listener);
  },
  onOpenDataPanel: (handler) => {
    const listener = () => handler();
    ipcRenderer.on("ui:open-export", listener);
    ipcRenderer.on("ui:open-uninstall", listener);
    return () => {
      ipcRenderer.removeListener("ui:open-export", listener);
      ipcRenderer.removeListener("ui:open-uninstall", listener);
    };
  },
});
