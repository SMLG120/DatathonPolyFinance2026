import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
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

describe("live HTTP client", () => {
  it("calls the documented routes with the bearer access code", async () => {
    const fetchImpl = vi.fn(async () => jsonResponse({ ok: true }));
    const api = client(fetchImpl as unknown as typeof fetch);

    await api.getPortfolio("robert");
    await api.interpretRules({ persona_id: "robert", text: "goal", clarification_answers: [] });
    await api.getInvestigation("inv 1/2");
    await api.challengeInvestigation("inv-1", { kind: "CLARIFY_PREFERENCE", text: "x" });

    const calls = fetchImpl.mock.calls as unknown as [string, RequestInit][];
    expect(calls.map(([url, init]) => `${init.method} ${url}`)).toEqual([
      `GET ${BASE}/portfolios/robert`,
      `POST ${BASE}/rules/interpret`,
      `GET ${BASE}/investigations/inv%201%2F2`,
      `POST ${BASE}/investigations/inv-1/challenge`,
    ]);
    for (const [, init] of calls) {
      expect((init.headers as Record<string, string>).Authorization).toBe(`Bearer ${CODE}`);
      expect(init.credentials).toBe("omit");
    }
    expect(calls[1]?.[1].body).toBe(JSON.stringify({ persona_id: "robert", text: "goal", clarification_answers: [] }));
  });

  it("sends no Authorization header when there is no access code", async () => {
    const fetchImpl = vi.fn(async () => jsonResponse({ ok: true }));
    await client(fetchImpl as unknown as typeof fetch, { code: null }).getPortfolio("robert");
    const [, init] = (fetchImpl.mock.calls as unknown as [string, RequestInit][])[0] ?? [];
    expect((init?.headers as Record<string, string>).Authorization).toBeUndefined();
  });

  it.each([401, 403])("reports %i as unauthorized and asks for the access code again", async (status) => {
    const onUnauthorized = vi.fn();
    const fetchImpl = vi.fn(async () => jsonResponse({ message: "Unauthorized" }, status));
    const error = await failure(client(fetchImpl as unknown as typeof fetch, { onUnauthorized }).getPortfolio("robert"));

    expect(error.kind).toBe("unauthorized");
    expect(error.status).toBe(status);
    expect(onUnauthorized).toHaveBeenCalledTimes(1);
  });

  it("carries the service's error code and message", async () => {
    const fetchImpl = vi.fn(async () => jsonResponse({ error: { code: "TARGET_BELOW_CURRENT", message: "Target is below the current weight." } }, 422));
    const error = await failure(client(fetchImpl as unknown as typeof fetch).check({ persona_id: "robert", purchase: null, rules: [], is_draft_preview: true }));

    expect(error).toMatchObject({ kind: "validation", status: 422, code: "TARGET_BELOW_CURRENT", message: "Target is below the current weight." });
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
