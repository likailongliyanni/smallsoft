import { spawn } from 'node:child_process'
import { createServer } from 'node:net'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const root = path.resolve(__dirname, '..')
const viteCli = path.join(root, 'node_modules', 'vite', 'bin', 'vite.js')
const electronCli = path.join(root, 'node_modules', 'electron', 'cli.js')

function portIsFree(portNumber, host = '127.0.0.1') {
  return new Promise((resolve) => {
    const probe = createServer()
    probe.once('error', () => resolve(false))
    probe.once('listening', () => probe.close(() => resolve(true)))
    probe.listen(portNumber, host)
  })
}

async function findAvailablePort(start = 5176, attempts = 20) {
  for (let offset = 0; offset < attempts; offset++) {
    const candidate = start + offset
    if (await portIsFree(candidate)) return candidate
  }
  throw new Error(`No available development port in ${start}-${start + attempts - 1}`)
}

const port = await findAvailablePort()

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

const vite = spawn(process.execPath, [viteCli, '--host', '127.0.0.1', '--port', String(port), '--strictPort'], {
  cwd: root,
  stdio: 'inherit',
  shell: false,
})

try {
  await waitForPort(port)
} catch (error) {
  console.error(error.message)
  vite.kill()
  process.exit(1)
}

const electron = spawn(process.execPath, [electronCli, '.'], {
  cwd: root,
  stdio: 'inherit',
  env: {
    ...process.env,
    AIDOC_DEV_SERVER_URL: `http://127.0.0.1:${port}`,
  },
  shell: false,
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
