import { expect, test } from "@playwright/test";
import { expectNoAxeViolations, expectNoHorizontalOverflow, expectPersistentLabels, expectStage, expectTestDataMarkers, overviewChart, START_URL } from "./helpers";

/** Runs in the mobile project only: 390 x 844, touch. Every action is a tap. */
test.describe("mobile viewport", () => {
  test("390 x 844: every stage fits the width, keeps its labels and passes axe", async ({ page }) => {
    test.setTimeout(120_000);
    expect(page.viewportSize()).toEqual({ width: 390, height: 844 });
    await page.goto(START_URL);
    await expect(page.getByTestId("portfolio-table")).toBeVisible();
    await expectPersistentLabels(page);
    await expectNoHorizontalOverflow(page, "stage 1");
    await expectNoAxeViolations(page, "mobile, stage 1");

    await page.getByRole("link", { name: "Continue to Goals & rules" }).tap();
    await expectStage(page, 2);
    await expect(page.getByTestId("rule-card")).toHaveCount(2);
    await expectNoHorizontalOverflow(page, "stage 2, proposed rules");
    await expectNoAxeViolations(page, "mobile, stage 2");
    await page.getByTestId("confirm-rules").tap();
    await expect(page.getByTestId("policy-rule-card")).toHaveCount(2);
    await expectNoHorizontalOverflow(page, "stage 2, confirmed policy");

    await page.getByRole("link", { name: "Continue to Proposed purchase" }).tap();
    await expectStage(page, 3);
    await expectPersistentLabels(page);
    await expect(page.getByTestId("purchase-preview").getByTestId("cash-after")).toHaveText("5.0%");
    await expectNoHorizontalOverflow(page, "stage 3");
    await expectNoAxeViolations(page, "mobile, stage 3");

    await page.getByTestId("start-investigation").tap();
    await expectStage(page, 4);
    await expect(page.getByTestId("see-verdict")).toBeVisible({ timeout: 30_000 });
    await expectNoHorizontalOverflow(page, "stage 4");
    await expectNoAxeViolations(page, "mobile, stage 4");

    await page.getByTestId("see-verdict").tap();
    await expectStage(page, 5);
    await expect(page.getByTestId("report")).toBeVisible();
    await expectPersistentLabels(page);
    await expect(page.getByTestId("verdict-summary").getByTestId("test-data-tag")).toBeVisible();
    await expectTestDataMarkers(page, "mobile, stage 5");
    // On a phone the limit label is a line of its own above the bars: the track is narrower than the label.
    await expect(overviewChart(page).getByTestId("limit-label")).toHaveText("Confirmed limit 10.0%");
    await expect(overviewChart(page).getByTestId("limit-label")).toBeVisible();
    await expectNoHorizontalOverflow(page, "stage 5");
    await expectNoAxeViolations(page, "mobile, stage 5");

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
    await expectNoHorizontalOverflow(page, "stage 5, exposure breakdowns open");
    await other.locator("summary").tap();
    await expect(other.getByTestId("exposure-breakdown")).toBeHidden();

    // The closed sections open with a tap, and a section link from the headline card opens its section.
    await page.locator("#report-coverage > summary").tap();
    await expect(page.getByTestId("fund-coverage").first()).toBeVisible();
    await page.getByRole("navigation", { name: "Sections of this report" }).getByRole("link", { name: "In sentences" }).tap();
    await expect(page.locator("#report-sentences")).toHaveJSProperty("open", true);
    await expect(page.getByTestId("explanation-statement").first()).toBeVisible();
    await page.locator("#report-about > summary").tap();
    await expect(page.getByTestId("disclosures")).toBeVisible();
    await expect(page).toHaveURL(/#\/verdict$/);
    await expectNoHorizontalOverflow(page, "stage 5, every section open");
    await expectNoAxeViolations(page, "mobile, stage 5 with every section open");

    // The drawer fills the width and nothing spills out of it.
    await page.getByRole("button", { name: "Evidence for Maximum exposure to a single company, after the purchase" }).tap();
    await expect(page.getByRole("dialog")).toBeVisible();
    await expect(page.getByRole("dialog").getByTestId("evidence-formula").first()).toBeVisible();
    await expectNoHorizontalOverflow(page, "stage 5, evidence drawer");
    await page.getByRole("button", { name: "Close evidence" }).tap();
    await expect(page.getByRole("dialog")).toBeHidden();

    await page.getByRole("link", { name: "Challenge this result" }).tap();
    await expectStage(page, 6);
    await expect(page.getByTestId("change-rule-form")).toBeVisible();
    await expectNoHorizontalOverflow(page, "stage 6, change a rule");
    await page.getByRole("tab", { name: "Correct a fact" }).tap();
    await expect(page.getByTestId("correct-fact-form")).toBeVisible();
    await expectNoHorizontalOverflow(page, "stage 6, correct a fact");
    await page.getByRole("tab", { name: "Change a rule" }).tap();
    await page.getByTestId("fill-example-rule").tap();
    await expect(page.getByTestId("change-rule-form").getByRole("textbox", { name: /^New value/ })).toHaveValue("30");
    await page.getByTestId("submit-rule-change").tap();
    await expect(page.getByTestId("result-comparison")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId("comparison-section")).toContainText("Outcome of the rule change — separate from the form above");
    await expectPersistentLabels(page);
    await expectTestDataMarkers(page, "mobile, stage 6");
    await expectNoHorizontalOverflow(page, "stage 6, comparison");
    await expectNoAxeViolations(page, "mobile, stage 6");
  });

  test("360 px wide: the narrowest supported width still has no sideways scroll", async ({ page }) => {
    await page.setViewportSize({ width: 360, height: 740 });
    await page.goto(START_URL);
    await expect(page.getByTestId("portfolio-table")).toBeVisible();
    await expectNoHorizontalOverflow(page, "360px, stage 1");

    await page.getByRole("link", { name: "Continue to Goals & rules" }).tap();
    await expect(page.getByTestId("rule-card")).toHaveCount(2);
    await expectNoHorizontalOverflow(page, "360px, stage 2");
    await page.getByTestId("confirm-rules").tap();
    await expect(page.getByTestId("policy-rule-card")).toHaveCount(2);
    await page.getByRole("link", { name: "Continue to Proposed purchase" }).tap();
    await expect(page.getByTestId("purchase-preview").getByTestId("cash-after")).toBeVisible();
    await expectNoHorizontalOverflow(page, "360px, stage 3");
    await page.getByTestId("start-investigation").tap();
    await page.getByTestId("see-verdict").tap({ timeout: 30_000 });
    await expect(page.getByTestId("report")).toBeVisible();
    await expectNoHorizontalOverflow(page, "360px, stage 5");
    // Every breakdown table and every closed section, open at once.
    await page.evaluate(() => document.querySelectorAll("main details").forEach((details) => ((details as HTMLDetailsElement).open = true)));
    await expectNoHorizontalOverflow(page, "360px, stage 5, everything open");
    // The returns of the replay are stacked on a phone and are still a table to a screen reader: caption, header row, one row per instrument.
    const returns = page.getByRole("table", { name: /^Return of each instrument over the replayed period/ });
    await expect(returns).toBeVisible();
    await expect(returns.getByRole("row")).toHaveCount(7);
    await expect(returns.getByRole("columnheader")).toHaveCount(3);
    await expect(returns.getByRole("rowheader")).toHaveCount(6);
    await expect(returns.getByRole("row").nth(2)).toContainText("Exchange rates: 31 Dec 2021 (same day) and 30 Dec 2022 (same day)");
    await expectNoAxeViolations(page, "360px, stage 5, everything open");
    await page.getByRole("link", { name: "Challenge this result" }).tap();
    await expectStage(page, 6);
    await expectNoHorizontalOverflow(page, "360px, stage 6");
  });

  test("Amira at 390 px: the third card, her portfolio and her clarification fit the width and pass axe", async ({ page }) => {
    await page.goto(START_URL);
    await expect(page.getByTestId("portfolio-table")).toBeAttached();
    await page.getByRole("button", { name: "Use Amira’s portfolio" }).tap();
    await expect(page.getByTestId("portfolio-table")).toContainText("Amira’s fictional portfolio");
    await page.locator("summary", { hasText: "View the fictional portfolio" }).click();
    await expect(page.getByTestId("portfolio-table")).toBeVisible();
    await expectNoHorizontalOverflow(page, "Amira, stage 1");
    await expectNoAxeViolations(page, "Amira, mobile, stage 1");
    await page.screenshot({ path: "test-results/screens/amira-mobile-stage1.png", fullPage: true });
    await page.evaluate(() => (window.location.hash = "#/goals"));
    await expect(page.getByTestId("rule-card")).toHaveCount(1);
    await page.locator("summary", { hasText: "Add a limit in your own words" }).tap();
    await page.getByTestId("use-scenario-sentence").tap();
    await page.getByTestId("interpret-words").tap();
    await expect(page.getByTestId("interpretation").getByTestId("clarification-card")).toBeVisible();
    await expectNoHorizontalOverflow(page, "Amira, stage 2, clarification");
    await expectNoAxeViolations(page, "Amira, mobile, stage 2");
    await page.screenshot({ path: "test-results/screens/amira-mobile-clarification.png", fullPage: true });
  });

  test("Mateo at 390 px: findings before the purchase and the wide possible range fit the width", async ({ page }) => {
    await page.goto(START_URL);
    await expect(page.getByTestId("portfolio-table")).toBeVisible();
    await page.getByRole("button", { name: "Use Mateo’s portfolio" }).tap();
    await expect(page.getByTestId("portfolio-table")).toContainText("Mateo’s fictional portfolio");
    await page.getByRole("link", { name: "Continue to Goals & rules" }).tap();
    await page.getByTestId("confirm-rules").tap();
    await expect(page.getByTestId("policy-rule-card")).toHaveCount(2);
    await page.getByRole("link", { name: "Continue to Proposed purchase" }).tap();
    await page.getByTestId("start-investigation").tap();
    await page.getByTestId("see-verdict").tap({ timeout: 30_000 });
    await expect(page.getByTestId("report")).toBeVisible();
    await expect(page.getByTestId("starting-finding")).toHaveCount(2);
    await page.evaluate(() => document.querySelectorAll("main details").forEach((details) => ((details as HTMLDetailsElement).open = true)));
    await expectNoHorizontalOverflow(page, "Mateo, stage 5, everything open");
    await expectTestDataMarkers(page, "Mateo, mobile, stage 5");
    await expectNoAxeViolations(page, "Mateo, mobile, stage 5");
  });

  test("the simulation notice stays on screen while the page is scrolled", async ({ page }) => {
    await page.goto(START_URL);
    await expect(page.getByTestId("portfolio-table")).toBeVisible();
    await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
    await expect(page.getByTestId("simulation-label")).toBeInViewport();
    await expect(page.getByTestId("valuation-date")).toBeInViewport();
    await expect(page.getByTestId("fixtures-label")).toBeInViewport();
  });
});
