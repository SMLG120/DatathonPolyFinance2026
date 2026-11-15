import { IDEMPOTENCY_KEY_HEADER, IDEMPOTENCY_KEY_PATTERN } from "@/lib/contracts";
import type { ApiClient, RequestOptions } from "./client";
import { ApiError, fallbackMessage, type ApiErrorDetail, type ApiErrorKind } from "./errors";
import { asAccepted, asChallengeResponse, asCheckResult, asConfirmResponse, asInterpretation, asJob, asPortfolioResponse } from "./validate";

export interface HttpClientOptions {
  /** Normalized base URL without a trailing slash. */
  baseUrl: string;
  /** Read at call time so a code typed later is picked up; never stored here. */
  getAccessCode: () => string | null;
  /** Called on 401 and 403 alike, so the app can ask for the access code again. */
  onUnauthorized?: () => void;
  fetchImpl?: typeof fetch;
  timeoutMs?: number;
}

const DEFAULT_TIMEOUT_MS = 20_000;

function kindForStatus(status: number): ApiErrorKind {
  if (status === 401 || status === 403) return "unauthorized";
  // 410: the record is past its expiry. Like 404, asking again gives the same answer.
  if (status === 404 || status === 410) return "not_found";
  if (status === 400 || status === 409 || status === 422) return "validation";
  if (status === 429) return "rate_limited";
  if (status >= 500) return "server";
  return "invalid_response";
}

/**
 * Reads the contract's error body, `{ "error": { code, message, details, request_id } }`, if the service sent one.
 *
 * A body in any other shape comes from the gateway in front of the service
 * (`{"message":"Forbidden"}`, `{"message":"Too Many Requests"}`). Nothing is
 * read from it: the page then acts on the status alone and words the failure
 * itself (contracts/api.md, "Errors").
 */
function readErrorBody(body: unknown): { code: string | null; message: string | null; details: ApiErrorDetail[]; requestId: string | null } {
  const empty = { code: null, message: null, details: [], requestId: null };
  if (typeof body !== "object" || body === null) return empty;
  const outer = body as Record<string, unknown>;
  if (typeof outer.error !== "object" || outer.error === null) return empty;
  const inner = outer.error as Record<string, unknown>;
  const details = Array.isArray(inner.details)
    ? inner.details.flatMap((detail) =>
        typeof detail === "object" && detail !== null && typeof (detail as ApiErrorDetail).issue === "string"
          ? [{ path: String((detail as ApiErrorDetail).path ?? ""), issue: (detail as ApiErrorDetail).issue }]
          : [],
      )
    : [];
  return {
    code: typeof inner.code === "string" ? inner.code : null,
    message: typeof inner.message === "string" ? inner.message : null,
    details,
    requestId: typeof inner.request_id === "string" ? inner.request_id : null,
  };
}

/**
 * The live client: plain `fetch` against the HTTP API with a bearer access
 * code. No AWS SDK and no credentials in the browser. Every answer passes a
 * shape check (`./validate`) before it reaches a screen.
 */
export function createHttpClient(options: HttpClientOptions): ApiClient {
  const fetchImpl = options.fetchImpl ?? ((input, init) => fetch(input, init));
  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;

  async function request<T>(
    method: "GET" | "POST",
    path: string,
    read: (value: unknown, status: number) => T,
    body?: unknown,
    requestOptions?: RequestOptions & { idempotencyKey?: string },
  ): Promise<T> {
    const headers: Record<string, string> = { Accept: "application/json" };
    if (body !== undefined) headers["Content-Type"] = "application/json";
    const idempotencyKey = requestOptions?.idempotencyKey;
    if (idempotencyKey !== undefined) {
      if (!IDEMPOTENCY_KEY_PATTERN.test(idempotencyKey)) {
        throw new ApiError("validation", "This request could not be sent: its idempotency key is not valid. Nothing was changed.");
      }
      headers[IDEMPOTENCY_KEY_HEADER] = idempotencyKey;
    }
    const accessCode = options.getAccessCode();
    if (accessCode) headers.Authorization = `Bearer ${accessCode}`;

    const controller = new AbortController();
    let timedOut = false;
    const timer = setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, timeoutMs);
    const callerSignal = requestOptions?.signal;
    const onCallerAbort = () => controller.abort();
    if (callerSignal?.aborted) controller.abort();
    else callerSignal?.addEventListener("abort", onCallerAbort, { once: true });

    let response: Response;
    try {
      response = await fetchImpl(`${options.baseUrl}${path}`, {
        method,
        headers,
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: controller.signal,
        // The access code travels in a header we set ourselves; no cookies.
        credentials: "omit",
        cache: "no-store",
      });
    } catch {
      // The thrown value is deliberately not forwarded: it can echo the request.
      if (timedOut) throw new ApiError("timeout", fallbackMessage("timeout"));
      if (controller.signal.aborted) throw new ApiError("aborted", fallbackMessage("aborted"));
      throw new ApiError("network", fallbackMessage("network"));
    } finally {
      clearTimeout(timer);
      callerSignal?.removeEventListener("abort", onCallerAbort);
    }

    let text = "";
    try {
      text = await response.text();
    } catch {
      // A successful answer that broke off on the way is a connection failure, not an answer in the wrong shape.
      // A refusal is still acted on by its status.
      if (response.ok) throw new ApiError(controller.signal.aborted ? "aborted" : "network", fallbackMessage(controller.signal.aborted ? "aborted" : "network"));
    }
    let parsed: unknown = undefined;
    let parseFailed = false;
    try {
      parsed = text === "" ? undefined : JSON.parse(text);
    } catch {
      parseFailed = true;
    }

    if (!response.ok) {
      const kind = kindForStatus(response.status);
      if (kind === "unauthorized") {
        // contracts/api.md, Authentication: 401 and 403 are treated alike, whoever answered, and their body is not read.
        options.onUnauthorized?.();
        throw new ApiError(kind, fallbackMessage(kind), { status: response.status });
      }
      const { code, message, details, requestId } = readErrorBody(parsed);
      throw new ApiError(kind, message ?? fallbackMessage(kind), { status: response.status, code, details, requestId });
    }
    if (parseFailed || parsed === undefined) {
      throw new ApiError("invalid_response", fallbackMessage("invalid_response"), { status: response.status });
    }
    return read(parsed, response.status);
  }

  const segment = (value: string) => encodeURIComponent(value);

  return {
    mode: "live",
    getPortfolio: (personaId, o) => request("GET", `/portfolios/${segment(personaId)}`, asPortfolioResponse, undefined, o),
    interpretRules: (body, o) => request("POST", "/rules/interpret", asInterpretation, body, o),
    confirmRules: (body, o) => request("POST", "/rules/confirm", asConfirmResponse, body, o),
    check: (body, o) => request("POST", "/check", asCheckResult, body, o),
    createInvestigation: (body, o) => request("POST", "/investigations", asAccepted, body, o),
    getInvestigation: (id, o) => request("GET", `/investigations/${segment(id)}`, asJob, undefined, o),
    challengeInvestigation: (id, body, o) =>
      request("POST", `/investigations/${segment(id)}/challenge`, asChallengeResponse, body, {
        signal: o.signal,
        // Only a rule change starts a new investigation; the other challenges carry no key.
        idempotencyKey: body.type === "CHANGE_RULE" ? o.idempotencyKey : undefined,
      }),
  };
}
