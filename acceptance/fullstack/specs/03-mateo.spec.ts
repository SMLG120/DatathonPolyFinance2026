import { expect, test } from "@playwright/test";
import { formatChange, formatFraction, formatFractionRange } from "../../../frontend/src/lib/format";
import { expectDrawerMatches, expectReportMatchesJob } from "./report";
import {
  choosePersona,
  confirmOfferedRules,
  engineCheck,
  expectNoTestDataMarkers,
  figureText,
  goToGoals,
  goToPurchase,
  mainAlert,
  openAllDetails,
  openApp,
  percentTokens,
  resetBackend,
  setPurchase,
  shot,
  Traffic,
  unexplainedFigures,
} from "./helpers";

/**
 * Mateo: a preference that needs a definition, and data that is missing. POST /rules/interpret is answered by this
 * backend with 502 INTERPRETER_FAILED (no interpreter is wired); the scenario's offered rules must stay confirmable.
 */
test.describe("Mateo, live against the local backend", () => {
  test.beforeEach(async () => {
    await resetBackend();
  });

  test("interpret -> 502 is readable and not a dead end; SPY to 15%: both exclusions FAIL from the starting portfolio, ranges, no largest-purchase number", async ({ page }) => {
    test.setTimeout(180_000);
    const traffic = new Traffic(page);
    await openApp(page);
    await choosePersona(page, "Mateo");
    const portfolio = (await traffic.last("GET", /^\/portfolios\/mateo$/)).body;
    for (const position of portfolio.scenario.portfolio.positions) {
      await expect(page.getByTestId("portfolio-row").filter({ hasText: position.instrument_id })).toContainText(formatFraction(position.weight));
    }

    // ---- "oil": the interpreter route answers 502 INTERPRETER_FAILED --------------------------------------------
    await goToGoals(page);
    await page.getByTestId("use-scenario-sentence").click();
    const words = page.getByLabel("What should the portfolio respect?");
    const typed = await words.inputValue();
    expect(typed).toMatch(/oil/);
    await page.getByRole("button", { name: "Interpret these words" }).click();
    const interpret = await traffic.last("POST", /^\/rules\/interpret$/);
    expect(interpret.status).toBe(502);
    expect(interpret.body.error.code).toBe("INTERPRETER_FAILED");
    expect(interpret.requestBody).toEqual({ persona_id: "mateo", text: typed, policy_id: null, policy_version: null });
    // What the user sees: the service's sentence, a retry, the text kept, and the offered rules still there.
    const alert = mainAlert(page).filter({ hasText: "Your words could not be read" });
    await expect(alert).toBeVisible();
    await expect(alert).toContainText(interpret.body.error.message);
    await expect(alert.getByRole("button", { name: "Try again" })).toBeVisible();
    await expect(words).toHaveValue(typed);
    await expect(page.getByTestId("interpretation")).toHaveCount(0);
    await expect(page.getByTestId("clarification-card")).toHaveCount(0);
    const offered = portfolio.scenario.scenario_rules;
    await expect(page.getByTestId("rule-card")).toHaveCount(offered.length);
    await shot(page, "10-mateo-interpret-502-readable-not-a-dead-end-live-local-backend-real-data", { fullPage: true });
    // A retry is answered the same way and still changes nothing.
    await alert.getByRole("button", { name: "Try again" }).click();
    await expect.poll(async () => (await traffic.find("POST", /^\/rules\/interpret$/)).length).toBe(2);
    await expect(alert).toBeVisible();

    // ---- The offered rules can be confirmed by hand ---------------------------------------------------------------
    await confirmOfferedRules(page);
    const confirm = await traffic.last("POST", /^\/rules\/confirm$/);
    expect(confirm.status).toBe(201);
    const v1 = confirm.body.policy;
    expect(v1.version).toBe(1);
    await expect(page.getByTestId("policy-rule-card")).toHaveCount(offered.length);

    // ---- SPY to 15% -----------------------------------------------------------------------------------------------
    await goToPurchase(page);
    await setPurchase(page, "SPY", "15");
    const preview = page.getByTestId("purchase-preview");
    await expect(preview.getByTestId("cash-after")).toBeVisible();
    const check = await traffic.last("POST", /^\/check$/, (call) => call.requestBody?.purchase_request?.instrument_id === "SPY" && call.status === 200);
    expect(check.requestBody.purchase_request.target_direct_weight).toBe(0.15);
    await expect(preview.getByTestId("cash-after")).toHaveText(formatFraction(check.body.feasibility.cash_after));
    await expect(preview.getByTestId("additional-purchase")).toHaveText(formatChange(check.body.feasibility.additional_purchase));
    expect(check.body).toEqual(
      await engineCheck({ persona_id: "mateo", policy: check.requestBody.policy_id ? v1 : null, purchase_request: check.requestBody.purchase_request, draft_rules: check.requestBody.draft_rules }),
    );

    await page.getByTestId("start-investigation").click();
    await page.getByTestId("see-verdict").click({ timeout: 60_000 });
    await expect(page.getByTestId("report")).toBeVisible();
    const created = await traffic.last("POST", /^\/investigations$/);
    const job = (await traffic.last("GET", /^\/investigations\/inv-[0-9a-f]+$/, (call) => call.body?.id === created.body.id && call.body?.status === "SUCCEEDED")).body;
    const result = job.result;

    // Both exclusion rules fail, and they already failed before any purchase.
    expect(offered.map((rule: any) => rule.rule_type)).toEqual(["exclusion", "controversy_exclusion"]);
    expect(result.rule_results.map((rule: any) => [rule.rule_type, rule.status, rule.starting.status])).toEqual(offered.map((rule: any) => [rule.rule_type, "FAIL", "FAIL"]));
    expect(result.summary.starting_portfolio_breaches).toBe(2);
    expect(result, "the investigation result equals backend.engine.check_rules on the same inputs").toEqual(
      await engineCheck({ persona_id: "mateo", policy: v1, purchase_request: job.resolved_request }),
    );
    await openAllDetails(page);
    await expectReportMatchesJob(page, job);

    // What is not known is printed as a range, never as one number and never as a pass.
    for (const rule of result.rule_results) {
      expect(rule.measured.upper, `${rule.rule_id} is a range in the API`).toBeGreaterThan(rule.measured.lower);
      const card = page.locator(`[data-testid="rule-result"][data-rule-id="${rule.rule_id}"]`);
      await expect(card.getByTestId("rule-measured")).toHaveText(formatFractionRange(rule.measured.lower, rule.measured.upper));
      await expect(card.getByTestId("rule-measured")).toContainText(" to ");
      await expect(card.getByTestId("unknown-causes")).toBeVisible();
      expect(rule.unknown_causes.length).toBeGreaterThan(0);
    }
    // The starting-portfolio findings are listed apart from the effect of the purchase.
    await expect(page.getByTestId("starting-finding")).toHaveCount(result.starting_portfolio_findings.length);
    expect(result.starting_portfolio_findings.length).toBe(2);
    await expect(page.getByTestId("starting-breaches")).toContainText("already not respected");

    // No "largest compliant purchase" figure.
    expect(result.max_compliant.status).not.toBe("SUPPORTED");
    expect(result.max_compliant.final_direct_weight).toBeNull();
    const maxBlock = page.getByTestId("max-compliant");
    await expect(maxBlock).toHaveAttribute("data-status", result.max_compliant.status);
    await expect(page.getByTestId("max-final-weight")).toHaveCount(0);
    await expect(page.getByTestId("max-additional")).toHaveCount(0);
    expect(percentTokens(await maxBlock.innerText()), "no percentage inside the largest-purchase block").toEqual([]);

    const reportText = await figureText(page.getByTestId("report"));
    expect(percentTokens(reportText).length).toBeGreaterThan(40);
    expect(unexplainedFigures(reportText, [job, v1]), "figures printed in the report that the API response does not contain").toEqual([]);
    await expectNoTestDataMarkers(page, "Mateo, stage 5");
    await shot(page, "11-mateo-verdict-exclusions-fail-from-start-ranges-live-local-backend-real-data", { fullPage: true });

    // Evidence of the first rule.
    const first = result.rule_results[0];
    await page.locator(`[data-testid="rule-result"][data-rule-id="${first.rule_id}"]`).getByRole("button", { name: /^Evidence for / }).click();
    const drawer = page.getByRole("dialog");
    await expect(drawer).toBeVisible();
    await expectDrawerMatches(drawer, result);
    expect(unexplainedFigures(await figureText(drawer), [job])).toEqual([]);
    await page.keyboard.press("Escape");

    await traffic.expectClean();
  });

  test("limits inside the possible range: both rules are UNKNOWN, shown as unknown with their ranges, and the largest purchase is withheld", async ({ page }) => {
    test.setTimeout(180_000);
    const traffic = new Traffic(page);
    await openApp(page);
    await choosePersona(page, "Mateo");
    await goToGoals(page);
    // The user's own numbers instead of the scenario's zero tolerance.
    const cards = page.getByTestId("rule-card");
    await cards.nth(0).getByRole("textbox").fill("10");
    await cards.nth(1).getByRole("textbox").fill("5");
    await expect(cards.nth(0).getByTestId("draft-preview-result")).toContainText("Preview:");
    const draft = await traffic.last("POST", /^\/check$/, (call) => Array.isArray(call.requestBody?.draft_rules) && call.status === 200);
    expect(draft.body.preview).toBe(true);
    expect(draft.body.policy_version).toBeNull();
    await confirmOfferedRules(page);
    const v1 = (await traffic.last("POST", /^\/rules\/confirm$/)).body.policy;
    expect(v1.rules.map((rule: any) => [rule.threshold, rule.origin, rule.threshold_source])).toEqual([
      [0.1, "USER_STATED", "USER_ENTERED"],
      [0.05, "USER_STATED", "USER_ENTERED"],
    ]);
    await goToPurchase(page);
    await setPurchase(page, "SPY", "15");
    await expect(page.getByTestId("purchase-preview").getByTestId("cash-after")).toBeVisible();
    await page.getByTestId("start-investigation").click();
    await page.getByTestId("see-verdict").click({ timeout: 60_000 });
    await expect(page.getByTestId("report")).toBeVisible();
    const job = (await traffic.last("GET", /^\/investigations\/inv-[0-9a-f]+$/, (call) => call.body?.status === "SUCCEEDED")).body;
    const result = job.result;
    expect(result.rule_results.map((rule: any) => rule.status)).toEqual(["UNKNOWN", "UNKNOWN"]);
    expect(result.rule_results.map((rule: any) => rule.gap)).toEqual([null, null]);
    expect(result.summary.counts).toEqual({ pass: 0, fail: 0, unknown: 2 });
    await openAllDetails(page);
    await expectReportMatchesJob(page, job);
    await expect(page.getByTestId("count-unknown")).toHaveAttribute("data-count", "2");
    await expect(page.getByTestId("count-pass")).toHaveAttribute("data-count", "0");
    await expect(page.getByTestId("verdict-headline")).not.toContainText(/respected$/);
    for (const rule of result.rule_results) {
      const card = page.locator(`[data-testid="rule-result"][data-rule-id="${rule.rule_id}"]`);
      await expect(card).toHaveAttribute("data-status", "UNKNOWN");
      await expect(card.getByTestId("rule-measured")).toContainText(" to ");
      await expect(card.getByTestId("rule-gap")).toHaveText("Cannot be determined");
      await expect(card.getByTestId("unknown-note")).toBeVisible();
    }
    expect(result.max_compliant.status).toBe("WITHHELD");
    await expect(page.getByTestId("max-compliant")).toHaveAttribute("data-status", "WITHHELD");
    await expect(page.getByTestId("max-final-weight")).toHaveCount(0);
    expect(unexplainedFigures(await figureText(page.getByTestId("report")), [job, v1])).toEqual([]);
    await shot(page, "12-mateo-verdict-unknown-as-ranges-live-local-backend-real-data");
  });

  test("challenge 'clarify a preference' is answered 502 INTERPRETER_FAILED: what the page does", async ({ page }) => {
    test.setTimeout(180_000);
    const traffic = new Traffic(page);
    await openApp(page);
    await choosePersona(page, "Mateo");
    await goToGoals(page);
    await confirmOfferedRules(page);
    await goToPurchase(page);
    await expect(page.getByTestId("purchase-preview").getByTestId("cash-after")).toBeVisible();
    await page.getByTestId("start-investigation").click();
    await page.getByTestId("see-verdict").click({ timeout: 60_000 });
    await page.getByRole("link", { name: "Challenge this result" }).click();
    await page.getByRole("tab", { name: "Clarify a preference" }).click();
    const form = page.getByTestId("clarify-preference-form");
    await expect(form).toBeVisible();
    await page.getByRole("button", { name: /^Fill in the scenario's example/ }).click();
    await expect(form.getByLabel("What did you mean?")).not.toHaveValue("");
    await page.getByTestId("submit-preference").click();
    const challenge = await traffic.last("POST", /\/challenge$/);
    expect(challenge.status).toBe(502);
    expect(challenge.body.error.code).toBe("INTERPRETER_FAILED");
    expect(challenge.requestBody.type).toBe("CLARIFY_PREFERENCE");
    expect(challenge.requestHeaders["idempotency-key"], "only a rule change carries a key").toBeUndefined();
    const alert = mainAlert(page).filter({ hasText: challenge.body.error.message });
    await expect(alert).toBeVisible();
    await expect(page.getByTestId("preference-response")).toHaveCount(0);
    // Not a dead end: the form is still there, and so is the report.
    await expect(page.getByTestId("submit-preference")).toBeEnabled();
    await expect(form.getByLabel("What did you mean?")).not.toHaveValue("");
    await page.getByRole("link", { name: "Step 5 of 6: Verdict & evidence" }).click();
    await expect(page.getByTestId("report")).toBeVisible();
  });
});
