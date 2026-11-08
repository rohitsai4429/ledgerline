import { randomBytes } from 'node:crypto'
import { execFileSync, spawn, type ChildProcess } from 'node:child_process'
import { unlinkSync, writeFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import type { FullConfig } from '@playwright/test'

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const repositoryRoot = path.resolve(frontendRoot, '..')
const backendRoot = path.join(repositoryRoot, 'backend')
const statePath = path.join(frontendRoot, '.playwright-state.json')
const python = process.env.E2E_PYTHON ?? path.join(backendRoot, '.venv', 'Scripts', 'python.exe')

interface E2EState {
  schema: string
  suffix: string
  password: string
  adminEmail: string
  auditorEmail: string
}

function runDatabaseAction(action: 'setup' | 'cleanup', state: E2EState): void {
  execFileSync(
    python,
    ['scripts/e2e_db.py', action, state.schema, state.suffix],
    {
      cwd: backendRoot,
      stdio: 'inherit',
      env: { ...process.env, E2E_TEST_PASSWORD: state.password },
    },
  )
}

function startProcess(
  executable: string,
  args: string[],
  cwd: string,
  env: NodeJS.ProcessEnv,
): ChildProcess {
  const child = spawn(executable, args, { cwd, env, stdio: 'inherit' })
  child.on('error', (error) => {
    console.error(`E2E service failed to start: ${error.message}`)
  })
  return child
}

async function waitForService(url: string, process: ChildProcess): Promise<void> {
  const deadline = Date.now() + 60_000
  while (Date.now() < deadline) {
    if (process.exitCode !== null) {
      throw new Error(`E2E service exited before becoming ready (code ${process.exitCode})`)
    }
    try {
      const response = await fetch(url)
      if (response.ok) return
    } catch {
      // The service may still be starting.
    }
    await new Promise((resolve) => setTimeout(resolve, 300))
  }
  throw new Error(`E2E service did not become ready at ${url}`)
}

async function stopProcess(process: ChildProcess): Promise<void> {
  if (process.exitCode !== null || process.signalCode !== null) return
  const exited = new Promise<void>((resolve) => process.once('exit', () => resolve()))
  process.kill()
  await Promise.race([
    exited,
    new Promise<void>((resolve) => setTimeout(resolve, 5_000)),
  ])
}

async function globalSetup(_config: FullConfig): Promise<() => Promise<void>> {
  const suffix = randomBytes(6).toString('hex')
  const password = `${randomBytes(32).toString('base64url')}!aA9`
  const state: E2EState = {
    schema: `ledgerline_e2e_${suffix}`,
    suffix,
    password,
    adminEmail: `admin-e2e-${suffix}@example.com`,
    auditorEmail: `auditor-e2e-${suffix}@example.com`,
  }

  writeFileSync(statePath, JSON.stringify(state), {
    encoding: 'utf8',
    mode: 0o600,
    flag: 'wx',
  })
  let backendProcess: ChildProcess | undefined
  let frontendProcess: ChildProcess | undefined
  let databaseReady = false
  try {
    runDatabaseAction('setup', state)
    databaseReady = true
    backendProcess = startProcess(
      python,
      ['scripts/e2e_server.py'],
      backendRoot,
      {
        ...process.env,
        E2E_STATE_PATH: statePath,
      },
    )
    frontendProcess = startProcess(
      process.execPath,
      [
        path.join(frontendRoot, 'node_modules', 'vite', 'bin', 'vite.js'),
        '--host',
        '127.0.0.1',
        '--port',
        '15173',
        '--strictPort',
      ],
      frontendRoot,
      {
        ...process.env,
        VITE_API_BASE_URL: 'http://127.0.0.1:18000',
      },
    )
    await Promise.all([
      waitForService('http://127.0.0.1:18000/health', backendProcess),
      waitForService('http://127.0.0.1:15173/login', frontendProcess),
    ])
    return async () => {
      await stopProcess(frontendProcess)
      await stopProcess(backendProcess)
      runDatabaseAction('cleanup', state)
      unlinkSync(statePath)
    }
  } catch (error) {
    if (frontendProcess) await stopProcess(frontendProcess)
    if (backendProcess) await stopProcess(backendProcess)
    if (databaseReady) {
      try {
        runDatabaseAction('cleanup', state)
        unlinkSync(statePath)
      } catch {
        console.error(`Isolated E2E cleanup failed; review the local state file for schema ${state.schema}`)
      }
    }
    throw error
  }
}

export default globalSetup
