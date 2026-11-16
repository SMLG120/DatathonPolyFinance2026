import { expect, test, type Page } from "@playwright/test";
import {
  browserHasWebGL,
  checkIdeaAndWaitForReport,
  confirmScenarioRules,
  continueToPurchase,
  expectNoAxeViolations,
  expectPortfolioLoaded,
  mainAlert,
  openExposurePanel,
  openPurchasePreview,
  overviewChart,
  START_URL,
} from "./helpers";

/**
 * The exposure explorer: one company before and after the purchase, as a 3D
 * drawing where the browser can draw it and as the flat chart everywhere else.
 * Desktop project only (a phone always gets the flat chart: see mobile.spec.ts).
 */

/** three.js announces itself on `window` when its code runs, and that name is in its source: both say whether it was loaded. */
const THREE_MARKER = "__THREE__";
const threeHasRun = (page: Page) => page.evaluate((marker) => marker in window, THREE_MARKER);

/** Records every script the page fetches, so a test can say what was downloaded and when. */
function recordScripts(page: Page): { urls: string[] } {
  const record = { urls: [] as string[] };
  page.on("request", (request) => {
    if (request.resourceType() === "script") record.urls.push(request.url());
  });
  return record;
}

/** The scripts (by URL) whose source holds three.js. Fetched again outside the page, so the page's own loading is not disturbed. */
async function scriptsHoldingThree(page: Page, urls: string[]): Promise<string[]> {
  const holding: string[] = [];
  for (const url of [...new Set(urls)]) {
    const response = await page.request.get(url);
    if (response.ok() && (await response.text()).includes(THREE_MARKER)) holding.push(url);
  }
  return holding;
}

/** Errors the page itself reports. A fallback must not be one. */
function recordPageErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  return errors;
}

/** "Test an idea" with its preview panel open: the explorer is under the service's preview, inside that panel. */
async function toPurchaseStage(page: Page) {
  await page.goto(START_URL);
  await expectPortfolioLoaded(page);
  await confirmScenarioRules(page);
  await continueToPurchase(page);
  await openPurchasePreview(page);
  await expect(page.getByTestId("purchase-preview").getByTestId("cash-after")).toHaveText("5.0%");
}

/** "Your result" with the panel "Explore my exposures" open: the chart of every company and the explorer are inside it. */
async function toVerdictStage(page: Page) {
  await checkIdeaAndWaitForReport(page);
  await openExposurePanel(page);
  await expect(page.getByTestId("exposure-explorer")).toBeVisible();
}

/** The flat chart of one company stands where the drawing would be, with the reason in words, and nothing is reported as an error. */
async function expectFlatChart(page: Page, reason: string, sentence: string) {
  const explorer = page.getByTestId("exposure-explorer");
  await expect(explorer).toHaveAttribute("data-mode", "FALLBACK");
  await expect(explorer).toHaveAttribute("data-fallback-reason", reason);
  await expect(explorer.getByTestId("explorer-fallback")).toContainText(sentence);
  await expect(explorer.getByTestId("explorer-fallback").getByTestId("exposure-row")).toHaveCount(1);
  await expect(explorer.getByTestId("explorer-fallback").getByTestId("exposure-after")).toHaveText("After 26.2% to 26.4%");
  await expect(explorer.locator("canvas")).toHaveCount(0);
  await expect(explorer.getByRole("button", { name: "Reset view" })).toHaveCount(0);
  // The values are all still there as text.
  await expect(explorer.getByTestId("explorer-table").locator('tr[data-row="upper"] td[data-state="proposed"]')).toHaveText("26.4%");
  await expect(mainAlert(page)).toHaveCount(0);
}

test.describe("exposure explorer", () => {
  test("three.js is fetched only when the 3D drawing is about to be shown, and then the drawing is really drawn", async ({ page }) => {
    const scripts = recordScripts(page);
    const errors = recordPageErrors(page);

    await page.goto(START_URL);
    await expectPortfolioLoaded(page);
    test.skip(!(await browserHasWebGL(page)), "This browser cannot create a WebGL context, so the 3D drawing cannot be exercised here.");

    // "Choose a profile" and "Your limits": nothing of three.js has been downloaded or run.
    await confirmScenarioRules(page);
    const before = [...scripts.urls];
    expect(before.length).toBeGreaterThan(0);
    expect(await scriptsHoldingThree(page, before)).toEqual([]);
    expect(await threeHasRun(page)).toBe(false);

    // "Test an idea": the explorer is under the preview, in the preview panel; its drawing arrives in scripts of its own.
    await continueToPurchase(page);
    await openPurchasePreview(page);
    await expect(page.getByTestId("purchase-preview").getByTestId("cash-after")).toHaveText("5.0%");
    const explorer = page.getByTestId("exposure-explorer");
    await expect(explorer).toHaveAttribute("data-mode", "3D");
    await expect(explorer.getByTestId("explorer-scene").locator("canvas")).toBeVisible();
    expect(await threeHasRun(page)).toBe(true);
    const after = scripts.urls.filter((url) => !before.includes(url));
    expect(await scriptsHoldingThree(page, after)).toHaveLength(1);

    // The canvas is decoration for assistive technology: hidden from it, and not a tab stop.
    const canvas = explorer.getByTestId("explorer-scene").locator("canvas");
    await expect(canvas).toHaveAttribute("aria-hidden", "true");
    await expect(canvas).toHaveAttribute("tabindex", "-1");
    // The drawing is a network whose labels are painted in the canvas, so the whole scene is hidden from assistive
    // technology. The two states and the limit are words beside it: the columns of the table and the limit line.
    await expect(explorer.getByTestId("explorer-scene")).toHaveAttribute("aria-hidden", "true");
    await expect(explorer.getByTestId("explorer-table").getByRole("columnheader")).toHaveText(["Current", "Proposed"]);
    await expect(explorer.getByTestId("explorer-table").locator('tr[data-row="limit"] td[data-state="proposed"]')).toHaveText("10.0%");
    await expect(explorer.getByTestId("explorer-limit")).toContainText("10.0%");

    // Something was drawn: ask the scene for a frame and read it back in that same frame.
    const frame = await page.evaluate(
      () =>
        new Promise<{ width: number; height: number; colours: number }>((resolve) => {
          document.querySelector<HTMLElement>('[data-testid="explorer-reset-view"]')?.click();
          requestAnimationFrame(() => {
            const drawing = document.querySelector<HTMLCanvasElement>('[data-testid="explorer-scene"] canvas');
            const gl = (drawing?.getContext("webgl2") ?? drawing?.getContext("webgl")) as WebGLRenderingContext | null;
            if (!gl) return resolve({ width: 0, height: 0, colours: 0 });
            const width = gl.drawingBufferWidth;
            const height = gl.drawingBufferHeight;
            const pixels = new Uint8Array(width * height * 4);
            gl.readPixels(0, 0, width, height, gl.RGBA, gl.UNSIGNED_BYTE, pixels);
            const colours = new Set<number>();
            for (let index = 0; index < pixels.length; index += 4 * 13) {
              colours.add((((pixels[index] ?? 0) << 24) | ((pixels[index + 1] ?? 0) << 16) | ((pixels[index + 2] ?? 0) << 8) | (pixels[index + 3] ?? 0)) >>> 0);
            }
            resolve({ width, height, colours: colours.size });
          });
        }),
    );
    expect(frame.width).toBeGreaterThan(100);
    expect(frame.height).toBeGreaterThan(100);
    // Background, floor, two kinds of block, the limit plane and their shading: a blank canvas has one colour.
    expect(frame.colours).toBeGreaterThan(4);

    // The view is turned and reset from the keyboard; the buttons are ordinary buttons.
    const controls = explorer.getByRole("group", { name: "3D view controls" });
    for (const name of ["Rotate left", "Rotate right", "Zoom in", "Zoom out", "Reset view"]) {
      await controls.getByRole("button", { name, exact: true }).focus();
      await page.keyboard.press("Enter");
    }
    await expect(explorer).toHaveAttribute("data-mode", "3D");

    // A part is chosen with its HTML button, and its calculation opens in the evidence drawer.
    await explorer.locator('[data-testid="explorer-segment"][data-segment="proposed:FUND:SPY"]').click();
    await expect(explorer.getByTestId("explorer-details")).toContainText("Through SPY: Proposed portfolio (after the purchase)");
    await explorer.getByTestId("explorer-open-evidence").click();
    await expect(page.getByRole("dialog")).toContainText("Evidence: exposure to NVIDIA through SPY, after the purchase");
    await page.getByRole("button", { name: "Close evidence" }).click();
    await expect(page.getByRole("dialog")).toBeHidden();
    await expect(explorer.getByTestId("explorer-open-evidence")).toBeFocused();
    await expectNoAxeViolations(page, "test an idea, with the 3D explorer and a part selected");

    // "Your result": the chart of every company is still there, and the explorer is beside it.
    await toVerdictStage(page);
    await expect(overviewChart(page).getByTestId("exposure-row")).toHaveCount(10);
    await expect(page.getByTestId("exposure-explorer")).toHaveAttribute("data-mode", "3D");
    await expect(page.getByTestId("exposure-explorer").getByTestId("explorer-scene").locator("canvas")).toBeVisible();
    await expect(page.getByTestId("exposure-explorer").getByTestId("explorer-origin")).toContainText("Test data");
    // Once the drawing is up there is one chart of bars on the page, not two.
    await expect(page.getByTestId("exposure-chart")).toHaveCount(1);
    await expectNoAxeViolations(page, "your result, with the 3D explorer");
    expect(errors).toEqual([]);
  });

  test("without WebGL the flat chart of the same company is shown, with no error, and three.js is never fetched", async ({ page }) => {
    const scripts = recordScripts(page);
    const errors = recordPageErrors(page);
    // A browser that exposes the API but refuses every context.
    await page.addInitScript(() => {
      const original = HTMLCanvasElement.prototype.getContext;
      HTMLCanvasElement.prototype.getContext = function (this: HTMLCanvasElement, contextId: string, ...rest: unknown[]) {
        if (contextId === "webgl" || contextId === "webgl2" || contextId === "experimental-webgl") return null;
        return (original as (...args: unknown[]) => unknown).call(this, contextId, ...rest);
      } as typeof HTMLCanvasElement.prototype.getContext;
    });

    await toPurchaseStage(page);
    expect(await browserHasWebGL(page)).toBe(false);
    await expectFlatChart(page, "NO_WEBGL", "The 3D view is not available in this browser, so the flat chart and the table are shown instead.");
    await expectNoAxeViolations(page, "test an idea, with the explorer's flat chart");

    await toVerdictStage(page);
    await expectFlatChart(page, "NO_WEBGL", "The 3D view is not available in this browser");
    await expect(overviewChart(page).getByTestId("exposure-row")).toHaveCount(10);
    await expectNoAxeViolations(page, "your result, with the explorer's flat chart");

    expect(await threeHasRun(page)).toBe(false);
    expect(await scriptsHoldingThree(page, scripts.urls)).toEqual([]);
    expect(errors).toEqual([]);
  });

  test("with reduced motion requested the flat chart is shown and three.js is never fetched", async ({ page }) => {
    const scripts = recordScripts(page);
    const errors = recordPageErrors(page);
    await page.emulateMedia({ reducedMotion: "reduce" });

    await toPurchaseStage(page);
    await expectFlatChart(page, "REDUCED_MOTION", "Reduced motion is turned on, so the flat chart and the table are shown instead of the 3D view.");
    await toVerdictStage(page);
    await expectFlatChart(page, "REDUCED_MOTION", "Reduced motion is turned on");

    expect(await threeHasRun(page)).toBe(false);
    expect(await scriptsHoldingThree(page, scripts.urls)).toEqual([]);
    expect(errors).toEqual([]);
  });

  test("when the script of the 3D drawing cannot be loaded the flat chart takes its place, with no error on the page", async ({ page }) => {
    await page.goto(START_URL);
    await expectPortfolioLoaded(page);
    test.skip(!(await browserHasWebGL(page)), "This browser cannot create a WebGL context, so the 3D drawing is never requested here.");
    await confirmScenarioRules(page);

    // Everything the page needs up front is loaded. From here on, every further script fails: the only one is the drawing's.
    const refused: string[] = [];
    await page.route("**/*.js", (route) => {
      refused.push(route.request().url());
      return route.abort("failed");
    });

    await continueToPurchase(page);
    await openPurchasePreview(page);
    await expect(page.getByTestId("purchase-preview").getByTestId("cash-after")).toHaveText("5.0%");
    await expectFlatChart(page, "LOAD_OR_RENDER_ERROR", "The 3D view could not be started, so the flat chart and the table are shown instead.");
    expect(refused.length).toBeGreaterThan(0);
    expect(await threeHasRun(page)).toBe(false);

    // The rest of the simulation is unaffected.
    await toVerdictStage(page);
    await expect(page.getByTestId("verdict-headline")).toHaveText("2 of 2 confirmed rules are not respected");
    await expect(overviewChart(page).getByTestId("exposure-row")).toHaveCount(10);
    await expect(page.getByTestId("exposure-explorer")).toHaveAttribute("data-mode", "FALLBACK");
  });
});
