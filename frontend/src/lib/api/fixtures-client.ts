import type { FixtureSimulation } from "@/lib/config";
import {
  EPS,
  IDEMPOTENCY_KEY_PATTERN,
  POLL_INTERVAL_MS,
  SCHEMA_VERSION,
  TERMINAL_JOB_STATUSES,
  type ChallengeRequest,
  type ChallengeResponse,
  type CheckRequest,
  type CheckResult,
  type ConfirmRequest,
  type ConfirmResponse,
  type Id,
  type Instrument,
  type InstrumentId,
  type InterpretRequest,
  type Interpretation,
  type InvestigationAccepted,
  type InvestigationJob,
  type PersonaId,
  type Policy,
  type PortfolioResponse,
  type ProposedCorrection,
  type PurchaseRequest,
  type Rule,
  type UnresolvedPurchaseRequest,
} from "@/lib/contracts";
import { canonical } from "@/lib/canonical";
import { FIXTURES } from "@/lib/fixtures";
import { formatFraction } from "@/lib/format";
import { measureKey } from "@/lib/rules";
import type { ApiClient, IdempotentRequestOptions, RequestOptions } from "./client";
import { ApiError } from "./errors";

/**
 * The fixtures client: a test double for the service that REPLAYS the recorded
 * bodies in `contracts/fixtures/api` (through `@/lib/fixtures`).
 *
 * It contains no calculation and writes no result: every `CheckResult` it
 * returns is a recorded one. A request is answered only when a recorded
 * answer exists for it; anything else is refused with a `no_fixture` error
 * that says what is recorded. Five things are not recordings of the route
 * they answer and are kept deliberately small:
 * - GET /portfolio is recorded for Robert only; for Mateo and Amira the answer
 *   is the contract's scenario file with the registry entries it names, put
 *   together the way the recorded Robert answer is (nothing is computed);
 * - a confirmation writes the stored rules the way contracts/SEMANTICS.md §14
 *   says the server does (status, provenance, new rule id on a change);
 * - the QUEUED and RUNNING snapshots of a job that has only a final recording
 *   are the same job cut short (no result, fewer steps);
 * - a CORRECT_FACT challenge echoes the user's assertion as an UNVERIFIED
 *   correction, as the route does for any evidence record;
 * - POST /check on a stored policy version answers with the recorded result
 *   of the investigation of the same request under the same rules: the same
 *   deterministic engine output, which is what both routes return.
 *
 * Screens show "Test data — fixtures" whenever this client is in use.
 */
export interface FixturesClientOptions {
  simulate?: FixtureSimulation | null;
  /** Artificial delay of every call, so loading states are visible. */
  latencyMs?: number;
}

const DEFAULT_LATENCY_MS = 120;
const CONFIRMED_BY = "demo_user";
/** Stored policies that are not recordings carry this instead of a real hash. */
const UNHASHED = `sha256:${"0".repeat(64)}`;

const clone = <T>(value: T): T => structuredClone(value);
const same = (a: number, b: number) => Math.abs(a - b) <= EPS;
const normalize = (text: string) => text.trim().replace(/\s+/g, " ").replace(/[.!]+$/, "").toLowerCase();

/** The rules a check evaluates: every rule with a number that is confirmed (or, in a preview, proposed). */
function evaluatedKeys(rules: Rule[], preview: boolean): string[] {
  return rules
    .filter((rule) => rule.threshold !== null && (rule.status === "CONFIRMED" || (preview && rule.status === "PROPOSED")))
    .map((rule) => `${measureKey(rule)}|${(rule.threshold as number).toFixed(9)}`)
    .sort();
}

const sameKeys = (a: string[], b: string[]) => a.length === b.length && a.every((key, index) => key === b[index]);

function isResolved(request: PurchaseRequest | UnresolvedPurchaseRequest): request is PurchaseRequest {
  return request.instrument_id !== null && request.target_direct_weight !== null;
}

const sameRequest = (a: PurchaseRequest, b: PurchaseRequest) => a.instrument_id === b.instrument_id && same(a.target_direct_weight, b.target_direct_weight);

function noFixture(message: string): never {
  throw new ApiError("no_fixture", message);
}

function delay(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new ApiError("aborted", "The request was cancelled."));
      return;
    }
    const timer = setTimeout(resolve, ms);
    signal?.addEventListener(
      "abort",
      () => {
        clearTimeout(timer);
        reject(new ApiError("aborted", "The request was cancelled."));
      },
      { once: true },
    );
  });
}

// ---------------------------------------------------------------------------
// Recorded material, indexed
// ---------------------------------------------------------------------------

/** Finished jobs that can answer a new investigation. */
const RECORDED_RESULTS: InvestigationJob[] = [
  FIXTURES.jobs.robertSucceeded.response,
  FIXTURES.jobs.robertAfterChallenge.response,
  FIXTURES.jobs.mateoSucceeded.response,
];

/** Stored policies that exist as recordings (they carry the real content hash and timestamps). */
const RECORDED_POLICIES: Policy[] = [FIXTURES.confirmRobertV1.response.policy, FIXTURES.challenges.changeRule.response.policy as Policy];

const RULE_SLUGS: Record<Rule["rule_type"], (rule: Rule) => string> = {
  max_issuer_exposure: () => "issuer-cap",
  min_issuer_exposure: () => "issuer-min",
  scenario_loss_budget: () => "loss-budget",
  controversy_exclusion: () => "controversy",
  exclusion: (rule) =>
    rule.rule_type === "exclusion" && rule.parameters.definition.kind === "fund_reported_sector"
      ? `excl-${rule.parameters.definition.sector.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`
      : "excl-named",
};

/** Finished checks that can answer POST /check. */
const RECORDED_CHECKS = [FIXTURES.checkRobertPreview, FIXTURES.checkMateoPreviewUnknown, FIXTURES.checkInvalidRequest];

function requestLabel(request: PurchaseRequest): string {
  return `${request.instrument_id} at a final direct weight of ${formatFraction(request.target_direct_weight)}`;
}

function thresholdList(rules: Rule[]): string {
  return rules
    .filter((rule) => rule.status === "CONFIRMED" && rule.threshold !== null)
    .map((rule) => `${RULE_SLUGS[rule.rule_type](rule)} ${formatFraction(rule.threshold)}`)
    .join(", ");
}

// ---------------------------------------------------------------------------
// Portfolios
// ---------------------------------------------------------------------------

function portfolioResponse(personaId: PersonaId): PortfolioResponse {
  if (personaId === FIXTURES.portfolioRobert.response.scenario.persona.persona_id) return FIXTURES.portfolioRobert.response;
  const scenario = FIXTURES.scenarios[personaId];
  const registry = FIXTURES.registries[`${personaId}_synthetic_universe`];
  if (!scenario || !registry) {
    throw new ApiError("not_found", "The test data holds no portfolio for this persona.", { status: 404, code: "NOT_FOUND" });
  }
  // Same construction as the recorded Robert answer: the scenario, plus the
  // registry entries of its positions and of the instruments it asks to buy.
  const ids = new Set<InstrumentId>([
    ...scenario.portfolio.positions.map((position) => position.instrument_id),
    ...scenario.demo_requests.map((request) => request.purchase_request.instrument_id),
  ]);
  const instruments: Record<InstrumentId, Instrument> = {};
  for (const id of ids) {
    const instrument = registry.instruments[id];
    if (instrument) instruments[id] = instrument;
  }
  return { schema_version: SCHEMA_VERSION, scenario, instruments, purchasable_instrument_ids: [...ids].sort() };
}

// ---------------------------------------------------------------------------
// Jobs
// ---------------------------------------------------------------------------

interface JobRecord {
  /** Snapshots returned by successive GETs; the last one repeats. */
  frames: InvestigationJob[];
  polls: number;
  corrections: ProposedCorrection[];
  accepted: InvestigationAccepted;
}

/** The same job, cut short: what GET returns before it is finished. */
function earlierFrames(final: InvestigationJob): InvestigationJob[] {
  const queued: InvestigationJob = {
    ...final,
    status: "QUEUED",
    updated_at: final.created_at,
    agent: { ...final.agent, tool_rounds: 0 },
    steps: [],
    clarification: null,
    result: null,
    explanation: [],
    failure: null,
    proposed_corrections: [],
  };
  const shown = Math.max(1, Math.ceil(final.steps.length / 2));
  const steps = final.steps.slice(0, shown).map((step, index) =>
    index === shown - 1
      ? { ...step, status: "RUNNING" as const, finished_at: null, result_summary: null, evidence_ids: [] }
      : { ...step, evidence_ids: [] },
  );
  const running: InvestigationJob = { ...queued, status: "RUNNING", updated_at: steps.at(-1)?.started_at ?? final.created_at, steps };
  return [queued, running];
}

function framesFor(final: InvestigationJob): InvestigationJob[] {
  const { robertQueued, robertRunning } = FIXTURES.jobs;
  if (final.id === robertQueued.response.id && final.id === robertRunning.response.id) {
    return [robertQueued.response, robertRunning.response, final];
  }
  return [...earlierFrames(final), final];
}

function acceptedFor(final: InvestigationJob): InvestigationAccepted {
  const recordedAccepted = [FIXTURES.investigationAccepted.response, FIXTURES.challenges.changeRule.response.investigation];
  const match = recordedAccepted.find((accepted) => accepted?.id === final.id);
  if (match) return match;
  return {
    schema_version: SCHEMA_VERSION,
    id: final.id,
    status: "QUEUED",
    created_at: final.created_at,
    deadline_at: final.deadline_at,
    expires_at: final.expires_at,
    poll: { path: `/investigations/${final.id}`, interval_ms: POLL_INTERVAL_MS },
  };
}

// ---------------------------------------------------------------------------
// The client
// ---------------------------------------------------------------------------

export function createFixturesClient(options: FixturesClientOptions = {}): ApiClient {
  const simulate = options.simulate ?? null;
  const latencyMs = options.latencyMs ?? DEFAULT_LATENCY_MS;

  /** Stored policy versions per persona, oldest first. */
  const policies = new Map<PersonaId, Policy[]>();
  const jobs = new Map<Id, JobRecord>();
  const jobByKey = new Map<string, Id>();
  let challengeCount = 0;

  const wait = (requestOptions?: RequestOptions) => delay(latencyMs, requestOptions?.signal);

  function storedPolicy(personaId: PersonaId, policyId: Id | null, version: number | null): Policy | null {
    return (policies.get(personaId) ?? []).find((policy) => policy.policy_id === policyId && policy.version === version) ?? null;
  }

  function register(final: InvestigationJob, frames: InvestigationJob[]): InvestigationAccepted {
    const accepted = acceptedFor(final);
    jobs.set(final.id, { frames, polls: 0, corrections: [], accepted });
    return accepted;
  }

  function requireKey(requestOptions: IdempotentRequestOptions | undefined): string {
    const key = requestOptions?.idempotencyKey;
    if (!key || !IDEMPOTENCY_KEY_PATTERN.test(key)) {
      throw new ApiError("validation", "The Idempotency-Key header is missing or malformed.", { status: 400, code: "VALIDATION_ERROR" });
    }
    return key;
  }

  /** Writes the stored rule for one confirmation (SEMANTICS §14) and gives it a server-side id. */
  function storeRule(rule: Rule, threshold: number, personaId: PersonaId, existing: Rule[], confirmedAt: string): Rule {
    const slug = RULE_SLUGS[rule.rule_type](rule);
    const number = existing.filter((other) => RULE_SLUGS[other.rule_type](other) === slug).length + 1;
    const unchanged = rule.threshold !== null && same(rule.threshold, threshold);
    const provenance =
      rule.origin === "FICTIONAL_SCENARIO" && unchanged
        ? ({ origin: "FICTIONAL_SCENARIO", threshold_source: "FICTIONAL_SCENARIO", threshold_quote: null } as const)
        : rule.threshold_source === "USER_WORDS" && unchanged
          ? ({ origin: "USER_STATED", threshold_source: "USER_WORDS", threshold_quote: rule.threshold_quote } as const)
          : ({ origin: "USER_STATED", threshold_source: "USER_ENTERED", threshold_quote: null } as const);
    return {
      ...rule,
      ...provenance,
      rule_id: `${personaId}-${slug}-${number}`,
      threshold,
      status: "CONFIRMED",
      confirmed_at: confirmedAt,
      confirmed_by: CONFIRMED_BY,
      supersedes_rule_id: null,
      superseded_by_rule_id: null,
    };
  }

  function confirm(body: ConfirmRequest): ConfirmResponse {
    const versions = body.policy_id === null ? [] : (policies.get(body.persona_id) ?? []);
    const latest = versions.at(-1) ?? null;
    if (body.policy_id !== null && (!latest || latest.policy_id !== body.policy_id || latest.version !== body.base_version)) {
      const conflict = FIXTURES.errors.policyVersionConflict;
      throw new ApiError("validation", conflict.response.error.message, { status: conflict.status, code: conflict.response.error.code });
    }
    for (const confirmation of body.confirmations) {
      if (typeof confirmation.threshold !== "number" || !Number.isFinite(confirmation.threshold) || confirmation.threshold < 0 || confirmation.threshold > 1) {
        throw new ApiError("validation", "A confirmation must carry the number the user accepted, as a fraction between 0 and 1.", {
          status: 422,
          code: "INVALID_CONFIRMATION",
        });
      }
    }

    const version = (latest?.version ?? 0) + 1;
    // Recorded timestamps: version 1 at 15:00, each later version six minutes on.
    const createdAt = `2026-11-14T15:${String((version - 1) * 6).padStart(2, "0")}:00Z`;
    const rules: Rule[] = (latest?.rules ?? []).map((rule) =>
      body.withdraw_rule_ids.includes(rule.rule_id) && rule.status === "CONFIRMED" ? { ...rule, status: "SUPERSEDED" } : { ...rule },
    );
    for (const { rule, threshold } of body.confirmations) {
      const stored = storeRule(rule, threshold, body.persona_id, rules, createdAt);
      // A confirmed rule that measures the same thing is replaced, and kept in the version as SUPERSEDED.
      const replaced = rules.find((other) => other.status === "CONFIRMED" && measureKey(other) === measureKey(stored));
      if (replaced) {
        replaced.status = "SUPERSEDED";
        replaced.superseded_by_rule_id = stored.rule_id;
        stored.supersedes_rule_id = replaced.rule_id;
      }
      rules.push(stored);
    }
    // Policy order as recorded: a replacement sits right after the rule it supersedes.
    const ordered: Rule[] = [];
    for (const rule of rules) {
      if (rule.supersedes_rule_id !== null && rules.some((other) => other.rule_id === rule.supersedes_rule_id)) continue;
      ordered.push(rule);
      const replacement = rules.find((other) => other.supersedes_rule_id === rule.rule_id);
      if (replacement) ordered.push(replacement);
    }

    const written: Policy = {
      schema_version: SCHEMA_VERSION,
      policy_id: latest?.policy_id ?? `pol-${body.persona_id}-demo`,
      persona_id: body.persona_id,
      version,
      parent_version: latest?.version ?? null,
      created_at: createdAt,
      objectives: body.objectives,
      rules: ordered,
      change_note: body.change_note ?? (version === 1 ? "Rules confirmed by the user." : "Rules changed by the user."),
      content_hash: UNHASHED,
    };
    // When the result is a policy that exists as a recording, the recording is returned, hash and all.
    const state = (policy: Policy) => policy.rules.map((rule) => `${rule.rule_id}|${rule.status}|${rule.threshold}|${rule.origin}`).join(";");
    const recordedTwin = RECORDED_POLICIES.find(
      (policy) => policy.persona_id === written.persona_id && policy.version === written.version && state(policy) === state(written),
    );
    const policy = recordedTwin ? clone(recordedTwin) : written;
    policies.set(body.persona_id, [...versions, policy]);
    return { schema_version: SCHEMA_VERSION, policy: clone(policy) };
  }

  function findRecordedResult(personaId: PersonaId, asked: PurchaseRequest | UnresolvedPurchaseRequest, policy: Policy): InvestigationJob | null {
    if (!isResolved(asked)) return null;
    const request = asked;
    return (
      RECORDED_RESULTS.find((job) => {
        if (job.persona_id !== personaId || !job.resolved_request || !job.result) return false;
        if (!sameRequest(job.resolved_request, request)) return false;
        const evaluated = job.result.rule_results.map((result) => `${result.rule_id}|${result.limit.toFixed(9)}`).sort();
        const confirmed = policy.rules
          .filter((rule) => rule.status === "CONFIRMED" && rule.threshold !== null)
          .map((rule) => `${rule.rule_id}|${(rule.threshold as number).toFixed(9)}`)
          .sort();
        return sameKeys(evaluated, confirmed);
      }) ?? null
    );
  }

  function recordedFor(personaId: PersonaId): string {
    const available = RECORDED_RESULTS.filter((job) => job.persona_id === personaId && job.resolved_request && job.result).map(
      (job) =>
        `${requestLabel(job.resolved_request as PurchaseRequest)} with limits ${(job.result as CheckResult).rule_results
          .map((result) => formatFraction(result.limit))
          .join(" and ")}`,
    );
    return available.length > 0 ? `Recorded for this persona: ${available.join("; ")}.` : "Nothing is recorded for this persona.";
  }

  return {
    mode: "fixtures",

    async getPortfolio(personaId, requestOptions) {
      await wait(requestOptions);
      if (simulate === "portfolio-error") {
        throw new ApiError("server", "Simulated failure (test data): the portfolio service did not answer. Nothing was loaded.", { status: 503 });
      }
      return clone(portfolioResponse(personaId));
    },

    async interpretRules(body: InterpretRequest, requestOptions) {
      await wait(requestOptions);
      const match = Object.values(FIXTURES.interpret).find(
        (fixture) => fixture.request.persona_id === body.persona_id && normalize(fixture.request.text) === normalize(body.text),
      );
      if (!match) {
        const known = Object.values(FIXTURES.interpret).filter((fixture) => fixture.request.persona_id === body.persona_id);
        noFixture(
          known.length > 0
            ? `The test data holds a recorded interpretation for one sentence of this persona only: "${known[0]?.request.text}" Use that sentence, or confirm the rules the scenario offers.`
            : "The test data holds no recorded interpretation for this persona. Confirm the rules the scenario offers; your own words need the live service.",
        );
      }
      return clone<Interpretation>(match.response);
    },

    async confirmRules(body, requestOptions) {
      await wait(requestOptions);
      return confirm(body);
    },

    async check(body: CheckRequest, requestOptions) {
      await wait(requestOptions);
      if (simulate === "check-error") {
        throw new ApiError("server", "Simulated failure (test data): the check service did not answer.", { status: 503 });
      }
      const recordedCheck = RECORDED_CHECKS.find((fixture) => {
        if (fixture.request.persona_id !== body.persona_id || !sameRequest(fixture.request.purchase_request, body.purchase_request)) return false;
        if (fixture.request.draft_rules === null || body.draft_rules === null) {
          return fixture.request.draft_rules === null && body.draft_rules === null && fixture.request.policy_version === body.policy_version;
        }
        return sameKeys(evaluatedKeys(body.draft_rules, true), evaluatedKeys(fixture.request.draft_rules, true));
      });
      if (recordedCheck) return clone(recordedCheck.response);

      if (body.draft_rules === null) {
        // A check of a stored policy version: the engine output recorded for the same request under the same rules.
        const policy = storedPolicy(body.persona_id, body.policy_id, body.policy_version);
        if (!policy) {
          throw new ApiError("not_found", "No stored policy with this id and version.", { status: 404, code: "NOT_FOUND" });
        }
        const finished = findRecordedResult(body.persona_id, body.purchase_request, policy);
        if (finished?.result) return clone(finished.result);
        noFixture(
          `The test data holds no recorded check of ${requestLabel(body.purchase_request)} under these rules (${thresholdList(policy.rules) || "no confirmed rule"}). ${recordedFor(body.persona_id)} Anything else needs the live service.`,
        );
      }

      const previews = RECORDED_CHECKS.filter((fixture) => fixture.request.persona_id === body.persona_id && fixture.request.draft_rules !== null).map(
        (fixture) =>
          `${requestLabel(fixture.request.purchase_request)} with ${(fixture.request.draft_rules ?? [])
            .filter((rule) => rule.status === "PROPOSED" && rule.threshold !== null)
            .map((rule) => `a draft ${RULE_SLUGS[rule.rule_type](rule) === "issuer-cap" ? "single-company limit" : "threshold"} of ${formatFraction(rule.threshold)}`)
            .join(" and ")}`,
      );
      noFixture(
        previews.length > 0
          ? `The test data holds one recorded preview for this persona: ${previews.join("; ")}. Other draft values need the live service.`
          : "The test data holds no recorded preview for this persona. Draft values need the live service.",
      );
    },

    async createInvestigation(body, requestOptions) {
      await wait(requestOptions);
      const key = requireKey(requestOptions);
      const knownId = jobByKey.get(key);
      const known = knownId ? jobs.get(knownId) : undefined;
      if (known) return clone(known.accepted);

      if (simulate === "job-failed") {
        const failed = FIXTURES.jobs.failed.response;
        const accepted = register(failed, [...earlierFrames({ ...failed, failure: null }), failed]);
        jobByKey.set(key, failed.id);
        return clone(accepted);
      }

      const policy = storedPolicy(body.persona_id, body.policy_id, body.policy_version);
      if (!policy) {
        throw new ApiError("not_found", "No stored policy with this id and version.", { status: 404, code: "NOT_FOUND" });
      }
      const final = findRecordedResult(body.persona_id, body.request, policy);
      if (!final) {
        const asked = isResolved(body.request) ? requestLabel(body.request) : "a request in free text";
        noFixture(
          `The test data holds no recorded investigation for ${asked} under these rules (${thresholdList(policy.rules) || "no confirmed rule"}). ${recordedFor(body.persona_id)} Anything else needs the live service.`,
        );
      }
      // A job that never finishes: the first two snapshots, and then the second one for ever.
      const frames = simulate === "poll-timeout" ? earlierFrames(final) : framesFor(final);
      const accepted = register(final, frames);
      jobByKey.set(key, final.id);
      return clone(accepted);
    },

    async getInvestigation(investigationId, requestOptions) {
      await wait(requestOptions);
      const record = jobs.get(investigationId);
      if (!record) {
        const missing = FIXTURES.errors.notFound;
        throw new ApiError("not_found", missing.response.error.message, { status: missing.status, code: missing.response.error.code });
      }
      const frame = record.frames[Math.min(record.polls, record.frames.length - 1)] as InvestigationJob;
      record.polls += 1;
      const job = clone(frame);
      if (TERMINAL_JOB_STATUSES.includes(job.status)) job.proposed_corrections = [...job.proposed_corrections, ...clone(record.corrections)];
      return job;
    },

    async challengeInvestigation(investigationId, body: ChallengeRequest, requestOptions) {
      await wait(requestOptions);
      const record = jobs.get(investigationId);
      const final = record?.frames.at(-1);
      if (!record || !final) {
        const missing = FIXTURES.errors.notFound;
        throw new ApiError("not_found", missing.response.error.message, { status: missing.status, code: missing.response.error.code });
      }
      if (final.status !== "SUCCEEDED" || record.polls < record.frames.length) {
        throw new ApiError("validation", "This investigation has not finished, so it cannot be challenged yet.", { status: 409, code: "INVESTIGATION_NOT_FINISHED" });
      }

      const matches = (fixture: { request: ChallengeRequest; response: ChallengeResponse }) =>
        fixture.response.challenge.investigation_id === investigationId && fixture.request.type === body.type;

      if (body.type === "CORRECT_FACT") {
        const fixture = FIXTURES.challenges.correctFact;
        const evidence = final.result?.evidence.find((item) => item.evidence_id === body.payload.evidence_id);
        if (!evidence) {
          throw new ApiError("validation", "This evidence record is not part of the investigation.", { status: 422, code: "UNSUPPORTED_CHALLENGE" });
        }
        let response: ChallengeResponse;
        if (matches(fixture) && canonical(fixture.request.payload) === canonical(body.payload) && record.corrections.length === 0) {
          response = clone(fixture.response);
        } else {
          challengeCount += 1;
          const number = String(challengeCount + 100).padStart(4, "0");
          const at = final.updated_at;
          response = {
            schema_version: SCHEMA_VERSION,
            challenge: { challenge_id: `ch-${final.persona_id}-${number}`, investigation_id: investigationId, type: "CORRECT_FACT", payload: clone(body.payload), created_at: at },
            proposed_correction: {
              correction_id: `corr-${final.persona_id}-${number}`,
              challenge_id: `ch-${final.persona_id}-${number}`,
              investigation_id: investigationId,
              evidence_id: evidence.evidence_id,
              original_value: evidence.value,
              original_unit: evidence.unit,
              asserted_value: body.payload.asserted_value,
              asserted_unit: body.payload.asserted_unit,
              provenance: { asserted_by: "USER", asserted_at: at, user_note: body.payload.user_note, user_source: body.payload.user_source },
              status: "UNVERIFIED",
              applied_to_calculation: false,
            },
            interpretation: null,
            policy: null,
            investigation: null,
          };
        }
        if (response.proposed_correction) record.corrections.push(clone(response.proposed_correction));
        return response;
      }

      if (body.type === "CLARIFY_PREFERENCE") {
        const fixture = FIXTURES.challenges.clarifyPreference;
        const recordedText = fixture.request.type === "CLARIFY_PREFERENCE" ? fixture.request.payload.text : "";
        if (matches(fixture) && normalize(recordedText) === normalize(body.payload.text)) return clone(fixture.response);
        noFixture(
          matches(fixture)
            ? `The test data holds one recorded clarification for this investigation: "${recordedText}" Other wording needs the live service.`
            : "The test data holds no recorded clarification for this investigation. It needs the live service.",
        );
      }

      const fixture = FIXTURES.challenges.changeRule;
      const recordedChange = fixture.request.type === "CHANGE_RULE" ? fixture.request.payload : null;
      const child = FIXTURES.jobs.robertAfterChallenge.response;
      if (matches(fixture) && recordedChange && fixture.response.policy && recordedChange.rule_id === body.payload.rule_id && same(recordedChange.new_threshold, body.payload.new_threshold)) {
        requireKey(requestOptions);
        const personaId = fixture.response.policy.persona_id;
        const versions = policies.get(personaId) ?? [];
        if (!versions.some((policy) => policy.version === fixture.response.policy?.version)) {
          policies.set(personaId, [...versions, clone(fixture.response.policy)]);
        }
        if (!jobs.has(child.id)) register(child, framesFor(child));
        return clone(fixture.response);
      }
      noFixture(
        matches(fixture) && recordedChange
          ? `The test data holds one recorded rule change for this investigation: ${recordedChange.rule_id} to ${formatFraction(recordedChange.new_threshold, { decimals: 0 })}. Other changes need the live service.`
          : "The test data holds no recorded rule change for this investigation. It needs the live service.",
      );
    },
  };
}
