import type { ApiClient, RequestOptions } from "./client";
import { ApiError, fallbackMessage, type ApiErrorKind } from "./errors";

export interface HttpClientOptions {
  /** Normalized base URL without a trailing slash. */
  baseUrl: string;
  /** Read at call time so a code typed later is picked up; never stored here. */
  getAccessCode: () => string | null;
  /** Called on 401/403 so the app can ask for the access code again. */
  onUnauthorized?: () => void;
  fetchImpl?: typeof fetch;
  timeoutMs?: number;
}

const DEFAULT_TIMEOUT_MS = 20_000;

function kindForStatus(status: number): ApiErrorKind {
  if (status === 401 || status === 403) return "unauthorized";
  if (status === 404) return "not_found";
  if (status === 400 || status === 409 || status === 422) return "validation";
  if (status >= 500) return "server";
  return "invalid_response";
}

/** Reads `{ "error": { "code", "message" } }` or `{ "code", "message" }` if the service sent one. */
function readErrorBody(body: unknown): { code: string | null; message: string | null } {
  if (typeof body !== "object" || body === null) return { code: null, message: null };
  const outer = body as Record<string, unknown>;
  const inner = typeof outer.error === "object" && outer.error !== null ? (outer.error as Record<string, unknown>) : outer;
  return {
    code: typeof inner.code === "string" ? inner.code : null,
    message: typeof inner.message === "string" ? inner.message : null,
  };
}

/**
 * The live client: plain `fetch` against the HTTP API with a bearer access
 * code. No AWS SDK and no credentials in the browser.
 *
 * PHASE 2: validate each response against the shared contract before it
 * reaches the screens; for now the JSON is trusted to match `@/lib/contracts`.
 */
export function createHttpClient(options: HttpClientOptions): ApiClient {
  const fetchImpl = options.fetchImpl ?? ((input, init) => fetch(input, init));
  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;

  async function request<T>(method: "GET" | "POST", path: string, body?: unknown, requestOptions?: RequestOptions): Promise<T> {
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

    const headers: Record<string, string> = { Accept: "application/json" };
    if (body !== undefined) headers["Content-Type"] = "application/json";
    const accessCode = options.getAccessCode();
    if (accessCode) headers.Authorization = `Bearer ${accessCode}`;

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

    let parsed: unknown = undefined;
    let parseFailed = false;
    try {
      const text = await response.text();
      parsed = text === "" ? undefined : JSON.parse(text);
    } catch {
      parseFailed = true;
    }

    if (!response.ok) {
      const kind = kindForStatus(response.status);
      if (kind === "unauthorized") options.onUnauthorized?.();
      const { code, message } = readErrorBody(parsed);
      throw new ApiError(kind, message ?? fallbackMessage(kind), { status: response.status, code });
    }
    if (parseFailed || parsed === undefined) {
      throw new ApiError("invalid_response", fallbackMessage("invalid_response"), { status: response.status });
    }
    return parsed as T;
  }

  const segment = (value: string) => encodeURIComponent(value);

  return {
    mode: "live",
    getPortfolio: (personaId, o) => request("GET", `/portfolios/${segment(personaId)}`, undefined, o),
    interpretRules: (body, o) => request("POST", "/rules/interpret", body, o),
    confirmRules: (body, o) => request("POST", "/rules/confirm", body, o),
    check: (body, o) => request("POST", "/check", body, o),
    createInvestigation: (body, o) => request("POST", "/investigations", body, o),
    getInvestigation: (id, o) => request("GET", `/investigations/${segment(id)}`, undefined, o),
    challengeInvestigation: (id, body, o) => request("POST", `/investigations/${segment(id)}/challenge`, body, o),
  };
}
