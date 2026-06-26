const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('aidocAPI', {
  version: '0.1.0',
  backend: (cmd, args) => ipcRenderer.invoke('backend', cmd, args || {}),
  pickFolder: (options) => ipcRenderer.invoke('pickFolder', options || {}),
  openExternalPath: (target) => ipcRenderer.invoke('openExternalPath', target),
  copy: (text) => ipcRenderer.invoke('copy', text),
  onBackendEvent: (callback) => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('backend-event', listener)
    return () => ipcRenderer.removeListener('backend-event', listener)
  },
})
