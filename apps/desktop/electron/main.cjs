/**
 * Electron main process (M1).
 * - Spawns Python sidecar (JSONL over stdio) — no listen ports
 * - contextIsolation + no nodeIntegration
 * - Tray + graceful sidecar SIGTERM (orphan layer ③)
 * - Crash recovery: restart sidecar
 */
const {
  app,
  BrowserWindow,
  ipcMain,
  dialog,
  Tray,
  Menu,
  nativeImage,
} = require("electron");
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
/** @type {BrowserWindow | null} */
let mainWindow = null;
/** @type {Tray | null} */
let tray = null;
let isQuitting = false;

// Disable crash reporter / breakpad (sensitive-data design §7)
try {
  app.commandLine.appendSwitch("disable-breakpad");
  app.commandLine.appendSwitch("disable-crash-reporter");
} catch (_) {
  /* ignore */
}

function findPython() {
  const venvPy = path.join(REPO_ROOT, ".venv", "bin", "python");
  if (fs.existsSync(venvPy)) return venvPy;
  return process.platform === "win32" ? "python" : "python3";
}

function stopSidecar(timeoutMs = 5000) {
  return new Promise((resolve) => {
    if (!sidecar) {
      resolve();
      return;
    }
    const child = sidecar;
    sidecar = null;
    let done = false;
    const finish = () => {
      if (done) return;
      done = true;
      resolve();
    };
    const timer = setTimeout(() => {
      try {
        child.kill("SIGKILL");
      } catch (_) {
        /* ignore */
      }
      finish();
    }, timeoutMs);
    child.once("exit", () => {
      clearTimeout(timer);
      finish();
    });
    try {
      child.kill("SIGTERM");
    } catch (_) {
      clearTimeout(timer);
      finish();
    }
  });
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
    if (!id || !pending.has(id)) return;
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
    for (const [id, slot] of pending) {
      slot.reject(new Error("sidecar exited"));
      pending.delete(id);
    }
    if (!isQuitting && sidecarRestarts < MAX_SIDECAR_RESTARTS) {
      sidecarRestarts += 1;
      console.error(
        `[main] restarting sidecar (${sidecarRestarts}/${MAX_SIDECAR_RESTARTS})`
      );
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

function createTray() {
  // 1x1 empty icon fallback — Electron needs a nativeImage
  const icon = nativeImage.createEmpty();
  tray = new Tray(icon);
  tray.setToolTip("CyberGuard Desktop (M1 dev)");
  const menu = Menu.buildFromTemplate([
    {
      label: "Show",
      click: () => {
        if (mainWindow) {
          mainWindow.show();
          mainWindow.focus();
        } else createWindow();
      },
    },
    {
      label: "Hide",
      click: () => mainWindow && mainWindow.hide(),
    },
    { type: "separator" },
    {
      label: "Quit",
      click: () => {
        isQuitting = true;
        app.quit();
      },
    },
  ]);
  tray.setContextMenu(menu);
  tray.on("click", () => {
    if (!mainWindow) return;
    if (mainWindow.isVisible()) mainWindow.hide();
    else {
      mainWindow.show();
      mainWindow.focus();
    }
  });
}

function createWindow() {
  mainWindow = new BrowserWindow({
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

  if (isDev) {
    mainWindow.loadURL("http://127.0.0.1:5173");
    mainWindow.webContents.openDevTools({ mode: "detach" });
  } else {
    mainWindow.loadFile(path.join(__dirname, "../dist-renderer/index.html"));
  }

  mainWindow.webContents.on("did-finish-load", () => {
    mainWindow.webContents
      .executeJavaScript(
        'console.info("%cCyberGuard Desktop M1 — mock only; no sandbox; do not use real sensitive data.", "color:#f59e0b")'
      )
      .catch(() => {});
  });

  mainWindow.on("close", (e) => {
    // On macOS, close-to-tray keeps agent available
    if (!isQuitting && process.platform === "darwin") {
      e.preventDefault();
      mainWindow.hide();
    }
  });
}

app.whenReady().then(() => {
  if (isDev) {
    dialog
      .showMessageBox({
        type: "warning",
        title: "CyberGuard Desktop — development build",
        message:
          "M3/M4 development version (not for distribution).\n\nSeatbelt + session encryption may be on; Plan Mode requires self-approval for high-risk runs.\nNot notarized. Do not process real sensitive production data without FileVault.\nData root: ~/Library/Application Support/CyberGuard",
        buttons: ["I understand"],
      })
      .catch(() => {});
  }

  startSidecar();
  createWindow();
  createTray();

  // Surface FileVault warning after sidecar is up
  setTimeout(() => {
    rpc("ping", {})
      .then((r) => {
        const w = r && r.filevault && r.filevault.warning;
        if (w && mainWindow) {
          dialog
            .showMessageBox(mainWindow, {
              type: "warning",
              title: "FileVault",
              message: w,
              buttons: ["OK"],
            })
            .catch(() => {});
        }
      })
      .catch(() => {});
  }, 1500);

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
    else if (mainWindow) mainWindow.show();
  });
});

app.on("before-quit", async (e) => {
  if (isQuitting && !sidecar) return;
  isQuitting = true;
  // Layer ③: give sidecar time to killpg / stop MCP children
  if (sidecar) {
    e.preventDefault();
    await stopSidecar(5000);
    app.exit(0);
  }
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    isQuitting = true;
    app.quit();
  }
});

// IPC bridge
ipcMain.handle("sidecar:ping", async () => rpc("ping", {}));
ipcMain.handle("sidecar:capabilities", async (_e, tier) =>
  rpc("session.capabilities", { tier })
);
ipcMain.handle("sidecar:run", async (event, { task, tier, sessionId }) => {
  const events = [];
  const result = await rpc(
    "agent.run",
    { task, tier: tier || "readonly", session_id: sessionId || undefined },
    (ev) => {
      events.push(ev);
      event.sender.send("sidecar:event", ev);
    }
  );
  return { result, events };
});
ipcMain.handle("sidecar:abort", async (_e, runId) =>
  rpc("agent.abort", { run_id: runId })
);
ipcMain.handle("sidecar:steer", async (_e, { runId, message }) =>
  rpc("agent.steer", { run_id: runId, message })
);
ipcMain.handle("sidecar:sessions:list", async () => rpc("sessions.list", {}));
ipcMain.handle("sidecar:sessions:create", async (_e, { title, tier }) =>
  rpc("sessions.create", { title, tier })
);
ipcMain.handle("sidecar:sessions:events", async (_e, sessionId) =>
  rpc("sessions.events", { session_id: sessionId })
);
ipcMain.handle("sidecar:plan:approve", async (_e, { planId, revisedPlan }) =>
  rpc("plan.approve", {
    plan_id: planId,
    revised_plan: revisedPlan || undefined,
  })
);
ipcMain.handle("sidecar:plan:reject", async (_e, { planId, reason }) =>
  rpc("plan.reject", { plan_id: planId, reason: reason || "rejected_by_user" })
);
ipcMain.handle("sidecar:plan:list", async () => rpc("plan.list", {}));
