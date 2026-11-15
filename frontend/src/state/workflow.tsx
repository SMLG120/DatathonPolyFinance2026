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
  Interpretation,
  InvestigationJob,
  Objective,
  PersonaId,
  Policy,
  PortfolioResponse,
  ProposedCorrection,
  PurchaseRequest,
  Rule,
} from "@/lib/contracts";
import { fractionToPercentInput, percentInputToFraction } from "@/lib/format";
import { measureKey, validateThreshold } from "@/lib/rules";
import { activeRules, isTerminalJobStatus } from "@/lib/verdict";
import { useRuntime } from "./runtime";

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

/** A user-triggered request: idle, in flight, or failed with a message that can be shown. */
export interface Operation {
  status: "idle" | "loading" | "error";
  error: string | null;
  /** What kind of failure it was, so "the test data has no recording" can be said calmly. */
  kind: ApiErrorKind | null;
}

const IDLE: Operation = { status: "idle", error: null, kind: null };
const LOADING: Operation = { status: "loading", error: null, kind: null };
const failed = (error: unknown): Operation => ({ status: "error", error: describeError(error), kind: isApiError(error) ? error.kind : null });

export interface WorkflowState {
  personaId: PersonaId | null;
  portfolio: { status: "idle" | "loading" | "ready" | "error"; data: PortfolioResponse | null; error: string | null };

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
  /** The option chosen for each clarification question, by clarification id. */
  chosenOptions: Record<string, string>;

  confirm: Operation;
  /** Every confirmed policy version of this session, oldest first. Versions are immutable. */
  policies: Policy[];

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
  personaId: null,
  portfolio: { status: "idle", data: null, error: null },
  goalText: "",
  interpret: IDLE,
  interpretation: null,
  objectives: [],
  proposedRules: [],
  thresholdText: {},
  chosenOptions: {},
  confirm: IDLE,
  policies: [],
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
  | { type: "persona/selected"; personaId: PersonaId }
  | { type: "portfolio/loaded"; personaId: PersonaId; data: PortfolioResponse }
  | { type: "portfolio/failed"; personaId: PersonaId; error: string }
  | { type: "goal/changed"; text: string }
  | { type: "interpret/started" }
  | { type: "interpret/succeeded"; personaId: PersonaId; interpretation: Interpretation }
  | { type: "interpret/failed"; error: unknown }
  | { type: "option/chosen"; clarificationId: string; optionId: string; draft: Rule | null }
  | { type: "threshold/changed"; ruleId: string; text: string }
  | { type: "confirm/started" }
  | { type: "confirm/succeeded"; policy: Policy; ruleIds: string[] }
  | { type: "confirm/failed"; error: unknown }
  | { type: "purchase/changed"; patch: Partial<WorkflowState["purchase"]> }
  | { type: "start/started" }
  | { type: "start/succeeded"; investigationId: string }
  | { type: "start/failed"; error: unknown }
  | { type: "investigation/updated"; investigation: InvestigationJob }
  | { type: "poll/restarted" }
  | { type: "report/viewed"; investigationId: string | null }
  | { type: "challenge/started" }
  | { type: "challenge/failed"; error: unknown }
  | { type: "challenge/cleared" }
  | { type: "challenge/factRecorded"; correction: ProposedCorrection }
  | { type: "challenge/preferenceRecorded"; interpretation: Interpretation }
  | { type: "challenge/ruleChanged"; policy: Policy; olderId: string; newerId: string };

/**
 * Adds drafts to the proposed list without listing the same check twice: a
 * draft that measures what a listed or confirmed rule already measures is
 * left out (the stage says so; nothing is dropped silently).
 */
function addDrafts(state: WorkflowState, drafts: Rule[]): Pick<WorkflowState, "proposedRules" | "thresholdText"> {
  const proposedRules = [...state.proposedRules];
  const thresholdText = { ...state.thresholdText };
  const inForce = activeRules(state.policies.at(-1)).map(measureKey);
  for (const draft of drafts) {
    if (draft.status !== "PROPOSED") continue;
    const key = measureKey(draft);
    if (inForce.includes(key) || proposedRules.some((rule) => rule.rule_id === draft.rule_id || measureKey(rule) === key)) continue;
    proposedRules.push(draft);
    // A system-proposed rule arrives with no number, so its field starts empty.
    thresholdText[draft.rule_id] = fractionToPercentInput(draft.threshold);
  }
  return { proposedRules, thresholdText };
}

function addObjectives(known: Objective[], more: Objective[]): Objective[] {
  const ids = new Set(known.map((objective) => objective.objective_id));
  return [...known, ...more.filter((objective) => !ids.has(objective.objective_id))];
}

function reducer(state: WorkflowState, action: Action): WorkflowState {
  switch (action.type) {
    case "persona/selected":
      return { ...INITIAL, personaId: action.personaId, portfolio: { status: "loading", data: null, error: null } };

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

    case "goal/changed":
      return { ...state, goalText: action.text };

    case "interpret/started":
      return { ...state, interpret: LOADING };

    case "interpret/succeeded":
      if (state.personaId !== action.personaId) return state;
      return {
        ...state,
        ...addDrafts(state, action.interpretation.proposed_rules),
        objectives: addObjectives(state.objectives, action.interpretation.objectives),
        interpret: IDLE,
        interpretation: action.interpretation,
        chosenOptions: {},
      };

    case "interpret/failed":
      return { ...state, interpret: failed(action.error) };

    case "option/chosen":
      return {
        ...state,
        ...(action.draft ? addDrafts(state, [action.draft]) : {}),
        chosenOptions: { ...state.chosenOptions, [action.clarificationId]: action.optionId },
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

    case "confirm/failed":
      return { ...state, confirm: failed(action.error) };

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

    case "challenge/preferenceRecorded":
      return {
        ...state,
        ...addDrafts(state, action.interpretation.proposed_rules),
        objectives: addObjectives(state.objectives, action.interpretation.objectives),
        challenge: IDLE,
        preferenceResponse: action.interpretation,
      };

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
  setGoalText: (text: string) => void;
  /** POST /rules/interpret with the user's sentence. The answer is a draft: nothing in it is active. */
  interpretGoal: () => Promise<void>;
  /** Records the definition chosen for a clarification question and lists the draft rule that option leads to. */
  chooseOption: (clarificationId: string, optionId: string) => void;
  setThresholdText: (ruleId: string, text: string) => void;
  /** POST /rules/confirm for the given proposed rules, in one new policy version. Rules without a valid threshold are skipped. */
  confirmRules: (ruleIds: string[]) => Promise<Policy | null>;
  setPurchase: (patch: Partial<WorkflowState["purchase"]>) => void;
  /** POST /investigations under the current policy. Resolves to the job id, or null on failure. */
  startInvestigation: (purchase: PurchaseRequest, parentInvestigationId?: string | null) => Promise<string | null>;
  /** Starts a fresh poll, with a fresh deadline, of the active job. */
  retryPolling: () => void;
  viewReport: (investigationId: string | null) => void;
  /** POST /investigations/{id}/challenge against the given report. */
  submitChallenge: (investigationId: string, request: ChallengeRequest) => Promise<ChallengeResponse | null>;
  clearChallengeError: () => void;
}

export interface WorkflowDerived {
  /** The policy version in force: the newest. */
  currentPolicy: Policy | null;
  /** The stored policy version a job or result was checked against, when this session holds it. */
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

  const portfolioRequest = useRef<AbortController | null>(null);
  const startKey = useActionKey();
  const challengeKey = useActionKey();

  useEffect(() => () => portfolioRequest.current?.abort(), []);

  const selectPersona = useCallback(
    (personaId: PersonaId) => {
      portfolioRequest.current?.abort();
      const controller = new AbortController();
      portfolioRequest.current = controller;
      startKey.done();
      challengeKey.done();
      dispatch({ type: "persona/selected", personaId });
      api.getPortfolio(personaId, { signal: controller.signal }).then(
        (data) => {
          if (controller.signal.aborted) return;
          dispatch({ type: "portfolio/loaded", personaId, data });
          announce("Portfolio loaded.");
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

  const setGoalText = useCallback((text: string) => dispatch({ type: "goal/changed", text }), []);

  const interpretGoal = useCallback(async () => {
    const current = latest.current;
    const personaId = current.personaId;
    if (!personaId || current.interpret.status === "loading") return;
    const policy = current.policies.at(-1) ?? null;
    dispatch({ type: "interpret/started" });
    try {
      const interpretation = await api.interpretRules({
        persona_id: personaId,
        text: current.goalText.trim(),
        policy_id: policy?.policy_id ?? null,
        policy_version: policy?.version ?? null,
      });
      dispatch({ type: "interpret/succeeded", personaId, interpretation });
      const rules = interpretation.proposed_rules.length;
      const questions = interpretation.clarifications.length;
      announce(
        `Interpretation ready: ${rules} drafted ${rules === 1 ? "rule" : "rules"}, inactive until confirmed` +
          (questions > 0 ? `, and ${questions} ${questions === 1 ? "question" : "questions"} for you.` : "."),
      );
    } catch (error) {
      if (isAbortError(error)) return;
      dispatch({ type: "interpret/failed", error });
    }
  }, [api, announce]);

  const chooseOption = useCallback(
    (clarificationId: string, optionId: string) => {
      // The question may come from stage 2 ("interpret my words") or from a "clarify a preference" challenge.
      const questions = [...(latest.current.interpretation?.clarifications ?? []), ...(latest.current.preferenceResponse?.clarifications ?? [])];
      const option = questions
        .find((clarification) => clarification.clarification_id === clarificationId)
        ?.options.find((candidate) => candidate.option_id === optionId);
      if (!option || !option.supported) return;
      dispatch({ type: "option/chosen", clarificationId, optionId, draft: option.proposed_rule });
      announce(option.proposed_rule ? "Definition chosen. Its rule is listed as proposed, without a number until you enter one." : "Definition chosen.");
    },
    [announce],
  );

  const setThresholdText = useCallback((ruleId: string, text: string) => dispatch({ type: "threshold/changed", ruleId, text }), []);

  const confirmRules = useCallback(
    async (ruleIds: string[]) => {
      const current = latest.current;
      const personaId = current.personaId;
      if (!personaId || current.confirm.status === "loading") return null;
      const confirmations = ruleIds.flatMap((ruleId) => {
        const rule = current.proposedRules.find((candidate) => candidate.rule_id === ruleId);
        const threshold = percentInputToFraction(current.thresholdText[ruleId] ?? "");
        // A rule is only ever confirmed with a number the user can see in its field.
        return rule && threshold !== null && validateThreshold(threshold) === null ? [{ rule, threshold }] : [];
      });
      if (confirmations.length === 0) return null;
      const base = current.policies.at(-1) ?? null;
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
        });
        dispatch({ type: "confirm/succeeded", policy, ruleIds: confirmations.map((confirmation) => confirmation.rule.rule_id) });
        const active = activeRules(policy).length;
        announce(`Confirmed. Policy version ${policy.version} is in force with ${active} confirmed ${active === 1 ? "rule" : "rules"}.`);
        return policy;
      } catch (error) {
        dispatch({ type: "confirm/failed", error });
        return null;
      }
    },
    [api, announce],
  );

  const setPurchase = useCallback((patch: Partial<WorkflowState["purchase"]>) => dispatch({ type: "purchase/changed", patch }), []);

  const startInvestigation = useCallback(
    async (purchase: PurchaseRequest, parentInvestigationId: string | null = null) => {
      const current = latest.current;
      const policy = current.policies.at(-1);
      if (!current.personaId || !policy || current.start.status === "loading") return null;
      const signature = [current.personaId, policy.policy_id, policy.version, purchase.instrument_id, purchase.target_direct_weight, parentInvestigationId].join("|");
      dispatch({ type: "start/started" });
      try {
        const accepted = await api.createInvestigation(
          {
            persona_id: current.personaId,
            policy_id: policy.policy_id,
            policy_version: policy.version,
            request: purchase,
            parent_investigation_id: parentInvestigationId,
          },
          { idempotencyKey: startKey.keyFor(signature) },
        );
        startKey.done();
        dispatch({ type: "start/succeeded", investigationId: accepted.id });
        announce("Investigation accepted. Waiting for its first step.");
        return accepted.id;
      } catch (error) {
        dispatch({ type: "start/failed", error });
        return null;
      }
    },
    [api, announce, startKey],
  );

  const retryPolling = useCallback(() => dispatch({ type: "poll/restarted" }), []);
  const viewReport = useCallback((investigationId: string | null) => dispatch({ type: "report/viewed", investigationId }), []);
  const clearChallengeError = useCallback(() => dispatch({ type: "challenge/cleared" }), []);

  const submitChallenge = useCallback(
    async (investigationId: string, request: ChallengeRequest) => {
      if (latest.current.challenge.status === "loading") return null;
      dispatch({ type: "challenge/started" });
      try {
        const response = await api.challengeInvestigation(investigationId, request, {
          idempotencyKey: challengeKey.keyFor(`${investigationId}|${canonical(request)}`),
        });
        challengeKey.done();
        if (response.proposed_correction) {
          dispatch({ type: "challenge/factRecorded", correction: response.proposed_correction });
          announce("Your correction is recorded as proposed and unverified. The original evidence is unchanged.");
        } else if (response.interpretation) {
          dispatch({ type: "challenge/preferenceRecorded", interpretation: response.interpretation });
          announce("Your preference is recorded as a new draft. No stored rule was changed.");
        } else if (response.policy && response.investigation) {
          dispatch({ type: "challenge/ruleChanged", policy: response.policy, olderId: investigationId, newerId: response.investigation.id });
          announce(`Policy version ${response.policy.version} created. Re-checking the same purchase under it.`);
        } else {
          throw new Error("The answer to the challenge carried nothing to show.");
        }
        return response;
      } catch (error) {
        dispatch({ type: "challenge/failed", error });
        return null;
      }
    },
    [api, announce, challengeKey],
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
    return {
      currentPolicy: state.policies.at(-1) ?? null,
      policyFor: (reference) => state.policies.find((policy) => policy.policy_id === reference.policy_id && policy.version === reference.policy_version) ?? null,
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
  }, [state.investigationIds, state.investigations, state.viewedInvestigationId, state.policies, state.corrections, polling.phase, polling.error]);

  const value = useMemo(() => ({ state, actions, derived }), [state, actions, derived]);
  return <WorkflowContext.Provider value={value}>{children}</WorkflowContext.Provider>;
}

export function useWorkflow(): WorkflowContextValue {
  const value = useContext(WorkflowContext);
  if (!value) throw new Error("useWorkflow must be used inside <WorkflowProvider>");
  return value;
}
