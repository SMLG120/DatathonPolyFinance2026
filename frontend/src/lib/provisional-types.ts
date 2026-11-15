/**
 * PROVISIONAL TYPES — PHASE 1 ONLY. DELETE IN PHASE 2.
 *
 * `contracts/typescript/contracts.ts` did not exist when the interface shell
 * was built, so these shapes were written from the names in
 * `docs/LEAD_DECISIONS.md` (D3–D7) and `docs/BUILD_BRIEF.md` (§2, §3, §6, §7).
 * They are a best guess, not an agreed contract.
 *
 * Nothing imports this file directly except `src/lib/contracts.ts`. Phase 2:
 *   1. run `npm run sync:contracts`,
 *   2. point `src/lib/contracts.ts` at the generated copy,
 *   3. delete this file and fix whatever `npm run typecheck` reports.
 *
 * Units: every weight, exposure, limit and return is a portfolio FRACTION
 * (10% = 0.10). Conversion to "10.0%" happens only in `src/lib/format.ts`.
 */

/** Portfolio fraction. 10% = 0.10. */
export type Fraction = number;
/** Calendar date, `YYYY-MM-DD`. */
export type IsoDate = string;
/** Timestamp, ISO 8601 in UTC. */
export type IsoDateTime = string;

// ---------------------------------------------------------------------------
// Persona and portfolio  (GET /portfolios/{persona})
// ---------------------------------------------------------------------------

export type PersonaId = "robert" | "mateo" | "amira";

export type AssetType = "EQUITY" | "EQUITY_FUND" | "BOND_FUND" | "COMMODITY" | "CRYPTO";

export interface Instrument {
  instrument_id: string;
  name: string;
  asset_type: AssetType;
  currency: "CAD" | "USD";
}

export interface Position extends Instrument {
  /** Direct weight of this position in the portfolio. */
  weight: Fraction;
}

export interface Portfolio {
  portfolio_id: string;
  persona_id: PersonaId;
  valuation_date: IsoDate;
  reporting_currency: "CAD";
  cash_weight: Fraction;
  positions: Position[];
  /** Always true: every portfolio in this product is invented. */
  is_fictional: true;
}

/** D5: a purchase is an instrument and the FINAL direct weight it should have. */
export interface PurchaseRequest {
  instrument_id: string;
  target_direct_weight: Fraction;
}

export interface PortfolioResponse {
  portfolio: Portfolio;
  /** The persona's goal sentence in the fictional scenario (D7). */
  scenario_objective_text: string;
  /** The purchase the fictional scenario demonstrates, if any (D7). */
  scenario_purchase: PurchaseRequest | null;
  /** Instruments a purchase request may name. */
  purchasable_instruments: Instrument[];
}

// ---------------------------------------------------------------------------
// Objectives, rules and policy  (POST /rules/interpret, POST /rules/confirm)
// ---------------------------------------------------------------------------

export type RuleType =
  | "max_issuer_exposure"
  | "min_issuer_exposure"
  | "exclusion"
  | "controversy_exclusion"
  | "scenario_loss_budget";

/** D3 lifecycle. Only CONFIRMED rules with a numeric threshold are evaluated. */
export type RuleLifecycleStatus = "PROPOSED" | "CONFIRMED" | "SUPERSEDED";

export type RuleOrigin = "USER_STATED" | "FICTIONAL_SCENARIO" | "SYSTEM_PROPOSED";

/** A qualitative objective. Never evaluated as PASS/FAIL. */
export interface Objective {
  objective_id: string;
  /** The user's own words, unchanged. */
  original_words: string;
  origin: Exclude<RuleOrigin, "SYSTEM_PROPOSED">;
}

interface RuleBase {
  rule_id: string;
  status: RuleLifecycleStatus;
  origin: RuleOrigin;
  /** The user's (or the fictional scenario's) wording this rule came from. */
  original_words: string;
  /** Precise scope, written by the service from a deterministic template. */
  scope_description: string;
  /** Context link only. It never produces a PASS/FAIL and never implies the threshold. */
  objective_id: string | null;
  /** The rule of an earlier policy version that this one replaced, if any. */
  supersedes_rule_id: string | null;
}

export interface MaxIssuerExposureRule extends RuleBase {
  rule_type: "max_issuer_exposure";
  /** `"any"` or one issuer id. */
  issuer_scope: string;
  max_fraction: Fraction | null;
}

export interface MinIssuerExposureRule extends RuleBase {
  rule_type: "min_issuer_exposure";
  issuer_scope: string;
  min_fraction: Fraction | null;
}

export type ExclusionDefinition =
  | { kind: "named_issuers"; issuer_ids: string[] }
  | { kind: "fund_reported_sector"; sector: string };

export interface ExclusionRule extends RuleBase {
  rule_type: "exclusion";
  definition: ExclusionDefinition;
  max_fraction: Fraction | null;
}

export interface ControversyExclusionRule extends RuleBase {
  rule_type: "controversy_exclusion";
  criteria_text: string;
  max_fraction: Fraction | null;
}

export interface ScenarioLossBudgetRule extends RuleBase {
  rule_type: "scenario_loss_budget";
  scenario_id: string;
  max_loss_fraction: Fraction | null;
}

export type Rule =
  | MaxIssuerExposureRule
  | MinIssuerExposureRule
  | ExclusionRule
  | ControversyExclusionRule
  | ScenarioLossBudgetRule;

export interface ClarificationOption {
  option_id: string;
  label: string;
  description: string;
  /** False when we hold no sourced definition for this reading (D3). */
  supported: boolean;
}

export interface ClarificationRequest {
  clarification_id: string;
  original_words: string;
  question: string;
  options: ClarificationOption[];
}

export interface UnsupportedRequest {
  original_words: string;
  reason: string;
}

export interface ClarificationAnswer {
  clarification_id: string;
  option_id: string;
}

export interface InterpretRequest {
  persona_id: PersonaId;
  text: string;
  clarification_answers: ClarificationAnswer[];
}

export interface InterpretResponse {
  objectives: Objective[];
  /** Always PROPOSED. SYSTEM_PROPOSED rules always carry a null threshold. */
  proposed_rules: Rule[];
  clarifications: ClarificationRequest[];
  unsupported: UnsupportedRequest[];
  notes: string[];
}

export interface RuleConfirmation {
  rule: Rule;
  /** The number the user entered or accepted. */
  threshold: Fraction;
}

export interface ConfirmRulesRequest {
  persona_id: PersonaId;
  /** Version this confirmation builds on; null for the first policy. */
  base_policy_version: number | null;
  objectives: Objective[];
  confirmations: RuleConfirmation[];
}

/** One immutable policy version. */
export interface Policy {
  policy_id: string;
  policy_version: number;
  previous_version: number | null;
  persona_id: PersonaId;
  created_at: IsoDateTime;
  objectives: Objective[];
  /** CONFIRMED rules of this version, plus the rules it SUPERSEDED. */
  rules: Rule[];
}

export interface ConfirmRulesResponse {
  policy: Policy;
}

// ---------------------------------------------------------------------------
// Results  (POST /check, GET /investigations/{id})
// ---------------------------------------------------------------------------

export type VerdictStatus = "PASS" | "FAIL" | "UNKNOWN";

/** D4: missing or partial holdings give a range, never a silent zero. */
export interface FractionInterval {
  lower: Fraction;
  upper: Fraction;
}

export interface RuleEvaluation {
  status: VerdictStatus;
  /** Null when nothing could be measured at all. */
  measured: FractionInterval | null;
  /** What was measured, e.g. the issuer with the largest exposure. */
  measured_label: string;
  limit: Fraction;
  /** Measured minus limit at the bound that decided the status. Null when UNKNOWN. */
  gap: Fraction | null;
  /** Deterministic template text from the engine. */
  reason: string;
  evidence_ids: string[];
}

export interface RuleResult {
  rule_id: string;
  rule_type: RuleType;
  /** The starting portfolio, before any purchase. */
  starting: RuleEvaluation;
  /** The portfolio after the proposed purchase; null when none was evaluated. */
  proposed: RuleEvaluation | null;
}

export interface FundPath {
  fund_id: string;
  fund_weight: Fraction;
  /** Null when the fund has no holdings file. */
  subject_weight_in_fund: Fraction | null;
  known_exposure: Fraction;
  /** `c` in D4: sum of reported weights, never rescaled. */
  coverage: Fraction;
  /** `w x (1 - c)`: the uncovered part that could be this subject. */
  possible_extra: Fraction;
  holdings_date: IsoDate | null;
}

export interface ExposureBreakdown {
  direct: Fraction;
  indirect_known: Fraction;
  possible_extra: Fraction;
  lower: Fraction;
  upper: Fraction;
  paths: FundPath[];
}

export interface ExposureResult {
  rule_id: string;
  subject_label: string;
  /** The confirmed (or draft) limit this exposure is compared with. */
  limit: Fraction | null;
  starting: ExposureBreakdown;
  proposed: ExposureBreakdown | null;
  evidence_ids: string[];
}

export interface ScenarioMeasurement {
  /** D6: terminal return over the scenario period; negative is a loss. Used for the budget. */
  scenario_terminal_return: Fraction | null;
  /** D6: context only. A different metric from the terminal return. */
  scenario_max_drawdown: Fraction | null;
}

export interface ScenarioResult {
  scenario_id: string;
  scenario_label: string;
  /** The confirmed scenario_loss_budget rule, or null when none is confirmed. */
  rule_id: string | null;
  period_start: IsoDate;
  period_end: IsoDate;
  starting: ScenarioMeasurement;
  proposed: ScenarioMeasurement | null;
  budget: Fraction | null;
  /** Status after the purchase (or of the starting portfolio when there is none). Null with no budget. */
  status: VerdictStatus | null;
  /** Measured loss minus budget. Null with no budget or no measurement. */
  gap: Fraction | null;
  assumptions: string[];
  evidence_ids: string[];
}

export type CoverageStatus = "COVERED" | "PARTIAL" | "MISSING";

export interface FundCoverage {
  fund_id: string;
  fund_name: string;
  portfolio_weight: Fraction;
  /** Null when look-through does not apply (for example a bond fund under an equity rule). */
  coverage: Fraction | null;
  status: CoverageStatus | "NOT_APPLICABLE";
  holdings_date: IsoDate | null;
  source_id: string | null;
  note: string;
}

export interface DataCoverage {
  status: CoverageStatus;
  funds: FundCoverage[];
  notes: string[];
}

/** D5: feasibility is reported apart from rule results. */
export interface Feasibility {
  status: "FEASIBLE" | "INSUFFICIENT_CASH";
  funding_path: "CASH";
  cash_before: Fraction;
  cash_after: Fraction;
  additional_purchase: Fraction;
}

export interface MaxCompliant {
  status: "SUPPORTED" | "WITHHELD" | "NO_FEASIBLE_PURCHASE";
  /** The boundary as a FINAL direct weight. */
  final_direct_weight: Fraction | null;
  /** The same boundary as an ADDITIONAL purchase from the starting weight. */
  additional_purchase: Fraction | null;
  binding_rule_ids: string[];
  /** True when the engine re-ran the same evaluator at the boundary. */
  verified_by_rerun: boolean;
  reason: string;
  evidence_ids: string[];
}

export interface PolicyConsistency {
  status: "CONSISTENT" | "PROVEN_CONFLICT";
  findings: { rule_ids: string[]; text: string }[];
}

/** Qualitative context about an objective. Never a verdict. */
export interface GoalContext {
  objective_id: string;
  text: string;
  evidence_ids: string[];
}

export interface ExplanationStatement {
  text: string;
  evidence_ids: string[];
}

/** §6 evidence record fields. */
export interface EvidenceRecord {
  evidence_id: string;
  metric_id: string;
  label: string;
  value: number | null;
  unit: "fraction" | "days" | "count";
  /** Instrument or portfolio the value belongs to. */
  subject: string;
  period_start: IsoDate | null;
  period_end: IsoDate | null;
  source_ids: string[];
  /** Share of the underlying data this value rests on, where that applies. */
  coverage: Fraction | null;
  assumptions: string[];
  /** Ordered description of how the value was calculated. */
  calculation_path: string[];
  calculation_version: string;
  policy_version: number | null;
}

/** §4 source record fields. */
export interface SourceRecord {
  source_id: string;
  publisher: string;
  title: string;
  url: string | null;
  relevant_date: IsoDate | null;
  retrieval_date: IsoDate | null;
  sha256: string | null;
  processing: string;
  terms: string;
  known_limitations: string[];
}

export interface CheckResult {
  persona_id: PersonaId;
  /** Null for a preview that uses draft thresholds. */
  policy_version: number | null;
  is_draft_preview: boolean;
  valuation_date: IsoDate;
  purchase: PurchaseRequest | null;
  feasibility: Feasibility | null;
  rule_results: RuleResult[];
  exposures: ExposureResult[];
  scenario: ScenarioResult | null;
  data_coverage: DataCoverage;
  policy_consistency: PolicyConsistency;
  goal_context: GoalContext[];
  max_compliant: MaxCompliant | null;
  explanation: ExplanationStatement[];
  evidence: EvidenceRecord[];
  sources: SourceRecord[];
  calculation_version: string;
}

/** POST /check: deterministic, bounded, no model. Used for labelled previews. */
export interface CheckRequest {
  persona_id: PersonaId;
  purchase: PurchaseRequest | null;
  /** Rules carrying the thresholds to evaluate; drafts are never stored. */
  rules: Rule[];
  is_draft_preview: boolean;
}

export interface CheckResponse {
  result: CheckResult;
}

// ---------------------------------------------------------------------------
// Investigations  (POST /investigations, GET /investigations/{id})
// ---------------------------------------------------------------------------

export type InvestigationStatus = "QUEUED" | "RUNNING" | "SUCCEEDED" | "FAILED";

export type StepStatus = "RUNNING" | "OK" | "ERROR";

/**
 * One tool call the job reported. The timeline shows these and nothing else:
 * a step is "in progress" only when the job itself says RUNNING.
 */
export interface InvestigationStep {
  seq: number;
  tool: string;
  /** Who asked for the call: the model, or the server's fixed sequence. */
  initiated_by: "MODEL" | "SERVER";
  status: StepStatus;
  started_at: IsoDateTime;
  /** Null while the step is RUNNING. */
  finished_at: IsoDateTime | null;
  input_summary: string;
  /** Null while the step is RUNNING. */
  result_summary: string | null;
}

/** How the investigation was driven. */
export interface InvestigationAgent {
  mode: "MODEL" | "DETERMINISTIC_FALLBACK";
  note: string | null;
}

export interface InvestigationError {
  code: string;
  message: string;
}

export interface Investigation {
  investigation_id: string;
  status: InvestigationStatus;
  persona_id: PersonaId;
  policy_version: number;
  purchase: PurchaseRequest;
  created_at: IsoDateTime;
  updated_at: IsoDateTime;
  /** Null until the job reports how it is being driven. */
  agent: InvestigationAgent | null;
  steps: InvestigationStep[];
  result: CheckResult | null;
  error: InvestigationError | null;
}

export interface CreateInvestigationRequest {
  persona_id: PersonaId;
  policy_version: number;
  purchase: PurchaseRequest;
  /** Lets a retried POST return the same job instead of a duplicate. */
  idempotency_key: string;
}

export interface CreateInvestigationResponse {
  investigation_id: string;
  status: InvestigationStatus;
}

// ---------------------------------------------------------------------------
// Challenge  (POST /investigations/{id}/challenge)
// ---------------------------------------------------------------------------

export type ChallengeRequest =
  | {
      kind: "CORRECT_FACT";
      evidence_id: string;
      proposed_value_text: string;
      reason_text: string;
    }
  | { kind: "CLARIFY_PREFERENCE"; text: string }
  | { kind: "CHANGE_RULE"; rule_id: string; new_threshold: Fraction };

/** A user's claim about a fact. Never verified, never used in a calculation. */
export interface ProposedCorrection {
  correction_id: string;
  evidence_id: string;
  proposed_value_text: string;
  reason_text: string;
  status: "UNVERIFIED";
  provenance: { asserted_by: "USER"; asserted_at: IsoDateTime };
  applied_to_calculation: false;
}

export type ChallengeResponse =
  | { kind: "CORRECT_FACT"; correction: ProposedCorrection }
  | { kind: "CLARIFY_PREFERENCE"; interpretation: InterpretResponse }
  | {
      kind: "CHANGE_RULE";
      /** The new immutable policy version. */
      policy: Policy;
      /** The job that re-evaluates the same purchase under the new version. */
      investigation_id: string;
      status: InvestigationStatus;
    };
