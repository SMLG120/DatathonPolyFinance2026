/**
 * Before You Buy: shared contracts, TypeScript mirror of contracts/schemas/*.schema.json.
 *
 * The JSON Schemas are normative; contracts/SEMANTICS.md says what the numbers mean;
 * contracts/api.md describes the routes. This file mirrors them and is checked against
 * them by contracts/python/tests/test_typescript_contracts.py (union members, property
 * names, optional and nullable members). Copy or import it; never edit a copy.
 *
 * Conventions
 * - Every property is required. An absent value is an explicit `null`.
 *   The only optional property is `FundHoldings.non_constituent_note`.
 * - Every weight, exposure, limit, return and gap is a FRACTION (10% = 0.10), never a percentage.
 * - Dates are `YYYY-MM-DD`; timestamps are UTC `YYYY-MM-DDTHH:MM:SS[.ffffff]Z`.
 * - Verdicts (`RuleResult.status`, `Summary`) come from the deterministic engine. Nothing
 *   in these types is a recommendation, and there is no overall "compliant" flag.
 */

// ---------------------------------------------------------------------------------------------
// Constants (mirror contracts/python/byb_contracts/constants.py)
// ---------------------------------------------------------------------------------------------

export const SCHEMA_VERSION = "1.0.0";
/** Absolute tolerance of every comparison with a limit. Equality with a limit passes. */
export const EPS = 1e-9;
/** `MaxIssuerExposureParameters.issuer_scope` value meaning "every issuer". */
export const ISSUER_SCOPE_ANY = "any";
/** Polling interval for GET /investigations/{id}. */
export const POLL_INTERVAL_MS = 1500;
/** The client stops polling this long after the 202 and shows a visible failure state. */
export const POLL_DEADLINE_MS = 180000;
export const IDEMPOTENCY_KEY_HEADER = "Idempotency-Key";
export const IDEMPOTENCY_KEY_PATTERN = /^[A-Za-z0-9_-]{8,64}$/;

// ---------------------------------------------------------------------------------------------
// Scalars (common.schema.json)
// ---------------------------------------------------------------------------------------------

export type SchemaVersion = "1.0.0";
/** A number in [0, 1]: a share of the portfolio or of a fund. 10% = 0.10. */
export type Fraction = number;
/** A fraction that may be negative (a return, a change). Never below -1. */
export type SignedFraction = number;
/** `YYYY-MM-DD`. */
export type IsoDate = string;
/** UTC `YYYY-MM-DDTHH:MM:SS[.ffffff]Z`. */
export type IsoDateTime = string;
export type Id = string;
/** Ticker-like id, e.g. `NVDA`, `XIU.TO`. */
export type InstrumentId = string;
/** Company id; the share classes of one company share it, e.g. `ALPHABET`. */
export type IssuerId = string;
/** `robert`, `mateo` or `amira`. */
export type PersonaId = string;
export type SourceId = string;
/** `"any"` (every issuer) or one issuer id. */
export type IssuerScope = string;

export interface Bounds {
  lower: number;
  upper: number;
}

// ---------------------------------------------------------------------------------------------
// String-literal unions (common.schema.json enums, same order)
// ---------------------------------------------------------------------------------------------

export type Currency = "CAD" | "USD";
export type AssetClass = "equity" | "etf_equity" | "etf_bond" | "etf_commodity" | "crypto";
export type Funding = "CASH";
export type ObjectiveKind = "goal" | "preference" | "constraint";
export type ObjectiveSource = "USER_STATED" | "FICTIONAL_SCENARIO";
export type RuleType =
  | "max_issuer_exposure"
  | "min_issuer_exposure"
  | "exclusion"
  | "controversy_exclusion"
  | "scenario_loss_budget";
/** Only CONFIRMED rules are evaluated (in a preview: PROPOSED or CONFIRMED drafts that carry a number). */
export type RuleStatus = "PROPOSED" | "CONFIRMED" | "SUPERSEDED";
/** SYSTEM_PROPOSED rules never carry a number. */
export type RuleOrigin = "USER_STATED" | "FICTIONAL_SCENARIO" | "SYSTEM_PROPOSED";
export type ThresholdKind = "max_fraction" | "min_fraction" | "max_loss_fraction";
export type ThresholdSource = "USER_WORDS" | "USER_ENTERED" | "FICTIONAL_SCENARIO";
export type ExclusionDefinitionKind = "named_issuers" | "fund_reported_sector";
export type ScenarioId = "replay_2022";
export type ControversyNature =
  | "ALLEGATION"
  | "REGULATORY_FINDING"
  | "COURT_RULING"
  | "SETTLEMENT"
  | "COMPANY_DISCLOSURE";
/** UNKNOWN is a result in its own right: show it, never as PASS and never as FAIL. */
export type VerdictStatus = "PASS" | "FAIL" | "UNKNOWN";
export type ExecutionStatus = "OK" | "INVALID_REQUEST" | "ERROR";
export type ExecutionCode =
  | "TARGET_BELOW_CURRENT_WEIGHT"
  | "TARGET_NEGATIVE"
  | "TARGET_ABOVE_ONE"
  | "UNSUPPORTED_INSTRUMENT"
  | "INVALID_PORTFOLIO"
  | "INVALID_POLICY"
  | "ENGINE_ERROR";
/** Not a rule result: show it next to the headline. */
export type FeasibilityStatus = "FEASIBLE" | "INSUFFICIENT_CASH";
/** CONSISTENT means only "no supported calculation proved a conflict". */
export type ConsistencyStatus = "CONSISTENT" | "PROVEN_CONFLICT" | "NOT_ASSESSED";
export type ConflictType = "MIN_EXCEEDS_MAX_SAME_ISSUER";
/** COVERED only when the fund's file reports its whole weight; real funds are usually PARTIAL. */
export type CoverageStatus = "COVERED" | "PARTIAL" | "MISSING";
export type UnknownCause =
  | "PARTIAL_HOLDINGS"
  | "MISSING_HOLDINGS"
  | "UNCLASSIFIED_SECTOR"
  | "REGISTRY_ABSENCE"
  | "INSUFFICIENT_HISTORY";
export type ScenarioStatus = "COMPUTED" | "INSUFFICIENT_HISTORY";
/** Show a maximum only when SUPPORTED. */
export type MaxCompliantStatus = "SUPPORTED" | "WITHHELD" | "NO_FEASIBLE_PURCHASE";
export type BindingConstraintType = "RULE" | "CASH";
export type Headline =
  | "ALL_PASS"
  | "HAS_FAIL"
  | "NO_FAIL_BUT_UNKNOWN"
  | "INVALID_REQUEST"
  | "POLICY_CONFLICT"
  | "NO_RULES_EVALUATED"
  | "EXECUTION_ERROR";
export type GoalContextType = "LINKED_RULE_RESULTS" | "CONCENTRATION" | "SCENARIO_DRAWDOWN" | "NOT_QUANTIFIED";
export type EvidenceLabel = "FACT" | "ASSUMPTION" | "FICTIONAL_SCENARIO" | "CALCULATION";
export type EvidenceUnit = "fraction" | "price" | "fx_rate" | "days" | "count" | "date" | "text";
export type MetricId =
  | "position_weight"
  | "cash_weight"
  | "cash_after_purchase"
  | "fund_constituent_weight"
  | "fund_coverage_fraction"
  | "unattributed_fund_weight"
  | "issuer_direct_exposure"
  | "issuer_exposure_via_fund"
  | "exposure_lower"
  | "exposure_upper"
  | "rule_threshold"
  | "gap_to_limit"
  | "scenario_instrument_return"
  | "scenario_terminal_return"
  | "scenario_max_drawdown"
  | "scenario_loss"
  | "price_adj_close"
  | "fx_usdcad"
  | "fx_rate_age_days"
  | "price_age_days"
  | "max_compliant_final_weight"
  | "max_compliant_additional_purchase"
  | "sector_label"
  | "controversy_record"
  | "holdings_date";
export type SubjectKind = "INSTRUMENT" | "ISSUER" | "FUND" | "PORTFOLIO" | "RULE" | "FX";
export type PortfolioState = "STARTING" | "PROPOSED" | "NOT_APPLICABLE";
export type JobStatus = "QUEUED" | "RUNNING" | "SUCCEEDED" | "FAILED";
export type ToolName =
  | "get_portfolio"
  | "get_policy"
  | "get_holdings"
  | "lookup_controversy_evidence"
  | "simulate_change"
  | "compute_exposure"
  | "replay_period"
  | "check_rules"
  | "max_compliant_amount";
export type StepStatus = "RUNNING" | "OK" | "ERROR";
/** MODEL: the investigator chose the call. SERVER: run by the service whatever the model did. */
export type StepInitiator = "MODEL" | "SERVER";
export type AgentMode = "MODEL" | "DETERMINISTIC_FALLBACK";
export type RenderedBy = "TEMPLATE" | "MODEL_VALIDATED";
export type FailureCode =
  | "DEADLINE_EXCEEDED"
  | "WORKER_INVOCATION_FAILED"
  | "WORKER_ERROR"
  | "ENGINE_ERROR"
  | "DATA_UNAVAILABLE";
export type ChallengeType = "CORRECT_FACT" | "CLARIFY_PREFERENCE" | "CHANGE_RULE";
export type CorrectionStatus = "UNVERIFIED";
export type UnsupportedCode = "UNSUPPORTED_DEFINITION" | "UNSUPPORTED_RULE_TYPE" | "OUT_OF_SCOPE" | "INSTRUCTION_IGNORED";
export type UiStage =
  | "PERSONA_PORTFOLIO"
  | "GOALS_RULES"
  | "PROPOSED_PURCHASE"
  | "INVESTIGATION"
  | "VERDICT_EVIDENCE"
  | "CHALLENGE";
export type ErrorCode =
  | "UNAUTHORIZED"
  | "VALIDATION_ERROR"
  | "NOT_FOUND"
  | "POLICY_VERSION_CONFLICT"
  | "IDEMPOTENCY_KEY_REUSED"
  | "INVESTIGATION_NOT_FINISHED"
  | "INVESTIGATION_EXPIRED"
  | "INVALID_PURCHASE_REQUEST"
  | "INVALID_CONFIRMATION"
  | "UNSUPPORTED_CHALLENGE"
  | "INTERPRETER_TIMEOUT"
  | "INTERPRETER_FAILED"
  | "WORKER_INVOCATION_FAILED"
  | "RATE_LIMITED"
  | "INTERNAL_ERROR";
/** scenario.schema.json: what a correct interpreter does with a demo phrase. */
export type DemoPhraseOutcome = "CLARIFICATION" | "PROPOSED_RULES" | "UNSUPPORTED";

export const TERMINAL_JOB_STATUSES: readonly JobStatus[] = ["SUCCEEDED", "FAILED"];

// ---------------------------------------------------------------------------------------------
// portfolio.schema.json, objective.schema.json, purchase_request.schema.json
// ---------------------------------------------------------------------------------------------

export interface Position {
  instrument_id: InstrumentId;
  /** Direct weight, greater than 0. */
  weight: Fraction;
}

/** A fictional portfolio. cash_weight + sum(position weights) = 1. */
export interface Portfolio {
  schema_version: SchemaVersion;
  portfolio_id: Id;
  persona_id: PersonaId;
  fictional: true;
  valuation_date: IsoDate;
  base_currency: "CAD";
  cash_weight: Fraction;
  positions: Position[];
}

/** A qualitative objective in the investor's own words. Never PASS or FAIL. */
export interface Objective {
  objective_id: Id;
  original_words: string;
  kind: ObjectiveKind;
  source: ObjectiveSource;
  case_reference: string | null;
}

/** A simulated purchase funded from cash. `target_direct_weight` is the FINAL direct weight, not the amount added. */
export interface PurchaseRequest {
  instrument_id: InstrumentId;
  target_direct_weight: number;
  funding: Funding;
  original_words: string | null;
}

/** Free text, accepted only by POST /investigations. It never reaches the engine in this form. */
export interface UnresolvedPurchaseRequest {
  instrument_id: null;
  target_direct_weight: null;
  funding: Funding;
  original_words: string;
}

// ---------------------------------------------------------------------------------------------
// rule.schema.json, policy.schema.json
// ---------------------------------------------------------------------------------------------

export interface MaxIssuerExposureParameters {
  issuer_scope: IssuerScope;
}

export interface MinIssuerExposureParameters {
  issuer_id: IssuerId;
}

export interface NamedIssuersDefinition {
  kind: "named_issuers";
  issuer_ids: IssuerId[];
}

/** Exact, case-sensitive sector label as reported in the fund issuer's holdings file. */
export interface FundReportedSectorDefinition {
  kind: "fund_reported_sector";
  sector: string;
}

export type ExclusionDefinition = NamedIssuersDefinition | FundReportedSectorDefinition;

export interface ExclusionParameters {
  definition: ExclusionDefinition;
}

export interface ControversyCriteria {
  natures: ControversyNature[];
  event_date_from: IsoDate | null;
}

export interface ControversyExclusionParameters {
  criteria: ControversyCriteria;
}

export interface ScenarioLossBudgetParameters {
  scenario_id: ScenarioId;
}

/**
 * Members shared by every rule. The number lives only in `threshold`.
 *
 * Invariants enforced by the schema:
 * - origin SYSTEM_PROPOSED: threshold null, threshold_source null, status PROPOSED.
 * - origin FICTIONAL_SCENARIO: a number, threshold_source FICTIONAL_SCENARIO.
 * - origin USER_STATED: a number, threshold_source USER_WORDS or USER_ENTERED.
 * - threshold_quote is a string only when threshold_source is USER_WORDS.
 * - status PROPOSED: confirmed_at, confirmed_by and superseded_by_rule_id are null.
 * - status CONFIRMED or SUPERSEDED: a number, confirmed_at and confirmed_by are set.
 * - A changed rule gets a new rule_id; the old one stays in the new version as SUPERSEDED.
 */
export interface RuleBase {
  rule_id: Id;
  threshold: Fraction | null;
  threshold_source: ThresholdSource | null;
  threshold_quote: string | null;
  unit: "fraction";
  status: RuleStatus;
  origin: RuleOrigin;
  original_words: string;
  /** Context link only. It never produces a PASS or FAIL. */
  objective_id: Id | null;
  /** Plain-language statement of what is measured and what is out of scope. Show it on the rule card. */
  scope_description: string;
  confirmed_at: IsoDateTime | null;
  confirmed_by: string | null;
  supersedes_rule_id: Id | null;
  superseded_by_rule_id: Id | null;
}

export interface MaxIssuerExposureRule extends RuleBase {
  rule_type: "max_issuer_exposure";
  parameters: MaxIssuerExposureParameters;
  threshold_kind: "max_fraction";
}

export interface MinIssuerExposureRule extends RuleBase {
  rule_type: "min_issuer_exposure";
  parameters: MinIssuerExposureParameters;
  threshold_kind: "min_fraction";
}

export interface ExclusionRule extends RuleBase {
  rule_type: "exclusion";
  parameters: ExclusionParameters;
  threshold_kind: "max_fraction";
}

export interface ControversyExclusionRule extends RuleBase {
  rule_type: "controversy_exclusion";
  parameters: ControversyExclusionParameters;
  threshold_kind: "max_fraction";
}

export interface ScenarioLossBudgetRule extends RuleBase {
  rule_type: "scenario_loss_budget";
  parameters: ScenarioLossBudgetParameters;
  threshold_kind: "max_loss_fraction";
}

/** Discriminated by `rule_type`. */
export type Rule =
  | MaxIssuerExposureRule
  | MinIssuerExposureRule
  | ExclusionRule
  | ControversyExclusionRule
  | ScenarioLossBudgetRule;

/** One immutable version of a policy. `rules` includes SUPERSEDED rules for history. */
export interface Policy {
  schema_version: SchemaVersion;
  policy_id: Id;
  persona_id: PersonaId;
  version: number;
  parent_version: number | null;
  created_at: IsoDateTime;
  objectives: Objective[];
  rules: Rule[];
  change_note: string;
  /** `sha256:` + 64 hex digits. */
  content_hash: string;
}

// ---------------------------------------------------------------------------------------------
// Data files: instrument, holdings_snapshot, market_data, controversy_record, source
// ---------------------------------------------------------------------------------------------

export interface Instrument {
  instrument_id: InstrumentId;
  issuer_id: IssuerId;
  name: string;
  asset_class: AssetClass;
  currency: Currency;
  is_fund: boolean;
  /** True for equities and equity funds only. Other positions are out of scope of exposure rules. */
  equity_scope: boolean;
  sector: string | null;
  sector_source: SourceId | null;
}

export interface InstrumentRegistry {
  schema_version: SchemaVersion;
  instruments: Record<InstrumentId, Instrument>;
}

export interface Holding {
  fund_id: InstrumentId;
  issuer_id: IssuerId;
  instrument_id: InstrumentId;
  name: string;
  weight_fraction: Fraction;
  /** Null means "not classified": unknown, never zero. */
  sector: string | null;
  sector_source: SourceId | null;
}

export interface FundHoldings {
  fund_id: InstrumentId;
  holdings_date: IsoDate;
  publication_date: IsoDate | null;
  retrieval_date: IsoDate;
  source_id: SourceId;
  /** Plain sum of the constituent weights. Never rescaled. */
  coverage_fraction: number;
  non_constituent_weight: number;
  non_constituent_note?: string;
  n_holdings: number;
  holdings: Holding[];
}

export interface HoldingsSnapshot {
  schema_version: SchemaVersion;
  funds: Record<InstrumentId, FundHoldings>;
}

/** `[date, value]`. */
export type DatedValue = [IsoDate, number];

export interface PriceSeries {
  currency: Currency;
  series: DatedValue[];
}

export interface MarketData {
  schema_version: SchemaVersion;
  valuation_date: IsoDate;
  prices: Record<InstrumentId, PriceSeries>;
  /** CAD per 1 USD. */
  fx_usdcad: DatedValue[];
}

/** A dated, sourced record. An issuer without a record is "not assessed", never "clean". */
export interface ControversyRecord {
  record_id: Id;
  issuer_id: IssuerId;
  event_date: IsoDate;
  nature: ControversyNature;
  summary: string;
  source_ids: SourceId[];
  coverage_note: string;
}

export interface ControversyRegistryScope {
  purpose: string;
  issuers_researched: IssuerId[];
  research_date: IsoDate;
  absence_meaning: string;
  source_policy: string;
  not_evidence: string;
  limits: string;
}

export interface ControversyRegistry {
  schema_version: SchemaVersion;
  registry_scope: ControversyRegistryScope;
  records: ControversyRecord[];
}

export interface Source {
  source_id: SourceId;
  publisher: string;
  title: string;
  url: string | null;
  relevant_date: IsoDate;
  retrieval_date: IsoDate;
  sha256: string;
  processing: string;
  terms: string;
  limitations: string;
}

export interface SourceRegistry {
  schema_version: SchemaVersion;
  sources: Record<SourceId, Source>;
}

// ---------------------------------------------------------------------------------------------
// evidence_record.schema.json
// ---------------------------------------------------------------------------------------------

export interface EvidenceSubject {
  kind: SubjectKind;
  /** instrument_id, issuer_id, fund_id, rule_id, `USDCAD` for FX, or the portfolio_id. */
  id: string;
  via_fund_id: InstrumentId | null;
  portfolio_state: PortfolioState;
}

export interface AsOfPeriod {
  type: "AS_OF";
  date: IsoDate;
}

export interface RangePeriod {
  type: "RANGE";
  start_date: IsoDate;
  end_date: IsoDate;
}

export type EvidencePeriod = AsOfPeriod | RangePeriod;

/**
 * One inspectable number or fact behind a result.
 * `value` is a string for units `date` and `text`, a number otherwise; null when it could not be
 * computed or the source reports none (a `sector_label` the holdings file does not give).
 * `currency` is set only for unit `price`.
 */
export interface EvidenceRecord {
  evidence_id: Id;
  label: EvidenceLabel;
  metric_id: MetricId;
  value: number | string | null;
  unit: EvidenceUnit;
  currency: Currency | null;
  subject: EvidenceSubject;
  period: EvidencePeriod;
  source_ids: SourceId[];
  assumptions: string[];
  /** The calculation path: evidence ids this value was computed from. */
  derived_from: Id[];
  formula: string | null;
  calculation_version: string;
  /** Null in a preview. */
  policy_version: number | null;
}

// ---------------------------------------------------------------------------------------------
// check_result.schema.json
// ---------------------------------------------------------------------------------------------

export interface Execution {
  status: ExecutionStatus;
  /** Null when status is OK. */
  code: ExecutionCode | null;
  message: string | null;
}

export interface Feasibility {
  funding: Funding;
  starting_direct_weight: Fraction;
  target_direct_weight: Fraction;
  /** target_direct_weight - starting_direct_weight. */
  additional_purchase: Fraction;
  cash_before: Fraction;
  /** Negative when cash is insufficient. */
  cash_after: number;
  status: FeasibilityStatus;
}

export interface PolicyConflict {
  conflict_type: ConflictType;
  /** `[minimum rule id, maximum rule id]`. */
  rule_ids: Id[];
  issuer_id: IssuerId;
  min_fraction: Fraction;
  max_fraction: Fraction;
  calculation: string;
}

export interface PolicyConsistency {
  status: ConsistencyStatus;
  conflicts: PolicyConflict[];
}

export interface BreachingSubject {
  subject_kind: "ISSUER";
  subject_id: IssuerId;
  lower: Fraction;
  upper: Fraction;
}

export interface RuleEvaluationSnapshot {
  status: VerdictStatus;
  measured: Bounds | null;
}

export interface OutOfScopePosition {
  instrument_id: InstrumentId;
  weight: Fraction;
  reason: string;
}

/** One evaluated rule. `status`, `measured` and `gap` describe the PROPOSED portfolio; `starting` the portfolio before the purchase. */
export interface RuleResult {
  rule_id: Id;
  rule_type: RuleType;
  status: VerdictStatus;
  /** `[lower, upper]` of the measured quantity; null only when it cannot be computed. */
  measured: Bounds | null;
  limit: Fraction;
  /** Positive = size of the breach, zero or negative = headroom, null when UNKNOWN. */
  gap: number | null;
  /** Issuers whose proven exposure causes the breach. Empty unless FAIL. */
  breaching_subjects: BreachingSubject[];
  out_of_scope: OutOfScopePosition[];
  /** May be non-empty with PASS or FAIL. */
  unknown_causes: UnknownCause[];
  starting: RuleEvaluationSnapshot;
  evidence_ids: Id[];
  /** Template-rendered sentence. Never model-written. */
  reason: string;
}

export interface RuleNotEvaluated {
  rule_id: Id;
  status: RuleStatus;
  reason: string;
}

export interface PurchaseEffect {
  lower_change: number;
  upper_change: number;
}

/** A rule already FAIL on the STARTING portfolio. Keeps an existing breach apart from what the purchase adds. */
export interface StartingFinding {
  rule_id: Id;
  status: "FAIL";
  measured: Bounds;
  limit: Fraction;
  gap: number;
  breaching_subjects: BreachingSubject[];
  /** PROPOSED minus STARTING bounds. */
  purchase_effect: PurchaseEffect;
  evidence_ids: Id[];
  reason: string;
}

export interface FundCoverage {
  fund_id: InstrumentId;
  portfolio_weight: Fraction;
  coverage_fraction: number;
  sector_labelled_fraction: number;
  uncovered_portfolio_weight: Fraction;
  holdings_date: IsoDate | null;
  source_id: SourceId | null;
  status: CoverageStatus;
}

export interface ScenarioMeasures {
  /** Value at end date / value at base date - 1. The measure used by scenario_loss_budget. */
  scenario_terminal_return: SignedFraction;
  /** Context only, never a rule. Between -1 and 0. */
  scenario_max_drawdown: number;
  max_drawdown_date: IsoDate | null;
}

export interface InstrumentReturn {
  instrument_id: InstrumentId;
  currency: Currency;
  base_price_date: IsoDate;
  end_price_date: IsoDate;
  base_price_age_days: number;
  end_price_age_days: number;
  base_fx_date: IsoDate | null;
  end_fx_date: IsoDate | null;
  base_fx_age_days: number | null;
  end_fx_age_days: number | null;
  return_cad: SignedFraction;
}

/** A replay of an assumed allocation through a past period. Not a forecast. */
export interface ScenarioResult {
  scenario_id: ScenarioId;
  label: string;
  base_date: IsoDate;
  end_date: IsoDate;
  status: ScenarioStatus;
  /** Null when status is INSUFFICIENT_HISTORY. */
  starting: ScenarioMeasures | null;
  proposed: ScenarioMeasures | null;
  target_instrument_return: SignedFraction | null;
  instrument_returns: InstrumentReturn[];
  missing_instruments: InstrumentId[];
  assumptions: string[];
  evidence_ids: Id[];
}

/** Qualitative context for an objective. It has no status by design. */
export interface GoalContext {
  objective_id: Id;
  context_type: GoalContextType;
  text: string;
  evidence_ids: Id[];
}

export interface BindingConstraint {
  type: BindingConstraintType;
  rule_id: Id | null;
}

export interface MaxCompliantSupported {
  status: "SUPPORTED";
  /** Largest FINAL direct weight at which every evaluated rule passes and cash suffices. */
  final_direct_weight: Fraction;
  /** The amount ADDED: final_direct_weight - starting direct weight. */
  additional_purchase: Fraction;
  binding_constraint: BindingConstraint;
  verified_by_rerun: true;
  reason: string;
  evidence_ids: Id[];
}

export interface MaxCompliantWithheld {
  status: "WITHHELD";
  final_direct_weight: null;
  additional_purchase: null;
  binding_constraint: null;
  verified_by_rerun: false;
  reason: string;
  evidence_ids: Id[];
}

export interface MaxCompliantNoFeasiblePurchase {
  status: "NO_FEASIBLE_PURCHASE";
  final_direct_weight: null;
  additional_purchase: null;
  binding_constraint: BindingConstraint;
  verified_by_rerun: false;
  reason: string;
  evidence_ids: Id[];
}

/** Discriminated by `status`. A number exists only when SUPPORTED. */
export type MaxCompliant = MaxCompliantSupported | MaxCompliantWithheld | MaxCompliantNoFeasiblePurchase;

export interface IndirectExposure {
  fund_id: InstrumentId;
  known: Fraction;
}

export interface ExposureBreakdown {
  direct: Fraction;
  indirect_by_fund: IndirectExposure[];
  /** direct + sum(known). */
  lower: Fraction;
  /** lower + possible_extra of that portfolio state. */
  upper: Fraction;
}

export interface PossibleExtra {
  starting: Fraction;
  proposed: Fraction;
}

export interface IssuerExposure {
  issuer_id: IssuerId;
  name: string;
  starting: ExposureBreakdown;
  proposed: ExposureBreakdown;
}

/** Chart rows: at most 10 issuers, largest proposed lower bound first. */
export interface Exposure {
  /** Fund weight not attributed to any issuer; it could belong to any of them. */
  possible_extra: PossibleExtra;
  issuers: IssuerExposure[];
  selection_note: string;
}

export interface SummaryCounts {
  pass: number;
  fail: number;
  unknown: number;
}

/** Derived, never authored. The headline covers rule results only. */
export interface Summary {
  headline: Headline;
  counts: SummaryCounts;
  rules_evaluated: number;
  rules_not_evaluated: number;
  starting_portfolio_breaches: number;
  feasibility_status: FeasibilityStatus | null;
}

/**
 * Output of the deterministic engine: body of POST /check and `result` of an investigation.
 * When `execution.status` is not OK: feasibility, scenario, max_compliant and exposure are
 * null and every list is empty.
 */
export interface CheckResult {
  schema_version: SchemaVersion;
  persona_id: PersonaId;
  portfolio_id: Id;
  /** Null in a preview. */
  policy_id: Id | null;
  policy_version: number | null;
  /** True when draft rules were evaluated instead of a stored policy version. */
  preview: boolean;
  calculation_version: string;
  valuation_date: IsoDate;
  purchase_request: PurchaseRequest;
  execution: Execution;
  feasibility: Feasibility | null;
  policy_consistency: PolicyConsistency;
  /** Policy order. */
  rule_results: RuleResult[];
  rules_not_evaluated: RuleNotEvaluated[];
  starting_portfolio_findings: StartingFinding[];
  data_coverage: FundCoverage[];
  scenario: ScenarioResult | null;
  goal_context: GoalContext[];
  max_compliant: MaxCompliant | null;
  exposure: Exposure | null;
  evidence: EvidenceRecord[];
  summary: Summary;
  disclosures: string[];
}

// ---------------------------------------------------------------------------------------------
// interpretation.schema.json
// ---------------------------------------------------------------------------------------------

export interface UnsupportedRequest {
  words: string;
  code: UnsupportedCode;
  reason: string;
}

/** A supported option carries the draft it leads to, so choosing it needs no second model call. */
export interface ClarificationOption {
  option_id: Id;
  label: string;
  description: string;
  /** False: show the option disabled, with the reason in `description`. */
  supported: boolean;
  proposed_rule: Rule | null;
  purchase_request: PurchaseRequest | null;
}

export interface Clarification {
  clarification_id: Id;
  about_words: string;
  question: string;
  options: ClarificationOption[];
}

/** A draft. Nothing in it is active and nothing in it changes a stored policy. */
export interface Interpretation {
  schema_version: SchemaVersion;
  interpretation_id: Id;
  persona_id: PersonaId;
  created_at: IsoDateTime;
  model_id: string | null;
  original_words: string;
  objectives: Objective[];
  proposed_rules: Rule[];
  unsupported: UnsupportedRequest[];
  clarifications: Clarification[];
}

// ---------------------------------------------------------------------------------------------
// challenge.schema.json
// ---------------------------------------------------------------------------------------------

export interface CorrectFactPayload {
  evidence_id: Id;
  /** A fraction, never a percentage, when asserted_unit is `fraction`. */
  asserted_value: number | string;
  asserted_unit: EvidenceUnit;
  user_note: string;
  user_source: string | null;
}

export interface ClarifyPreferencePayload {
  text: string;
  objective_id: Id | null;
}

export interface ChangeRulePayload {
  rule_id: Id;
  new_threshold: Fraction;
  user_note: string | null;
}

export interface CorrectFactChallengeRequest {
  type: "CORRECT_FACT";
  payload: CorrectFactPayload;
}

export interface ClarifyPreferenceChallengeRequest {
  type: "CLARIFY_PREFERENCE";
  payload: ClarifyPreferencePayload;
}

export interface ChangeRuleChallengeRequest {
  type: "CHANGE_RULE";
  payload: ChangeRulePayload;
}

/** Body of POST /investigations/{id}/challenge. Discriminated by `type`. */
export type ChallengeRequest =
  | CorrectFactChallengeRequest
  | ClarifyPreferenceChallengeRequest
  | ChangeRuleChallengeRequest;

export interface ChallengeBase {
  challenge_id: Id;
  investigation_id: Id;
  created_at: IsoDateTime;
}

export interface CorrectFactChallenge extends ChallengeBase {
  type: "CORRECT_FACT";
  payload: CorrectFactPayload;
}

export interface ClarifyPreferenceChallenge extends ChallengeBase {
  type: "CLARIFY_PREFERENCE";
  payload: ClarifyPreferencePayload;
}

export interface ChangeRuleChallenge extends ChallengeBase {
  type: "CHANGE_RULE";
  payload: ChangeRulePayload;
}

/** A stored challenge. Discriminated by `type`. */
export type Challenge = CorrectFactChallenge | ClarifyPreferenceChallenge | ChangeRuleChallenge;

export interface CorrectionProvenance {
  asserted_by: "USER";
  asserted_at: IsoDateTime;
  user_note: string;
  user_source: string | null;
}

/**
 * An UNVERIFIED user assertion. It is never used in a calculation and never replaces the
 * evidence record it disputes. Show it next to the original evidence, labelled unverified.
 */
export interface ProposedCorrection {
  correction_id: Id;
  challenge_id: Id;
  investigation_id: Id;
  evidence_id: Id;
  original_value: number | string | null;
  original_unit: EvidenceUnit;
  asserted_value: number | string;
  asserted_unit: EvidenceUnit;
  provenance: CorrectionProvenance;
  status: CorrectionStatus;
  applied_to_calculation: false;
}

// ---------------------------------------------------------------------------------------------
// investigation_job.schema.json
// ---------------------------------------------------------------------------------------------

export interface InvestigationAgent {
  /** DETERMINISTIC_FALLBACK: the model was unavailable or rejected; every statement is a template. */
  mode: AgentMode;
  model_id: string | null;
  tool_rounds: number;
  note: string | null;
}

/** A real tool event. Never model reasoning. */
export interface InvestigationStep {
  seq: number;
  tool: ToolName;
  initiated_by: StepInitiator;
  started_at: IsoDateTime;
  /** Null while status is RUNNING. */
  finished_at: IsoDateTime | null;
  status: StepStatus;
  input_summary: string;
  /** Null while status is RUNNING. */
  result_summary: string | null;
  evidence_ids: Id[];
}

export interface ExplanationStatement {
  statement_id: Id;
  text: string;
  evidence_ids: Id[];
  rendered_by: RenderedBy;
}

export interface InvestigationFailure {
  code: FailureCode;
  message: string;
  /** True when a new investigation (new idempotency key) may succeed. */
  retryable: boolean;
}

/**
 * Body of GET /investigations/{id}. Lifecycle QUEUED -> RUNNING -> SUCCEEDED | FAILED.
 * - QUEUED: no steps, no result, no clarification, no failure, no explanation.
 * - RUNNING: steps may exist; no result, clarification, failure or explanation yet.
 * - SUCCEEDED: `result` and/or `clarification` is set; `failure` is null.
 * - FAILED: `failure` is set; `result` and `clarification` are null; `explanation` is empty.
 * Once terminal, only `proposed_corrections` can grow.
 */
export interface InvestigationJob {
  schema_version: SchemaVersion;
  id: Id;
  status: JobStatus;
  created_at: IsoDateTime;
  updated_at: IsoDateTime;
  deadline_at: IsoDateTime;
  expires_at: IsoDateTime;
  idempotency_key: string;
  persona_id: PersonaId;
  policy_id: Id;
  policy_version: number;
  request: PurchaseRequest | UnresolvedPurchaseRequest;
  /** The structured request actually evaluated; null while a free-text request is unresolved. */
  resolved_request: PurchaseRequest | null;
  parent_investigation_id: Id | null;
  /** The CHANGE_RULE challenge that created this job, else null. */
  challenge: Challenge | null;
  agent: InvestigationAgent;
  steps: InvestigationStep[];
  clarification: Clarification | null;
  result: CheckResult | null;
  explanation: ExplanationStatement[];
  failure: InvestigationFailure | null;
  proposed_corrections: ProposedCorrection[];
  /** The exact fictional portfolio this job is checked against, fixed at creation. Absent only on jobs stored before this member existed. */
  portfolio?: Portfolio;
}

// ---------------------------------------------------------------------------------------------
// scenario.schema.json
// ---------------------------------------------------------------------------------------------

export interface PersonaFact {
  fact_id: Id;
  label: string;
  /** Wording of the official case. */
  text: string;
  case_reference: string;
}

export interface PersonaTests {
  text: string;
  case_reference: string;
}

export interface Persona {
  persona_id: PersonaId;
  display_name: string;
  case_reference: string;
  facts: PersonaFact[];
  what_this_persona_tests: PersonaTests;
}

export interface AlternativeRuleSet {
  set_id: Id;
  label: string;
  purpose: string;
  rules: Rule[];
}

export interface DemoPhrase {
  phrase_id: Id;
  original_words: string;
  expected_outcome: DemoPhraseOutcome;
  note: string;
}

export interface DemoRequest {
  request_id: Id;
  label: string;
  purchase_request: PurchaseRequest;
}

export interface DemoChallenge {
  label: string;
  type: ChallengeType;
  payload: Record<string, unknown>;
}

export interface DemoStep {
  seq: number;
  stage: UiStage;
  description: string;
}

/**
 * A fictional persona scenario. Persona facts quote the official case; the portfolio, the
 * thresholds and the scripted requests are invented by the team. `scenario_rules` are
 * OFFERED for confirmation (status PROPOSED): inactive until the user confirms them.
 */
export interface Scenario {
  schema_version: SchemaVersion;
  fictional: true;
  fiction_notice: string;
  persona: Persona;
  portfolio: Portfolio;
  objectives: Objective[];
  scenario_rules: Rule[];
  alternative_rule_sets: AlternativeRuleSet[];
  demo_phrases: DemoPhrase[];
  demo_requests: DemoRequest[];
  demo_challenge: DemoChallenge | null;
  demo_steps: DemoStep[];
}

// ---------------------------------------------------------------------------------------------
// api.schema.json: request and response bodies of the seven routes (contracts/api.md)
// ---------------------------------------------------------------------------------------------

export interface ErrorDetail {
  /** JSON path of the offending field, `""` for the body. */
  path: string;
  issue: string;
}

export interface ErrorBody {
  code: ErrorCode;
  /** Safe to display. */
  message: string;
  details: ErrorDetail[];
  request_id: string | null;
}

/** Body of every 4xx and 5xx answer produced by the service. */
export interface ErrorResponse {
  error: ErrorBody;
}

/** GET /portfolios/{persona_id}: 200. */
export interface PortfolioResponse {
  schema_version: SchemaVersion;
  scenario: Scenario;
  /** Registry entries for every position and every purchasable instrument. */
  instruments: Record<InstrumentId, Instrument>;
  purchasable_instrument_ids: InstrumentId[];
}

/**
 * A user-edited fictional portfolio (POST /check, POST /investigations). Weights only: the server builds
 * the full portfolio and its id. cash_weight + sum(position weights) = 1; instruments unique and purchasable.
 */
export interface CustomPortfolio {
  cash_weight: Fraction;
  positions: Position[];
}

/** POST /rules/interpret: request. */
export interface InterpretRequest {
  persona_id: PersonaId;
  /** The user's words, 1 to 2000 characters. */
  text: string;
  policy_id: Id | null;
  policy_version: number | null;
}

/** POST /rules/interpret: 200. */
export type InterpretResponse = Interpretation;

export interface RuleConfirmation {
  /** The PROPOSED rule being confirmed, as displayed. */
  rule: Rule;
  /** The number the user explicitly entered, selected or accepted. Always required. */
  threshold: Fraction;
}

/** POST /rules/confirm: request. */
export interface ConfirmRequest {
  persona_id: PersonaId;
  /** Null creates a new policy (version 1). */
  policy_id: Id | null;
  /** The version the client saw; required with policy_id. */
  base_version: number | null;
  /** The complete objective list of the new version. */
  objectives: Objective[];
  confirmations: RuleConfirmation[];
  withdraw_rule_ids: Id[];
  change_note: string | null;
}

/** POST /rules/confirm: 201. */
export interface ConfirmResponse {
  schema_version: SchemaVersion;
  policy: Policy;
}

/** POST /check: request. */
export interface CheckRequest {
  persona_id: PersonaId;
  policy_id: Id | null;
  policy_version: number | null;
  purchase_request: PurchaseRequest;
  /** Null: evaluate the stored policy version. Array: evaluate exactly these rules; the result has `preview: true` and nothing is stored. */
  draft_rules: Rule[] | null;
  /** Optional. Absent or null: the persona's scenario portfolio. An object: this customized fictional portfolio is checked instead. */
  custom_portfolio?: CustomPortfolio | null;
}

/** POST /check: 200. */
export type CheckResponse = CheckResult;

/** POST /investigations: request. Needs the `Idempotency-Key` header. */
export interface InvestigationCreateRequest {
  persona_id: PersonaId;
  policy_id: Id;
  policy_version: number;
  request: PurchaseRequest | UnresolvedPurchaseRequest;
  parent_investigation_id: Id | null;
  /** Optional. Absent or null: the persona's scenario portfolio. An object: this customized fictional portfolio is investigated and stored with the job. */
  custom_portfolio?: CustomPortfolio | null;
}

export interface PollInstruction {
  path: string;
  interval_ms: number;
}

/** POST /investigations: 202. */
export interface InvestigationAccepted {
  schema_version: SchemaVersion;
  id: Id;
  status: JobStatus;
  created_at: IsoDateTime;
  deadline_at: IsoDateTime;
  expires_at: IsoDateTime;
  poll: PollInstruction;
}

/** GET /investigations/{id}: 200. */
export type InvestigationResponse = InvestigationJob;

/**
 * POST /investigations/{id}/challenge: response. Exactly the members that belong to
 * `challenge.type` are non-null:
 * CORRECT_FACT (201) -> proposed_correction; CLARIFY_PREFERENCE (200) -> interpretation;
 * CHANGE_RULE (202) -> policy and investigation.
 */
export interface ChallengeResponse {
  schema_version: SchemaVersion;
  challenge: Challenge;
  proposed_correction: ProposedCorrection | null;
  interpretation: Interpretation | null;
  policy: Policy | null;
  investigation: InvestigationAccepted | null;
}

// ---------------------------------------------------------------------------------------------
// fixture.schema.json: wrappers of contracts/fixtures (useful in tests)
// ---------------------------------------------------------------------------------------------

export interface ApiFixture {
  fixture: true;
  fixture_id: Id;
  synthetic: boolean;
  synthetic_note: string;
  description: string;
  /** e.g. `POST /check`. */
  route: string;
  http_status: number;
  request_headers: Record<string, string>;
  request_body: Record<string, unknown> | null;
  response_schema: string;
  response_body: Record<string, unknown>;
}

export interface EngineUniverse {
  fixture: true;
  universe_id: Id;
  synthetic: true;
  synthetic_note: string;
  instruments: InstrumentRegistry;
  holdings: HoldingsSnapshot;
  market_data: MarketData;
  controversies: ControversyRegistry;
  sources: SourceRegistry;
}

export interface EngineFixtureInputs {
  portfolio: Portfolio;
  policy: Policy;
  purchase_request: PurchaseRequest;
}

export interface EngineFixture {
  fixture: true;
  fixture_id: Id;
  synthetic: true;
  synthetic_note: string;
  title: string;
  tests: string[];
  universe: string;
  hand_calc: string;
  inputs: EngineFixtureInputs;
  /** A PARTIAL CheckResult (subset match, contracts/SEMANTICS.md section 12). */
  expected: Record<string, unknown>;
}
