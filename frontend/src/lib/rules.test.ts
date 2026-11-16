import { describe, expect, it } from "vitest";
import type { Rule } from "@/lib/contracts";
import { FIXTURES } from "@/lib/fixtures";
import {
  draftRule,
  getRuleThreshold,
  isRuleActive,
  limitNoun,
  measureKey,
  originLabel,
  previewRuleSet,
  ruleDirection,
  ruleParametersText,
  ruleStatusLabel,
  ruleSummary,
  ruleTypeLabel,
  thresholdSourceText,
  thresholdText,
  validateThreshold,
} from "./rules";

// Recorded rules only: the scenarios, the recorded interpretation and the recorded policy versions.
const robert = FIXTURES.scenarios.robert?.scenario_rules ?? [];
const mateo = FIXTURES.scenarios.mateo?.scenario_rules ?? [];
const amiraAlternative = FIXTURES.scenarios.amira?.alternative_rule_sets[0]?.rules ?? [];
const drafted = FIXTURES.interpret.mateo.response.proposed_rules;
const policyV1 = FIXTURES.confirmRobertV1.response.policy;
const policyV2 = FIXTURES.challenges.changeRule.response.policy;

function rule(list: Rule[], ruleId: string): Rule {
  const found = list.find((candidate) => candidate.rule_id === ruleId);
  if (!found) throw new Error(`No recorded rule ${ruleId}`);
  return found;
}

const cap = rule(robert, "robert-issuer-cap-1");
const budget = rule(robert, "robert-loss-budget-1");
const energy = rule(mateo, "mateo-excl-energy-1");
const controversy = rule(mateo, "mateo-controversy-1");
const minimum = rule(amiraAlternative, "amira-min-nvidia-1");
const namedCap = rule(amiraAlternative, "amira-max-nvidia-1");
const draftedControversy = rule(drafted, "draft-controversy-1");

describe("rule thresholds", () => {
  it("reads the number of a rule, and no number when the system proposed only its structure", () => {
    expect(getRuleThreshold(cap)).toBe(0.1);
    expect(getRuleThreshold(energy)).toBe(0);
    expect(getRuleThreshold(draftedControversy)).toBeNull();
  });

  it("keeps a zero threshold as zero, distinct from not set", () => {
    expect(thresholdText(energy)).toBe("0.0%");
    expect(thresholdText(draftedControversy)).toBe("Not set");
  });

  it("treats only the minimum rule as a floor", () => {
    expect(ruleDirection("min_issuer_exposure")).toBe("min");
    for (const type of ["max_issuer_exposure", "exclusion", "controversy_exclusion", "scenario_loss_budget"] as const) expect(ruleDirection(type)).toBe("max");
    expect(limitNoun("min_issuer_exposure")).toBe("Minimum");
    expect(limitNoun("scenario_loss_budget")).toBe("Budget");
    expect(limitNoun("max_issuer_exposure")).toBe("Limit");
  });
});

describe("draftRule", () => {
  it("is PROPOSED, keeps the id of the rule it stands in for and carries the number being tried", () => {
    const confirmed = rule(policyV1.rules, "robert-issuer-cap-1");
    const draft = draftRule(confirmed, 0.2);
    expect(draft).toMatchObject({ rule_id: "robert-issuer-cap-1", status: "PROPOSED", threshold: 0.2, confirmed_at: null, confirmed_by: null });
    expect(confirmed.status).toBe("CONFIRMED");
    expect(confirmed.threshold).toBe(0.1);
  });

  it("marks a number the user typed as theirs, and leaves an untouched scenario number as the scenario's", () => {
    expect(draftRule(cap, 0.2)).toMatchObject({ origin: "USER_STATED", threshold_source: "USER_ENTERED", threshold_quote: null });
    expect(draftRule(cap, 0.1)).toMatchObject({ origin: "FICTIONAL_SCENARIO", threshold_source: "FICTIONAL_SCENARIO" });
  });

  it("gives a system-proposed structure the user's number, never one of its own", () => {
    expect(draftRule(draftedControversy, 0)).toMatchObject({ threshold: 0, origin: "USER_STATED", threshold_source: "USER_ENTERED" });
  });
});

describe("measureKey", () => {
  it("is the same for two rules that measure the same thing, whatever their id, wording or number", () => {
    expect(measureKey(draftedControversy)).toBe(measureKey(controversy));
    expect(measureKey(rule(policyV2?.rules ?? [], "robert-issuer-cap-2"))).toBe(measureKey(cap));
  });

  it("differs when the scope differs", () => {
    expect(measureKey(namedCap)).not.toBe(measureKey(cap));
    expect(measureKey(energy)).not.toBe(measureKey(controversy));
  });
});

describe("previewRuleSet", () => {
  it("replaces the rule in force by its draft, in place, and keeps the others confirmed", () => {
    const set = previewRuleSet(policyV1.rules, [draftRule(rule(policyV1.rules, "robert-issuer-cap-1"), 0.2)]);
    expect(set.map((item) => [item.rule_id, item.status, item.threshold])).toEqual([
      ["robert-issuer-cap-1", "PROPOSED", 0.2],
      ["robert-loss-budget-1", "CONFIRMED", 0.1],
    ]);
  });

  it("is the recorded preview request when Robert tries 20% on the single-company limit", () => {
    const set = previewRuleSet(policyV1.rules, [draftRule(rule(policyV1.rules, "robert-issuer-cap-1"), 0.2)]);
    const recordedDrafts = FIXTURES.checkRobertPreview.request.draft_rules ?? [];
    expect(set.map((item) => [measureKey(item), item.status, item.threshold])).toEqual(recordedDrafts.map((item) => [measureKey(item), item.status, item.threshold]));
  });

  it("leaves superseded rules out and appends drafts that replace nothing", () => {
    const set = previewRuleSet(policyV2?.rules ?? [], [draftRule(energy, 0)]);
    expect(set.map((item) => item.rule_id)).toEqual(["robert-issuer-cap-2", "robert-loss-budget-1", "mateo-excl-energy-1"]);
  });

  it("is only the drafts when no policy exists yet", () => {
    expect(previewRuleSet([], [draftRule(cap, 0.2), draftRule(budget, 0.1)]).map((item) => item.status)).toEqual(["PROPOSED", "PROPOSED"]);
  });
});

describe("rule lifecycle", () => {
  it("evaluates only confirmed rules that have a number", () => {
    expect(isRuleActive(cap)).toBe(false);
    expect(isRuleActive(draftedControversy)).toBe(false);
    expect(isRuleActive(rule(policyV1.rules, "robert-issuer-cap-1"))).toBe(true);
    expect(isRuleActive(rule(policyV2?.rules ?? [], "robert-issuer-cap-1"))).toBe(false);
  });

  it("labels a proposed rule as inactive", () => {
    expect(ruleStatusLabel("PROPOSED")).toBe("Proposed: inactive");
    expect(ruleStatusLabel("CONFIRMED")).toBe("Confirmed: active");
    expect(ruleStatusLabel("SUPERSEDED")).toBe("Superseded");
  });

  it("names where a rule and its number came from", () => {
    expect(originLabel("SYSTEM_PROPOSED")).toBe("Proposed by the system");
    expect(originLabel("FICTIONAL_SCENARIO")).toBe("From the fictional scenario");
    expect(originLabel("USER_STATED")).toBe("Stated by you");
    expect(thresholdSourceText(cap)).toBe("Number from the fictional scenario");
    expect(thresholdSourceText(draftedControversy)).toBe("No number yet");
    expect(thresholdSourceText(rule(policyV2?.rules ?? [], "robert-issuer-cap-2"))).toBe("Number entered by you");
  });
});

describe("rule wording", () => {
  it("describes the loss budget as a replay, never as a future or maximum loss", () => {
    const label = ruleTypeLabel("scenario_loss_budget");
    expect(label).toBe("Loss budget in a historical replay");
    expect(label).not.toMatch(/forecast|expected|future|guarantee/i);
    expect(ruleParametersText(budget)).toBe("Scenario: replay of calendar 2022");
  });

  it("says what each recorded rule is set to measure", () => {
    expect(ruleParametersText(cap)).toBe("Applies to every company");
    expect(ruleParametersText(namedCap)).toBe("Applies to one company: NVIDIA");
    expect(ruleParametersText(minimum)).toBe("Applies to one company: NVIDIA");
    expect(ruleParametersText(energy)).toBe("Holdings labelled “Energy” in what the funds report");
    expect(ruleParametersText(controversy)).toBe("Registry records of these kinds: regulatory finding, court ruling, settlement");
  });

  it("summarises a rule with its threshold", () => {
    expect(ruleSummary(cap)).toBe("Maximum exposure to a single company: 10.0%");
    expect(ruleSummary(draftedControversy)).toBe("Exclusion of companies with a controversy record: Not set");
  });
});

describe("validateThreshold", () => {
  it("refuses confirmation without a number", () => {
    expect(validateThreshold(null)).toMatch(/Enter a number/);
  });

  it("accepts 0%, 100% and anything between", () => {
    expect(validateThreshold(0)).toBeNull();
    expect(validateThreshold(0.1)).toBeNull();
    expect(validateThreshold(1)).toBeNull();
  });

  it("refuses values outside 0% to 100%", () => {
    expect(validateThreshold(-0.01)).toMatch(/negative/);
    expect(validateThreshold(1.01)).toMatch(/more than 100%/);
  });
});
