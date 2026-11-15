import { describe, expect, it } from "vitest";
import type { Rule } from "@/lib/contracts";
import {
  getRuleThreshold,
  isRuleActive,
  originLabel,
  ruleDirection,
  ruleStatusLabel,
  ruleSummary,
  ruleTypeLabel,
  thresholdText,
  validateThreshold,
  withRuleThreshold,
} from "./rules";

const base = {
  rule_id: "r",
  status: "PROPOSED",
  origin: "SYSTEM_PROPOSED",
  original_words: "words",
  scope_description: "scope",
  objective_id: null,
  supersedes_rule_id: null,
} as const;

const rules: Rule[] = [
  { ...base, rule_type: "max_issuer_exposure", issuer_scope: "any", max_fraction: null },
  { ...base, rule_type: "min_issuer_exposure", issuer_scope: "issuer-x", min_fraction: null },
  { ...base, rule_type: "exclusion", definition: { kind: "fund_reported_sector", sector: "Energy" }, max_fraction: null },
  { ...base, rule_type: "controversy_exclusion", criteria_text: "any record", max_fraction: null },
  { ...base, rule_type: "scenario_loss_budget", scenario_id: "replay_2022", max_loss_fraction: null },
];

describe("rule thresholds", () => {
  it.each(rules)("reads and writes the threshold of a $rule_type rule", (rule) => {
    expect(getRuleThreshold(rule)).toBeNull();
    const updated = withRuleThreshold(rule, 0.15);
    expect(getRuleThreshold(updated)).toBe(0.15);
    // The original is not mutated.
    expect(getRuleThreshold(rule)).toBeNull();
    expect(updated.rule_type).toBe(rule.rule_type);
  });

  it("keeps a zero threshold as zero, distinct from not set", () => {
    const zero = withRuleThreshold(rules[2]!, 0);
    expect(getRuleThreshold(zero)).toBe(0);
    expect(thresholdText(zero)).toBe("0.0%");
    expect(thresholdText(rules[2]!)).toBe("Not set");
  });

  it("treats only the minimum rule as a floor", () => {
    expect(rules.map((r) => ruleDirection(r.rule_type))).toEqual(["max", "min", "max", "max", "max"]);
  });
});

describe("rule lifecycle", () => {
  it("evaluates only confirmed rules that have a number", () => {
    const withNumber = withRuleThreshold(rules[0]!, 0.1);
    expect(isRuleActive(withNumber)).toBe(false); // still PROPOSED
    expect(isRuleActive({ ...withNumber, status: "CONFIRMED" })).toBe(true);
    expect(isRuleActive({ ...rules[0]!, status: "CONFIRMED" })).toBe(false); // confirmed but no number
    expect(isRuleActive({ ...withNumber, status: "SUPERSEDED" })).toBe(false);
  });

  it("labels a proposed rule as inactive", () => {
    expect(ruleStatusLabel("PROPOSED")).toBe("Proposed — inactive");
    expect(ruleStatusLabel("CONFIRMED")).toBe("Confirmed — active");
    expect(ruleStatusLabel("SUPERSEDED")).toBe("Superseded");
  });

  it("names where a rule came from", () => {
    expect(originLabel("USER_STATED")).toBe("Stated by you");
    expect(originLabel("FICTIONAL_SCENARIO")).toBe("From the fictional scenario");
    expect(originLabel("SYSTEM_PROPOSED")).toBe("Proposed by the system");
  });
});

describe("rule wording", () => {
  it("describes the loss budget as a replay, never as a future or maximum loss", () => {
    const label = ruleTypeLabel("scenario_loss_budget");
    expect(label).toMatch(/historical replay/i);
    expect(label).not.toMatch(/future|maximum future loss|forecast/i);
  });

  it("summarises a rule with its threshold", () => {
    expect(ruleSummary(withRuleThreshold(rules[0]!, 0.1))).toBe("Maximum exposure to a single company: 10.0%");
    expect(ruleSummary(rules[0]!)).toBe("Maximum exposure to a single company: Not set");
  });
});

describe("validateThreshold", () => {
  it("refuses confirmation without a number", () => {
    expect(validateThreshold(null)).toMatch(/enter a number/i);
  });

  it("accepts 0%, 100% and anything between", () => {
    expect(validateThreshold(0)).toBeNull();
    expect(validateThreshold(0.1)).toBeNull();
    expect(validateThreshold(1)).toBeNull();
  });

  it("refuses values outside 0% to 100%", () => {
    expect(validateThreshold(-0.01)).not.toBeNull();
    expect(validateThreshold(1.01)).not.toBeNull();
  });
});
