const { contextBridge, ipcRenderer, webUtils } = require('electron');
contextBridge.exposeInMainWorld('ailabHF', {
  filePath: file => webUtils.getPathForFile(file),
  runtime: (action, component) => ipcRenderer.invoke('ailab:runtime', action, component),
  request: (action, payload) => ipcRenderer.invoke('ailab:official-models', action, payload)
});
