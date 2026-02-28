const { app, BrowserWindow, ipcMain, shell } = require("electron");
const path = require("path");
const { spawn, execFile } = require("child_process");
const http = require("http");
const fs = require("fs");
const os = require("os");

let mainWindow = null;
let apiProcess = null;

const PY_DIST_FOLDER = "extra";
const PY_EXE = "oracle-engine.exe";
const DEV_SERVER_URL = process.env.LYRA_RENDERER_URL;
const PROJECT_ROOT = path.resolve(__dirname, "..");
const API_PORT = 5000;
const API_HEALTH_URL = `http://127.0.0.1:${API_PORT}/api/health`;

function loadProjectEnv() {
  const envPath = path.join(PROJECT_ROOT, ".env");
  try {
    if (!fs.existsSync(envPath)) {
      return;
    }
    const raw = fs.readFileSync(envPath, "utf8");
    for (const line of raw.split(/\r?\n/)) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith("#")) {
        continue;
      }
      const separator = trimmed.indexOf("=");
      if (separator === -1) {
        continue;
      }
      const key = trimmed.slice(0, separator).trim();
      if (!key || Object.prototype.hasOwnProperty.call(process.env, key)) {
        continue;
      }
      let value = trimmed.slice(separator + 1).trim();
      if (
        (value.startsWith("\"") && value.endsWith("\"")) ||
        (value.startsWith("'") && value.endsWith("'"))
      ) {
        value = value.slice(1, -1);
      }
      process.env[key] = value;
    }
  } catch (error) {
    console.log("[lyra] failed to load .env:", error.message);
  }
}

loadProjectEnv();

// ---------------------------------------------------------------------------
// Utility: HTTP probe (no dependencies)
// ---------------------------------------------------------------------------

function httpReady(url, timeoutMs = 3000) {
  return new Promise((resolve) => {
    const req = http.get(url, { timeout: timeoutMs }, (res) => {
      res.resume();
      resolve(res.statusCode >= 200 && res.statusCode < 500);
    });
    req.on("error", () => resolve(false));
    req.on("timeout", () => {
      req.destroy();
      resolve(false);
    });
  });
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function isLocalLlmBaseUrl(value) {
  try {
    const parsed = new URL(value);
    return ["127.0.0.1", "localhost"].includes(parsed.hostname);
  } catch {
    return false;
  }
}

function sendBootStatus(phase, message, ready = false) {
  console.log(`[lyra-boot] ${phase}: ${message}`);
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send("boot-status", { phase, message, ready });
  }
}

// ---------------------------------------------------------------------------
// Phase 1: Docker daemon
// ---------------------------------------------------------------------------

function runCommand(cmd, args, timeoutMs = 10000) {
  return new Promise((resolve) => {
    try {
      const proc = execFile(cmd, args, { timeout: timeoutMs, windowsHide: true }, (err, stdout, stderr) => {
        resolve({ ok: !err, stdout: stdout || "", stderr: stderr || "" });
      });
    } catch {
      resolve({ ok: false, stdout: "", stderr: "spawn failed" });
    }
  });
}

async function dockerDaemonReady() {
  const result = await runCommand("docker", ["info"], 8000);
  return result.ok;
}

function findDockerDesktop() {
  const candidates = [
    path.join(process.env.ProgramFiles || "C:\\Program Files", "Docker", "Docker", "Docker Desktop.exe"),
    path.join(process.env.LOCALAPPDATA || "", "Docker Desktop", "Docker Desktop.exe"),
    path.join(process.env.ProgramW6432 || "C:\\Program Files", "Docker", "Docker", "Docker Desktop.exe"),
  ];
  return candidates.find((p) => {
    try { return fs.existsSync(p); } catch { return false; }
  }) || null;
}

async function ensureDocker() {
  if (await dockerDaemonReady()) {
    sendBootStatus("docker", "Docker running");
    return true;
  }

  const exe = findDockerDesktop();
  if (!exe) {
    sendBootStatus("docker", "Docker Desktop not found — skipping");
    return false;
  }

  sendBootStatus("docker", "Starting Docker Desktop...");
  try {
    spawn(exe, [], { detached: true, stdio: "ignore", cwd: path.dirname(exe) }).unref();
  } catch (err) {
    sendBootStatus("docker", `Failed to launch Docker: ${err.message}`);
    return false;
  }

  for (let i = 0; i < 90; i++) {
    await sleep(1000);
    if (await dockerDaemonReady()) {
      sendBootStatus("docker", "Docker ready");
      return true;
    }
  }

  sendBootStatus("docker", "Docker did not start in time");
  return false;
}

// ---------------------------------------------------------------------------
// Phase 2: Docker Compose services
// ---------------------------------------------------------------------------

async function ensureDockerServices() {
  const services = ["prowlarr", "rdtclient", "slskd", "qobuz"];
  const healthUrls = {
    prowlarr: "http://localhost:9696/health",
    rdtclient: "http://localhost:6500",
    slskd: "http://localhost:5030/api/v0/application",
    qobuz: "http://localhost:7700/health",
  };

  // Check if all already running
  const checks = await Promise.all(services.map((s) => httpReady(healthUrls[s])));
  if (checks.every(Boolean)) {
    sendBootStatus("services", "All services running");
    return true;
  }

  sendBootStatus("services", "Starting Docker services...");

  // Find docker-compose.yml
  const composeFile = app.isPackaged
    ? path.join(PROJECT_ROOT, "docker-compose.yml")
    : path.join(__dirname, "..", "docker-compose.yml");

  if (!fs.existsSync(composeFile)) {
    sendBootStatus("services", "docker-compose.yml not found — skipping");
    return false;
  }

  const result = await runCommand(
    "docker",
    ["compose", "-f", composeFile, "up", "-d", ...services],
    60000
  );

  if (result.ok) {
    sendBootStatus("services", "Services started");
    return true;
  }

  // Maybe they're already running under a different compose project
  const recheck = await Promise.all(services.map((s) => httpReady(healthUrls[s])));
  if (recheck.every(Boolean)) {
    sendBootStatus("services", "Services already running");
    return true;
  }

  sendBootStatus("services", "Some services failed to start");
  return false;
}

// ---------------------------------------------------------------------------
// Phase 3: LLM provider probe
// ---------------------------------------------------------------------------

const LLM_PROVIDER = (process.env.LYRA_LLM_PROVIDER || "local").trim().toLowerCase();
const LLM_BASE_URL = (process.env.LYRA_LLM_BASE_URL || "http://localhost:1234/v1").replace(/\/+$/, "");
const LLM_MODELS_PROBE = `${LLM_BASE_URL}/models`;
const LM_STUDIO_PROBE = LLM_MODELS_PROBE;

function llmHostPort(baseUrl) {
  try {
    const parsed = new URL(baseUrl);
    const host = parsed.hostname === "localhost" ? "127.0.0.1" : parsed.hostname;
    return { host, port: String(parsed.port || "1234") };
  } catch {
    return { host: "127.0.0.1", port: "1234" };
  }
}

function findLMStudio() {
  const localAppData = process.env.LOCALAPPDATA || "";
  const programFiles = process.env.ProgramFiles || "C:\\Program Files";
  const candidates = [
    path.join(localAppData, "Programs", "LM Studio", "LM Studio.exe"),
    path.join(localAppData, "LM-Studio", "LM Studio.exe"),
    path.join(programFiles, "LM Studio", "LM Studio.exe"),
    path.join(programFiles, "AMD", "AI_Bundle", "LMStudio", "LM Studio", "LM Studio.exe"),
  ];
  return candidates.find((p) => {
    try { return fs.existsSync(p); } catch { return false; }
  }) || null;
}

function findLmsCli(lmStudioExe) {
  const userProfile = process.env.USERPROFILE || "";
  const localAppData = process.env.LOCALAPPDATA || "";
  const programFiles = process.env.ProgramFiles || "C:\\Program Files";
  const pathCandidates = [];
  if (process.env.LYRA_LMS_CLI_EXE) pathCandidates.push(process.env.LYRA_LMS_CLI_EXE);
  if (process.env.LMS_CLI_EXE) pathCandidates.push(process.env.LMS_CLI_EXE);
  if (lmStudioExe) {
    pathCandidates.push(path.join(path.dirname(lmStudioExe), "resources", "app", ".webpack", "lms.exe"));
  }
  pathCandidates.push(
    path.join(userProfile, ".lmstudio", "bin", "lms.exe"),
    path.join(localAppData, "Programs", "LM Studio", "resources", "app", ".webpack", "lms.exe"),
    path.join(localAppData, "LM-Studio", "resources", "app", ".webpack", "lms.exe"),
    path.join(programFiles, "LM Studio", "resources", "app", ".webpack", "lms.exe")
  );
  return pathCandidates.find((candidate) => {
    try { return candidate && fs.existsSync(candidate); } catch { return false; }
  }) || null;
}

function spawnDetached(cmd, args, cwd) {
  try {
    const child = spawn(cmd, args, {
      cwd,
      detached: true,
      stdio: "ignore",
      windowsHide: true,
    });
    child.unref();
    return true;
  } catch {
    return false;
  }
}

async function ensureLMStudio() {
  if (await httpReady(LM_STUDIO_PROBE)) {
    sendBootStatus("llm", "LM Studio running");
    return true;
  }

  const exe = findLMStudio();
  const cli = findLmsCli(exe);
  const { host, port } = llmHostPort(LLM_BASE_URL);

  if (cli) {
    sendBootStatus("llm", "Starting LM Studio server...");
    if (spawnDetached(cli, ["server", "start", "--port", port, "--bind", host], path.dirname(cli))) {
      for (let i = 0; i < 40; i++) {
        await sleep(1500);
        if (await httpReady(LM_STUDIO_PROBE)) {
          sendBootStatus("llm", "LM Studio server ready");
          return true;
        }
      }
    }
  }

  if (!exe) {
    sendBootStatus("llm", "LM Studio not found — skipping");
    return false;
  }

  sendBootStatus("llm", "Starting LM Studio...");
  try {
    spawn(exe, [], { detached: true, stdio: "ignore", cwd: path.dirname(exe) }).unref();
  } catch (err) {
    sendBootStatus("llm", `Failed to launch LM Studio: ${err.message}`);
    return false;
  }

  for (let i = 0; i < 40; i++) {
    await sleep(1500);
    if (await httpReady(LM_STUDIO_PROBE)) {
      sendBootStatus("llm", "LM Studio ready");
      return true;
    }
  }

  sendBootStatus("llm", "LM Studio did not respond — continuing without it");
  return false;
}

async function ensureLLMProvider() {
  if (LLM_PROVIDER === "disabled" || LLM_PROVIDER === "none") {
    sendBootStatus("llm", "LLM disabled by configuration");
    return false;
  }

  if (LLM_PROVIDER !== "local" && LLM_PROVIDER !== "openai_compatible" && LLM_PROVIDER !== "openai") {
    sendBootStatus("llm", `Provider ${LLM_PROVIDER} configured; skipping local bootstrap`);
    return false;
  }

  if (!isLocalLlmBaseUrl(LLM_BASE_URL)) {
    sendBootStatus("llm", `Remote LLM endpoint configured (${LLM_BASE_URL})`);
    return httpReady(LLM_MODELS_PROBE);
  }

  if (await httpReady(LLM_MODELS_PROBE)) {
    sendBootStatus("llm", `LLM endpoint ready (${LLM_PROVIDER})`);
    return true;
  }

  return ensureLMStudio();
}

// ---------------------------------------------------------------------------
// Phase 4: Flask API (oracle-engine.exe)
// ---------------------------------------------------------------------------

const getApiPath = () =>
  app.isPackaged
    ? path.join(process.resourcesPath, PY_DIST_FOLDER, PY_EXE)
    : path.join(__dirname, "oracle-engine.exe");

function createPyProc() {
  const script = getApiPath();
  console.log("[lyra] backend executable:", script);

  if (!app.isPackaged) {
    console.log("[lyra] dev mode — expecting backend to run separately (oracle serve)");
    sendBootStatus("api", "Dev mode — run oracle serve separately");
    return;
  }

  if (!fs.existsSync(script)) {
    sendBootStatus("api", "oracle-engine.exe not found — run oracle serve manually");
    return;
  }

  sendBootStatus("api", "Starting API server...");
  try {
    apiProcess = spawn(script, [], { windowsHide: true });
    if (apiProcess) {
      apiProcess.stdout.on("data", (data) => console.log("[lyra-api]", String(data).trim()));
      apiProcess.stderr.on("data", (data) => console.log("[lyra-api:error]", String(data).trim()));
      apiProcess.on("exit", (code) => {
        console.log(`[lyra-api] exited with code ${code}`);
        apiProcess = null;
      });
    }
  } catch (error) {
    console.log("[lyra] failed to start python backend:", error);
    sendBootStatus("api", `Backend failed: ${error.message}`);
  }
}

async function waitForApi(timeoutSec = 30) {
  for (let i = 0; i < timeoutSec * 2; i++) {
    if (await httpReady(API_HEALTH_URL)) {
      sendBootStatus("api", "API ready");
      return true;
    }
    await sleep(500);
  }
  sendBootStatus("api", "API did not respond — some features may be unavailable");
  return false;
}

function exitPyProc() {
  if (apiProcess) {
    apiProcess.kill();
    apiProcess = null;
  }
}

// ---------------------------------------------------------------------------
// Full bootstrap sequence
// ---------------------------------------------------------------------------

async function bootstrapBackend() {
  sendBootStatus("boot", "Initializing...");

  // Phase 1-2: Docker (only in packaged mode — dev users manage their own)
  if (app.isPackaged) {
    const dockerOk = await ensureDocker();
    if (dockerOk) {
      await ensureDockerServices();
    }
  }

  // Phase 3: LM Studio (both dev and packaged — it's a separate app)
  await ensureLLMProvider();

  // Phase 4-5: Flask API
  createPyProc();
  if (app.isPackaged) {
    await waitForApi(30);
  }

  sendBootStatus("ready", "Connected", true);
}

// ---------------------------------------------------------------------------
// Window
// ---------------------------------------------------------------------------

async function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1680,
    height: 1040,
    minWidth: 1280,
    minHeight: 860,
    frame: false,
    titleBarStyle: "hidden",
    title: "Lyra",
    backgroundColor: "#080808",
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, "preload.js"),
    },
  });

  if (DEV_SERVER_URL) {
    console.log("[lyra] loading renderer dev server:", DEV_SERVER_URL);
    await mainWindow.loadURL(DEV_SERVER_URL);
  } else {
    const rendererPath = path.join(__dirname, "renderer-app", "dist", "index.html");
    console.log("[lyra] loading packaged renderer:", rendererPath);
    await mainWindow.loadFile(rendererPath);
  }

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: "deny" };
  });
}

// ---------------------------------------------------------------------------
// App lifecycle
// ---------------------------------------------------------------------------

app.whenReady().then(async () => {
  await createWindow();

  ipcMain.on("window-minimize", () => mainWindow?.minimize());
  ipcMain.on("window-maximize", () => {
    if (!mainWindow) return;
    mainWindow.isMaximized() ? mainWindow.unmaximize() : mainWindow.maximize();
  });
  ipcMain.on("window-close", () => app.quit());

  // Run bootstrap after window is visible so user sees progress
  bootstrapBackend();
});

app.on("will-quit", exitPyProc);
