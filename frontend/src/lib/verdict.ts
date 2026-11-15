import type {
  CheckResult,
  CoverageStatus,
  EvidenceRecord,
  InvestigationStatus,
  Policy,
  Rule,
  RuleEvaluation,
  RuleResult,
  SourceRecord,
  VerdictStatus,
} from "@/lib/contracts";

/**
 * Wording and counting for results. The statuses themselves always come from
 * the service; nothing here decides PASS, FAIL or UNKNOWN.
 */

export interface VerdictCounts {
  pass: number;
  fail: number;
  unknown: number;
  total: number;
}

/** The evaluation that describes the request: after the purchase when there is one. */
export function decisiveEvaluation(ruleResult: RuleResult): RuleEvaluation {
  return ruleResult.proposed ?? ruleResult.starting;
}

export function countStatuses(statuses: VerdictStatus[]): VerdictCounts {
  const counts: VerdictCounts = { pass: 0, fail: 0, unknown: 0, total: statuses.length };
  for (const status of statuses) {
    if (status === "PASS") counts.pass += 1;
    else if (status === "FAIL") counts.fail += 1;
    else counts.unknown += 1;
  }
  return counts;
}

export function countResult(result: CheckResult, phase: "decisive" | "starting" = "decisive"): VerdictCounts {
  return countStatuses(result.rule_results.map((r) => (phase === "starting" ? r.starting : decisiveEvaluation(r)).status));
}

export type HeadlineTone = "fail" | "unknown" | "pass" | "none";

export interface VerdictHeadline {
  tone: HeadlineTone;
  title: string;
  detail: string;
}

const plural = (n: number, one: string, many: string) => (n === 1 ? one : many);

/**
 * The headline of a result. It can only say the rules are respected when every
 * checked rule passed: a single UNKNOWN makes the headline "not determined",
 * and a FAIL is always stated even when other checks are unknown.
 */
export function verdictHeadline(counts: VerdictCounts): VerdictHeadline {
  const { pass, fail, unknown, total } = counts;
  if (total === 0) {
    return {
      tone: "none",
      title: "No confirmed rule was checked",
      detail: "A result needs at least one confirmed rule with a threshold.",
    };
  }
  if (fail > 0) {
    return {
      tone: "fail",
      title: `${fail} of ${total} confirmed ${plural(total, "rule", "rules")} ${plural(fail, "is", "are")} not respected`,
      detail:
        unknown > 0
          ? `${unknown} more could not be determined and ${pass} passed. The unknown ${plural(unknown, "check is", "checks are")} not counted as passed.`
          : `${pass} passed and none are unknown.`,
    };
  }
  if (unknown > 0) {
    return {
      tone: "unknown",
      title: `Not determined: ${unknown} of ${total} confirmed ${plural(total, "rule", "rules")} could not be checked`,
      detail: `${pass} passed and none failed, but this is not a pass. Missing data is never treated as zero.`,
    };
  }
  return {
    tone: "pass",
    title: total === 1 ? "The one confirmed rule is respected" : `All ${total} confirmed rules are respected`,
    detail: "Every confirmed rule was checked and none is unknown.",
  };
}

const STATUS_TEXT: Record<VerdictStatus, string> = { PASS: "Pass", FAIL: "Fail", UNKNOWN: "Unknown" };

export function statusText(status: VerdictStatus): string {
  return STATUS_TEXT[status];
}

const JOB_STATUS_TEXT: Record<InvestigationStatus, string> = {
  QUEUED: "Queued",
  RUNNING: "Running",
  SUCCEEDED: "Completed",
  FAILED: "Failed",
};

export function jobStatusText(status: InvestigationStatus): string {
  return JOB_STATUS_TEXT[status];
}

export function isTerminalJobStatus(status: InvestigationStatus): boolean {
  return status === "SUCCEEDED" || status === "FAILED";
}

const COVERAGE_TEXT: Record<CoverageStatus | "NOT_APPLICABLE", string> = {
  COVERED: "Complete",
  PARTIAL: "Partial",
  MISSING: "Missing",
  NOT_APPLICABLE: "Not applicable",
};

export function coverageText(status: CoverageStatus | "NOT_APPLICABLE"): string {
  return COVERAGE_TEXT[status];
}

export function findEvidence(result: CheckResult, evidenceId: string): EvidenceRecord | undefined {
  return result.evidence.find((record) => record.evidence_id === evidenceId);
}

export function findSource(result: CheckResult, sourceId: string): SourceRecord | undefined {
  return result.sources.find((source) => source.source_id === sourceId);
}

export function findRule(policy: Policy | null | undefined, ruleId: string): Rule | undefined {
  return policy?.rules.find((rule) => rule.rule_id === ruleId);
}

/** The rules of a policy version that are in force. */
export function activeRules(policy: Policy | null | undefined): Rule[] {
  return policy?.rules.filter((rule) => rule.status === "CONFIRMED") ?? [];
}

export type RuleChangeKind = "CHANGED" | "ADDED" | "REMOVED" | "UNCHANGED";

export interface RuleDiffRow {
  kind: RuleChangeKind;
  before: Rule | null;
  after: Rule | null;
}

/**
 * Compares the rules in force in two policy versions. A rule of the newer
 * version is paired with the rule it supersedes, or with the same rule id.
 */
export function diffPolicies(older: Policy, newer: Policy): RuleDiffRow[] {
  const before = activeRules(older);
  const after = activeRules(newer);
  const matched = new Set<string>();
  const rows: RuleDiffRow[] = [];
  for (const rule of after) {
    const previous = before.find((b) => b.rule_id === rule.supersedes_rule_id) ?? before.find((b) => b.rule_id === rule.rule_id);
    if (!previous) {
      rows.push({ kind: "ADDED", before: null, after: rule });
      continue;
    }
    matched.add(previous.rule_id);
    rows.push({ kind: previous.rule_id === rule.rule_id ? "UNCHANGED" : "CHANGED", before: previous, after: rule });
  }
  for (const rule of before) {
    if (!matched.has(rule.rule_id)) rows.push({ kind: "REMOVED", before: rule, after: null });
  }
  const order: Record<RuleChangeKind, number> = { CHANGED: 0, ADDED: 1, REMOVED: 2, UNCHANGED: 3 };
  return rows.sort((a, b) => order[a.kind] - order[b.kind]);
}

/** Pairs the rule results of two reports so they can be read side by side. */
export function pairRuleResults(
  olderPolicy: Policy,
  newerPolicy: Policy,
  older: CheckResult,
  newer: CheckResult,
): { diff: RuleDiffRow; before: RuleResult | null; after: RuleResult | null }[] {
  return diffPolicies(olderPolicy, newerPolicy).map((diff) => ({
    diff,
    before: diff.before ? (older.rule_results.find((r) => r.rule_id === diff.before?.rule_id) ?? null) : null,
    after: diff.after ? (newer.rule_results.find((r) => r.rule_id === diff.after?.rule_id) ?? null) : null,
  }));
}
