import type {
  ChallengeResponse,
  CheckResult,
  ConfirmResponse,
  Interpretation,
  InvestigationAccepted,
  InvestigationJob,
  PortfolioResponse,
} from "@/lib/contracts";
import { isReadableResult } from "@/lib/result";
import { ApiError } from "./errors";

/**
 * Shape checks on what the live service sends, done once at the edge.
 *
 * They cover the members the screens read without checking, so an answer in
 * an older or broken shape becomes a visible "could not be read" error
 * instead of a crash or a half-drawn screen. They are not a schema validator:
 * the JSON Schemas in `contracts/schemas` stay the authority, on the server.
 */
const isObject = (value: unknown): value is Record<string, unknown> => typeof value === "object" && value !== null && !Array.isArray(value);
const isString = (value: unknown): value is string => typeof value === "string";
const isNumber = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value);

function unreadable(what: string, status: number | null): never {
  throw new ApiError("invalid_response", `The service sent ${what} in a shape this page does not understand. Nothing is shown in its place.`, { status });
}

const JOB_STATUSES = ["QUEUED", "RUNNING", "SUCCEEDED", "FAILED"];

function isRuleList(value: unknown): boolean {
  return Array.isArray(value) && value.every((rule) => isObject(rule) && isString(rule.rule_id) && isString(rule.rule_type) && isString(rule.status) && isObject(rule.parameters));
}

function isPolicy(value: unknown): boolean {
  return isObject(value) && isString(value.policy_id) && isNumber(value.version) && Array.isArray(value.objectives) && isRuleList(value.rules);
}

/**
 * `interpretation_id`, `clarification_id` and `option_id` are what the page names a question and its
 * answer by, so an interpretation without them is unreadable rather than half-usable. Their values are
 * not constrained: the service numbers questions and drafts from 1 in every answer.
 */
function isInterpretation(value: unknown): boolean {
  return (
    isObject(value) &&
    isString(value.interpretation_id) &&
    Array.isArray(value.objectives) &&
    value.objectives.every((objective) => isObject(objective) && isString(objective.objective_id) && isString(objective.original_words)) &&
    isRuleList(value.proposed_rules) &&
    Array.isArray(value.unsupported) &&
    Array.isArray(value.clarifications) &&
    value.clarifications.every(
      (item) =>
        isObject(item) &&
        isString(item.clarification_id) &&
        isString(item.question) &&
        Array.isArray(item.options) &&
        item.options.every(
          (option) => isObject(option) && isString(option.option_id) && (option.proposed_rule === null || option.proposed_rule === undefined || isRuleList([option.proposed_rule])),
        ),
    )
  );
}

/** The members of a portfolio document the screens read: its id, its date and its weights. */
function isPortfolio(value: unknown): boolean {
  return (
    isObject(value) &&
    isString(value.portfolio_id) &&
    isString(value.valuation_date) &&
    isString(value.base_currency) &&
    isNumber(value.cash_weight) &&
    Array.isArray(value.positions) &&
    value.positions.every((position) => isObject(position) && isString(position.instrument_id) && isNumber(position.weight))
  );
}

function isAccepted(value: unknown): boolean {
  return isObject(value) && isString(value.id) && isString(value.status) && JOB_STATUSES.includes(value.status);
}

export function asPortfolioResponse(value: unknown, status: number | null = null): PortfolioResponse {
  const scenario = isObject(value) ? value.scenario : null;
  const portfolio = isObject(scenario) ? scenario.portfolio : null;
  const persona = isObject(scenario) ? scenario.persona : null;
  const ok =
    isObject(value) &&
    isObject(value.instruments) &&
    Array.isArray(value.purchasable_instrument_ids) &&
    isObject(scenario) &&
    isObject(persona) &&
    Array.isArray(persona.facts) &&
    isObject(portfolio) &&
    isString(portfolio.valuation_date) &&
    isNumber(portfolio.cash_weight) &&
    Array.isArray(portfolio.positions) &&
    portfolio.positions.every((position) => isObject(position) && isString(position.instrument_id) && isNumber(position.weight)) &&
    Array.isArray(scenario.objectives) &&
    isRuleList(scenario.scenario_rules) &&
    Array.isArray(scenario.demo_phrases) &&
    Array.isArray(scenario.demo_requests);
  if (!ok) unreadable("the portfolio", status);
  return value as unknown as PortfolioResponse;
}

export function asInterpretation(value: unknown, status: number | null = null): Interpretation {
  if (!isInterpretation(value)) unreadable("the interpretation", status);
  return value as Interpretation;
}

export function asConfirmResponse(value: unknown, status: number | null = null): ConfirmResponse {
  if (!isObject(value) || !isPolicy(value.policy)) unreadable("the confirmed policy", status);
  return value as unknown as ConfirmResponse;
}

/** A preview or check body. Whether it may be drawn as a verdict is decided where it is drawn (`assessResult`). */
export function asCheckResult(value: unknown, status: number | null = null): CheckResult {
  if (!isReadableResult(value)) unreadable("the check result", status);
  return value;
}

export function asAccepted(value: unknown, status: number | null = null): InvestigationAccepted {
  if (!isAccepted(value)) unreadable("the answer to the investigation request", status);
  return value as InvestigationAccepted;
}

/**
 * A job body. `result` is not checked here on purpose: it is assessed where it
 * is drawn (`assessResult`), so a result that was not executed or cannot be
 * read is shown as such while the steps of the job stay visible.
 */
export function asJob(value: unknown, status: number | null = null): InvestigationJob {
  const ok =
    isObject(value) &&
    isString(value.id) &&
    isString(value.status) &&
    JOB_STATUSES.includes(value.status) &&
    Array.isArray(value.steps) &&
    value.steps.every((step) => isObject(step) && isNumber(step.seq) && isString(step.tool) && isString(step.status)) &&
    Array.isArray(value.explanation) &&
    Array.isArray(value.proposed_corrections) &&
    isObject(value.agent) &&
    (value.failure === null || (isObject(value.failure) && isString(value.failure.message))) &&
    // Optional: the portfolio the job was checked against. Absent on jobs stored before it existed.
    (value.portfolio === undefined || isPortfolio(value.portfolio));
  if (!ok) unreadable("the investigation", status);
  return value as unknown as InvestigationJob;
}

export function asChallengeResponse(value: unknown, status: number | null = null): ChallengeResponse {
  const challenge = isObject(value) ? value.challenge : null;
  const ok =
    isObject(value) &&
    isObject(challenge) &&
    isString(challenge.type) &&
    ((challenge.type === "CORRECT_FACT" && isObject(value.proposed_correction)) ||
      (challenge.type === "CLARIFY_PREFERENCE" && isInterpretation(value.interpretation)) ||
      (challenge.type === "CHANGE_RULE" && isPolicy(value.policy) && isAccepted(value.investigation)));
  if (!ok) unreadable("the answer to the challenge", status);
  return value as unknown as ChallengeResponse;
}
