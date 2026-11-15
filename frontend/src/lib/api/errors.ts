export type ApiErrorKind =
  /** The request never reached the service (offline, DNS, CORS, connection reset). */
  | "network"
  /** No response within the client-side time limit. */
  | "timeout"
  /** 401 or 403: the access code is missing or was not accepted. */
  | "unauthorized"
  | "not_found"
  /** 400, 409 or 422: the service rejected the request as invalid. */
  | "validation"
  /** 429: too many requests. */
  | "rate_limited"
  /** 5xx. */
  | "server"
  /** The response was not the JSON the shared contract describes. */
  | "invalid_response"
  /** Fixtures mode only: the test data holds no recorded answer for this request. */
  | "no_fixture"
  /** The caller cancelled the request (a newer request replaced it, or the view closed). */
  | "aborted";

export interface ApiErrorDetail {
  path: string;
  issue: string;
}

/**
 * Every failure of the API layer, in a form that is safe to show to the user.
 * It never carries request headers, so the access code cannot leak through it.
 */
export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly status: number | null;
  /** `error.code` of the service's error body (contract `ErrorCode`), when it sent one. */
  readonly code: string | null;
  readonly details: ApiErrorDetail[];
  readonly requestId: string | null;

  constructor(
    kind: ApiErrorKind,
    message: string,
    options: { status?: number | null; code?: string | null; details?: ApiErrorDetail[]; requestId?: string | null } = {},
  ) {
    super(message);
    this.name = "ApiError";
    this.kind = kind;
    this.status = options.status ?? null;
    this.code = options.code ?? null;
    this.details = options.details ?? [];
    this.requestId = options.requestId ?? null;
  }
}

export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError;
}

export function isAbortError(error: unknown): boolean {
  if (isApiError(error)) return error.kind === "aborted";
  return error instanceof DOMException && error.name === "AbortError";
}

const FALLBACK_MESSAGES: Record<ApiErrorKind, string> = {
  network: "The service could not be reached. Check the connection and try again.",
  timeout: "The service did not answer in time. Try again.",
  unauthorized: "The access code was not accepted.",
  not_found: "The service has no record of this item.",
  validation: "The service rejected the request as invalid.",
  rate_limited: "The service is receiving too many requests. Wait a moment and try again.",
  server: "The service reported an internal error. Nothing was changed.",
  invalid_response: "The service sent an answer this page could not read. Nothing is shown in its place.",
  no_fixture: "The test data holds no recorded answer for this request.",
  aborted: "The request was cancelled.",
};

/** A sentence that can be shown to the user for any thrown value. */
export function describeError(error: unknown): string {
  if (isApiError(error)) return error.message || FALLBACK_MESSAGES[error.kind];
  return "Something went wrong in this page. Try again.";
}

export function fallbackMessage(kind: ApiErrorKind): string {
  return FALLBACK_MESSAGES[kind];
}
