import { defineConfig, devices } from "@playwright/test";

/**
 * Validator's local config for specs/06-customize.spec.ts (independent validation of "Customize this profile").
 * Same stack as playwright.config.ts (the real handlers behind local_api.py, loopback only), but:
 *   - the Python interpreter comes from BYB_PYTHON (this machine has no `uv`);
 *   - the static site directory comes from BYB_SITE_DIR (built by validation/customize/run_browser.sh);
 *   - only 06-customize runs unless BYB_SPECS names another pattern.
 * Started through validation/customize/run_browser.sh.
 */
const API_PORT = Number(process.env.BYB_LOCAL_API_PORT ?? 4184);
const SITE_PORT = Number(process.env.BYB_LOCAL_SITE_PORT ?? 4185);
const CONTROL_PORT = Number(process.env.BYB_LOCAL_CONTROL_PORT ?? 4186);
const PYTHON = process.env.BYB_PYTHON;
const SITE_DIR = process.env.BYB_SITE_DIR;

if (!process.env.BYB_LOCAL_ACCESS_CODE || !PYTHON || !SITE_DIR) {
  throw new Error("BYB_LOCAL_ACCESS_CODE, BYB_PYTHON and BYB_SITE_DIR must be set: start the run with validation/customize/run_browser.sh");
}

export default defineConfig({
  testDir: ".",
  testMatch: new RegExp(process.env.BYB_SPECS ?? "specs/06-customize\\.spec\\.ts"),
  outputDir: process.env.BYB_OUTPUT_DIR ?? ".run/test-results-customize",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  timeout: 180_000,
  expect: { timeout: 15_000 },
  use: {
    ...devices["Desktop Chrome"],
    viewport: { width: 1280, height: 900 },
    baseURL: `http://127.0.0.1:${SITE_PORT}`,
    trace: "retain-on-failure",
  },
  webServer: {
    command: `"${PYTHON}" local_api.py --api-port ${API_PORT} --site-port ${SITE_PORT} --control-port ${CONTROL_PORT} --site-dir "${SITE_DIR}"`,
    url: `http://127.0.0.1:${CONTROL_PORT}/health`,
    reuseExistingServer: false,
    timeout: 60_000,
    stdout: "pipe",
    stderr: "pipe",
  },
});
