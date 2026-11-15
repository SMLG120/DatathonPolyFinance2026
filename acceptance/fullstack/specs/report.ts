import { expect, type Locator, type Page } from "@playwright/test";
import { formatEvidenceValue } from "../../../frontend/src/lib/evidence";
import { formatChange, formatCoverage, formatDate, formatDateTime, formatFraction, formatFractionRange, formatGap, formatReturn } from "../../../frontend/src/lib/format";
import { limitNoun, ruleDirection } from "../../../frontend/src/lib/rules";
import { coverageText, verdictHeadline } from "../../../frontend/src/lib/verdict";

/**
 * What the verdict and evidence screens must print for a job, computed from the API response the page received with
 * the frontend's own formatters (`frontend/src/lib/format.ts`, `evidence.ts`, `rules.ts`, `verdict.ts`). No figure
 * is typed in here.
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

