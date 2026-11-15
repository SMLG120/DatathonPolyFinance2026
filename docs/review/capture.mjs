#!/usr/bin/env node
/**
 * Captures genuine screenshots of the built app (frontend/out) in FIXTURES mode.
 * Nothing here calls the real API. Usage, from the repo root:
 *   (cd frontend && npm ci && npm run build)
 *   node docs/review/capture.mjs <output-dir> [port]
 */
import { spawn } from "node:child_process";
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const frontend = path.resolve(here, "..", "..", "frontend");
const require = createRequire(path.join(frontend, "package.json"));
const { chromium } = require("@playwright/test");

const outDir = path.resolve(process.argv[2] ?? path.join(here, "screenshots", "latest"));
const port = Number(process.argv[3] ?? 4319);
const base = `http://127.0.0.1:${port}/?fixtures=1`;

const server = spawn("node", [path.join(frontend, "scripts", "serve-out.mjs"), "--port", String(port)], { stdio: "ignore" });
const log = [];
const consoleErrors = [];

async function waitForServer() {
  for (let i = 0; i < 50; i += 1) {
    try { if ((await fetch(base)).ok) return; } catch { /* not up yet */ }
    await new Promise((r) => setTimeout(r, 200));
  }
  throw new Error("static server did not start");
}

async function shot(page, name, note) {
  // Full-page captures paint sticky bars where the viewport is, so start from the top and let transitions end.
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForTimeout(400);
  await page.screenshot({ path: path.join(outDir, `${name}.png`), fullPage: true });
  log.push({ file: `${name}.png`, note });
}

async function robert(page, prefix) {
  await page.goto(base);
  await page.getByTestId("portfolio-table").waitFor();
  await shot(page, `${prefix}01-workspace-robert`, "Stage 1, Robert's fictional portfolio");
  await page.getByRole("link", { name: "Continue to Goals & rules" }).click();
  await page.getByTestId("propose-rules").click();
  await page.getByTestId("rule-card").first().waitFor();
  await shot(page, `${prefix}02-rules-proposed`, "Stage 2, proposed rules, inactive until confirmed");
  await page.getByTestId("confirm-all").click();
  await page.getByTestId("policy-rule-card").first().waitFor();
  await shot(page, `${prefix}03-policy-v1-confirmed`, "Stage 2, confirmed policy version 1");
  await page.getByRole("link", { name: "Continue to Proposed purchase" }).click();
  await page.getByTestId("before-after-table").waitFor();
  await shot(page, `${prefix}04-purchase-nvda-25`, "Stage 3, NVDA at 25% final direct weight, cash funded");
  await page.getByTestId("start-investigation").click();
  await page.getByTestId("timeline-waiting").waitFor({ timeout: 5000 }).catch(() => {});
  await shot(page, `${prefix}05-investigation-running`, "Stage 4, investigation in progress (fixture job)");
  await page.getByTestId("see-verdict").waitFor({ timeout: 30000 });
  await shot(page, `${prefix}06-investigation-done`, "Stage 4, all reported steps");
  await page.getByTestId("see-verdict").click();
  await page.getByTestId("verdict-headline").waitFor();
  await shot(page, `${prefix}07-verdict-failed-concentration`, "Stage 5, failed concentration check with exposure chart");
}

try {
  await waitForServer();
  const browser = await chromium.launch();

  // Desktop: Robert, evidence, rule change.
  const desktop = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await desktop.newPage();
  page.on("console", (m) => { if (m.type() === "error") consoleErrors.push(m.text()); });
  page.on("pageerror", (e) => consoleErrors.push(String(e)));
  await robert(page, "");
  await page.getByRole("button", { name: /^Evidence for Maximum exposure to a single company/ }).first().click();
  await page.getByRole("dialog").getByRole("heading", { name: "Calculation path" }).first().waitFor();
  await page.waitForTimeout(600); // drawer slide-in
  await page.screenshot({ path: path.join(outDir, "08-evidence-panel.png") });
  log.push({ file: "08-evidence-panel.png", note: "Stage 5, evidence drawer for the issuer-exposure rule (viewport only)" });
  await page.keyboard.press("Escape");
  await page.getByRole("link", { name: "Challenge this result" }).click();
  await page.getByRole("tab", { name: "Change a rule" }).click();
  const form = page.getByTestId("change-rule-form");
  await form.getByRole("textbox").fill("30");
  await form.getByTestId("draft-preview-result").waitFor();
  await shot(page, "09-rule-change-preview", "Stage 6, issuer cap 10% -> 30% as a draft preview, not yet confirmed");
  await page.getByTestId("submit-rule-change").click();
  await page.getByTestId("result-comparison").waitFor({ timeout: 30000 });
  await shot(page, "10-rule-change-recalculated", "Stage 6, policy version 2 and old vs new result");
  await desktop.close();

  // Desktop: Mateo, missing data.
  const mateoCtx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const m = await mateoCtx.newPage();
  await m.goto(base);
  await m.getByTestId("portfolio-table").waitFor();
  await m.getByRole("button", { name: "Use Mateo’s portfolio" }).click();
  await m.getByRole("link", { name: "Continue to Goals & rules" }).click();
  await m.getByTestId("propose-rules").click();
  const q = m.getByTestId("clarification-card");
  await q.waitFor();
  await shot(m, "11-mateo-clarification", "Mateo, the interpreter asks what 'oil' means instead of guessing");
  await q.getByRole("radio").first().check();
  await q.getByRole("button", { name: "Use this definition" }).click();
  await m.getByTestId("rule-card").nth(1).waitFor();
  for (const card of await m.getByTestId("rule-card").all()) await card.getByRole("textbox").fill("0");
  await m.getByTestId("confirm-all").click();
  await m.getByRole("link", { name: "Continue to Proposed purchase" }).click();
  await m.getByTestId("start-investigation").click();
  await m.getByTestId("see-verdict").click({ timeout: 30000 });
  await m.getByTestId("verdict-headline").waitFor();
  await shot(m, "12-mateo-missing-data-unknown", "Mateo, verdict with UNKNOWN results from missing holdings");
  await mateoCtx.close();

  // Mobile: Robert through the verdict.
  const mobile = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, deviceScaleFactor: 2 });
  await robert(await mobile.newPage(), "mobile-");
  await mobile.close();
  await browser.close();
  console.log(JSON.stringify({ outDir, shots: log, consoleErrors }, null, 2));
} finally {
  server.kill();
}
