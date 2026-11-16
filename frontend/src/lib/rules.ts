import type { ControversyNature, ExclusionDefinition, Rule, RuleOrigin, RuleStatus, RuleType } from "@/lib/contracts";
import { canonical } from "@/lib/canonical";
import { formatDate, formatFraction, NOT_SET_TEXT, type LimitDirection } from "@/lib/format";

/**
 * Everything the interface needs to know about a rule beyond its raw fields:
 * wording, and the two operations that build a rule to send (a draft for a
 * preview, a threshold change). Nothing here evaluates a rule.
 */

/** The number of a rule. Null when it has none yet (system-proposed structures never carry one). */
export function getRuleThreshold(rule: Rule): number | null {
  return rule.threshold;
}

/**
 * The rule as a DRAFT carrying a number the user is trying out, for a preview
 * (POST /check with `draft_rules`). It is PROPOSED, so nothing about it is
 * confirmed, and it keeps the id of the rule it stands in for.
 */
export function draftRule(rule: Rule, threshold: number): Rule {
  const unchanged = rule.threshold !== null && rule.threshold === threshold;
  return {
    ...rule,
    threshold,
    // A number the user typed is theirs; an untouched scenario or quoted number keeps its provenance.
    ...(unchanged && rule.threshold_source !== null
      ? {}
      : { origin: "USER_STATED" as const, threshold_source: "USER_ENTERED" as const, threshold_quote: null }),
    status: "PROPOSED",
    confirmed_at: null,
    confirmed_by: null,
    superseded_by_rule_id: null,
  };
}

/** What a rule measures, whatever its id, wording or number. Two rules with the same key are the same check. */
export function measureKey(rule: Rule): string {
  return `${rule.rule_type}|${canonical(rule.parameters)}`;
}

/**
 * The rule set a preview evaluates: the rules in force, each replaced in place
 * by the draft that stands in for it (same id or same measure), then any other
 * draft. Sent as `draft_rules` to POST /check; nothing is stored.
 */
export function previewRuleSet(inForce: Rule[], drafts: Rule[]): Rule[] {
  const used = new Set<string>();
  const rules = inForce
    .filter((rule) => rule.status === "CONFIRMED")
    .map((rule) => {
      const draft = drafts.find((candidate) => candidate.rule_id === rule.rule_id || measureKey(candidate) === measureKey(rule));
      if (!draft) return rule;
      used.add(draft.rule_id);
      return draft;
    });
  return [...rules, ...drafts.filter((draft) => !used.has(draft.rule_id))];
}

/** Whether the threshold is a ceiling or a floor. */
export function ruleDirection(ruleType: RuleType): LimitDirection {
  return ruleType === "min_issuer_exposure" ? "min" : "max";
}

/** Only CONFIRMED rules with a number are evaluated (contracts/SEMANTICS.md §3). */
export function isRuleActive(rule: Rule): boolean {
  return rule.status === "CONFIRMED" && rule.threshold !== null;
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

const NATURE_LABELS: Record<ControversyNature, string> = {
  ALLEGATION: "allegation",
  REGULATORY_FINDING: "regulatory finding",
  COURT_RULING: "court ruling",
  SETTLEMENT: "settlement",
  COMPANY_DISCLOSURE: "company disclosure",
};

export function exclusionDefinitionLabel(definition: ExclusionDefinition): string {
  if (definition.kind === "fund_reported_sector") return `Holdings labelled “${definition.sector}” in what the funds report`;
  return `Named companies: ${definition.issuer_ids.join(", ")}`;
}

/** What exactly this rule is set to measure, from its parameters. One short line. */
export function ruleParametersText(rule: Rule): string {
  switch (rule.rule_type) {
    case "max_issuer_exposure":
      return rule.parameters.issuer_scope === "any" ? "Applies to every company" : `Applies to one company: ${rule.parameters.issuer_scope}`;
    case "min_issuer_exposure":
      return `Applies to one company: ${rule.parameters.issuer_id}`;
    case "exclusion":
      return exclusionDefinitionLabel(rule.parameters.definition);
    case "controversy_exclusion": {
      const natures = rule.parameters.criteria.natures.map((nature) => NATURE_LABELS[nature]).join(", ");
      const since = rule.parameters.criteria.event_date_from;
      return `Registry records of these kinds: ${natures}${since ? `, dated ${formatDate(since)} or later` : ""}`;
    }
    case "scenario_loss_budget":
      return rule.parameters.scenario_id === "replay_2022" ? "Scenario: replay of calendar 2022" : `Scenario: ${rule.parameters.scenario_id}`;
  }
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

/** Where the number of a rule comes from, in words. */
export function thresholdSourceText(rule: Rule): string {
  switch (rule.threshold_source) {
    case "USER_WORDS":
      return rule.threshold_quote ? `Number taken from your words: “${rule.threshold_quote}”` : "Number taken from your words";
    case "USER_ENTERED":
      return "Number entered by you";
    case "FICTIONAL_SCENARIO":
      return "Number from the fictional scenario";
    case null:
      return "No number yet";
  }
}

const STATUS_LABELS: Record<RuleStatus, string> = {
  PROPOSED: "Proposed: inactive",
  CONFIRMED: "Confirmed: active",
  SUPERSEDED: "Superseded",
};

export function ruleStatusLabel(status: RuleStatus): string {
  return STATUS_LABELS[status];
}

const STATUS_DESCRIPTIONS: Record<RuleStatus, string> = {
  PROPOSED: "Not used in any check until you confirm it.",
  CONFIRMED: "Used in every check of this policy version.",
  SUPERSEDED: "Replaced in a later policy version. Kept so earlier reports stay reproducible.",
};

export function ruleStatusDescription(status: RuleStatus): string {
  return STATUS_DESCRIPTIONS[status];
}

/** "10.0%" or "Not set" — for rule summaries and diffs. */
export function thresholdText(rule: Rule): string {
  return rule.threshold === null ? NOT_SET_TEXT : formatFraction(rule.threshold);
}

/** One line naming a rule and its threshold, e.g. for policy summaries. */
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
