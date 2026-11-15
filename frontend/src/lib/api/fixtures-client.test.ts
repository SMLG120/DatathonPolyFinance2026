import { describe, expect, it } from "vitest";
import type { Investigation, PersonaId, Policy, Rule } from "@/lib/contracts";
import { getRuleThreshold, withRuleThreshold } from "@/lib/rules";
import type { ApiClient } from "./client";
import { ApiError } from "./errors";
import { createFixturesClient, type FixturesClientOptions } from "./fixtures-client";

const make = (options: FixturesClientOptions = {}) => createFixturesClient({ latencyMs: 0, ...options });

async function failure(promise: Promise<unknown>): Promise<ApiError> {
  try {
    await promise;
  } catch (error) {
    if (error instanceof ApiError) return error;
    throw error;
  }
  throw new Error("expected the request to fail");
}

async function proposedRules(api: ApiClient, persona: PersonaId, answers: { clarification_id: string; option_id: string }[] = []) {
  const { portfolio: _portfolio, scenario_objective_text } = await api.getPortfolio(persona);
  void _portfolio;
  return api.interpretRules({ persona_id: persona, text: scenario_objective_text, clarification_answers: answers });
}

async function confirmAll(api: ApiClient, persona: PersonaId, rules: Rule[], thresholds: Record<string, number> = {}): Promise<Policy> {
  const interpretation = await proposedRules(api, persona);
  const { policy } = await api.confirmRules({
    persona_id: persona,
    base_policy_version: null,
    objectives: interpretation.objectives,
    confirmations: rules.map((rule) => ({ rule, threshold: thresholds[rule.rule_id] ?? (getRuleThreshold(rule) as number) })),
  });
  return policy;
}

async function runToEnd(api: ApiClient, id: string): Promise<{ final: Investigation; snapshots: Investigation[] }> {
  const snapshots: Investigation[] = [];
  for (let i = 0; i < 20; i += 1) {
    const snapshot = await api.getInvestigation(id);
    snapshots.push(snapshot);
    if (snapshot.status === "SUCCEEDED" || snapshot.status === "FAILED") return { final: snapshot, snapshots };
  }
  throw new Error("the job never reached a terminal status");
}

async function robertReport(api: ApiClient) {
  const interpretation = await proposedRules(api, "robert");
  const policy = await confirmAll(api, "robert", interpretation.proposed_rules);
  const { scenario_purchase } = await api.getPortfolio("robert");
  const created = await api.createInvestigation({
    persona_id: "robert",
    policy_version: policy.policy_version,
    purchase: scenario_purchase!,
    idempotency_key: "key-1",
  });
  const { final, snapshots } = await runToEnd(api, created.investigation_id);
  return { policy, id: created.investigation_id, final, snapshots };
}

describe("fixtures client — portfolios", () => {
  it("serves Robert's fictional portfolio from the frozen scenario, summing to 100%", async () => {
    const { portfolio, scenario_purchase } = await make().getPortfolio("robert");
    const weights = Object.fromEntries(portfolio.positions.map((p) => [p.instrument_id, p.weight]));

    expect(weights).toEqual({ "XBB.TO": 0.3, SPY: 0.2, "XIU.TO": 0.1, "RY.TO": 0.05, JNJ: 0.05 });
    expect(portfolio.cash_weight).toBe(0.3);
    expect(portfolio.positions.reduce((sum, p) => sum + p.weight, portfolio.cash_weight)).toBeCloseTo(1, 12);
    expect(portfolio.valuation_date).toBe("2026-11-12");
    expect(portfolio.is_fictional).toBe(true);
    expect(scenario_purchase).toEqual({ instrument_id: "NVDA", target_direct_weight: 0.25 });
  });

  it("serves Mateo's fictional portfolio, summing to 100%", async () => {
    const { portfolio, scenario_purchase } = await make().getPortfolio("mateo");
    expect(portfolio.positions.reduce((sum, p) => sum + p.weight, portfolio.cash_weight)).toBeCloseTo(1, 12);
    expect(portfolio.cash_weight).toBe(0.25);
    expect(scenario_purchase).toEqual({ instrument_id: "SPY", target_direct_weight: 0.15 });
  });

  it("has no data for Amira, who comes after the core", async () => {
    const error = await failure(make().getPortfolio("amira"));
    expect(error.kind).toBe("not_found");
  });

  it("hands out copies, so a screen cannot corrupt the recorded data", async () => {
    const api = make();
    const first = await api.getPortfolio("robert");
    first.portfolio.cash_weight = 0.99;
    expect((await api.getPortfolio("robert")).portfolio.cash_weight).toBe(0.3);
  });
});

describe("fixtures client — interpretation", () => {
  it("offers Robert's scenario rules as PROPOSED with the scenario's numbers", async () => {
    const interpretation = await proposedRules(make(), "robert");

    expect(interpretation.objectives).toHaveLength(1);
    expect(interpretation.proposed_rules.map((r) => [r.rule_type, r.status, r.origin, getRuleThreshold(r)])).toEqual([
      ["max_issuer_exposure", "PROPOSED", "FICTIONAL_SCENARIO", 0.1],
      ["scenario_loss_budget", "PROPOSED", "FICTIONAL_SCENARIO", 0.1],
    ]);
  });

  it("never gives a system-proposed rule a threshold", async () => {
    const api = make();
    const first = await proposedRules(api, "mateo");
    const answered = await proposedRules(api, "mateo", [{ clarification_id: "clar-mateo-oil", option_id: "energy-sector" }]);

    const systemProposed = [...first.proposed_rules, ...answered.proposed_rules].filter((r) => r.origin === "SYSTEM_PROPOSED");
    expect(systemProposed.length).toBeGreaterThan(0);
    for (const rule of systemProposed) expect(getRuleThreshold(rule)).toBeNull();
  });

  it("asks what “oil” means instead of proposing a rule for it", async () => {
    const interpretation = await proposedRules(make(), "mateo");

    expect(interpretation.proposed_rules.some((r) => r.rule_type === "exclusion")).toBe(false);
    expect(interpretation.clarifications).toHaveLength(1);
    const options = interpretation.clarifications[0]!.options;
    expect(options.filter((o) => o.supported).map((o) => o.option_id)).toEqual(["energy-sector", "named-issuers"]);
    expect(options.filter((o) => !o.supported).map((o) => o.option_id)).toEqual(["oil-producers", "fossil-fuels"]);
  });

  it("proposes the Energy-sector exclusion only after that definition is chosen", async () => {
    const answered = await proposedRules(make(), "mateo", [{ clarification_id: "clar-mateo-oil", option_id: "energy-sector" }]);

    expect(answered.clarifications).toHaveLength(0);
    const exclusion = answered.proposed_rules.find((r) => r.rule_type === "exclusion");
    expect(exclusion).toMatchObject({ status: "PROPOSED", definition: { kind: "fund_reported_sector", sector: "Energy" }, max_fraction: null });
  });

  it("says when edited wording was not interpreted", async () => {
    const response = await make().interpretRules({ persona_id: "robert", text: "Something else entirely", clarification_answers: [] });
    expect(response.notes.join(" ")).toMatch(/not interpreted/i);
  });
});

describe("fixtures client — policy versions", () => {
  it("creates policy version 1 with the confirmed rules active", async () => {
    const api = make();
    const interpretation = await proposedRules(api, "robert");
    const policy = await confirmAll(api, "robert", interpretation.proposed_rules);

    expect(policy.policy_version).toBe(1);
    expect(policy.previous_version).toBeNull();
    expect(policy.rules.map((r) => r.status)).toEqual(["CONFIRMED", "CONFIRMED"]);
  });

  it("carries confirmed rules into the next version when another rule is confirmed", async () => {
    const api = make();
    const interpretation = await proposedRules(api, "robert");
    const [first, second] = interpretation.proposed_rules as [Rule, Rule];
    const v1 = await confirmAll(api, "robert", [first]);
    const { policy: v2 } = await api.confirmRules({
      persona_id: "robert",
      base_policy_version: v1.policy_version,
      objectives: v1.objectives,
      confirmations: [{ rule: second, threshold: 0.1 }],
    });

    expect(v2.policy_version).toBe(2);
    expect(v2.previous_version).toBe(1);
    expect(v2.rules.filter((r) => r.status === "CONFIRMED").map((r) => r.rule_type)).toEqual(["max_issuer_exposure", "scenario_loss_budget"]);
  });

  it("rejects a threshold outside 0% to 100%", async () => {
    const api = make();
    const interpretation = await proposedRules(api, "robert");
    const error = await failure(
      api.confirmRules({
        persona_id: "robert",
        base_policy_version: null,
        objectives: [],
        confirmations: [{ rule: interpretation.proposed_rules[0]!, threshold: 1.5 }],
      }),
    );
    expect(error.kind).toBe("validation");
  });
});

describe("fixtures client — investigation lifecycle", () => {
  it("reveals completed steps progressively and the result only at the end", async () => {
    const { snapshots, final } = await robertReport(make());

    expect(snapshots.length).toBeGreaterThan(2);
    for (let i = 1; i < snapshots.length; i += 1) {
      const previous = snapshots[i - 1]!;
      const current = snapshots[i]!;
      // Steps are only ever appended: what was shown is never rewritten or removed.
      expect(current.steps.slice(0, previous.steps.length)).toEqual(previous.steps);
    }
    for (const snapshot of snapshots.slice(0, -1)) {
      expect(snapshot.status).toBe("RUNNING");
      expect(snapshot.result).toBeNull();
    }
    expect(final.status).toBe("SUCCEEDED");
    expect(final.result).not.toBeNull();
    expect(final.steps.map((s) => s.seq)).toEqual(final.steps.map((_, i) => i + 1));
    expect(final.steps.map((s) => s.tool)).toEqual([
      "get_portfolio",
      "get_policy",
      "simulate_change",
      "get_holdings",
      "compute_exposure",
      "replay_period",
      "check_rules",
      "max_compliant_amount",
    ]);
  });

  it("returns the same job for a repeated request with the same idempotency key", async () => {
    const api = make();
    const interpretation = await proposedRules(api, "robert");
    const policy = await confirmAll(api, "robert", interpretation.proposed_rules);
    const request = {
      persona_id: "robert" as const,
      policy_version: policy.policy_version,
      purchase: { instrument_id: "NVDA", target_direct_weight: 0.25 },
      idempotency_key: "same-key",
    };
    const first = await api.createInvestigation(request);
    const second = await api.createInvestigation(request);
    expect(second.investigation_id).toBe(first.investigation_id);
  });

  it("refuses a purchase it has no recorded result for, instead of inventing one", async () => {
    const api = make();
    const interpretation = await proposedRules(api, "robert");
    const policy = await confirmAll(api, "robert", interpretation.proposed_rules);
    const error = await failure(
      api.createInvestigation({
        persona_id: "robert",
        policy_version: policy.policy_version,
        purchase: { instrument_id: "NVDA", target_direct_weight: 0.2 },
        idempotency_key: "other",
      }),
    );
    expect(error).toMatchObject({ kind: "validation", code: "FIXTURE_NOT_RECORDED" });
  });

  it("refuses to run against a policy version that does not exist", async () => {
    const error = await failure(
      make().createInvestigation({
        persona_id: "robert",
        policy_version: 7,
        purchase: { instrument_id: "NVDA", target_direct_weight: 0.25 },
        idempotency_key: "k",
      }),
    );
    expect(error.kind).toBe("validation");
  });

  it("can simulate a failed job: terminal, with an error and no result", async () => {
    const { final } = await robertReport(make({ simulate: "job-failed" }));
    expect(final.status).toBe("FAILED");
    expect(final.result).toBeNull();
    expect(final.error?.message).toMatch(/simulated failure/i);
  });

  it("can simulate a job that never finishes", async () => {
    const api = make({ simulate: "poll-timeout" });
    const interpretation = await proposedRules(api, "robert");
    const policy = await confirmAll(api, "robert", interpretation.proposed_rules);
    const { investigation_id } = await api.createInvestigation({
      persona_id: "robert",
      policy_version: policy.policy_version,
      purchase: { instrument_id: "NVDA", target_direct_weight: 0.25 },
      idempotency_key: "k",
    });
    for (let i = 0; i < 10; i += 1) expect((await api.getInvestigation(investigation_id)).status).toBe("RUNNING");
  });

  it("honours an abort signal", async () => {
    const controller = new AbortController();
    const pending = failure(createFixturesClient({ latencyMs: 50 }).getPortfolio("robert", { signal: controller.signal }));
    controller.abort();
    expect((await pending).kind).toBe("aborted");
  });
});

describe("fixtures client — Robert's result", () => {
  it("fails both confirmed rules after the purchase and passes both before it", async () => {
    const { final } = await robertReport(make());
    const result = final.result!;
    const issuer = result.rule_results.find((r) => r.rule_type === "max_issuer_exposure")!;
    const budget = result.rule_results.find((r) => r.rule_type === "scenario_loss_budget")!;

    expect(issuer.starting.status).toBe("PASS");
    expect(issuer.proposed).toMatchObject({ status: "FAIL", measured: { lower: 0.265, upper: 0.265 }, limit: 0.1 });
    expect(issuer.proposed!.gap).toBeCloseTo(0.165, 10);

    expect(budget.starting.status).toBe("PASS");
    expect(budget.proposed).toMatchObject({ status: "FAIL", limit: 0.1 });
    expect(budget.proposed!.measured!.lower).toBeCloseTo(0.1778, 10);
    expect(budget.proposed!.gap).toBeCloseTo(0.0778, 10);
  });

  it("splits the exposure into direct and look-through and restates the cash arithmetic", async () => {
    const { final } = await robertReport(make());
    const result = final.result!;
    const exposure = result.exposures[0]!;

    expect(exposure.proposed).toMatchObject({ direct: 0.25, indirect_known: 0.015, possible_extra: 0, lower: 0.265, upper: 0.265 });
    expect(exposure.starting).toMatchObject({ direct: 0, indirect_known: 0.015 });
    expect(result.feasibility).toMatchObject({ status: "FEASIBLE", funding_path: "CASH", cash_before: 0.3, additional_purchase: 0.25 });
    expect(result.feasibility!.cash_after).toBeCloseTo(0.05, 10);
  });

  it("reports the scenario result with return and drawdown as separate metrics", async () => {
    const { final } = await robertReport(make());
    const scenario = final.result!.scenario!;

    expect(scenario.scenario_id).toBe("replay_2022");
    expect(scenario.proposed).toEqual({ scenario_terminal_return: -0.1778, scenario_max_drawdown: -0.232 });
    expect(scenario).toMatchObject({ budget: 0.1, status: "FAIL" });
    expect(scenario.assumptions.join(" ")).toMatch(/no rebalancing/i);
  });

  it("gives a maximum compliant weight that accounts for look-through, cash and the loss budget", async () => {
    const { final } = await robertReport(make());
    const max = final.result!.max_compliant!;

    expect(max.status).toBe("SUPPORTED");
    expect(max.verified_by_rerun).toBe(true);
    // Issuer cap alone would allow 10% - 1.5% = 8.5%; the loss budget binds slightly lower.
    expect(max.final_direct_weight!).toBeLessThan(0.085);
    expect(max.final_direct_weight!).toBeCloseTo((0.1 - 0.0603) / 0.47, 8);
    expect(max.additional_purchase).toBe(max.final_direct_weight);
    expect(max.binding_rule_ids).toEqual(["rule-robert-loss-budget"]);
  });

  it("attaches an evidence record, with sources, to every figure it reports", async () => {
    const { final } = await robertReport(make());
    const result = final.result!;
    const evidenceIds = new Set(result.evidence.map((e) => e.evidence_id));
    const sourceIds = new Set(result.sources.map((s) => s.source_id));

    const referenced = [
      ...result.rule_results.flatMap((r) => [...r.starting.evidence_ids, ...(r.proposed?.evidence_ids ?? [])]),
      ...result.exposures.flatMap((e) => e.evidence_ids),
      ...(result.scenario?.evidence_ids ?? []),
      ...(result.max_compliant?.evidence_ids ?? []),
    ];
    expect(referenced.length).toBeGreaterThan(0);
    for (const id of referenced) expect(evidenceIds.has(id)).toBe(true);
    for (const record of result.evidence) {
      expect(record.policy_version).toBe(1);
      expect(record.calculation_version).not.toBe("");
      for (const sourceId of record.source_ids) expect(sourceIds.has(sourceId)).toBe(true);
    }
    expect(evidenceIds.size).toBe(result.evidence.length);
  });

  it("labels every measured source as a placeholder", async () => {
    const { final } = await robertReport(make());
    const measured = final.result!.sources.filter((s) => s.source_id !== "fx-src-scenario");
    for (const source of measured) expect(source.known_limitations.join(" ")).toMatch(/placeholder/i);
  });
});

describe("fixtures client — challenge", () => {
  it("raising the issuer cap creates policy version 2 and leaves version 1 and its report untouched", async () => {
    const api = make();
    const { policy: v1, id, final } = await robertReport(api);
    const before = JSON.stringify(final);

    const response = await api.challengeInvestigation(id, { kind: "CHANGE_RULE", rule_id: "rule-robert-issuer-cap", new_threshold: 0.3 });
    if (response.kind !== "CHANGE_RULE") throw new Error("expected a rule change");
    const v2 = response.policy;

    expect(v2.policy_version).toBe(2);
    expect(v2.previous_version).toBe(1);
    const superseded = v2.rules.find((r) => r.status === "SUPERSEDED")!;
    const replacement = v2.rules.find((r) => r.supersedes_rule_id === superseded.rule_id)!;
    expect(getRuleThreshold(superseded)).toBe(0.1);
    expect(replacement).toMatchObject({ status: "CONFIRMED", origin: "USER_STATED", rule_type: "max_issuer_exposure" });
    expect(getRuleThreshold(replacement)).toBe(0.3);
    expect(replacement.rule_id).not.toBe(superseded.rule_id);
    expect(v2.objectives).toEqual(v1.objectives);

    // The earlier report is immutable and still retrievable.
    expect(v1.rules.every((r) => r.status === "CONFIRMED")).toBe(true);
    expect(JSON.stringify(await api.getInvestigation(id))).toBe(before);
    expect(response.investigation_id).not.toBe(id);
  });

  it("re-evaluates every remaining rule: the cap now passes, the loss budget still fails with its gap", async () => {
    const api = make();
    const { id } = await robertReport(api);
    const response = await api.challengeInvestigation(id, { kind: "CHANGE_RULE", rule_id: "rule-robert-issuer-cap", new_threshold: 0.3 });
    if (response.kind !== "CHANGE_RULE") throw new Error("expected a rule change");
    const { final } = await runToEnd(api, response.investigation_id);
    const result = final.result!;

    expect(result.policy_version).toBe(2);
    const issuer = result.rule_results.find((r) => r.rule_type === "max_issuer_exposure")!;
    const budget = result.rule_results.find((r) => r.rule_type === "scenario_loss_budget")!;
    expect(issuer.proposed).toMatchObject({ status: "PASS", limit: 0.3 });
    expect(budget.proposed).toMatchObject({ status: "FAIL", limit: 0.1 });
    expect(budget.proposed!.gap).toBeCloseTo(0.0778, 10);
    expect(result.scenario).toMatchObject({ status: "FAIL", budget: 0.1 });
    expect(result.rule_results).toHaveLength(2);
  });

  it("records a fact correction as an unverified user claim and changes nothing else", async () => {
    const api = make();
    const { id, final } = await robertReport(api);
    const before = JSON.stringify(final);
    const evidenceId = final.result!.evidence[0]!.evidence_id;

    const response = await api.challengeInvestigation(id, {
      kind: "CORRECT_FACT",
      evidence_id: evidenceId,
      proposed_value_text: "6.1%",
      reason_text: "The fund's fact sheet says so.",
    });
    if (response.kind !== "CORRECT_FACT") throw new Error("expected a fact correction");

    expect(response.correction).toMatchObject({
      evidence_id: evidenceId,
      status: "UNVERIFIED",
      applied_to_calculation: false,
      proposed_value_text: "6.1%",
    });
    expect(response.correction.provenance.asserted_by).toBe("USER");
    expect(JSON.stringify(await api.getInvestigation(id))).toBe(before);
  });

  it("rejects a correction to a figure that is not in the report", async () => {
    const api = make();
    const { id } = await robertReport(api);
    const error = await failure(
      api.challengeInvestigation(id, { kind: "CORRECT_FACT", evidence_id: "nope", proposed_value_text: "1%", reason_text: "x" }),
    );
    expect(error.kind).toBe("validation");
  });

  it("stores a clarified preference in the user's own words without inventing a rule", async () => {
    const api = make();
    const { id } = await robertReport(api);
    const response = await api.challengeInvestigation(id, { kind: "CLARIFY_PREFERENCE", text: "  Not losing money matters most to me.  " });
    if (response.kind !== "CLARIFY_PREFERENCE") throw new Error("expected a preference clarification");

    expect(response.interpretation.objectives).toEqual([
      expect.objectContaining({ original_words: "Not losing money matters most to me.", origin: "USER_STATED" }),
    ]);
    expect(response.interpretation.proposed_rules).toEqual([]);
  });
});

describe("fixtures client — Mateo's result (a failure together with unknowns)", () => {
  async function mateoReport(api: ApiClient) {
    const interpretation = await proposedRules(api, "mateo", [{ clarification_id: "clar-mateo-oil", option_id: "energy-sector" }]);
    const { policy } = await api.confirmRules({
      persona_id: "mateo",
      base_policy_version: null,
      objectives: interpretation.objectives,
      confirmations: interpretation.proposed_rules.map((rule) => ({ rule, threshold: 0 })),
    });
    const created = await api.createInvestigation({
      persona_id: "mateo",
      policy_version: policy.policy_version,
      purchase: { instrument_id: "SPY", target_direct_weight: 0.15 },
      idempotency_key: "mateo-1",
    });
    return (await runToEnd(api, created.investigation_id)).final.result!;
  }

  it("fails the Energy exclusion on the STARTING portfolio, before any purchase", async () => {
    const result = await mateoReport(make());
    const exclusion = result.rule_results.find((r) => r.rule_type === "exclusion")!;

    expect(exclusion.starting).toMatchObject({ status: "FAIL", limit: 0 });
    expect(exclusion.starting.measured).toEqual({ lower: 0.034, upper: 0.184 });
    expect(exclusion.proposed!.status).toBe("FAIL");
    expect(exclusion.proposed!.measured!.lower).toBeCloseTo(0.03895, 10);
    expect(exclusion.proposed!.measured!.upper).toBeCloseTo(0.18895, 10);
  });

  it("keeps the controversy check UNKNOWN next to the proven failure", async () => {
    const result = await mateoReport(make());
    const statuses = Object.fromEntries(result.rule_results.map((r) => [r.rule_type, r.proposed!.status]));

    expect(statuses).toEqual({ controversy_exclusion: "UNKNOWN", exclusion: "FAIL" });
    expect(result.rule_results.find((r) => r.rule_type === "controversy_exclusion")!.proposed!.gap).toBeNull();
  });

  it("treats the fund without holdings as an unknown range, not as zero", async () => {
    const result = await mateoReport(make());
    const esgv = result.data_coverage.funds.find((f) => f.fund_id === "ESGV")!;
    const exposure = result.exposures.find((e) => e.rule_id === "rule-mateo-energy")!;

    expect(esgv).toMatchObject({ status: "MISSING", coverage: 0, holdings_date: null });
    expect(result.data_coverage.status).toBe("PARTIAL");
    expect(exposure.proposed!.possible_extra).toBe(0.15);
    expect(exposure.proposed!.upper).toBeGreaterThan(exposure.proposed!.lower);
  });

  it("says no purchase is feasible instead of giving a maximum", async () => {
    const result = await mateoReport(make());
    expect(result.max_compliant).toMatchObject({ status: "NO_FEASIBLE_PURCHASE", final_direct_weight: null, additional_purchase: null });
    expect(result.max_compliant!.reason).toMatch(/no purchase is feasible under this funding path/i);
  });

  it("replays no scenario when no loss budget is confirmed", async () => {
    expect((await mateoReport(make())).scenario).toBeNull();
  });
});

describe("fixtures client — draft previews (POST /check)", () => {
  async function preview(api: ApiClient, persona: PersonaId, ruleType: Rule["rule_type"], threshold: number, withPurchase: boolean) {
    const answers = persona === "mateo" ? [{ clarification_id: "clar-mateo-oil", option_id: "energy-sector" }] : [];
    const interpretation = await proposedRules(api, persona, answers);
    const rule = interpretation.proposed_rules.find((r) => r.rule_type === ruleType)!;
    const { scenario_purchase } = await api.getPortfolio(persona);
    const { result } = await api.check({
      persona_id: persona,
      purchase: withPurchase ? scenario_purchase : null,
      rules: [withRuleThreshold(rule, threshold)],
      is_draft_preview: true,
    });
    return result;
  }

  it("is marked as a draft preview and belongs to no policy version", async () => {
    const result = await preview(make(), "robert", "max_issuer_exposure", 0.12, false);
    expect(result.is_draft_preview).toBe(true);
    expect(result.policy_version).toBeNull();
    expect(result.max_compliant).toBeNull();
    expect(result.rule_results[0]!.proposed).toBeNull();
  });

  it("passes when the measured value is exactly at the limit", async () => {
    const result = await preview(make(), "robert", "max_issuer_exposure", 0.265, true);
    expect(result.rule_results[0]!.proposed).toMatchObject({ status: "PASS", gap: 0 });
    expect(result.rule_results[0]!.proposed!.reason).toMatch(/exactly at the limit/i);
  });

  it("fails just below the measured value", async () => {
    const result = await preview(make(), "robert", "max_issuer_exposure", 0.2649, true);
    expect(result.rule_results[0]!.proposed!.status).toBe("FAIL");
  });

  it("is UNKNOWN when the limit falls inside the possible range", async () => {
    const result = await preview(make(), "mateo", "exclusion", 0.05, false);
    expect(result.rule_results[0]!.starting).toMatchObject({ status: "UNKNOWN", gap: null, measured: { lower: 0.034, upper: 0.184 } });
  });

  it("passes only when even the upper bound is within the limit", async () => {
    expect((await preview(make(), "mateo", "exclusion", 0.184, false)).rule_results[0]!.starting.status).toBe("PASS");
    expect((await preview(make(), "mateo", "exclusion", 0.1839, false)).rule_results[0]!.starting.status).toBe("UNKNOWN");
    expect((await preview(make(), "mateo", "exclusion", 0.0339, false)).rule_results[0]!.starting.status).toBe("FAIL");
  });

  it("does not create a policy version or a job", async () => {
    const api = make();
    await preview(api, "robert", "max_issuer_exposure", 0.5, true);
    const interpretation = await proposedRules(api, "robert");
    const policy = await confirmAll(api, "robert", interpretation.proposed_rules);
    // Had the preview been stored, this would not be version 1 with the scenario's 10% cap.
    expect(policy.policy_version).toBe(1);
    expect(getRuleThreshold(policy.rules[0]!)).toBe(0.1);
  });

  it("skips rules that have no threshold yet", async () => {
    const api = make();
    const interpretation = await proposedRules(api, "mateo");
    const { result } = await api.check({ persona_id: "mateo", purchase: null, rules: interpretation.proposed_rules, is_draft_preview: true });
    expect(result.rule_results).toEqual([]);
  });
});
