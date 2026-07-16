const { app, BrowserWindow, Tray, Menu, Notification, ipcMain, nativeImage, shell, dialog, session } = require("electron");
const path = require("path");
const { spawn, spawnSync } = require("child_process");
const fs = require("fs");
const http = require("http");
const crypto = require("crypto");
const { autoUpdater } = require("electron-updater");

const isDev = !app.isPackaged;

const gotTheLock = app.requestSingleInstanceLock();
if (!gotTheLock) {
  app.quit();
  process.exit(0);
}

if (process.platform === "win32") {
  app.setAppUserModelId("com.kinexis.desktop");
}

let mainWindow = null;
let tray = null;
let backendProcess = null;
const BACKEND_PORT = 8000;
let isQuitting = false;
let backendRestartAttempts = 0;
const MAX_BACKEND_RESTARTS = 5;
let apiToken = null;

const ALLOWED_EXTERNAL_HOSTS = new Set([
  "accounts.google.com",
  "oauth2.googleapis.com",
  "dash.cloudflare.com",
]);

function isLoopbackHostname(hostname) {
  const host = String(hostname || "")
    .toLowerCase()
    .replace(/^\[|\]$/g, "");
  return host === "127.0.0.1" || host === "localhost" || host === "::1";
}

function isAllowedExternalUrl(url) {
  if (typeof url !== "string" || !(url.startsWith("https://") || url.startsWith("http://"))) {
    return false;
  }
  try {
    const parsed = new URL(url);
    if (isLoopbackHostname(parsed.hostname)) return true;
    return ALLOWED_EXTERNAL_HOSTS.has(parsed.hostname.toLowerCase());
  } catch {
    return false;
  }
}

function getOrCreateApiToken() {
  if (apiToken) return apiToken;

  const userDataTokenPath = path.join(app.getPath("userData"), "api_token");
  const backendTokenPath = path.join(getBackendPath(), ".kinexis_api_token");

  let token = null;
  try {
    if (fs.existsSync(userDataTokenPath)) {
      token = fs.readFileSync(userDataTokenPath, "utf8").trim();
    }
  } catch {
    // fall through
  }

  if (!token && isDev) {
    try {
      if (fs.existsSync(backendTokenPath)) {
        token = fs.readFileSync(backendTokenPath, "utf8").trim();
      }
    } catch {
      // fall through
    }
  }

  if (!token) {
    token = crypto.randomBytes(32).toString("base64url");
  }

  apiToken = token;

  try {
    fs.mkdirSync(path.dirname(userDataTokenPath), { recursive: true });
    fs.writeFileSync(userDataTokenPath, token + "\n", { encoding: "utf8", mode: 0o600 });
  } catch (err) {
    console.error("Failed to persist API token to userData:", err.message);
    if (!apiToken) {
      console.error("CRITICAL: Token persistence failed and no in-memory token exists. Auth will fail on restart.");
    }
  }

  if (isDev) {
    try {
      fs.mkdirSync(path.dirname(backendTokenPath), { recursive: true });
      fs.writeFileSync(backendTokenPath, token + "\n", { encoding: "utf8", mode: 0o600 });
    } catch (err) {
      console.error("Failed to write backend/.kinexis_api_token:", err.message);
    }
  }

  apiToken = token;
  return apiToken;
}

/** Per-install Fernet key — never reuse the builder's shared .env key. */
function getOrCreateFernetKey() {
  const userDataPath = path.join(app.getPath("userData"), "fernet_key");
  let key = null;
  try {
    if (fs.existsSync(userDataPath)) {
      key = fs.readFileSync(userDataPath, "utf8").trim();
    }
  } catch {
    // fall through
  }
  if (!key) {
    // cryptography.Fernet expects url-safe base64 of 32 random bytes, unpadded
    key = crypto.randomBytes(32).toString("base64").replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  }
  try {
    fs.mkdirSync(path.dirname(userDataPath), { recursive: true });
    fs.writeFileSync(userDataPath, key + "\n", { encoding: "utf8", mode: 0o600 });
  } catch (err) {
    console.error("Failed to persist Fernet key to userData:", err.message);
  }
  return key;
}

function backendAuthHeaders(extra) {
  const headers = { ...(extra || {}) };
  const token = getOrCreateApiToken();
  if (token) headers["X-Kinexis-Token"] = token;
  return headers;
}

function getBackendPath() {
  if (isDev) {
    return path.join(__dirname, "..", "backend");
  }
  return path.join(process.resourcesPath, "backend");
}

function resolvePythonCommand() {
  const fromEnv = process.env.KINEAXIS_PYTHON || process.env.PYTHON;
  if (fromEnv) return fromEnv;

  const candidates =
    process.platform === "win32"
      ? ["py", "python", "python3"]
      : ["python3", "python"];

  for (const cmd of candidates) {
    try {
      const result = spawnSync(cmd, ["--version"], {
        windowsHide: true,
        encoding: "utf8",
      });
      if (result.status === 0) return cmd;
    } catch {
      // try next
    }
  }
  return process.platform === "win32" ? "py" : "python3";
}

function getBackendExe() {
  if (isDev) {
    return resolvePythonCommand();
  }
  return path.join(process.resourcesPath, "backend", "kinexis-backend.exe");
}

function readPortalConfig() {
  try {
    const flagPath = path.join(app.getPath("userData"), "kinexis-portal.json");
    if (!fs.existsSync(flagPath)) return { enabled: false, public_base_url: "" };
    const raw = JSON.parse(fs.readFileSync(flagPath, "utf8"));
    return {
      enabled: !!(raw && raw.enabled),
      public_base_url: (raw && raw.public_base_url) || "",
    };
  } catch (e) {
    console.warn("Could not read portal config:", e);
    return { enabled: false, public_base_url: "" };
  }
}

function getBackendArgs() {
  const portal = readPortalConfig();
  const host = portal.enabled || process.env.KINEAXIS_PORTAL_MODE === "1" ? "0.0.0.0" : "127.0.0.1";
  if (isDev) {
    const cmd = resolvePythonCommand();
    // `py -3 -m uvicorn ...` on Windows when using the launcher
    if (process.platform === "win32" && cmd === "py") {
      return ["-3", "-m", "uvicorn", "app.main:app", "--host", host, "--port", String(BACKEND_PORT)];
    }
    return ["-m", "uvicorn", "app.main:app", "--host", host, "--port", String(BACKEND_PORT)];
  }
  return [];
}

function getDbPath() {
  return path.join(app.getPath("userData"), "kinexis.db");
}

function getDatabaseUrl() {
  return `sqlite:///${getDbPath().replace(/\\/g, "/")}`;
}

function startBackend() {
  if (isQuitting) return;

  const exe = getBackendExe();
  const args = getBackendArgs();
  const backendDir = getBackendPath();

  if (!isDev && !fs.existsSync(exe)) {
    console.error("Backend executable missing:", exe);
    return;
  }

  const token = getOrCreateApiToken();
  const fernetKey = getOrCreateFernetKey();
  const portal = readPortalConfig();
  const portalOn = portal.enabled || process.env.KINEAXIS_PORTAL_MODE === "1";
  const env = {
    ...process.env,
    DATABASE_URL: getDatabaseUrl(),
    BACKEND_PORT: String(BACKEND_PORT),
    BACKEND_HOST: portalOn ? "0.0.0.0" : "127.0.0.1",
    KINEAXIS_API_TOKEN: token,
    KINEAXIS_REQUIRE_API_TOKEN: "1",
    // Override any baked installer .env so each machine has its own crypto key.
    FERNET_KEY: fernetKey,
    FERNET_KEY_FILE: path.join(app.getPath("userData"), "fernet_key"),
  };
  if (portalOn) {
    env.KINEAXIS_ALLOW_REMOTE = "1";
    env.KINEAXIS_PORTAL_MODE = "1";
    env.KINEAXIS_DISABLE_DOCS = "1";
    if (portal.public_base_url) {
      env.PUBLIC_BASE_URL = String(portal.public_base_url).replace(/\/$/, "");
    }
    console.log("[portal] Client portal mode ON — binding 0.0.0.0, remote share links enabled");
  }

  backendProcess = spawn(exe, args, {
    cwd: backendDir,
    env,
    stdio: ["ignore", "pipe", "pipe"],
    windowsHide: true,
  });

  backendProcess.stdout.on("data", (data) => {
    const line = data.toString().trim();
    if (line.length > 500) {
      console.log(`[backend] ${line.substring(0, 500)}...`);
    } else {
      console.log(`[backend] ${line}`);
    }
    // Forward truncated output to renderer for diagnostics only
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send("backend-log", line.substring(0, 300));
    }
  });

  backendProcess.stderr.on("data", (data) => {
    const line = data.toString().trim();
    if (line.length > 500) {
      console.error(`[backend:err] ${line.substring(0, 500)}...`);
    } else {
      console.error(`[backend:err] ${line}`);
    }
  });

  backendProcess.on("error", (err) => {
    console.error("Failed to start backend:", err);
    if (!isQuitting && backendRestartAttempts < MAX_BACKEND_RESTARTS) {
      backendRestartAttempts += 1;
      console.log(
        `Restarting backend after spawn error (attempt ${backendRestartAttempts}/${MAX_BACKEND_RESTARTS})…`
      );
      setTimeout(() => { if (!isQuitting) startBackend(); }, 2000);
    } else if (!isQuitting) {
      console.error("Backend restart limit reached — giving up.");
      if (mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.webContents.send("backend-unavailable", true);
      }
    }
  });

  backendProcess.on("exit", (code) => {
    console.log(`Backend exited with code ${code}`);
    backendProcess = null;
    if (!isQuitting && backendRestartAttempts < MAX_BACKEND_RESTARTS) {
      backendRestartAttempts += 1;
      console.log(
        `Restarting backend (attempt ${backendRestartAttempts}/${MAX_BACKEND_RESTARTS})…`
      );
      setTimeout(() => { if (!isQuitting) startBackend(); }, 2000);
    } else if (!isQuitting) {
      console.error("Backend restart limit reached (5 attempts) — giving up.");
      if (mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.webContents.send("backend-unavailable", true);
      }
    }
  });
}

function waitForBackend(retries, delay) {
  if (retries === undefined) retries = 15;
  if (delay === undefined) delay = 1000;
  return new Promise((resolve, reject) => {
    function check(remaining) {
      const req = http.get(
        {
          hostname: "127.0.0.1",
          port: BACKEND_PORT,
          path: "/health",
          headers: backendAuthHeaders(),
        },
      (res) => {
        if (res.statusCode === 200) {
          backendRestartAttempts = 0;
          res.resume();
          resolve();
        } else if (remaining > 0) {
          res.resume();
            setTimeout(() => check(remaining - 1), delay);
          } else {
            reject(new Error("Backend did not become healthy"));
          }
        }
      );
      req.on("error", () => {
        if (remaining > 0) {
          setTimeout(() => check(remaining - 1), delay);
        } else {
          reject(new Error("Backend did not become healthy"));
        }
      });
      req.setTimeout(3000, () => {
        req.destroy();
        if (remaining > 0) {
          setTimeout(() => check(remaining - 1), delay);
        } else {
          reject(new Error("Backend did not become healthy"));
        }
      });
    }
    check(retries);
  });
}

function getFrontendUrl() {
  if (isDev) {
    return "http://localhost:3000";
  }
  return `http://127.0.0.1:${BACKEND_PORT}`;
}

function getAssetsDir() {
  return isDev
    ? path.join(__dirname, "assets")
    : path.join(process.resourcesPath, "assets");
}

function loadAppIcon() {
  const iconPath = path.join(getAssetsDir(), "icon.ico");
  try {
    const icon = nativeImage.createFromPath(iconPath);
    if (!icon.isEmpty()) return icon;
    console.error("App icon loaded but is empty:", iconPath);
  } catch (err) {
    console.error("Failed to load app icon from", iconPath, ":", err.message);
  }
  return null;
}

function loadTrayIcon() {
  const iconPath = path.join(getAssetsDir(), "tray-icon.png");
  try {
    const icon = nativeImage.createFromPath(iconPath);
    if (!icon.isEmpty()) {
      return icon.resize({ width: 16, height: 16 });
    }
    console.error("Tray icon loaded but is empty:", iconPath);
  } catch (err) {
    console.error("Failed to load tray icon from", iconPath, ":", err.message);
  }
  return nativeImage.createEmpty();
}

function signOutFromApp() {
  return new Promise((resolve) => {
    const req = http.request(
      {
        hostname: "127.0.0.1",
        port: BACKEND_PORT,
        path: "/auth/signout",
        method: "POST",
        headers: backendAuthHeaders({ "Content-Length": "0" }),
        timeout: 5000,
      },
      (res) => {
        res.resume();
        resolve(res.statusCode === 200);
      }
    );
    req.on("error", () => resolve(false));
    req.end();
  });
}

async function handleSignOut() {
  await signOutFromApp();
  if (mainWindow) {
    mainWindow.webContents.send("sign-out-complete");
  }
}

function focusMainWindow() {
  if (!mainWindow) return;
  if (mainWindow.isMinimized()) mainWindow.restore();
  if (!mainWindow.isVisible()) mainWindow.show();
  mainWindow.focus();
}

function createWindow() {
  const appIcon = loadAppIcon();
  // Frameless + in-app caption buttons (Cursor-style top bar). Drag via -webkit-app-region.
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 920,
    minWidth: 1100,
    minHeight: 700,
    title: "Kinexis",
    icon: appIcon || undefined,
    backgroundColor: "#f4f5f7",
    show: false,
    frame: false,
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      webviewTag: false,
    },
  });

  mainWindow.webContents.session.webRequest.onHeadersReceived((details, callback) => {
    const url = details.url || "";
    // Skip CSP injection for OAuth redirects to avoid breaking auth flows
    if (
      url.includes("/auth/google/callback") ||
      url.includes("/auth/cloudflare/callback") ||
      url.startsWith("data:")
    ) {
      callback({ responseHeaders: details.responseHeaders });
      return;
    }
    callback({
      responseHeaders: {
        ...details.responseHeaders,
        "Content-Security-Policy": [
          "default-src 'self' http://127.0.0.1:8000 http://localhost:3000; " +
          "script-src 'self' 'unsafe-eval' 'unsafe-inline' http://127.0.0.1:8000 http://localhost:3000; " +
          "style-src 'self' 'unsafe-inline' http://127.0.0.1:8000 http://localhost:3000; " +
          "img-src 'self' data: blob: https: http:; " +
          "connect-src 'self' http://127.0.0.1:8000 http://localhost:3000; " +
          "font-src 'self' data:;"
        ],
      },
    });
  });

  mainWindow.loadURL(`data:text/html,
    <html>
    <head><style>
      *{box-sizing:border-box}
      body{margin:0;background:#08090c;display:flex;align-items:center;justify-content:center;height:100vh;font-family:'Segoe UI',system-ui,sans-serif}
      .wrap{text-align:center}
      .mark{width:52px;height:52px;border-radius:12px;background:linear-gradient(145deg,#2563EB,#06B6D4);margin:0 auto 20px;display:flex;align-items:center;justify-content:center;color:#fff;font-weight:700;font-size:20px;letter-spacing:-0.04em;box-shadow:0 2px 12px rgba(6,182,212,0.3)}
      .spinner{width:28px;height:28px;border:2px solid #2a2d35;border-top-color:#06B6D4;border-radius:50%;animation:spin 0.75s linear infinite;margin:0 auto}
      @keyframes spin{to{transform:rotate(360deg)}}
      p{color:#82899a;font-size:14px;margin-top:18px;font-weight:500}
    </style></head>
    <body>
    <div class="wrap">
      <div class="mark">K</div>
      <div class="spinner"></div>
      <p>Starting Kinexis…</p>
    </div>
    </body></html>`);

  mainWindow.once("ready-to-show", () => {
    mainWindow.show();
  });

  mainWindow.on("close", (event) => {
    if (!isQuitting) {
      event.preventDefault();
      mainWindow.hide();
    }
  });

  mainWindow.on("closed", () => {
    mainWindow = null;
  });

  mainWindow.on("maximize", () => {
    if (!mainWindow || mainWindow.isDestroyed()) return;
    mainWindow.webContents.send("window-maximized", true);
  });
  mainWindow.on("unmaximize", () => {
    if (!mainWindow || mainWindow.isDestroyed()) return;
    mainWindow.webContents.send("window-maximized", false);
  });
}

function createTray() {
  const trayIcon = loadTrayIcon();

  tray = new Tray(trayIcon);
  tray.setToolTip("Kinexis Digital Dashboard");

  const contextMenu = Menu.buildFromTemplate([
    {
      label: "Open Kinexis",
      click: () => {
        focusMainWindow();
      },
    },
    { type: "separator" },
    {
      label: "Sign out",
      click: () => {
        void handleSignOut();
      },
    },
    { type: "separator" },
    {
      label: "Launch on Startup",
      type: "checkbox",
      checked: app.getLoginItemSettings().openAtLogin,
      click: (menuItem) => {
        app.setLoginItemSettings({ openAtLogin: menuItem.checked });
      },
    },
    { type: "separator" },
    {
      label: "Quit",
      click: () => {
        isQuitting = true;
        if (backendProcess) {
          try { backendProcess.kill(); } catch {}
          backendProcess = null;
        }
        app.quit();
      },
    },
  ]);

  tray.setContextMenu(contextMenu);

  tray.on("double-click", () => {
    focusMainWindow();
  });
}

function checkForHighSeverityInsights() {
  const req = http.get(
    {
      hostname: "127.0.0.1",
      port: BACKEND_PORT,
      path: "/insights/notifications/pending",
      headers: backendAuthHeaders(),
      timeout: 10000,
    },
      (res) => {
        let body = "";
        res.on("data", (chunk) => (body += chunk));
        res.on("end", () => {
          try {
            const payload = JSON.parse(body);
            const items = payload.items || [];
            if (items.length === 0 || !Notification.isSupported()) return;
            const ids = [];
            for (const item of items.slice(0, 3)) {
              ids.push(item.id);
              const n = new Notification({
                title: item.title || "Kinexis Alert",
                body: item.body,
                urgency: item.severity === "high" ? "critical" : "normal",
              });
              n.show();
              if (mainWindow && !mainWindow.isDestroyed()) {
                mainWindow.webContents.send("insight-notification", item);
              }
            }
            if (ids.length) {
              const data = JSON.stringify({ ids });
              const req = http.request(
                {
                  hostname: "127.0.0.1",
                  port: BACKEND_PORT,
                  path: "/insights/notifications/delivered",
                  method: "POST",
                  headers: backendAuthHeaders({
                    "Content-Type": "application/json",
                    "Content-Length": Buffer.byteLength(data),
                  }),
                },
                (res) => {
                  if (res.statusCode !== 200) {
                    console.warn("Failed to mark notifications delivered, status:", res.statusCode);
                  }
                }
              );
              req.on("error", (err) => {
                console.warn("Failed to mark notifications delivered:", err.message);
              });
              req.write(data);
              req.end();
            }
          } catch (e) {
            console.warn("Failed to parse notification payload:", e.message);
          }
        });
        res.on("error", (err) => {
          console.warn("Failed to read notification response:", err.message);
        });
      }
    );
  req.on("error", (err) => {
    console.warn("Failed to check for insights notifications:", err.message);
  });
}

function isAuthCallback(url) {
  return (
    typeof url === "string" &&
    url.startsWith(`http://127.0.0.1:${BACKEND_PORT}/auth/`) &&
    url.includes("/callback")
  );
}

function openAuthWindow(authUrl) {
  return new Promise((resolve, reject) => {
    let settled = false;
    const TIMEOUT_MS = 5 * 60 * 1000; // 5 minutes
    const finish = (ok) => {
      if (settled) return;
      settled = true;
      clearTimeout(authTimeout);
      resolve(ok);
    };

    const authTimeout = setTimeout(() => {
      if (!settled) {
        settled = true;
        if (!authWindow.isDestroyed()) authWindow.close();
        reject(new Error("OAuth window timed out after 5 minutes"));
      }
    }, TIMEOUT_MS);

    const authWindow = new BrowserWindow({
      width: 520,
      height: 720,
      parent: mainWindow || undefined,
      modal: !!mainWindow,
      title: "Sign in",
      backgroundColor: "#0c0d0f",
      autoHideMenuBar: true,
      webPreferences: {
        nodeIntegration: false,
        contextIsolation: true,
        webviewTag: false,
      },
    });

    let succeeded = false;
    const onCallback = (url) => {
      if (!isAuthCallback(url)) return;
      succeeded = true;
      finish(true);
      setTimeout(() => {
        if (!authWindow.isDestroyed()) authWindow.close();
      }, 1200);
    };

    authWindow.webContents.on("will-navigate", (_event, url) => onCallback(url));
    authWindow.webContents.on("will-redirect", (_event, url) => onCallback(url));
    authWindow.webContents.on("did-navigate", (_event, url) => onCallback(url));
    authWindow.webContents.on("did-navigate-in-page", (_event, url) => onCallback(url));

    authWindow.on("closed", () => {
      if (!succeeded) finish(false);
    });

    authWindow.loadURL(authUrl).catch(() => finish(false));
  });
}

function getProjectRoot() {
  if (isDev) {
    return path.join(__dirname, "..", "..");
  }
  return app.getPath("userData");
}

function writeCursorApiToken() {
  const cursorDir = path.join(getProjectRoot(), ".cursor");
  try {
    fs.mkdirSync(cursorDir, { recursive: true });
    const token = getOrCreateApiToken();
    fs.writeFileSync(path.join(cursorDir, "api_token"), token + "\n", { encoding: "utf8", mode: 0o600 });
  } catch (err) {
    console.error("Failed to write .cursor/api_token:", err.message);
  }
}

function writeCursorTaskFile(taskId, taskData) {
  if (!taskId || !/^\d+$/.test(String(taskId))) {
    console.error("Invalid taskId for Cursor task file:", taskId);
    return null;
  }
  const tasksDir = path.join(getProjectRoot(), ".cursor", "tasks");
  try {
    fs.mkdirSync(tasksDir, { recursive: true });
    const recommendedAction = taskData.recommendedAction || taskData.message || "";
    const evidence = taskData.evidence || "";
    const targetUrl = taskData.targetUrl || "";
    const targetQuery = taskData.targetQuery || "";
    const fromToCopy = taskData.fromToCopy || "";

    const sections = [
      `# Task ${taskId}: ${taskData.title || "Fix issue"}`,
      "",
      "> **@AI** — This is a Kinexis work item assigned to you. Read this file, implement the fix, then run the completion command at the bottom.",
      "",
      `**Task ID:** ${taskId}`,
      `**Client:** ${taskData.clientName || "Unknown"}`,
      `**Assigned to:** Cursor AI`,
      `**Playbook:** ${taskData.playbookPattern || "ctr_title_meta"}`,
      "",
      "---",
      "",
      "## Evidence (before state)",
      "",
    ];

    if (targetQuery) {
      sections.push(`**Query:** "${targetQuery}"`);
      sections.push("");
    }
    if (targetUrl) {
      sections.push(`**Target URL:** ${targetUrl}`);
      sections.push("");
    }
    if (evidence) {
      sections.push(evidence);
      sections.push("");
    } else if (targetQuery || targetUrl) {
      sections.push(`Fix the page ranking for this query to improve CTR/clicks.`);
      sections.push("");
    }
    sections.push("");

    sections.push("## What needs to be done");
    sections.push("");

    sections.push(recommendedAction || "Review the issue details below and implement the appropriate fix.");
    sections.push("");
    sections.push("");

    if (targetUrl) {
      sections.push(`**Target URL:** ${targetUrl}`);
      sections.push("");
    }
    if (targetQuery) {
      sections.push(`**Target Query:** "${targetQuery}"`);
      sections.push("");
    }
    if (evidence) {
      sections.push("### Evidence");
      sections.push("");
      sections.push(evidence);
      sections.push("");
    }
    if (fromToCopy) {
      sections.push("### FROM → TO Copy");
      sections.push("");
      sections.push(fromToCopy);
      sections.push("");
    }

    sections.push(taskData.message && taskData.message !== recommendedAction ? "## Full context\n\n" + taskData.message + "\n" : "");
    sections.push(taskData.notes && taskData.notes !== taskData.message ? "## Additional notes\n\n" + taskData.notes + "\n" : "");

    sections.push("---");
    sections.push("");
    sections.push("## Restrictions");
    sections.push("");
    sections.push("- Do NOT invent FAQ schema, featured-snippet, or \"audit all\" patterns");
    sections.push("- Do NOT add mobile or page-speed actions without specific PSI/CTR evidence");
    sections.push("- Do NOT suggest \"wait and recheck\" steps — Prove handles measurement");
    sections.push("- Every change must name the exact target_url and the exact string to change (FROM → TO)");
    sections.push("");
    sections.push("## Acceptance criteria");
    sections.push("");
    sections.push("- Fix is live on the target URL");
    sections.push("- Title/meta changes verified via View Source or browser DevTools");
    sections.push("- No accidental noindex or broken layout introduced");
    sections.push("- Run the completion command below after deploying");
    sections.push("");
    sections.push("## Completion");
    sections.push("");
    sections.push("When the fix is implemented and verified, mark this task as done by running:");
    sections.push("");
    sections.push("```powershell");
    sections.push(`powershell -ExecutionPolicy Bypass -File "kinexis\\scripts\\cursor-complete.ps1" -TaskId ${taskId}`);
    sections.push("```");
    sections.push("");
    sections.push("This tells Kinexis the work is complete so it can capture Prove baselines.");
    sections.push("");
    sections.push(`*Generated by Kinexis on ${new Date().toISOString()}*`);

    const content = sections.join("\n");
    const filePath = path.join(tasksDir, `task-${taskId}.md`);
    fs.writeFileSync(filePath, content, { encoding: "utf8" });
    return filePath;
  } catch (err) {
    console.error("Failed to write cursor task file:", err.message);
    return null;
  }
}

function findCursorExe() {
  const localAppData = process.env.LOCALAPPDATA || "";
  const candidates = [
    path.join(localAppData, "Programs", "Cursor", "Cursor.exe"),
    path.join(process.env.APPDATA || "", "..", "Local", "Programs", "Cursor", "Cursor.exe"),
  ];
  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) return candidate;
  }
  console.warn("Cursor executable not found in standard locations. Falling back to PATH.");
  return "Cursor.exe";
}

function openCursorForTask(taskId, taskData) {
  writeCursorApiToken();
  const taskFilePath = writeCursorTaskFile(taskId, taskData);
  const cursorExe = findCursorExe();
  const projectRoot = getProjectRoot();

  try {
    const args = taskFilePath ? [projectRoot, taskFilePath] : [projectRoot];
    spawn(cursorExe, args, {
      detached: true,
      stdio: "ignore",
      windowsHide: false,
    }).unref();
    return { ok: true, taskFile: taskFilePath, projectRoot };
  } catch (err) {
    console.error("Failed to open Cursor:", err.message);
    return { ok: false, error: err.message };
  }
}

function setupIpcHandlers() {
  ipcMain.handle("get-backend-port", () => BACKEND_PORT);
  ipcMain.handle("get-api-token", () => getOrCreateApiToken());
  ipcMain.handle("get-startup-setting", () => app.getLoginItemSettings().openAtLogin);
  ipcMain.handle("set-startup-setting", (_event, enabled) => {
    app.setLoginItemSettings({ openAtLogin: Boolean(enabled) });
    return app.getLoginItemSettings().openAtLogin;
  });
  ipcMain.handle("get-version", () => app.getVersion());
  ipcMain.handle("open-external-url", (_event, url) => {
    if (isAllowedExternalUrl(url)) {
      return shell.openExternal(url);
    }
    return false;
  });
  ipcMain.handle("open-auth-window", (_event, url) => {
    if (isAllowedExternalUrl(url)) {
      return openAuthWindow(url);
    }
    return false;
  });
  ipcMain.handle("window-minimize", (event) => {
    const win = BrowserWindow.fromWebContents(event.sender);
    if (win) win.minimize();
  });
  ipcMain.handle("window-maximize", (event) => {
    const win = BrowserWindow.fromWebContents(event.sender);
    if (!win) return false;
    if (win.isMaximized()) {
      win.unmaximize();
      return false;
    }
    win.maximize();
    return true;
  });
  ipcMain.handle("window-close", (event) => {
    const win = BrowserWindow.fromWebContents(event.sender);
    if (win) win.close();
  });
  ipcMain.handle("window-is-maximized", (event) => {
    const win = BrowserWindow.fromWebContents(event.sender);
    return win ? win.isMaximized() : false;
  });
  ipcMain.handle("open-cursor-for-task", (_event, taskId, taskData) => {
    return openCursorForTask(taskId, taskData);
  });
  ipcMain.handle("get-project-root", () => getProjectRoot());
}

function setupUpdateIpcHandlers() {
  let updateDownloaded = false;

  autoUpdater.autoDownload = false;

  autoUpdater.on("update-available", (info) => {
    console.log("Update available:", info.version);
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send("update-status", {
        status: "available",
        version: info.version,
      });
    }
    autoUpdater.downloadUpdate();
  });

  autoUpdater.on("update-not-available", () => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send("update-status", { status: "up-to-date" });
    }
  });

  autoUpdater.on("download-progress", (progress) => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send("update-status", {
        status: "downloading",
        percent: Math.round(progress.percent),
      });
    }
  });

  autoUpdater.on("update-downloaded", () => {
    updateDownloaded = true;
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send("update-status", { status: "downloaded" });
    }
    dialog
      .showMessageBox(mainWindow, {
        type: "info",
        title: "Update Ready",
        message: "A new version has been downloaded. Restart now to install?",
        buttons: ["Restart now", "Later"],
        defaultId: 0,
      })
      .then(({ response }) => {
        if (response === 0) {
          setImmediate(() => autoUpdater.quitAndInstall());
        }
      });
  });

  autoUpdater.on("error", (err) => {
    console.warn("Auto-updater error:", err.message);
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send("update-status", {
        status: "error",
        message: err.message,
      });
    }
  });

  ipcMain.handle("check-for-updates", async () => {
    try {
      await autoUpdater.checkForUpdates();
      return { ok: true };
    } catch (e) {
      return { ok: false, error: e.message };
    }
  });

  ipcMain.handle("install-update", () => {
    if (updateDownloaded) {
      setImmediate(() => autoUpdater.quitAndInstall());
      return true;
    }
    return false;
  });

  ipcMain.handle("get-update-status", () => {
    if (updateDownloaded) return { status: "downloaded" };
    return { status: "pending" };
  });
}

app.on("second-instance", () => {
  focusMainWindow();
});

app.on("activate", () => {
  focusMainWindow();
});

app.whenReady().then(async () => {
  const appIcon = loadAppIcon();
  if (appIcon) {
    app.dock?.setIcon?.(appIcon);
  }

  setupIpcHandlers();
  setupUpdateIpcHandlers();

  startBackend();
  createWindow();

  try {
    await waitForBackend(30, 1000);
    console.log("Backend is ready");
    writeCursorApiToken();
    if (mainWindow) {
      await session.defaultSession.clearCache();
      await session.defaultSession.clearStorageData();
      mainWindow.loadURL(getFrontendUrl());
    }
  } catch (err) {
    console.error("Backend failed to start:", err.message);
    if (mainWindow) {
      mainWindow.loadURL(`data:text/html,<html><head><style>body{font-family:system-ui,sans-serif;background:%2308090c;color:%23edeef2;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;text-align:center;padding:2rem}h2{letter-spacing:-0.02em;font-size:1.25rem}p{color:%236b7080;font-size:0.875rem}</style></head><body><div><h2>Backend failed to start</h2><p>Check that Kinexis was installed correctly and no antivirus is blocking it.</p><p style="color:%234a4e5a">${err.message}</p></div></body></html>`);
    }
  }

  createTray();

  // Check for updates on startup, then every 6 hours
  autoUpdater.checkForUpdates();
  setInterval(() => autoUpdater.checkForUpdates(), 6 * 60 * 60 * 1000);

  // Initial check, then every 5 minutes
  checkForHighSeverityInsights();
  setInterval(checkForHighSeverityInsights, 5 * 60 * 1000);
});

app.on("window-all-closed", (event) => {
  if (process.platform !== "darwin") {
    event.preventDefault();
  }
});

app.on("before-quit", (event) => {
  if (!isQuitting) {
    event.preventDefault();
    isQuitting = true;
  }
  if (backendProcess) {
    try {
      const shutdownReq = http.request(
        {
          hostname: "127.0.0.1",
          port: BACKEND_PORT,
          path: "/shutdown",
          method: "POST",
          headers: backendAuthHeaders({ "Content-Length": "0" }),
          timeout: 3000,
        },
        (res) => { res.resume(); }
      );
      shutdownReq.on("error", () => {});
      shutdownReq.end();
    } catch {
      // ignore
    }
    const killTimer = setTimeout(() => {
      if (backendProcess) {
        backendProcess.kill();
        backendProcess = null;
      }
      app.quit();
    }, 1500);
    killTimer.unref();
  } else {
    app.quit();
  }
});
