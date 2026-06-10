import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: 'html',

  use: {
    baseURL: 'http://localhost:5000',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    headless: true,
  },

  projects: [
    {
      name: 'chromium',
      use: { browserName: 'chromium' },
    },
  ],

  webServer: {
    command: 'script/server',
    url: 'http://localhost:5000',
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
    env: {
      ...process.env,
      // The chat/page E2E tests need a readable Google Doc + Gemini key.
      // Provide these via the shell environment; the first three tests pass
      // with Docs access alone, the fourth additionally needs a live Gemini key.
      GOOGLE_DOC_ID: process.env.GOOGLE_DOC_ID ?? '',
      GOOGLE_SERVICE_ACCOUNT_JSON: process.env.GOOGLE_SERVICE_ACCOUNT_JSON ?? '',
      GEMINI_API_KEY: process.env.GEMINI_API_KEY ?? '',
    },
  },
});
