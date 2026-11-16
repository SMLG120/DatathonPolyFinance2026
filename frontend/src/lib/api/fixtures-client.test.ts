import { describe, expect, it } from "vitest";
import type { ApiClient } from "@/lib/api";
import type { ConfirmRequest, InvestigationJob, Policy, PurchaseRequest, Rule } from "@/lib/contracts";
import { FIXTURES } from "@/lib/fixtures";
import { draftRule, previewRuleSet } from "@/lib/rules";
import { ApiError } from "./errors";
import { createFixturesClient } from "./fixtures-client";

/**
 * The fixtures client replays recorded bodies. Every expectation below is the
 * recorded body itself (`FIXTURES`, a copy of contracts/fixtures/api), so a
 * test can only pass when the client returned what was recorded.
 */
const KEY_1 = "0b6f0c9e-5a7e-4c0e-9a55-1f2d3c4b5a61";
const KEY_2 = "7d1e2f3a-4b5c-4d6e-8f70-91a2b3c4d5e6";
const KEY_3 = "3c9d8e7f-6a5b-4c3d-9e2f-1a0b9c8d7e6f";

const client = (options: Parameters<typeof createFixturesClient>[0] = {}) => createFixturesClient({ latencyMs: 0, ...options });

async function failure(promise: Promise<unknown>): Promise<ApiError> {
  try {
    await promise;
  } catch (error) {
    if (error instanceof ApiError) return error;
    throw error;
  }
  throw new Error("expected the request to be refused");
}

const robertScenario = FIXTURES.portfolioRobert.response.scenario;
const mateoScenario = FIXTURES.scenarios.mateo;
if (!mateoScenario) throw new Error("The Mateo scenario is not among the copied contracts.");
const robertPurchase = FIXTURES.investigationAccepted.request.request as PurchaseRequest;
const mateoPurchase = mateoScenario.demo_requests[0]?.purchase_request as PurchaseRequest;

/** Confirms a persona's scenario rules at the numbers the scenario offers, in one new policy version. */
function confirmScenarioRules(api: ApiClient, scenario: typeof robertScenario, overrides: Record<string, number> = {}): Promise<Policy> {
  const request: ConfirmRequest = {
    persona_id: scenario.persona.persona_id,
    policy_id: null,
    base_version: null,
    objectives: scenario.objectives,
    confirmations: scenario.scenario_rules.map((rule) => ({ rule, threshold: overrides[rule.rule_id] ?? (rule.threshold as number) })),
    withdraw_rule_ids: [],
    change_note: null,
  };
  return api.confirmRules(request).then((response) => response.policy);
}

async function pollToEnd(api: ApiClient, id: string, limit = 10): Promise<InvestigationJob[]> {
  const frames: InvestigationJob[] = [];
  for (let index = 0; index < limit; index += 1) {
    const frame = await api.getInvestigation(id);
    frames.push(frame);
    if (frame.status === "SUCCEEDED" || frame.status === "FAILED") break;
  }
  return frames;
}

async function robertFinished(api: ApiClient) {
  const policy = await confirmScenarioRules(api, robertScenario);
  const accepted = await api.createInvestigation(
    { persona_id: "robert", policy_id: policy.policy_id, policy_version: policy.version, request: robertPurchase, parent_investigation_id: null },
    { idempotencyKey: KEY_1 },
  );
  const frames = await pollToEnd(api, accepted.id);
  return { policy, accepted, frames, final: frames.at(-1) as InvestigationJob };
}

async function mateoFinished(api: ApiClient) {
  const policy = await confirmScenarioRules(api, mateoScenario as typeof robertScenario);
  const accepted = await api.createInvestigation(
    { persona_id: "mateo", policy_id: policy.policy_id, policy_version: policy.version, request: mateoPurchase, parent_investigation_id: null },
    { idempotencyKey: KEY_3 },
  );
  const frames = await pollToEnd(api, accepted.id);
  return { policy, accepted, final: frames.at(-1) as InvestigationJob };
}

describe("fixtures client — portfolios", () => {
  it("replays the recorded answer for Robert", async () => {
    expect(await client().getPortfolio("robert")).toEqual(FIXTURES.portfolioRobert.response);
  });

  it("serves Mateo's copied scenario with the registry entries of what he holds and may buy", async () => {
    const response = await client().getPortfolio("mateo");
    const registry = FIXTURES.registries.mateo_synthetic_universe?.instruments ?? {};
    const ids = [...mateoScenario.portfolio.positions.map((position) => position.instrument_id), mateoPurchase.instrument_id].sort();
    expect(response.scenario).toEqual(mateoScenario);
    expect(Object.keys(response.instruments).sort()).toEqual(ids);
    expect(response.purchasable_instrument_ids).toEqual(ids);
    for (const id of ids) expect(response.instruments[id]).toEqual(registry[id]);
  });

  it("replays the recorded answer for Amira, crypto assets outside company-exposure scope", async () => {
    const response = await client().getPortfolio("amira");
    expect(response).toEqual(FIXTURES.portfolioAmira.response);
    expect(response.scenario.fictional).toBe(true);
    for (const position of response.scenario.portfolio.positions) expect(response.instruments[position.instrument_id]).toBeDefined();
    expect(response.instruments["BTC-USD"]?.equity_scope).toBe(false);
    expect(response.instruments["ETH-USD"]?.equity_scope).toBe(false);
  });

  it("has no portfolio for a persona without recorded data", async () => {
    expect((await failure(client().getPortfolio("nobody"))).kind).toBe("not_found");
  });

  it("hands out copies, so a screen cannot corrupt the recorded data", async () => {
    const api = client();
    const first = await api.getPortfolio("robert");
    first.scenario.portfolio.cash_weight = 0.99;
    first.scenario.scenario_rules.length = 0;
    expect(await api.getPortfolio("robert")).toEqual(FIXTURES.portfolioRobert.response);
  });

  it("can simulate a failure, saying that it is simulated", async () => {
    const error = await failure(client({ simulate: "portfolio-error" }).getPortfolio("robert"));
    expect(error.kind).toBe("server");
    expect(error.message).toMatch(/Simulated failure \(test data\)/);
  });
});

describe("fixtures client — interpretation", () => {
  const recordedMateo = FIXTURES.interpret.mateo;

  it("replays the recorded interpretation of Mateo's sentence", async () => {
    expect(await client().interpretRules(recordedMateo.request)).toEqual(recordedMateo.response);
  });

  it("recognises the recorded sentence whatever its spacing, case or final full stop", async () => {
    const text = `  ${recordedMateo.request.text.toUpperCase().replace(/\.$/, "")}  `;
    expect(await client().interpretRules({ ...recordedMateo.request, text })).toEqual(recordedMateo.response);
  });

  it("refuses other wording and says which sentence is recorded, instead of guessing", async () => {
    const error = await failure(client().interpretRules({ ...recordedMateo.request, text: "I do not want any tobacco." }));
    expect(error.kind).toBe("no_fixture");
    expect(error.message).toContain(recordedMateo.request.text);
  });

  it("says so when nothing is recorded for the persona", async () => {
    const error = await failure(client().interpretRules({ persona_id: "robert", text: "Keep me safe.", policy_id: null, policy_version: null }));
    expect(error.kind).toBe("no_fixture");
    expect(error.message).toMatch(/no recorded interpretation for this persona/);
  });

  it("holds no system-proposed rule with a number: the recording never invents one", () => {
    const drafts: Rule[] = [
      ...recordedMateo.response.proposed_rules,
      ...recordedMateo.response.clarifications.flatMap((clarification) => clarification.options.flatMap((option) => (option.proposed_rule ? [option.proposed_rule] : []))),
    ];
    expect(drafts.length).toBeGreaterThan(0);
    for (const draft of drafts) expect(draft).toMatchObject({ status: "PROPOSED", origin: "SYSTEM_PROPOSED", threshold: null, threshold_source: null });
  });
});

describe("fixtures client — confirmation", () => {
  it("replays the recorded policy version 1 for the recorded confirmation", async () => {
    expect(await client().confirmRules(FIXTURES.confirmRobertV1.request)).toEqual(FIXTURES.confirmRobertV1.response);
  });

  it("gives the recorded version 1 when the scenario's rules are confirmed at the scenario's numbers", async () => {
    expect(await confirmScenarioRules(client(), robertScenario)).toEqual(FIXTURES.confirmRobertV1.response.policy);
  });

  it("stores another number as the user's own, in a version that claims no recorded hash", async () => {
    const policy = await confirmScenarioRules(client(), robertScenario, { "robert-issuer-cap-1": 0.2 });
    expect(policy.version).toBe(1);
    expect(policy.content_hash).toBe(`sha256:${"0".repeat(64)}`);
    expect(policy.rules.map((rule) => [rule.rule_id, rule.status, rule.threshold, rule.origin, rule.threshold_source])).toEqual([
      ["robert-issuer-cap-1", "CONFIRMED", 0.2, "USER_STATED", "USER_ENTERED"],
      ["robert-loss-budget-1", "CONFIRMED", 0.1, "FICTIONAL_SCENARIO", "FICTIONAL_SCENARIO"],
    ]);
  });

  it("writes the next version on top of the last one and supersedes the rule that measured the same thing", async () => {
    const api = client();
    const first = await confirmScenarioRules(api, robertScenario);
    const cap = first.rules.find((rule) => rule.rule_id === "robert-issuer-cap-1") as Rule;
    const { policy: second } = await api.confirmRules({
      persona_id: "robert",
      policy_id: first.policy_id,
      base_version: first.version,
      objectives: first.objectives,
      confirmations: [{ rule: draftRule(cap, 0.3), threshold: 0.3 }],
      withdraw_rule_ids: [],
      change_note: null,
    });
    // The same state as the recorded version 2, so the recording itself is returned.
    expect(second).toEqual(FIXTURES.challenges.changeRule.response.policy);
  });

  it("refuses a confirmation based on a version that is no longer the latest, with the recorded error", async () => {
    const api = client();
    const first = await confirmScenarioRules(api, robertScenario);
    const error = await failure(
      api.confirmRules({ persona_id: "robert", policy_id: first.policy_id, base_version: 7, objectives: [], confirmations: [], withdraw_rule_ids: [], change_note: null }),
    );
    expect(error).toMatchObject({ kind: "validation", status: FIXTURES.errors.policyVersionConflict.status, code: "POLICY_VERSION_CONFLICT" });
    expect(error.message).toBe(FIXTURES.errors.policyVersionConflict.response.error.message);
  });

  it.each([-0.01, 1.01, Number.NaN])("refuses a confirmation whose number is %s", async (threshold) => {
    const error = await failure(confirmScenarioRules(client(), robertScenario, { "robert-issuer-cap-1": threshold }));
    expect(error).toMatchObject({ kind: "validation", code: "INVALID_CONFIRMATION" });
  });
});

describe("fixtures client — investigation lifecycle", () => {
  it("accepts the recorded request and replays the recorded QUEUED, RUNNING and SUCCEEDED bodies in that order", async () => {
    const { accepted, frames } = await robertFinished(client());
    expect(accepted).toEqual(FIXTURES.investigationAccepted.response);
    expect(frames).toEqual([FIXTURES.jobs.robertQueued.response, FIXTURES.jobs.robertRunning.response, FIXTURES.jobs.robertSucceeded.response]);
  });

  it("keeps answering with the final body once the job is finished", async () => {
    const api = client();
    const { accepted } = await robertFinished(api);
    expect(await api.getInvestigation(accepted.id)).toEqual(FIXTURES.jobs.robertSucceeded.response);
  });

  it("returns the same job for a repeated request with the same idempotency key", async () => {
    const api = client();
    const policy = await confirmScenarioRules(api, robertScenario);
    const body = { persona_id: "robert", policy_id: policy.policy_id, policy_version: policy.version, request: robertPurchase, parent_investigation_id: null };
    const first = await api.createInvestigation(body, { idempotencyKey: KEY_1 });
    await api.getInvestigation(first.id);
    const again = await api.createInvestigation(body, { idempotencyKey: KEY_1 });
    expect(again).toEqual(first);
    // The job was not restarted: the next poll continues where the first left off.
    expect((await api.getInvestigation(first.id)).status).toBe("RUNNING");
  });

  it.each([undefined, "", "short", "has spaces in it", "x".repeat(65)])("refuses to start a job without a well-formed idempotency key (%j)", async (idempotencyKey) => {
    const api = client();
    const policy = await confirmScenarioRules(api, robertScenario);
    const error = await failure(
      api.createInvestigation(
        { persona_id: "robert", policy_id: policy.policy_id, policy_version: policy.version, request: robertPurchase, parent_investigation_id: null },
        { idempotencyKey: idempotencyKey as string },
      ),
    );
    expect(error.kind).toBe("validation");
  });

  it("refuses a purchase it holds no recorded result for, instead of inventing one, and says what is recorded", async () => {
    const api = client();
    const policy = await confirmScenarioRules(api, robertScenario);
    const error = await failure(
      api.createInvestigation(
        { persona_id: "robert", policy_id: policy.policy_id, policy_version: policy.version, request: { ...robertPurchase, target_direct_weight: 0.2 }, parent_investigation_id: null },
        { idempotencyKey: KEY_1 },
      ),
    );
    expect(error.kind).toBe("no_fixture");
    expect(error.message).toContain("NVDA at a final direct weight of 20.0%");
    expect(error.message).toContain("Recorded for this persona: NVDA at a final direct weight of 25.0% with limits 10.0% and 10.0%");
  });

  it("refuses the recorded purchase under rules the recording was not made with", async () => {
    const api = client();
    const policy = await confirmScenarioRules(api, robertScenario, { "robert-issuer-cap-1": 0.2 });
    const error = await failure(
      api.createInvestigation(
        { persona_id: "robert", policy_id: policy.policy_id, policy_version: policy.version, request: robertPurchase, parent_investigation_id: null },
        { idempotencyKey: KEY_1 },
      ),
    );
    expect(error.kind).toBe("no_fixture");
    expect(error.message).toContain("issuer-cap 20.0%");
  });

  it("refuses a free-text request: nothing recorded resolves it", async () => {
    const api = client();
    const policy = await confirmScenarioRules(api, robertScenario);
    const error = await failure(
      api.createInvestigation(
        { persona_id: "robert", policy_id: policy.policy_id, policy_version: policy.version, request: { instrument_id: null, target_direct_weight: null, funding: "CASH", original_words: "Buy some Nvidia" }, parent_investigation_id: null },
        { idempotencyKey: KEY_1 },
      ),
    );
    expect(error.kind).toBe("no_fixture");
    expect(error.message).toContain("a request in free text");
  });

  it("refuses to run against a policy version that does not exist", async () => {
    const error = await failure(
      client().createInvestigation({ persona_id: "robert", policy_id: "pol-robert-demo", policy_version: 1, request: robertPurchase, parent_investigation_id: null }, { idempotencyKey: KEY_1 }),
    );
    expect(error.kind).toBe("not_found");
  });

  it("answers an unknown job id with the recorded not-found error", async () => {
    const error = await failure(client().getInvestigation("inv-nope"));
    expect(error).toMatchObject({ kind: "not_found", status: FIXTURES.errors.notFound.status, message: FIXTURES.errors.notFound.response.error.message });
  });

  it("can simulate a failed job: it ends with the recorded failure and no result", async () => {
    const api = client({ simulate: "job-failed" });
    const accepted = await api.createInvestigation({ persona_id: "robert", policy_id: "any", policy_version: 1, request: robertPurchase, parent_investigation_id: null }, { idempotencyKey: KEY_1 });
    const frames = await pollToEnd(api, accepted.id);
    expect(frames.at(-1)).toEqual(FIXTURES.jobs.failed.response);
    expect(frames.at(-1)?.result).toBeNull();
    expect(frames.slice(0, -1).every((frame) => frame.result === null && frame.failure === null)).toBe(true);
  });

  it("can simulate a job that never finishes", async () => {
    const api = client({ simulate: "poll-timeout" });
    const policy = await confirmScenarioRules(api, robertScenario);
    const accepted = await api.createInvestigation(
      { persona_id: "robert", policy_id: policy.policy_id, policy_version: policy.version, request: robertPurchase, parent_investigation_id: null },
      { idempotencyKey: KEY_1 },
    );
    const frames = await pollToEnd(api, accepted.id, 8);
    expect(frames).toHaveLength(8);
    expect(frames.every((frame) => frame.result === null && (frame.status === "QUEUED" || frame.status === "RUNNING"))).toBe(true);
  });

  it("shows a job that has only a final recording as the same job cut short, never with a result before the end", async () => {
    const { final, policy } = await mateoFinished(client());
    expect(final).toEqual(FIXTURES.jobs.mateoSucceeded.response);
    expect(policy.rules.map((rule) => rule.rule_id)).toEqual(["mateo-excl-energy-1", "mateo-controversy-1"]);

    const api = client();
    const again = await confirmScenarioRules(api, mateoScenario as typeof robertScenario);
    const accepted = await api.createInvestigation(
      { persona_id: "mateo", policy_id: again.policy_id, policy_version: again.version, request: mateoPurchase, parent_investigation_id: null },
      { idempotencyKey: KEY_3 },
    );
    const queued = await api.getInvestigation(accepted.id);
    const running = await api.getInvestigation(accepted.id);
    expect(queued).toMatchObject({ id: final.id, status: "QUEUED", steps: [], result: null, explanation: [], failure: null });
    expect(running).toMatchObject({ id: final.id, status: "RUNNING", result: null, explanation: [] });
    expect(running.steps.length).toBeLessThan(final.steps.length);
    expect(running.steps.map((step) => step.tool)).toEqual(final.steps.slice(0, running.steps.length).map((step) => step.tool));
    expect(running.steps.at(-1)).toMatchObject({ status: "RUNNING", finished_at: null, result_summary: null });
  });

  it("honours an abort signal", async () => {
    const controller = new AbortController();
    controller.abort();
    expect((await failure(createFixturesClient({ latencyMs: 20 }).getPortfolio("robert", { signal: controller.signal }))).kind).toBe("aborted");
  });
});

describe("fixtures client — checks and previews (POST /check)", () => {
  const preview = FIXTURES.checkRobertPreview;

  it("replays the recorded preview for the recorded request", async () => {
    expect(await client().check(preview.request)).toEqual(preview.response);
  });

  it("replays it for the rule set the interface builds when Robert tries 20% on his single-company limit", async () => {
    const api = client();
    const policy = await confirmScenarioRules(api, robertScenario);
    const cap = policy.rules.find((rule) => rule.rule_id === "robert-issuer-cap-1") as Rule;
    const result = await api.check({
      persona_id: "robert",
      policy_id: policy.policy_id,
      policy_version: policy.version,
      purchase_request: robertPurchase,
      draft_rules: previewRuleSet(policy.rules, [draftRule(cap, 0.2)]),
    });
    expect(result).toEqual(preview.response);
    expect(result.preview).toBe(true);
    expect(result.policy_version).toBeNull();
  });

  it("refuses any other draft value and names the one recorded preview", async () => {
    const drafts = (preview.request.draft_rules ?? []).map((rule) => (rule.status === "PROPOSED" ? draftRule(rule, 0.15) : rule));
    const error = await failure(client().check({ ...preview.request, draft_rules: drafts }));
    expect(error.kind).toBe("no_fixture");
    expect(error.message).toContain("NVDA at a final direct weight of 25.0% with a draft single-company limit of 20.0%");
  });

  it("replays the recorded UNKNOWN preview for Mateo", async () => {
    const recordedUnknown = FIXTURES.checkMateoPreviewUnknown;
    const result = await client().check(recordedUnknown.request);
    expect(result).toEqual(recordedUnknown.response);
    expect(result.rule_results.map((item) => item.status)).toEqual(["UNKNOWN"]);
    expect(result.max_compliant?.status).toBe("WITHHELD");
  });

  it("replays the recorded refusal of a request that cannot be evaluated", async () => {
    const invalid = FIXTURES.checkInvalidRequest;
    const result = await client().check(invalid.request);
    expect(result).toEqual(invalid.response);
    expect(result.execution.status).toBe("INVALID_REQUEST");
    expect(result.rule_results).toEqual([]);
  });

  it("answers a check of a stored policy version with the recorded result of the same request under the same rules", async () => {
    const api = client();
    const policy = await confirmScenarioRules(api, robertScenario);
    const result = await api.check({ persona_id: "robert", policy_id: policy.policy_id, policy_version: policy.version, purchase_request: robertPurchase, draft_rules: null });
    expect(result).toEqual(FIXTURES.jobs.robertSucceeded.response.result);
  });

  it("refuses a check of a stored policy version that nothing was recorded for", async () => {
    const api = client();
    const policy = await confirmScenarioRules(api, robertScenario);
    const error = await failure(
      api.check({ persona_id: "robert", policy_id: policy.policy_id, policy_version: policy.version, purchase_request: { ...robertPurchase, target_direct_weight: 0.1 }, draft_rules: null }),
    );
    expect(error.kind).toBe("no_fixture");
    expect(error.message).toContain("NVDA at a final direct weight of 10.0%");
  });

  it("does not know a policy version that was never confirmed", async () => {
    const error = await failure(client().check({ persona_id: "robert", policy_id: "pol-robert-demo", policy_version: 3, purchase_request: robertPurchase, draft_rules: null }));
    expect(error.kind).toBe("not_found");
  });

  it("creates no policy version and no job", async () => {
    const api = client();
    await api.check(preview.request);
    expect((await failure(api.getInvestigation("inv-robert-0001"))).kind).toBe("not_found");
    expect(
      (await failure(api.createInvestigation({ persona_id: "robert", policy_id: "pol-robert-demo", policy_version: 1, request: robertPurchase, parent_investigation_id: null }, { idempotencyKey: KEY_1 }))).kind,
    ).toBe("not_found");
  });

  it("can simulate a failed check", async () => {
    expect((await failure(client({ simulate: "check-error" }).check(preview.request))).kind).toBe("server");
  });
});

describe("fixtures client — challenges", () => {
  const change = FIXTURES.challenges.changeRule;
  const fact = FIXTURES.challenges.correctFact;
  const preference = FIXTURES.challenges.clarifyPreference;

  it("replays the recorded rule change: policy version 2 and a new job, leaving version 1 and its report as they were", async () => {
    const api = client();
    const { accepted } = await robertFinished(api);
    const response = await api.challengeInvestigation(accepted.id, change.request, { idempotencyKey: KEY_2 });
    expect(response).toEqual(change.response);

    const child = await pollToEnd(api, response.investigation?.id as string);
    expect(child.at(-1)).toEqual(FIXTURES.jobs.robertAfterChallenge.response);
    expect(await api.getInvestigation(accepted.id)).toEqual(FIXTURES.jobs.robertSucceeded.response);
    // Version 1 is still stored and still checks as it did.
    expect(await api.check({ persona_id: "robert", policy_id: "pol-robert-demo", policy_version: 1, purchase_request: robertPurchase, draft_rules: null })).toEqual(
      FIXTURES.jobs.robertSucceeded.response.result,
    );
  });

  it("needs an idempotency key for a rule change, because it starts a job", async () => {
    const api = client();
    const { accepted } = await robertFinished(api);
    expect((await failure(api.challengeInvestigation(accepted.id, change.request, { idempotencyKey: "" }))).kind).toBe("validation");
  });

  it("refuses a rule change it has no recording for", async () => {
    const api = client();
    const { accepted } = await robertFinished(api);
    const error = await failure(
      api.challengeInvestigation(accepted.id, { type: "CHANGE_RULE", payload: { rule_id: "robert-issuer-cap-1", new_threshold: 0.4, user_note: null } }, { idempotencyKey: KEY_2 }),
    );
    expect(error.kind).toBe("no_fixture");
    expect(error.message).toContain("robert-issuer-cap-1 to 30%");
  });

  it("refuses to challenge a job that has not finished", async () => {
    const api = client();
    const policy = await confirmScenarioRules(api, robertScenario);
    const accepted = await api.createInvestigation(
      { persona_id: "robert", policy_id: policy.policy_id, policy_version: policy.version, request: robertPurchase, parent_investigation_id: null },
      { idempotencyKey: KEY_1 },
    );
    await api.getInvestigation(accepted.id);
    const error = await failure(api.challengeInvestigation(accepted.id, change.request, { idempotencyKey: KEY_2 }));
    expect(error).toMatchObject({ kind: "validation", code: "INVESTIGATION_NOT_FINISHED" });
  });

  it("replays the recorded fact correction, and the job then carries it as in the recording", async () => {
    const api = client();
    const { accepted } = await robertFinished(api);
    expect(await api.challengeInvestigation(accepted.id, fact.request, { idempotencyKey: KEY_2 })).toEqual(fact.response);
    expect(await api.getInvestigation(accepted.id)).toEqual(FIXTURES.jobs.robertWithCorrection.response);
  });

  it("echoes any other correction as an UNVERIFIED assertion and changes no figure", async () => {
    const api = client();
    const { accepted, final } = await robertFinished(api);
    const record = final.result?.evidence.find((item) => item.evidence_id === "ev-xiu-ry-weight");
    const response = await api.challengeInvestigation(
      accepted.id,
      { type: "CORRECT_FACT", payload: { evidence_id: "ev-xiu-ry-weight", asserted_value: 0.09, asserted_unit: "fraction", user_note: "My copy says otherwise.", user_source: null } },
      { idempotencyKey: KEY_2 },
    );
    expect(response.proposed_correction).toMatchObject({
      investigation_id: accepted.id,
      evidence_id: "ev-xiu-ry-weight",
      original_value: record?.value,
      original_unit: record?.unit,
      asserted_value: 0.09,
      status: "UNVERIFIED",
      applied_to_calculation: false,
      provenance: { asserted_by: "USER", user_note: "My copy says otherwise.", user_source: null },
    });
    expect(response.policy).toBeNull();
    expect(response.investigation).toBeNull();
    const after = await api.getInvestigation(accepted.id);
    expect(after.result).toEqual(FIXTURES.jobs.robertSucceeded.response.result);
    expect(after.proposed_corrections).toEqual([response.proposed_correction]);
  });

  it("refuses a correction to a figure that is not in the report", async () => {
    const api = client();
    const { accepted } = await robertFinished(api);
    const error = await failure(
      api.challengeInvestigation(accepted.id, { type: "CORRECT_FACT", payload: { evidence_id: "ev-nope", asserted_value: 1, asserted_unit: "count", user_note: "x", user_source: null } }, { idempotencyKey: KEY_2 }),
    );
    expect(error).toMatchObject({ kind: "validation", code: "UNSUPPORTED_CHALLENGE" });
  });

  it("replays the recorded clarification for Mateo: a draft, with no policy and no job", async () => {
    const api = client();
    const { accepted } = await mateoFinished(api);
    const response = await api.challengeInvestigation(accepted.id, preference.request, { idempotencyKey: KEY_2 });
    expect(response).toEqual(preference.response);
    expect(response.policy).toBeNull();
    expect(response.investigation).toBeNull();
  });

  it("refuses a clarification in other words", async () => {
    const api = client();
    const { accepted } = await mateoFinished(api);
    const error = await failure(api.challengeInvestigation(accepted.id, { type: "CLARIFY_PREFERENCE", payload: { text: "I meant coal.", objective_id: null } }, { idempotencyKey: KEY_2 }));
    expect(error.kind).toBe("no_fixture");
  });

  it("answers a challenge to an unknown job with the recorded not-found error", async () => {
    const error = await failure(client().challengeInvestigation("inv-nope", change.request, { idempotencyKey: KEY_2 }));
    expect(error.kind).toBe("not_found");
  });
});
