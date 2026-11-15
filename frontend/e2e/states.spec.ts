import { expect, test, type Page } from "@playwright/test";
import { expectNoAxeViolations, expectPersistentLabels, expectStage, START_URL } from "./helpers";

/**
 * An error block inside the page content. Next.js adds its own empty
 * `role="alert"` route announcer to every page, so a bare role query is
 * ambiguous; the application's alerts all live inside <main>.
 */
function mainAlert(page: Page) {
  return page.getByRole("main").getByRole("alert");
}

async function confirmScenarioRules(page: Page) {
  await page.getByRole("link", { name: "Continue to Goals & rules" }).click();
  await page.getByTestId("propose-rules").click();
  await expect(page.getByTestId("rule-card").first()).toBeVisible();
  await page.getByTestId("confirm-all").click();
  await expect(page.getByTestId("policy-rule-card").first()).toBeVisible();
}

test.describe("states other than the happy path", () => {
  test("Mateo: a question instead of a guessed rule, empty thresholds, and unknown shown as unknown", async ({ page }) => {
    await page.goto(START_URL);
    await expect(page.getByTestId("portfolio-table")).toBeVisible();
    await page.getByRole("button", { name: "Use Mateo’s portfolio" }).click();
    await expect(page.getByTestId("portfolio-table")).toContainText("Mateo’s fictional portfolio");

    await page.getByRole("link", { name: "Continue to Goals & rules" }).click();
    await page.getByTestId("propose-rules").click();
    const question = page.getByTestId("clarification-card");
    await expect(question).toBeVisible();
    await expect(page.getByTestId("rule-card")).toHaveCount(1);
    await expect(page.getByTestId("rule-card").getByRole("textbox")).toHaveValue("");
    await expect(page.getByTestId("rule-card").getByRole("slider")).toHaveAttribute("aria-valuetext", "Not set");
    await expect(page.getByTestId("rule-card").getByTestId("confirm-rule")).toHaveAttribute("aria-disabled", "true");
    await expectNoAxeViolations(page, "Mateo, clarification question and an empty threshold");

    await question.getByRole("radio").first().check();
    await question.getByRole("button", { name: "Use this definition" }).click();
    await expect(page.getByTestId("rule-card")).toHaveCount(2);
    for (const card of await page.getByTestId("rule-card").all()) {
      await expect(card.getByRole("textbox")).toHaveValue("");
      await card.getByRole("textbox").fill("0");
    }
    await page.getByTestId("confirm-all").click();
    await expect(page.getByTestId("policy-rule-card")).toHaveCount(2);

    await page.getByRole("link", { name: "Continue to Proposed purchase" }).click();
    await page.getByTestId("start-investigation").click();
    await page.getByTestId("see-verdict").click({ timeout: 30_000 });
    await expectStage(page, 5);

    const report = page.getByTestId("report");
    await expect(report.getByTestId("verdict-summary")).not.toHaveAttribute("data-tone", "pass");
    await expect(report.getByTestId("count-unknown")).not.toHaveAttribute("data-count", "0");
    await expect(report.getByTestId("verdict-headline")).not.toHaveText(/^All \d+ confirmed rules are respected$/);
    await expect(report.locator('[data-testid="rule-result"][data-status="UNKNOWN"]').first()).toContainText("Unknown is not a pass.");
    await expect(report.locator('[data-seg="possible"]').first()).toBeVisible();
    await expect(report.getByTestId("max-compliant")).not.toHaveAttribute("data-status", "SUPPORTED");
    await expectPersistentLabels(page);
    await expectNoAxeViolations(page, "Mateo, verdict with unknowns and a possible range");
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
    await expect(page.getByTestId("portfolio-table")).toBeVisible();
    await confirmScenarioRules(page);
    await page.getByRole("link", { name: "Continue to Proposed purchase" }).click();
    await page.getByTestId("start-investigation").click();
    await expect(mainAlert(page)).toContainText("The investigation failed", { timeout: 30_000 });
    await expect(page.getByTestId("see-verdict")).toHaveCount(0);
    await expectNoAxeViolations(page, "investigation failed");

    await page.getByRole("link", { name: "Continue to Verdict & evidence" }).click();
    await expect(mainAlert(page)).toContainText("This investigation failed, so there is no verdict");
    await expect(page.getByTestId("report")).toHaveCount(0);
  });

  test("polling stops at its deadline with a visible failure and a way to keep waiting", async ({ page }) => {
    await page.goto("/?fixtures=1&simulate=poll-timeout");
    await expect(page.getByTestId("portfolio-table")).toBeVisible();
    await confirmScenarioRules(page);
    await page.getByRole("link", { name: "Continue to Proposed purchase" }).click();
    await page.getByTestId("start-investigation").click();
    await expect(page.getByTestId("timeline-waiting")).toBeVisible();

    const alert = mainAlert(page);
    await expect(alert).toContainText("No final answer within 4 seconds", { timeout: 30_000 });
    await expect(alert).toContainText("No verdict is shown, because none was received.");
    await expect(page.getByTestId("timeline-waiting")).toHaveCount(0);
    await expect(page.getByTestId("see-verdict")).toHaveCount(0);
    await expectNoAxeViolations(page, "polling deadline reached");

    // "Keep waiting" starts a fresh poll with a fresh deadline.
    await alert.getByRole("button", { name: "Keep waiting" }).click();
    await expect(page.getByTestId("timeline-waiting")).toBeVisible();
  });

  test("a preview that fails says so and leaves the proposed rule untouched", async ({ page }) => {
    await page.goto("/?fixtures=1&simulate=check-error");
    await expect(page.getByTestId("portfolio-table")).toBeVisible();
    await page.getByRole("link", { name: "Continue to Goals & rules" }).click();
    await page.getByTestId("propose-rules").click();
    const card = page.getByTestId("rule-card").first();
    await card.getByRole("textbox").fill("12");
    await expect(card.getByTestId("draft-preview-error")).toContainText("The preview could not be calculated.");
    await expect(card.getByText("Proposed — inactive")).toBeVisible();
    await expectNoAxeViolations(page, "preview failed");
  });
});
