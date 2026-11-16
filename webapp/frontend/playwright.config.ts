import { resolve } from 'node:path'
import { defineConfig, devices } from '@playwright/test'

const port = 18090
const baseURL = `http://127.0.0.1:${port}`

export default defineConfig({
  testDir: './e2e',
  workers: 1,
  forbidOnly: Boolean(process.env.CI),
  projects: [
    {
      name: 'desktop Chromium',
      testMatch: ['desktop.spec.ts', 'recording.spec.ts'],
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'mobile Chromium',
      testMatch: 'mobile.spec.ts',
      use: { ...devices['Pixel 7'], viewport: { width: 390, height: 844 } },
    },
  ],
  use: {
    baseURL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  webServer: {
    command: `uv run --frozen uvicorn tests.browser_app:app --host 127.0.0.1 --port ${port}`,
    cwd: resolve(import.meta.dirname, '../src'),
    env: { FRONTEND_DIST: resolve(import.meta.dirname, 'dist') },
    url: `${baseURL}/healthz`,
    reuseExistingServer: false,
  },
})
