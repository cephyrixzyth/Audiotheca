import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  expect: { timeout: 15_000 },
  timeout: 60_000,
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: "list",
  use: {
    baseURL: "http://127.0.0.1:45173",
    trace: "on-first-retry",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: "python scripts/browser_test_api.py",
      cwd: "..",
      url: "http://127.0.0.1:48787/api/health",
      reuseExistingServer: false,
      timeout: 120_000,
      env: {
        ...process.env,
        AUDIOTHECA_NO_RELOAD: "1",
        AUDIOTHECA_API_HOST: "127.0.0.1",
        AUDIOTHECA_API_PORT: "48787",
      },
    },
    {
      env: { VITE_API_PORT: "48787" },
      command: "npm run dev -- --host 127.0.0.1 --port 45173",
      url: "http://127.0.0.1:45173",
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ],
});
