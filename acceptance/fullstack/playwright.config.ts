import { defineConfig, devices } from "@playwright/test";

/**
 * Full-stack acceptance: the live-mode static build of the frontend (served on SITE) against the real backend
 * handlers behind local_api.py (API). Loopback only. Started through ./run.sh, which builds the site, generates the
 * made-up access code and exports the variables read here.
 */
const API_PORT = Number(process.env.BYB_LOCAL_API_PORT ?? 4184);
const SITE_PORT = Number(process.env.BYB_LOCAL_SITE_PORT ?? 4185);
const CONTROL_PORT = Number(process.env.BYB_LOCAL_CONTROL_PORT ?? 4186);

// BYB_PYTHON: an interpreter that has boto3 and jsonschema, for a machine without `uv`. BYB_SITE_DIR: the built site.
const PYTHON = process.env.BYB_PYTHON
  ? `"${process.env.BYB_PYTHON}"`
  : "uv run --offline --no-project --python 3.14 --with boto3 --with jsonschema python";
const SITE_DIR = process.env.BYB_SITE_DIR ? ` --site-dir "${process.env.BYB_SITE_DIR}"` : "";

if (!process.env.BYB_LOCAL_ACCESS_CODE) {
  throw new Error("BYB_LOCAL_ACCESS_CODE is not set: start the run with acceptance/fullstack/run.sh");
}

export default defineConfig({
  testDir: ".",
  testMatch: /specs\/.*\.spec\.ts/,
  outputDir: process.env.BYB_OUTPUT_DIR ?? ".run/test-results",
  // One backend with global switches (Bedrock mode, delays, throttling): tests run one after another.
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  timeout: 120_000,
  expect: { timeout: 15_000 },
  use: {
    ...devices["Desktop Chrome"],
    viewport: { width: 1280, height: 900 },
    baseURL: `http://127.0.0.1:${SITE_PORT}`,
    trace: "retain-on-failure",
  },
  webServer: {
    command:
      `${PYTHON} local_api.py --api-port ${API_PORT} --site-port ${SITE_PORT} --control-port ${CONTROL_PORT}${SITE_DIR}`,
    url: `http://127.0.0.1:${CONTROL_PORT}/health`,
    reuseExistingServer: false,
    timeout: 60_000,
    stdout: "pipe",
    stderr: "pipe",
  },
});
