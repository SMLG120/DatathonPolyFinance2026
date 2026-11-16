import { expect, test } from "@playwright/test";
import { checkIdeaAndWaitForReport, confirmScenarioRules, continueToPurchase, expectNoAxeViolations, expectScreen, START_URL } from "./helpers";

/** What a first-time user meets: what the tool does, the four steps, a plain reading of the result, and no lost work. */
test.describe("a first-time user", () => {
  test("reads what the tool does, follows the four steps, and gets a plain reading of the result with next actions", async ({ page }) => {
    test.setTimeout(90_000);
    await page.goto(START_URL);
    await expect(page.getByTestId("how-it-works")).toContainText("gives no advice and places no trade");
    await expect(page.getByRole("navigation", { name: "Stages of the simulation" }).getByRole("link")).toHaveCount(4);
    await expectNoAxeViolations(page, "step 1 with the introduction");
    await page.screenshot({ path: "test-results/screens/beginner-step1.png", fullPage: true });

    await confirmScenarioRules(page);
    await continueToPurchase(page);
    await expect(page.getByRole("link", { name: "Back to your limits" })).toHaveAttribute("href", "#/goals");
    await checkIdeaAndWaitForReport(page);
    const next = page.getByTestId("what-next");
    await expect(next.getByTestId("what-next-meaning")).toContainText("This idea goes over 2 of the 2 limits you confirmed.");
    await expect(next.getByRole("link", { name: "Modify my idea" })).toBeVisible();
    await next.getByRole("link", { name: "Sources and missing data" }).click();
    await expect(page.locator("#report-coverage")).toHaveJSProperty("open", true);
    await expectScreen(page, "verdict", { focused: false });
    await expectNoAxeViolations(page, "result with the plain reading");
    await page.screenshot({ path: "test-results/screens/beginner-result.png", fullPage: true });

    // A reload starts a new session (state is kept in memory only): the empty result screen says so and where to go.
    await page.reload();
    await expectScreen(page, "verdict", { focused: false });
    await expect(page.getByTestId("empty-result-reload-note")).toContainText("reloading the page");
    await expect(page.getByTestId("empty-result-action")).toHaveAttribute("href", "#/purchase");
  });

  test("opens the Evidence Investigator in a new tab, still on test data, and keeps the progress of the main page", async ({ page, context }) => {
    await page.goto(START_URL);
    await confirmScenarioRules(page);
    const [investigator] = await Promise.all([context.waitForEvent("page"), page.getByRole("link", { name: /^Evidence Investigator/ }).click()]);
    await investigator.waitForLoadState();
    await expect(investigator).toHaveURL(/\/evidence\/\?fixtures=1$/);
    await expect(investigator.getByRole("heading", { name: "Enter the access code" })).toHaveCount(0);
    await expect(investigator.getByText(/Test data/).first()).toBeVisible();
    // The main page is untouched: the confirmed limits are still there.
    await expectScreen(page, "goals", { focused: false });
    await expect(page.getByTestId("policy-rule-card").first()).toBeVisible();
  });
});
