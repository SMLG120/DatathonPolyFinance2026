import { expect, test } from "@playwright/test";
import {
  expectNoAxeViolations,
  expectPersistentLabels,
  expectStage,
  expectTestDataMarkers,
  expectVisibleFocusRing,
  stageHeading,
  START_URL,
  tabBackTo,
  tabTo,
  tabToAndPress,
} from "./helpers";

const ROBERT_HEADLINE = "2 of 2 confirmed rules are not respected";

/**
 * The whole simulation, driven with the keyboard only (Tab, Shift+Tab, Enter,
 * Space, arrows, Escape, typing) on the static build in fixtures mode. No
 * mouse action is used anywhere in this file.
 */
test.describe("keyboard-only journey through the six stages", () => {
  test("Robert: persona to challenge, with axe on every stage", async ({ page }) => {
    // Two investigations are polled at the contract's interval of 1.5 s, and every control is reached with Tab.
    test.setTimeout(180_000);
    await page.goto(START_URL);
    await expect(page.getByTestId("portfolio-table")).toBeVisible();

    // ---- Stage 1: focus order follows the reading order --------------------
    await expectStage(page, 1, { focused: false });
    await expectPersistentLabels(page);
    // Read once the page has settled: the title must still name the stage after hydration.
    await page.waitForLoadState("networkidle");
    expect(await page.title()).toBe("Persona & portfolio — Before You Buy — fictional simulation");
    expect(await page.locator("title").count()).toBe(1);
    const expectedOrder = [
      page.getByRole("link", { name: "Skip to main content" }),
      page.getByRole("link", { name: "Step 1 of 6: Persona & portfolio" }),
      page.getByRole("link", { name: "Step 2 of 6: Goals & rules" }),
      page.getByRole("link", { name: "Step 3 of 6: Proposed purchase" }),
      page.getByRole("link", { name: "Step 4 of 6: Investigation steps" }),
      page.getByRole("link", { name: "Step 5 of 6: Verdict & evidence" }),
      page.getByRole("link", { name: "Step 6 of 6: Challenge" }),
      page.getByRole("button", { name: "Use Mateo’s portfolio" }),
      page.getByTestId("case-facts").locator("summary"),
      page.getByRole("link", { name: "Continue to Goals & rules" }),
    ];
    for (const control of expectedOrder) {
      await page.keyboard.press("Tab");
      await expect(control).toBeFocused();
      await expectVisibleFocusRing(control);
    }
    await expectTestDataMarkers(page, "stage 1");
    await expectNoAxeViolations(page, "stage 1, persona and portfolio");

    // The skip link is the first stop and moves focus to the main region.
    await page.goto(START_URL);
    await expect(page.getByTestId("portfolio-table")).toBeVisible();
    await page.keyboard.press("Tab");
    await expect(page.getByRole("link", { name: "Skip to main content" })).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(page.locator("#main-content")).toBeFocused();
    await expect(page).toHaveURL(/\?fixtures=1$/); // the skip link does not disturb the stage in the hash

    // ---- Stage 2: the scenario's rules as proposals -> explicit confirmation
    await tabToAndPress(page, page.getByRole("link", { name: "Continue to Goals & rules" }));
    await expectStage(page, 2);
    await expectPersistentLabels(page);
    await expect(page).toHaveTitle("Goals & rules — Before You Buy — fictional simulation");
    await expect(page.getByTestId("rule-card")).toHaveCount(2);
    await expect(page.getByTestId("rule-card").first().getByText("Proposed — inactive")).toBeVisible();
    await expect(page.getByText("No confirmed rule yet")).toBeVisible();
    await expectNoAxeViolations(page, "stage 2, proposed rules");

    // A threshold can be changed from the keyboard, and a preview is labelled as a preview.
    const firstCard = page.getByTestId("rule-card").first();
    const field = firstCard.getByRole("textbox");
    const slider = firstCard.getByRole("slider");
    await tabTo(page, slider);
    await expectVisibleFocusRing(slider);
    await page.keyboard.press("ArrowRight");
    await expect(field).toHaveValue("10.5");
    // The test data holds one recorded preview (a draft limit of 20%); any other draft value says so calmly.
    await expect(firstCard.getByTestId("draft-preview-not-recorded")).toContainText("No preview for this draft value in the test data");
    await page.keyboard.press("ArrowLeft");
    await expect(field).toHaveValue("10");

    await page.keyboard.press("Shift+Tab");
    await expect(field).toBeFocused();
    await page.keyboard.press("ControlOrMeta+a");
    await page.keyboard.type("20");
    await expect(firstCard.getByTestId("draft-preview-result")).toContainText("Preview: Fail");
    await expect(firstCard.getByTestId("draft-preview")).toContainText("Preview with draft threshold — not your confirmed policy");
    await expect(firstCard.getByTestId("draft-preview").getByTestId("test-data-tag")).toBeVisible();
    await expectNoAxeViolations(page, "stage 2, a draft preview");
    await page.keyboard.press("ControlOrMeta+a");
    await page.keyboard.type("10");
    await expect(field).toHaveValue("10");

    await tabToAndPress(page, page.getByTestId("confirm-rules"));
    await expect(page.getByTestId("policy-rule-card")).toHaveCount(2);
    // The cards that held focus are gone: focus goes to the policy they became part of.
    await expect(page.getByRole("heading", { name: "Confirmed policy — version 1" })).toBeFocused();
    await expectTestDataMarkers(page, "stage 2, confirmed policy");
    await expectNoAxeViolations(page, "stage 2, confirmed policy");

    // ---- Stage 3: the purchase as a final direct weight --------------------
    await tabToAndPress(page, page.getByRole("link", { name: "Continue to Proposed purchase" }));
    await expectStage(page, 3);
    await expectPersistentLabels(page);
    await expect(page.getByTestId("funding-statement")).toHaveText("Funded from existing cash; all other positions unchanged; fees and taxes excluded.");
    await expect(page.getByLabel("Final direct weight of this position")).toHaveValue("25");
    await expect(page.getByTestId("entered-target")).toHaveText("25.0%");
    await expect(page.getByTestId("figures-after-check")).toContainText("Computed by the service, not by this page");
    // The cash figure is the service's answer to POST /check, labelled as a preview.
    await expect(page.getByTestId("purchase-preview-label")).toHaveText("Preview — computed by the service for the request above");
    await expect(page.getByTestId("purchase-preview").getByTestId("cash-after")).toHaveText("5.0%");
    await expect(page.getByTestId("purchase-preview").getByTestId("additional-purchase")).toHaveText("+25.0 points");
    await expectTestDataMarkers(page, "stage 3");
    await expectNoAxeViolations(page, "stage 3, proposed purchase");

    // ---- Stage 4: only the steps the job reports ---------------------------
    await tabToAndPress(page, page.getByTestId("start-investigation"));
    await expectStage(page, 4);
    await expectPersistentLabels(page);
    // While it runs, the list holds only the steps the job has reported so far, and a plain waiting line.
    await expect(page.getByTestId("timeline-waiting")).toHaveText("Waiting for the next step");
    const stepsSeen: number[] = [];
    await expect(async () => {
      stepsSeen.push(await page.getByTestId("timeline-step").count());
      await expect(page.getByTestId("see-verdict")).toBeVisible({ timeout: 100 });
    }).toPass({ timeout: 30_000, intervals: [100] });
    const totalSteps = await page.getByTestId("timeline-step").count();
    expect(totalSteps).toBe(8);
    expect(stepsSeen[0], "every step was on screen before the job had reported it").toBeLessThan(totalSteps);
    expect(stepsSeen, "a step that had been shown went away").toEqual([...stepsSeen].sort((a, b) => a - b));
    await expect(page.locator('[data-testid="timeline-step"]:not([data-step-status="OK"])')).toHaveCount(0);
    await expect(page.getByTestId("step-count")).toHaveText(String(totalSteps));
    await expect(page.getByTestId("timeline-waiting")).toHaveCount(0);
    await expectTestDataMarkers(page, "stage 4");
    await expectNoAxeViolations(page, "stage 4, investigation steps");

    // ---- Stage 5: verdict and evidence -------------------------------------
    await tabToAndPress(page, page.getByTestId("see-verdict"));
    await expectStage(page, 5);
    await expectPersistentLabels(page);
    await expect(page.getByTestId("verdict-headline")).toHaveText(ROBERT_HEADLINE);
    await expect(page.getByTestId("count-fail")).toHaveAttribute("data-count", "2");
    await expect(page.getByTestId("count-unknown")).toHaveAttribute("data-count", "0");
    await expect(page.getByTestId("verdict-summary").getByTestId("test-data-tag")).toBeVisible();
    await expect(page.getByTestId("exposure-chart")).toBeVisible();
    await expect(page.getByTestId("scenario-note")).toBeVisible();

    // The limit label starts at the marker it names and stays inside the chart.
    const chart = page.getByTestId("exposure-chart");
    await expect(chart.getByTestId("limit-label")).toHaveText("Confirmed limit 10.0%");
    const labelBox = await chart.getByTestId("limit-label").boundingBox();
    const markerBox = await chart.getByTestId("limit-marker").first().boundingBox();
    const chartBox = await chart.boundingBox();
    expect(labelBox && markerBox && chartBox).toBeTruthy();
    expect(Math.abs(labelBox!.x - (markerBox!.x + markerBox!.width / 2))).toBeLessThanOrEqual(2);
    expect(labelBox!.x + labelBox!.width).toBeLessThanOrEqual(chartBox!.x + chartBox!.width + 0.5);

    // Headline, per-rule results and the exposure chart come first, in that order on screen.
    const top = async (selector: string) => (await page.locator(selector).boundingBox())?.y ?? Number.NaN;
    const order = [await top('[data-testid="verdict-summary"]'), await top("#report-rules"), await top("#report-exposure"), await top("#report-cash"), await top("#report-coverage")];
    expect(order, "headline, rules, exposure, then the rest").toEqual([...order].sort((a, b) => a - b));
    await expectTestDataMarkers(page, "stage 5");
    await expectNoAxeViolations(page, "stage 5, verdict and evidence");

    // Coverage, the sentences and the notes are closed sections that the keyboard opens and closes.
    for (const id of ["report-coverage", "report-sentences", "report-about"]) {
      await expect(page.locator(`#${id}`)).toHaveJSProperty("open", false);
    }
    const coverageSummary = page.locator("#report-coverage > summary");
    await expect(coverageSummary).toContainText("SPY complete · XIU.TO partial (98.0%)");
    await expect(page.getByTestId("fund-coverage").first()).toBeHidden();
    await tabTo(page, coverageSummary);
    await expectVisibleFocusRing(coverageSummary);
    await page.keyboard.press("Enter");
    await expect(page.locator("#report-coverage")).toHaveJSProperty("open", true);
    await expect(page.getByTestId("fund-coverage")).toHaveCount(2);
    await expect(page.getByTestId("fund-coverage").first()).toBeVisible();
    await expect(page.locator('[data-testid="fund-coverage"][data-fund-id="XIU.TO"]').getByTestId("coverage-sentence")).toHaveText("Partial — 98.0% of the fund reported");
    await page.keyboard.press("Space");
    await expect(page.locator("#report-coverage")).toHaveJSProperty("open", false);

    // The headline card links to each section: a closed one is opened and receives focus, and the stage in the address stays.
    const sectionLinks = page.getByRole("navigation", { name: "Sections of this report" });
    await tabBackTo(page, sectionLinks.getByRole("link", { name: "In sentences" }));
    await expectVisibleFocusRing(sectionLinks.getByRole("link", { name: "In sentences" }));
    await page.keyboard.press("Enter");
    await expect(page.locator("#report-sentences")).toHaveJSProperty("open", true);
    await expect(page.locator("#report-sentences > summary")).toBeFocused();
    await expect(page.getByTestId("explanation-statement")).toHaveCount(5);
    await expect(page).toHaveURL(/#\/verdict$/);
    await tabBackTo(page, sectionLinks.getByRole("link", { name: "Exposure" }));
    await page.keyboard.press("Enter");
    await expect(page.getByRole("heading", { level: 2, name: "Exposure: held directly and through funds" })).toBeFocused();
    await expect(page).toHaveURL(/#\/verdict$/);

    // Exposure chart: the breakdown of a company's bar opens from the keyboard; nothing depends on hover.
    const nvidia = page.locator('[data-testid="exposure-row"][data-issuer-id="NVIDIA"]');
    await expect(nvidia.getByTestId("exposure-breakdown")).toBeVisible(); // the company being bought starts open
    const other = page.locator('[data-testid="exposure-row"]:not([data-issuer-id="NVIDIA"])').first();
    await expect(other.getByTestId("exposure-breakdown")).toBeHidden();
    await tabTo(page, other.locator("summary"));
    await expectVisibleFocusRing(other.locator("summary"));
    await page.keyboard.press("Enter");
    await expect(other.getByTestId("exposure-breakdown")).toBeVisible();
    await expect(other.locator('tr[data-row="range"]')).toBeVisible();
    await page.keyboard.press("Space");
    await expect(other.getByTestId("exposure-breakdown")).toBeHidden();
    await page.keyboard.press("Enter");
    await expect(page.getByTestId("exposure-chart").locator("[title]")).toHaveCount(0);
    await expectNoAxeViolations(page, "stage 5, sections and an exposure breakdown open");

    // Evidence drawer: opens from a figure, traps focus, closes on Escape, returns focus.
    const evidenceButton = page.getByRole("button", { name: "Evidence for Maximum exposure to a single company, after the purchase" });
    await tabBackTo(page, evidenceButton);
    await expectVisibleFocusRing(evidenceButton);
    await page.keyboard.press("Enter");
    const drawer = page.getByRole("dialog");
    await expect(drawer).toBeVisible();
    await expect(drawer).toHaveAccessibleName(/^Evidence: Maximum exposure to a single company/);
    // The formula is its own block, apart from the values it was computed from.
    const firstRecord = drawer.getByTestId("evidence-record").first();
    await expect(firstRecord.getByRole("heading", { name: "How it was calculated" })).toBeVisible();
    await expect(firstRecord.getByRole("heading", { name: "Formula, as recorded by the engine" })).toBeVisible();
    await expect(firstRecord.getByTestId("evidence-formula")).toHaveText("0.25 + 0.012 = 0.262");
    await expect(firstRecord.getByRole("heading", { name: "Values it was computed from" })).toBeVisible();
    await expect(firstRecord.getByTestId("evidence-input")).toHaveCount(2);
    await expect(drawer.getByTestId("source-details-note")).toContainText("load with the live API");
    await expect(firstRecord.getByTestId("test-data-tag")).toBeVisible();
    const focusIsInDrawer = () => page.evaluate(() => Boolean(document.activeElement?.closest('[role="dialog"]')));
    expect(await focusIsInDrawer()).toBe(true);
    for (let press = 0; press < 25; press += 1) {
      await page.keyboard.press("Tab");
      expect(await focusIsInDrawer(), `focus left the drawer after ${press + 1} presses of Tab`).toBe(true);
    }
    for (let press = 0; press < 5; press += 1) {
      await page.keyboard.press("Shift+Tab");
      expect(await focusIsInDrawer(), "focus left the drawer on Shift+Tab").toBe(true);
    }
    await expectNoAxeViolations(page, "stage 5, evidence drawer open");
    await page.keyboard.press("Escape");
    await expect(drawer).toBeHidden();
    await expect(evidenceButton).toBeFocused();

    // The close button returns focus as well.
    await page.keyboard.press("Enter");
    await expect(drawer).toBeVisible();
    await tabToAndPress(page, drawer.getByRole("button", { name: "Close evidence" }));
    await expect(drawer).toBeHidden();
    await expect(evidenceButton).toBeFocused();

    // ---- Stage 6: challenge -------------------------------------------------
    await tabToAndPress(page, page.getByRole("link", { name: "Challenge this result" }), "Enter");
    await expectStage(page, 6);
    await expectPersistentLabels(page);
    // Robert's scenario challenge is a rule change, so that path is shown first.
    const ruleTab = page.getByRole("tab", { name: "Change a rule" });
    await expect(ruleTab).toHaveAttribute("aria-selected", "true");
    await expect(page.getByTestId("change-rule-form")).toBeVisible();
    await expectNoAxeViolations(page, "stage 6, change a rule");

    // Tabs: one tab stop, arrow keys move between the three paths.
    await tabTo(page, ruleTab);
    await expectVisibleFocusRing(ruleTab);
    await page.keyboard.press("ArrowLeft");
    await expect(page.getByRole("tab", { name: "Clarify a preference" })).toBeFocused();
    await expect(page.getByRole("tab", { name: "Clarify a preference" })).toHaveAttribute("aria-selected", "true");
    await expectNoAxeViolations(page, "stage 6, clarify a preference");
    await page.keyboard.press("ArrowLeft");
    await expect(page.getByRole("tab", { name: "Correct a fact" })).toBeFocused();
    await expect(page.getByTestId("correct-fact-form")).toBeVisible();
    await expectNoAxeViolations(page, "stage 6, correct a fact");
    await page.keyboard.press("ArrowRight");
    await page.keyboard.press("ArrowRight");
    await expect(ruleTab).toBeFocused();
    await expect(page.getByTestId("change-rule-form")).toBeVisible();

    // A draft number shows the recorded preview; nothing is confirmed by it.
    const form = page.getByTestId("change-rule-form");
    const newValue = form.getByRole("textbox", { name: /^New value/ });
    await tabTo(page, newValue);
    await expectVisibleFocusRing(newValue);
    await page.keyboard.type("20");
    await expect(form.getByTestId("draft-preview-result")).toContainText("Preview: Fail");
    await expect(form.getByTestId("draft-preview-result")).toContainText("draft limit 20.0%");
    await expect(page.getByTestId("rule-change-comparison")).toHaveCount(0);
    await expectNoAxeViolations(page, "stage 6, change a rule with a preview");

    // The scenario's own change: 10% to 30%.
    await tabBackTo(page, form.getByTestId("fill-example-rule"));
    await page.keyboard.press("Enter");
    await expect(newValue).toHaveValue("30");
    await expect(form.getByTestId("draft-preview-not-recorded")).toBeVisible();
    await tabToAndPress(page, page.getByTestId("submit-rule-change"));
    const comparisonHeading = page.getByRole("heading", { level: 2, name: "Version comparison: before and after the rule change" });
    await expect(comparisonHeading).toBeFocused();
    const changedRows = page.locator('[data-testid="policy-diff-row"][data-change="CHANGED"]');
    await expect(changedRows).toHaveCount(1);
    await expect(changedRows).toContainText("10.0%");
    await expect(changedRows).toContainText("30.0%");
    await expect(page.locator('[data-testid="policy-diff-row"][data-change="UNCHANGED"]')).toHaveCount(1);
    await expect(page.getByTestId("result-comparison")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId("comparison-headline")).toHaveText([ROBERT_HEADLINE, "1 of 2 confirmed rules is not respected"]);

    // The form and the comparison are separate sections, each under its own heading, the comparison below the form.
    const formsPanel = page.locator("#challenge-forms");
    const comparisonSection = page.getByTestId("comparison-section");
    await expect(formsPanel.getByTestId("change-rule-form")).toBeVisible();
    await expect(formsPanel.getByTestId("rule-change-comparison")).toHaveCount(0);
    await expect(comparisonSection.getByTestId("change-rule-form")).toHaveCount(0);
    await expect(comparisonSection).toContainText("Outcome of the rule change — separate from the form above");
    await expect(comparisonSection.getByRole("heading", { level: 3 })).toHaveText(["What changed in the policy", "The same purchase under each version", "Each rule under the two versions"]);
    const formsBox = await formsPanel.boundingBox();
    const comparisonBox = await comparisonSection.boundingBox();
    expect(comparisonBox && formsBox && comparisonBox.y >= formsBox.y + formsBox.height, "the comparison starts below the end of the forms panel").toBe(true);
    await expectTestDataMarkers(page, "stage 6, old and new compared");
    await expectNoAxeViolations(page, "stage 6, old and new compared");

    // The earlier report can still be opened, and is unchanged.
    await tabToAndPress(page, page.getByTestId("comparison-report").first().getByRole("button", { name: "Open this report" }));
    await expectStage(page, 5);
    await expect(page.getByText("You are reading an earlier report, checked against policy version 1")).toBeVisible();
    await expect(page.getByTestId("verdict-headline")).toHaveText(ROBERT_HEADLINE);
    await expect(page.getByTestId("report-entry")).toHaveCount(2);
    await expectNoAxeViolations(page, "stage 5, earlier report reopened");
  });

  test("the stepper works as links: Enter moves to a stage and Back returns", async ({ page }) => {
    await page.goto(START_URL);
    await expect(page.getByTestId("portfolio-table")).toBeVisible();
    await tabToAndPress(page, page.getByRole("link", { name: "Step 3 of 6: Proposed purchase" }));
    await expectStage(page, 3);
    await expect(page).toHaveURL(/#\/purchase$/);
    await page.goBack();
    await expectStage(page, 1);
    await page.goForward();
    await expectStage(page, 3);
    await expect(stageHeading(page)).toBeVisible();
  });
});
