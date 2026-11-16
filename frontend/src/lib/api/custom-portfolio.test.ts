import { describe, expect, it, vi } from "vitest";
import type { CheckRequest, CustomPortfolio, InvestigationCreateRequest, PurchaseRequest } from "@/lib/contracts";
import { FIXTURES } from "@/lib/fixtures";
import { ApiError } from "./errors";
import { createFixturesClient } from "./fixtures-client";
import { createHttpClient } from "./http-client";

const BASE = "https://api.example.test/prod";
const KEY = "0b6f0c9e-5a7e-4c0e-9a55-1f2d3c4b5a61";
const KEY_2 = "7d1f4b1a-93c2-4f55-8a0e-6b2c9d3e4f10";

const scenario = FIXTURES.portfolioRobert.response.scenario;
const purchase = FIXTURES.investigationAccepted.request.request as PurchaseRequest;
const CUSTOM: CustomPortfolio = { cash_weight: 0.5, positions: [{ instrument_id: "XBB.TO", weight: 0.3 }, { instrument_id: "SPY", weight: 0.2 }] };

async function failure(promise: Promise<unknown>): Promise<ApiError> {
  try {
    await promise;
  } catch (error) {
    if (error instanceof ApiError) return error;
    throw error;
  }
  throw new Error("expected the request to be refused");
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

describe("fixtures client: a customized portfolio is never answered from a recording", () => {
  async function withPolicy() {
    const api = createFixturesClient({ latencyMs: 0 });
    const { policy } = await api.confirmRules({
      persona_id: "robert",
      policy_id: null,
      base_version: null,
      objectives: scenario.objectives,
      confirmations: scenario.scenario_rules.map((rule) => ({ rule, threshold: rule.threshold as number })),
      withdraw_rule_ids: [],
      change_note: null,
    });
    const check: CheckRequest = { persona_id: "robert", policy_id: policy.policy_id, policy_version: policy.version, purchase_request: purchase, draft_rules: null };
    const create: InvestigationCreateRequest = { persona_id: "robert", policy_id: policy.policy_id, policy_version: policy.version, request: purchase, parent_investigation_id: null };
    return { api, check, create };
  }

  it("refuses a check that carries one, with the no-recording error, though the same check without it is recorded", async () => {
    const { api, check } = await withPolicy();
    expect((await api.check(check)).execution.status).toBe("OK");
    const error = await failure(api.check({ ...check, custom_portfolio: CUSTOM }));
    expect(error.kind).toBe("no_fixture");
    expect(error.message).toContain("customized portfolio");
    expect(error.message).toContain("needs the live service");
  });

  it("refuses a draft preview that carries one", async () => {
    const api = createFixturesClient({ latencyMs: 0 });
    const recordedPreview = FIXTURES.checkRobertPreview.request;
    expect((await api.check(recordedPreview)).preview).toBe(true);
    expect((await failure(api.check({ ...recordedPreview, custom_portfolio: CUSTOM }))).kind).toBe("no_fixture");
  });

  it("refuses an investigation that carries one, even under a key that already started the recorded one", async () => {
    const { api, create } = await withPolicy();
    const error = await failure(api.createInvestigation({ ...create, custom_portfolio: CUSTOM }, { idempotencyKey: KEY }));
    expect(error.kind).toBe("no_fixture");
    expect(error.message).toContain("customized portfolio");

    const accepted = await api.createInvestigation(create, { idempotencyKey: KEY_2 });
    expect(accepted.id).toBe(FIXTURES.investigationAccepted.response.id);
    expect((await failure(api.createInvestigation({ ...create, custom_portfolio: CUSTOM }, { idempotencyKey: KEY_2 }))).kind).toBe("no_fixture");
  });

  it("treats an absent or null member as the scenario portfolio", async () => {
    const { api, check, create } = await withPolicy();
    expect((await api.check({ ...check, custom_portfolio: null })).execution.status).toBe("OK");
    expect((await api.createInvestigation({ ...create, custom_portfolio: null }, { idempotencyKey: KEY })).id).toBe(FIXTURES.investigationAccepted.response.id);
  });
});

describe("live HTTP client: custom_portfolio and the job's portfolio", () => {
  const client = (fetchImpl: typeof fetch) => createHttpClient({ baseUrl: BASE, getAccessCode: () => "demo-code-123", fetchImpl });
  const bodyOf = (fetchImpl: ReturnType<typeof vi.fn>, call = 0) => String((fetchImpl.mock.calls[call] as [string, RequestInit])[1].body);

  it("passes the member through untouched, and sends a request without it exactly as written", async () => {
    const fetchImpl = vi.fn(async (url: string) =>
      url.endsWith("/check") ? jsonResponse(FIXTURES.checkRobertPreview.response) : jsonResponse(FIXTURES.investigationAccepted.response, FIXTURES.investigationAccepted.status),
    );
    const api = client(fetchImpl as unknown as typeof fetch);
    const check = FIXTURES.checkRobertPreview.request;
    const create = FIXTURES.investigationAccepted.request;

    await api.check(check);
    await api.createInvestigation(create, { idempotencyKey: KEY });
    expect(bodyOf(fetchImpl, 0)).toBe(JSON.stringify(check));
    expect(bodyOf(fetchImpl, 1)).toBe(JSON.stringify(create));
    expect(bodyOf(fetchImpl, 0)).not.toContain("custom_portfolio");
    expect(bodyOf(fetchImpl, 1)).not.toContain("custom_portfolio");

    await api.check({ ...check, custom_portfolio: CUSTOM });
    await api.createInvestigation({ ...create, custom_portfolio: CUSTOM }, { idempotencyKey: KEY_2 });
    expect(JSON.parse(bodyOf(fetchImpl, 2))).toEqual({ ...check, custom_portfolio: CUSTOM });
    expect(JSON.parse(bodyOf(fetchImpl, 3))).toEqual({ ...create, custom_portfolio: CUSTOM });
  });

  it("shows the service's refusal of a customized portfolio as a validation error with its details", async () => {
    const refusal = {
      ...FIXTURES.errors.validation.response,
      error: {
        ...FIXTURES.errors.validation.response.error,
        code: "VALIDATION_ERROR",
        message: "The customized portfolio is not valid.",
        details: [{ path: "custom_portfolio", issue: "cash_weight plus the position weights must equal 1" }],
      },
    };
    const api = client((async () => jsonResponse(refusal, 400)) as unknown as typeof fetch);
    const error = await failure(api.check({ ...FIXTURES.checkRobertPreview.request, custom_portfolio: CUSTOM }));
    expect(error).toMatchObject({ kind: "validation", status: 400, code: "VALIDATION_ERROR" });
    expect(error.details.map((detail) => detail.issue)).toEqual(["cash_weight plus the position weights must equal 1"]);
  });

  it("accepts a job with or without `portfolio`, and refuses one whose portfolio cannot be read", async () => {
    const job = FIXTURES.jobs.robertSucceeded.response;
    const stored = { ...scenario.portfolio, portfolio_id: "pf-robert-custom-0123456789ab", cash_weight: CUSTOM.cash_weight, positions: CUSTOM.positions };
    const answer = (body: unknown) => client((async () => jsonResponse(body)) as unknown as typeof fetch).getInvestigation(job.id);

    expect((await answer(job)).portfolio).toBeUndefined();
    expect((await answer({ ...job, portfolio: stored })).portfolio).toEqual(stored);
    for (const broken of [null, "pf-robert-fictional-1", { ...stored, positions: [{ instrument_id: "SPY" }] }, { ...stored, cash_weight: "0.5" }]) {
      expect((await failure(answer({ ...job, portfolio: broken }))).kind).toBe("invalid_response");
    }
  });
});
