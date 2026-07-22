import { defineConfig } from '@playwright/test'
import fs from 'fs'

// In the authoring sandbox a preinstalled Chromium lives at /opt/pw-browsers/chromium;
// on a normal machine `npx playwright install chromium` provides the default browser.
const sandboxChromium = '/opt/pw-browsers/chromium'

export default defineConfig({
  testDir: './tests/e2e',
  timeout: 120_000,
  retries: 0,
  reporter: 'line',
  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'http://localhost:8001',
    screenshot: 'only-on-failure',
    launchOptions: fs.existsSync(sandboxChromium) ? { executablePath: sandboxChromium } : {},
  },
})
