const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("lyraWindow", {
  minimize: () => ipcRenderer.send("window-minimize"),
  maximize: () => ipcRenderer.send("window-maximize"),
  close: () => ipcRenderer.send("window-close"),
  platform: process.platform,
  appVersion: process.versions.electron,
});
