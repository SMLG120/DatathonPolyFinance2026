"""Light TypedDict views of the main contract shapes. Standard library only.

These are for editor help and static checks; the JSON Schemas remain the
authority and ``validate_*`` is what enforces them at runtime. Nested or rarely
used shapes are typed as ``dict``/``list`` on purpose to keep this file small.
"""

from __future__ import annotations

from typing import Any, List, Literal, Optional, TypedDict, Union

Fraction = float
IsoDate = str
IsoDateTime = str

RuleType = Literal["max_issuer_exposure", "min_issuer_exposure", "exclusion", "controversy_exclusion", "scenario_loss_budget"]
RuleStatus = Literal["PROPOSED", "CONFIRMED", "SUPERSEDED"]
RuleOrigin = Literal["USER_STATED", "FICTIONAL_SCENARIO", "SYSTEM_PROPOSED"]
ThresholdKind = Literal["max_fraction", "min_fraction", "max_loss_fraction"]
ThresholdSource = Literal["USER_WORDS", "USER_ENTERED", "FICTIONAL_SCENARIO"]
VerdictStatus = Literal["PASS", "FAIL", "UNKNOWN"]
JobStatus = Literal["QUEUED", "RUNNING", "SUCCEEDED", "FAILED"]
Headline = Literal["ALL_PASS", "HAS_FAIL", "NO_FAIL_BUT_UNKNOWN", "INVALID_REQUEST", "POLICY_CONFLICT", "NO_RULES_EVALUATED", "EXECUTION_ERROR"]


class Position(TypedDict):
    instrument_id: str
    weight: Fraction


class Portfolio(TypedDict):
    schema_version: str
    portfolio_id: str
    persona_id: str
    fictional: Literal[True]
    valuation_date: IsoDate
    base_currency: Literal["CAD"]
    cash_weight: Fraction
    positions: List[Position]


class Objective(TypedDict):
    objective_id: str
    original_words: str
    kind: Literal["goal", "preference", "constraint"]
    source: Literal["USER_STATED", "FICTIONAL_SCENARIO"]
    case_reference: Optional[str]


class Rule(TypedDict):
    rule_id: str
    rule_type: RuleType
    parameters: dict
    threshold: Optional[Fraction]
    threshold_kind: ThresholdKind
    threshold_source: Optional[ThresholdSource]
    threshold_quote: Optional[str]
    unit: Literal["fraction"]
    status: RuleStatus
    origin: RuleOrigin
    original_words: str
    objective_id: Optional[str]
    scope_description: str
    confirmed_at: Optional[IsoDateTime]
    confirmed_by: Optional[str]
    supersedes_rule_id: Optional[str]
    superseded_by_rule_id: Optional[str]


class Policy(TypedDict):
    schema_version: str
    policy_id: str
    persona_id: str
    version: int
    parent_version: Optional[int]
    created_at: IsoDateTime
    objectives: List[Objective]
    rules: List[Rule]
    change_note: str
    content_hash: str


class PurchaseRequest(TypedDict):
    instrument_id: str
    target_direct_weight: Fraction
    funding: Literal["CASH"]
    original_words: Optional[str]


class Instrument(TypedDict):
    instrument_id: str
    issuer_id: str
    name: str
    asset_class: Literal["equity", "etf_equity", "etf_bond", "etf_commodity", "crypto"]
    currency: Literal["CAD", "USD"]
    is_fund: bool
    equity_scope: bool
    sector: Optional[str]
    sector_source: Optional[str]


class Holding(TypedDict):
    fund_id: str
    issuer_id: str
    instrument_id: str
    name: str
    weight_fraction: Fraction
    sector: Optional[str]
    sector_source: Optional[str]


class Bounds(TypedDict):
    lower: float
    upper: float


class EvidenceRecord(TypedDict):
    evidence_id: str
    label: Literal["FACT", "ASSUMPTION", "FICTIONAL_SCENARIO", "CALCULATION"]
    metric_id: str
    value: Union[float, str, None]
    unit: Literal["fraction", "price", "fx_rate", "days", "count", "date", "text"]
    currency: Optional[str]
    subject: dict
    period: dict
    source_ids: List[str]
    assumptions: List[str]
    derived_from: List[str]
    formula: Optional[str]
    calculation_version: str
    policy_version: Optional[int]


class RuleResult(TypedDict):
    rule_id: str
    rule_type: RuleType
    status: VerdictStatus
    measured: Optional[Bounds]
    limit: Fraction
    gap: Optional[float]
    breaching_subjects: List[dict]
    out_of_scope: List[dict]
    unknown_causes: List[str]
    starting: dict
    evidence_ids: List[str]
    reason: str


class Summary(TypedDict):
    headline: Headline
    counts: dict
    rules_evaluated: int
    rules_not_evaluated: int
    starting_portfolio_breaches: int
    feasibility_status: Optional[str]


class CheckResult(TypedDict):
    schema_version: str
    persona_id: str
    portfolio_id: str
    policy_id: Optional[str]
    policy_version: Optional[int]
    preview: bool
    calculation_version: str
    valuation_date: IsoDate
    purchase_request: PurchaseRequest
    execution: dict
    feasibility: Optional[dict]
    policy_consistency: dict
    rule_results: List[RuleResult]
    rules_not_evaluated: List[dict]
    starting_portfolio_findings: List[dict]
    data_coverage: List[dict]
    scenario: Optional[dict]
    goal_context: List[dict]
    max_compliant: Optional[dict]
    exposure: Optional[dict]
    evidence: List[EvidenceRecord]
    summary: Summary
    disclosures: List[str]


class InvestigationJob(TypedDict):
    schema_version: str
    id: str
    status: JobStatus
    created_at: IsoDateTime
    updated_at: IsoDateTime
    deadline_at: IsoDateTime
    expires_at: IsoDateTime
    idempotency_key: str
    persona_id: str
    policy_id: str
    policy_version: int
    request: dict
    resolved_request: Optional[PurchaseRequest]
    parent_investigation_id: Optional[str]
    challenge: Optional[dict]
    agent: dict
    steps: List[dict]
    clarification: Optional[dict]
    result: Optional[CheckResult]
    explanation: List[dict]
    failure: Optional[dict]
    proposed_corrections: List[dict]


class Interpretation(TypedDict):
    schema_version: str
    interpretation_id: str
    persona_id: str
    created_at: IsoDateTime
    model_id: Optional[str]
    original_words: str
    objectives: List[Objective]
    proposed_rules: List[Rule]
    unsupported: List[dict]
    clarifications: List[dict]


JsonObject = dict[str, Any]
