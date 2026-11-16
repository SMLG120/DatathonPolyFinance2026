import { readAccessCode } from "@/lib/access-code";
import { ApiError, fallbackMessage, type ApiErrorKind } from "@/lib/api/errors";
import type { RuntimeConfig } from "@/lib/config";
import { OVERVIEW_QUESTION, type EvidenceRequest, type EvidenceResponse } from "./types";

export interface EvidenceClient {
  investigate(request: EvidenceRequest, options?: { signal?: AbortSignal }): Promise<EvidenceResponse>;
}

const TIMEOUT_MS = 25_000;
const isList = (value: unknown): value is unknown[] => Array.isArray(value);

/** Shape check of an answer before it reaches the screen. Anything else is refused, never patched up. */
export function asEvidenceResponse(value: unknown): EvidenceResponse {
  const body = value as Partial<EvidenceResponse> | null;
  const ok =
    typeof body === "object" &&
    body !== null &&
    typeof body.schema_version === "string" &&
    body.schema_version.startsWith("evidence-investigator/") &&
    typeof body.summary === "object" &&
    body.summary !== null &&
    typeof body.explanation === "string" &&
    typeof body.headline === "string" &&
    isList(body.verified_findings) &&
    isList(body.missing_evidence) &&
    isList(body.hypothetical_scenarios) &&
    isList(body.next_evidence) &&
    isList(body.sources) &&
    isList(body.limitations);
  if (!ok) throw new ApiError("invalid_response", fallbackMessage("invalid_response"));
  return body as EvidenceResponse;
}

function kindForStatus(status: number): ApiErrorKind {
  if (status === 401 || status === 403) return "unauthorized";
  if (status === 404 || status === 410) return "not_found";
  if (status === 400 || status === 409 || status === 422) return "validation";
  if (status === 429) return "rate_limited";
  return status >= 500 ? "server" : "invalid_response";
}

/** Live: plain `fetch` with the bearer access code, like the main client. No AWS SDK, no credentials in the page. */
export function createHttpEvidenceClient(baseUrl: string, getAccessCode: () => string | null = readAccessCode, fetchImpl: typeof fetch = (input, init) => fetch(input, init)): EvidenceClient {
  return {
    async investigate(request, options) {
      const controller = new AbortController();
      let timedOut = false;
      const timer = setTimeout(() => {
        timedOut = true;
        controller.abort();
      }, TIMEOUT_MS);
      const onAbort = () => controller.abort();
      options?.signal?.addEventListener("abort", onAbort, { once: true });
      try {
        const headers: Record<string, string> = { Accept: "application/json", "Content-Type": "application/json" };
        const code = getAccessCode();
        if (code) headers.Authorization = `Bearer ${code}`;
        let response: Response;
        let parsed: unknown;
        try {
          response = await fetchImpl(`${baseUrl}/evidence/investigate`, {
            method: "POST",
            headers,
            body: JSON.stringify(request),
            signal: controller.signal,
            credentials: "omit",
            cache: "no-store",
          });
          const text = await response.text();
          parsed = text === "" ? undefined : JSON.parse(text);
        } catch (error) {
          if (timedOut) throw new ApiError("timeout", fallbackMessage("timeout"));
          if (controller.signal.aborted) throw new ApiError("aborted", fallbackMessage("aborted"));
          if (error instanceof SyntaxError) throw new ApiError("invalid_response", fallbackMessage("invalid_response"));
          throw new ApiError("network", fallbackMessage("network"));
        }
        if (!response.ok) {
          const kind = kindForStatus(response.status);
          const inner = (parsed as { error?: { message?: unknown; code?: unknown } } | undefined)?.error;
          // A 404 on the route itself means the service was deployed without the investigator.
          const message = kind !== "unauthorized" && typeof inner?.message === "string" ? inner.message : fallbackMessage(kind);
          throw new ApiError(kind, message, { status: response.status, code: typeof inner?.code === "string" ? inner.code : null });
        }
        return asEvidenceResponse(parsed);
      } finally {
        clearTimeout(timer);
        options?.signal?.removeEventListener("abort", onAbort);
      }
    },
  };
}

interface Recorded {
  answers: Record<string, { base: EvidenceResponse; by_question: Record<string, Partial<EvidenceResponse>> }>;
}

export const NO_RECORDED_ANSWER =
  "The test data holds recorded answers for the suggested questions only (Robert and Mateo). Free-form questions need the live service.";

/**
 * Test data: answers recorded from the real service code on the synthetic universes
 * (backend/tests/holdings_evidence/record_frontend_fixtures.py). Loaded on demand; nothing is computed here.
 */
export function createRecordedEvidenceClient(load: () => Promise<Recorded> = async () => (await import("./recorded-answers.json")).default as unknown as Recorded): EvidenceClient {
  return {
    async investigate(request) {
      const recorded = await load();
      const scope = recorded.answers[`${request.persona_id}|${request.fund_id ?? "*"}`];
      if (!scope) throw new ApiError("no_fixture", NO_RECORDED_ANSWER);
      const { base } = scope;
      const difference = request.question === OVERVIEW_QUESTION ? {} : scope.by_question[request.question];
      if (difference === undefined) throw new ApiError("no_fixture", NO_RECORDED_ANSWER);
      return asEvidenceResponse({ ...base, ...difference });
    },
  };
}

export function createEvidenceClient(config: RuntimeConfig): EvidenceClient {
  return config.mode === "live" && config.apiBaseUrl ? createHttpEvidenceClient(config.apiBaseUrl) : createRecordedEvidenceClient();
}
