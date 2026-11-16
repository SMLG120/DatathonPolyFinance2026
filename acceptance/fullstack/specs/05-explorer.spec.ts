import { expect, test, type Locator, type Page } from "@playwright/test";
import { formatFractionRange } from "../../../frontend/src/lib/format";
import { confirmOfferedRules, expectNoTestDataMarkers, goToGoals, goToPurchase, openApp, openPreview, percentTokens, resetBackend, shot, startAndOpenVerdict, Traffic } from "./helpers";

/**
 * The exposure explorer of the result screen in live mode: its drawing arrives in its own script, its table holds
 * the API's values, and the flat chart takes its place on a phone-width viewport and without WebGL.
 *
 * On the current interface the explorer sits in two panels that are closed by default: "Preview cash and exposures"
 * (step 2) and "Explore my exposures" (the report). Each case opens the panel the way a reader does.
 */

/** three.js announces itself on `window` when its code runs, and that name is in its source. */
const THREE_MARKER = "__THREE__";
const threeHasRun = (page: Page) => page.evaluate((marker) => marker in window, THREE_MARKER);

function recordScripts(page: Page): string[] {
  const urls: string[] = [];
  page.on("request", (request) => {
    if (request.resourceType() === "script") urls.push(request.url());
  });
  return urls;
}

async function scriptsHoldingThree(page: Page, urls: string[]): Promise<string[]> {
  const holding: string[] = [];
  for (const url of [...new Set(urls)]) {
    const response = await page.request.get(url);
    if (response.ok() && (await response.text()).includes(THREE_MARKER)) holding.push(url);
  }
  return holding;
}

const browserHasWebGL = (page: Page) =>
  page.evaluate(() => {
    const canvas = document.createElement("canvas");
    return Boolean(canvas.getContext("webgl2") ?? canvas.getContext("webgl"));
  });

/** The one percentage printed in a cell is the API fraction, rounded to the printed precision (nearest or down). */
async function expectCell(cell: Locator, fraction: number, what: string) {
  const text = (await cell.innerText()).trim();
  const tokens = percentTokens(text);
  expect(tokens.length, `${what}: "${text}" holds one percentage`).toBe(1);
  const unit = 10 ** -tokens[0].decimals;
  expect(Math.abs(fraction * 100 - tokens[0].value), `${what}: "${text}" for the API value ${fraction}`).toBeLessThan(unit - 1e-9);
}

/** Every cell of the explorer's HTML table against `result.exposure` for the company the explorer shows. */
async function expectExplorerTable(page: Page, result: any, issuerId: string) {
  const issuer = result.exposure.issuers.find((row: any) => row.issuer_id === issuerId);
  expect(issuer, `the API result holds an exposure row for ${issuerId}`).toBeTruthy();
  const table = page.getByTestId("exposure-explorer").getByTestId("explorer-table");
  await expect(table).toBeVisible();
  const cap = result.rule_results.find((rule: any) => rule.rule_type === "max_issuer_exposure");
  for (const [state, column] of [
    ["starting", "starting"],
    ["proposed", "proposed"],
  ] as const) {
    const cell = (row: string) => table.locator(`tr[data-row="${row}"] td[data-state="${column}"]`);
    await expectCell(cell("direct"), issuer[state].direct, `held directly, ${state}`);
    for (const part of issuer[state].indirect_by_fund) await expectCell(cell(`fund:${part.fund_id}`), part.known, `through ${part.fund_id}, ${state}`);
    await expectCell(cell("known"), issuer[state].lower, `proven total, ${state}`);
    await expectCell(cell("upper"), issuer[state].upper, `possible total, ${state}`);
    if (result.exposure.possible_extra[state] > 0) {
      await expect(cell("unresolved")).toContainText("up to");
      await expectCell(cell("unresolved"), result.exposure.possible_extra[state], `not attributed, ${state}`);
    }
    if (cap) await expectCell(cell("limit"), cap.limit, `limit, ${state}`);
  }
  return issuer;
}

/** "Check my idea", then the report's own link "Explore my exposures", which opens that closed section. */
async function toVerdict(page: Page, traffic: Traffic) {
  await startAndOpenVerdict(page);
  const section = page.locator("#report-exposure");
  await expect(section, "the exposure section of the report is closed until asked for").not.toHaveAttribute("open", "");
  await page.getByTestId("summary-links").getByRole("link", { name: "Explore my exposures" }).click();
  await expect(section).toHaveAttribute("open", "");
  await expect(section.getByTestId("exposure-explorer")).toBeVisible();
  return (await traffic.last("GET", /^\/investigations\/inv-[0-9a-f]+$/, (call) => call.body?.status === "SUCCEEDED")).body;
}

test.describe("exposure explorer, live against the local backend", () => {
  test.beforeEach(async () => {
    await resetBackend();
  });

  test("the 3D drawing loads lazily; on the verdict screen its table holds the API's values", async ({ page }) => {
    const scripts = recordScripts(page);
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    const traffic = new Traffic(page);
    await openApp(page);
    test.skip(!(await browserHasWebGL(page)), "This browser cannot create a WebGL context, so the 3D drawing cannot be exercised here.");
    await goToGoals(page);
    await confirmOfferedRules(page);
    const before = [...scripts];
    expect(await scriptsHoldingThree(page, before), "three.js is not downloaded on stages 1 and 2").toEqual([]);
    expect(await threeHasRun(page)).toBe(false);

    await goToPurchase(page);
    await openPreview(page);
    const explorer = page.getByTestId("exposure-explorer");
    await expect(explorer).toHaveAttribute("data-mode", "3D");
    await expect(explorer.getByTestId("explorer-scene").locator("canvas")).toBeVisible();
    expect(await threeHasRun(page)).toBe(true);
    const added = scripts.filter((url) => !before.includes(url));
    expect((await scriptsHoldingThree(page, added)).length, "the drawing arrived in a script of its own").toBeGreaterThan(0);

    const job = await toVerdict(page, traffic);
    const portfolio = (await traffic.last("GET", /^\/portfolios\/robert$/)).body;
    const issuerId = portfolio.instruments[job.resolved_request.instrument_id].issuer_id;
    await expect(explorer).toHaveAttribute("data-status", "READY");
    await expect(explorer).toHaveAttribute("data-mode", "3D");
    await expect(explorer.getByTestId("explorer-scene").locator("canvas")).toBeVisible();
    await expect(explorer.getByTestId("explorer-context")).toContainText(`Confirmed policy version ${job.result.policy_version}`);
    await expect(explorer.getByTestId("explorer-context")).toContainText(job.result.calculation_version);
    await expectExplorerTable(page, job.result, issuerId);
    await expectNoTestDataMarkers(page, "verdict with the explorer");
    expect(errors).toEqual([]);
    await traffic.expectClean();
    await explorer.scrollIntoViewIfNeeded();
    await shot(page, "18-explorer-3d-on-verdict-live-local-backend-real-data", { locator: explorer });
  });

  test("at 390 px the flat chart stands in for the drawing, with the API's values, and three.js is never fetched", async ({ browser }) => {
    const context = await browser.newContext({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true, baseURL: test.info().project.use.baseURL });
    const page = await context.newPage();
    const scripts = recordScripts(page);
    const traffic = new Traffic(page);
    await openApp(page);
    await goToGoals(page);
    await confirmOfferedRules(page);
    await goToPurchase(page);
    await expect((await openPreview(page)).getByTestId("cash-after")).toBeVisible();
    const job = await toVerdict(page, traffic);
    const portfolio = (await traffic.last("GET", /^\/portfolios\/robert$/)).body;
    const issuerId = portfolio.instruments[job.resolved_request.instrument_id].issuer_id;
    const explorer = page.getByTestId("exposure-explorer");
    await expect(explorer).toHaveAttribute("data-mode", "FALLBACK");
    await expect(explorer.locator("canvas")).toHaveCount(0);
    const fallback = explorer.getByTestId("explorer-fallback");
    await expect(fallback.getByTestId("exposure-row")).toHaveCount(1);
    const issuer = await expectExplorerTable(page, job.result, issuerId);
    await expect(fallback.getByTestId("exposure-after")).toHaveText(`After ${formatFractionRange(issuer.proposed.lower, issuer.proposed.upper)}`);
    await expect(fallback.getByTestId("exposure-before")).toHaveText(`Before ${formatFractionRange(issuer.starting.lower, issuer.starting.upper)}`);
    expect(await threeHasRun(page)).toBe(false);
    expect(await scriptsHoldingThree(page, scripts)).toEqual([]);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow, "the page does not scroll sideways at 390 px").toBeLessThanOrEqual(0);
    await explorer.scrollIntoViewIfNeeded();
    await shot(page, "19-explorer-flat-fallback-390px-live-local-backend-real-data", { locator: explorer });
    await context.close();
  });

  test("without WebGL the flat chart stands in for the drawing, with the API's values and no page error", async ({ page }) => {
    const scripts = recordScripts(page);
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.addInitScript(() => {
      const original = HTMLCanvasElement.prototype.getContext;
      HTMLCanvasElement.prototype.getContext = function (this: HTMLCanvasElement, contextId: string, ...rest: unknown[]) {
        if (contextId === "webgl" || contextId === "webgl2" || contextId === "experimental-webgl") return null;
        return (original as (...args: unknown[]) => unknown).call(this, contextId, ...rest);
      } as typeof HTMLCanvasElement.prototype.getContext;
    });
    const traffic = new Traffic(page);
    await openApp(page);
    expect(await browserHasWebGL(page)).toBe(false);
    await goToGoals(page);
    await confirmOfferedRules(page);
    await goToPurchase(page);
    await expect((await openPreview(page)).getByTestId("cash-after")).toBeVisible();
    const job = await toVerdict(page, traffic);
    const portfolio = (await traffic.last("GET", /^\/portfolios\/robert$/)).body;
    const explorer = page.getByTestId("exposure-explorer");
    await expect(explorer).toHaveAttribute("data-mode", "FALLBACK");
    await expect(explorer).toHaveAttribute("data-fallback-reason", "NO_WEBGL");
    await expect(explorer.getByTestId("explorer-fallback")).toContainText("The 3D view is not available in this browser");
    await expect(explorer.locator("canvas")).toHaveCount(0);
    const issuer = await expectExplorerTable(page, job.result, portfolio.instruments[job.resolved_request.instrument_id].issuer_id);
    await expect(explorer.getByTestId("explorer-fallback").getByTestId("exposure-after")).toHaveText(`After ${formatFractionRange(issuer.proposed.lower, issuer.proposed.upper)}`);
    expect(await threeHasRun(page)).toBe(false);
    expect(await scriptsHoldingThree(page, scripts)).toEqual([]);
    expect(errors).toEqual([]);
  });
});
