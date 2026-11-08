import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  testMatch: '**/*.spec.ts',
  globalSetup: './e2e/global-setup.ts',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [
    ['list'],
    ['html', { outputFolder: 'playwright-report', open: 'never' }],
  ],
  outputDir: 'test-results',
  use: {
    ...devices['Desktop Chrome'],
    baseURL: 'http://127.0.0.1:15173',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
})
