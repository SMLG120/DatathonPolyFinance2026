import { expect, test } from "@playwright/test";
import { expectNoAxeViolations, expectPersistentLabels, expectStage, expectVisibleFocusRing, stageHeading, START_URL, tabTo, tabToAndPress } from "./helpers";

/**
 * The whole simulation, driven with the keyboard only (Tab, Shift+Tab, Enter,
 * arrows, Escape, typing) on the static build in fixtures mode. No mouse
 * action is used anywhere in this file.
 */
test.describe("keyboard-only journey through the six stages", () => {
  test("Robert: persona to challenge, with axe on every stage", async ({ page }) => {
    await page.goto(START_URL);
    await expect(page.getByTestId("portfolio-table")).toBeVisible();

    // ---- Stage 1: focus order follows the reading order --------------------
    await expectStage(page, 1, { focused: false });
    await expectPersistentLabels(page);
    const expectedOrder = [
      page.getByRole("link", { name: "Skip to main content" }),
      page.getByRole("link", { name: "Step 1 of 6: Persona & portfolio" }),
      page.getByRole("link", { name: "Step 2 of 6: Goals & rules" }),
      page.getByRole("link", { name: "Step 3 of 6: Proposed purchase" }),
      page.getByRole("link", { name: "Step 4 of 6: Investigation steps" }),
      page.getByRole("link", { name: "Step 5 of 6: Verdict & evidence" }),
      page.getByRole("link", { name: "Step 6 of 6: Challenge" }),
      page.getByRole("button", { name: "Use Mateo’s portfolio" }),
      page.getByRole("link", { name: "Continue to Goals & rules" }),
    ];
    for (const control of expectedOrder) {
      await page.keyboard.press("Tab");
      await expect(control).toBeFocused();
      await expectVisibleFocusRing(control);
    }
    await expectNoAxeViolations(page, "stage 1, persona and portfolio");

    // The skip link is the first stop and moves focus to the main region.
    await page.goto(START_URL);
    await expect(page.getByTestId("portfolio-table")).toBeVisible();
    await page.keyboard.press("Tab");
    await expect(page.getByRole("link", { name: "Skip to main content" })).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(page.locator("#main-content")).toBeFocused();
    await expect(page).toHaveURL(/\?fixtures=1$/); // the skip link does not disturb the stage in the hash

    // ---- Stage 2: goal -> proposed rules -> explicit confirmation ----------
    await tabToAndPress(page, page.getByRole("link", { name: "Continue to Goals & rules" }));
    await expectStage(page, 2);
    await expectPersistentLabels(page);
    await expect(page).toHaveTitle("Goals & rules — Before You Buy — fictional simulation");

    await tabToAndPress(page, page.getByRole("button", { name: "Propose rules from this text" }));
    await expect(page.getByTestId("rule-card")).toHaveCount(2);
    await expect(page.getByTestId("rule-card").first().getByText("Proposed — inactive")).toBeVisible();
    await expectNoAxeViolations(page, "stage 2, proposed rules");

    // A threshold can be changed from the keyboard, and the preview is labelled as a preview.
    const firstCard = page.getByTestId("rule-card").first();
    const slider = firstCard.getByRole("slider");
    await tabTo(page, slider);
    await expectVisibleFocusRing(slider);
    await page.keyboard.press("ArrowRight");
    await expect(firstCard.getByRole("textbox")).toHaveValue("10.5");
    await expect(firstCard.getByTestId("draft-preview-result")).toContainText("Preview:");
    await expect(firstCard.getByTestId("draft-preview")).toContainText("Preview with draft threshold — not your confirmed policy");
    await page.keyboard.press("ArrowLeft");
    await expect(firstCard.getByRole("textbox")).toHaveValue("10");

    await tabToAndPress(page, page.getByTestId("confirm-all"));
    await expect(page.getByTestId("policy-rule-card")).toHaveCount(2);
    // The confirmed card took the place of the button that had focus: focus goes to the policy.
    await expect(page.getByRole("heading", { name: "Confirmed policy — version 1" })).toBeFocused();
    await expectNoAxeViolations(page, "stage 2, confirmed policy");

    // ---- Stage 3: the purchase as a final direct weight --------------------
    await tabToAndPress(page, page.getByRole("link", { name: "Continue to Proposed purchase" }));
    await expectStage(page, 3);
    await expectPersistentLabels(page);
    await expect(page.getByTestId("funding-statement")).toHaveText("Funded from existing cash; all other positions unchanged; fees and taxes excluded.");
    await expect(page.getByLabel("Final direct weight of this position")).toHaveValue("25");
    await expect(page.getByTestId("cash-after")).toHaveText("5.0%");
    await expect(page.getByTestId("before-after-table")).toBeVisible();
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
    expect(totalSteps).toBeGreaterThan(0);
    expect(stepsSeen[0], "every step was on screen before the job had reported it").toBeLessThan(totalSteps);
    expect(stepsSeen, "a step that had been shown went away").toEqual([...stepsSeen].sort((a, b) => a - b));
    await expect(page.locator('[data-testid="timeline-step"]:not([data-step-status="OK"])')).toHaveCount(0);
    await expect(page.getByTestId("step-count")).toHaveText(String(totalSteps));
    await expect(page.getByTestId("timeline-waiting")).toHaveCount(0);
    await expectNoAxeViolations(page, "stage 4, investigation steps");

    // ---- Stage 5: verdict and evidence -------------------------------------
    await tabToAndPress(page, page.getByTestId("see-verdict"));
    await expectStage(page, 5);
    await expectPersistentLabels(page);
    await expect(page.getByTestId("verdict-headline")).toHaveText("2 of 2 confirmed rules are not respected");
    await expect(page.getByTestId("count-fail")).toHaveAttribute("data-count", "2");
    await expect(page.getByTestId("count-unknown")).toHaveAttribute("data-count", "0");
    await expect(page.getByTestId("exposure-chart")).toBeVisible();
    await expect(page.getByTestId("scenario-note")).toBeVisible();
    await expectNoAxeViolations(page, "stage 5, verdict and evidence");

    // Evidence drawer: opens from a figure, traps focus, closes on Escape, returns focus.
    const evidenceButton = page.getByRole("button", { name: "Evidence for Maximum exposure to a single company, after the purchase" });
    await tabTo(page, evidenceButton);
    await expectVisibleFocusRing(evidenceButton);
    await page.keyboard.press("Enter");
    const drawer = page.getByRole("dialog");
    await expect(drawer).toBeVisible();
    await expect(drawer).toHaveAccessibleName(/^Evidence: Maximum exposure to a single company/);
    await expect(drawer.getByRole("heading", { name: "Calculation path" }).first()).toBeVisible();
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
    await tabToAndPress(page, page.getByRole("link", { name: "Challenge this result" }));
    await expectStage(page, 6);
    await expectPersistentLabels(page);
    await expectNoAxeViolations(page, "stage 6, correct a fact");

    // Tabs: one tab stop, arrow keys move between the three paths.
    await tabTo(page, page.getByRole("tab", { name: "Correct a fact" }));
    await expectVisibleFocusRing(page.getByRole("tab", { name: "Correct a fact" }));
    await page.keyboard.press("ArrowRight");
    await expect(page.getByRole("tab", { name: "Clarify a preference" })).toBeFocused();
    await expect(page.getByRole("tab", { name: "Clarify a preference" })).toHaveAttribute("aria-selected", "true");
    await expectNoAxeViolations(page, "stage 6, clarify a preference");
    await page.keyboard.press("ArrowRight");
    await expect(page.getByRole("tab", { name: "Change a rule" })).toBeFocused();
    await expect(page.getByTestId("change-rule-form")).toBeVisible();

    const newValue = page.getByTestId("change-rule-form").getByRole("textbox");
    await tabTo(page, newValue);
    await expectVisibleFocusRing(newValue);
    await page.keyboard.type("30");
    await expect(page.getByTestId("change-rule-form").getByTestId("draft-preview-result")).toContainText("Preview: Pass");
    await expectNoAxeViolations(page, "stage 6, change a rule with a preview");

    await tabToAndPress(page, page.getByTestId("submit-rule-change"));
    await expect(page.getByRole("heading", { name: "Before and after your rule change" })).toBeFocused();
    const changedRows = page.locator('[data-testid="policy-diff-row"][data-change="CHANGED"]');
    await expect(changedRows).toHaveCount(1);
    await expect(changedRows).toContainText("10.0%");
    await expect(changedRows).toContainText("30.0%");
    await expect(page.locator('[data-testid="policy-diff-row"][data-change="UNCHANGED"]')).toHaveCount(1);
    await expect(page.getByTestId("result-comparison")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId("comparison-headline")).toHaveText(["2 of 2 confirmed rules are not respected", "1 of 2 confirmed rules is not respected"]);
    await expectNoAxeViolations(page, "stage 6, old and new compared");

    // The earlier report can still be opened, and is unchanged.
    await tabToAndPress(page, page.getByTestId("comparison-report").first().getByRole("button", { name: "Open this report" }));
    await expectStage(page, 5);
    await expect(page.getByText("You are reading an earlier report, checked against policy version 1")).toBeVisible();
    await expect(page.getByTestId("verdict-headline")).toHaveText("2 of 2 confirmed rules are not respected");
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
