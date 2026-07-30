/**
 * Electron main process (M1).
 * - Spawns Python sidecar (JSONL over stdio) — no listen ports
 * - contextIsolation + no nodeIntegration
 * - Dev: load Vite; Prod: load built renderer
 * - Crash recovery: restart sidecar once
 */
const { app, BrowserWindow, ipcMain, dialog } = require("electron");
const path = require("node:path");
const { spawn } = require("node:child_process");
const readline = require("node:readline");
const fs = require("node:fs");

const isDev = !app.isPackaged;
const REPO_ROOT = path.resolve(__dirname, "../../..");

/** @type {import('child_process').ChildProcess | null} */
let sidecar = null;
/** @type {Map<string, {resolve: Function, reject: Function, onEvent?: Function}>} */
const pending = new Map();
let reqSeq = 0;
let sidecarRestarts = 0;
const MAX_SIDECAR_RESTARTS = 3;

function findPython() {
  const venvPy = path.join(REPO_ROOT, ".venv", "bin", "python");
  if (fs.existsSync(venvPy)) return venvPy;
  return process.platform === "win32" ? "python" : "python3";
}

function startSidecar() {
  if (sidecar) {
    try {
      sidecar.kill("SIGTERM");
    } catch (_) {
      /* ignore */
    }
    sidecar = null;
  }

  const py = findPython();
  const env = {
    ...process.env,
    PYTHONPATH: [path.join(REPO_ROOT, "packages"), REPO_ROOT, process.env.PYTHONPATH || ""]
      .filter(Boolean)
      .join(path.delimiter),
    PYTHONUNBUFFERED: "1",
  };

  sidecar = spawn(py, ["-m", "apps.desktop.sidecar"], {
    cwd: REPO_ROOT,
    env,
    stdio: ["pipe", "pipe", "pipe"],
  });

  // Process group: future MCP children should share this for orphan cleanup (M1 stub)
  sidecar.on("error", (err) => {
    console.error("[main] sidecar spawn error", err);
  });

  const rl = readline.createInterface({ input: sidecar.stdout });
  rl.on("line", (line) => {
    let msg;
    try {
      msg = JSON.parse(line);
    } catch {
      console.error("[main] bad jsonl from sidecar", line.slice(0, 200));
      return;
    }
    const id = msg.id != null ? String(msg.id) : null;
    if (!id || !pending.has(id)) {
      // unsolicited — ignore
      return;
    }
    const slot = pending.get(id);
    if (msg.event && slot.onEvent) {
      slot.onEvent(msg.event);
      return;
    }
    if (msg.error) {
      pending.delete(id);
      slot.reject(new Error(msg.error.message || JSON.stringify(msg.error)));
      return;
    }
    if ("result" in msg) {
      pending.delete(id);
      slot.resolve(msg.result);
    }
  });

  sidecar.stderr.on("data", (buf) => {
    process.stderr.write(`[sidecar] ${buf}`);
  });

  sidecar.on("exit", (code, signal) => {
    console.error(`[main] sidecar exited code=${code} signal=${signal}`);
    sidecar = null;
    // Fail pending
    for (const [id, slot] of pending) {
      slot.reject(new Error("sidecar exited"));
      pending.delete(id);
    }
    if (!app.isQuitting && sidecarRestarts < MAX_SIDECAR_RESTARTS) {
      sidecarRestarts += 1;
      console.error(`[main] restarting sidecar (${sidecarRestarts}/${MAX_SIDECAR_RESTARTS})`);
      startSidecar();
    }
  });
}

/**
 * @param {string} method
 * @param {object} params
 * @param {(ev: object) => void} [onEvent]
 */
function rpc(method, params = {}, onEvent) {
  return new Promise((resolve, reject) => {
    if (!sidecar || !sidecar.stdin.writable) {
      reject(new Error("sidecar not running"));
      return;
    }
    const id = `r${++reqSeq}`;
    pending.set(id, { resolve, reject, onEvent });
    sidecar.stdin.write(JSON.stringify({ id, method, params }) + "\n");
  });
}

function createWindow() {
  const win = new BrowserWindow({
    width: 1200,
    height: 800,
    title: "CyberGuard Desktop (M1 dev)",
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  // Disable Chromium crash upload / telemetry-ish defaults where possible
  app.commandLine.appendSwitch("disable-breakpad");

  if (isDev) {
    win.loadURL("http://127.0.0.1:5173");
    win.webContents.openDevTools({ mode: "detach" });
  } else {
    win.loadFile(path.join(__dirname, "../dist-renderer/index.html"));
  }

  // Dev banner
  win.webContents.on("did-finish-load", () => {
    win.webContents
      .executeJavaScript(
        'console.info("%cCyberGuard Desktop M1 — mock only; no sandbox; do not use real sensitive data.", "color:#f59e0b")'
      )
      .catch(() => {});
  });
}

app.whenReady().then(() => {
  // Dev-only warning once
  if (isDev) {
    dialog
      .showMessageBox({
        type: "warning",
        title: "CyberGuard Desktop — development build",
        message:
          "M1 development version.\n\nSandbox and at-rest encryption are NOT enabled.\nDo not process real sensitive production data.\nMock LLM/tools only.",
        buttons: ["I understand"],
      })
      .catch(() => {});
  }

  startSidecar();
  createWindow();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("before-quit", () => {
  app.isQuitting = true;
  if (sidecar) {
    try {
      sidecar.kill("SIGTERM");
    } catch (_) {
      /* ignore */
    }
  }
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

// IPC bridge (preload whitelist)
ipcMain.handle("sidecar:ping", async () => rpc("ping", {}));
ipcMain.handle("sidecar:capabilities", async (_e, tier) =>
  rpc("session.capabilities", { tier })
);
ipcMain.handle("sidecar:run", async (event, { task, tier }) => {
  const events = [];
  const result = await rpc("agent.run", { task, tier: tier || "readonly" }, (ev) => {
    events.push(ev);
    event.sender.send("sidecar:event", ev);
  });
  return { result, events };
});
ipcMain.handle("sidecar:abort", async (_e, runId) =>
  rpc("agent.abort", { run_id: runId })
);
ipcMain.handle("sidecar:steer", async (_e, { runId, message }) =>
  rpc("agent.steer", { run_id: runId, message })
);
