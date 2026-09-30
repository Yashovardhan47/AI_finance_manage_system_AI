import { spawn } from 'node:child_process'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url))
const backendDirectory = path.resolve(scriptDirectory, '..', '..', 'backend')
const python = process.env.E2E_PYTHON || 'python'

const child = spawn(
  python,
  ['-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8000'],
  {
    cwd: backendDirectory,
    env: {
      ...process.env,
      DATABASE_URL: 'sqlite:///./e2e.db',
      JWT_SECRET: 'e2e-secret',
      CORS_ORIGINS: 'http://localhost:4173',
      FRONTEND_URL: 'http://localhost:4173',
      AUTO_CREATE_SCHEMA: 'true',
    },
    stdio: 'inherit',
  },
)

let shuttingDown = false
for (const signal of ['SIGINT', 'SIGTERM']) {
  process.on(signal, () => {
    shuttingDown = true
    child.kill(signal)
  })
}

child.on('error', (error) => {
  console.error(`Unable to start the E2E backend: ${error.message}`)
  process.exitCode = 1
})

child.on('exit', (code) => process.exit(shuttingDown ? 0 : (code ?? 1)))
