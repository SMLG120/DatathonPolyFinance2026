"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useReducer, useRef, type ReactNode } from "react";
import { useAnnounce } from "@/components/ui/Announcer";
import { usePolling, type PollingPhase } from "@/hooks/usePolling";
import { describeError, isAbortError, isApiError, newIdempotencyKey } from "@/lib/api";
import type { ApiErrorKind } from "@/lib/api/errors";
import { canonical } from "@/lib/canonical";
import type {
  ChallengeRequest,
  ChallengeResponse,
  CustomPortfolio,
  Interpretation,
  InvestigationJob,
  Objective,
  PersonaId,
  Policy,
  Portfolio,
  PortfolioResponse,
  ProposedCorrection,
  PurchaseRequest,
  Rule,
} from "@/lib/contracts";
import { applyCustomPortfolio, isScenarioPortfolio, restatedObjective, withCustomPortfolio, type CustomizeFormInput } from "@/lib/customize";
import { fractionToPercentInput, percentInputToFraction } from "@/lib/format";
import { measureKey, validateThreshold } from "@/lib/rules";
import { activeRules, isTerminalJobStatus } from "@/lib/verdict";
import { useRuntime } from "./runtime";
import { t, tf } from "@/lib/i18n";

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

/** A user-triggered request: idle, in flight, or failed with a message that can be shown. */
export interface Operation {
  status: "idle" | "loading" | "error";
  error: string | null;
  /** What kind of failure it was, so "the test data has no recording" can be said calmly. */
  kind: ApiErrorKind | null;
  /** `error.code` of the service's own error body (contract `ErrorCode`), when it sent one. */
  code: string | null;
  /** `error.details[].issue` of the service's own error body: what exactly it refused. */
  issues: string[];
}

const IDLE: Operation = { status: "idle", error: null, kind: null, code: null, issues: [] };
const LOADING: Operation = { status: "loading", error: null, kind: null, code: null, issues: [] };
const failed = (error: unknown): Operation => ({
  status: "error",
  error: describeError(error),
  kind: isApiError(error) ? error.kind : null,
  code: isApiError(error) ? error.code : null,
  issues: isApiError(error) ? error.details.map((detail) => detail.issue) : [],
});

/** The service's error code of a thrown value, when the service itself answered (contract `ErrorCode`). */
const errorCode = (error: unknown): string | null => (isApiError(error) ? error.code : null);

export interface WorkflowState {
  /**
   * The number of the session: it goes up each time a persona is chosen, the same one again included.
   * A request notes it when it starts, and its answer is applied only if the number is still the same,
   * so an answer for an earlier session never lands in a later one.
   */
  session: number;
  personaId: PersonaId | null;
  portfolio: { status: "idle" | "loading" | "ready" | "error"; data: PortfolioResponse | null; error: string | null };
  /**
   * The applied customization of the persona's fictional portfolio, or null for the scenario portfolio.
   * This one value is what the screens show (`derived.effectivePortfolio`) and what every check and
   * investigation sends (`derived.customPortfolio`). Never the scenario's own weights: those are null.
   */
  customPortfolio: CustomPortfolio | null;
  /** True while the scenario objective carries the user's wording instead of the scenario's. */
  objectiveEdited: boolean;
  /**
   * The text in the "Customize this profile" editor while it is open: typed, not applied. Null when the
   * editor is closed. It is kept here, and not in the editor, so that leaving stage 1 does not drop it.
   * Nothing reads it but the editor: it is never shown as the portfolio and never sent.
   */
  customizeDraft: CustomizeFormInput | null;

  /** The user's own sentence in stage 2. Empty until they type or take the scenario's sentence. */
  goalText: string;
  interpret: Operation;
  /** The latest answer to "interpret my words": questions, drafts and what could not become a rule. */
  interpretation: Interpretation | null;
  /** Qualitative objectives, kept apart from rules. */
  objectives: Objective[];
  /** PROPOSED rules: offered by the scenario or drafted from the user's words. Inactive until confirmed. */
  proposedRules: Rule[];
  /** Text of each proposed rule's threshold field, as a percentage. "" means not set. */
  thresholdText: Record<string, string>;
  /**
   * The option chosen for each clarification question, by `clarificationKey`: the answer the question
   * belongs to, then its id. A question's id alone is not enough: the interpreter numbers its questions
   * from 1 in every answer, so the question of a later answer has the id of an earlier one.
   */
  chosenOptions: Record<string, string>;

  confirm: Operation;
  /** Every confirmed policy version this page builds on, oldest first. Versions are immutable. The last one is in force. */
  policies: Policy[];
  /**
   * Versions set aside after the service answered 409 POLICY_VERSION_CONFLICT:
   * a newer version exists than the newest one held here, and no route reads
   * it. They are kept only so that reports made under them keep the version
   * they were checked against; nothing is confirmed or checked on top of them.
   */
  retiredPolicies: Policy[];

  purchase: { instrumentId: string; targetText: string };
  start: Operation;

  investigations: Record<string, InvestigationJob>;
  /** Jobs in the order they were started. */
  investigationIds: string[];
  /** The job being polled. */
  activeInvestigationId: string | null;
  pollEpoch: number;
  /** The report stage 5 shows. Null means the latest. */
  viewedInvestigationId: string | null;

  /** Corrections proposed in this session. Unverified; never applied to a calculation. */
  corrections: ProposedCorrection[];
  challenge: Operation;
  /** The answer to the last "clarify a preference" challenge: a fresh draft interpretation. */
  preferenceResponse: Interpretation | null;
  /** Set by a rule change: the report before and the job after. */
  comparison: { olderId: string; newerId: string } | null;
}

const INITIAL: WorkflowState = {
  session: 0,
  personaId: null,
  portfolio: { status: "idle", data: null, error: null },
  customPortfolio: null,
  objectiveEdited: false,
  customizeDraft: null,
  goalText: "",
  interpret: IDLE,
  interpretation: null,
  objectives: [],
  proposedRules: [],
  thresholdText: {},
  chosenOptions: {},
  confirm: IDLE,
  policies: [],
  retiredPolicies: [],
  purchase: { instrumentId: "", targetText: "" },
  start: IDLE,
  investigations: {},
  investigationIds: [],
  activeInvestigationId: null,
  pollEpoch: 0,
  viewedInvestigationId: null,
  corrections: [],
  challenge: IDLE,
  preferenceResponse: null,
  comparison: null,
};

type Action =
  | { type: "persona/selected"; session: number; personaId: PersonaId }
  | { type: "portfolio/loaded"; personaId: PersonaId; data: PortfolioResponse }
  | { type: "portfolio/failed"; personaId: PersonaId; error: string }
  | { type: "customization/applied"; portfolio: CustomPortfolio; objectiveWords: string | null }
  | { type: "customization/reset" }
  | { type: "customization/draftChanged"; draft: CustomizeFormInput | null }
  | { type: "goal/changed"; text: string }
  | { type: "interpret/started" }
  | { type: "interpret/succeeded"; session: number; personaId: PersonaId; interpretation: Interpretation }
  | { type: "interpret/failed"; session: number; error: unknown }
  | { type: "option/chosen"; interpretationId: string; clarificationId: string; optionId: string; draft: Rule | null }
  | { type: "threshold/changed"; ruleId: string; text: string }
  | { type: "confirm/started" }
  | { type: "confirm/succeeded"; session: number; policy: Policy; ruleIds: string[] }
  | { type: "confirm/failed"; session: number; error: unknown }
  | { type: "purchase/changed"; patch: Partial<WorkflowState["purchase"]> }
  | { type: "start/started" }
  | { type: "start/succeeded"; session: number; investigationId: string }
  | { type: "start/failed"; session: number; error: unknown }
  | { type: "investigation/updated"; investigation: InvestigationJob }
  | { type: "poll/restarted" }
  | { type: "report/viewed"; investigationId: string | null }
  | { type: "challenge/started" }
  | { type: "challenge/failed"; session: number; error: unknown }
  | { type: "challenge/cleared" }
  | { type: "challenge/factRecorded"; session: number; correction: ProposedCorrection }
  | { type: "challenge/preferenceRecorded"; session: number; interpretation: Interpretation }
  | { type: "challenge/ruleChanged"; session: number; policy: Policy; olderId: string; newerId: string };

/**
 * The key of a clarification question in `chosenOptions`, and its React key.
 *
 * The interpreter numbers what it writes from 1 in every answer ("clar-1", "draft-excl-1", "obj-1"), so
 * none of these ids says which answer it came from. A question is therefore named by its answer as well.
 */
export function clarificationKey(interpretationId: string, clarificationId: string): string {
  return `${interpretationId}/${clarificationId}`;
}

/** The chosen options without those of the given answers (an answer that is replaced takes its choices with it). */
function withoutChoicesOf(chosen: WorkflowState["chosenOptions"], interpretationIds: (string | undefined)[]): WorkflowState["chosenOptions"] {
  const prefixes = interpretationIds.flatMap((id) => (id === undefined ? [] : [clarificationKey(id, "")]));
  return Object.fromEntries(Object.entries(chosen).filter(([key]) => !prefixes.some((prefix) => key.startsWith(prefix))));
}

/** `id`, or the first of `id-2`, `id-3`… that nothing else has. */
function freeId(id: string, taken: ReadonlySet<string>): string {
  if (!taken.has(id)) return id;
  let suffix = 2;
  while (taken.has(`${id}-${suffix}`)) suffix += 1;
  return `${id}-${suffix}`;
}

/**
 * Adds drafts to the proposed list without listing the same check twice: a
 * draft that measures what a listed or confirmed rule already measures is
 * left out (the stage says so; nothing is dropped silently).
 *
 * What a rule is, is what it measures, not its id: two answers of the
 * interpreter can give two different rules the same id. A policy cannot hold
 * two rules under one id (contracts/api.md section 4, rule 7), so a draft
 * whose id another rule of the list or of the policy has is listed under an
 * id of its own.
 */
function addDrafts(state: WorkflowState, drafts: Rule[]): Pick<WorkflowState, "proposedRules" | "thresholdText"> {
  const proposedRules = [...state.proposedRules];
  const thresholdText = { ...state.thresholdText };
  const policy = state.policies.at(-1);
  const inForce = activeRules(policy).map(measureKey);
  const taken = new Set([...proposedRules, ...(policy?.rules ?? [])].map((rule) => rule.rule_id));
  for (const draft of drafts) {
    if (draft.status !== "PROPOSED") continue;
    const key = measureKey(draft);
    if (inForce.includes(key) || proposedRules.some((rule) => measureKey(rule) === key)) continue;
    const ruleId = freeId(draft.rule_id, taken);
    taken.add(ruleId);
    proposedRules.push(ruleId === draft.rule_id ? draft : { ...draft, rule_id: ruleId });
    // A system-proposed rule arrives with no number, so its field starts empty.
    thresholdText[ruleId] = fractionToPercentInput(draft.threshold);
  }
  return { proposedRules, thresholdText };
}

/**
 * Brings the objectives of an interpreter's answer into the session's list, and returns the answer with
 * the ids they have there.
 *
 * What an objective is, is its words. One that is already listed word for word is not listed twice. One
 * whose id other words already have gets an id of its own, and the drafts of this answer that name it
 * follow it, so a drafted rule is never shown with, or confirmed under, the objective of another answer.
 */
function adoptObjectives(known: Objective[], answer: Interpretation): { objectives: Objective[]; interpretation: Interpretation } {
  const objectives = [...known];
  const taken = new Set(known.map((objective) => objective.objective_id));
  const listedAs = new Map<string, string>();
  for (const objective of answer.objectives) {
    const same = objectives.find((candidate) => candidate.original_words === objective.original_words);
    const id = same ? same.objective_id : freeId(objective.objective_id, taken);
    listedAs.set(objective.objective_id, id);
    if (same) continue;
    taken.add(id);
    objectives.push(id === objective.objective_id ? objective : { ...objective, objective_id: id });
  }
  if ([...listedAs].every(([from, to]) => from === to)) return { objectives, interpretation: answer };

  const follow = (rule: Rule): Rule => {
    const id = rule.objective_id === null ? undefined : listedAs.get(rule.objective_id);
    return id === undefined || id === rule.objective_id ? rule : { ...rule, objective_id: id };
  };
  return {
    objectives,
    interpretation: {
      ...answer,
      objectives: answer.objectives.map((objective) => ({ ...objective, objective_id: listedAs.get(objective.objective_id) ?? objective.objective_id })),
      proposed_rules: answer.proposed_rules.map(follow),
      clarifications: answer.clarifications.map((clarification) => ({
        ...clarification,
        options: clarification.options.map((option) => (option.proposed_rule ? { ...option, proposed_rule: follow(option.proposed_rule) } : option)),
      })),
    },
  };
}

/**
 * The session's objectives with the words of the scenario objective replaced. `words` null, or the
 * scenario's own words, puts the scenario objective back.
 *
 * Only that one objective changes: same id, same kind, the words verbatim. No rule is created, changed,
 * confirmed or given a number here, and the interpreter is not asked anything.
 */
function restateScenarioObjective(state: WorkflowState, words: string | null): Pick<WorkflowState, "objectives" | "objectiveEdited"> {
  const original = state.portfolio.data?.scenario.objectives[0];
  if (!original) return { objectives: state.objectives, objectiveEdited: false };
  const edited = words !== null && words !== original.original_words;
  const next = edited ? restatedObjective(original, words) : original;
  return {
    objectives: state.objectives.map((objective) => (objective.objective_id === original.objective_id ? next : objective)),
    objectiveEdited: edited,
  };
}

function reducer(state: WorkflowState, action: Action): WorkflowState {
  // Choosing a persona starts a new session, under the number the provider gave it.
  if (action.type === "persona/selected") {
    return { ...INITIAL, session: action.session, personaId: action.personaId, portfolio: { status: "loading", data: null, error: null } };
  }
  // The answer to a request made in an earlier session (before another persona was chosen, or the same one
  // again) is dropped: its policy, job, drafts or error belong to a session that no longer exists.
  if ("session" in action && action.session !== state.session) return state;
  switch (action.type) {

    case "portfolio/loaded": {
      if (state.personaId !== action.personaId) return state;
      const { scenario } = action.data;
      const scripted = scenario.demo_requests[0]?.purchase_request;
      return {
        ...state,
        portfolio: { status: "ready", data: action.data, error: null },
        objectives: scenario.objectives,
        // The scenario's rules are offers: listed as proposed, inactive until the user confirms them.
        ...addDrafts({ ...state, proposedRules: [], thresholdText: {} }, scenario.scenario_rules),
        purchase: scripted ? { instrumentId: scripted.instrument_id, targetText: fractionToPercentInput(scripted.target_direct_weight) } : state.purchase,
      };
    }

    case "portfolio/failed":
      if (state.personaId !== action.personaId) return state;
      return { ...state, portfolio: { status: "error", data: null, error: action.error } };

    case "customization/applied": {
      const scenario = state.portfolio.data?.scenario;
      if (!scenario) return state;
      // Policies and reports are kept: a policy does not depend on the portfolio, and a report is immutable.
      // A refusal of the previous request no longer describes what would be sent, so it is cleared.
      return {
        ...state,
        // The scenario's own weights are the scenario portfolio (contracts/api.md section 2a, rule 5): not a customization.
        customPortfolio: isScenarioPortfolio(action.portfolio, scenario.portfolio) ? null : action.portfolio,
        ...restateScenarioObjective(state, action.objectiveWords),
        customizeDraft: null,
        start: IDLE,
      };
    }

    case "customization/reset":
      return { ...state, customPortfolio: null, ...restateScenarioObjective(state, null), customizeDraft: null, start: IDLE };

    case "customization/draftChanged":
      return state.portfolio.status === "ready" ? { ...state, customizeDraft: action.draft } : state;

    case "goal/changed":
      return { ...state, goalText: action.text };

    case "interpret/started":
      return { ...state, interpret: LOADING };

    case "interpret/succeeded": {
      if (state.personaId !== action.personaId) return state;
      const { objectives, interpretation } = adoptObjectives(state.objectives, action.interpretation);
      return {
        ...state,
        ...addDrafts(state, interpretation.proposed_rules),
        objectives,
        interpret: IDLE,
        interpretation,
        // The answer this one replaces takes the choices made in it along. Those of a clarified preference stay.
        chosenOptions: withoutChoicesOf(state.chosenOptions, [state.interpretation?.interpretation_id, interpretation.interpretation_id]),
      };
    }

    case "interpret/failed":
      return { ...state, interpret: failed(action.error) };

    case "option/chosen":
      return {
        ...state,
        ...(action.draft ? addDrafts(state, [action.draft]) : {}),
        chosenOptions: { ...state.chosenOptions, [clarificationKey(action.interpretationId, action.clarificationId)]: action.optionId },
      };

    case "threshold/changed":
      return { ...state, thresholdText: { ...state.thresholdText, [action.ruleId]: action.text } };

    case "confirm/started":
      return { ...state, confirm: LOADING };

    case "confirm/succeeded": {
      const confirmed = new Set(action.ruleIds);
      return {
        ...state,
        confirm: IDLE,
        policies: [...state.policies, action.policy],
        proposedRules: state.proposedRules.filter((rule) => !confirmed.has(rule.rule_id)),
      };
    }

    case "confirm/failed": {
      if (errorCode(action.error) !== "POLICY_VERSION_CONFLICT") return { ...state, confirm: failed(action.error) };
      // contracts/api.md section 4, rule 8: "On 409 the client drops its policy state and starts the rule stage
      // again: there is no route that reads a stored policy." The versions held here are set aside, and every rule
      // the scenario or the user's own words offer is a proposal again. What is listed now keeps the number typed
      // in it. The next confirmation carries no policy id and no base version, so it creates a new policy.
      const withoutPolicy = { ...state, policies: [] };
      const chosenDrafts = [state.interpretation, state.preferenceResponse].flatMap((answer) =>
        (answer?.clarifications ?? []).flatMap((clarification) => {
          const chosen = state.chosenOptions[clarificationKey(answer?.interpretation_id ?? "", clarification.clarification_id)];
          const draft = clarification.options.find((option) => option.option_id === chosen)?.proposed_rule;
          return draft ? [draft] : [];
        }),
      );
      return {
        ...withoutPolicy,
        confirm: failed(action.error),
        retiredPolicies: [...state.retiredPolicies, ...state.policies],
        ...addDrafts(withoutPolicy, [
          ...(state.portfolio.data?.scenario.scenario_rules ?? []),
          ...(state.interpretation?.proposed_rules ?? []),
          ...(state.preferenceResponse?.proposed_rules ?? []),
          ...chosenDrafts,
        ]),
      };
    }

    case "purchase/changed":
      return { ...state, purchase: { ...state.purchase, ...action.patch }, start: IDLE };

    case "start/started":
      return { ...state, start: LOADING };

    case "start/succeeded":
      return {
        ...state,
        start: IDLE,
        investigationIds: state.investigationIds.includes(action.investigationId) ? state.investigationIds : [...state.investigationIds, action.investigationId],
        activeInvestigationId: action.investigationId,
        viewedInvestigationId: null,
        pollEpoch: state.pollEpoch + 1,
        comparison: null,
      };

    case "start/failed":
      return { ...state, start: failed(action.error) };

    case "investigation/updated": {
      const id = action.investigation.id;
      if (!state.investigationIds.includes(id)) return state;
      const previous = state.investigations[id];
      // A terminal result is immutable: never let a late answer replace it.
      if (previous && isTerminalJobStatus(previous.status)) return state;
      return { ...state, investigations: { ...state.investigations, [id]: action.investigation } };
    }

    case "poll/restarted":
      return { ...state, pollEpoch: state.pollEpoch + 1 };

    case "report/viewed":
      return { ...state, viewedInvestigationId: action.investigationId };

    case "challenge/started":
      return { ...state, challenge: LOADING };

    case "challenge/failed":
      return { ...state, challenge: failed(action.error) };

    case "challenge/cleared":
      return { ...state, challenge: IDLE };

    case "challenge/factRecorded":
      return {
        ...state,
        challenge: IDLE,
        corrections: state.corrections.some((correction) => correction.correction_id === action.correction.correction_id)
          ? state.corrections
          : [...state.corrections, action.correction],
      };

    case "challenge/preferenceRecorded": {
      const { objectives, interpretation } = adoptObjectives(state.objectives, action.interpretation);
      return {
        ...state,
        ...addDrafts(state, interpretation.proposed_rules),
        objectives,
        challenge: IDLE,
        preferenceResponse: interpretation,
        chosenOptions: withoutChoicesOf(state.chosenOptions, [state.preferenceResponse?.interpretation_id, interpretation.interpretation_id]),
      };
    }

    case "challenge/ruleChanged":
      return {
        ...state,
        challenge: IDLE,
        policies: [...state.policies, action.policy],
        investigationIds: state.investigationIds.includes(action.newerId) ? state.investigationIds : [...state.investigationIds, action.newerId],
        activeInvestigationId: action.newerId,
        viewedInvestigationId: null,
        pollEpoch: state.pollEpoch + 1,
        comparison: { olderId: action.olderId, newerId: action.newerId },
      };
  }
}

// ---------------------------------------------------------------------------
// Context
// ---------------------------------------------------------------------------

export interface WorkflowActions {
  selectPersona: (personaId: PersonaId) => void;
  retryPortfolio: () => void;
  /**
   * Applies an edited fictional portfolio and, when given, the user's wording of the scenario objective.
   * Rules, confirmed policies and reports are left exactly as they are; nothing is sent to the service.
   */
  applyCustomization: (portfolio: CustomPortfolio, objectiveWords: string | null) => void;
  /** Puts the scenario portfolio and the scenario objective back. Policies and reports are kept. */
  resetCustomization: () => void;
  /**
   * Keeps the text of the open customization editor (null closes it and discards the text). Nothing is
   * applied, shown as the portfolio or sent: only Apply does that.
   */
  setCustomizeDraft: (draft: CustomizeFormInput | null) => void;
  setGoalText: (text: string) => void;
  /** POST /rules/interpret with the user's sentence. The answer is a draft: nothing in it is active. */
  interpretGoal: () => Promise<void>;
  /**
   * Records the definition chosen for a clarification question and lists the draft rule that option leads to.
   * The question is named by the answer it belongs to (`interpretation_id`) and its id: see `clarificationKey`.
   */
  chooseOption: (interpretationId: string, clarificationId: string, optionId: string) => void;
  setThresholdText: (ruleId: string, text: string) => void;
  /** POST /rules/confirm for the given proposed rules, in one new policy version. Rules without a valid threshold are skipped. */
  confirmRules: (ruleIds: string[]) => Promise<Policy | null>;
  setPurchase: (patch: Partial<WorkflowState["purchase"]>) => void;
  /** POST /investigations under the current policy. Resolves to the job id, or null on failure. */
  /**
   * `portfolio` is given only to run an earlier job's request again: that job's stored portfolio (null for the
   * scenario portfolio). Left out, the applied customization is sent: the portfolio the screens show.
   */
  startInvestigation: (purchase: PurchaseRequest, parentInvestigationId?: string | null, portfolio?: CustomPortfolio | null) => Promise<string | null>;
  /** Starts a fresh poll, with a fresh deadline, of the active job. */
  retryPolling: () => void;
  viewReport: (investigationId: string | null) => void;
  /** POST /investigations/{id}/challenge against the given report. */
  submitChallenge: (investigationId: string, request: ChallengeRequest) => Promise<ChallengeResponse | null>;
  clearChallengeError: () => void;
}

export interface WorkflowDerived {
  /**
   * The fictional portfolio the next check starts from: the scenario's, with cash and positions replaced
   * by `customPortfolio` when one is applied. Every screen that shows the starting portfolio reads this.
   */
  effectivePortfolio: Portfolio | null;
  /**
   * The applied customization, exactly as every POST /check and POST /investigations sends it
   * (`withCustomPortfolio`), or null: the member is then left out. It is the value `effectivePortfolio`
   * is built from, so what is shown and what is sent cannot differ.
   */
  customPortfolio: CustomPortfolio | null;
  /** The policy version in force: the newest. */
  currentPolicy: Policy | null;
  /** The stored policy version a job or result was checked against, when this session holds it (in force or set aside). */
  policyFor: (reference: { policy_id: string | null; policy_version: number | null }) => Policy | null;
  /** The newest job, whatever its status. */
  latestInvestigation: InvestigationJob | null;
  latestInvestigationId: string | null;
  /** The report stage 5 shows. */
  viewedInvestigation: InvestigationJob | null;
  viewedInvestigationId: string | null;
  /** The newest job that produced a result. */
  latestReport: InvestigationJob | null;
  /** Unverified corrections proposed against a report: those the job carries and those made in this session. */
  correctionsFor: (investigationId: string) => ProposedCorrection[];
  /** How the poll of the active job is going. */
  polling: { phase: PollingPhase; error: string | null };
}

interface WorkflowContextValue {
  state: WorkflowState;
  actions: WorkflowActions;
  derived: WorkflowDerived;
}

const WorkflowContext = createContext<WorkflowContextValue | null>(null);

/** One idempotency key per user action: a retry of the same action reuses it, a new action gets a new one. */
function useActionKey(): { keyFor: (signature: string) => string; done: () => void } {
  const held = useRef<{ signature: string; key: string } | null>(null);
  return useMemo(
    () => ({
      keyFor: (signature: string) => {
        if (held.current?.signature !== signature) held.current = { signature, key: newIdempotencyKey() };
        return held.current.key;
      },
      done: () => {
        held.current = null;
      },
    }),
    [],
  );
}

export function WorkflowProvider({ children }: { children: ReactNode }) {
  const { api, timing } = useRuntime();
  const announce = useAnnounce();
  const [state, dispatch] = useReducer(reducer, INITIAL);

  // Actions run from event handlers, after render, and read the latest state here.
  const latest = useRef(state);
  useEffect(() => {
    latest.current = state;
  }, [state]);

  // The session number, counted here and not read back from the state: it is current the moment a persona is
  // chosen, before the next render, so an answer that arrives in between is already known to be late.
  const sessionNumber = useRef(INITIAL.session);
  const portfolioRequest = useRef<AbortController | null>(null);
  // Each selection starts a new session, even when selecting the same persona again.
  // Aborting it also invalidates responses from clients that ignore AbortSignal.
  const sessionRequest = useRef<AbortController | null>(null);
  const startKey = useActionKey();
  const challengeKey = useActionKey();

  useEffect(() => () => {
    portfolioRequest.current?.abort();
    sessionRequest.current?.abort();
  }, []);

  const selectPersona = useCallback(
    (personaId: PersonaId) => {
      sessionRequest.current?.abort();
      sessionRequest.current = new AbortController();
      portfolioRequest.current?.abort();
      const controller = new AbortController();
      portfolioRequest.current = controller;
      startKey.done();
      challengeKey.done();
      sessionNumber.current += 1;
      dispatch({ type: "persona/selected", session: sessionNumber.current, personaId });
      api.getPortfolio(personaId, { signal: controller.signal }).then(
        (data) => {
          if (controller.signal.aborted) return;
          dispatch({ type: "portfolio/loaded", personaId, data });
          announce(t("Portfolio loaded."));
        },
        (error: unknown) => {
          if (controller.signal.aborted || isAbortError(error)) return;
          dispatch({ type: "portfolio/failed", personaId, error: describeError(error) });
        },
      );
    },
    [api, announce, startKey, challengeKey],
  );

  const retryPortfolio = useCallback(() => {
    const personaId = latest.current.personaId;
    if (personaId) selectPersona(personaId);
  }, [selectPersona]);

  const applyCustomization = useCallback(
    (portfolio: CustomPortfolio, objectiveWords: string | null) => {
      if (latest.current.portfolio.status !== "ready") return;
      dispatch({ type: "customization/applied", portfolio, objectiveWords });
      announce(t("Customization applied. No rule was changed and nothing was checked."));
    },
    [announce],
  );

  const resetCustomization = useCallback(() => {
    if (latest.current.portfolio.status !== "ready") return;
    dispatch({ type: "customization/reset" });
    announce(t("The original scenario is restored: its portfolio and its objective."));
  }, [announce]);

  const setCustomizeDraft = useCallback((draft: CustomizeFormInput | null) => dispatch({ type: "customization/draftChanged", draft }), []);

  const setGoalText = useCallback((text: string) => dispatch({ type: "goal/changed", text }), []);

  // True once another persona was chosen (or the same one again) after a request noted `session`. Its answer is
  // then dropped whole: no state, no announcement, no idempotency key of the new session is touched.
  const left = useCallback((session: number) => sessionNumber.current !== session, []);

  const interpretGoal = useCallback(async () => {
    const current = latest.current;
    const live = sessionRequest.current;
    const personaId = current.personaId;
    if (!personaId || !live || live.signal.aborted || current.interpret.status === "loading") return;
    const policy = current.policies.at(-1) ?? null;
    const session = sessionNumber.current;
    dispatch({ type: "interpret/started" });
    try {
      const interpretation = await api.interpretRules({
        persona_id: personaId,
        text: current.goalText.trim(),
        policy_id: policy?.policy_id ?? null,
        policy_version: policy?.version ?? null,
      }, { signal: live.signal });
      if (live.signal.aborted || left(session)) return;
      dispatch({ type: "interpret/succeeded", session, personaId, interpretation });
      const rules = interpretation.proposed_rules.length;
      const questions = interpretation.clarifications.length;
      announce(
        (rules === 1
          ? t("Interpretation ready: 1 drafted rule, inactive until confirmed")
          : tf("Interpretation ready: {count} drafted rules, inactive until confirmed", { count: rules })) +
          (questions > 0 ? (questions === 1 ? t(", and 1 question for you.") : tf(", and {count} questions for you.", { count: questions })) : "."),
      );
    } catch (error) {
      if (live.signal.aborted || isAbortError(error) || left(session)) return;
      dispatch({ type: "interpret/failed", session, error });
    }
  }, [api, announce, left]);

  const chooseOption = useCallback(
    (interpretationId: string, clarificationId: string, optionId: string) => {
      // The question may come from stage 2 ("interpret my words") or from a "clarify a preference" challenge. Both
      // answers can hold a question with the same id, so the question is looked up in the answer it was shown from.
      const answer = [latest.current.interpretation, latest.current.preferenceResponse].find((candidate) => candidate?.interpretation_id === interpretationId);
      const option = answer?.clarifications
        .find((clarification) => clarification.clarification_id === clarificationId)
        ?.options.find((candidate) => candidate.option_id === optionId);
      if (!option || !option.supported) return;
      dispatch({ type: "option/chosen", interpretationId, clarificationId, optionId, draft: option.proposed_rule });
      announce(option.proposed_rule ? t("Definition chosen. Its rule is listed as proposed, without a number until you enter one.") : t("Definition chosen."));
    },
    [announce],
  );

  const setThresholdText = useCallback((ruleId: string, text: string) => dispatch({ type: "threshold/changed", ruleId, text }), []);

  const confirmRules = useCallback(
    async (ruleIds: string[]) => {
      const current = latest.current;
      const live = sessionRequest.current;
      const personaId = current.personaId;
      if (!personaId || !live || live.signal.aborted || current.confirm.status === "loading") return null;
      const confirmations = ruleIds.flatMap((ruleId) => {
        const rule = current.proposedRules.find((candidate) => candidate.rule_id === ruleId);
        const threshold = percentInputToFraction(current.thresholdText[ruleId] ?? "");
        // A rule is only ever confirmed with a number the user can see in its field.
        return rule && threshold !== null && validateThreshold(threshold) === null ? [{ rule, threshold }] : [];
      });
      if (confirmations.length === 0) return null;
      const base = current.policies.at(-1) ?? null;
      const session = sessionNumber.current;
      dispatch({ type: "confirm/started" });
      try {
        const { policy } = await api.confirmRules({
          persona_id: personaId,
          policy_id: base?.policy_id ?? null,
          base_version: base?.version ?? null,
          objectives: current.objectives,
          confirmations,
          withdraw_rule_ids: [],
          change_note: null,
        }, { signal: live.signal });
        if (live.signal.aborted || left(session)) return null;
        dispatch({ type: "confirm/succeeded", session, policy, ruleIds: confirmations.map((confirmation) => confirmation.rule.rule_id) });
        const active = activeRules(policy).length;
        announce(
          active === 1
            ? tf("Confirmed. Policy version {version} is in force with 1 confirmed rule.", { version: policy.version })
            : tf("Confirmed. Policy version {version} is in force with {count} confirmed rules.", { version: policy.version, count: active }),
        );
        return policy;
      } catch (error) {
        if (live.signal.aborted || isAbortError(error) || left(session)) return null;
        dispatch({ type: "confirm/failed", session, error });
        return null;
      }
    },
    [api, announce, left],
  );

  const setPurchase = useCallback((patch: Partial<WorkflowState["purchase"]>) => dispatch({ type: "purchase/changed", patch }), []);

  const startInvestigation = useCallback(
    async (purchase: PurchaseRequest, parentInvestigationId: string | null = null, portfolio?: CustomPortfolio | null) => {
      const current = latest.current;
      const live = sessionRequest.current;
      const policy = current.policies.at(-1);
      if (!current.personaId || !policy || !live || live.signal.aborted || current.start.status === "loading") return null;
      // The same value the screens show. It is part of the signature: another portfolio is another body, so another key.
      // Running a failed job's request again names that job's stored portfolio instead (contracts/api.md section 2a).
      const customPortfolio = portfolio === undefined ? current.customPortfolio : portfolio;
      const signature = [
        current.personaId,
        policy.policy_id,
        policy.version,
        purchase.instrument_id,
        purchase.target_direct_weight,
        parentInvestigationId,
        canonical(customPortfolio),
      ].join("|");
      const session = sessionNumber.current;
      dispatch({ type: "start/started" });
      try {
        const accepted = await api.createInvestigation(
          withCustomPortfolio(
            {
              persona_id: current.personaId,
              policy_id: policy.policy_id,
              policy_version: policy.version,
              request: purchase,
              parent_investigation_id: parentInvestigationId,
            },
            customPortfolio,
          ),
          { idempotencyKey: startKey.keyFor(signature), signal: live.signal },
        );
        // Accepted for a session that was left since: the job is not attached to the one on screen, and the
        // caller is told nothing started, so it does not move to a result that is not this session's.
        if (live.signal.aborted || left(session)) return null;
        startKey.done();
        dispatch({ type: "start/succeeded", session, investigationId: accepted.id });
        announce(t("Investigation accepted. Waiting for its first step."));
        return accepted.id;
      } catch (error) {
        if (live.signal.aborted || isAbortError(error)) return null;
        // contracts/api.md section 6, rule 5: after 503 WORKER_INVOCATION_FAILED the job stored under this key is
        // FAILED, so the same key would replay the 503 for ever: "The client retries with a new key." After every
        // other failure (429, a network error, no answer in time) the key is kept, so a retry cannot start a second job.
        if (left(session)) return null;
        if (errorCode(error) === "WORKER_INVOCATION_FAILED") startKey.done();
        dispatch({ type: "start/failed", session, error });
        return null;
      }
    },
    [api, announce, startKey, left],
  );

  const retryPolling = useCallback(() => dispatch({ type: "poll/restarted" }), []);
  const viewReport = useCallback((investigationId: string | null) => dispatch({ type: "report/viewed", investigationId }), []);
  const clearChallengeError = useCallback(() => dispatch({ type: "challenge/cleared" }), []);

  const submitChallenge = useCallback(
    async (investigationId: string, request: ChallengeRequest) => {
      const live = sessionRequest.current;
      if (!live || live.signal.aborted || latest.current.challenge.status === "loading") return null;
      const session = sessionNumber.current;
      dispatch({ type: "challenge/started" });
      try {
        const response = await api.challengeInvestigation(investigationId, request, {
          idempotencyKey: challengeKey.keyFor(`${investigationId}|${canonical(request)}`),
          signal: live.signal,
        });
        if (live.signal.aborted || left(session)) return null;
        challengeKey.done();
        if (response.proposed_correction) {
          dispatch({ type: "challenge/factRecorded", session, correction: response.proposed_correction });
          announce(t("Your correction is recorded as proposed and unverified. The original evidence is unchanged."));
        } else if (response.interpretation) {
          dispatch({ type: "challenge/preferenceRecorded", session, interpretation: response.interpretation });
          announce(t("Your preference is recorded as a new draft. No stored rule was changed."));
        } else if (response.policy && response.investigation) {
          dispatch({ type: "challenge/ruleChanged", session, policy: response.policy, olderId: investigationId, newerId: response.investigation.id });
          announce(tf("Policy version {version} created. Re-checking the same purchase under it.", { version: response.policy.version }));
        } else {
          throw new Error(t("The answer to the challenge carried nothing to show."));
        }
        return response;
      } catch (error) {
        if (live.signal.aborted || isAbortError(error)) return null;
        // contracts/api.md section 8, CHANGE_RULE: "The client retries the challenge with a new key" after 503
        // WORKER_INVOCATION_FAILED, and only then.
        if (left(session)) return null;
        if (errorCode(error) === "WORKER_INVOCATION_FAILED") challengeKey.done();
        dispatch({ type: "challenge/failed", session, error });
        return null;
      }
    },
    [api, announce, challengeKey, left],
  );

  // --- Polling of the active job -------------------------------------------------
  const activeId = state.activeInvestigationId;
  const active = activeId ? state.investigations[activeId] : undefined;
  const activeIsTerminal = active ? isTerminalJobStatus(active.status) : false;
  const polling = usePolling<InvestigationJob>({
    pollKey: activeId && !activeIsTerminal ? `${activeId}#${state.pollEpoch}` : null,
    fetcher: (signal) => api.getInvestigation(activeId as string, { signal }),
    isTerminal: (investigation) => isTerminalJobStatus(investigation.status),
    onValue: (investigation) => dispatch({ type: "investigation/updated", investigation }),
    intervalMs: timing.pollIntervalMs,
    deadlineMs: timing.pollDeadlineMs,
  });

  const actions = useMemo<WorkflowActions>(
    () => ({
      selectPersona,
      retryPortfolio,
      applyCustomization,
      resetCustomization,
      setCustomizeDraft,
      setGoalText,
      interpretGoal,
      chooseOption,
      setThresholdText,
      confirmRules,
      setPurchase,
      startInvestigation,
      retryPolling,
      viewReport,
      submitChallenge,
      clearChallengeError,
    }),
    [
      selectPersona,
      retryPortfolio,
      applyCustomization,
      resetCustomization,
      setCustomizeDraft,
      setGoalText,
      interpretGoal,
      chooseOption,
      setThresholdText,
      confirmRules,
      setPurchase,
      startInvestigation,
      retryPolling,
      viewReport,
      submitChallenge,
      clearChallengeError,
    ],
  );

  const derived = useMemo<WorkflowDerived>(() => {
    const latestInvestigationId = state.investigationIds.at(-1) ?? null;
    const viewedInvestigationId = state.viewedInvestigationId ?? latestInvestigationId;
    const reports = state.investigationIds.map((id) => state.investigations[id]).filter((job): job is InvestigationJob => Boolean(job?.result));
    const scenarioPortfolio = state.portfolio.data?.scenario.portfolio ?? null;
    return {
      effectivePortfolio: scenarioPortfolio ? applyCustomPortfolio(scenarioPortfolio, state.customPortfolio) : null,
      customPortfolio: state.customPortfolio,
      currentPolicy: state.policies.at(-1) ?? null,
      policyFor: (reference) =>
        [...state.policies, ...state.retiredPolicies].find((policy) => policy.policy_id === reference.policy_id && policy.version === reference.policy_version) ?? null,
      latestInvestigationId,
      latestInvestigation: latestInvestigationId ? (state.investigations[latestInvestigationId] ?? null) : null,
      viewedInvestigationId,
      viewedInvestigation: viewedInvestigationId ? (state.investigations[viewedInvestigationId] ?? null) : null,
      latestReport: reports.at(-1) ?? null,
      correctionsFor: (investigationId) => {
        const carried = state.investigations[investigationId]?.proposed_corrections ?? [];
        const ids = new Set(carried.map((correction) => correction.correction_id));
        return [...carried, ...state.corrections.filter((correction) => correction.investigation_id === investigationId && !ids.has(correction.correction_id))];
      },
      polling: { phase: polling.phase, error: polling.error ? describeError(polling.error) : null },
    };
  }, [state.portfolio.data, state.customPortfolio, state.investigationIds, state.investigations, state.viewedInvestigationId, state.policies, state.retiredPolicies, state.corrections, polling.phase, polling.error]);

  const value = useMemo(() => ({ state, actions, derived }), [state, actions, derived]);
  return <WorkflowContext.Provider value={value}>{children}</WorkflowContext.Provider>;
}

export function useWorkflow(): WorkflowContextValue {
  const value = useContext(WorkflowContext);
  if (!value) throw new Error("useWorkflow must be used inside <WorkflowProvider>");
  return value;
}
