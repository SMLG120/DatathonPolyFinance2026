import type {
  ChallengeRequest,
  ChallengeResponse,
  CheckRequest,
  CheckResult,
  ConfirmRequest,
  ConfirmResponse,
  Id,
  InterpretRequest,
  Interpretation,
  InvestigationAccepted,
  InvestigationCreateRequest,
  InvestigationJob,
  PersonaId,
  PortfolioResponse,
} from "@/lib/contracts";
import type { AppMode } from "@/lib/config";

export interface RequestOptions {
  /** Lets the caller cancel a request that a newer one has replaced. */
  signal?: AbortSignal;
}

export interface IdempotentRequestOptions extends RequestOptions {
  /**
   * Sent as the `Idempotency-Key` header. One key per user action: a retry of
   * the same action reuses it, so the service never starts a duplicate job.
   */
  idempotencyKey: string;
}

/**
 * One method per route of the shared contract. The interface talks to the
 * service only through this, so the live client and the fixtures client are
 * interchangeable and every screen can be tested without a network.
 */
export interface ApiClient {
  readonly mode: AppMode;
  /** GET /portfolios/{persona_id} */
  getPortfolio(personaId: PersonaId, options?: RequestOptions): Promise<PortfolioResponse>;
  /** POST /rules/interpret */
  interpretRules(request: InterpretRequest, options?: RequestOptions): Promise<Interpretation>;
  /** POST /rules/confirm */
  confirmRules(request: ConfirmRequest, options?: RequestOptions): Promise<ConfirmResponse>;
  /** POST /check — deterministic, no model. With `draft_rules` it is a preview and nothing is stored. */
  check(request: CheckRequest, options?: RequestOptions): Promise<CheckResult>;
  /** POST /investigations — answers 202 once the job is accepted. Needs an idempotency key. */
  createInvestigation(request: InvestigationCreateRequest, options: IdempotentRequestOptions): Promise<InvestigationAccepted>;
  /** GET /investigations/{id} */
  getInvestigation(investigationId: Id, options?: RequestOptions): Promise<InvestigationJob>;
  /**
   * POST /investigations/{id}/challenge. A CHANGE_RULE challenge starts a new
   * investigation, so it carries an idempotency key as well.
   */
  challengeInvestigation(investigationId: Id, request: ChallengeRequest, options: IdempotentRequestOptions): Promise<ChallengeResponse>;
}

/** A new key for one user action. Matches the contract's IDEMPOTENCY_KEY_PATTERN (letters, digits, `-`, `_`; 8 to 64). */
export function newIdempotencyKey(): string {
  return crypto.randomUUID();
}
