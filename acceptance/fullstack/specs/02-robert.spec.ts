import { expect, test, type Locator, type Page } from "@playwright/test";
import { formatEvidenceValue } from "../../../frontend/src/lib/evidence";
import { formatChange, formatCoverage, formatDate, formatDateTime, formatFraction, formatFractionRange, formatGap, formatReturn } from "../../../frontend/src/lib/format";
import { limitNoun, ruleDirection } from "../../../frontend/src/lib/rules";
import { coverageText, verdictHeadline } from "../../../frontend/src/lib/verdict";
import {
  api,
  choosePersona,
  confirmOfferedRules,
  engineCheck,
  expectNoTestDataMarkers,
  figureText,
  goToGoals,
  goToPurchase,
  openAllDetails,
  percentTokens,
  openApp,
  resetBackend,
  serverLog,
  setPurchase,
  shot,
  Traffic,
  unexplainedFigures,
} from "./helpers";

/**
 * Robert, the complete demonstration, in a real browser against the real handlers on the real data snapshot.
 * Every expected figure is read from the API response the page received and formatted with the frontend's own
 * formatters (`frontend/src/lib/format.ts`); the API responses are compared with `backend.engine.check_rules`
 * run directly on the same inputs. No figure is typed in here.
 */

const measureDecimals = (ruleType: string) => (ruleType === "scenario_loss_budget" ? 2 : 1);

const startingText = (rule: any) => formatFractionRange(rule.starting.measured.lower, rule.starting.measured.upper, { decimals: measureDecimals(rule.rule_type) }).toLowerCase();

/** The figures of every rule card of the report equal the formatted values of `result.rule_results`. */
export async function expectRuleCards(page: Page, result: any) {
  await expect(page.getByTestId("rule-result")).toHaveCount(result.rule_results.length);
  for (const rule of result.rule_results) {
    const card = page.locator(`[data-testid="rule-result"][data-rule-id="${rule.rule_id}"]`);
    await expect(card, `rule card ${rule.rule_id}`).toHaveAttribute("data-status", rule.status);
    const decimals = measureDecimals(rule.rule_type);
    if (rule.measured) {
      await expect(card.getByTestId("rule-measured")).toHaveText(formatFractionRange(rule.measured.lower, rule.measured.upper, { decimals }));
    }
    await expect(card.getByTestId("rule-limit")).toHaveText(formatFraction(rule.limit));
    const noun = limitNoun(rule.rule_type);
    await expect(card.getByTestId("rule-gap")).toHaveText(formatGap(rule.gap, ruleDirection(rule.rule_type), noun.toLowerCase(), decimals));
    await expect(card.getByTestId("rule-reason")).toContainText(rule.reason);
    if (rule.starting?.measured) {
      await expect(card.getByTestId("rule-starting")).toHaveAttribute("data-starting-status", rule.starting.status);
      await expect(card.getByTestId("rule-starting")).toContainText(startingText(rule));
    }
  }
}

/** Headline, counts, feasibility, replay, largest compliant purchase, coverage and the "about" block against the job. */
export async function expectReportMatchesJob(page: Page, job: any) {
  const result = job.result;
  const report = page.getByTestId("report");
  await expect(report).toHaveAttribute("data-job-id", job.id);
  await expect(page.getByTestId("verdict-headline")).toHaveText(verdictHeadline(result.summary).title);
  for (const kind of ["fail", "unknown", "pass"] as const) {
    await expect(page.getByTestId(`count-${kind}`)).toHaveAttribute("data-count", String(result.summary.counts[kind]));
  }
  await expectRuleCards(page, result);

  // Feasibility: reported separately from the rules.
  const feasibility = page.getByTestId("feasibility");
  await expect(feasibility).toHaveAttribute("data-feasibility", result.feasibility.status);
  await expect(feasibility).toContainText(formatFraction(result.feasibility.cash_before));
  await expect(feasibility).toContainText(formatFraction(result.feasibility.cash_after));
  const cashPanel = page.locator("#report-cash");
  await expect(cashPanel.getByTestId("cash-after")).toHaveText(formatFraction(result.feasibility.cash_after));
  await expect(cashPanel.getByTestId("additional-purchase")).toHaveText(formatChange(result.feasibility.additional_purchase));
  await expect(page.getByTestId("starting-breaches")).toHaveAttribute("data-count", String(result.summary.starting_portfolio_breaches));

  // Historical replay.
  const scenario = result.scenario;
  if (scenario) {
    await expect(page.getByTestId("scenario-note")).toContainText(formatDate(scenario.base_date));
    await expect(page.getByTestId("scenario-note")).toContainText(formatDate(scenario.end_date));
    const cells = (testId: string) => page.getByTestId(testId).locator("td");
    if (scenario.starting && scenario.proposed) {
      await expect(cells("scenario-terminal")).toHaveText([formatReturn(scenario.starting.scenario_terminal_return), formatReturn(scenario.proposed.scenario_terminal_return)]);
      await expect(cells("scenario-drawdown")).toHaveText([formatReturn(scenario.starting.scenario_max_drawdown), formatReturn(scenario.proposed.scenario_max_drawdown)]);
      await expect(cells("scenario-drawdown-date")).toHaveText([formatDate(scenario.starting.max_drawdown_date), formatDate(scenario.proposed.max_drawdown_date)]);
    }
    if (scenario.target_instrument_return !== null && scenario.target_instrument_return !== undefined) {
      await expect(page.getByTestId("scenario-target-return")).toContainText(formatReturn(scenario.target_instrument_return));
    }
  }

  // Largest compliant purchase.
  const max = result.max_compliant;
  const maxBlock = page.getByTestId("max-compliant");
  if (max?.status === "SUPPORTED") {
    await expect(maxBlock).toHaveAttribute("data-status", "SUPPORTED");
    await expect(page.getByTestId("max-final-weight")).toHaveText(formatFraction(max.final_direct_weight, { rounding: "down" }));
    await expect(page.getByTestId("max-additional")).toHaveText(formatFraction(max.additional_purchase, { rounding: "down" }));
    await expect(page.getByTestId("max-reason")).toContainText(max.reason);
  } else if (max) {
    await expect(maxBlock).toHaveAttribute("data-status", max.status);
    await expect(page.getByTestId("max-final-weight")).toHaveCount(0);
    await expect(page.getByTestId("max-additional")).toHaveCount(0);
  }

  // Data coverage, one card per fund.
  for (const fund of result.data_coverage?.funds ?? []) {
    const card = page.locator(`[data-testid="fund-coverage"][data-fund-id="${fund.fund_id}"]`);
    await expect(card).toHaveAttribute("data-coverage-status", fund.status);
    if (fund.status === "PARTIAL" || fund.status === "COMPLETE") {
      await expect(card.getByTestId("coverage-sentence")).toHaveText(`${coverageText(fund.status)} — ${formatCoverage(fund.coverage_fraction)} of the fund reported`);
    }
    await expect(card).toContainText(formatFraction(fund.portfolio_weight));
  }

  // Versions and dates.
  const about = page.locator("#report-about");
  await expect(about).toContainText(`Version ${result.policy_version}`);
  await expect(about).toContainText(result.policy_id);
  await expect(about).toContainText(formatDate(result.valuation_date));
  await expect(about).toContainText(result.calculation_version);
  await expect(about).toContainText(job.id);
  await expect(about).toContainText(formatDateTime(job.updated_at));
  await expect(page.getByTestId("valuation-date")).toHaveText(`Valuation date: ${formatDate(result.valuation_date)}`);
}

/** Every record of the open evidence drawer shows the formatted value, version and id of the API's record. */
export async function expectDrawerMatches(drawer: Locator, result: any) {
  const records = drawer.getByTestId("evidence-record");
  const count = await records.count();
  expect(count, "the drawer lists at least one record").toBeGreaterThan(0);
  for (let index = 0; index < count; index += 1) {
    const element = records.nth(index);
    const id = await element.getAttribute("data-evidence-id");
    const record = result.evidence.find((candidate: any) => candidate.evidence_id === id);
    expect(record, `evidence record ${id} exists in result.evidence`).toBeTruthy();
    await expect(element.getByTestId("evidence-value"), `value of ${id}`).toHaveText(formatEvidenceValue(record));
    await expect(element, `calculation version of ${id}`).toContainText(result.calculation_version);
    if (record.policy_version !== null && record.policy_version !== undefined) await expect(element).toContainText(`Version ${record.policy_version}`);
    if (record.calculation?.formula) await expect(element.getByTestId("evidence-formula")).toHaveText(record.calculation.formula);
  }
  return count;
}

test.describe("Robert: the complete demonstration, live against the local backend", () => {
  test.beforeEach(async () => {
    await resetBackend();
  });

  test("persona -> rules v1 -> NVDA 25% -> preview -> investigation -> verdict -> evidence -> challenge to 30% -> v2 -> comparison -> v1 report still there", async ({ page }) => {
    test.setTimeout(240_000);
    const traffic = new Traffic(page);
    await openApp(page);
    await choosePersona(page, "Robert");
    await expectNoTestDataMarkers(page, "stage 1");

    // ---- Stage 1: the portfolio table shows the API's weights -------------------------------------------------
    const portfolio = (await traffic.last("GET", /^\/portfolios\/robert$/)).body;
    const positions = portfolio.scenario.portfolio.positions;
    await expect(page.getByTestId("portfolio-row")).toHaveCount(positions.length + 1); // + the cash row
    for (const position of positions) {
      const row = page.getByTestId("portfolio-row").filter({ hasText: position.instrument_id });
      await expect(row).toContainText(formatFraction(position.weight));
    }
    await expect(page.getByTestId("portfolio-row").last()).toContainText(formatFraction(portfolio.scenario.portfolio.cash_weight));
    await shot(page, "01-robert-portfolio-live-local-backend");

    // ---- Stage 2: the offered rules are inactive until confirmed -> policy version 1 ---------------------------
    await goToGoals(page);
    const offered = portfolio.scenario.scenario_rules;
    await expect(page.getByTestId("rule-card")).toHaveCount(offered.length);
    expect((await traffic.find("POST", /^\/rules\/confirm$/)).length, "nothing is confirmed before the user confirms").toBe(0);
    await confirmOfferedRules(page);
    const confirm = await traffic.last("POST", /^\/rules\/confirm$/);
    expect(confirm.status).toBe(201);
    const v1 = confirm.body.policy;
    expect(v1.version).toBe(1);
    await expect(page.getByRole("heading", { name: `Confirmed policy — version ${v1.version}` })).toBeVisible();
    const confirmedRules = v1.rules.filter((rule: any) => rule.status === "CONFIRMED");
    await expect(page.getByTestId("policy-rule-card")).toHaveCount(confirmedRules.length);
    await expect(page.getByTestId("policy-rule-threshold")).toHaveText(confirmedRules.map((rule: any) => formatFraction(rule.threshold)));
    await expectNoTestDataMarkers(page, "stage 2");
    await shot(page, "02-robert-policy-v1-confirmed-live-local-backend", { fullPage: true });

    // ---- Stage 3: NVDA to 25%, the preview is the service's answer --------------------------------------------
    await goToPurchase(page);
    await setPurchase(page, "NVDA", "25");
    const preview = page.getByTestId("purchase-preview");
    await expect(preview.getByTestId("cash-after")).toBeVisible();
    const check = await traffic.last("POST", /^\/check$/, (call) => call.requestBody?.purchase_request?.instrument_id === "NVDA" && call.status === 200);
    expect(check.requestBody.purchase_request.target_direct_weight).toBe(0.25);
    const checked = check.body;
    await expect(page.getByTestId("entered-target")).toHaveText(formatFraction(check.requestBody.purchase_request.target_direct_weight));
    await expect(preview.getByTestId("cash-after")).toHaveText(formatFraction(checked.feasibility.cash_after));
    await expect(preview.getByTestId("additional-purchase")).toHaveText(formatChange(checked.feasibility.additional_purchase));
    await expect(page.getByTestId("purchase-preview-label")).toContainText("Preview");
    // The same inputs through the engine directly.
    const direct = await engineCheck({
      persona_id: "robert",
      policy: check.requestBody.draft_rules === null ? v1 : check.requestBody.policy_id ? v1 : null,
      purchase_request: check.requestBody.purchase_request,
      draft_rules: check.requestBody.draft_rules,
    });
    expect(checked, "POST /check equals backend.engine.check_rules on the same inputs").toEqual(direct);
    await expectNoTestDataMarkers(page, "stage 3");
    await shot(page, "03-robert-purchase-preview-live-local-backend", { fullPage: true });

    // ---- Stage 4: one investigation, with a bearer header and an idempotency key -------------------------------
    await page.getByTestId("start-investigation").click();
    await expect(page.getByTestId("see-verdict")).toBeVisible({ timeout: 60_000 });
    const created = await traffic.last("POST", /^\/investigations$/);
    expect(created.status).toBe(202);
    expect(created.requestHeaders["idempotency-key"]).toMatch(/^[A-Za-z0-9_-]{8,64}$/);
    expect(created.requestBody).toMatchObject({ persona_id: "robert", policy_id: v1.policy_id, policy_version: 1, parent_investigation_id: null });
    const job1 = (await traffic.last("GET", /^\/investigations\/inv-[0-9a-f]+$/, (call) => call.body?.id === created.body.id && call.body?.status === "SUCCEEDED")).body;
    await expect(page.getByTestId("step-count")).toHaveText(String(job1.steps.length));
    await expect(page.getByTestId("timeline-step")).toHaveCount(job1.steps.length);
    // The local Bedrock fake refuses every call, so the job reports the deterministic fallback, and the page says so.
    expect(job1.agent.mode).toBe("DETERMINISTIC_FALLBACK");
    await expect(page.getByTestId("agent-mode")).toHaveAttribute("data-agent-mode", "DETERMINISTIC_FALLBACK");
    await expect(page.getByTestId("agent-mode")).toContainText("Deterministic fallback");
    await expectNoTestDataMarkers(page, "stage 4");
    await shot(page, "04-robert-investigation-steps-fallback-live-local-backend", { fullPage: true });

    // ---- Stage 5: the verdict ---------------------------------------------------------------------------------
    await page.getByTestId("see-verdict").click();
    await expect(page.getByTestId("report")).toBeVisible();
    const r1 = job1.result;
    // The demonstration's outcome: both confirmed rules fail, the issuer cap and the 2022 loss budget.
    expect(r1.rule_results.map((rule: any) => [rule.rule_type, rule.status])).toEqual([
      ["max_issuer_exposure", "FAIL"],
      ["scenario_loss_budget", "FAIL"],
    ]);
    expect(r1.summary.counts).toEqual({ pass: 0, fail: 2, unknown: 0 });
    await openAllDetails(page);
    await expectReportMatchesJob(page, job1);
    // The job's result is the engine's: identical to check_rules run directly with the stored policy version.
    const directJob = await engineCheck({ persona_id: "robert", policy: v1, purchase_request: job1.resolved_request });
    expect(r1, "the investigation result equals backend.engine.check_rules on the same inputs").toEqual(directJob);
    // And identical to what POST /check answered for the stored policy, when the preview used it.
    // Every printed percentage of the report is explained by a number (or a service-written sentence) of the job.
    const reportText = await figureText(page.getByTestId("report"));
    expect(percentTokens(reportText).length, "the sweep below reads a real report").toBeGreaterThan(40);
    expect(unexplainedFigures(reportText, [job1, v1]), "figures printed in the report that the API response does not contain").toEqual([]);
    await expectNoTestDataMarkers(page, "stage 5");
    await shot(page, "05-robert-verdict-two-fails-live-local-backend", { fullPage: true });

    // ---- Evidence drawer ---------------------------------------------------------------------------------------
    for (const rule of r1.rule_results) {
      const card = page.locator(`[data-testid="rule-result"][data-rule-id="${rule.rule_id}"]`);
      await card.getByRole("button", { name: /^Evidence for / }).click();
      const drawer = page.getByRole("dialog");
      await expect(drawer).toBeVisible();
      const shown = await expectDrawerMatches(drawer, r1);
      expect(shown).toBeGreaterThanOrEqual(rule.evidence_ids.length);
      for (const id of rule.evidence_ids) await expect(drawer.locator(`[data-evidence-id="${id}"]`)).toHaveCount(1);
      expect(unexplainedFigures(await figureText(drawer), [job1]), `figures in the evidence drawer of ${rule.rule_id} that the API response does not contain`).toEqual([]);
      if (rule.rule_type === "max_issuer_exposure") await shot(page, "06-robert-evidence-drawer-live-local-backend");
      await page.keyboard.press("Escape");
      await expect(drawer).toBeHidden();
    }

    // ---- Stage 6: raise the single-company limit to 30% -> policy version 2 -> a new investigation -------------
    await page.getByRole("link", { name: "Challenge this result" }).click();
    const form = page.getByTestId("change-rule-form");
    await expect(form).toBeVisible();
    const capRule = v1.rules.find((rule: any) => rule.rule_type === "max_issuer_exposure");
    await expect(form.getByTestId("current-threshold")).toContainText(formatFraction(capRule.threshold));
    await form.getByRole("textbox", { name: /^New value/ }).fill("30");
    await expect(form.getByTestId("draft-preview-result")).toContainText("Preview:");
    await page.getByTestId("submit-rule-change").click();
    await expect(page.getByTestId("result-comparison")).toBeVisible({ timeout: 60_000 });

    const challenge = await traffic.last("POST", /^\/investigations\/inv-[0-9a-f]+\/challenge$/);
    expect(challenge.status).toBe(202);
    expect(challenge.path).toBe(`/investigations/${job1.id}/challenge`);
    expect(challenge.requestHeaders["idempotency-key"]).toMatch(/^[A-Za-z0-9_-]{8,64}$/);
    expect(challenge.requestBody).toMatchObject({ type: "CHANGE_RULE", payload: { rule_id: capRule.rule_id, new_threshold: 0.3 } });
    const v2 = challenge.body.policy;
    expect(v2.version).toBe(2);
    expect(v2.parent_version).toBe(1);
    const job2 = (await traffic.last("GET", /^\/investigations\/inv-[0-9a-f]+$/, (call) => call.body?.id === challenge.body.investigation.id && call.body?.status === "SUCCEEDED")).body;
    const r2 = job2.result;
    expect(job2.policy_version).toBe(2);
    expect(job2.parent_investigation_id).toBe(job1.id);

    // The cap now passes, the loss budget still fails.
    const byType = (result: any, type: string) => result.rule_results.find((rule: any) => rule.rule_type === type);
    expect(byType(r2, "max_issuer_exposure").status).toBe("PASS");
    expect(byType(r2, "max_issuer_exposure").limit).toBe(0.3);
    expect(byType(r2, "scenario_loss_budget").status).toBe("FAIL");
    // The measured NVIDIA exposure is identical under both versions: only the rule changed.
    expect(byType(r2, "max_issuer_exposure").measured).toEqual(byType(r1, "max_issuer_exposure").measured);
    expect(byType(r2, "scenario_loss_budget").measured).toEqual(byType(r1, "scenario_loss_budget").measured);
    const nvidia = (result: any) => result.exposure.issuers.find((issuer: any) => issuer.issuer_id === "NVIDIA");
    expect(nvidia(r2), "NVIDIA exposure record, version 2 vs version 1").toEqual(nvidia(r1));
    const directJob2 = await engineCheck({ persona_id: "robert", policy: v2, purchase_request: job2.resolved_request });
    expect(r2, "the re-investigation equals backend.engine.check_rules under policy version 2").toEqual(directJob2);

    // What the comparison shows.
    await expect(page.getByTestId("comparison-headline")).toHaveText([verdictHeadline(r1.summary).title, verdictHeadline(r2.summary).title]);
    const changed = page.locator('[data-testid="policy-diff-row"][data-change="CHANGED"]');
    await expect(changed).toHaveCount(1);
    await expect(changed.locator("td")).toHaveText([formatFraction(capRule.threshold), formatFraction(0.3)]);
    const capRow = page.getByTestId("result-comparison-row").first();
    const capMeasured = byType(r1, "max_issuer_exposure").measured;
    const measuredText = `measured ${formatFractionRange(capMeasured.lower, capMeasured.upper)}`;
    await expect(capRow.locator("td").nth(0)).toContainText(measuredText);
    await expect(capRow.locator("td").nth(1)).toContainText(measuredText);
    await expect(capRow.locator("td").nth(0).locator("[data-status]").first()).toHaveAttribute("data-status", "FAIL");
    await expect(capRow.locator("td").nth(1).locator("[data-status]").first()).toHaveAttribute("data-status", "PASS");
    const lossRow = page.getByTestId("result-comparison-row").nth(1);
    await expect(lossRow.locator("td").nth(1).locator("[data-status]").first()).toHaveAttribute("data-status", "FAIL");
    expect(unexplainedFigures(await figureText(page.getByTestId("comparison-section")), [job1, job2, v1, v2])).toEqual([]);
    await expectNoTestDataMarkers(page, "stage 6");
    await shot(page, "07-robert-challenge-v1-v2-comparison-live-local-backend", { locator: page.getByTestId("comparison-section") });

    // ---- The new report -----------------------------------------------------------------------------------------
    await page.getByTestId("comparison-report").nth(1).getByRole("button", { name: "Open this report" }).click();
    await expect(page.getByTestId("report")).toHaveAttribute("data-job-id", job2.id);
    await openAllDetails(page);
    await expectReportMatchesJob(page, job2);
    expect(unexplainedFigures(await figureText(page.getByTestId("report")), [job2, v2])).toEqual([]);
    await shot(page, "08-robert-verdict-policy-v2-cap-passes-live-local-backend", { fullPage: true });

    // ---- The earlier report is still there, unchanged ----------------------------------------------------------
    await expect(page.getByTestId("report-entry")).toHaveCount(2);
    await page.getByTestId("report-entry").first().getByRole("button", { name: /^Open report 1/ }).click();
    await expect(page.getByText("You are reading an earlier report, checked against policy version 1")).toBeVisible();
    await expect(page.getByTestId("report")).toHaveAttribute("data-job-id", job1.id);
    await openAllDetails(page);
    await expectReportMatchesJob(page, job1);
    // ... and the service still returns it, byte for byte the terminal members it returned before the challenge.
    const again = await api("GET", `/investigations/${job1.id}`);
    expect(again.status).toBe(200);
    for (const member of ["status", "steps", "result", "explanation", "clarification", "failure", "policy_version"]) {
      expect(again.body[member], `member ${member} of the version-1 job after the challenge`).toEqual(job1[member]);
    }
    const stored = await api("POST", "/check", { persona_id: "robert", policy_id: v1.policy_id, policy_version: 1, purchase_request: job1.resolved_request, draft_rules: null });
    expect(stored.body.rule_results, "policy version 1 is still stored and still evaluates as before").toEqual(r1.rule_results);

    // ---- Headers, hosts, storage --------------------------------------------------------------------------------
    await traffic.expectClean();
    const log = await serverLog();
    const pageCalls = log.filter((entry) => entry.method !== "OPTIONS" && entry.origin !== null);
    expect(pageCalls.length).toBeGreaterThan(8);
    for (const entry of pageCalls) {
      expect(entry.authorization, `${entry.method} ${entry.path}`).toBe("expected");
      expect(entry.cookie).toBeNull();
      expect(entry.query).toBe("");
    }
    const posts = log.filter((entry) => entry.route === "POST /investigations" || (entry.route === "POST /investigations/{id}/challenge" && entry.origin !== null));
    for (const entry of posts) expect(entry.idempotency_key, `${entry.path} carries Idempotency-Key`).toMatch(/^[A-Za-z0-9_-]{8,64}$/);
    expect(log.filter((entry) => entry.route === "POST /investigations").length, "one investigation was created by the page").toBe(1);
  });
});
