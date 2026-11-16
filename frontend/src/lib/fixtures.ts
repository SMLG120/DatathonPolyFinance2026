/**
 * The single import point for fixture data.
 *
 * Everything here is a generated copy of `contracts/fixtures/api/*.json` and
 * `contracts/scenarios/*.json` (`npm run sync:contracts`): recorded request and
 * response bodies of the seven routes. Nothing is authored in this file. The
 * fixtures client (`src/lib/api/fixtures-client.ts`) and tests are the only
 * consumers; screens never import it.
 */
import challengeChangeRule from "@/generated/contracts/fixtures/api/challenge_change_rule.json";
import challengeClarifyPreference from "@/generated/contracts/fixtures/api/challenge_clarify_preference.json";
import challengeCorrectFact from "@/generated/contracts/fixtures/api/challenge_correct_fact.json";
import checkInvalidRequest from "@/generated/contracts/fixtures/api/check_invalid_request.json";
import checkMateoPreviewUnknown from "@/generated/contracts/fixtures/api/check_mateo_preview_unknown.json";
import checkRobertPreview from "@/generated/contracts/fixtures/api/check_robert_preview.json";
import confirmRobertV1 from "@/generated/contracts/fixtures/api/confirm_robert_v1.json";
import errorInterpreterTimeout from "@/generated/contracts/fixtures/api/error_interpreter_timeout.json";
import errorNotFound from "@/generated/contracts/fixtures/api/error_not_found.json";
import errorPolicyVersionConflict from "@/generated/contracts/fixtures/api/error_policy_version_conflict.json";
import errorUnauthorized from "@/generated/contracts/fixtures/api/error_unauthorized.json";
import errorValidation from "@/generated/contracts/fixtures/api/error_validation.json";
import interpretAmira from "@/generated/contracts/fixtures/api/interpret_amira_ambiguous.json";
import portfolioAmira from "@/generated/contracts/fixtures/api/portfolio_amira.json";
import interpretMateo from "@/generated/contracts/fixtures/api/interpret_mateo_clarification.json";
import investigationAccepted from "@/generated/contracts/fixtures/api/investigation_accepted.json";
import investigationAmiraClarification from "@/generated/contracts/fixtures/api/investigation_amira_clarification.json";
import investigationFailed from "@/generated/contracts/fixtures/api/investigation_failed.json";
import investigationMateoSucceeded from "@/generated/contracts/fixtures/api/investigation_mateo_succeeded.json";
import investigationRobertAfterChallenge from "@/generated/contracts/fixtures/api/investigation_robert_after_challenge_succeeded.json";
import investigationRobertQueued from "@/generated/contracts/fixtures/api/investigation_robert_queued.json";
import investigationRobertRunning from "@/generated/contracts/fixtures/api/investigation_robert_running.json";
import investigationRobertSucceeded from "@/generated/contracts/fixtures/api/investigation_robert_succeeded.json";
import investigationRobertWithCorrection from "@/generated/contracts/fixtures/api/investigation_robert_with_correction.json";
import portfolioRobert from "@/generated/contracts/fixtures/api/portfolio_robert.json";
import registries from "@/generated/contracts/fixtures/registries.json";
import amiraScenario from "@/generated/contracts/scenarios/amira.json";
import mateoScenario from "@/generated/contracts/scenarios/mateo.json";
import robertScenario from "@/generated/contracts/scenarios/robert.json";
import type {
  ChallengeRequest,
  ChallengeResponse,
  CheckRequest,
  CheckResult,
  ConfirmRequest,
  ConfirmResponse,
  ErrorResponse,
  Instrument,
  InstrumentId,
  InterpretRequest,
  Interpretation,
  InvestigationAccepted,
  InvestigationCreateRequest,
  InvestigationJob,
  PortfolioResponse,
  Scenario,
  Source,
  SourceId,
} from "@/lib/contracts";

/** The wrapper every API fixture has (contracts/schemas/fixture.schema.json). */
interface Envelope {
  fixture_id: string;
  description: string;
  synthetic: boolean;
  synthetic_note: string;
  route: string;
  http_status: number;
  request_headers: Record<string, string>;
  request_body: unknown;
  response_body: unknown;
}

export interface Recorded<Request, Response> {
  fixtureId: string;
  description: string;
  status: number;
  headers: Record<string, string>;
  request: Request;
  response: Response;
}

function recorded<Request, Response>(file: unknown): Recorded<Request, Response> {
  const envelope = file as Envelope;
  return {
    fixtureId: envelope.fixture_id,
    description: envelope.description,
    status: envelope.http_status,
    headers: envelope.request_headers,
    request: envelope.request_body as Request,
    response: envelope.response_body as Response,
  };
}

export interface FixtureRegistry {
  synthetic: boolean;
  synthetic_note: string;
  instruments: Record<InstrumentId, Instrument>;
  sources: Record<SourceId, Source>;
}

export const FIXTURES = {
  portfolioRobert: recorded<null, PortfolioResponse>(portfolioRobert),
  portfolioAmira: recorded<null, PortfolioResponse>(portfolioAmira),
  scenarios: {
    robert: robertScenario as unknown as Scenario,
    mateo: mateoScenario as unknown as Scenario,
    amira: amiraScenario as unknown as Scenario,
  } as Record<string, Scenario>,
  /** Instrument and source registries of the synthetic engine universes, keyed by universe id. */
  registries: registries.universes as unknown as Record<string, FixtureRegistry>,
  interpret: {
    mateo: recorded<InterpretRequest, Interpretation>(interpretMateo),
    amira: recorded<InterpretRequest, Interpretation>(interpretAmira),
  },
  confirmRobertV1: recorded<ConfirmRequest, ConfirmResponse>(confirmRobertV1),
  checkRobertPreview: recorded<CheckRequest, CheckResult>(checkRobertPreview),
  checkMateoPreviewUnknown: recorded<CheckRequest, CheckResult>(checkMateoPreviewUnknown),
  checkInvalidRequest: recorded<CheckRequest, CheckResult>(checkInvalidRequest),
  investigationAccepted: recorded<InvestigationCreateRequest, InvestigationAccepted>(investigationAccepted),
  jobs: {
    robertQueued: recorded<null, InvestigationJob>(investigationRobertQueued),
    robertRunning: recorded<null, InvestigationJob>(investigationRobertRunning),
    robertSucceeded: recorded<null, InvestigationJob>(investigationRobertSucceeded),
    robertWithCorrection: recorded<null, InvestigationJob>(investigationRobertWithCorrection),
    robertAfterChallenge: recorded<null, InvestigationJob>(investigationRobertAfterChallenge),
    mateoSucceeded: recorded<null, InvestigationJob>(investigationMateoSucceeded),
    amiraClarification: recorded<null, InvestigationJob>(investigationAmiraClarification),
    failed: recorded<null, InvestigationJob>(investigationFailed),
  },
  challenges: {
    changeRule: recorded<ChallengeRequest, ChallengeResponse>(challengeChangeRule),
    correctFact: recorded<ChallengeRequest, ChallengeResponse>(challengeCorrectFact),
    clarifyPreference: recorded<ChallengeRequest, ChallengeResponse>(challengeClarifyPreference),
  },
  errors: {
    interpreterTimeout: recorded<InterpretRequest, ErrorResponse>(errorInterpreterTimeout),
    notFound: recorded<null, ErrorResponse>(errorNotFound),
    policyVersionConflict: recorded<ConfirmRequest, ErrorResponse>(errorPolicyVersionConflict),
    unauthorized: recorded<null, ErrorResponse>(errorUnauthorized),
    validation: recorded<unknown, ErrorResponse>(errorValidation),
  },
};
