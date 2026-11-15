import type {
  ChallengeRequest,
  ChallengeResponse,
  CheckRequest,
  CheckResponse,
  ConfirmRulesRequest,
  ConfirmRulesResponse,
  CreateInvestigationRequest,
  CreateInvestigationResponse,
  InterpretRequest,
  InterpretResponse,
  Investigation,
  PersonaId,
  PortfolioResponse,
} from "@/lib/contracts";
import type { AppMode } from "@/lib/config";

export interface RequestOptions {
  /** Lets the caller cancel a request that a newer one has replaced. */
  signal?: AbortSignal;
}

/**
 * One method per route in BUILD_BRIEF §7. The interface talks to the service
 * only through this, so the live client and the fixtures client are
 * interchangeable and every screen can be tested without a network.
 */
export interface ApiClient {
  readonly mode: AppMode;
  /** GET /portfolios/{persona} */
  getPortfolio(personaId: PersonaId, options?: RequestOptions): Promise<PortfolioResponse>;
  /** POST /rules/interpret */
  interpretRules(request: InterpretRequest, options?: RequestOptions): Promise<InterpretResponse>;
  /** POST /rules/confirm */
  confirmRules(request: ConfirmRulesRequest, options?: RequestOptions): Promise<ConfirmRulesResponse>;
  /** POST /check — deterministic, no model. Also used for labelled draft previews. */
  check(request: CheckRequest, options?: RequestOptions): Promise<CheckResponse>;
  /** POST /investigations — answers 202 once the job is accepted. */
  createInvestigation(
    request: CreateInvestigationRequest,
    options?: RequestOptions,
  ): Promise<CreateInvestigationResponse>;
  /** GET /investigations/{id} */
  getInvestigation(investigationId: string, options?: RequestOptions): Promise<Investigation>;
  /** POST /investigations/{id}/challenge */
  challengeInvestigation(
    investigationId: string,
    request: ChallengeRequest,
    options?: RequestOptions,
  ): Promise<ChallengeResponse>;
}
