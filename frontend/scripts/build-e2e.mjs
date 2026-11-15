#!/usr/bin/env node
/**
 * Builds the two static sites the end-to-end tests need:
 *
 *   out-live/  built with an API address, so the app runs in live mode and
 *              asks for the access code. The address is a local mock that
 *              e2e/live.spec.ts starts; it is never a real service.
 *   out/       the normal build (`npm run build`), left in place afterwards
 *              so `out/` is always what a deployment would upload.
 *
 * The API address is fixed at build time and cannot be changed from the URL,
 * which is why live mode needs its own build.
 */
import { spawnSync } from "node:child_process";
import { cpSync, existsSync, rmSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

/** Must match LIVE_API in e2e/live.spec.ts. */
const LIVE_API_BASE_URL = "http://127.0.0.1:4174";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const nextBin = path.join(root, "node_modules", "next", "dist", "bin", "next");

function build(label, extraEnv) {
  console.log(`\nbuild-e2e: ${label}`);
  const result = spawnSync(process.execPath, [nextBin, "build"], { cwd: root, stdio: "inherit", env: { ...process.env, ...extraEnv } });
  if (result.status !== 0) {
    console.error(`build-e2e: ${label} failed`);
    process.exit(result.status ?? 1);
  }
}

build(`live-mode build for the access-code tests (API address ${LIVE_API_BASE_URL})`, { NEXT_PUBLIC_API_BASE_URL: LIVE_API_BASE_URL });
rmSync(path.join(root, "out-live"), { recursive: true, force: true });
cpSync(path.join(root, "out"), path.join(root, "out-live"), { recursive: true });

build("normal build into out/", {});
if (!existsSync(path.join(root, "out", "index.html")) || !existsSync(path.join(root, "out-live", "index.html"))) {
  console.error("build-e2e: a build did not produce index.html");
  process.exit(1);
}
console.log("\nbuild-e2e: out/ and out-live/ are ready");
