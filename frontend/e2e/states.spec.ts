import { expect, test, type Page } from "@playwright/test";
import {
  checkIdeaAndWaitForReport,
  confirmScenarioRules,
  continueToPurchase,
  expectNoAxeViolations,
  expectPersistentLabels,
  expectPortfolioLoaded,
  expectScreen,
  expectTestDataMarkers,
  mainAlert,
  openExposurePanel,
  openPortfolioPanel,
  openPurchasePreview,
  openReport,
  panelSummary,
  START_URL,
  stepLink,
} from "./helpers";

/** From the first screen to "Your limits", with the pointer, without confirming anything. */
async function toLimits(page: Page) {
  await page.getByTestId("continue-link").click();
  await expectScreen(page, "goals");
}

test.describe("states other than the happy path", () => {
  test("Mateo: a question instead of a guessed rule, two failures stated plainly, and what was already failing kept apart", async ({ page }) => {
    test.setTimeout(90_000);
    await page.goto(START_URL);
    await expectPortfolioLoaded(page);
    await page.getByRole("button", { name: "Use Mateo’s portfolio" }).click();
    await expectPortfolioLoaded(page, "Mateo");
    await openPortfolioPanel(page);

    await toLimits(page);
    await expect(page.getByTestId("rule-card")).toHaveCount(2);

    // His own sentence: ambiguous wording becomes a question, not a rule. The field is in a panel that is closed until asked for.
    await panelSummary(page, "Add a limit in your own words").click();
    await page.getByTestId("use-scenario-sentence").click();
    await page.getByTestId("interpret-words").click();
    const question = page.getByTestId("interpretation").getByTestId("clarification-card");
    await expect(question).toBeVisible();
    await expect(question.getByText("No rule written yet")).toBeVisible();
    await expect(question.getByTestId("unsupported-option").first()).toBeVisible();
    // The draft that measures what a listed rule already measures is not listed twice.
    await expect(page.getByTestId("drafted-rule")).toContainText("Already listed under “Your limits”");
    await expect(page.getByTestId("rule-card")).toHaveCount(2);
    await expectNoAxeViolations(page, "Mateo, clarification question");

    await question.getByRole("radio").first().check();
    await question.getByTestId("choose-definition").click();
    await expect(question.getByTestId("clarification-outcome")).toContainText("Already listed under “Your limits”");
    await expect(page.getByTestId("rule-card")).toHaveCount(2);

    await page.getByTestId("confirm-rules").click();
    await expect(page.getByTestId("policy-rule-card")).toHaveCount(2);

    await continueToPurchase(page);
    await checkIdeaAndWaitForReport(page);

    const report = page.getByTestId("report");
    await expect(report.getByTestId("verdict-headline")).toHaveText("2 of 2 confirmed rules are not respected");
    await expect(report.getByTestId("verdict-summary")).toHaveAttribute("data-tone", "fail");
    await expect(report.getByTestId("count-fail")).toHaveAttribute("data-count", "2");
    await expect(report.getByTestId("starting-breaches")).toHaveAttribute("data-count", "2");
    // Already failing before the purchase: its own panel, and what the purchase adds shown as an unresolved range.
    const starting = page.locator("#report-starting");
    await expect(starting.getByRole("heading", { level: 2 })).toHaveText("Already not respected before the purchase");
    await expect(starting.getByTestId("starting-finding")).toHaveCount(2);
    await expect(starting.getByTestId("purchase-effect").first()).toContainText("Unresolved");
    await expect(starting.getByTestId("purchase-effect").first()).toContainText("0.0% to +15.0%");
    await expect(report.getByTestId("unknown-causes").first()).toContainText("What is still unknown");
    // What a fund without a holdings file leaves unknown stays on the line of the closed section.
    await expect(page.locator("#report-details > summary")).toContainText("ESGV missing");
    // The chart is in the closed panel "Explore my exposures": the possible but unmeasured part is drawn there.
    await openExposurePanel(page);
    await expect(report.locator('[data-seg="possible"]').first()).toBeVisible();
    // The largest compliant purchase and the coverage are in "More analysis and sources".
    await page.locator("#report-details > summary").click();
    await panelSummary(page, "Largest purchase that respects every confirmed rule").click();
    await expect(report.getByTestId("max-compliant")).toBeVisible();
    await expect(report.getByTestId("max-compliant")).toHaveAttribute("data-status", "NO_FEASIBLE_PURCHASE");
    await expect(report.getByTestId("max-final-weight")).toHaveCount(0);
    await expect(page.locator("#report-coverage > summary")).toContainText("ESGV missing");
    await expectPersistentLabels(page);
    await expectTestDataMarkers(page, "Mateo, verdict");
    await expectNoAxeViolations(page, "Mateo, verdict with findings before the purchase and a possible range");

    // His scenario challenge is a clarification: it is read again and changes neither the policy nor the report.
    await page.getByRole("link", { name: "Review or dispute this result" }).click();
    await expectScreen(page, "challenge");
    await expect(page.getByRole("tab", { name: "Clarify a preference" })).toHaveAttribute("aria-selected", "true");
    await page.getByTestId("fill-example-preference").click();
    await page.getByTestId("submit-preference").click();
    await expect(page.getByTestId("preference-response")).toContainText("Your clarification was read. No rule was changed.");
    await expect(page.getByTestId("preference-response").getByTestId("unsupported-request")).toBeVisible();
    await expect(page.getByTestId("rule-change-comparison")).toHaveCount(0);
    await expectNoAxeViolations(page, "Mateo, clarified preference");
  });

  test("a rule whose number is cleared is left out of the confirmation and says so", async ({ page }) => {
    await page.goto(START_URL);
    await expectPortfolioLoaded(page);
    await toLimits(page);
    const card = page.getByTestId("rule-card").first();
    await card.getByRole("textbox").fill("");
    await expect(card.getByTestId("threshold-empty-note")).toContainText("No threshold has been set");
    await expect(card.getByRole("slider")).toHaveAttribute("aria-valuetext", "Not set");
    await expect(page.getByTestId("confirm-rules")).toHaveText("Confirm this 1 rule with its number");
    await expect(page.getByTestId("confirm-hint")).toContainText("1 rule has no valid number and stays proposed.");
    await expectNoAxeViolations(page, "a proposed rule with an empty threshold");

    await page.getByTestId("rule-card").nth(1).getByRole("textbox").fill("");
    // With no valid number left, the button reads as unavailable but still takes focus and a key press, so that it can say why.
    // (Playwright's click() waits for an element that is not aria-disabled; it is pressed from the keyboard, as a person would.)
    const confirm = page.getByTestId("confirm-rules");
    await expect(confirm).toHaveText("Confirm the rules");
    await expect(confirm).toHaveAttribute("aria-disabled", "true");
    await confirm.focus();
    await expect(confirm).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(mainAlert(page)).toContainText("No proposed rule has a valid number yet");
    await expect(card.getByRole("textbox")).toBeFocused();
    await expect(page.getByTestId("policy-rule-card")).toHaveCount(0);
  });

  test("a request the service cannot evaluate shows its execution state, never a verdict", async ({ page }) => {
    await page.goto(START_URL);
    await expectPortfolioLoaded(page);
    await confirmScenarioRules(page);
    await continueToPurchase(page);
    await openPurchasePreview(page);
    await expect(page.getByTestId("purchase-preview").getByTestId("cash-after")).toHaveText("5.0%");

    // The recorded invalid request: a final weight below what is already held.
    await page.getByLabel("Which investment?").selectOption("RY.TO");
    await page.getByLabel("Share of the portfolio after buying").fill("2");
    const state = page.getByTestId("execution-state");
    await expect(state).toBeVisible();
    await expect(state).toHaveAttribute("data-execution-status", "INVALID_REQUEST");
    await expect(state.getByTestId("execution-message")).toContainText("below its current direct weight (5.0%)");
    await expect(state).toContainText("No rule was evaluated, so there is no preview to show.");
    const preview = page.getByTestId("purchase-preview");
    await expect(preview.locator("[data-status]")).toHaveCount(0);
    await expect(preview.getByTestId("feasibility-table")).toHaveCount(0);
    await expect(page.getByTestId("verdict-summary")).toHaveCount(0);
    // Started as it is, it would be refused for the same reason, and the page says so beside the button.
    await expect(page.getByTestId("start-preview-refusal")).toContainText("this request cannot be evaluated");
    await expectNoAxeViolations(page, "purchase the service cannot evaluate");
  });

  test("a request the test data holds no answer for is refused calmly, with nothing invented", async ({ page }) => {
    await page.goto(START_URL);
    await expectPortfolioLoaded(page);
    await confirmScenarioRules(page);
    await continueToPurchase(page);
    await openPurchasePreview(page);
    await page.getByLabel("Share of the portfolio after buying").fill("12");
    await expect(page.getByLabel("Share of the portfolio after buying")).toHaveValue("12");
    await expect(page.getByTestId("purchase-preview-not-recorded")).toBeVisible();
    await expect(page.getByTestId("purchase-preview-not-recorded")).toContainText("The test data holds no recorded check of NVDA at a final direct weight of 12.0%");
    await expect(page.getByTestId("cash-after")).toHaveCount(0);

    await page.getByTestId("start-investigation").click();
    await expect(page.getByTestId("start-not-recorded")).toContainText("NVDA at a final direct weight of 12.0%");
    await expect(page.getByText("No investigation was created.")).toBeVisible();
    await expectScreen(page, "purchase", { focused: false });
    await expect(page.getByTestId("verdict-summary")).toHaveCount(0);
    await expectNoAxeViolations(page, "no recorded answer for this request");
  });

  test("a failed portfolio load is an error with a retry, not an empty table", async ({ page }) => {
    await page.goto("/?fixtures=1&simulate=portfolio-error");
    const alert = mainAlert(page);
    await expect(alert).toContainText("The portfolio could not be loaded");
    await expect(alert.getByRole("button", { name: "Try again" })).toBeVisible();
    await expect(page.getByTestId("portfolio-table")).toHaveCount(0);
    await expect(page.getByTestId("valuation-date")).toHaveText("Valuation date: unavailable");
    await expect(page.getByTestId("simulation-label")).toBeVisible();
    await expectNoAxeViolations(page, "portfolio load failed");
  });

  test("a failed job is shown as failed and produces no verdict", async ({ page }) => {
    await page.goto("/?fixtures=1&simulate=job-failed");
    await expectPortfolioLoaded(page);
    await confirmScenarioRules(page);
    await continueToPurchase(page);
    await page.getByTestId("start-investigation").click();
    // "Check my idea" leads to the result screen; while the job runs it links to the steps of the investigation.
    await expectScreen(page, "verdict");
    await page.getByRole("link", { name: "See the investigation steps" }).click();
    await expectScreen(page, "investigation");
    await expect(mainAlert(page)).toContainText("The investigation failed", { timeout: 30_000 });
    await expect(mainAlert(page)).toContainText("DATA_UNAVAILABLE");
    await expect(page.locator('[data-testid="timeline-step"][data-step-status="ERROR"]')).toHaveCount(1);
    await expect(page.getByTestId("see-verdict")).toHaveCount(0);
    await expectNoAxeViolations(page, "investigation failed");

    // The result screen of the same job: the last step of the navigation leads back to it.
    await stepLink(page, 4).click();
    await expectScreen(page, "verdict");
    await expect(mainAlert(page)).toContainText("This investigation failed, so there is no verdict");
    await expect(page.getByTestId("failure-code")).toContainText("A failed run is not a pass and not a fail.");
    await expect(page.getByTestId("report")).toHaveCount(0);
    await expect(page.getByTestId("verdict-summary")).toHaveCount(0);
    await expect(page.getByRole("main").locator("[data-status]")).toHaveCount(0);
    await expectNoAxeViolations(page, "result screen of a failed investigation");
  });

  test("polling stops at its deadline with a visible failure and a way to keep waiting", async ({ page }) => {
    await page.goto("/?fixtures=1&simulate=poll-timeout");
    await expectPortfolioLoaded(page);
    await confirmScenarioRules(page);
    await continueToPurchase(page);
    await page.getByTestId("start-investigation").click();
    // The result screen waits, then says that no final answer came; it never shows a verdict in its place.
    await expectScreen(page, "verdict");
    await expect(page.getByRole("main").getByRole("status").filter({ hasText: "No verdict exists yet." })).toBeVisible();
    await expect(mainAlert(page)).toContainText("No final answer within the time limit", { timeout: 30_000 });
    await expect(mainAlert(page)).toContainText("No verdict is shown, because none was received.");
    await expect(page.getByTestId("report")).toHaveCount(0);
    await expectNoAxeViolations(page, "result screen, polling deadline reached");

    // The steps of the investigation, with the same failure and a way to keep waiting.
    await page.getByRole("link", { name: "See the investigation steps" }).click();
    await expectScreen(page, "investigation");

    const alert = mainAlert(page);
    await expect(alert).toContainText("No final answer within 4 seconds", { timeout: 30_000 });
    await expect(alert).toContainText("No verdict is shown, because none was received.");
    await expect(page.getByTestId("timeline-waiting")).toHaveCount(0);
    await expect(page.getByTestId("see-verdict")).toHaveCount(0);
    await expectNoAxeViolations(page, "polling deadline reached");

    // "Keep waiting" starts a fresh poll with a fresh deadline: the failure goes away and the job's own running step is shown.
    await alert.getByRole("button", { name: "Keep waiting" }).click();
    await expect(mainAlert(page)).toHaveCount(0);
    await expect(page.locator('[data-testid="timeline-step"][data-step-status="RUNNING"]')).toBeVisible();
    await expect(page.getByTestId("see-verdict")).toHaveCount(0);
  });

  test("a preview that fails says so, shows no figure, and leaves the proposed rule untouched", async ({ page }) => {
    await page.goto("/?fixtures=1&simulate=check-error");
    await expectPortfolioLoaded(page);
    await toLimits(page);
    const card = page.getByTestId("rule-card").first();
    await card.locator("summary", { hasText: "Preview this limit" }).click();
    await card.getByRole("textbox").fill("12");
    await expect(card.getByTestId("draft-preview-error")).toBeVisible();
    await expect(card.getByTestId("draft-preview-error")).toContainText("The preview could not be calculated.");
    await expect(card.getByText("Proposed: inactive")).toBeVisible();
    await expectNoAxeViolations(page, "draft preview failed");

    await card.getByRole("textbox").fill("10");
    await page.getByTestId("confirm-rules").click();
    await expect(page.getByTestId("policy-rule-card")).toHaveCount(2);
    await continueToPurchase(page);
    await openPurchasePreview(page);
    await expect(page.getByTestId("purchase-preview-error")).toBeVisible();
    await expect(page.getByTestId("purchase-preview-error")).toContainText("Simulated failure (test data)");
    await expect(page.getByTestId("cash-after")).toHaveCount(0);
    await expectNoAxeViolations(page, "purchase preview failed");
  });

  test("a fact proposed as a correction is shown as unverified beside the recorded value", async ({ page }) => {
    await page.goto(START_URL);
    await openReport(page);
    // From the evidence drawer of a figure straight to "Correct a fact", with that figure chosen.
    await page.getByRole("button", { name: "Evidence for Maximum exposure to a single company, after the purchase" }).click();
    await page.getByRole("dialog").getByTestId("evidence-record").first().getByRole("link", { name: "Challenge this figure" }).click();
    await expectScreen(page, "challenge");
    await expect(page.getByRole("tab", { name: "Correct a fact" })).toHaveAttribute("aria-selected", "true");
    const form = page.getByTestId("correct-fact-form");
    await expect(form.getByLabel("Which figure?")).toHaveValue("ev-nvda-lower");

    // The recorded exchange: the weight of NVIDIA inside SPY.
    await form.getByLabel("Which figure?").selectOption("ev-spy-nvda-weight");
    await expect(form.getByTestId("original-evidence")).toContainText("6.00%");
    await form.getByLabel("The value you believe is right, in percent").fill("8");
    await form.getByLabel("Why you believe the recorded value is wrong").fill("The fund fact sheet I have shows a higher NVIDIA weight in SPY.");
    await form.getByLabel("Where your value comes from (optional)").fill("SPY fact sheet, user's own copy (not retrieved by the system)");
    await page.getByTestId("submit-correction").click();

    const card = page.getByTestId("correction-card");
    await expect(card).toContainText("Proposed correction: unverified");
    await expect(card.getByTestId("correction-proposed")).toHaveText("8.00%");
    await expect(card.getByTestId("correction-original")).toContainText("6.00%");
    await expect(card).toContainText("Not used in any calculation");
    await expect(form.getByTestId("original-evidence")).toContainText("6.00%");
    await expectTestDataMarkers(page, "review, a proposed correction");
    await expectNoAxeViolations(page, "review, a proposed correction");
  });
});
