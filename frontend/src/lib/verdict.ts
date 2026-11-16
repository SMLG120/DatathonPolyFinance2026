import {
  TERMINAL_JOB_STATUSES,
  type BindingConstraint,
  type CheckResult,
  type CoverageStatus,
  type EvidenceRecord,
  type JobStatus,
  type Policy,
  type Rule,
  type RuleResult,
  type RuleType,
  type Summary,
  type UnknownCause,
  type VerdictStatus,
} from "@/lib/contracts";
import { getLocale, t } from "@/lib/i18n";

/**
 * Wording and counting for results. The statuses and the summary always come
 * from the service; nothing here decides PASS, FAIL or UNKNOWN.
 */

export interface VerdictCounts {
  pass: number;
  fail: number;
  unknown: number;
  /** `summary.rules_evaluated`: how many confirmed rules the engine evaluated. */
  total: number;
}

/** The engine's own counts for the portfolio after the purchase. Nothing is counted here. */
/** French agreement: 0 and 1 take the singular ("0 règle respectée", "2 règles respectées"). */
function frN(count: number, one: string, many: string): string {
  return count <= 1 ? one : many;
}

export function summaryCounts(summary: Summary): VerdictCounts {
  const { pass, fail, unknown } = summary.counts;
  return { pass, fail, unknown, total: summary.rules_evaluated };
}

export type HeadlineTone = "fail" | "unknown" | "pass" | "none";

export interface VerdictHeadline {
  tone: HeadlineTone;
  title: string;
  detail: string;
}

const plural = (n: number, one: string, many: string) => (n === 1 ? one : many);

/**
 * The headline of a result, worded from the engine's summary.
 *
 * It says the rules are respected only when the engine's headline is ALL_PASS
 * and its counts agree: a single UNKNOWN or FAIL in the counts makes that
 * headline impossible, whatever the `headline` member says.
 */
export function verdictHeadline(summary: Summary): VerdictHeadline {
  const french = getLocale() === "fr";
  const { pass, fail, unknown, total } = summaryCounts(summary);
  switch (summary.headline) {
    case "EXECUTION_ERROR":
      return { tone: "none", title: t("The check could not be run"), detail: t("No rule was evaluated, so there is no result to show.") };
    case "INVALID_REQUEST":
      return { tone: "none", title: t("This request cannot be evaluated"), detail: t("No rule was evaluated, so there is no result to show.") };
    case "NO_RULES_EVALUATED":
      return { tone: "none", title: t("No confirmed rule was checked"), detail: t("A result needs at least one confirmed rule with a threshold.") };
    case "POLICY_CONFLICT":
      return {
        tone: "none",
        title: t("Two confirmed rules cannot both be met"),
        detail: french
          ? `Les règles ont tout de même été vérifiées une à une : ${fail} ${frN(fail, "non respectée", "non respectées")}, ${unknown} ${frN(unknown, "indéterminée", "indéterminées")}, ${pass} ${frN(pass, "respectée", "respectées")}.`
          : `The rules were still checked one by one: ${fail} not respected, ${unknown} unknown, ${pass} passed.`,
      };
    case "HAS_FAIL":
    case "NO_FAIL_BUT_UNKNOWN":
    case "ALL_PASS":
      break;
  }
  const inconsistent: VerdictHeadline = {
    tone: "none",
    title: t("The summary of this result is inconsistent"),
    detail: t("The counts and the headline sent by the service disagree, so no overall statement is shown."),
  };
  if (total === 0) {
    return { tone: "none", title: t("No confirmed rule was checked"), detail: t("A result needs at least one confirmed rule with a threshold.") };
  }
  if (summary.headline === "HAS_FAIL") {
    if (fail === 0) return inconsistent;
    return {
      tone: "fail",
      title: french
        ? `${fail} sur ${total} ${frN(total, "règle confirmée", "règles confirmées")} ${frN(fail, "n’est pas respectée", "ne sont pas respectées")}`
        : `${fail} of ${total} confirmed ${plural(total, "rule", "rules")} ${plural(fail, "is", "are")} not respected`,
      detail:
        unknown > 0
          ? french
            ? `${unknown} ${frN(unknown, "autre n’a pas pu être déterminée", "autres n’ont pas pu être déterminées")} et ${pass} ${frN(pass, "est respectée", "sont respectées")}. Les vérifications indéterminées ne sont pas comptées comme respectées.`
            : `${unknown} more could not be determined and ${pass} passed. The unknown ${plural(unknown, "check is", "checks are")} not counted as passed.`
          : french
            ? `${pass} ${frN(pass, "règle respectée", "règles respectées")}, et aucune n’est indéterminée.`
            : `${pass} passed and none are unknown.`,
    };
  }
  if (summary.headline === "NO_FAIL_BUT_UNKNOWN") {
    if (fail > 0 || unknown === 0) return inconsistent;
    return {
      tone: "unknown",
      title: french
        ? `Indéterminé : ${unknown} sur ${total} ${frN(total, "règle confirmée", "règles confirmées")} ${frN(unknown, "n’a pas pu être vérifiée", "n’ont pas pu être vérifiées")}`
        : `Not determined: ${unknown} of ${total} confirmed ${plural(total, "rule", "rules")} could not be checked`,
      detail: french
        ? `${pass} ${frN(pass, "règle respectée", "règles respectées")}, aucune en échec, mais cela ne signifie pas que tout est respecté. Les données manquantes ne sont jamais considérées comme nulles.`
        : `${pass} passed and none failed, but this is not a pass. Missing data is never treated as zero.`,
    };
  }
  // ALL_PASS: said only when the engine's counts agree that nothing failed and nothing is unknown.
  if (fail > 0 || unknown > 0) return inconsistent;
  return {
    tone: "pass",
    title: french
      ? total === 1 ? "L’unique règle confirmée est respectée" : `Les ${total} règles confirmées sont respectées`
      : total === 1 ? "The one confirmed rule is respected" : `All ${total} confirmed rules are respected`,
    detail: t("Every confirmed rule was checked and none is unknown."),
  };
}

const STATUS_TEXT: Record<VerdictStatus, string> = { PASS: "Pass", FAIL: "Fail", UNKNOWN: "Unknown" };

export function statusText(status: VerdictStatus): string {
  return t(STATUS_TEXT[status]);
}

const JOB_STATUS_TEXT: Record<JobStatus, string> = {
  QUEUED: "Queued",
  RUNNING: "Running",
  SUCCEEDED: "Completed",
  FAILED: "Failed",
};

export function jobStatusText(status: JobStatus): string {
  return t(JOB_STATUS_TEXT[status]);
}

export function isTerminalJobStatus(status: JobStatus): boolean {
  return TERMINAL_JOB_STATUSES.includes(status);
}

const COVERAGE_TEXT: Record<CoverageStatus, string> = {
  COVERED: "Complete",
  PARTIAL: "Partial",
  MISSING: "Missing",
};

export function coverageText(status: CoverageStatus): string {
  return t(COVERAGE_TEXT[status]);
}

const UNKNOWN_CAUSE_TEXT: Record<UnknownCause, string> = {
  PARTIAL_HOLDINGS: "a fund's holdings file reports only part of the fund",
  MISSING_HOLDINGS: "a fund has no holdings file",
  UNCLASSIFIED_SECTOR: "some holdings carry no sector label",
  REGISTRY_ABSENCE: "companies without a registry record are not assessed",
  INSUFFICIENT_HISTORY: "price history is missing for the replayed period",
};

/** Why part of a measurement is unknown, in words. */
export function unknownCauseText(cause: UnknownCause): string {
  return t(UNKNOWN_CAUSE_TEXT[cause]);
}

export function findEvidence(result: CheckResult, evidenceId: string): EvidenceRecord | undefined {
  return result.evidence.find((record) => record.evidence_id === evidenceId);
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

/** What stops a larger purchase: a rule or the cash available. */
export function bindingConstraintText(constraint: BindingConstraint, ruleLabel: (ruleId: string) => string): string {
  if (constraint.type === "CASH") return t("the cash available");
  return constraint.rule_id ? `${t("the rule “")}${ruleLabel(constraint.rule_id)}”` : t("a confirmed rule");
}

/** What the measured quantity of a rule type is called in result rows. */
export function measuredNoun(ruleType: RuleType): string {
  switch (ruleType) {
    case "max_issuer_exposure":
      return t("Largest exposure to one company");
    case "min_issuer_exposure":
      return t("Exposure to the named company");
    case "exclusion":
      return t("Share in the excluded holdings");
    case "controversy_exclusion":
      return t("Share in companies with a matching record");
    case "scenario_loss_budget":
      return t("Loss over the replayed period");
  }
}

/** The display name of a company in a result: the one the exposure rows carry, else its id. */
export function issuerName(result: CheckResult, issuerId: string): string {
  return result.exposure?.issuers.find((issuer) => issuer.issuer_id === issuerId)?.name ?? issuerId;
}
