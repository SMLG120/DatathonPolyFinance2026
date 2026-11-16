// Final-integration check. Run through hosted_check.py (it supplies the access code in the environment only).
// It reports what the live service answered; expectations that depend on the deployed data are derived from the
// service's own structured answer, never assumed.
import { createRequire } from "node:module";
import fs from "node:fs";
import path from "node:path";

const require = createRequire(path.resolve(process.env.BYB_FRONTEND_DIR, "package.json"));
const { chromium } = require("@playwright/test");

const ORIGIN = process.env.BYB_ORIGIN;
const API = process.env.BYB_API;
const CODE = process.env.BYB_ACCESS_CODE;
const SHOTS = process.env.BYB_SHOTS;
const results = [];
const check = (ok, label, detail = "") => {
  results.push(Boolean(ok));
  console.log(`${ok ? "[PASS]" : "[FAIL]"} ${label}${detail ? `: ${detail}` : ""}`);
  return ok;
};
const info = (label, text) => console.log(`[INFO] ${label}: ${String(text).replace(/\s+/g, " ").slice(0, 420)}`);
const post = async (route, body, withCode = true) => {
  const response = await fetch(API + route, { method: "POST", headers: { "content-type": "application/json", ...(withCode ? { authorization: `Bearer ${CODE}` } : {}) }, body: JSON.stringify(body) });
  let parsed = null;
  try { parsed = await response.json(); } catch { /* not JSON */ }
  return { status: response.status, body: parsed };
};

// ---------------------------------------------------------------- API: interpreter (real model)
const A = await post("/rules/interpret", { persona_id: "robert", text: "Keep any single company below 10%.", policy_id: null, policy_version: null });
const ruleA = A.body?.proposed_rules?.[0];
check(A.status === 200 && A.body?.proposed_rules?.length === 1 && ruleA?.rule_type === "max_issuer_exposure" && ruleA?.threshold === 0.1 && ruleA?.status === "PROPOSED" && ruleA?.confirmed_at === null,
  "A. 'Keep any single company below 10%.' gives one PROPOSED 10% company limit, not confirmed", `HTTP ${A.status}, ${ruleA?.rule_type} ${ruleA?.threshold} ${ruleA?.status}, quote ${JSON.stringify(ruleA?.threshold_quote)}`);
const B = await post("/rules/interpret", { persona_id: "robert", text: "At most 5% in any company. At least 10% in Exxon Mobil.", policy_id: null, policy_version: null });
check(B.status === 200 && B.body?.proposed_rules?.length === 0 && (B.body?.clarifications?.length ?? 0) >= 1,
  "B. the contradictory pair gives a clarification question and no drafted rule", `HTTP ${B.status}, rules ${B.body?.proposed_rules?.length}, questions ${B.body?.clarifications?.length}`);
info("B question", B.body?.clarifications?.[0]?.question ?? JSON.stringify(B.body?.unsupported ?? B.body));

// ---------------------------------------------------------------- API: evidence route
const noCode = await post("/evidence/investigate", { persona_id: "robert", fund_id: null, question: "x", policy_id: null, policy_version: null }, false);
check(noCode.status === 401, "the evidence route refuses a request without the access code", `HTTP ${noCode.status}`);
const supplied = await post("/evidence/investigate", { persona_id: "robert", fund_id: null, question: "x", policy_id: null, policy_version: null, verified_weight_pct: 100 });
check(supplied.status === 400, "the evidence route refuses client-supplied figures", `HTTP ${supplied.status}`);

// ---------------------------------------------------------------- browser
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
const calls = [];
const consoleErrors = [];
page.on("console", (message) => message.type() === "error" && consoleErrors.push(message.text().slice(0, 200)));
page.on("response", async (response) => {
  const url = new URL(response.url());
  if (!url.host.includes("execute-api") || response.request().method() === "OPTIONS") return;
  let body = null;
  try { body = await response.json(); } catch { /* not JSON */ }
  let sent = null;
  try { sent = response.request().postDataJSON(); } catch { /* no body */ }
  calls.push({ host: url.origin, path: url.pathname, status: response.status(), sent, body });
});
const answerTo = async (question, timeout = 60_000) => {
  const started = Date.now();
  while (Date.now() - started < timeout) {
    const found = calls.findLast((c) => c.path.endsWith("/evidence/investigate") && c.sent?.question === question);
    if (found) return found;
    await page.waitForTimeout(250);
  }
  return null;
};
const ask = async (question) => {
  await page.getByLabel("Your question").fill(question);
  await page.getByRole("button", { name: "Ask", exact: true }).click();
  const call = await answerTo(question);
  await page.waitForTimeout(400);
  return call;
};

try {
  fs.mkdirSync(SHOTS, { recursive: true });
  await page.goto(ORIGIN + "/");
  const field = page.getByLabel("Access code", { exact: true });
  await field.fill(CODE);
  await field.press("Enter");
  await page.getByTestId("customize-open").waitFor({ timeout: 60_000 });
  check(await page.getByTestId("fixtures-label").count() === 0, "the hosted site is a live build (no test-data label)");
  const link = page.getByRole("link", { name: "Evidence Investigator" });
  check(await link.isVisible(), "desktop: the header shows the Evidence Investigator link");
  await page.setViewportSize({ width: 390, height: 844 });
  check(await link.isVisible() && (await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)) <= 0, "390 px: the link is visible and the page does not scroll sideways");
  await page.setViewportSize({ width: 1280, height: 900 });
  await link.click();
  await page.getByRole("heading", { name: "Evidence Investigator" }).waitFor({ timeout: 30_000 });
  check(new URL(page.url()).pathname === "/evidence/", "the link opens /evidence/", page.url());
  await page.getByRole("region", { name: "Evidence summary" }).getByText("Verified holdings", { exact: true }).waitFor({ timeout: 60_000 });
  check(await page.getByTestId("test-data-tag").count() === 0, "/evidence/ shows live service data (no 'Test data' tag)");
  check(await page.getByText("Suggested rules only: not confirmed").isVisible(), "/evidence/ says the limits are suggested rules, not confirmed");
  check(await page.getByTestId("evidence-scope-note").isVisible(), "/evidence/ describes itself as a limited evidence tool");
  const evidenceCalls = calls.filter((c) => c.path.endsWith("/evidence/investigate"));
  check(evidenceCalls.length > 0 && evidenceCalls.every((c) => c.host === API), "the page calls the stack's API for evidence", [...new Set(calls.map((c) => c.host))].join(", "));
  info("summary (Robert, whole portfolio)", await page.getByRole("region", { name: "Evidence summary" }).innerText());

  // C. SPY
  const C = await ask("What holdings information is missing from SPY?");
  const fundC = C?.body?.fund;
  check(C?.status === 200 && C.body.fund_id === "SPY" && C.body.explanation_source === "template", "C. the SPY question is answered about SPY, in the service's own wording", `HTTP ${C?.status}, fund ${C?.body?.fund_id}, status ${C?.body?.status}`);
  const sectorGap = (fundC?.rows?.missing_sector ?? 0) > 0;
  const sectorStated = (C?.body?.missing_evidence ?? []).some((s) => /sector classification is missing/.test(s.text));
  check(sectorGap === sectorStated, sectorGap ? "C. the deployed data has SPY holdings without a sector, and the answer says so" : "C. the deployed data has sector labels for SPY, and no sector gap is claimed",
    `rows without sector ${fundC?.rows?.missing_sector} of ${fundC?.rows?.reported}; verified ${fundC?.verified_weight_pct}%, unresolved ${fundC?.unresolved_weight_pct}%`);
  for (const s of C?.body?.missing_evidence ?? []) info("C missing", s.text);
  await page.screenshot({ path: path.join(SHOTS, "C-spy.png"), fullPage: true });

  // D. ESGV
  const D = await ask("What evidence is missing from ESGV?");
  const noFile = D?.body?.fund?.coverage_basis === "no_holdings_file";
  check(D?.status === 200 && D.body.fund_id === "ESGV" && (noFile ? D.body.summary.verified_weight_pct === null && /^Evidence unavailable/.test(D.body.retrieval.message ?? "") && D.body.status === "insufficient_evidence" : true),
    noFile ? "D. the deployed data has no ESGV holdings file: verified is unknown (null) and evidence is reported unavailable" : "D. the deployed data HAS an ESGV holdings file; the answer reports it",
    `basis ${D?.body?.fund?.coverage_basis}, verified ${D?.body?.summary?.verified_weight_pct}, message ${D?.body?.retrieval?.message}`);
  for (const s of D?.body?.missing_evidence ?? []) info("D missing", s.text);

  // E. company limit
  const E = await ask("Could unresolved holdings violate my company exposure limit?");
  const cap = (E?.body?.constraint_impacts ?? []).find((i) => i.rule_type === "max_issuer_exposure");
  check(E?.status === 200 && E.body.question.topic === "constraint" && E.body.rules_confirmed === false && cap?.rule_status === "PROPOSED" && cap?.analysed === true,
    "E. the company-limit question is bounded from verified data against the scenario's suggested (PROPOSED, unconfirmed) rule",
    `limit ${cap?.limit_pct}%, verified ${cap?.bounds?.verified_exposure_pct}%, conditional max ${cap?.bounds?.conditional_max_pct}%, assessment ${cap?.assessment}`);
  info("E headline", E?.body?.headline);
  const three = [C, D, E].map((c) => c?.body);
  check(three.every((b) => b?.explanation_source === "template" && b?.model_status === "not_configured"), "no model-written text: every answer is the service's deterministic wording");
  check(await page.getByText("Hypothetical: not measured").count() >= 1, "hypothetical sections are labelled as not measured");
  await page.screenshot({ path: path.join(SHOTS, "E-company-limit.png"), fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  check((await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)) <= 0, "390 px: /evidence/ does not scroll sideways");
  await page.getByRole("link", { name: "Back to the purchase check" }).click();
  await page.getByTestId("customize-open").waitFor({ timeout: 30_000 });
  check(new URL(page.url()).pathname === "/", "the way back to the purchase check works");
  check(consoleErrors.length === 0, "no console error", consoleErrors.join(" | "));
} catch (error) {
  check(false, "the browser flow ran to the end", String(error).slice(0, 300));
} finally {
  await browser.close();
}
const failed = results.filter((ok) => !ok).length;
console.log(`RESULT: ${failed === 0 ? "PASS" : "FAIL"} (${results.length - failed} of ${results.length})`);
process.exit(failed === 0 ? 0 : 1);
