const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("kinexis", {
  backendPort: 8000,
  getBackendPort: () => ipcRenderer.invoke("get-backend-port"),
  getApiToken: () => ipcRenderer.invoke("get-api-token"),
  onInsightNotification: (callback) => {
    const handler = (_event, data) => callback(data);
    ipcRenderer.on("insight-notification", handler);
    return () => ipcRenderer.removeListener("insight-notification", handler);
  },
  getStartupSetting: () => ipcRenderer.invoke("get-startup-setting"),
  setStartupSetting: (enabled) => ipcRenderer.invoke("set-startup-setting", enabled),
  getVersion: () => ipcRenderer.invoke("get-version"),
  openExternalUrl: (url) => ipcRenderer.invoke("open-external-url", url),
  openAuthWindow: (url) => ipcRenderer.invoke("open-auth-window", url),
  windowMinimize: () => ipcRenderer.invoke("window-minimize"),
  windowMaximize: () => ipcRenderer.invoke("window-maximize"),
  windowClose: () => ipcRenderer.invoke("window-close"),
  windowIsMaximized: () => ipcRenderer.invoke("window-is-maximized"),
  onWindowMaximized: (callback) => {
    const handler = (_event, maximized) => callback(Boolean(maximized));
    ipcRenderer.on("window-maximized", handler);
    return () => ipcRenderer.removeListener("window-maximized", handler);
  },
  openCursorForTask: (taskId, taskData) => ipcRenderer.invoke("open-cursor-for-task", taskId, taskData),
  getProjectRoot: () => ipcRenderer.invoke("get-project-root"),
  onSignOutComplete: (callback) => {
    const handler = () => callback();
    ipcRenderer.on("sign-out-complete", handler);
    return () => ipcRenderer.removeListener("sign-out-complete", handler);
  },
  onBackendUnavailable: (callback) => {
    const handler = (_event, unavailable) => callback(Boolean(unavailable));
    ipcRenderer.on("backend-unavailable", handler);
    return () => ipcRenderer.removeListener("backend-unavailable", handler);
  },
  checkForUpdates: () => ipcRenderer.invoke("check-for-updates"),
  installUpdate: () => ipcRenderer.invoke("install-update"),
  getUpdateStatus: () => ipcRenderer.invoke("get-update-status"),
  onUpdateStatus: (callback) => {
    const handler = (_event, data) => callback(data);
    ipcRenderer.on("update-status", handler);
    return () => ipcRenderer.removeListener("update-status", handler);
  },
});
