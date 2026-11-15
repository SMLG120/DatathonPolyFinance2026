import { defineConfig, devices } from "@playwright/test";

const PORT = Number(process.env.E2E_PORT ?? 4173);
const BASE_URL = `http://127.0.0.1:${PORT}`;
/** The live-mode build (`out-live/`). Must match LIVE_SITE in e2e/live.spec.ts. */
const LIVE_PORT = 4175;
const LIVE_BASE_URL = `http://127.0.0.1:${LIVE_PORT}`;

/**
 * End-to-end and accessibility checks run against the static exports that
 * `npm run test:e2e` builds first (scripts/build-e2e.mjs). They never talk to
 * the real API:
 * - `out/` is opened with `?fixtures=1` (desktop and mobile projects);
 * - `out-live/` is a live-mode build whose API address is a mock started by
 *   e2e/live.spec.ts (live project).
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: 0,
  reporter: [["list"]],
  timeout: 60_000,
  expect: { timeout: 10_000 },
  use: {
    baseURL: BASE_URL,
    trace: "retain-on-failure",
  },
  webServer: [
    {
      command: `node scripts/serve-out.mjs --port ${PORT}`,
      url: BASE_URL,
      reuseExistingServer: !process.env.CI,
      timeout: 30_000,
    },
    {
      command: `node scripts/serve-out.mjs --port ${LIVE_PORT} --dir out-live`,
      url: LIVE_BASE_URL,
      reuseExistingServer: !process.env.CI,
      timeout: 30_000,
    },
  ],
  projects: [
    {
      name: "desktop-chromium",
      use: { ...devices["Desktop Chrome"] },
      testIgnore: [/mobile\.spec\.ts/, /live\.spec\.ts/],
    },
    {
      name: "live-chromium",
      use: { ...devices["Desktop Chrome"], baseURL: LIVE_BASE_URL },
      testMatch: /live\.spec\.ts/,
    },
    {
      name: "mobile-chromium",
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 390, height: 844 },
        hasTouch: true,
        isMobile: true,
      },
      testMatch: /mobile\.spec\.ts/,
    },
  ],
});
