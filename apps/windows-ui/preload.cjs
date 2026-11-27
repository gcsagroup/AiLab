const { contextBridge, ipcRenderer, webUtils } = require('electron');
contextBridge.exposeInMainWorld('ailabHF', {
  filePath: file => webUtils.getPathForFile(file),
  openRuntimeDownloads: () => ipcRenderer.invoke('ailab:runtime-downloads'),
  request: (action, payload) => ipcRenderer.invoke('ailab:official-models', action, payload)
});
