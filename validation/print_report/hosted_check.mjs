// "Print / Save as PDF" on the hosted site, in headless Chromium. Run through hosted_check.py, which reads the access
// code from SSM and passes it in the environment of this process only. Nothing here prints the code.
//
// Two real investigations on the deployed backend: a customized Robert portfolio, and Mateo with limits that lie
// inside the possible range (UNKNOWN). For each: the export button calls the browser's print; the print document is
// compared with the job the page received and with the figures the screen report shows; the PDF is written.
import { createRequire } from "node:module";
import fs from "node:fs";
import path from "node:path";

const require = createRequire(path.resolve(process.env.BYB_FRONTEND_DIR, "package.json"));
const { chromium } = require("@playwright/test");

const ORIGIN = process.env.BYB_ORIGIN;
const CODE = process.env.BYB_ACCESS_CODE;
const PDF_DIR = process.env.BYB_PDF_DIR;
const results = [];
const check = (ok, label, detail = "") => {
  results.push(Boolean(ok));
  console.log(`${ok ? "[PASS]" : "[FAIL]"} ${label}${!ok && detail ? `: ${detail}` : ""}`);
  return Boolean(ok);
};
const DATE = (iso) => {
  const [year, month, day] = iso.split("-").map(Number);
  return `${day} ${["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][month - 1]} ${year}`;
};
const squash = (text) => (text ?? "").replace(/\s+/g, " ").trim();

const browser = await chromium.launch();

async function session() {
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
  await page.goto(ORIGIN + "/");
  const field = page.getByLabel("Access code", { exact: true });
  await field.fill(CODE);
  await field.press("Enter");
  await page.getByTestId("customize-open").waitFor({ timeout: 60_000 });
  return { page, waitFor, go, consoleErrors };
}

/** Confirm the rules on screen, enter the purchase, run the investigation, wait for the report. Returns the job. */
async function investigate({ page, waitFor, go }, instrument, percent) {
  await page.getByTestId("confirm-rules").click();
  await page.getByTestId("policy-rule-card").first().waitFor({ timeout: 30_000 });
  await go("purchase");
  await page.getByTestId("funding-statement").waitFor({ timeout: 30_000 });
  await page.getByLabel("Which investment?").selectOption(instrument);
  await page.getByLabel("Share of the portfolio after buying").fill(percent);
  await page.getByTestId("start-investigation").click();
  const created = await waitFor((c) => c.method === "POST" && c.path.endsWith("/investigations"), 40_000);
  const done = await waitFor((c) => c.method === "GET" && /\/investigations\/inv-/.test(c.path) && c.body?.id === created?.body?.id && ["SUCCEEDED", "FAILED"].includes(c.body?.status), 200_000);
  if (!check(done?.body?.status === "SUCCEEDED", `the live investigation of ${instrument} to ${percent}% succeeds`, JSON.stringify(done?.body?.failure ?? done?.body?.status))) return null;
  const report = page.getByTestId("report");
  await report.waitFor({ timeout: 90_000 }).catch(async () => { await go("verdict"); await report.waitFor({ timeout: 30_000 }); });
  console.log(`[INFO] investigation ${done.body.id}: agent mode ${done.body.agent.mode}, headline ${done.body.result.summary.headline}`);
  return done.body;
}

/** The export on the report now on screen. Returns the print document, shown in print media. */
async function exportAndCompare(page, job, name) {
  const result = job.result;
  // What the screen report shows for each rule, read before anything is printed.
  const shown = await page.getByTestId("report").getByTestId("rule-result").evaluateAll((rows) =>
    rows.map((row) => ({
      id: row.getAttribute("data-rule-id"),
      status: row.getAttribute("data-status"),
      measured: row.querySelector('[data-testid="rule-measured"]')?.textContent,
      limit: row.querySelector('[data-testid="rule-limit"]')?.textContent,
      gap: row.querySelector('[data-testid="rule-gap"]')?.textContent,
      reason: row.querySelector('[data-testid="rule-reason"]')?.textContent,
    })),
  );
  const shownHeadline = squash(await page.getByTestId("report").getByTestId("verdict-summary").getByRole("heading").first().textContent());

  const button = page.getByTestId("result-actions").getByRole("button", { name: "Print / Save as PDF" });
  check(await button.isVisible(), `${name}: the report has a "Print / Save as PDF" button`);
  check((await page.getByTestId("print-report").count()) === 0, `${name}: no print document exists before printing`);
  await page.evaluate(() => {
    window.__printCalls = 0;
    window.print = () => { window.__printCalls += 1; };
  });
  await button.click();
  check((await page.evaluate(() => window.__printCalls)) === 1, `${name}: the button calls the browser's print once`);
  const doc = page.getByTestId("print-report");
  check((await doc.count()) === 1 && !(await doc.isVisible()), `${name}: the print document is prepared and is not shown on screen`);
  check((await page.title()).includes(job.id), `${name}: the page title (the proposed PDF file name) carries the investigation id`);

  await page.emulateMedia({ media: "print" });
  check(await doc.isVisible(), `${name}: in print media the document is shown`);
  const hidden = [];
  for (const testId of ["simulation-label", "report", "result-actions", "what-next"]) hidden.push(!(await page.getByTestId(testId).first().isVisible()));
  check(hidden.every(Boolean), `${name}: banner, interactive report and controls are not printed`);
  check((await doc.locator("button, a, input, select, textarea, summary, svg, canvas").count()) === 0, `${name}: the document has no control, link or chart`);
  check(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1), `${name}: nothing overflows sideways in print`);

  const text = async (testId) => squash(await doc.getByTestId(testId).first().textContent());
  check((await text("print-simulation-label")).includes("Simulation: fictional portfolio, not advice"), `${name}: simulation label`);
  check((await text("print-not-advice")).includes("not personalized financial advice"), `${name}: says it is not personalized financial advice`);
  check((await doc.getByTestId("print-test-data").count()) === 0, `${name}: not marked as test data (live service)`);
  check((await text("print-investigation-id")) === job.id, `${name}: investigation id is the job's`);
  check((await text("print-policy")).includes(`Version ${result.policy_version}`) && (await text("print-policy")).includes(result.policy_id), `${name}: policy version and id are the result's`);
  check((await text("print-valuation-date")) === DATE(result.valuation_date), `${name}: valuation date is the result's (${result.valuation_date})`, await text("print-valuation-date"));
  check((await doc.getByTestId("print-verdict").getAttribute("data-headline")) === result.summary.headline, `${name}: verdict headline is the engine's (${result.summary.headline})`);
  check((await text("print-headline")) === shownHeadline, `${name}: the printed headline is the one on screen`, `${await text("print-headline")} / ${shownHeadline}`);
  check((await text("print-counts")).includes(`Pass: ${result.summary.counts.pass}. Fail: ${result.summary.counts.fail}. Unknown: ${result.summary.counts.unknown}.`), `${name}: counts are the engine's`);

  const printed = await doc.getByTestId("print-rule").evaluateAll((rows) =>
    rows.map((row) => ({
      id: row.getAttribute("data-rule-id"),
      status: row.getAttribute("data-status"),
      measured: row.querySelector('[data-testid="print-rule-measured"]')?.textContent,
      limit: row.querySelector('[data-testid="print-rule-limit"]')?.textContent,
      gap: row.querySelector('[data-testid="print-rule-gap"]')?.textContent,
      text: row.textContent,
    })),
  );
  check(printed.length === result.rule_results.length && printed.every((row, index) => row.id === result.rule_results[index].rule_id && row.status === result.rule_results[index].status),
    `${name}: every rule of the result is printed with the engine's status (${result.rule_results.map((rule) => rule.status).join(", ")})`);
  check(printed.length === shown.length && printed.every((row, index) => row.id === shown[index].id && squash(row.measured) === squash(shown[index].measured) && squash(row.limit) === squash(shown[index].limit) && squash(row.gap) === squash(shown[index].gap)),
    `${name}: measured value, limit and gap of each rule are printed exactly as the screen shows them`, JSON.stringify({ printed: printed.map(({ measured, limit, gap }) => [measured, limit, gap]), shown: shown.map(({ measured, limit, gap }) => [measured, limit, gap]) }));
  check(printed.every((row, index) => squash(row.text).includes(squash(shown[index].reason)) && squash(shown[index].reason) === squash(result.rule_results[index].reason)), `${name}: each rule's reason is the engine's sentence, on screen and in print`);
  check((await doc.getByTestId("print-coverage-row").count()) === result.data_coverage.length, `${name}: one coverage row per fund of the result (${result.data_coverage.length})`);
  check((await doc.getByTestId("print-portfolio-row").count()) === job.portfolio.positions.length + 1, `${name}: the portfolio stored with the job is printed, position by position`);
  const sources = new Set([...result.evidence.flatMap((record) => record.source_ids), ...result.data_coverage.flatMap((fund) => (fund.source_id ? [fund.source_id] : []))]);
  const sourceText = await text("print-sources");
  check((await doc.getByTestId("print-source").count()) === sources.size && [...sources].every((id) => sourceText.includes(id)), `${name}: the ${sources.size} source ids recorded with the figures are printed`);
  check((await text("print-source-note")).includes("The source registry is not delivered to this page") && !/https?:\/\//.test(sourceText), `${name}: the document says source details are not available and prints no URL`);
  check((await Promise.all(result.disclosures.map(async (disclosure) => (await text("print-disclosures")).includes(squash(disclosure))))).every(Boolean), `${name}: the result's ${result.disclosures.length} disclosures are printed`);
  return doc;
}

async function writePdf(page, name) {
  fs.mkdirSync(PDF_DIR, { recursive: true });
  const file = path.join(PDF_DIR, `${name}.pdf`);
  await page.pdf({ path: file, format: "Letter", preferCSSPageSize: false });
  check(fs.statSync(file).size > 10_000, `${name}: PDF written by the browser (${fs.statSync(file).size} bytes)`);
  console.log(`[INFO] pdf ${file}`);
  // Producing a PDF is a print: the browser fires afterprint and the document is removed again.
  check((await page.getByTestId("print-report").count()) === 0, `${name}: after printing the print document is removed`);
  await page.emulateMedia({ media: "screen" });
  check(await page.getByTestId("report").isVisible(), `${name}: the interactive report is back on screen`);
}

try {
  // ---- 1. Robert, customized: JNJ removed, SPY 15%, cash 40% --------------------------------------------------
  {
    const s = await session();
    const { page } = s;
    check((await page.getByTestId("fixtures-label").count()) === 0, "the hosted site is a live build (no 'Test data: fixtures' label)");
    await page.getByTestId("persona-robert").getByTestId("persona-selected").waitFor({ timeout: 30_000 });
    await page.getByTestId("customize-open").click();
    await page.getByTestId("customize-remove-JNJ").click();
    await page.getByTestId("customize-weight-SPY").fill("15");
    await page.getByTestId("customize-cash").fill("40");
    await page.getByTestId("customize-apply").click();
    await page.getByTestId("customized-badge").first().waitFor({ timeout: 10_000 });
    await s.go("goals");
    await page.getByTestId("rule-card").first().waitFor({ timeout: 30_000 });
    const job = await investigate(s, "NVDA", "25");
    if (job) {
      check(String(job.portfolio?.portfolio_id).startsWith("pf-robert-custom-"), "Robert: the job stores a customized portfolio", job.portfolio?.portfolio_id);
      const doc = await exportAndCompare(page, job, "robert-customized");
      const label = doc.getByTestId("print-portfolio-label");
      check((await label.getAttribute("data-customized")) === "true" && squash(await label.textContent()).includes("Customized fictional portfolio") && squash(await label.textContent()).includes(job.portfolio.portfolio_id),
        "robert-customized: the document names the portfolio as customized, with the stored id");
      const rows = (await doc.getByTestId("print-portfolio-row").allTextContents()).map(squash);
      const row = (id) => rows.find((line) => line.includes(`(${id})`)) ?? "";
      check(row("SPY").endsWith("15.0%") && row("XBB.TO").endsWith("30.0%") && row("XIU.TO").endsWith("10.0%") && row("RY.TO").endsWith("5.0%") && rows.at(-1).endsWith("40.0%") && !rows.some((line) => line.includes("(JNJ)")),
        "robert-customized: the customized weights are printed (SPY 15.0%, cash 40.0%, no JNJ)", rows.join(" | "));
      check(squash(await doc.getByTestId("print-persona").textContent()).includes("Robert"), "robert-customized: persona");
      check((await doc.getByTestId("print-limitations").count()) === 1, "robert-customized: the block of unknowns and limitations is printed");
      await writePdf(page, "hosted-robert-customized-letter");
      // The interactive journey afterwards: evidence opens, and the report still leads on.
      await page.getByTestId("report").getByTestId("rule-result").first().getByRole("button", { name: /evidence/i }).first().click();
      check(await page.getByRole("dialog").isVisible(), "robert-customized: after printing, the evidence drawer still opens");
      await page.keyboard.press("Escape");
    }
    check(s.consoleErrors.length === 0, "robert-customized: no error in the browser console", s.consoleErrors.slice(0, 3).join(" | "));
    await page.close();
  }

  // ---- 2. Mateo, limits of 10% and 5% inside the possible range: UNKNOWN ----------------------------------------
  {
    const s = await session();
    const { page } = s;
    await page.getByTestId("persona-mateo").getByRole("button").click();
    await page.getByTestId("persona-mateo").getByTestId("persona-selected").waitFor({ timeout: 30_000 });
    await page.getByTestId("customize-open").waitFor({ timeout: 30_000 });
    await s.go("goals");
    const cards = page.getByTestId("rule-card");
    await cards.first().waitFor({ timeout: 30_000 });
    await cards.nth(0).getByRole("textbox").fill("10");
    await cards.nth(1).getByRole("textbox").fill("5");
    const job = await investigate(s, "SPY", "15");
    if (job) {
      const unknown = job.result.rule_results.filter((rule) => rule.status === "UNKNOWN");
      check(unknown.length > 0, `Mateo: the live result has UNKNOWN rules (${job.result.rule_results.map((rule) => rule.status).join(", ")})`);
      const doc = await exportAndCompare(page, job, "mateo-unknown");
      check(squash(await doc.getByTestId("print-persona").textContent()).includes("Mateo"), "mateo-unknown: persona");
      check((await doc.getByTestId("print-portfolio-label").getAttribute("data-customized")) === "false", "mateo-unknown: the portfolio is named as the persona's original one");
      check((await doc.getByTestId("print-unknown-note").count()) === unknown.length && (await doc.getByTestId("print-unknown-causes").count()) >= unknown.length,
        `mateo-unknown: each UNKNOWN rule keeps "Unknown is not a pass" and why it is unknown (${unknown.length})`);
      const verdict = squash(await doc.getByTestId("print-verdict").textContent());
      check(job.result.summary.headline !== "NO_FAIL_BUT_UNKNOWN" || (verdict.includes("Not determined") && verdict.includes("this is not a pass")), "mateo-unknown: the verdict says not determined, and that this is not a pass");
      const limitations = squash(await doc.getByTestId("print-limitations").textContent());
      check(limitations.includes("UNKNOWN") && limitations.includes("never counted as a pass"), "mateo-unknown: UNKNOWN is listed under the verdict as not counted as a pass");
      check(job.result.data_coverage.filter((fund) => fund.status !== "COVERED").every((fund) => limitations.includes(fund.fund_id)), "mateo-unknown: every fund with missing or partial holdings is listed as a limitation");
      const order = await doc.evaluate((element) => [...element.children].map((child) => child.getAttribute("data-testid")));
      check(order.indexOf("print-limitations") === order.indexOf("print-verdict") + 1, "mateo-unknown: the limitations come straight after the verdict");
      check(job.result.max_compliant?.status !== "WITHHELD" || squash(await doc.getByTestId("print-max-withheld").textContent()).includes("No maximum is shown."), "mateo-unknown: no largest purchase is printed when it is withheld");
      await writePdf(page, "hosted-mateo-unknown-letter");
    }
    check(s.consoleErrors.length === 0, "mateo-unknown: no error in the browser console", s.consoleErrors.slice(0, 3).join(" | "));
    await page.close();
  }
} catch (error) {
  check(false, "the check ran to its end", String(error?.stack ?? error).slice(0, 600));
} finally {
  await browser.close();
}
const failed = results.filter((ok) => !ok).length;
console.log(`RESULT: ${failed === 0 ? "PASS" : "FAIL"} (${results.length - failed} of ${results.length})`);
process.exit(failed === 0 ? 0 : 1);
