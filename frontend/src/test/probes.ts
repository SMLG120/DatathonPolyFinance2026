/**
 * Test inputs.
 *
 * `recorded` hands out copies of the recorded contract bodies. Every test
 * that can use a recording uses one.
 *
 * `probe` holds the few inputs no recording covers. Each is a recorded body
 * with named fields replaced, built here and nowhere else, so that a test can
 * show the screen READS a value instead of working it out, or does not draw a
 * verdict it must not draw. None is a result the product ever shows, and none
 * is written out as a whole: `src/guard.test.ts` allows result fields to be
 * assigned in this one file only, and checks it never writes a full result.
 */
import type { CheckResult, Headline, InvestigationJob, Summary } from "@/lib/contracts";
import { FIXTURES } from "@/lib/fixtures";

const copy = <T>(value: T): T => structuredClone(value);

function resultOf(job: InvestigationJob): CheckResult {
  if (!job.result) throw new Error("This recorded job has no result.");
  return job.result;
}

export const recorded = {
  robertJob: () => copy(FIXTURES.jobs.robertSucceeded.response),
  robertResult: () => resultOf(copy(FIXTURES.jobs.robertSucceeded.response)),
  robertAfterChangeJob: () => copy(FIXTURES.jobs.robertAfterChallenge.response),
  robertPolicyV1: () => copy(FIXTURES.confirmRobertV1.response.policy),
  robertPreview: () => copy(FIXTURES.checkRobertPreview.response),
  robertPreviewRequest: () => copy(FIXTURES.checkRobertPreview.request),
  mateoJob: () => copy(FIXTURES.jobs.mateoSucceeded.response),
  mateoResult: () => resultOf(copy(FIXTURES.jobs.mateoSucceeded.response)),
  mateoPreviewUnknown: () => copy(FIXTURES.checkMateoPreviewUnknown.response),
  mateoPreviewUnknownRequest: () => copy(FIXTURES.checkMateoPreviewUnknown.request),
  invalidRequest: () => copy(FIXTURES.checkInvalidRequest.response),
  failedJob: () => copy(FIXTURES.jobs.failed.response),
  robertPortfolio: () => copy(FIXTURES.portfolioRobert.response),
};

/** Figures that cannot be obtained from one another by any arithmetic. A screen that shows them read them. */
export const SENTINEL = {
  startingWeight: 0.011,
  additionalPurchase: 0.777,
  cashBefore: 0.666,
  cashAfter: 0.555,
  pass: 7,
  fail: 8,
  unknown: 9,
  rulesEvaluated: 24,
  startingBreaches: 5,
  maxFinal: 0.4321,
  maxAdditional: 0.1234,
} as const;

export const probe = {
  /**
   * A recorded summary with its headline and counts replaced. The recordings
   * hold no ALL_PASS result and no summary whose counts contradict its
   * headline; the wording of both cases still has to be tested.
   */
  summaryWith(headline: Headline, counts: { pass: number; fail: number; unknown: number; evaluated: number }): Summary {
    const summary = recorded.robertResult().summary;
    summary.headline = headline;
    summary.counts.pass = counts.pass;
    summary.counts.fail = counts.fail;
    summary.counts.unknown = counts.unknown;
    summary.rules_evaluated = counts.evaluated;
    return summary;
  },

  /**
   * Robert's recorded job with mutually inconsistent figures in `feasibility`,
   * `summary` and `max_compliant`: cash before minus the purchase is not cash
   * after, and the counts are not the number of rule results listed.
   */
  sentinelFigures(): InvestigationJob {
    const job = recorded.robertJob();
    const result = resultOf(job);
    if (!result.feasibility || result.max_compliant?.status !== "SUPPORTED") throw new Error("The recording changed: feasibility and a supported maximum are expected.");
    result.feasibility.starting_direct_weight = SENTINEL.startingWeight;
    result.feasibility.additional_purchase = SENTINEL.additionalPurchase;
    result.feasibility.cash_before = SENTINEL.cashBefore;
    result.feasibility.cash_after = SENTINEL.cashAfter;
    result.summary.counts.pass = SENTINEL.pass;
    result.summary.counts.fail = SENTINEL.fail;
    result.summary.counts.unknown = SENTINEL.unknown;
    result.summary.rules_evaluated = SENTINEL.rulesEvaluated;
    result.summary.starting_portfolio_breaches = SENTINEL.startingBreaches;
    result.max_compliant.final_direct_weight = SENTINEL.maxFinal;
    result.max_compliant.additional_purchase = SENTINEL.maxAdditional;
    return job;
  },

  /**
   * Robert's recorded job, rule results and all, carrying the execution block
   * of the recorded invalid request. No recording has rule results together
   * with an execution status that is not OK; this shows what is drawn if one
   * ever arrives.
   */
  notExecutedWithRuleResults(): InvestigationJob {
    const job = recorded.robertJob();
    resultOf(job).execution = recorded.invalidRequest().execution;
    return job;
  },

  /** Robert's recorded result with no exposure block, or with one that lists no company. */
  withoutExposure(kind: "null" | "empty"): CheckResult {
    const result = recorded.robertResult();
    if (kind === "null") result.exposure = null;
    else if (result.exposure) result.exposure.issuers = [];
    return result;
  },

  /** Robert's recorded result with one fund's reported share replaced, status PARTIAL. */
  withCoverage(fundId: string, fraction: number): CheckResult {
    const result = recorded.robertResult();
    const fund = result.data_coverage.find((candidate) => candidate.fund_id === fundId);
    if (!fund) throw new Error(`The recording lists no fund ${fundId}.`);
    fund.coverage_fraction = fraction;
    fund.status = "PARTIAL";
    return result;
  },

  /** Robert's recorded result with the formula text of one evidence record replaced. */
  withFormula(evidenceId: string, formula: string): CheckResult {
    const result = recorded.robertResult();
    const record = result.evidence.find((candidate) => candidate.evidence_id === evidenceId);
    if (!record) throw new Error(`The recording has no evidence record ${evidenceId}.`);
    record.formula = formula;
    return result;
  },

  /** Robert's recorded result without one evidence record that other records still name as an input. */
  withoutEvidenceRecord(evidenceId: string): CheckResult {
    const result = recorded.robertResult();
    const kept = result.evidence.filter((candidate) => candidate.evidence_id !== evidenceId);
    if (kept.length === result.evidence.length) throw new Error(`The recording has no evidence record ${evidenceId}.`);
    result.evidence = kept;
    return result;
  },

  /**
   * Robert's recorded exposure with the proven total and the possible total of
   * one company after the purchase replaced by figures that no sum of its
   * parts gives.
   */
  withIssuerTotals(issuerId: string, lower: number, upper: number): CheckResult {
    const result = recorded.robertResult();
    const issuer = result.exposure?.issuers.find((candidate) => candidate.issuer_id === issuerId);
    if (!issuer) throw new Error(`The recorded exposure lists no company ${issuerId}.`);
    issuer.proposed.lower = lower;
    issuer.proposed.upper = upper;
    return result;
  },

  /**
   * Robert's recorded result with the replay marked as not computable: no
   * measures, and the named instruments without a usable price history. No
   * recording holds this status.
   */
  withoutReplayHistory(missing: string[]): CheckResult {
    const result = recorded.robertResult();
    if (!result.scenario) throw new Error("The recording changed: a replay is expected.");
    result.scenario.status = "INSUFFICIENT_HISTORY";
    result.scenario.starting = null;
    result.scenario.proposed = null;
    result.scenario.target_instrument_return = null;
    result.scenario.missing_instruments = missing;
    return result;
  },

  /** Robert's recorded job carrying one of the results above. */
  robertJobWith(result: CheckResult): InvestigationJob {
    const job = recorded.robertJob();
    job.result = result;
    return job;
  },

  /** Robert's recorded job with the text of one explanation sentence replaced. */
  withStatementText(statementId: string, text: string): InvestigationJob {
    const job = recorded.robertJob();
    const statement = job.explanation.find((candidate) => candidate.statement_id === statementId);
    if (!statement) throw new Error(`The recording has no statement ${statementId}.`);
    statement.text = text;
    return job;
  },
};
