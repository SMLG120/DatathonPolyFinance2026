import { expect, test } from "@playwright/test";
import { expectNoAxeViolations, expectNoHorizontalOverflow, expectPersistentLabels, expectStage, START_URL } from "./helpers";

/** Runs in the mobile project only: 390 x 844, touch. */
test.describe("mobile viewport", () => {
  test("390 x 844: every stage fits the width, keeps its labels and passes axe", async ({ page }) => {
    expect(page.viewportSize()).toEqual({ width: 390, height: 844 });
    await page.goto(START_URL);
    await expect(page.getByTestId("portfolio-table")).toBeVisible();
    await expectPersistentLabels(page);
    await expectNoHorizontalOverflow(page, "stage 1");
    await expectNoAxeViolations(page, "mobile, stage 1");

    await page.getByRole("link", { name: "Continue to Goals & rules" }).tap();
    await expectStage(page, 2);
    await page.getByTestId("propose-rules").tap();
    await expect(page.getByTestId("rule-card")).toHaveCount(2);
    await expectNoHorizontalOverflow(page, "stage 2, proposed rules");
    await expectNoAxeViolations(page, "mobile, stage 2");
    await page.getByTestId("confirm-all").tap();
    await expect(page.getByTestId("policy-rule-card")).toHaveCount(2);
    await expectNoHorizontalOverflow(page, "stage 2, confirmed policy");

    await page.getByRole("link", { name: "Continue to Proposed purchase" }).tap();
    await expectStage(page, 3);
    await expectPersistentLabels(page);
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
    await expectNoHorizontalOverflow(page, "stage 5");
    await expectNoAxeViolations(page, "mobile, stage 5");

    // The drawer fills the width and nothing spills out of it.
    await page.getByRole("button", { name: "Evidence for Maximum exposure to a single company, after the purchase" }).tap();
    await expect(page.getByRole("dialog")).toBeVisible();
    await expectNoHorizontalOverflow(page, "stage 5, evidence drawer");
    await page.getByRole("button", { name: "Close evidence" }).tap();
    await expect(page.getByRole("dialog")).toBeHidden();

    await page.getByRole("link", { name: "Challenge this result" }).tap();
    await expectStage(page, 6);
    await expectNoHorizontalOverflow(page, "stage 6, correct a fact");
    await page.getByRole("tab", { name: "Change a rule" }).tap();
    await page.getByTestId("change-rule-form").getByRole("textbox").fill("30");
    await expect(page.getByTestId("change-rule-form").getByTestId("draft-preview-result")).toBeVisible();
    await page.getByTestId("submit-rule-change").tap();
    await expect(page.getByTestId("result-comparison")).toBeVisible({ timeout: 30_000 });
    await expectPersistentLabels(page);
    await expectNoHorizontalOverflow(page, "stage 6, comparison");
    await expectNoAxeViolations(page, "mobile, stage 6");
  });

  test("360 px wide: the narrowest supported width still has no sideways scroll", async ({ page }) => {
    await page.setViewportSize({ width: 360, height: 740 });
    await page.goto(START_URL);
    await expect(page.getByTestId("portfolio-table")).toBeVisible();
    await expectNoHorizontalOverflow(page, "360px, stage 1");

    await page.getByRole("link", { name: "Continue to Goals & rules" }).tap();
    await page.getByTestId("propose-rules").tap();
    await expect(page.getByTestId("rule-card")).toHaveCount(2);
    await expectNoHorizontalOverflow(page, "360px, stage 2");
    await page.getByTestId("confirm-all").tap();
    await page.getByRole("link", { name: "Continue to Proposed purchase" }).tap();
    await expectNoHorizontalOverflow(page, "360px, stage 3");
    await page.getByTestId("start-investigation").tap();
    await page.getByTestId("see-verdict").tap({ timeout: 30_000 });
    await expect(page.getByTestId("report")).toBeVisible();
    await expectNoHorizontalOverflow(page, "360px, stage 5");
    await page.getByRole("link", { name: "Challenge this result" }).tap();
    await expectStage(page, 6);
    await expectNoHorizontalOverflow(page, "360px, stage 6");
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
