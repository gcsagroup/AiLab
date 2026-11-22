const { contextBridge, ipcRenderer, webUtils } = require('electron');
contextBridge.exposeInMainWorld('ailabHF', {
  filePath: file => webUtils.getPathForFile(file),
  request: (action, payload) => ipcRenderer.invoke('ailab:official-models', action, payload)
});
