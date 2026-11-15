import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { IDEMPOTENCY_KEY_HEADER } from "@/lib/contracts";
import { FIXTURES } from "@/lib/fixtures";
import { ApiError } from "./errors";
import { createHttpClient } from "./http-client";

const BASE = "https://api.example.test/prod";
const CODE = "demo-code-123";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function client(fetchImpl: typeof fetch, overrides: { code?: string | null; onUnauthorized?: () => void; timeoutMs?: number } = {}) {
  return createHttpClient({
    baseUrl: BASE,
    getAccessCode: () => (overrides.code === undefined ? CODE : overrides.code),
    onUnauthorized: overrides.onUnauthorized,
    fetchImpl,
    timeoutMs: overrides.timeoutMs,
  });
}

async function failure(promise: Promise<unknown>): Promise<ApiError> {
  try {
    await promise;
  } catch (error) {
    if (error instanceof ApiError) return error;
    throw error;
  }
  throw new Error("expected the request to fail");
}

/** Answers every route with the body recorded for it, so the shape checks at the edge see what the service really sends. */
function recordedService() {
  return vi.fn(async (url: string, init: RequestInit) => {
    const route = `${init.method} ${url.slice(BASE.length)}`;
    if (route === "GET /portfolios/robert") return jsonResponse(FIXTURES.portfolioRobert.response);
    if (route === "POST /rules/interpret") return jsonResponse(FIXTURES.interpret.mateo.response);
    if (route === "POST /rules/confirm") return jsonResponse(FIXTURES.confirmRobertV1.response, FIXTURES.confirmRobertV1.status);
    if (route === "POST /check") return jsonResponse(FIXTURES.checkRobertPreview.response);
    if (route === "POST /investigations") return jsonResponse(FIXTURES.investigationAccepted.response, FIXTURES.investigationAccepted.status);
    if (route === "GET /investigations/inv%201%2F2") return jsonResponse(FIXTURES.jobs.robertSucceeded.response);
    if (route === "POST /investigations/inv-mateo-0001/challenge") return jsonResponse(FIXTURES.challenges.clarifyPreference.response);
    if (route === "POST /investigations/inv-robert-0001/challenge") {
      const body = JSON.parse(String(init.body)) as { type: string };
      return jsonResponse(body.type === "CHANGE_RULE" ? FIXTURES.challenges.changeRule.response : FIXTURES.challenges.correctFact.response);
    }
    return jsonResponse(FIXTURES.errors.notFound.response, 404);
  });
}

const KEY = "0b6f0c9e-5a7e-4c0e-9a55-1f2d3c4b5a61";
/** What a stage shows for a request the service refused for its access code. Seen only once a code was accepted again. */
const UNAUTHORIZED_SENTENCE =
  "The service refused the access code that was in use when this was requested. A code has been accepted since, so it can be requested again.";
const calls = (fetchImpl: ReturnType<typeof recordedService>) => fetchImpl.mock.calls as unknown as [string, RequestInit][];
const headersOf = (init: RequestInit | undefined) => (init?.headers ?? {}) as Record<string, string>;

describe("live HTTP client", () => {
  it("calls the seven documented routes with the bearer access code and returns the body the service sent", async () => {
    const fetchImpl = recordedService();
    const api = client(fetchImpl as unknown as typeof fetch);

    expect(await api.getPortfolio("robert")).toEqual(FIXTURES.portfolioRobert.response);
    expect(await api.interpretRules(FIXTURES.interpret.mateo.request)).toEqual(FIXTURES.interpret.mateo.response);
    expect(await api.confirmRules(FIXTURES.confirmRobertV1.request)).toEqual(FIXTURES.confirmRobertV1.response);
    expect(await api.check(FIXTURES.checkRobertPreview.request)).toEqual(FIXTURES.checkRobertPreview.response);
    expect(await api.createInvestigation(FIXTURES.investigationAccepted.request, { idempotencyKey: KEY })).toEqual(FIXTURES.investigationAccepted.response);
    expect(await api.getInvestigation("inv 1/2")).toEqual(FIXTURES.jobs.robertSucceeded.response);
    expect(await api.challengeInvestigation("inv-mateo-0001", FIXTURES.challenges.clarifyPreference.request, { idempotencyKey: KEY })).toEqual(FIXTURES.challenges.clarifyPreference.response);

    expect(calls(fetchImpl).map(([url, init]) => `${init.method} ${url}`)).toEqual([
      `GET ${BASE}/portfolios/robert`,
      `POST ${BASE}/rules/interpret`,
      `POST ${BASE}/rules/confirm`,
      `POST ${BASE}/check`,
      `POST ${BASE}/investigations`,
      `GET ${BASE}/investigations/inv%201%2F2`,
      `POST ${BASE}/investigations/inv-mateo-0001/challenge`,
    ]);
    for (const [, init] of calls(fetchImpl)) {
      expect(headersOf(init).Authorization).toBe(`Bearer ${CODE}`);
      expect(init.credentials).toBe("omit");
    }
    expect(calls(fetchImpl)[1]?.[1].body).toBe(JSON.stringify(FIXTURES.interpret.mateo.request));
    expect(calls(fetchImpl)[3]?.[1].body).toBe(JSON.stringify(FIXTURES.checkRobertPreview.request));
  });

  it("sends the Idempotency-Key header on POST /investigations, with the key it was given", async () => {
    const fetchImpl = recordedService();
    await client(fetchImpl as unknown as typeof fetch).createInvestigation(FIXTURES.investigationAccepted.request, { idempotencyKey: KEY });
    const [, init] = calls(fetchImpl)[0] ?? [];
    expect(IDEMPOTENCY_KEY_HEADER).toBe("Idempotency-Key");
    expect(headersOf(init)[IDEMPOTENCY_KEY_HEADER]).toBe(KEY);
    // The recorded request was made with the same header.
    expect(Object.keys(FIXTURES.investigationAccepted.headers)).toContain(IDEMPOTENCY_KEY_HEADER);
  });

  it("sends the key with a rule change, which starts a job, and with no other challenge or route", async () => {
    const fetchImpl = recordedService();
    const api = client(fetchImpl as unknown as typeof fetch);
    await api.challengeInvestigation("inv-robert-0001", FIXTURES.challenges.changeRule.request, { idempotencyKey: KEY });
    await api.challengeInvestigation("inv-robert-0001", FIXTURES.challenges.correctFact.request, { idempotencyKey: KEY });
    await api.challengeInvestigation("inv-mateo-0001", FIXTURES.challenges.clarifyPreference.request, { idempotencyKey: KEY });
    await api.check(FIXTURES.checkRobertPreview.request);
    await api.getPortfolio("robert");
    expect(calls(fetchImpl).map(([, init]) => headersOf(init)[IDEMPOTENCY_KEY_HEADER])).toEqual([KEY, undefined, undefined, undefined, undefined]);
  });

  it.each(["", "short", "has a space in it", "x".repeat(65)])("refuses to send a request whose idempotency key is malformed (%j)", async (idempotencyKey) => {
    const fetchImpl = recordedService();
    const error = await failure(client(fetchImpl as unknown as typeof fetch).createInvestigation(FIXTURES.investigationAccepted.request, { idempotencyKey }));
    expect(error.kind).toBe("validation");
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it("sends no Authorization header when there is no access code", async () => {
    const fetchImpl = recordedService();
    await client(fetchImpl as unknown as typeof fetch, { code: null }).getPortfolio("robert");
    const [, init] = calls(fetchImpl)[0] ?? [];
    expect(headersOf(init).Authorization).toBeUndefined();
  });

  it("refuses a 200 answer that is not in the agreed shape, instead of passing it to a screen", async () => {
    const wrong = (async () => jsonResponse({ ok: true })) as unknown as typeof fetch;
    for (const call of [
      () => client(wrong).getPortfolio("robert"),
      () => client(wrong).check(FIXTURES.checkRobertPreview.request),
      () => client(wrong).getInvestigation("inv-robert-0001"),
      () => client(wrong).confirmRules(FIXTURES.confirmRobertV1.request),
    ]) {
      expect((await failure(call())).kind).toBe("invalid_response");
    }
  });

  it("reads an interpretation as the service numbers and dates it: ids from 1, milliseconds, a reading that leads to no rule", async () => {
    // The recorded answer with only what differs in what the service sends (see the interpreter's own description).
    const recordedAnswer = structuredClone(FIXTURES.interpret.mateo.response);
    const sent = {
      ...recordedAnswer,
      interpretation_id: "int-0a1b2c3d4e5f",
      created_at: "2026-11-14T15:10:00.123Z",
      clarifications: recordedAnswer.clarifications.map((clarification) => ({
        ...clarification,
        clarification_id: "clar-1",
        about_words: "oil",
        options: clarification.options.map((option) => (option.proposed_rule ? { ...option, proposed_rule: { ...option.proposed_rule, rule_id: "draft-excl-1", original_words: "oil" } } : option)),
      })),
      proposed_rules: recordedAnswer.proposed_rules.map((rule) => ({ ...rule, rule_id: "draft-controversy-2" })),
    };
    expect(sent.clarifications[0]?.options).toHaveLength(4);
    expect(sent.clarifications[0]?.options.some((option) => option.supported && option.proposed_rule === null)).toBe(true);
    const fetchImpl = (async () => jsonResponse(sent)) as unknown as typeof fetch;
    expect(await client(fetchImpl).interpretRules(FIXTURES.interpret.mateo.request)).toEqual(sent);
  });

  it("refuses an interpretation that does not say which answer or which question it is: the page names a question by both", async () => {
    const unnamed: Partial<typeof FIXTURES.interpret.mateo.response> = structuredClone(FIXTURES.interpret.mateo.response);
    delete unnamed.interpretation_id;
    const unnumbered = structuredClone(FIXTURES.interpret.mateo.response);
    for (const clarification of unnumbered.clarifications as Partial<(typeof unnumbered.clarifications)[number]>[]) delete clarification.clarification_id;
    for (const body of [unnamed, unnumbered]) {
      const fetchImpl = (async () => jsonResponse(body)) as unknown as typeof fetch;
      expect((await failure(client(fetchImpl).interpretRules(FIXTURES.interpret.mateo.request))).kind).toBe("invalid_response");
    }
  });

  it.each([401, 403])("reports %i as unauthorized and asks for the access code again", async (status) => {
    const onUnauthorized = vi.fn();
    const fetchImpl = vi.fn(async () => jsonResponse({ message: "Unauthorized" }, status));
    const error = await failure(client(fetchImpl as unknown as typeof fetch, { onUnauthorized }).getPortfolio("robert"));

    expect(error.kind).toBe("unauthorized");
    expect(error.status).toBe(status);
    expect(onUnauthorized).toHaveBeenCalledTimes(1);
  });

  it("carries the service's error code, message, details and request id, as in the recorded error body", async () => {
    const recordedError = FIXTURES.errors.validation;
    const fetchImpl = vi.fn(async () => jsonResponse(recordedError.response, recordedError.status));
    const error = await failure(client(fetchImpl as unknown as typeof fetch).check(FIXTURES.checkRobertPreview.request));

    expect(error).toMatchObject({
      kind: "validation",
      status: recordedError.status,
      code: recordedError.response.error.code,
      message: recordedError.response.error.message,
      requestId: recordedError.response.error.request_id,
    });
    expect(error.details).toEqual(recordedError.response.error.details);
  });

  // contracts/api.md, Authentication: "Clients treat 401 and 403 alike: forget the stored code, show the
  // access-code prompt, do not read the body" — also when the service itself answered, in the error shape.
  it.each([401, 403])("does not read the body of a %i, even the service's own error body, and words the refusal itself (finding F-05)", async (status) => {
    const recordedError = FIXTURES.errors.unauthorized;
    const onUnauthorized = vi.fn();
    const fetchImpl = vi.fn(async () => jsonResponse(recordedError.response, status));
    const error = await failure(client(fetchImpl as unknown as typeof fetch, { onUnauthorized }).getPortfolio("robert"));
    expect(error).toMatchObject({ kind: "unauthorized", status, code: null, requestId: null, message: UNAUTHORIZED_SENTENCE });
    expect(error.details).toEqual([]);
    expect(error.message).not.toContain(recordedError.response.error.message);
    expect(onUnauthorized).toHaveBeenCalledTimes(1);
  });

  // Finding F-01. contracts/api.md, "Errors": a body that is not the error shape comes from the gateway; act on the status alone.
  it.each([
    [401, { message: "Unauthorized" }, "unauthorized", UNAUTHORIZED_SENTENCE],
    [403, { message: "Forbidden" }, "unauthorized", UNAUTHORIZED_SENTENCE],
    [404, { message: "Not Found" }, "not_found", "The service has no record of this item."],
    [429, { message: "Too Many Requests" }, "rate_limited", "The service is receiving too many requests. Wait a moment and try again."],
    [503, { message: "Service Unavailable" }, "server", "The service reported an internal error. Nothing was changed."],
  ] as const)("words a gateway %i itself and reads nothing from its body", async (status, body, kind, sentence) => {
    const fetchImpl = vi.fn(async () => jsonResponse(body, status));
    const error = await failure(client(fetchImpl as unknown as typeof fetch).getPortfolio("robert"));
    expect(error).toMatchObject({ kind, status, code: null, requestId: null, message: sentence });
    expect(error.details).toEqual([]);
    expect(error.message).not.toContain(body.message);
  });

  it("reads nothing from a body whose `error` member is not an object", async () => {
    for (const body of [{ error: "Forbidden", message: "Forbidden" }, { error: null, message: "x", code: "Y", request_id: "z", details: [{ path: "", issue: "i" }] }, ["Forbidden"], "Forbidden"]) {
      const error = await failure(client((async () => jsonResponse(body, 429)) as unknown as typeof fetch).getPortfolio("robert"));
      expect(error).toMatchObject({ kind: "rate_limited", code: null, requestId: null, message: "The service is receiving too many requests. Wait a moment and try again." });
      expect(error.details).toEqual([]);
    }
  });

  it("treats 410 like 404: the record is gone and asking again cannot help", async () => {
    const gone = await failure(client((async () => jsonResponse({ error: { code: "INVESTIGATION_EXPIRED", message: "This investigation has expired.", details: [], request_id: "req-1" } }, 410)) as unknown as typeof fetch).getInvestigation("old"));
    expect(gone).toMatchObject({ kind: "not_found", status: 410, code: "INVESTIGATION_EXPIRED", message: "This investigation has expired." });
  });

  it("reports an answer that breaks off while it is read as a connection failure, not as an unreadable answer", async () => {
    const broken = () => {
      const response = new Response("{}", { status: 200 });
      vi.spyOn(response, "text").mockRejectedValue(new TypeError("network error"));
      return response;
    };
    const error = await failure(client((async () => broken()) as unknown as typeof fetch).getInvestigation("inv-robert-0001"));
    expect(error.kind).toBe("network");
  });

  it("maps server and not-found statuses", async () => {
    const server = await failure(client((async () => jsonResponse({}, 503)) as unknown as typeof fetch).getPortfolio("robert"));
    expect(server.kind).toBe("server");
    const missing = await failure(client((async () => jsonResponse({}, 404)) as unknown as typeof fetch).getInvestigation("nope"));
    expect(missing.kind).toBe("not_found");
  });

  it("reports a connection failure as a network error", async () => {
    const fetchImpl = vi.fn(async () => {
      throw new TypeError("Failed to fetch");
    });
    const error = await failure(client(fetchImpl as unknown as typeof fetch).getPortfolio("robert"));
    expect(error.kind).toBe("network");
  });

  it("reports a body that is not JSON as an invalid response", async () => {
    const fetchImpl = vi.fn(async () => new Response("<html>gateway</html>", { status: 200 }));
    const error = await failure(client(fetchImpl as unknown as typeof fetch).getPortfolio("robert"));
    expect(error.kind).toBe("invalid_response");
  });

  it("cancels the request when the caller aborts", async () => {
    const fetchImpl = vi.fn(
      (_url: string, init: RequestInit) =>
        new Promise<Response>((_resolve, reject) => {
          init.signal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")));
        }),
    );
    const controller = new AbortController();
    const pending = failure(client(fetchImpl as unknown as typeof fetch).getPortfolio("robert", { signal: controller.signal }));
    controller.abort();
    expect((await pending).kind).toBe("aborted");
  });

  describe("time limit", () => {
    beforeEach(() => vi.useFakeTimers());
    afterEach(() => vi.useRealTimers());

    it("gives up with a timeout error when the service does not answer", async () => {
      const fetchImpl = vi.fn(
        (_url: string, init: RequestInit) =>
          new Promise<Response>((_resolve, reject) => {
            init.signal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")));
          }),
      );
      const pending = failure(client(fetchImpl as unknown as typeof fetch, { timeoutMs: 5_000 }).getPortfolio("robert"));
      await vi.advanceTimersByTimeAsync(5_000);
      expect((await pending).kind).toBe("timeout");
    });
  });

  it("never exposes the access code in an error or in the console", async () => {
    const spies = (["log", "info", "warn", "error", "debug"] as const).map((method) =>
      vi.spyOn(console, method).mockImplementation(() => {}),
    );
    const responses: (() => Promise<Response>)[] = [
      async () => jsonResponse({ message: `echo Bearer ${CODE}`.replace(CODE, "***") }, 401),
      async () => {
        throw new TypeError(`Failed to fetch with Authorization: Bearer ${CODE}`);
      },
      async () => jsonResponse({}, 500),
    ];
    for (const respond of responses) {
      const error = await failure(client(respond as unknown as typeof fetch).getPortfolio("robert"));
      expect(JSON.stringify({ ...error, message: error.message, stack: error.stack })).not.toContain(CODE);
    }
    for (const spy of spies) expect(spy).not.toHaveBeenCalled();
  });
});
