import { expect, test } from "@playwright/test";
import {
  expectNoAxeViolations,
  expectPersistentLabels,
  expectPortfolioLoaded,
  expectScreen,
  expectTestDataMarkers,
  expectVisibleFocusRing,
  overviewChart,
  panelSummary,
  stageHeading,
  START_URL,
  stepLink,
  tabBackTo,
  tabTo,
  tabToAndPress,
} from "./helpers";

const ROBERT_HEADLINE = "2 of 2 confirmed rules are not respected";
const APP_NAME = "ETHOS: fictional simulation";

/**
 * The whole simulation, driven with the keyboard only (Tab, Shift+Tab, Enter,
 * Space, arrows, Escape, typing) on the static build in fixtures mode. No
 * mouse action is used anywhere in this file.
 *
 * The journey has three moments (choose a profile, test an idea, understand
 * the result). "Your limits", "Analysis details" and "Review this result" are
 * secondary screens of the second and third moment.
 */
test.describe("keyboard-only journey through the three steps", () => {
  test("Robert: profile to challenge, with axe on every screen", async ({ page }) => {
    // Two investigations are polled at the contract's interval of 1.5 s, and every control is reached with Tab.
    test.setTimeout(180_000);
    await page.goto(START_URL);
    await expectPortfolioLoaded(page);

    // ---- Step 1, "Choose a profile": focus order follows the reading order --
    await expectScreen(page, "persona", { focused: false });
    await expectPersistentLabels(page);
    // Read once the page has settled: the title must still name the screen after hydration.
    await page.waitForLoadState("networkidle");
    expect(await page.title()).toBe(`Choose a profile: ${APP_NAME}`);
    expect(await page.locator("title").count()).toBe(1);
    const portfolioSummary = panelSummary(page, "View the fictional portfolio");
    const continueLink = page.getByTestId("continue-link");
    await expect(continueLink).toHaveAccessibleName("Set your limits");
    await expect(continueLink).toHaveAttribute("href", "#/goals");
    const expectedOrder = [
      page.getByRole("link", { name: "Skip to main content" }),
      // The header's link to the separate /evidence/ page comes before the steps, in reading order.
      page.getByRole("link", { name: /^Evidence Investigator/ }),
      stepLink(page, 1),
      stepLink(page, 2),
      stepLink(page, 3),
      stepLink(page, 4),
      page.getByTestId("persona-robert").locator("summary"),
      page.getByTestId("persona-mateo").locator("summary"),
      page.getByRole("button", { name: "Use Mateo’s portfolio" }),
      page.getByTestId("persona-amira").locator("summary"),
      page.getByRole("button", { name: "Use Amira’s portfolio" }),
      portfolioSummary,
      page.getByTestId("customize-open"),
      continueLink,
    ];
    for (const control of expectedOrder) {
      await page.keyboard.press("Tab");
      await expect(control).toBeFocused();
      await expectVisibleFocusRing(control);
    }
    await expectTestDataMarkers(page, "step 1, portfolio panel closed");
    await expectNoAxeViolations(page, "step 1, choose a profile");

    // The portfolio is a closed panel that the keyboard opens; the case facts inside it are one more stop.
    await expect(page.getByTestId("portfolio-table")).toBeHidden();
    await tabBackTo(page, portfolioSummary);
    await page.keyboard.press("Enter");
    await expect(page.getByTestId("portfolio-table")).toBeVisible();
    await expect(page.getByTestId("fiction-notice")).toBeVisible();
    await page.keyboard.press("Tab");
    await expect(page.getByTestId("case-facts").locator("summary")).toBeFocused();
    await expectVisibleFocusRing(page.getByTestId("case-facts").locator("summary"));
    await expectTestDataMarkers(page, "step 1, portfolio panel open");
    await expectNoAxeViolations(page, "step 1, portfolio panel open");

    // The skip link is the first stop and moves focus to the main region.
    await page.goto(START_URL);
    await expectPortfolioLoaded(page);
    await page.keyboard.press("Tab");
    await expect(page.getByRole("link", { name: "Skip to main content" })).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(page.locator("#main-content")).toBeFocused();
    await expect(page).toHaveURL(/\?fixtures=1$/); // the skip link does not disturb the stage in the hash

    // ---- Step 3, "Test an idea", opened early from the stepper: without a confirmed limit it says what comes first
    await tabToAndPress(page, stepLink(page, 3));
    await expectScreen(page, "purchase");
    await expectPersistentLabels(page);
    await expect(page).toHaveTitle(`Test an idea: ${APP_NAME}`);
    await expect(page.getByRole("main").getByText("First, confirm your limits")).toBeVisible();
    await expect(page.getByTestId("start-investigation")).toHaveAttribute("aria-disabled", "true");
    await expect(page.getByRole("main").getByText("Needs at least one confirmed rule.")).toBeVisible();
    await expectNoAxeViolations(page, "step 2, test an idea, no confirmed limit yet");

    // ---- Step 2, "Your limits": the scenario's rules as proposals -> explicit confirmation
    await tabToAndPress(page, page.getByRole("link", { name: "Set my limits" }));
    await expectScreen(page, "goals");
    await expectPersistentLabels(page);
    await expect(page).toHaveTitle(`Your limits: ${APP_NAME}`);
    await expect(page.getByTestId("rule-card")).toHaveCount(2);
    await expect(page.getByTestId("rule-card").first().getByText("Proposed: inactive")).toBeVisible();
    await expect(page.getByTestId("policy-rule-card")).toHaveCount(0);
    await expectNoAxeViolations(page, "step 2, proposed limits");

    // A threshold can be changed from the keyboard, and a preview is labelled as a preview.
    const firstCard = page.getByTestId("rule-card").first();
    const field = firstCard.getByRole("textbox");
    const slider = firstCard.getByRole("slider");
    // The preview of a card is a closed section of it: open it first, from the keyboard.
    const previewSummary = firstCard.locator("summary", { hasText: "Preview this limit" });
    await expect(firstCard.getByTestId("draft-preview")).toBeHidden();
    await tabToAndPress(page, previewSummary);
    await expect(firstCard.getByTestId("draft-preview")).toBeVisible();
    await tabBackTo(page, slider);
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
    await expect(firstCard.getByTestId("draft-preview")).toContainText("Preview with draft threshold: not your confirmed policy");
    await expect(firstCard.getByTestId("draft-preview").getByTestId("test-data-tag")).toBeVisible();
    await expectNoAxeViolations(page, "step 2, a draft preview");
    await page.keyboard.press("ControlOrMeta+a");
    await page.keyboard.type("10");
    await expect(field).toHaveValue("10");

    await tabToAndPress(page, page.getByTestId("confirm-rules"));
    await expect(page.getByTestId("policy-rule-card")).toHaveCount(2);
    // The cards that held focus are gone: focus goes to the policy they became part of.
    await expect(page.getByRole("heading", { name: "Your confirmed limits" })).toBeFocused();
    await expect(page.locator("#confirmed-policy")).toContainText("2 active rules");
    await expectTestDataMarkers(page, "step 2, confirmed limits");
    await expectNoAxeViolations(page, "step 2, confirmed limits");

    // ---- Step 2, "Test an idea": the purchase as a final direct weight -----
    await tabToAndPress(page, page.getByTestId("continue-link"));
    await expectScreen(page, "purchase");
    await expectPersistentLabels(page);
    await expect(page.getByRole("main").getByText("First, confirm your limits")).toHaveCount(0);
    await expect(page.getByTestId("funding-statement")).toHaveText("Funded from existing cash; all other positions unchanged; fees and taxes excluded.");
    await expect(page.getByLabel("Which investment?")).toHaveValue("NVDA");
    await expect(page.getByLabel("Share of the portfolio after buying")).toHaveValue("25");
    // The cash figure is the service's answer to POST /check, labelled as a preview. Its panel is closed until asked for.
    const previewPanel = panelSummary(page, "Preview cash and exposures");
    await expect(page.getByTestId("purchase-preview")).toBeHidden();
    await tabToAndPress(page, previewPanel);
    await expect(page.getByTestId("purchase-preview-label")).toHaveText("Preview: computed by the service for the request above");
    await expect(page.getByTestId("purchase-preview-label")).toBeVisible();
    await expect(page.getByTestId("purchase-preview").getByTestId("cash-after")).toHaveText("5.0%");
    await expect(page.getByTestId("purchase-preview").getByTestId("additional-purchase")).toHaveText("+25.0 points");
    await expectTestDataMarkers(page, "step 2, test an idea");
    await expectNoAxeViolations(page, "step 2, test an idea with its preview open");

    // ---- Step 3, "Your result" while the investigation runs: no verdict yet -
    await tabBackTo(page, page.getByTestId("start-investigation"));
    await page.keyboard.press("Enter");
    await expectScreen(page, "verdict");
    await expectPersistentLabels(page);
    await expect(page).toHaveTitle(`Your result: ${APP_NAME}`);
    await expect(page.getByRole("main").getByRole("status").filter({ hasText: "No verdict exists yet." })).toBeVisible();
    await expect(page.getByTestId("verdict-summary")).toHaveCount(0);

    // ---- Step 3, "Analysis details": only the steps the job reports --------
    await tabToAndPress(page, page.getByRole("link", { name: "See the investigation steps" }));
    await expectScreen(page, "investigation");
    await expectPersistentLabels(page);
    await expect(page).toHaveTitle(`Analysis details: ${APP_NAME}`);
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
    await expectTestDataMarkers(page, "step 3, analysis details");
    await expectNoAxeViolations(page, "step 3, analysis details");

    // ---- Step 3, "Your result": verdict and evidence ------------------------
    await tabToAndPress(page, page.getByTestId("see-verdict"));
    await expectScreen(page, "verdict");
    await expectPersistentLabels(page);
    await expect(page.getByTestId("verdict-headline")).toHaveText(ROBERT_HEADLINE);
    await expect(page.getByTestId("count-fail")).toHaveAttribute("data-count", "2");
    await expect(page.getByTestId("count-unknown")).toHaveAttribute("data-count", "0");
    await expect(page.getByTestId("verdict-summary").getByTestId("test-data-tag")).toBeVisible();
    await expect(page.getByTestId("rule-result")).toHaveCount(2);

    // Headline and per-rule results come first; the exposure panel and the further analysis follow, in that order on screen.
    const top = async (selector: string) => (await page.locator(selector).boundingBox())?.y ?? Number.NaN;
    const order = [await top('[data-testid="verdict-summary"]'), await top("#report-rules"), await top("#report-exposure"), await top("#report-details")];
    expect(order.every((y) => Number.isFinite(y)), "every section is on the page").toBe(true);
    expect(order, "headline, rules, exposure, then the rest").toEqual([...order].sort((a, b) => a - b));
    await expectTestDataMarkers(page, "step 3, your result");
    await expectNoAxeViolations(page, "step 3, your result");

    // The exposures, the further analysis and, inside it, coverage, the sentences and the notes are closed sections
    // that the keyboard opens and closes.
    for (const id of ["report-exposure", "report-details", "report-coverage", "report-sentences", "report-about"]) {
      await expect(page.locator(`#${id}`)).toHaveJSProperty("open", false);
    }
    const detailsSummary = page.locator("#report-details > summary");
    // What the closed section says of the data stays readable while it is closed.
    await expect(detailsSummary).toContainText("SPY complete · XIU.TO partial (98.0%)");
    await expect(page.getByTestId("fund-coverage").first()).toBeHidden();
    await tabTo(page, detailsSummary);
    await expectVisibleFocusRing(detailsSummary);
    await page.keyboard.press("Enter");
    await expect(page.locator("#report-details")).toHaveJSProperty("open", true);
    await expect(page.locator("#report-cash")).toBeVisible();
    const coverageSummary = page.locator("#report-coverage > summary");
    await expect(coverageSummary).toContainText("SPY complete · XIU.TO partial (98.0%)");
    await expect(page.getByTestId("fund-coverage").first()).toBeHidden();
    await tabTo(page, coverageSummary);
    await expectVisibleFocusRing(coverageSummary);
    await page.keyboard.press("Enter");
    await expect(page.locator("#report-coverage")).toHaveJSProperty("open", true);
    await expect(page.getByTestId("fund-coverage")).toHaveCount(2);
    await expect(page.getByTestId("fund-coverage").first()).toBeVisible();
    await expect(page.locator('[data-testid="fund-coverage"][data-fund-id="XIU.TO"]').getByTestId("coverage-sentence")).toHaveText("Partial: 98.0% of the fund reported");
    await page.keyboard.press("Space");
    await expect(page.locator("#report-coverage")).toHaveJSProperty("open", false);
    // The result in sentences: one more closed section, each sentence a restatement of the figures.
    const sentencesSummary = page.locator("#report-sentences > summary");
    await tabTo(page, sentencesSummary);
    await page.keyboard.press("Enter");
    await expect(page.locator("#report-sentences")).toHaveJSProperty("open", true);
    await expect(page.getByTestId("explanation-statement")).toHaveCount(5);
    await expect(page.getByTestId("explanation-statement").first()).toBeVisible();
    await page.keyboard.press("Enter");
    await expect(page.locator("#report-sentences")).toHaveJSProperty("open", false);
    await tabBackTo(page, detailsSummary);
    await page.keyboard.press("Space");
    await expect(page.locator("#report-details")).toHaveJSProperty("open", false);

    // The headline card links to each section: a closed one is opened, with the sections around it, and receives focus;
    // the stage in the address stays.
    const sectionLinks = page.getByRole("navigation", { name: "Sections of this report" });
    await expect(sectionLinks.getByRole("link")).toHaveText(["See the checks", "Explore my exposures", "Sources and missing data"]);
    await tabBackTo(page, sectionLinks.getByRole("link", { name: "Sources and missing data" }));
    await expectVisibleFocusRing(sectionLinks.getByRole("link", { name: "Sources and missing data" }));
    await page.keyboard.press("Enter");
    await expect(page.locator("#report-details")).toHaveJSProperty("open", true);
    await expect(page.locator("#report-coverage")).toHaveJSProperty("open", true);
    await expect(coverageSummary).toBeFocused();
    await expect(page.getByTestId("fund-coverage").first()).toBeVisible();
    await expect(page).toHaveURL(/#\/verdict$/);
    await tabBackTo(page, sectionLinks.getByRole("link", { name: "See the checks" }));
    await page.keyboard.press("Enter");
    await expect(page.getByRole("heading", { level: 2, name: "What fits and what doesn’t" })).toBeFocused();
    await expect(page).toHaveURL(/#\/verdict$/);
    await expect(overviewChart(page)).toBeHidden();
    await tabBackTo(page, sectionLinks.getByRole("link", { name: "Explore my exposures" }));
    await page.keyboard.press("Enter");
    await expect(page.locator("#report-exposure")).toHaveJSProperty("open", true);
    await expect(page.locator("#report-exposure > summary")).toBeFocused();
    await expect(page).toHaveURL(/#\/verdict$/);
    await expect(overviewChart(page)).toBeVisible();

    // The limit label starts at the marker it names and stays inside the chart.
    const chart = overviewChart(page);
    await expect(chart.getByTestId("limit-label")).toHaveText("Confirmed limit 10.0%");
    const labelBox = await chart.getByTestId("limit-label").boundingBox();
    const markerBox = await chart.getByTestId("limit-marker").first().boundingBox();
    const chartBox = await chart.boundingBox();
    expect(labelBox && markerBox && chartBox).toBeTruthy();
    expect(Math.abs(labelBox!.x - (markerBox!.x + markerBox!.width / 2))).toBeLessThanOrEqual(2);
    expect(labelBox!.x + labelBox!.width).toBeLessThanOrEqual(chartBox!.x + chartBox!.width + 0.5);

    // Exposure chart: the breakdown of a company's bar opens from the keyboard; nothing depends on hover.
    const nvidia = overviewChart(page).locator('[data-testid="exposure-row"][data-issuer-id="NVIDIA"]');
    await expect(nvidia.getByTestId("exposure-breakdown")).toBeVisible(); // the company being bought starts open
    const other = overviewChart(page).locator('[data-testid="exposure-row"]:not([data-issuer-id="NVIDIA"])').first();
    await expect(other.getByTestId("exposure-breakdown")).toBeHidden();
    await tabTo(page, other.locator("summary"));
    await expectVisibleFocusRing(other.locator("summary"));
    await page.keyboard.press("Enter");
    await expect(other.getByTestId("exposure-breakdown")).toBeVisible();
    await expect(other.locator('tr[data-row="range"]')).toBeVisible();
    await page.keyboard.press("Space");
    await expect(other.getByTestId("exposure-breakdown")).toBeHidden();
    await page.keyboard.press("Enter");
    await expect(page.getByTestId("exposure-views").locator("[title]")).toHaveCount(0);
    await expectTestDataMarkers(page, "step 3, sections and an exposure breakdown open");
    await expectNoAxeViolations(page, "step 3, sections and an exposure breakdown open");

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
    await expect(drawer.getByTestId("source-details-note")).toContainText("Only the ids of a figure’s sources are available here");
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
    await expectNoAxeViolations(page, "step 3, evidence drawer open");
    await page.keyboard.press("Escape");
    await expect(drawer).toBeHidden();
    await expect(evidenceButton).toBeFocused();

    // The close button returns focus as well.
    await page.keyboard.press("Enter");
    await expect(drawer).toBeVisible();
    await tabToAndPress(page, drawer.getByRole("button", { name: "Close evidence" }));
    await expect(drawer).toBeHidden();
    await expect(evidenceButton).toBeFocused();

    // ---- Step 4, "Review this result": challenge ----------------------------
    // The next actions of the plain reading; Robert's recorded result supports a largest compliant purchase.
    await expect(page.getByTestId("result-actions").getByRole("link")).toHaveText(["Modify my idea", "Largest share that fits my limits", "Sources and missing data", "Review or dispute this result"]);
    await tabToAndPress(page, page.getByRole("link", { name: "Review or dispute this result" }), "Enter");
    await expectScreen(page, "challenge");
    await expectPersistentLabels(page);
    await expect(page).toHaveTitle(`Review this result: ${APP_NAME}`);
    // Robert's scenario challenge is a rule change, so that path is shown first.
    const ruleTab = page.getByRole("tab", { name: "Change a rule" });
    await expect(ruleTab).toHaveAttribute("aria-selected", "true");
    await expect(page.getByTestId("change-rule-form")).toBeVisible();
    await expectNoAxeViolations(page, "step 3, review, change a rule");

    // Tabs: one tab stop, arrow keys move between the three paths.
    await tabTo(page, ruleTab);
    await expectVisibleFocusRing(ruleTab);
    await page.keyboard.press("ArrowLeft");
    await expect(page.getByRole("tab", { name: "Clarify a preference" })).toBeFocused();
    await expect(page.getByRole("tab", { name: "Clarify a preference" })).toHaveAttribute("aria-selected", "true");
    await expectNoAxeViolations(page, "step 3, review, clarify a preference");
    await page.keyboard.press("ArrowLeft");
    await expect(page.getByRole("tab", { name: "Correct a fact" })).toBeFocused();
    await expect(page.getByTestId("correct-fact-form")).toBeVisible();
    await expectNoAxeViolations(page, "step 3, review, correct a fact");
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
    await expectNoAxeViolations(page, "step 3, review, change a rule with a preview");

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
    await expect(comparisonSection).toContainText("Outcome of the rule change: separate from the form above");
    await expect(comparisonSection.getByRole("heading", { level: 3 })).toHaveText(["What changed in the policy", "The same purchase under each version", "Each rule under the two versions"]);
    const formsBox = await formsPanel.boundingBox();
    const comparisonBox = await comparisonSection.boundingBox();
    expect(comparisonBox && formsBox && comparisonBox.y >= formsBox.y + formsBox.height, "the comparison starts below the end of the forms panel").toBe(true);
    await expectTestDataMarkers(page, "step 3, review, old and new compared");
    await expectNoAxeViolations(page, "step 3, review, old and new compared");

    // The earlier report can still be opened, and is unchanged.
    await tabToAndPress(page, page.getByTestId("comparison-report").first().getByRole("button", { name: "Open this report" }));
    await expectScreen(page, "verdict");
    await expect(page.getByText("You are reading an earlier report, checked against policy version 1")).toBeVisible();
    await expect(page.getByTestId("verdict-headline")).toHaveText(ROBERT_HEADLINE);
    await expect(page.getByTestId("report-entry")).toHaveCount(2);
    await expectNoAxeViolations(page, "step 3, earlier report reopened");
  });

  test("the stepper works as links: Enter moves to a step and Back returns", async ({ page }) => {
    await page.goto(START_URL);
    await expectPortfolioLoaded(page);
    await tabToAndPress(page, stepLink(page, 3));
    await expectScreen(page, "purchase");
    await expect(page).toHaveURL(/#\/purchase$/);
    await page.goBack();
    await expectScreen(page, "persona");
    await page.goForward();
    await expectScreen(page, "purchase");
    await expect(stageHeading(page)).toBeVisible();
    // No step is locked: the last one says what it needs instead of showing a verdict.
    await tabToAndPress(page, stepLink(page, 4));
    await expectScreen(page, "verdict");
    await expect(page).toHaveURL(/#\/verdict$/);
    await expect(page.getByRole("main").getByText("There is no result to show yet")).toBeVisible();
    await expect(page.getByTestId("verdict-summary")).toHaveCount(0);
  });
});
