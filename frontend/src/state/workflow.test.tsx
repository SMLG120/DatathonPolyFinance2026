import { act, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { createFixturesClient } from "@/lib/api/fixtures-client";
import type { ChallengeResponse, ConfirmResponse, Interpretation, InvestigationAccepted } from "@/lib/contracts";
import { FIXTURES } from "@/lib/fixtures";
import { deferred } from "@/test/deferred";
import { renderWithApp } from "@/test/render";
import { useWorkflow } from "./workflow";

function session(api = createFixturesClient({ latencyMs: 0 })) {
  let current!: ReturnType<typeof useWorkflow>;
  function Probe() { current = useWorkflow(); return null; }
  const view = renderWithApp(<Probe />, { api });
  return {
    view,
    get current() { return current; },
    async select(persona: "robert" | "mateo") {
      act(() => current.actions.selectPersona(persona));
      await waitFor(() => expect(current.state.portfolio.status).toBe("ready"));
      await act(async () => {}); // flush the provider's latest-state effect before calling another action
    },
  };
}

describe("asynchronous actions belong to their originating session", () => {
  it.each(["mateo", "robert"] as const)("ignores a late confirmation after selecting %s, including a fresh session of the same persona", async (persona) => {
    const pending = deferred<ConfirmResponse>();
    const api = createFixturesClient({ latencyMs: 0 });
    api.confirmRules = vi.fn(() => pending.promise); // intentionally ignores cancellation
    const test = session(api);
    await test.select("robert");
    let action!: Promise<unknown>;
    act(() => { action = test.current.actions.confirmRules(test.current.state.proposedRules.map((r) => r.rule_id)); });
    expect(api.confirmRules).toHaveBeenCalledOnce();
    const signal = vi.mocked(api.confirmRules).mock.calls[0]?.[1]?.signal;
    await test.select(persona);
    expect(signal?.aborted).toBe(true);
    await act(async () => { pending.resolve(FIXTURES.confirmRobertV1.response); await action; });
    expect(test.current.state.personaId).toBe(persona);
    expect(test.current.state.policies).toEqual([]);
    expect(test.current.state.confirm.status).toBe("idle");
  });

  it("ignores a late confirmation failure after switching personas", async () => {
    const pending = deferred<ConfirmResponse>();
    const api = createFixturesClient({ latencyMs: 0 });
    api.confirmRules = () => pending.promise;
    const test = session(api);
    await test.select("robert");
    let action!: Promise<unknown>;
    act(() => { action = test.current.actions.confirmRules(test.current.state.proposedRules.map((r) => r.rule_id)); });
    await test.select("mateo");
    await act(async () => { pending.reject(new Error("old request failed")); await action; });
    expect(test.current.state.confirm.status).toBe("idle");
    expect(test.current.state.policies).toEqual([]);
  });

  it("does not poll an old session's late investigation", async () => {
    const pending = deferred<InvestigationAccepted>();
    const api = createFixturesClient({ latencyMs: 0 });
    api.createInvestigation = () => pending.promise;
    const poll = vi.spyOn(api, "getInvestigation");
    const test = session(api);
    await test.select("robert");
    await act(async () => { await test.current.actions.confirmRules(test.current.state.proposedRules.map((r) => r.rule_id)); });
    let action!: Promise<unknown>;
    act(() => { action = test.current.actions.startInvestigation(FIXTURES.checkRobertPreview.request.purchase_request); });
    await test.select("mateo");
    await act(async () => { pending.resolve(FIXTURES.investigationAccepted.response); await action; });
    expect(test.current.state.investigationIds).toEqual([]);
    expect(test.current.state.activeInvestigationId).toBeNull();
    expect(poll).not.toHaveBeenCalled();
  });

  it.each(["changeRule", "correctFact", "clarifyPreference"] as const)("discards a late %s challenge", async (kind) => {
    const pending = deferred<ChallengeResponse>();
    const api = createFixturesClient({ latencyMs: 0 });
    api.challengeInvestigation = () => pending.promise;
    const test = session(api);
    await test.select("robert");
    let action!: Promise<unknown>;
    act(() => { action = test.current.actions.submitChallenge("inv-robert-0001", FIXTURES.challenges[kind].request); });
    await test.select("mateo");
    await act(async () => { pending.resolve(FIXTURES.challenges[kind].response); await action; });
    expect(test.current.state.policies).toEqual([]);
    expect(test.current.state.corrections).toEqual([]);
    expect(test.current.state.preferenceResponse).toBeNull();
    expect(test.current.state.investigationIds).toEqual([]);
    expect(test.current.state.challenge.status).toBe("idle");
  });

  it("ignores an interpretation after leaving and returning to the same persona", async () => {
    const pending = deferred<Interpretation>();
    const api = createFixturesClient({ latencyMs: 0 });
    api.interpretRules = () => pending.promise;
    const test = session(api);
    await test.select("mateo");
    act(() => test.current.actions.setGoalText("I want to avoid oil."));
    let action!: Promise<unknown>;
    act(() => { action = test.current.actions.interpretGoal(); });
    await test.select("robert");
    await test.select("mateo");
    await act(async () => { pending.resolve(FIXTURES.interpret.mateo.response); await action; });
    expect(test.current.state.interpretation).toBeNull();
    expect(test.current.state.interpret.status).toBe("idle");
  });
});
