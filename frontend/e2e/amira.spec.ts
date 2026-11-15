import { expect, test } from "@playwright/test";
import { expectNoAxeViolations, expectNoHorizontalOverflow, expectPersistentLabels, START_URL, tabToAndPress } from "./helpers";

const SENTENCE = "I want maximum growth and strict diversification.";

/** Desktop, test data: Amira is the third persona; her sentence gets a question, not a verdict. */
test.describe("Amira, the third persona", () => {
  test("is chosen from the keyboard, loads her fictional portfolio, and her sentence becomes a question", async ({ page }) => {
    test.setTimeout(90_000);
    await page.goto(START_URL);
    await expect(page.getByTestId("portfolio-table")).toBeAttached();
    await expect(page.locator('[data-testid^="persona-"]').filter({ has: page.locator("h3") })).toHaveCount(3);

    await tabToAndPress(page, page.getByRole("button", { name: "Use Amira’s portfolio" }));
    await expect(page.getByTestId("portfolio-table")).toContainText("Amira’s fictional portfolio");
    await page.locator("summary", { hasText: "View the fictional portfolio" }).click();
    await expect(page.getByTestId("portfolio-table")).toBeVisible();
    await expect(page.getByTestId("persona-amira").getByTestId("persona-selected")).toBeVisible();
    await expect(page.getByTestId("fiction-notice")).toBeVisible();
    for (const name of ["Bitcoin", "Ether", "Shopify", "JPMorgan Chase"]) await expect(page.getByTestId("portfolio-table")).toContainText(name);
    await expectPersistentLabels(page);
    await expectNoAxeViolations(page, "Amira, stage 1");
    await page.screenshot({ path: "test-results/screens/amira-desktop-stage1.png", fullPage: true });

    await page.evaluate(() => (window.location.hash = "#/goals"));
    await expect(page.getByTestId("rule-card")).toHaveCount(1);
    await expect(page.getByTestId("rule-card")).toHaveCount(1);
    await expect(page.getByTestId("rule-card")).toHaveAttribute("data-rule-origin", "FICTIONAL_SCENARIO");
    await page.locator("summary", { hasText: "Add a limit in your own words" }).click();
    await page.getByTestId("use-scenario-sentence").click();
    await expect(page.locator("textarea").filter({ hasText: "" }).first()).toHaveValue(SENTENCE);
    await page.getByTestId("interpret-words").click();
    const question = page.getByTestId("interpretation").getByTestId("clarification-card");
    await expect(question).toContainText("not a proven contradiction");
    await expect(question.getByTestId("unsupported-option").first()).toBeVisible();
    await expect(page.getByTestId("policy-rule-card")).toHaveCount(0);
    await expectNoAxeViolations(page, "Amira, stage 2, clarification");
    await page.screenshot({ path: "test-results/screens/amira-desktop-clarification.png", fullPage: true });
  });

  test("Robert and Mateo are unchanged after Amira is offered", async ({ page }) => {
    await page.goto(START_URL);
    await expect(page.getByTestId("persona-robert").getByTestId("persona-selected")).toBeVisible();
    await expect(page.getByTestId("portfolio-table")).toContainText("Robert’s fictional portfolio");
    await page.getByRole("button", { name: "Use Mateo’s portfolio" }).click();
    await expect(page.getByTestId("portfolio-table")).toContainText("Mateo’s fictional portfolio");
    await page.getByRole("button", { name: "Use Amira’s portfolio" }).click();
    await expect(page.getByTestId("portfolio-table")).toContainText("Amira’s fictional portfolio");
    await page.getByRole("button", { name: "Use Robert’s portfolio" }).click();
    await expect(page.getByTestId("portfolio-table")).toContainText("Robert’s fictional portfolio");
    await expectNoHorizontalOverflow(page, "desktop, three persona cards");
  });
});
