"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useReducer, useRef, type ReactNode } from "react";
import { useAnnounce } from "@/components/ui/Announcer";
import { usePolling, type PollingPhase } from "@/hooks/usePolling";
import { describeError, isAbortError } from "@/lib/api";
import type {
  ChallengeRequest,
  ChallengeResponse,
  ClarificationAnswer,
  ClarificationRequest,
  InterpretResponse,
  Investigation,
  Objective,
  PersonaId,
  Policy,
  PortfolioResponse,
  ProposedCorrection,
  PurchaseRequest,
  Rule,
  UnsupportedRequest,
} from "@/lib/contracts";
import { fractionToPercentInput, percentInputToFraction } from "@/lib/format";
import { getRuleThreshold, validateThreshold } from "@/lib/rules";
import { activeRules, isTerminalJobStatus } from "@/lib/verdict";
import { useRuntime } from "./runtime";

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

/** A user-triggered request: idle, in flight, or failed with a message that can be shown. */
export interface Operation {
  status: "idle" | "loading" | "error";
  error: string | null;
}

const IDLE: Operation = { status: "idle", error: null };
const LOADING: Operation = { status: "loading", error: null };
const failed = (error: string): Operation => ({ status: "error", error });

export interface WorkflowState {
  personaId: PersonaId | null;
  portfolio: { status: "idle" | "loading" | "ready" | "error"; data: PortfolioResponse | null; error: string | null };

  /** The goal sentence being typed in stage 2. */
  goalText: string;
  interpret: Operation;
  hasInterpretation: boolean;
  /** Qualitative objectives, kept apart from rules. */
  objectives: Objective[];
  /** PROPOSED rules: inactive until confirmed. */
  proposedRules: Rule[];
  /** Text of each proposed rule's threshold field, as a percentage. "" means not set. */
  thresholdText: Record<string, string>;
  clarifications: ClarificationRequest[];
  clarificationAnswers: ClarificationAnswer[];
  unsupported: UnsupportedRequest[];
  notes: string[];

  confirm: Operation & { ruleIds: string[] };
  /** Every confirmed policy version of this session, oldest first. Versions are immutable. */
  policies: Policy[];

  purchase: { instrumentId: string; targetText: string };
  start: Operation;

  investigations: Record<string, Investigation>;
  /** Jobs in the order they were started. */
  investigationIds: string[];
  /** The job being polled. */
  activeInvestigationId: string | null;
  pollEpoch: number;
  /** The report stage 5 shows. Null means the latest. */
  viewedInvestigationId: string | null;

  corrections: ProposedCorrection[];
  challenge: Operation;
  /** The answer to the last "clarify a preference" challenge. */
  preferenceResponse: InterpretResponse | null;
  /** Set by a rule change: the report before and the job after. */
  comparison: { olderId: string; newerId: string } | null;
}

const INITIAL: WorkflowState = {
  personaId: null,
  portfolio: { status: "idle", data: null, error: null },
  goalText: "",
  interpret: IDLE,
  hasInterpretation: false,
  objectives: [],
  proposedRules: [],
  thresholdText: {},
  clarifications: [],
  clarificationAnswers: [],
  unsupported: [],
  notes: [],
  confirm: { ...IDLE, ruleIds: [] },
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
  | { type: "interpret/succeeded"; personaId: PersonaId; response: InterpretResponse; answers: ClarificationAnswer[] }
  | { type: "interpret/failed"; error: string }
  | { type: "threshold/changed"; ruleId: string; text: string }
  | { type: "confirm/started"; ruleIds: string[] }
  | { type: "confirm/succeeded"; policy: Policy; ruleIds: string[] }
  | { type: "confirm/failed"; error: string }
  | { type: "purchase/changed"; patch: Partial<WorkflowState["purchase"]> }
  | { type: "start/started" }
  | { type: "start/succeeded"; investigationId: string }
  | { type: "start/failed"; error: string }
  | { type: "investigation/updated"; investigation: Investigation }
  | { type: "poll/restarted" }
  | { type: "report/viewed"; investigationId: string | null }
  | { type: "challenge/started" }
  | { type: "challenge/failed"; error: string }
  | { type: "challenge/cleared" }
  | { type: "challenge/factRecorded"; correction: ProposedCorrection }
  | { type: "challenge/preferenceRecorded"; response: InterpretResponse }
  | { type: "challenge/ruleChanged"; policy: Policy; olderId: string; newerId: string };

/** Adds what an interpretation returned without disturbing what the user already did. */
function mergeInterpretation(state: WorkflowState, response: InterpretResponse): Pick<WorkflowState, "objectives" | "proposedRules" | "thresholdText"> {
  const knownObjectives = new Set(state.objectives.map((o) => o.objective_id));
  const knownRules = new Set([
    ...state.proposedRules.map((r) => r.rule_id),
    ...state.policies.flatMap((p) => p.rules.map((r) => r.rule_id)),
  ]);
  const newRules = response.proposed_rules.filter((r) => !knownRules.has(r.rule_id));
  return {
    objectives: [...state.objectives, ...response.objectives.filter((o) => !knownObjectives.has(o.objective_id))],
    proposedRules: [...state.proposedRules, ...newRules],
    thresholdText: {
      ...state.thresholdText,
      // A system-proposed rule arrives with no number, so its field starts empty.
      ...Object.fromEntries(newRules.map((r) => [r.rule_id, fractionToPercentInput(getRuleThreshold(r))])),
    },
  };
}

function reducer(state: WorkflowState, action: Action): WorkflowState {
  switch (action.type) {
    case "persona/selected":
      return { ...INITIAL, personaId: action.personaId, portfolio: { status: "loading", data: null, error: null } };

    case "portfolio/loaded": {
      if (state.personaId !== action.personaId) return state;
      const scenarioPurchase = action.data.scenario_purchase;
      return {
        ...state,
        portfolio: { status: "ready", data: action.data, error: null },
        goalText: state.goalText === "" ? action.data.scenario_objective_text : state.goalText,
        purchase: scenarioPurchase
          ? { instrumentId: scenarioPurchase.instrument_id, targetText: fractionToPercentInput(scenarioPurchase.target_direct_weight) }
          : state.purchase,
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
        ...mergeInterpretation(state, action.response),
        interpret: IDLE,
        hasInterpretation: true,
        clarifications: action.response.clarifications,
        clarificationAnswers: action.answers,
        unsupported: action.response.unsupported,
        notes: action.response.notes,
      };

    case "interpret/failed":
      return { ...state, interpret: failed(action.error) };

    case "threshold/changed":
      return { ...state, thresholdText: { ...state.thresholdText, [action.ruleId]: action.text } };

    case "confirm/started":
      return { ...state, confirm: { ...LOADING, ruleIds: action.ruleIds } };

    case "confirm/succeeded": {
      const confirmed = new Set(action.ruleIds);
      return {
        ...state,
        confirm: { ...IDLE, ruleIds: [] },
        policies: [...state.policies, action.policy],
        proposedRules: state.proposedRules.filter((r) => !confirmed.has(r.rule_id)),
      };
    }

    case "confirm/failed":
      return { ...state, confirm: { ...failed(action.error), ruleIds: state.confirm.ruleIds } };

    case "purchase/changed":
      return { ...state, purchase: { ...state.purchase, ...action.patch }, start: IDLE };

    case "start/started":
      return { ...state, start: LOADING };

    case "start/succeeded":
      return {
        ...state,
        start: IDLE,
        investigationIds: state.investigationIds.includes(action.investigationId)
          ? state.investigationIds
          : [...state.investigationIds, action.investigationId],
        activeInvestigationId: action.investigationId,
        viewedInvestigationId: null,
        pollEpoch: state.pollEpoch + 1,
        comparison: null,
      };

    case "start/failed":
      return { ...state, start: failed(action.error) };

    case "investigation/updated": {
      const id = action.investigation.investigation_id;
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
      return { ...state, challenge: IDLE, corrections: [...state.corrections, action.correction] };

    case "challenge/preferenceRecorded":
      return {
        ...state,
        ...mergeInterpretation(state, action.response),
        challenge: IDLE,
        preferenceResponse: action.response,
        clarifications: [
          ...state.clarifications,
          ...action.response.clarifications.filter((c) => !state.clarifications.some((k) => k.clarification_id === c.clarification_id)),
        ],
      };

    case "challenge/ruleChanged":
      return {
        ...state,
        challenge: IDLE,
        policies: [...state.policies, action.policy],
        investigationIds: [...state.investigationIds, action.newerId],
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
  /** POST /rules/interpret with the goal text and any clarification answers. */
  interpretGoal: (answer?: ClarificationAnswer) => Promise<void>;
  setThresholdText: (ruleId: string, text: string) => void;
  /** POST /rules/confirm for the given proposed rules. Rules without a valid threshold are skipped. */
  confirmRules: (ruleIds: string[]) => Promise<Policy | null>;
  setPurchase: (patch: Partial<WorkflowState["purchase"]>) => void;
  /** POST /investigations under the current policy. Resolves to the job id, or null on failure. */
  startInvestigation: (purchase: PurchaseRequest) => Promise<string | null>;
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
  policyByVersion: (version: number) => Policy | null;
  /** The newest job, whatever its status. */
  latestInvestigation: Investigation | null;
  latestInvestigationId: string | null;
  /** The report stage 5 shows. */
  viewedInvestigation: Investigation | null;
  viewedInvestigationId: string | null;
  /** The newest job that produced a result. */
  latestReport: Investigation | null;
  /** How the poll of the active job is going. */
  polling: { phase: PollingPhase; error: string | null };
}

interface WorkflowContextValue {
  state: WorkflowState;
  actions: WorkflowActions;
  derived: WorkflowDerived;
}

const WorkflowContext = createContext<WorkflowContextValue | null>(null);

function newIdempotencyKey(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") return crypto.randomUUID();
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
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
  /** Reused when the same start request is retried after a failure, so the service can deduplicate. */
  const startKey = useRef<{ signature: string; key: string } | null>(null);

  useEffect(() => () => portfolioRequest.current?.abort(), []);

  const selectPersona = useCallback(
    (personaId: PersonaId) => {
      portfolioRequest.current?.abort();
      const controller = new AbortController();
      portfolioRequest.current = controller;
      startKey.current = null;
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
    [api, announce],
  );

  const retryPortfolio = useCallback(() => {
    const personaId = latest.current.personaId;
    if (personaId) selectPersona(personaId);
  }, [selectPersona]);

  const setGoalText = useCallback((text: string) => dispatch({ type: "goal/changed", text }), []);

  const interpretGoal = useCallback(
    async (answer?: ClarificationAnswer) => {
      const current = latest.current;
      const personaId = current.personaId;
      if (!personaId) return;
      const answers = answer
        ? [...current.clarificationAnswers.filter((a) => a.clarification_id !== answer.clarification_id), answer]
        : current.clarificationAnswers;
      dispatch({ type: "interpret/started" });
      try {
        const response = await api.interpretRules({ persona_id: personaId, text: current.goalText, clarification_answers: answers });
        dispatch({ type: "interpret/succeeded", personaId, response, answers });
        const rules = response.proposed_rules.length;
        const questions = response.clarifications.length;
        announce(
          `Interpretation ready: ${rules} proposed ${rules === 1 ? "rule" : "rules"}, inactive until confirmed` +
            (questions > 0 ? `, and ${questions} ${questions === 1 ? "question" : "questions"} for you.` : "."),
        );
      } catch (error) {
        if (isAbortError(error)) return;
        dispatch({ type: "interpret/failed", error: describeError(error) });
      }
    },
    [api, announce],
  );

  const setThresholdText = useCallback((ruleId: string, text: string) => dispatch({ type: "threshold/changed", ruleId, text }), []);

  const confirmRules = useCallback(
    async (ruleIds: string[]) => {
      const current = latest.current;
      const personaId = current.personaId;
      if (!personaId || current.confirm.status === "loading") return null;
      const confirmations = ruleIds.flatMap((ruleId) => {
        const rule = current.proposedRules.find((r) => r.rule_id === ruleId);
        const threshold = percentInputToFraction(current.thresholdText[ruleId] ?? "");
        // A rule is only ever confirmed with a number the user can see in its field.
        return rule && threshold !== null && validateThreshold(threshold) === null ? [{ rule, threshold }] : [];
      });
      if (confirmations.length === 0) return null;
      const confirmedIds = confirmations.map((c) => c.rule.rule_id);
      dispatch({ type: "confirm/started", ruleIds: confirmedIds });
      try {
        const { policy } = await api.confirmRules({
          persona_id: personaId,
          base_policy_version: current.policies.at(-1)?.policy_version ?? null,
          objectives: current.objectives,
          confirmations,
        });
        dispatch({ type: "confirm/succeeded", policy, ruleIds: confirmedIds });
        const active = activeRules(policy).length;
        announce(`Confirmed. Policy version ${policy.policy_version} is active with ${active} confirmed ${active === 1 ? "rule" : "rules"}.`);
        return policy;
      } catch (error) {
        dispatch({ type: "confirm/failed", error: describeError(error) });
        return null;
      }
    },
    [api, announce],
  );

  const setPurchase = useCallback((patch: Partial<WorkflowState["purchase"]>) => dispatch({ type: "purchase/changed", patch }), []);

  const startInvestigation = useCallback(
    async (purchase: PurchaseRequest) => {
      const current = latest.current;
      const policy = current.policies.at(-1);
      if (!current.personaId || !policy || current.start.status === "loading") return null;
      const signature = [current.personaId, policy.policy_version, purchase.instrument_id, purchase.target_direct_weight].join("|");
      if (startKey.current?.signature !== signature) startKey.current = { signature, key: newIdempotencyKey() };
      dispatch({ type: "start/started" });
      try {
        const created = await api.createInvestigation({
          persona_id: current.personaId,
          policy_version: policy.policy_version,
          purchase,
          idempotency_key: startKey.current.key,
        });
        startKey.current = null;
        dispatch({ type: "start/succeeded", investigationId: created.investigation_id });
        announce("Investigation accepted. Waiting for its first step.");
        return created.investigation_id;
      } catch (error) {
        dispatch({ type: "start/failed", error: describeError(error) });
        return null;
      }
    },
    [api, announce],
  );

  const retryPolling = useCallback(() => dispatch({ type: "poll/restarted" }), []);
  const viewReport = useCallback((investigationId: string | null) => dispatch({ type: "report/viewed", investigationId }), []);
  const clearChallengeError = useCallback(() => dispatch({ type: "challenge/cleared" }), []);

  const submitChallenge = useCallback(
    async (investigationId: string, request: ChallengeRequest) => {
      if (latest.current.challenge.status === "loading") return null;
      dispatch({ type: "challenge/started" });
      try {
        const response = await api.challengeInvestigation(investigationId, request);
        if (response.kind === "CORRECT_FACT") {
          dispatch({ type: "challenge/factRecorded", correction: response.correction });
          announce("Your correction is recorded as proposed and unverified. The original evidence is unchanged.");
        } else if (response.kind === "CLARIFY_PREFERENCE") {
          dispatch({ type: "challenge/preferenceRecorded", response: response.interpretation });
          announce("Your preference is recorded. No rule was changed.");
        } else {
          dispatch({ type: "challenge/ruleChanged", policy: response.policy, olderId: investigationId, newerId: response.investigation_id });
          announce(`Policy version ${response.policy.policy_version} created. Re-checking the same purchase under it.`);
        }
        return response;
      } catch (error) {
        dispatch({ type: "challenge/failed", error: describeError(error) });
        return null;
      }
    },
    [api, announce],
  );

  // --- Polling of the active job -------------------------------------------------
  const activeId = state.activeInvestigationId;
  const active = activeId ? state.investigations[activeId] : undefined;
  const activeIsTerminal = active ? isTerminalJobStatus(active.status) : false;
  const polling = usePolling<Investigation>({
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
    const reports = state.investigationIds.map((id) => state.investigations[id]).filter((i): i is Investigation => Boolean(i?.result));
    return {
      currentPolicy: state.policies.at(-1) ?? null,
      policyByVersion: (version) => state.policies.find((p) => p.policy_version === version) ?? null,
      latestInvestigationId,
      latestInvestigation: latestInvestigationId ? (state.investigations[latestInvestigationId] ?? null) : null,
      viewedInvestigationId,
      viewedInvestigation: viewedInvestigationId ? (state.investigations[viewedInvestigationId] ?? null) : null,
      latestReport: reports.at(-1) ?? null,
      polling: { phase: polling.phase, error: polling.error ? describeError(polling.error) : null },
    };
  }, [state.investigationIds, state.investigations, state.viewedInvestigationId, state.policies, polling.phase, polling.error]);

  const value = useMemo(() => ({ state, actions, derived }), [state, actions, derived]);
  return <WorkflowContext.Provider value={value}>{children}</WorkflowContext.Provider>;
}

export function useWorkflow(): WorkflowContextValue {
  const value = useContext(WorkflowContext);
  if (!value) throw new Error("useWorkflow must be used inside <WorkflowProvider>");
  return value;
}
