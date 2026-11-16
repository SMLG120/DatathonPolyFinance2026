// Hosted-site check after a release (read-only for the product: it creates one fictional policy and investigations).
// Run through validation/customize/hosted_check.py, which reads the access code from SSM and passes it in the
// environment of this process only. Nothing here prints the code.
import { createRequire } from "node:module";
import fs from "node:fs";
import path from "node:path";

const require = createRequire(path.resolve(process.env.BYB_FRONTEND_DIR, "package.json"));
const { chromium } = require("@playwright/test");

const ORIGIN = process.env.BYB_ORIGIN;
const CODE = process.env.BYB_ACCESS_CODE;
const SHOTS = process.env.BYB_SHOTS;
const results = [];
const check = (ok, label, detail = "") => {
  results.push(ok);
  console.log(`${ok ? "[PASS]" : "[FAIL]"} ${label}${!ok && detail ? `: ${detail}` : ""}`);
  return ok;
};

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
const calls = [];
const consoleErrors = [];
page.on("console", (message) => message.type() === "error" && consoleErrors.push(message.text().slice(0, 200)));
page.on("response", async (response) => {
  const url = new URL(response.url());
  if (!url.host.includes("execute-api")) return;
  const request = response.request();
  if (request.method() === "OPTIONS") return;
  let body = null;
  try { body = await response.json(); } catch { /* not JSON */ }
  let sent = null;
  try { sent = request.postDataJSON(); } catch { /* no body */ }
  calls.push({ method: request.method(), path: url.pathname, status: response.status(), sent, body });
});
const waitFor = async (predicate, timeout = 120_000) => {
  const started = Date.now();
  while (Date.now() - started < timeout) {
    const found = calls.findLast(predicate);
    if (found) return found;
    await page.waitForTimeout(300);
  }
  return null;
};
const go = (stage) => page.evaluate((id) => (window.location.hash = `#/${id}`), stage);
const shot = (name) => page.screenshot({ path: path.join(SHOTS, `${name}.png`), fullPage: true });

try {
  fs.mkdirSync(SHOTS, { recursive: true });
  await page.goto(ORIGIN + "/");
  const field = page.getByLabel("Access code", { exact: true });
  await field.fill(CODE);
  await field.press("Enter");
  await page.getByTestId("customize-open").waitFor({ timeout: 60_000 });
  check(await page.getByTestId("fixtures-label").count() === 0, "the hosted site is a live build (no 'Test data: fixtures' label)");
  check(await page.getByTestId("simulation-label").isVisible(), "the simulation label is shown");

  // The palette of the published build (PR #20 with the contrast fixes): read from the page, not from the source.
  const palette = await page.evaluate(() => {
    const root = getComputedStyle(document.documentElement);
    const token = (name) => root.getPropertyValue(name).trim().toLowerCase();
    const primary = [...document.querySelectorAll("button, a")].map((element) => getComputedStyle(element).backgroundImage).find((image) => image.includes("linear-gradient") && image.includes("rgb(79, 70, 229)")) ?? "";
    return { direct: token("--color-chart-direct"), indirect: token("--color-chart-indirect"), banner: token("--color-banner"), primary };
  });
  check(palette.banner === "#2448c6", "the new palette is published (banner colour)", palette.banner);
  check(palette.direct === "#2247bd" && palette.indirect === "#5b82e6", "the exposure series use the distinguishable colours", `${palette.direct} / ${palette.indirect}`);
  check(palette.primary.includes("rgb(124, 58, 237)") && !palette.primary.includes("rgb(139, 92, 246)"), "the primary button's gradient ends on the readable violet", palette.primary.slice(0, 120));

  // Amira (new in this frontend)
  await page.getByTestId("persona-amira").getByRole("button").click();
  await page.getByTestId("persona-amira").getByTestId("persona-selected").waitFor({ timeout: 30_000 });
  const amira = await waitFor((c) => c.method === "GET" && c.path.endsWith("/portfolios/amira"));
  check(amira?.status === 200 && amira.body?.scenario?.persona?.persona_id === "amira", "Amira's portfolio loads from the live API", `HTTP ${amira?.status}`);

  // Robert, customized
  await page.getByTestId("persona-robert").getByRole("button").click();
  await page.getByTestId("persona-robert").getByTestId("persona-selected").waitFor({ timeout: 30_000 });
  await page.getByTestId("customize-open").click();
  await page.getByTestId("customize-remove-JNJ").click();
  await page.getByTestId("customize-weight-SPY").fill("15");
  await page.getByTestId("customize-cash").fill("40");
  check((await page.getByTestId("customize-total").getAttribute("data-total-valid")) === "true", "the editor accepts weights totalling 100%");
  await shot("hosted-01-editor");
  await page.getByTestId("customize-apply").click();
  await page.getByTestId("customized-badge").first().waitFor({ timeout: 10_000 });
  check(true, "the customized badge is shown after Apply");
  const expected = { cash_weight: 0.4, positions: [{ instrument_id: "XBB.TO", weight: 0.3 }, { instrument_id: "SPY", weight: 0.15 },
                                                   { instrument_id: "XIU.TO", weight: 0.1 }, { instrument_id: "RY.TO", weight: 0.05 }] };

  await go("goals");
  await page.getByTestId("rule-card").first().waitFor({ timeout: 30_000 });
  await page.getByTestId("confirm-rules").click();
  await page.getByTestId("policy-rule-card").first().waitFor({ timeout: 30_000 });
  const confirm = await waitFor((c) => c.method === "POST" && c.path.endsWith("/rules/confirm"));
  check(confirm?.status === 201, "the scenario rules are confirmed into a policy version", `HTTP ${confirm?.status}`);

  await go("purchase");
  await page.getByTestId("funding-statement").waitFor({ timeout: 30_000 });
  await page.getByLabel("Which investment?").selectOption("NVDA");
  await page.getByLabel("Share of the portfolio after buying").fill("25");
  const preview = await waitFor((c) => c.method === "POST" && c.path.endsWith("/check") && c.status === 200 && c.sent?.purchase_request?.target_direct_weight === 0.25, 40_000);
  check(JSON.stringify(preview?.sent?.custom_portfolio) === JSON.stringify(expected), "the preview request carries exactly the displayed customized weights");
  check(String(preview?.body?.portfolio_id).startsWith("pf-robert-custom-"), "the live engine checked a customized portfolio", preview?.body?.portfolio_id);

  await page.getByTestId("start-investigation").click();
  const created = await waitFor((c) => c.method === "POST" && c.path.endsWith("/investigations"), 40_000);
  check(created?.status === 202 && JSON.stringify(created.sent?.custom_portfolio) === JSON.stringify(expected), "the investigation is accepted with the customized weights", `HTTP ${created?.status}`);
  const done = await waitFor((c) => c.method === "GET" && /\/investigations\/inv-/.test(c.path) && c.body?.id === created?.body?.id && ["SUCCEEDED", "FAILED"].includes(c.body?.status), 200_000);
  if (check(done?.body?.status === "SUCCEEDED", "the live investigation succeeds", JSON.stringify(done?.body?.failure ?? done?.body?.status))) {
    const job = done.body;
    check(job.portfolio?.portfolio_id === job.result.portfolio_id && job.portfolio.portfolio_id.startsWith("pf-robert-custom-"), "the job stores the customized portfolio it was checked against");
    check(job.result.feasibility.cash_before === 0.4, "the engine used the customized cash (40%)", String(job.result.feasibility.cash_before));
    console.log(`[INFO] investigation ${job.id}: agent mode ${job.agent.mode}, headline ${job.result.summary.headline}`);
    const report = page.getByTestId("report");
    await report.waitFor({ timeout: 90_000 }).catch(async () => { await go("verdict"); await report.waitFor({ timeout: 30_000 }); });
    const block = report.getByTestId("report-portfolio");
    check((await block.getAttribute("data-customized")) === "true", "the report labels the portfolio as customized");
    check((await block.getByTestId("report-portfolio-label").innerText()).trim() === "Customized fictional portfolio", "the report says 'Customized fictional portfolio'");
    await block.evaluate((element) => (element.open = true));
    const text = await block.innerText();
    check(text.includes("15.0%") && text.includes("40.0%") && !text.includes("JNJ"), "the report shows the edited weights (SPY 15%, cash 40%, no JNJ)");
    await shot("hosted-02-report-customized");
  }
  check(consoleErrors.length === 0, "no error in the browser console", consoleErrors.slice(0, 3).join(" | "));

  // Mobile layout, 390 px: the report just produced, then step 1 with Amira, without sideways scrolling.
  const noOverflow = () => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.waitForTimeout(300);
  check(await noOverflow(), "390 px: the customized report does not scroll sideways");
  await shot("hosted-03-report-390px");
  await go("persona");
  await page.getByTestId("persona-amira").getByRole("button").click();
  await page.getByTestId("persona-amira").getByTestId("persona-selected").waitFor({ timeout: 30_000 });
  await page.getByTestId("customize-open").waitFor({ timeout: 30_000 });
  check(await noOverflow(), "390 px: step 1 with three personas and Amira selected does not scroll sideways");
  check(await page.getByTestId("customize-open").isVisible(), "390 px: 'Customize this profile' is reachable for Amira");
  await shot("hosted-04-amira-390px");
} catch (error) {
  check(false, "the hosted journey ran to the end", String(error).slice(0, 300));
  await shot("hosted-99-failure").catch(() => undefined);
} finally {
  await browser.close();
}
const failed = results.filter((ok) => !ok).length;
console.log(failed ? `FAILED: ${failed} hosted check(s) failed.` : `PASS: ${results.length} hosted checks.`);
process.exit(failed ? 1 : 0);
