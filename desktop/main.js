const { app, BrowserWindow, ipcMain, shell } = require("electron");
const path = require("path");
const { spawn } = require("child_process");

let mainWindow = null;
let apiProcess = null;

const PY_DIST_FOLDER = "extra";
const PY_EXE = "oracle-engine.exe";
const DEV_SERVER_URL = process.env.LYRA_RENDERER_URL;

const getApiPath = () =>
  app.isPackaged
    ? path.join(process.resourcesPath, PY_DIST_FOLDER, PY_EXE)
    : path.join(__dirname, "oracle-engine.exe");

function createPyProc() {
  const script = getApiPath();
  console.log("[lyra] backend executable:", script);

  if (!app.isPackaged) {
    console.log("[lyra] dev mode active, expecting backend to run separately");
    return;
  }

  try {
    apiProcess = spawn(script);
    if (apiProcess) {
      apiProcess.stdout.on("data", (data) => console.log("[lyra-api]", String(data).trim()));
      apiProcess.stderr.on("data", (data) => console.log("[lyra-api:error]", String(data).trim()));
    }
  } catch (error) {
    console.log("[lyra] failed to start python backend:", error);
  }
}

function exitPyProc() {
  if (apiProcess) {
    apiProcess.kill();
  }
}

async function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1680,
    height: 1040,
    minWidth: 1280,
    minHeight: 860,
    frame: false,
    titleBarStyle: "hidden",
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

app.whenReady().then(async () => {
  createPyProc();
  await createWindow();

  ipcMain.on("window-minimize", () => mainWindow?.minimize());
  ipcMain.on("window-maximize", () => {
    if (!mainWindow) {
      return;
    }
    if (mainWindow.isMaximized()) {
      mainWindow.unmaximize();
    } else {
      mainWindow.maximize();
    }
  });
  ipcMain.on("window-close", () => app.quit());
});

app.on("will-quit", exitPyProc);
