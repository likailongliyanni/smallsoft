import { spawn } from 'node:child_process'
import { createServer } from 'node:net'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const root = path.resolve(__dirname, '..')
const port = 5176

function command(name) {
  return process.platform === 'win32' ? `${name}.cmd` : name
}

function waitForPort(portNumber, host = '127.0.0.1', timeoutMs = 30000) {
  const started = Date.now()
  return new Promise((resolve, reject) => {
    const probe = () => {
      const socket = createServer()
      socket.once('error', () => resolve())
      socket.once('listening', () => {
        socket.close()
        if (Date.now() - started > timeoutMs) {
          reject(new Error(`Vite did not start on ${host}:${portNumber}`))
        } else {
          setTimeout(probe, 250)
        }
      })
      socket.listen(portNumber, host)
    }
    probe()
  })
}

const vite = spawn(command('npx'), ['vite', '--host', '127.0.0.1', '--port', String(port), '--strictPort'], {
  cwd: root,
  stdio: 'inherit',
  // Windows + 新版 Node 不允许 shell:false 直接 spawn .cmd（EINVAL），故用 shell:true
  shell: true,
})

try {
  await waitForPort(port)
} catch (error) {
  console.error(error.message)
  vite.kill()
  process.exit(1)
}

const electron = spawn(command('npx'), ['electron', '.'], {
  cwd: root,
  stdio: 'inherit',
  env: {
    ...process.env,
    AIDOC_DEV_SERVER_URL: `http://127.0.0.1:${port}`,
  },
  shell: true,
})

electron.on('exit', (code) => {
  vite.kill()
  process.exit(code ?? 0)
})

process.on('SIGINT', () => {
  electron.kill()
  vite.kill()
  process.exit(0)
})
