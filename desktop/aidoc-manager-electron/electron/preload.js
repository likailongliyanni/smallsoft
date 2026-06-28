const { contextBridge, ipcRenderer, webUtils } = require('electron')

contextBridge.exposeInMainWorld('aidocAPI', {
  version: '0.1.0',
  backend: (cmd, args) => ipcRenderer.invoke('backend', cmd, args || {}),
  pickFolder: (options) => ipcRenderer.invoke('pickFolder', options || {}),
  pickFiles: (options) => ipcRenderer.invoke('pickFiles', options || {}),
  // 取拖入文件的本地绝对路径（Electron 32+ 不再有 File.path，必须走 webUtils）。
  getPathForFile: (file) => webUtils.getPathForFile(file),
  openExternalPath: (target) => ipcRenderer.invoke('openExternalPath', target),
  copy: (text) => ipcRenderer.invoke('copy', text),
  onBackendEvent: (callback) => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('backend-event', listener)
    return () => ipcRenderer.removeListener('backend-event', listener)
  },
})
