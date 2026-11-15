import type { ExclusionDefinition, Rule, RuleLifecycleStatus, RuleOrigin, RuleType } from "@/lib/contracts";
import { formatFraction, NOT_SET_TEXT, type LimitDirection } from "@/lib/format";

/**
 * Everything the interface needs to know about a rule beyond its raw fields.
 * Components read rules through these helpers so the exact field names of the
 * shared contract are used in one file only.
 */

/** The numeric threshold of a rule, whatever the field is called for its type. Null when not set. */
export function getRuleThreshold(rule: Rule): number | null {
  switch (rule.rule_type) {
    case "max_issuer_exposure":
    case "exclusion":
    case "controversy_exclusion":
      return rule.max_fraction;
    case "min_issuer_exposure":
      return rule.min_fraction;
    case "scenario_loss_budget":
      return rule.max_loss_fraction;
  }
}

/** A copy of the rule carrying the given threshold. The original is never mutated. */
export function withRuleThreshold(rule: Rule, threshold: number | null): Rule {
  switch (rule.rule_type) {
    case "max_issuer_exposure":
    case "exclusion":
    case "controversy_exclusion":
      return { ...rule, max_fraction: threshold };
    case "min_issuer_exposure":
      return { ...rule, min_fraction: threshold };
    case "scenario_loss_budget":
      return { ...rule, max_loss_fraction: threshold };
  }
}

/** Whether the threshold is a ceiling or a floor. */
export function ruleDirection(ruleType: RuleType): LimitDirection {
  return ruleType === "min_issuer_exposure" ? "min" : "max";
}

/** Only CONFIRMED rules with a numeric threshold are evaluated (LEAD_DECISIONS D3). */
export function isRuleActive(rule: Rule): boolean {
  return rule.status === "CONFIRMED" && getRuleThreshold(rule) !== null;
}

const RULE_TYPE_LABELS: Record<RuleType, string> = {
  max_issuer_exposure: "Maximum exposure to a single company",
  min_issuer_exposure: "Minimum exposure to a named company",
  exclusion: "Exclusion of a defined set of holdings",
  controversy_exclusion: "Exclusion of companies with a controversy record",
  scenario_loss_budget: "Loss budget in a historical replay",
};

/** The rule type in plain language. */
export function ruleTypeLabel(ruleType: RuleType): string {
  return RULE_TYPE_LABELS[ruleType];
}

const THRESHOLD_LABELS: Record<RuleType, string> = {
  max_issuer_exposure: "Maximum share of the portfolio",
  min_issuer_exposure: "Minimum share of the portfolio",
  exclusion: "Maximum tolerated share of the portfolio",
  controversy_exclusion: "Maximum tolerated share of the portfolio",
  scenario_loss_budget: "Maximum loss over the replayed period",
};

/** Label of the threshold field for this rule type. */
export function thresholdLabel(ruleType: RuleType): string {
  return THRESHOLD_LABELS[ruleType];
}

const THRESHOLD_HINTS: Record<RuleType, string> = {
  max_issuer_exposure: "Direct holdings plus look-through via equity funds. Exactly at the limit passes.",
  min_issuer_exposure: "Direct holdings plus look-through via equity funds. Exactly at the minimum passes.",
  exclusion: "Enter 0 to tolerate none. Exactly at the limit passes.",
  controversy_exclusion: "Enter 0 to tolerate none. Companies missing from the registry are reported as unknown.",
  scenario_loss_budget: "A test you choose, measured on a replay of the past. It is not a forecast and not a guarantee.",
};

export function thresholdHint(ruleType: RuleType): string {
  return THRESHOLD_HINTS[ruleType];
}

/** Short noun for the limit in result rows: "limit", "minimum" or "budget". */
export function limitNoun(ruleType: RuleType): string {
  if (ruleType === "min_issuer_exposure") return "Minimum";
  if (ruleType === "scenario_loss_budget") return "Budget";
  return "Limit";
}

const ORIGIN_LABELS: Record<RuleOrigin, string> = {
  USER_STATED: "Stated by you",
  FICTIONAL_SCENARIO: "From the fictional scenario",
  SYSTEM_PROPOSED: "Proposed by the system",
};

export function originLabel(origin: RuleOrigin): string {
  return ORIGIN_LABELS[origin];
}

const ORIGIN_DESCRIPTIONS: Record<RuleOrigin, string> = {
  USER_STATED: "You supplied this rule and its number.",
  FICTIONAL_SCENARIO: "The number comes from the invented scenario for this persona. It applies only if you confirm it.",
  SYSTEM_PROPOSED: "The system suggested this kind of rule from your wording. It never suggests the number: you enter it.",
};

export function originDescription(origin: RuleOrigin): string {
  return ORIGIN_DESCRIPTIONS[origin];
}

const STATUS_LABELS: Record<RuleLifecycleStatus, string> = {
  PROPOSED: "Proposed — inactive",
  CONFIRMED: "Confirmed — active",
  SUPERSEDED: "Superseded",
};

export function ruleStatusLabel(status: RuleLifecycleStatus): string {
  return STATUS_LABELS[status];
}

const STATUS_DESCRIPTIONS: Record<RuleLifecycleStatus, string> = {
  PROPOSED: "Not used in any check until you confirm it.",
  CONFIRMED: "Used in every check of this policy version.",
  SUPERSEDED: "Replaced in a later policy version. Kept so earlier reports stay reproducible.",
};

export function ruleStatusDescription(status: RuleLifecycleStatus): string {
  return STATUS_DESCRIPTIONS[status];
}

export function exclusionDefinitionLabel(definition: ExclusionDefinition): string {
  if (definition.kind === "fund_reported_sector") return `Sector “${definition.sector}” as reported in fund holdings files`;
  return `Named companies: ${definition.issuer_ids.join(", ")}`;
}

/** "10.0%" or "Not set" — for rule summaries and diffs. */
export function thresholdText(rule: Rule): string {
  const threshold = getRuleThreshold(rule);
  return threshold === null ? NOT_SET_TEXT : formatFraction(threshold);
}

/** One line naming a rule and its threshold, e.g. for the timeline and policy summaries. */
export function ruleSummary(rule: Rule): string {
  return `${ruleTypeLabel(rule.rule_type)}: ${thresholdText(rule)}`;
}

/** Why a threshold typed by the user cannot be confirmed, or null when it can. */
export function validateThreshold(value: number | null): string | null {
  if (value === null) return "Enter a number before confirming. This rule has no threshold yet.";
  if (value < 0) return "The threshold cannot be negative.";
  if (value > 1) return "The threshold cannot be more than 100% of the portfolio.";
  return null;
}
