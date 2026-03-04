const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("lyraWindow", {
  minimize: () => ipcRenderer.send("window-minimize"),
  maximize: () => ipcRenderer.send("window-maximize"),
  close: () => ipcRenderer.send("window-close"),
  platform: process.platform,
  appVersion: process.versions.electron,

  // Boot status: main process sends phase updates during startup
  onBootStatus: (callback) => {
    const handler = (_event, status) => callback(status);
    ipcRenderer.on("boot-status", handler);
    return () => ipcRenderer.removeListener("boot-status", handler);
  },
});
