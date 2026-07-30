const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("cyberguard", {
  ping: () => ipcRenderer.invoke("sidecar:ping"),
  capabilities: (tier) => ipcRenderer.invoke("sidecar:capabilities", tier),
  run: (task, tier) => ipcRenderer.invoke("sidecar:run", { task, tier }),
  abort: (runId) => ipcRenderer.invoke("sidecar:abort", runId),
  steer: (runId, message) =>
    ipcRenderer.invoke("sidecar:steer", { runId, message }),
  onEvent: (handler) => {
    const listener = (_event, payload) => handler(payload);
    ipcRenderer.on("sidecar:event", listener);
    return () => ipcRenderer.removeListener("sidecar:event", listener);
  },
});
