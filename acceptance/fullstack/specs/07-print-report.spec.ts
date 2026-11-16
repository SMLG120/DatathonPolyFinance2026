import fs from "node:fs";
import path from "node:path";
import { expect, test, type Page } from "@playwright/test";
import {
  choosePersona,
  confirmOfferedRules,
  goToGoals,
  goToPurchase,
  openApp,
  resetBackend,
  setPurchase,
  SIMULATION_LABEL,
  startAndOpenVerdict,
  Traffic,
} from "./helpers";

/**
 * "Print / Save as PDF" of a finished report, in a real browser against the real handlers, worker and engine on
 * the real data snapshot (local_api.py). Run with:
 *
 *   BYB_SPECS='specs/07-print-report\.spec\.ts' validation/customize/run_browser.sh
 *
 * Each case drives the ordinary journey to a report, uses the export button, checks the print document against the
 * job the page received, writes the PDF the browser produces, and then goes on using the interactive page.
 * The PDFs go to BYB_PDF_DIR (default: the test output directory); they are generated files and are not versioned.
 */

const PDF_DIR = process.env.BYB_PDF_DIR ?? path.resolve(process.env.BYB_OUTPUT_DIR ?? path.resolve(__dirname, "..", ".run"), "print-report-pdf");

async function finishedJob(traffic: Traffic) {
  return (await traffic.last("GET", /^\/investigations\/inv-[0-9a-f]+$/, (call) => call.body?.status === "SUCCEEDED", 60_000)).body;
}

/** The export button -> the print document exists and is hidden on screen -> print media shows it alone. */
async function exportReport(page: Page, job: any, name: string, format: "Letter" | "A4" = "Letter") {
  const button = page.getByTestId("result-actions").getByRole("button", { name: "Print / Save as PDF" });
  await expect(button).toBeVisible();
  await expect(page.getByTestId("print-report")).toHaveCount(0);

  // The print dialog cannot be driven: the call is recorded instead, and the PDF is produced by the browser below.
  await page.evaluate(() => {
    (window as any).__printCalls = 0;
    window.print = () => {
      (window as any).__printCalls += 1;
    };
  });
  await button.click();
  expect(await page.evaluate(() => (window as any).__printCalls)).toBe(1);
  const doc = page.getByTestId("print-report");
  await expect(doc).toHaveCount(1);
  await expect(doc).toBeHidden(); // never shown on screen
  await expect(doc).toHaveAttribute("data-job-id", job.id);
  expect(await page.title()).toContain(job.id);

  await page.emulateMedia({ media: "print" });
  await expect(doc).toBeVisible();
  // Navigation, the interactive report and every control are out of the printed page.
  for (const testId of ["simulation-label", "report", "result-actions", "evidence-investigator-link"]) await expect(page.getByTestId(testId).first()).toBeHidden();
  expect(await doc.locator("button, a, input, select, textarea, summary, svg, canvas").count()).toBe(0);
  // Nothing is clipped sideways.
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1)).toBe(true);

  // ---- the document against the job the page received --------------------------------------------------------
  const result = job.result;
  await expect(doc.getByTestId("print-simulation-label")).toContainText(SIMULATION_LABEL);
  await expect(doc.getByTestId("print-not-advice")).toContainText("not personalized financial advice");
  await expect(doc.getByTestId("print-test-data")).toHaveCount(0);
  await expect(doc.getByTestId("print-investigation-id")).toHaveText(job.id);
  await expect(doc.getByTestId("print-policy")).toContainText(`Version ${result.policy_version}`);
  await expect(doc.getByTestId("print-verdict")).toHaveAttribute("data-headline", result.summary.headline);
  await expect(doc.getByTestId("print-counts")).toContainText(
    `Pass: ${result.summary.counts.pass}. Fail: ${result.summary.counts.fail}. Unknown: ${result.summary.counts.unknown}.`,
  );
  const rules = doc.getByTestId("print-rule");
  await expect(rules).toHaveCount(result.rule_results.length);
  for (let index = 0; index < result.rule_results.length; index += 1) {
    await expect(rules.nth(index)).toHaveAttribute("data-status", result.rule_results[index].status);
    await expect(rules.nth(index)).toContainText(result.rule_results[index].reason);
  }
  await expect(doc.getByTestId("print-coverage-row")).toHaveCount(result.data_coverage.length);
  await expect(doc.getByTestId("print-portfolio-row")).toHaveCount(job.portfolio.positions.length + 1);
  for (const disclosure of result.disclosures) await expect(doc.getByTestId("print-disclosures")).toContainText(disclosure);
  const sourceIds = new Set<string>([...result.evidence.flatMap((record: any) => record.source_ids), ...result.data_coverage.flatMap((fund: any) => (fund.source_id ? [fund.source_id] : []))]);
  await expect(doc.getByTestId("print-source")).toHaveCount(sourceIds.size);
  for (const sourceId of sourceIds) await expect(doc.getByTestId("print-sources")).toContainText(sourceId);

  fs.mkdirSync(PDF_DIR, { recursive: true });
  const file = path.join(PDF_DIR, `${name}-${format.toLowerCase()}.pdf`);
  await page.pdf({ path: file, format, preferCSSPageSize: false });
  expect(fs.statSync(file).size).toBeGreaterThan(10_000);
  // Producing the PDF is a print: the browser fires `afterprint` when it is done and the document is removed.
  await expect(doc).toHaveCount(0);
  // The caller reads more of the document: it is prepared again the way the browser's own Print command does.
  await page.evaluate(() => window.dispatchEvent(new Event("beforeprint")));
  await expect(doc).toBeVisible();
  return { doc, file };
}

/** Printing is over: the document is gone and the page is the interactive report again. */
async function backToScreen(page: Page) {
  await page.emulateMedia({ media: "screen" });
  await page.evaluate(() => window.dispatchEvent(new Event("afterprint")));
  await expect(page.getByTestId("print-report")).toHaveCount(0);
  await expect(page.getByTestId("report")).toBeVisible();
  expect(await page.title()).not.toContain("inv-");
}

test.describe("Print / Save as PDF of a finished report, live against the local backend", () => {
  test.beforeEach(async () => {
    await resetBackend();
  });

  test("Robert: scenario rules, NVDA to 25% -> the report prints as a document; the interactive journey goes on afterwards", async ({ page }) => {
    test.setTimeout(240_000);
    const traffic = new Traffic(page);
    await openApp(page);
    await choosePersona(page, "Robert");
    await goToGoals(page);
    await confirmOfferedRules(page);
    await goToPurchase(page);
    await setPurchase(page, "NVDA", "25");
    await startAndOpenVerdict(page);
    const job = await finishedJob(traffic);
    expect(job.result.summary.headline).toBe("HAS_FAIL");

    const { doc } = await exportReport(page, job, "robert-default");
    await expect(doc.getByTestId("print-persona")).toContainText("Robert");
    await expect(doc.getByTestId("print-portfolio-label")).toHaveAttribute("data-customized", "false");
    await expect(doc.getByTestId("print-portfolio-label")).toContainText("original fictional portfolio");
    await expect(doc.getByTestId("print-valuation-date")).toHaveText("12 Nov 2026");
    await expect(doc.getByTestId("print-headline")).toContainText("not respected");
    await exportPdfAgain(page, "robert-default", "A4");
    await backToScreen(page);

    // The browser's own Print command (Ctrl/Cmd+P) prepares the same document.
    await page.evaluate(() => window.dispatchEvent(new Event("beforeprint")));
    await expect(page.getByTestId("print-report")).toHaveCount(1);
    await page.evaluate(() => window.dispatchEvent(new Event("afterprint")));
    await expect(page.getByTestId("print-report")).toHaveCount(0);

    // The interactive journey is as before: evidence opens, and the report leads on to the review screen.
    await page.getByTestId("report").getByTestId("rule-result").first().getByRole("button", { name: /evidence/i }).first().click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await page.getByTestId("result-actions").getByRole("link", { name: "Review or dispute this result" }).click();
    await expect(page.getByRole("heading", { level: 1 })).toContainText(/Review/);
  });

  test("a customized portfolio: the document names it as customized and prints the stored weights", async ({ page }) => {
    test.setTimeout(240_000);
    const traffic = new Traffic(page);
    await openApp(page);
    await choosePersona(page, "Robert");
    // Typed into the editor: two positions removed, one added, new weights and cash (total 100).
    const typed: [string, string][] = [["XBB.TO", "10"], ["SPY", "45"], ["JNJ", "5"], ["GOOGL", "2.5"]];
    await page.getByTestId("customize-open").click();
    await page.getByTestId("customize-remove-XIU.TO").click();
    await page.getByTestId("customize-remove-RY.TO").click();
    await page.getByTestId("customize-add-select").selectOption("GOOGL");
    await page.getByTestId("customize-add").click();
    for (const [id, text] of typed) await page.getByTestId(`customize-weight-${id}`).fill(text);
    await page.getByTestId("customize-cash").fill("37.5");
    await expect(page.getByTestId("customize-total")).toHaveAttribute("data-total-valid", "true");
    await page.getByTestId("customize-apply").click({ force: true });
    await expect(page.getByTestId("customized-badge").first()).toBeVisible();

    await goToGoals(page);
    await confirmOfferedRules(page);
    await goToPurchase(page);
    await setPurchase(page, "NVDA", "25");
    await startAndOpenVerdict(page);
    const job = await finishedJob(traffic);
    expect(job.portfolio.portfolio_id).toContain("custom");

    const { doc } = await exportReport(page, job, "robert-customized");
    const label = doc.getByTestId("print-portfolio-label");
    await expect(label).toHaveAttribute("data-customized", "true");
    await expect(label).toContainText("Customized fictional portfolio");
    await expect(label).toContainText(job.portfolio.portfolio_id);
    const rows = doc.getByTestId("print-portfolio-row");
    for (const [id, text] of typed) await expect(rows.filter({ hasText: `(${id})` })).toContainText(`${Number(text).toFixed(1)}%`);
    await expect(rows.last()).toContainText("37.5%");
    await expect(rows.filter({ hasText: "(XIU.TO)" })).toHaveCount(0);
    await backToScreen(page);
  });

  test("Mateo: limits inside the possible range -> UNKNOWN stays UNKNOWN in the document, with its limitations under the verdict", async ({ page }) => {
    test.setTimeout(240_000);
    const traffic = new Traffic(page);
    await openApp(page);
    await choosePersona(page, "Mateo");
    await goToGoals(page);
    const cards = page.getByTestId("rule-card");
    await cards.nth(0).getByRole("textbox").fill("10");
    await cards.nth(1).getByRole("textbox").fill("5");
    await expect(cards.nth(0).getByTestId("draft-preview-result")).toContainText("Preview:");
    await confirmOfferedRules(page);
    await goToPurchase(page);
    await setPurchase(page, "SPY", "15");
    await startAndOpenVerdict(page);
    const job = await finishedJob(traffic);
    expect(job.result.rule_results.map((rule: any) => rule.status)).toEqual(["UNKNOWN", "UNKNOWN"]);

    const { doc } = await exportReport(page, job, "mateo-unknown");
    await expect(doc.getByTestId("print-persona")).toContainText("Mateo");
    await expect(doc.getByTestId("print-headline")).toContainText("Not determined");
    await expect(doc.getByTestId("print-verdict")).toContainText("this is not a pass");
    await expect(doc.getByTestId("print-unknown-note")).toHaveCount(2);
    await expect(doc.getByTestId("print-unknown-causes")).toHaveCount(2);
    const limitations = doc.getByTestId("print-limitations");
    await expect(limitations).toContainText("UNKNOWN");
    await expect(limitations).toContainText("never counted as a pass");
    for (const fund of job.result.data_coverage.filter((candidate: any) => candidate.status !== "COVERED")) await expect(limitations).toContainText(fund.fund_id);
    if (job.result.max_compliant?.status === "WITHHELD") await expect(doc.getByTestId("print-max-withheld")).toContainText("No maximum is shown.");
    // The limitations are the block straight after the verdict.
    const order = await doc.evaluate((element) => [...element.children].map((child) => child.getAttribute("data-testid")));
    expect(order.indexOf("print-limitations")).toBe(order.indexOf("print-verdict") + 1);
    await backToScreen(page);
  });
});

/** A second paper size of the same document, while print media is still emulated. */
async function exportPdfAgain(page: Page, name: string, format: "Letter" | "A4") {
  const file = path.join(PDF_DIR, `${name}-${format.toLowerCase()}.pdf`);
  await page.pdf({ path: file, format, preferCSSPageSize: false });
  expect(fs.statSync(file).size).toBeGreaterThan(10_000);
}
