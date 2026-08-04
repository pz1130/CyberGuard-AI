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
  planApprove: (planId, revisedPlan) =>
    ipcRenderer.invoke("sidecar:plan:approve", { planId, revisedPlan }),
  planReject: (planId, reason) =>
    ipcRenderer.invoke("sidecar:plan:reject", { planId, reason }),
  planList: () => ipcRenderer.invoke("sidecar:plan:list"),
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
