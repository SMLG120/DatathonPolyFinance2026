/**
 * FIXTURES CLIENT — A TEST DOUBLE, NOT THE ENGINE.
 *
 * It implements the same `ApiClient` interface as the live client so the whole
 * journey can run with no network. To make threshold previews and the
 * "change a rule" challenge demonstrable it re-applies the D4 comparison
 * (PASS / FAIL / UNKNOWN against a range) to RECORDED placeholder
 * measurements. That logic exists here for test data only:
 *
 *   - it is never used in live mode, where every verdict comes from the
 *     deterministic engine behind the API;
 *   - it only knows the recorded purchase of each persona and refuses others;
 *   - the interface shows "Test data — fixtures" whenever it is in use.
 *
 * PHASE 2: replace the recorded placeholders with the JSON fixtures in
 * `contracts/fixtures/api/` (through `@/lib/fixtures`).
 */
import type {
  ChallengeRequest,
  ChallengeResponse,
  CheckRequest,
  CheckResult,
  ConfirmRulesRequest,
  CreateInvestigationRequest,
  EvidenceRecord,
  ExposureBreakdown,
  ExposureResult,
  Feasibility,
  FractionInterval,
  InterpretRequest,
  InterpretResponse,
  Investigation,
  InvestigationStep,
  MaxCompliant,
  PersonaId,
  Policy,
  Portfolio,
  PurchaseRequest,
  Rule,
  RuleEvaluation,
  RuleResult,
  ScenarioResult,
  VerdictStatus,
} from "@/lib/contracts";
import type { FixtureSimulation } from "@/lib/config";
import {
  FIXTURE_CALCULATION_VERSION,
  FIXTURE_CLOCK_START,
  FIXTURE_SCENARIOS,
  FIXTURE_SOURCES,
  type FixtureRuleMeasure,
  type FixtureScenario,
} from "@/lib/fixtures";
import { EPS, formatFraction, formatFractionRange, type LimitDirection } from "@/lib/format";
import { getRuleThreshold, ruleDirection, ruleSummary, ruleTypeLabel, withRuleThreshold } from "@/lib/rules";
import type { ApiClient, RequestOptions } from "./client";
import { ApiError } from "./errors";

export interface FixturesClientOptions {
  simulate?: FixtureSimulation | null;
  /** Artificial delay so loading states are visible. Tests pass 0. */
  latencyMs?: number;
  /** How many recorded steps each poll reveals. */
  stepsPerPoll?: number;
}

interface Job {
  base: Omit<Investigation, "status" | "steps" | "result" | "error" | "updated_at">;
  steps: InvestigationStep[];
  result: CheckResult;
  polls: number;
}

function tidy(value: number): number {
  return Math.round(value * 1e10) / 1e10;
}

function clone<T>(value: T): T {
  return structuredClone(value);
}

function delay(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const aborted = () => reject(new ApiError("aborted", "The request was cancelled."));
    if (signal?.aborted) return aborted();
    const timer = setTimeout(() => {
      signal?.removeEventListener("abort", onAbort);
      resolve();
    }, ms);
    const onAbort = () => {
      clearTimeout(timer);
      aborted();
    };
    signal?.addEventListener("abort", onAbort, { once: true });
  });
}

function notRecorded(message: string): ApiError {
  return new ApiError("validation", message, { status: 422, code: "FIXTURE_NOT_RECORDED" });
}

// ---------------------------------------------------------------------------
// D4 comparison applied to recorded measurements
// ---------------------------------------------------------------------------

function compare(direction: LimitDirection, interval: FractionInterval | null, limit: number): VerdictStatus {
  if (!interval) return "UNKNOWN";
  if (direction === "max") {
    if (interval.upper <= limit + EPS) return "PASS";
    if (interval.lower > limit + EPS) return "FAIL";
    return "UNKNOWN";
  }
  if (interval.lower >= limit - EPS) return "PASS";
  if (interval.upper < limit - EPS) return "FAIL";
  return "UNKNOWN";
}

function gapFor(direction: LimitDirection, status: VerdictStatus, interval: FractionInterval | null, limit: number): number | null {
  if (!interval || status === "UNKNOWN") return null;
  const decisive =
    direction === "max"
      ? status === "FAIL"
        ? interval.lower
        : interval.upper
      : status === "FAIL"
        ? interval.upper
        : interval.lower;
  return tidy(decisive - limit);
}

function reasonFor(
  direction: LimitDirection,
  status: VerdictStatus,
  label: string,
  interval: FractionInterval | null,
  limit: number,
  noun: string,
): string {
  const limitText = formatFraction(limit);
  if (!interval) return `${label}: no measurement is available, so this cannot be determined.`;
  const measured = formatFractionRange(interval.lower, interval.upper);
  if (status === "UNKNOWN") {
    return `${label}: ${measured}. The ${noun} of ${limitText} falls inside that range, so this cannot be determined.`;
  }
  const atLimit = Math.abs((direction === "max" ? interval.upper : interval.lower) - limit) <= EPS;
  if (status === "PASS") {
    if (atLimit) return `${label}: ${measured}, exactly at the ${noun} of ${limitText}, which passes.`;
    return direction === "max"
      ? `${label}: ${measured}, within the ${noun} of ${limitText}.`
      : `${label}: ${measured}, at or above the ${noun} of ${limitText}.`;
  }
  return direction === "max"
    ? `${label}: ${measured}, above the ${noun} of ${limitText}.`
    : `${label}: ${measured}, below the ${noun} of ${limitText}.`;
}

function makeEvaluation(
  rule: Rule,
  label: string,
  interval: FractionInterval | null,
  limit: number,
  evidenceIds: string[],
  noun: string,
): RuleEvaluation {
  const direction = ruleDirection(rule.rule_type);
  const status = compare(direction, interval, limit);
  return {
    status,
    measured: interval,
    measured_label: label,
    limit,
    gap: gapFor(direction, status, interval, limit),
    reason: reasonFor(direction, status, label, interval, limit, noun),
    evidence_ids: evidenceIds,
  };
}

function describePaths(b: ExposureBreakdown): string[] {
  const lines = [`direct weight: ${formatFraction(b.direct)}`];
  for (const p of b.paths) {
    lines.push(
      p.subject_weight_in_fund === null
        ? `${p.fund_id}: no holdings file; ${formatFraction(p.fund_weight)} of the portfolio counted as possible extra`
        : `${p.fund_id}: fund weight ${formatFraction(p.fund_weight)} x weight in fund ${formatFraction(p.subject_weight_in_fund)} = ${formatFraction(p.known_exposure, { decimals: 2 })}`,
    );
  }
  lines.push(`known total (lower bound): ${formatFraction(b.lower, { decimals: 2 })}`);
  if (b.possible_extra > EPS) lines.push(`upper bound with possible extra: ${formatFraction(b.upper, { decimals: 2 })}`);
  return lines;
}

function coverageOf(b: ExposureBreakdown): number | null {
  const funds = b.paths.reduce((sum, p) => sum + p.fund_weight, 0);
  if (funds <= EPS) return null;
  return tidy(b.paths.reduce((sum, p) => sum + p.fund_weight * p.coverage, 0) / funds);
}

function directWeight(portfolio: Portfolio, instrumentId: string): number {
  return portfolio.positions.find((p) => p.instrument_id === instrumentId)?.weight ?? 0;
}

function samePurchase(a: PurchaseRequest | null, b: PurchaseRequest | null): boolean {
  if (a === null || b === null) return a === b;
  return a.instrument_id === b.instrument_id && Math.abs(a.target_direct_weight - b.target_direct_weight) <= EPS;
}

function describePurchase(purchase: PurchaseRequest): string {
  return `${purchase.instrument_id} at a final direct weight of ${formatFraction(purchase.target_direct_weight)}`;
}

function evaluateScenario(
  scenario: FixtureScenario,
  rules: Rule[],
  purchase: PurchaseRequest | null,
  policyVersion: number | null,
  isDraft: boolean,
): CheckResult {
  const portfolio = scenario.portfolio_response.portfolio;
  const evidence: EvidenceRecord[] = [];
  const addEvidence = (record: Omit<EvidenceRecord, "calculation_version" | "policy_version">): string => {
    evidence.push({ ...record, calculation_version: FIXTURE_CALCULATION_VERSION, policy_version: policyVersion });
    return record.evidence_id;
  };
  const phases = purchase ? (["starting", "proposed"] as const) : (["starting"] as const);
  const subjectOf = (phase: "starting" | "proposed") =>
    phase === "starting" ? "Starting portfolio" : "Portfolio after the proposed purchase";

  const ruleResults: RuleResult[] = [];
  const exposures: ExposureResult[] = [];
  let scenarioResult: ScenarioResult | null = null;

  const evaluable = rules.filter((rule) => rule.status !== "SUPERSEDED" && getRuleThreshold(rule) !== null);
  for (const rule of evaluable) {
    const limit = getRuleThreshold(rule) as number;

    if (rule.rule_type === "scenario_loss_budget") {
      const replay = scenario.replay && scenario.replay.scenario_id === rule.scenario_id ? scenario.replay : null;
      const evaluations = {} as Record<"starting" | "proposed", RuleEvaluation>;
      for (const phase of phases) {
        const label = `Loss over the ${replay?.scenario_label ?? "replayed period"}`;
        if (!replay) {
          evaluations[phase] = makeEvaluation(rule, label, null, limit, [], "budget");
          continue;
        }
        const measurement = replay[phase];
        const returnId = addEvidence({
          evidence_id: `ev-${rule.rule_id}-${phase}-return`,
          metric_id: "scenario_terminal_return",
          label: `Return over the ${replay.scenario_label}`,
          value: measurement.scenario_terminal_return,
          unit: "fraction",
          subject: subjectOf(phase),
          period_start: replay.period_start,
          period_end: replay.period_end,
          source_ids: ["fx-src-scenario", "fx-src-prices"],
          coverage: null,
          assumptions: replay.assumptions,
          calculation_path: [
            "for each instrument: adjusted price at period end / adjusted price at period start - 1, in CAD",
            "portfolio return: sum of starting weight x instrument return; cash contributes 0",
            "loss compared with the budget: minus the portfolio return",
          ],
        });
        addEvidence({
          evidence_id: `ev-${rule.rule_id}-${phase}-drawdown`,
          metric_id: "scenario_max_drawdown",
          label: `Deepest fall during the ${replay.scenario_label} (context only)`,
          value: measurement.scenario_max_drawdown,
          unit: "fraction",
          subject: subjectOf(phase),
          period_start: replay.period_start,
          period_end: replay.period_end,
          source_ids: ["fx-src-scenario", "fx-src-prices"],
          coverage: null,
          assumptions: [...replay.assumptions, "Daily values on the union calendar; each instrument's last value is carried forward."],
          calculation_path: ["largest peak-to-trough fall of the daily portfolio value during the period"],
        });
        const loss = tidy(-measurement.scenario_terminal_return);
        evaluations[phase] = makeEvaluation(rule, label, { lower: loss, upper: loss }, limit, [returnId], "budget");
      }
      ruleResults.push({
        rule_id: rule.rule_id,
        rule_type: rule.rule_type,
        starting: evaluations.starting,
        proposed: purchase ? evaluations.proposed : null,
      });
      if (replay) {
        const decisive = purchase ? evaluations.proposed : evaluations.starting;
        scenarioResult = {
          scenario_id: replay.scenario_id,
          scenario_label: replay.scenario_label,
          rule_id: rule.rule_id,
          period_start: replay.period_start,
          period_end: replay.period_end,
          starting: replay.starting,
          proposed: purchase ? replay.proposed : null,
          budget: limit,
          status: decisive.status,
          gap: decisive.gap,
          assumptions: replay.assumptions,
          evidence_ids: phases.flatMap((phase) => [
            `ev-${rule.rule_id}-${phase}-return`,
            `ev-${rule.rule_id}-${phase}-drawdown`,
          ]),
        };
      }
      continue;
    }

    const measure: FixtureRuleMeasure | undefined = scenario.measures[rule.rule_type];
    const evaluations = {} as Record<"starting" | "proposed", RuleEvaluation>;
    for (const phase of phases) {
      if (!measure) {
        evaluations[phase] = makeEvaluation(rule, ruleTypeLabel(rule.rule_type), null, limit, [], "limit");
        continue;
      }
      const { label, breakdown } = measure[phase];
      const evidenceId = addEvidence({
        evidence_id: `ev-${rule.rule_id}-${phase}`,
        metric_id: rule.rule_type === "max_issuer_exposure" || rule.rule_type === "min_issuer_exposure" ? "issuer_exposure_total" : "set_exposure_total",
        label,
        value: breakdown.lower,
        unit: "fraction",
        subject: subjectOf(phase),
        period_start: null,
        period_end: portfolio.valuation_date,
        source_ids: measure.source_ids,
        coverage: coverageOf(breakdown),
        assumptions: measure.assumptions,
        calculation_path: [...measure.calculation_path, ...describePaths(breakdown)],
      });
      evaluations[phase] = makeEvaluation(
        rule,
        label,
        { lower: breakdown.lower, upper: breakdown.upper },
        limit,
        [evidenceId],
        rule.rule_type === "min_issuer_exposure" ? "minimum" : "limit",
      );
    }
    ruleResults.push({
      rule_id: rule.rule_id,
      rule_type: rule.rule_type,
      starting: evaluations.starting,
      proposed: purchase ? evaluations.proposed : null,
    });

    if (measure && rule.rule_type !== "controversy_exclusion") {
      const chart = measure.chart ?? {
        subject_label: measure.proposed.label,
        starting: measure.starting.breakdown,
        proposed: measure.proposed.breakdown,
      };
      const chartIds = phases.map((phase) =>
        addEvidence({
          evidence_id: `ev-${rule.rule_id}-chart-${phase}`,
          metric_id: "exposure_breakdown",
          label: `Exposure to ${chart.subject_label}`,
          value: chart[phase].lower,
          unit: "fraction",
          subject: subjectOf(phase),
          period_start: null,
          period_end: portfolio.valuation_date,
          source_ids: measure.source_ids,
          coverage: coverageOf(chart[phase]),
          assumptions: measure.assumptions,
          calculation_path: [...measure.calculation_path, ...describePaths(chart[phase])],
        }),
      );
      exposures.push({
        rule_id: rule.rule_id,
        subject_label: chart.subject_label,
        limit,
        starting: chart.starting,
        proposed: purchase ? chart.proposed : null,
        evidence_ids: chartIds,
      });
    }
  }

  let feasibility: Feasibility | null = null;
  if (purchase) {
    const additional = tidy(purchase.target_direct_weight - directWeight(portfolio, purchase.instrument_id));
    const cashAfter = tidy(portfolio.cash_weight - additional);
    feasibility = {
      status: cashAfter < -EPS ? "INSUFFICIENT_CASH" : "FEASIBLE",
      funding_path: "CASH",
      cash_before: portfolio.cash_weight,
      cash_after: cashAfter,
      additional_purchase: additional,
    };
    addEvidence({
      evidence_id: "ev-cash-after",
      metric_id: "cash_after_purchase",
      label: "Cash after the purchase",
      value: cashAfter,
      unit: "fraction",
      subject: "Portfolio after the proposed purchase",
      period_start: null,
      period_end: portfolio.valuation_date,
      source_ids: ["fx-src-scenario"],
      coverage: null,
      assumptions: [
        "Funded from existing cash only.",
        "All other positions unchanged.",
        "Fees and taxes excluded.",
      ],
      calculation_path: [
        "cash after = starting cash - (target direct weight - starting direct weight)",
        `${formatFraction(portfolio.cash_weight)} - (${formatFraction(purchase.target_direct_weight)} - ${formatFraction(directWeight(portfolio, purchase.instrument_id))}) = ${formatFraction(cashAfter)}`,
      ],
    });
  }

  const funds = purchase ? scenario.funds.proposed : scenario.funds.starting;
  const anyMissing = funds.some((f) => f.status === "MISSING" || f.status === "PARTIAL");
  const allMissing = funds.filter((f) => f.status !== "NOT_APPLICABLE").every((f) => f.status === "MISSING");

  const proposedIssuer = ruleResults.find((r) => r.rule_type === "max_issuer_exposure")?.proposed;
  const goalContext = purchase
    ? scenario.goal_context.map((context) => ({
        objective_id: context.objective_id,
        text: context.text.replace(
          "{value}",
          proposedIssuer?.measured ? formatFractionRange(proposedIssuer.measured.lower, proposedIssuer.measured.upper) : "a larger share",
        ),
        evidence_ids: proposedIssuer?.evidence_ids ?? [],
      }))
    : [];

  const result: CheckResult = {
    persona_id: scenario.persona_id,
    policy_version: policyVersion,
    is_draft_preview: isDraft,
    valuation_date: portfolio.valuation_date,
    purchase,
    feasibility,
    rule_results: ruleResults,
    exposures,
    scenario: scenarioResult,
    data_coverage: {
      status: allMissing && funds.length > 0 ? "MISSING" : anyMissing ? "PARTIAL" : "COVERED",
      funds,
      notes: scenario.coverage_notes,
    },
    policy_consistency: { status: "CONSISTENT", findings: [] },
    goal_context: goalContext,
    max_compliant: null,
    explanation: [],
    evidence,
    sources: FIXTURE_SOURCES,
    calculation_version: FIXTURE_CALCULATION_VERSION,
  };

  if (purchase && !isDraft) {
    result.max_compliant = maxCompliant(scenario, evaluable, ruleResults, purchase);
    if (result.max_compliant.status === "SUPPORTED") {
      result.evidence.push({
        evidence_id: "ev-max-compliant",
        metric_id: "max_compliant_final_weight",
        label: `Largest final direct weight of ${purchase.instrument_id} that passes every confirmed rule`,
        value: result.max_compliant.final_direct_weight,
        unit: "fraction",
        subject: "Portfolio after a purchase at the boundary",
        period_start: null,
        period_end: portfolio.valuation_date,
        source_ids: ["fx-src-scenario", "fx-src-holdings", "fx-src-prices"],
        coverage: null,
        assumptions: ["Funded from existing cash only.", "All other positions unchanged.", "Fees and taxes excluded."],
        calculation_path: [
          "for each confirmed rule: the largest final weight at which that rule still passes",
          "also limited by available cash",
          "the smallest of these, then the same checks re-run at that weight",
        ],
        calculation_version: FIXTURE_CALCULATION_VERSION,
        policy_version: policyVersion,
      });
      result.max_compliant.evidence_ids = ["ev-max-compliant"];
    }
  }

  result.explanation = ruleResults.map((r) => {
    const evaluation = r.proposed ?? r.starting;
    return { text: evaluation.reason, evidence_ids: evaluation.evidence_ids };
  });
  return result;
}

/**
 * The boundary for the recorded purchase. Only the two rule types with a
 * closed form in the test data are supported; anything else withholds it.
 */
function maxCompliant(
  scenario: FixtureScenario,
  rules: Rule[],
  ruleResults: RuleResult[],
  purchase: PurchaseRequest,
): MaxCompliant {
  const none = { final_direct_weight: null, additional_purchase: null, binding_rule_ids: [], verified_by_rerun: false, evidence_ids: [] };
  const labelOf = (ruleId: string) => {
    const rule = rules.find((r) => r.rule_id === ruleId);
    return rule ? ruleTypeLabel(rule.rule_type) : ruleId;
  };

  const startingFail = ruleResults.find((r) => r.starting.status === "FAIL");
  if (startingFail) {
    return {
      ...none,
      status: "NO_FEASIBLE_PURCHASE",
      binding_rule_ids: [startingFail.rule_id],
      reason: `The starting portfolio already breaks the rule “${labelOf(startingFail.rule_id)}”. A purchase paid from existing cash, with every other position unchanged, cannot repair that: it would take a sale, which this funding path does not allow. No purchase is feasible under this funding path.`,
    };
  }
  const unknown = ruleResults.find((r) => r.starting.status === "UNKNOWN" || r.proposed?.status === "UNKNOWN");
  if (unknown) {
    return {
      ...none,
      status: "WITHHELD",
      binding_rule_ids: [unknown.rule_id],
      reason: `The rule “${labelOf(unknown.rule_id)}” cannot be determined with the data available, so a maximum that respects every rule is not shown.`,
    };
  }

  const portfolio = scenario.portfolio_response.portfolio;
  const startingDirect = directWeight(portfolio, purchase.instrument_id);
  const candidates: { rule_id: string | null; value: number }[] = [
    { rule_id: null, value: tidy(startingDirect + portfolio.cash_weight) },
  ];
  for (const rule of rules) {
    const limit = getRuleThreshold(rule) as number;
    if (rule.rule_type === "max_issuer_exposure" && scenario.measures.max_issuer_exposure?.chart) {
      const chart = scenario.measures.max_issuer_exposure.chart.proposed;
      candidates.push({ rule_id: rule.rule_id, value: tidy(limit - chart.indirect_known - chart.possible_extra) });
    } else if (rule.rule_type === "scenario_loss_budget" && scenario.replay) {
      const slope = scenario.replay.instrument_return;
      if (slope < 0) {
        const room = limit + scenario.replay.starting.scenario_terminal_return;
        candidates.push({ rule_id: rule.rule_id, value: tidy(startingDirect + room / -slope) });
      }
    } else {
      return {
        ...none,
        status: "WITHHELD",
        binding_rule_ids: [rule.rule_id],
        reason: `Test data holds no boundary calculation for the rule “${ruleTypeLabel(rule.rule_type)}”, so a maximum that respects every rule is not shown.`,
      };
    }
  }

  const boundary = Math.min(...candidates.map((c) => c.value));
  if (boundary < startingDirect - EPS) {
    return {
      ...none,
      status: "NO_FEASIBLE_PURCHASE",
      reason: "Respecting every confirmed rule would need a smaller position than the one already held. That takes a sale, which this funding path does not allow. No purchase is feasible under this funding path.",
    };
  }
  const binding = candidates.filter((c) => c.rule_id !== null && Math.abs(c.value - boundary) <= 1e-6).map((c) => c.rule_id as string);
  return {
    status: "SUPPORTED",
    final_direct_weight: boundary,
    additional_purchase: tidy(boundary - startingDirect),
    binding_rule_ids: binding,
    verified_by_rerun: true,
    reason:
      binding.length > 0
        ? `Set by the rule “${labelOf(binding[0] as string)}”. The same checks were re-run at this weight and every confirmed rule passed.`
        : "Set by the cash available. The same checks were re-run at this weight and every confirmed rule passed.",
    evidence_ids: [],
  };
}

function buildSteps(scenario: FixtureScenario, policy: Policy, purchase: PurchaseRequest, result: CheckResult, jobIndex: number): InvestigationStep[] {
  const portfolio = scenario.portfolio_response.portfolio;
  const active = policy.rules.filter((r) => r.status === "CONFIRMED");
  const start = Date.parse(FIXTURE_CLOCK_START) + jobIndex * 5 * 60_000;
  const steps: Omit<InvestigationStep, "seq" | "finished_at" | "started_at" | "status" | "initiated_by">[] = [];

  steps.push({
    tool: "get_portfolio",
    input_summary: `persona ${scenario.persona_id}`,
    result_summary: `${portfolio.positions.length} positions and cash ${formatFraction(portfolio.cash_weight)}; valuation date ${portfolio.valuation_date}`,
  });
  steps.push({
    tool: "get_policy",
    input_summary: `policy version ${policy.policy_version}`,
    result_summary: `${active.length} confirmed ${active.length === 1 ? "rule" : "rules"}: ${active.map(ruleSummary).join("; ")}`,
  });
  if (result.feasibility) {
    steps.push({
      tool: "simulate_change",
      input_summary: `${describePurchase(purchase)}, funded from existing cash`,
      result_summary: `additional purchase ${formatFraction(result.feasibility.additional_purchase)} of the portfolio; cash after ${formatFraction(result.feasibility.cash_after)}; ${result.feasibility.status === "FEASIBLE" ? "feasible" : "insufficient cash"}`,
    });
  }
  const lookThrough = result.data_coverage.funds.filter((f) => f.status !== "NOT_APPLICABLE");
  if (lookThrough.length > 0) {
    steps.push({
      tool: "get_holdings",
      input_summary: lookThrough.map((f) => f.fund_id).join(", "),
      result_summary: lookThrough
        .map((f) => (f.status === "MISSING" ? `${f.fund_id}: no holdings file` : `${f.fund_id}: coverage ${formatFraction(f.coverage)}`))
        .join("; "),
    });
  }
  for (const exposure of result.exposures) {
    const after = exposure.proposed ?? exposure.starting;
    steps.push({
      tool: "compute_exposure",
      input_summary: `${exposure.subject_label}, portfolio after the purchase`,
      result_summary:
        after.possible_extra > EPS
          ? `known ${formatFraction(after.lower)}; possible range ${formatFractionRange(after.lower, after.upper)}`
          : `direct ${formatFraction(after.direct)} + through funds ${formatFraction(after.indirect_known)} = ${formatFraction(after.lower)}`,
    });
  }
  const controversy = result.rule_results.find((r) => r.rule_type === "controversy_exclusion");
  if (controversy) {
    const evaluation = controversy.proposed ?? controversy.starting;
    steps.push({
      tool: "lookup_controversy_evidence",
      input_summary: "companies held directly and through funds",
      result_summary: evaluation.measured
        ? `registry records found for ${formatFraction(evaluation.measured.lower)} of the portfolio; up to ${formatFraction(evaluation.measured.upper)} is in companies the registry does not cover`
        : "no registry coverage",
    });
  }
  if (result.scenario) {
    const measurement = result.scenario.proposed ?? result.scenario.starting;
    steps.push({
      tool: "replay_period",
      input_summary: `${result.scenario.scenario_id}, allocation after the purchase`,
      result_summary: `return over the period ${formatFraction(measurement.scenario_terminal_return, { signed: true })}; deepest fall during the period ${formatFraction(measurement.scenario_max_drawdown, { signed: true })} (context only)`,
    });
  }
  const counts = { PASS: 0, FAIL: 0, UNKNOWN: 0 };
  for (const r of result.rule_results) counts[(r.proposed ?? r.starting).status] += 1;
  steps.push({
    tool: "check_rules",
    input_summary: `policy version ${policy.policy_version}, portfolio after the purchase`,
    result_summary: `${result.rule_results.length} ${result.rule_results.length === 1 ? "rule" : "rules"} checked: ${counts.PASS} pass, ${counts.FAIL} fail, ${counts.UNKNOWN} unknown`,
  });
  if (result.max_compliant) {
    const max = result.max_compliant;
    steps.push({
      tool: "max_compliant_amount",
      input_summary: `${purchase.instrument_id}, policy version ${policy.policy_version}`,
      result_summary:
        max.status === "SUPPORTED"
          ? `largest final direct weight ${formatFraction(max.final_direct_weight, { decimals: 2, rounding: "down" })}; re-checked at that weight`
          : max.status === "WITHHELD"
            ? "withheld: a rule cannot be determined"
            : "no purchase is feasible under this funding path",
    });
  }

  return steps.map((step, index) => ({
    ...step,
    seq: index + 1,
    status: "OK",
    initiated_by: "SERVER",
    started_at: new Date(start + index * 2_000 + 1_000).toISOString().replace(".000Z", "Z"),
    finished_at: new Date(start + (index + 1) * 2_000).toISOString().replace(".000Z", "Z"),
  }));
}

export function createFixturesClient(options: FixturesClientOptions = {}): ApiClient {
  const latencyMs = options.latencyMs ?? 150;
  const stepsPerPoll = options.stepsPerPoll ?? 3;
  const simulate = options.simulate ?? null;

  const policies = new Map<PersonaId, Policy[]>();
  const jobs = new Map<string, Job>();
  const jobIdByKey = new Map<string, string>();
  let correctionCount = 0;
  let objectiveCount = 0;

  function scenarioFor(personaId: PersonaId): FixtureScenario {
    const scenario = FIXTURE_SCENARIOS[personaId];
    if (!scenario) {
      throw new ApiError("not_found", `Test data holds no portfolio for this persona (${personaId}).`, {
        status: 404,
        code: "FIXTURE_NOT_RECORDED",
      });
    }
    return scenario;
  }

  function requireRecordedPurchase(scenario: FixtureScenario, purchase: PurchaseRequest | null): void {
    const recorded = scenario.portfolio_response.scenario_purchase;
    if (purchase === null || samePurchase(purchase, recorded)) return;
    throw notRecorded(
      recorded
        ? `Test data only holds a recorded result for ${describePurchase(recorded)}. Other requests need the live service.`
        : "Test data holds no recorded purchase for this persona.",
    );
  }

  async function respond<T>(requestOptions: RequestOptions | undefined, produce: () => T): Promise<T> {
    await delay(latencyMs, requestOptions?.signal);
    return clone(produce());
  }

  function createJob(scenario: FixtureScenario, policy: Policy, purchase: PurchaseRequest): string {
    const index = jobs.size;
    const id = `fx-inv-${index + 1}`;
    const result = evaluateScenario(scenario, policy.rules, purchase, policy.policy_version, false);
    const steps = buildSteps(scenario, policy, purchase, result, index);
    jobs.set(id, {
      base: {
        investigation_id: id,
        persona_id: scenario.persona_id,
        policy_version: policy.policy_version,
        purchase,
        created_at: new Date(Date.parse(FIXTURE_CLOCK_START) + index * 5 * 60_000).toISOString().replace(".000Z", "Z"),
        // Honest about what this is: a replay of recorded steps. No model is called in fixtures mode.
        agent: { mode: "DETERMINISTIC_FALLBACK", note: "Test data: the fixtures client replays a fixed sequence of steps. No model was called." },
      },
      steps,
      result,
      polls: 0,
    });
    return id;
  }

  function snapshot(job: Job): Investigation {
    const revealed = job.steps.slice(0, Math.min(job.steps.length, job.polls * stepsPerPoll));
    const lastTime = revealed.at(-1)?.finished_at ?? job.base.created_at;
    if (simulate === "poll-timeout") {
      const stuck = job.steps.slice(0, Math.min(2, revealed.length));
      return { ...job.base, status: job.polls === 0 ? "QUEUED" : "RUNNING", steps: stuck, result: null, error: null, updated_at: stuck.at(-1)?.finished_at ?? job.base.created_at };
    }
    if (simulate === "job-failed" && job.polls >= 2) {
      const done = job.steps.slice(0, 3);
      return {
        ...job.base,
        status: "FAILED",
        steps: done,
        result: null,
        error: {
          code: "FIXTURE_SIMULATED_FAILURE",
          message: "Simulated failure (test data): the investigation worker stopped before it finished. No result was produced.",
        },
        updated_at: done.at(-1)?.finished_at ?? job.base.created_at,
      };
    }
    if (job.polls === 0) return { ...job.base, status: "QUEUED", steps: [], result: null, error: null, updated_at: job.base.created_at };
    const finished = job.polls > Math.ceil(job.steps.length / stepsPerPoll);
    return {
      ...job.base,
      status: finished ? "SUCCEEDED" : "RUNNING",
      steps: revealed,
      result: finished ? job.result : null,
      error: null,
      updated_at: lastTime,
    };
  }

  function latestPolicy(personaId: PersonaId): Policy | null {
    return policies.get(personaId)?.at(-1) ?? null;
  }

  function storePolicy(policy: Policy): Policy {
    policies.set(policy.persona_id, [...(policies.get(policy.persona_id) ?? []), policy]);
    return policy;
  }

  function interpret(request: InterpretRequest): InterpretResponse {
    const scenario = scenarioFor(request.persona_id);
    if (request.text.trim() === "") {
      throw new ApiError("validation", "Enter a goal or preference first.", { status: 422, code: "EMPTY_TEXT" });
    }
    const response = clone(scenario.interpretation);
    for (const answer of request.clarification_answers) {
      const outcome = scenario.clarification_outcomes[answer.option_id];
      response.clarifications = response.clarifications.filter((c) => c.clarification_id !== answer.clarification_id);
      if (!outcome) continue;
      response.proposed_rules.push(...outcome.proposed_rules);
      response.unsupported.push(...outcome.unsupported);
    }
    if (request.text.trim() !== scenario.portfolio_response.scenario_objective_text) {
      response.notes.push(
        "Test data returns the recorded interpretation of the scenario sentence. Your edited wording was not interpreted; the live service interprets what you type.",
      );
    }
    return response;
  }

  function confirm(request: ConfirmRulesRequest): Policy {
    scenarioFor(request.persona_id);
    if (request.confirmations.length === 0) {
      throw new ApiError("validation", "There is no rule to confirm.", { status: 422, code: "NOTHING_TO_CONFIRM" });
    }
    for (const { threshold } of request.confirmations) {
      if (!Number.isFinite(threshold) || threshold < 0 || threshold > 1) {
        throw new ApiError("validation", "A threshold must be between 0% and 100% of the portfolio.", { status: 422, code: "THRESHOLD_OUT_OF_RANGE" });
      }
    }
    const history = policies.get(request.persona_id) ?? [];
    const base = request.base_policy_version === null ? null : history.find((p) => p.policy_version === request.base_policy_version);
    if (request.base_policy_version !== null && !base) {
      throw new ApiError("validation", `Policy version ${request.base_policy_version} does not exist.`, { status: 422, code: "UNKNOWN_POLICY_VERSION" });
    }
    const version = (history.at(-1)?.policy_version ?? 0) + 1;
    const carried = base ? base.rules.filter((r) => r.status === "CONFIRMED") : [];
    const replaced = new Set(request.confirmations.map((c) => c.rule.supersedes_rule_id ?? c.rule.rule_id));
    const confirmed = request.confirmations.map(({ rule, threshold }): Rule => {
      const previous = carried.find((r) => r.rule_id === (rule.supersedes_rule_id ?? rule.rule_id));
      return {
        ...withRuleThreshold(rule, threshold),
        rule_id: previous ? `${previous.rule_id.replace(/-v\d+$/, "")}-v${version}` : rule.rule_id,
        supersedes_rule_id: previous ? previous.rule_id : null,
        status: "CONFIRMED",
      };
    });
    return storePolicy({
      policy_id: `fx-policy-${request.persona_id}`,
      policy_version: version,
      previous_version: base?.policy_version ?? null,
      persona_id: request.persona_id,
      created_at: new Date(Date.parse(FIXTURE_CLOCK_START) - 60_000 + version * 1_000).toISOString().replace(".000Z", "Z"),
      objectives: request.objectives,
      rules: [
        ...carried.filter((r) => !replaced.has(r.rule_id)),
        ...confirmed,
        ...carried.filter((r) => replaced.has(r.rule_id)).map((r): Rule => ({ ...r, status: "SUPERSEDED" })),
      ],
    });
  }

  function challenge(investigationId: string, request: ChallengeRequest): ChallengeResponse {
    const job = jobs.get(investigationId);
    if (!job) throw new ApiError("not_found", "Test data has no record of this investigation.", { status: 404 });
    const scenario = scenarioFor(job.base.persona_id);

    if (request.kind === "CORRECT_FACT") {
      if (!job.result.evidence.some((e) => e.evidence_id === request.evidence_id)) {
        throw new ApiError("validation", "That figure is not part of this report.", { status: 422, code: "UNKNOWN_EVIDENCE" });
      }
      correctionCount += 1;
      return {
        kind: "CORRECT_FACT",
        correction: {
          correction_id: `fx-correction-${correctionCount}`,
          evidence_id: request.evidence_id,
          proposed_value_text: request.proposed_value_text,
          reason_text: request.reason_text,
          status: "UNVERIFIED",
          provenance: { asserted_by: "USER", asserted_at: new Date().toISOString() },
          applied_to_calculation: false,
        },
      };
    }

    if (request.kind === "CLARIFY_PREFERENCE") {
      if (request.text.trim() === "") {
        throw new ApiError("validation", "Describe the preference first.", { status: 422, code: "EMPTY_TEXT" });
      }
      objectiveCount += 1;
      return {
        kind: "CLARIFY_PREFERENCE",
        interpretation: {
          objectives: [
            { objective_id: `obj-${job.base.persona_id}-stated-${objectiveCount}`, original_words: request.text.trim(), origin: "USER_STATED" },
          ],
          proposed_rules: [],
          clarifications: [],
          unsupported: [],
          notes: [
            "Test data does not interpret new wording. Your sentence is stored, unchanged, as a qualitative objective. The live service may also answer with proposed rules or a clarification question.",
          ],
        },
      };
    }

    const policy = (policies.get(job.base.persona_id) ?? []).find((p) => p.policy_version === job.base.policy_version);
    const rule = policy?.rules.find((r) => r.rule_id === request.rule_id && r.status === "CONFIRMED");
    if (!policy || !rule) {
      throw new ApiError("validation", "That rule is not a confirmed rule of the policy this report used.", { status: 422, code: "UNKNOWN_RULE" });
    }
    const previousText = formatFraction(getRuleThreshold(rule));
    const next = confirm({
      persona_id: job.base.persona_id,
      base_policy_version: latestPolicy(job.base.persona_id)?.policy_version ?? policy.policy_version,
      objectives: policy.objectives,
      confirmations: [
        {
          rule: {
            ...rule,
            origin: "USER_STATED",
            original_words: `Change requested by you: ${ruleTypeLabel(rule.rule_type).toLowerCase()} from ${previousText} to ${formatFraction(request.new_threshold)}.`,
            supersedes_rule_id: rule.rule_id,
          },
          threshold: request.new_threshold,
        },
      ],
    });
    const id = createJob(scenario, next, job.base.purchase);
    return { kind: "CHANGE_RULE", policy: next, investigation_id: id, status: "QUEUED" };
  }

  return {
    mode: "fixtures",

    getPortfolio: (personaId, o) =>
      respond(o, () => {
        if (simulate === "portfolio-error") {
          throw new ApiError("server", "Simulated failure (test data): the portfolio could not be loaded.", { status: 503, code: "FIXTURE_SIMULATED_FAILURE" });
        }
        return scenarioFor(personaId).portfolio_response;
      }),

    interpretRules: (request, o) => respond(o, () => interpret(request)),

    confirmRules: (request, o) => respond(o, () => ({ policy: confirm(request) })),

    check: (request: CheckRequest, o) =>
      respond(o, () => {
        if (simulate === "check-error") {
          throw new ApiError("server", "Simulated failure (test data): the preview could not be calculated.", { status: 503, code: "FIXTURE_SIMULATED_FAILURE" });
        }
        const scenario = scenarioFor(request.persona_id);
        requireRecordedPurchase(scenario, request.purchase);
        return { result: evaluateScenario(scenario, request.rules, request.purchase, null, request.is_draft_preview) };
      }),

    createInvestigation: (request: CreateInvestigationRequest, o) =>
      respond(o, () => {
        const scenario = scenarioFor(request.persona_id);
        const existing = jobIdByKey.get(request.idempotency_key);
        if (existing) return { investigation_id: existing, status: snapshot(jobs.get(existing) as Job).status };
        const policy = (policies.get(request.persona_id) ?? []).find((p) => p.policy_version === request.policy_version);
        if (!policy) {
          throw new ApiError("validation", `Policy version ${request.policy_version} does not exist. Confirm at least one rule first.`, { status: 422, code: "UNKNOWN_POLICY_VERSION" });
        }
        requireRecordedPurchase(scenario, request.purchase);
        const id = createJob(scenario, policy, request.purchase);
        jobIdByKey.set(request.idempotency_key, id);
        return { investigation_id: id, status: "QUEUED" as const };
      }),

    getInvestigation: (investigationId, o) =>
      respond(o, () => {
        const job = jobs.get(investigationId);
        if (!job) throw new ApiError("not_found", "Test data has no record of this investigation.", { status: 404 });
        job.polls += 1;
        return snapshot(job);
      }),

    challengeInvestigation: (investigationId, request, o) => respond(o, () => challenge(investigationId, request)),
  };
}
