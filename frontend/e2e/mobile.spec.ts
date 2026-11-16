import { expect, test, type Page } from "@playwright/test";
import {
  expectNoAxeViolations,
  expectNoHorizontalOverflow,
  expectPersistentLabels,
  expectPortfolioLoaded,
  expectScreen,
  expectTestDataMarkers,
  openEverySection,
  overviewChart,
  panelSummary,
  START_URL,
  stepLink,
} from "./helpers";

/** Screen 1: the portfolio table is in a closed panel; a tap opens it. */
async function tapPortfolioOpen(page: Page) {
  await expect(page.getByTestId("portfolio-table")).toBeHidden();
  await panelSummary(page, "View the fictional portfolio").tap();
  await expect(page.getByTestId("portfolio-table")).toBeVisible();
}

/** From screen 1 to "Your limits" with taps: "Set your limits" is the next step. */
async function tapToLimits(page: Page) {
  await page.getByTestId("continue-link").tap();
  await expectScreen(page, "goals");
}

/** From "Your limits" to "Test an idea", with its preview panel opened by a tap. */
async function tapToPurchaseWithPreview(page: Page) {
  await page.getByTestId("continue-link").tap();
  await expectScreen(page, "purchase");
  await panelSummary(page, "Preview cash and exposures").tap();
  await expect(page.getByTestId("purchase-preview")).toBeVisible();
}

/** "Check my idea" leads to the result screen, which shows the report once the investigation has finished. */
async function tapCheckAndWaitForReport(page: Page) {
  await page.getByTestId("start-investigation").tap();
  await expectScreen(page, "verdict");
  await expect(page.getByTestId("report")).toBeVisible({ timeout: 30_000 });
}

/** Runs in the mobile project only: 390 x 844, touch. Every action is a tap. */
test.describe("mobile viewport", () => {
  test("390 x 844: every screen fits the width, keeps its labels and passes axe", async ({ page }) => {
    test.setTimeout(120_000);
    expect(page.viewportSize()).toEqual({ width: 390, height: 844 });
    await page.goto(START_URL);
    await expectPortfolioLoaded(page);
    await expectScreen(page, "persona", { focused: false });
    await expectPersistentLabels(page);
    await expectNoHorizontalOverflow(page, "step 1, portfolio panel closed");
    await tapPortfolioOpen(page);
    await expectNoHorizontalOverflow(page, "step 1, portfolio panel open");
    await expectTestDataMarkers(page, "mobile, step 1");
    await expectNoAxeViolations(page, "mobile, step 1");

    await stepLink(page, 3).tap();
    await expectScreen(page, "purchase");
    await expect(page.getByRole("main").getByText("First, confirm your limits")).toBeVisible();
    await expectNoHorizontalOverflow(page, "step 2, test an idea, no confirmed limit yet");
    await page.getByRole("link", { name: "Set my limits" }).tap();
    await expectScreen(page, "goals");
    await expect(page.getByTestId("rule-card")).toHaveCount(2);
    await expectNoHorizontalOverflow(page, "step 2, proposed limits");
    await expectNoAxeViolations(page, "mobile, step 2, your limits");
    await page.getByTestId("confirm-rules").tap();
    await expect(page.getByTestId("policy-rule-card")).toHaveCount(2);
    await expectNoHorizontalOverflow(page, "step 2, confirmed limits");

    await tapToPurchaseWithPreview(page);
    await expectPersistentLabels(page);
    await expect(page.getByTestId("purchase-preview").getByTestId("cash-after")).toHaveText("5.0%");
    await expect(page.getByTestId("purchase-preview").getByTestId("cash-after")).toBeVisible();
    await expectNoHorizontalOverflow(page, "step 2, test an idea with its preview open");
    await expectNoAxeViolations(page, "mobile, step 2, test an idea");

    // The result screen waits for the investigation; while it runs it links to the steps.
    await page.getByTestId("start-investigation").tap();
    await expectScreen(page, "verdict");
    await page.getByRole("link", { name: "See the investigation steps" }).tap();
    await expectScreen(page, "investigation");
    await expect(page.getByTestId("see-verdict")).toBeVisible({ timeout: 30_000 });
    await expectNoHorizontalOverflow(page, "step 3, analysis details");
    await expectNoAxeViolations(page, "mobile, step 3, analysis details");

    await page.getByTestId("see-verdict").tap();
    await expectScreen(page, "verdict");
    await expect(page.getByTestId("report")).toBeVisible();
    await expectPersistentLabels(page);
    await expect(page.getByTestId("verdict-summary").getByTestId("test-data-tag")).toBeVisible();
    await expectTestDataMarkers(page, "mobile, step 3, your result");
    await expectNoHorizontalOverflow(page, "step 3, your result");
    await expectNoAxeViolations(page, "mobile, step 3, your result");

    // The exposures are a closed panel that a tap opens.
    await expect(overviewChart(page)).toBeHidden();
    await panelSummary(page, "Explore my exposures").tap();
    // On a phone the limit label is a line of its own above the bars: the track is narrower than the label.
    await expect(overviewChart(page).getByTestId("limit-label")).toHaveText("Confirmed limit 10.0%");
    await expect(overviewChart(page).getByTestId("limit-label")).toBeVisible();
    await expectNoHorizontalOverflow(page, "step 3, exposures open");

    // The explorer of one company: a phone is too narrow for the 3D drawing, so it shows the flat chart of that company
    // and says why. The 3D code is not even fetched.
    const explorer = page.getByTestId("exposure-explorer");
    await expect(explorer).toHaveAttribute("data-mode", "FALLBACK");
    await expect(explorer).toHaveAttribute("data-fallback-reason", "NARROW_VIEWPORT");
    await expect(explorer.getByTestId("explorer-fallback")).toContainText("On a narrow screen the flat chart and the table are shown instead of the 3D view.");
    await expect(explorer.getByTestId("explorer-fallback").getByTestId("exposure-row")).toHaveCount(1);
    await expect(explorer.locator("canvas")).toHaveCount(0);
    await expect(explorer.getByTestId("explorer-origin")).toContainText("Test data");
    expect(await page.evaluate(() => "__THREE__" in window)).toBe(false);

    // Exposure chart: the details of a bar open with a tap; there is nothing to hover on a touch screen.
    const other = overviewChart(page).locator('[data-testid="exposure-row"]:not([data-issuer-id="NVIDIA"])').first();
    await expect(other.getByTestId("exposure-breakdown")).toBeHidden();
    await other.locator("summary").tap();
    await expect(other.getByTestId("exposure-breakdown")).toBeVisible();
    await expect(overviewChart(page).locator('[data-testid="exposure-row"][data-issuer-id="NVIDIA"]').getByTestId("exposure-breakdown")).toBeVisible();
    await expectNoHorizontalOverflow(page, "step 3, exposure breakdowns open");
    await other.locator("summary").tap();
    await expect(other.getByTestId("exposure-breakdown")).toBeHidden();

    // The closed sections open with a tap, and a section link from the headline card opens its section and the one around it.
    await expect(page.getByTestId("fund-coverage").first()).toBeHidden();
    await page.getByRole("navigation", { name: "Sections of this report" }).getByRole("link", { name: "Sources and missing data" }).tap();
    await expect(page.locator("#report-details")).toHaveJSProperty("open", true);
    await expect(page.locator("#report-coverage")).toHaveJSProperty("open", true);
    await expect(page.getByTestId("fund-coverage").first()).toBeVisible();
    await page.locator("#report-sentences > summary").tap();
    await expect(page.locator("#report-sentences")).toHaveJSProperty("open", true);
    await expect(page.getByTestId("explanation-statement").first()).toBeVisible();
    await page.locator("#report-about > summary").tap();
    await expect(page.getByTestId("disclosures")).toBeVisible();
    for (const title of ["The purchase and the cash that funds it", "Historical replay", "Largest purchase that respects every confirmed rule", "Context for the objectives"]) {
      await panelSummary(page, title).tap();
    }
    await expect(page.locator("#report-cash").getByTestId("feasibility-table")).toBeVisible();
    await expect(page.getByTestId("max-compliant")).toBeVisible();
    await expect(page.locator('main details[id^="report-"]:not([open])'), "every section of the report is open").toHaveCount(0);
    await expect(page).toHaveURL(/#\/verdict$/);
    await expectTestDataMarkers(page, "mobile, step 3, every section open");
    await expectNoHorizontalOverflow(page, "step 3, every section open");
    await expectNoAxeViolations(page, "mobile, step 3, your result with every section open");

    // The drawer fills the width and nothing spills out of it.
    await page.getByRole("button", { name: "Evidence for Maximum exposure to a single company, after the purchase" }).tap();
    await expect(page.getByRole("dialog")).toBeVisible();
    await expect(page.getByRole("dialog").getByTestId("evidence-formula").first()).toBeVisible();
    await expectNoHorizontalOverflow(page, "step 3, evidence drawer");
    await page.getByRole("button", { name: "Close evidence" }).tap();
    await expect(page.getByRole("dialog")).toBeHidden();

    await page.getByRole("link", { name: "Review or dispute this result" }).tap();
    await expectScreen(page, "challenge");
    await expect(page.getByTestId("change-rule-form")).toBeVisible();
    await expectNoHorizontalOverflow(page, "step 3, review, change a rule");
    await page.getByRole("tab", { name: "Correct a fact" }).tap();
    await expect(page.getByTestId("correct-fact-form")).toBeVisible();
    await expectNoHorizontalOverflow(page, "step 3, review, correct a fact");
    await page.getByRole("tab", { name: "Change a rule" }).tap();
    await page.getByTestId("fill-example-rule").tap();
    await expect(page.getByTestId("change-rule-form").getByRole("textbox", { name: /^New value/ })).toHaveValue("30");
    await page.getByTestId("submit-rule-change").tap();
    await expect(page.getByTestId("result-comparison")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId("comparison-section")).toContainText("Outcome of the rule change: separate from the form above");
    await expectPersistentLabels(page);
    await expectTestDataMarkers(page, "mobile, step 3, review");
    await expectNoHorizontalOverflow(page, "step 3, review, comparison");
    await expectNoAxeViolations(page, "mobile, step 3, review");
  });

  test("360 px wide: the narrowest supported width still has no sideways scroll", async ({ page }) => {
    await page.setViewportSize({ width: 360, height: 740 });
    await page.goto(START_URL);
    await expectPortfolioLoaded(page);
    await expectNoHorizontalOverflow(page, "360px, step 1");
    await tapPortfolioOpen(page);
    await openEverySection(page);
    await expectNoHorizontalOverflow(page, "360px, step 1, everything open");

    await tapToLimits(page);
    await expect(page.getByTestId("rule-card")).toHaveCount(2);
    await expectNoHorizontalOverflow(page, "360px, step 2, your limits");
    await openEverySection(page);
    await expectNoHorizontalOverflow(page, "360px, step 2, your limits, everything open");
    await page.getByTestId("confirm-rules").tap();
    await expect(page.getByTestId("policy-rule-card")).toHaveCount(2);
    await tapToPurchaseWithPreview(page);
    await expect(page.getByTestId("purchase-preview").getByTestId("cash-after")).toBeVisible();
    await openEverySection(page);
    await expectNoHorizontalOverflow(page, "360px, step 2, test an idea, everything open");
    await tapCheckAndWaitForReport(page);
    await expectNoHorizontalOverflow(page, "360px, step 3, your result");
    // Every breakdown table and every closed section, the nested ones included, open at once.
    await openEverySection(page);
    await expect(overviewChart(page)).toBeVisible();
    await expectNoHorizontalOverflow(page, "360px, step 3, your result, everything open");
    // The returns of the replay are stacked on a phone and are still a table to a screen reader: caption, header row, one row per instrument.
    const returns = page.getByRole("table", { name: /^Return of each instrument over the replayed period/ });
    await expect(returns).toBeVisible();
    await expect(returns.getByRole("row")).toHaveCount(7);
    await expect(returns.getByRole("columnheader")).toHaveCount(3);
    await expect(returns.getByRole("rowheader")).toHaveCount(6);
    await expect(returns.getByRole("row").nth(2)).toContainText("Exchange rates: 31 Dec 2021 (same day) and 30 Dec 2022 (same day)");
    await expectNoAxeViolations(page, "360px, step 3, your result, everything open");
    await page.getByRole("link", { name: "Review or dispute this result" }).tap();
    await expectScreen(page, "challenge");
    await expectNoHorizontalOverflow(page, "360px, step 3, review");
  });

  test("Amira at 390 px: the third card, her portfolio and her clarification fit the width and pass axe", async ({ page }) => {
    await page.goto(START_URL);
    await expectPortfolioLoaded(page);
    await expect(page.locator('[data-testid^="persona-"]').filter({ has: page.locator("h3") })).toHaveCount(3);
    await page.getByRole("button", { name: "Use Amira’s portfolio" }).tap();
    await expectPortfolioLoaded(page, "Amira");
    await tapPortfolioOpen(page);
    await expectNoHorizontalOverflow(page, "Amira, step 1");
    await expectNoAxeViolations(page, "Amira, mobile, step 1");
    await page.screenshot({ path: "test-results/screens/amira-mobile-stage1.png", fullPage: true });
    await tapToLimits(page);
    await expect(page.getByTestId("rule-card")).toHaveCount(1);
    await panelSummary(page, "Add a limit in your own words").tap();
    await page.getByTestId("use-scenario-sentence").tap();
    await page.getByTestId("interpret-words").tap();
    await expect(page.getByTestId("interpretation").getByTestId("clarification-card")).toBeVisible();
    await expectNoHorizontalOverflow(page, "Amira, step 2, clarification");
    await expectNoAxeViolations(page, "Amira, mobile, step 2");
    await page.screenshot({ path: "test-results/screens/amira-mobile-clarification.png", fullPage: true });
  });

  test("Mateo at 390 px: findings before the purchase and the wide possible range fit the width", async ({ page }) => {
    await page.goto(START_URL);
    await expectPortfolioLoaded(page);
    await page.getByRole("button", { name: "Use Mateo’s portfolio" }).tap();
    await expectPortfolioLoaded(page, "Mateo");
    await tapToLimits(page);
    await page.getByTestId("confirm-rules").tap();
    await expect(page.getByTestId("policy-rule-card")).toHaveCount(2);
    await page.getByTestId("continue-link").tap();
    await expectScreen(page, "purchase");
    await tapCheckAndWaitForReport(page);
    await expect(page.getByTestId("starting-finding")).toHaveCount(2);
    await openEverySection(page);
    await expect(page.locator('[data-testid="report"] [data-seg="possible"]').first()).toBeVisible();
    await expectNoHorizontalOverflow(page, "Mateo, step 3, everything open");
    await expectTestDataMarkers(page, "Mateo, mobile, step 3");
    await expectNoAxeViolations(page, "Mateo, mobile, step 3");
  });

  test("the simulation notice stays on screen while the page is scrolled", async ({ page }) => {
    await page.goto(START_URL);
    await expectPortfolioLoaded(page);
    // Make the page long enough to scroll, then go to its end.
    await tapPortfolioOpen(page);
    await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
    expect(await page.evaluate(() => window.scrollY), "the page was scrolled").toBeGreaterThan(100);
    const notice = page.getByRole("region", { name: "Simulation notice" });
    await expect(notice).toBeInViewport();
    await expect(page.getByTestId("simulation-label")).toBeInViewport();
    await expect(page.getByTestId("fixtures-label")).toBeInViewport();
    // The valuation date is part of the same notice, as text for assistive technology only: it is visually hidden,
    // so what is checked is that the notice that stays on screen carries it.
    await expect(notice.getByTestId("valuation-date")).toHaveText("Valuation date: 12 Nov 2026");
  });
});
