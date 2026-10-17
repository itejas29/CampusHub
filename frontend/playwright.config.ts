import { defineConfig } from "@playwright/test";

/**
 * Browser tests for the flows the portal exists for: sign in, allocate
 * internship mentors, review a student's submission.
 *
 * They run against their own API (fresh seeded SQLite, see e2e/start-api.sh)
 * and their own Vite server, on ports that do not clash with `npm run dev`.
 * The tests change data, so they run one at a time, in file order.
 *
 * Uses the installed Google Chrome — no Playwright browser download needed.
 * Set E2E_BROWSER_CHANNEL="" to use a Playwright-managed Chromium instead (CI).
 */
const API_PORT = Number(process.env.E2E_API_PORT ?? 8100);
const WEB_PORT = Number(process.env.E2E_WEB_PORT ?? 5180);
const channel = process.env.E2E_BROWSER_CHANNEL ?? "chrome";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  timeout: 60_000,
  expect: { timeout: 15_000 },
  reporter: [["list"], ["html", { open: "never", outputFolder: "playwright-report" }]],
  use: {
    baseURL: `http://localhost:${WEB_PORT}`,
    ...(channel ? { channel } : {}),
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    viewport: { width: 1440, height: 900 },
  },
  webServer: [
    {
      command: "sh e2e/start-api.sh",
      url: `http://localhost:${API_PORT}/docs`,
      env: { E2E_API_PORT: String(API_PORT) },
      // Seeding the full demo dataset takes a while on a cold machine.
      timeout: 300_000,
      reuseExistingServer: false,
    },
    {
      command: `./node_modules/.bin/vite --port ${WEB_PORT} --strictPort`,
      url: `http://localhost:${WEB_PORT}`,
      env: { VITE_PROXY_TARGET: `http://localhost:${API_PORT}` },
      timeout: 120_000,
      reuseExistingServer: false,
    },
  ],
});
