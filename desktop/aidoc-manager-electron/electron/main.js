const { app, BrowserWindow, clipboard, dialog, ipcMain, shell } = require('electron')
const path = require('path')
const fs = require('fs')
const { spawn } = require('child_process')

let mainWindow = null
let backend = null
let backendBuffer = ''
let nextRequestId = 0
const pending = new Map()

const BACKEND_PATH = path.resolve(__dirname, '..', 'backend.py')

function pythonCommand() {
  if (process.env.AIDOC_PYTHON) return process.env.AIDOC_PYTHON
  return process.platform === 'win32' ? 'python' : 'python3'
}

function startBackend() {
  if (backend) return
  backend = spawn(pythonCommand(), [BACKEND_PATH], {
    cwd: path.resolve(__dirname, '..'),
    windowsHide: true,
    env: {
      ...process.env,
      PYTHONIOENCODING: 'utf-8',
    },
  })

  backend.stdout.on('data', (chunk) => {
    backendBuffer += chunk.toString('utf8')
    let newlineIndex
    while ((newlineIndex = backendBuffer.indexOf('\n')) >= 0) {
      const line = backendBuffer.slice(0, newlineIndex).trim()
      backendBuffer = backendBuffer.slice(newlineIndex + 1)
      if (!line) continue

      let message
      try {
        message = JSON.parse(line)
      } catch {
        continue
      }

      if (message.event) {
        if (mainWindow && !mainWindow.isDestroyed()) {
          mainWindow.webContents.send('backend-event', message)
        }
        continue
      }

      const waiting = pending.get(message.id)
      if (!waiting) continue
      pending.delete(message.id)
      clearTimeout(waiting.timer)
      if (message.ok) waiting.resolve(message.data)
      else waiting.reject(new Error(message.error || '后端处理失败'))
    }
  })

  backend.stderr.on('data', (chunk) => {
    console.error('[aidoc-backend]', chunk.toString('utf8'))
  })

  backend.on('exit', (code) => {
    for (const [, waiting] of pending) {
      clearTimeout(waiting.timer)
      waiting.reject(new Error('本地处理进程已退出'))
    }
    pending.clear()
    backend = null
    console.error('[aidoc-backend] exited', code)
  })
}

function callBackend(cmd, args = {}) {
  return new Promise((resolve, reject) => {
    if (!backend) return reject(new Error('本地处理进程未启动'))
    const id = ++nextRequestId
    const timeoutMs = cmd === 'scan_folder' ? 12 * 60 * 1000 : 90 * 1000
    const timer = setTimeout(() => {
      if (pending.has(id)) {
        pending.delete(id)
        reject(new Error(`请求超时（${Math.round(timeoutMs / 1000)} 秒）`))
      }
    }, timeoutMs)
    pending.set(id, { resolve, reject, timer })
    backend.stdin.write(JSON.stringify({ id, cmd, args }) + '\n')
  })
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1240,
    height: 800,
    minWidth: 980,
    minHeight: 680,
    title: '好办法 AI 档案管理',
    backgroundColor: '#f7f8f5',
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  })

  const devUrl = process.env.AIDOC_DEV_SERVER_URL
  if (devUrl) {
    mainWindow.loadURL(devUrl)
  } else {
    mainWindow.loadFile(path.resolve(__dirname, '..', 'dist', 'index.html'))
  }

  mainWindow.on('closed', () => {
    mainWindow = null
  })
}

ipcMain.handle('backend', async (_event, cmd, args) => {
  try {
    const data = await callBackend(cmd, args || {})
    return { ok: true, data }
  } catch (error) {
    return { ok: false, error: error.message || String(error) }
  }
})

ipcMain.handle('pickFolder', async (_event, options = {}) => {
  const result = await dialog.showOpenDialog({
    title: options.title || '选择文件夹',
    defaultPath: options.defaultPath || undefined,
    properties: ['openDirectory'],
  })
  return result.canceled ? '' : result.filePaths[0]
})

ipcMain.handle('openExternalPath', async (_event, target) => {
  const value = String(target || '').trim()
  if (!value || !fs.existsSync(value)) {
    return { ok: false, error: '目录或文件不存在' }
  }
  const error = await shell.openPath(value)
  return error ? { ok: false, error } : { ok: true }
})

ipcMain.handle('copy', (_event, text) => {
  clipboard.writeText(String(text || ''))
  return true
})

app.whenReady().then(() => {
  startBackend()
  createWindow()
  app.on('activate', () => {
    if (!mainWindow) createWindow()
  })
})

app.on('window-all-closed', () => {
  if (backend) {
    try {
      backend.kill()
    } catch {}
  }
  if (process.platform !== 'darwin') app.quit()
})
