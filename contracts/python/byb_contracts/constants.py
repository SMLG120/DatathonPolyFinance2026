"""Constants and enumerations shared by every Before You Buy component.

Standard library only. Values mirror ``contracts/schemas/common.schema.json``;
``contracts/python/tests/test_enums_match_schemas.py`` fails if they drift.
"""

from __future__ import annotations

SCHEMA_VERSION = "1.0.0"

# LEAD_DECISIONS D2: fractions are compared with an absolute tolerance.
# value <= limit + EPS passes, so exact equality passes.
EPS = 1e-9
# Tolerance when checking that reported weights add up to coverage_fraction.
COVERAGE_SUM_TOLERANCE = 1e-8
# Largest number of issuers in exposure.issuers and in breaching_subjects.
EXPOSURE_TOP_N = 10
MAX_BREACHING_SUBJECTS = 10

BASE_CURRENCY = "CAD"
FUNDING = "CASH"
UNIT_FRACTION = "fraction"
DEFAULT_VALUATION_DATE = "2026-11-12"

CURRENCIES = ("CAD", "USD")
ASSET_CLASSES = ("equity", "etf_equity", "etf_bond", "etf_commodity", "crypto")
# asset_class -> (is_fund, equity_scope). Derivable, enforced by validate_instrument.
ASSET_CLASS_FLAGS = {
    "equity": (False, True),
    "etf_equity": (True, True),
    "etf_bond": (True, False),
    "etf_commodity": (True, False),
    "crypto": (False, False),
}

OBJECTIVE_KINDS = ("goal", "preference", "constraint")
OBJECTIVE_SOURCES = ("USER_STATED", "FICTIONAL_SCENARIO")

RULE_TYPES = ("max_issuer_exposure", "min_issuer_exposure", "exclusion", "controversy_exclusion", "scenario_loss_budget")
RULE_STATUSES = ("PROPOSED", "CONFIRMED", "SUPERSEDED")
RULE_ORIGINS = ("USER_STATED", "FICTIONAL_SCENARIO", "SYSTEM_PROPOSED")
THRESHOLD_KINDS = ("max_fraction", "min_fraction", "max_loss_fraction")
THRESHOLD_SOURCES = ("USER_WORDS", "USER_ENTERED", "FICTIONAL_SCENARIO")
# rule_type -> threshold_kind (LEAD_DECISIONS D3).
THRESHOLD_KIND_BY_RULE_TYPE = {
    "max_issuer_exposure": "max_fraction",
    "min_issuer_exposure": "min_fraction",
    "exclusion": "max_fraction",
    "controversy_exclusion": "max_fraction",
    "scenario_loss_budget": "max_loss_fraction",
}
# Rules whose measured value must stay at or below the limit / at or above it.
MAX_TYPE_RULES = ("max_issuer_exposure", "exclusion", "controversy_exclusion", "scenario_loss_budget")
MIN_TYPE_RULES = ("min_issuer_exposure",)
EXCLUSION_DEFINITION_KINDS = ("named_issuers", "fund_reported_sector")
ISSUER_SCOPE_ANY = "any"

SCENARIO_IDS = ("replay_2022",)
# A price or FX rate used at a scenario base or end date may be at most this many calendar days old.
# Older (or absent) means the instrument has no usable history: INSUFFICIENT_HISTORY, never a proxy.
MAX_PRICE_AGE_DAYS = 7
# LEAD_DECISIONS D6. Prices and FX are the latest values on or before each date.
SCENARIOS = {
    "replay_2022": {
        "scenario_id": "replay_2022",
        "base_date": "2021-12-31",
        "end_date": "2022-12-30",
        "label": "Replay of the assumed allocation through calendar 2022 (historical replay, not a forecast)",
        "assumptions": (
            "Initial weights are the evaluated allocation, applied at the base date.",
            "Buy and hold: no rebalancing during the period.",
            "Cash earns a return of 0 (no interest credited).",
            "Each instrument uses its own adjusted-close series; a fund uses the fund's series, not its constituents.",
            "USD prices are converted to CAD with the latest Bank of Canada rate on or before each valuation date.",
            "A price or rate more than 7 days older than the base or end date is not used: the result is then unknown.",
            "Fees and taxes are excluded.",
        ),
    }
}

CONTROVERSY_NATURES = ("ALLEGATION", "REGULATORY_FINDING", "COURT_RULING", "SETTLEMENT", "COMPANY_DISCLOSURE")

VERDICT_STATUSES = ("PASS", "FAIL", "UNKNOWN")
EXECUTION_STATUSES = ("OK", "INVALID_REQUEST", "ERROR")
EXECUTION_CODES = (
    "TARGET_BELOW_CURRENT_WEIGHT", "TARGET_NEGATIVE", "TARGET_ABOVE_ONE", "UNSUPPORTED_INSTRUMENT",
    "INVALID_PORTFOLIO", "INVALID_POLICY", "ENGINE_ERROR",
)
FEASIBILITY_STATUSES = ("FEASIBLE", "INSUFFICIENT_CASH")
CONSISTENCY_STATUSES = ("CONSISTENT", "PROVEN_CONFLICT", "NOT_ASSESSED")
CONFLICT_TYPES = ("MIN_EXCEEDS_MAX_SAME_ISSUER",)
COVERAGE_STATUSES = ("COVERED", "PARTIAL", "MISSING")
UNKNOWN_CAUSES = ("PARTIAL_HOLDINGS", "MISSING_HOLDINGS", "UNCLASSIFIED_SECTOR", "REGISTRY_ABSENCE", "INSUFFICIENT_HISTORY")
SCENARIO_STATUSES = ("COMPUTED", "INSUFFICIENT_HISTORY")
MAX_COMPLIANT_STATUSES = ("SUPPORTED", "WITHHELD", "NO_FEASIBLE_PURCHASE")
BINDING_CONSTRAINT_TYPES = ("RULE", "CASH")
HEADLINES = (
    "ALL_PASS", "HAS_FAIL", "NO_FAIL_BUT_UNKNOWN", "INVALID_REQUEST", "POLICY_CONFLICT",
    "NO_RULES_EVALUATED", "EXECUTION_ERROR",
)
GOAL_CONTEXT_TYPES = ("LINKED_RULE_RESULTS", "CONCENTRATION", "SCENARIO_DRAWDOWN", "NOT_QUANTIFIED")

EVIDENCE_LABELS = ("FACT", "ASSUMPTION", "FICTIONAL_SCENARIO", "CALCULATION")
EVIDENCE_UNITS = ("fraction", "price", "fx_rate", "days", "count", "date", "text")
METRIC_IDS = (
    "position_weight", "cash_weight", "cash_after_purchase",
    "fund_constituent_weight", "fund_coverage_fraction", "unattributed_fund_weight",
    "issuer_direct_exposure", "issuer_exposure_via_fund", "exposure_lower", "exposure_upper",
    "rule_threshold", "gap_to_limit",
    "scenario_instrument_return", "scenario_terminal_return", "scenario_max_drawdown", "scenario_loss",
    "price_adj_close", "fx_usdcad", "fx_rate_age_days", "price_age_days",
    "max_compliant_final_weight", "max_compliant_additional_purchase",
    "sector_label", "controversy_record", "holdings_date",
)
SUBJECT_KINDS = ("INSTRUMENT", "ISSUER", "FUND", "PORTFOLIO", "RULE", "FX")
PORTFOLIO_STATES = ("STARTING", "PROPOSED", "NOT_APPLICABLE")

JOB_STATUSES = ("QUEUED", "RUNNING", "SUCCEEDED", "FAILED")
TERMINAL_JOB_STATUSES = ("SUCCEEDED", "FAILED")
TOOL_NAMES = (
    "get_portfolio", "get_policy", "get_holdings", "lookup_controversy_evidence", "simulate_change",
    "compute_exposure", "replay_period", "check_rules", "max_compliant_amount",
)
STEP_STATUSES = ("RUNNING", "OK", "ERROR")
STEP_INITIATORS = ("MODEL", "SERVER")
AGENT_MODES = ("MODEL", "DETERMINISTIC_FALLBACK")
RENDERED_BY = ("TEMPLATE", "MODEL_VALIDATED")
FAILURE_CODES = ("DEADLINE_EXCEEDED", "WORKER_INVOCATION_FAILED", "WORKER_ERROR", "ENGINE_ERROR", "DATA_UNAVAILABLE")

CHALLENGE_TYPES = ("CORRECT_FACT", "CLARIFY_PREFERENCE", "CHANGE_RULE")
CORRECTION_STATUSES = ("UNVERIFIED",)
UNSUPPORTED_CODES = ("UNSUPPORTED_DEFINITION", "UNSUPPORTED_RULE_TYPE", "OUT_OF_SCOPE", "INSTRUCTION_IGNORED")
UI_STAGES = ("PERSONA_PORTFOLIO", "GOALS_RULES", "PROPOSED_PURCHASE", "INVESTIGATION", "VERDICT_EVIDENCE", "CHALLENGE")
ERROR_CODES = (
    "UNAUTHORIZED", "VALIDATION_ERROR", "NOT_FOUND", "POLICY_VERSION_CONFLICT", "IDEMPOTENCY_KEY_REUSED",
    "INVESTIGATION_NOT_FINISHED", "INVESTIGATION_EXPIRED", "INVALID_PURCHASE_REQUEST", "INVALID_CONFIRMATION",
    "UNSUPPORTED_CHALLENGE", "INTERPRETER_TIMEOUT", "INTERPRETER_FAILED", "WORKER_INVOCATION_FAILED",
    "RATE_LIMITED", "INTERNAL_ERROR",
)

# API timing (contracts/api.md). The job document carries the binding server values.
POLL_INTERVAL_MS = 1500
# Server side: deadline_at = created_at + this. A job not terminal by then is FAILED with DEADLINE_EXCEEDED.
INVESTIGATION_DEADLINE_SECONDS = 150
# Client side: stop polling this long after the 202. It must outlast the job deadline.
POLL_DEADLINE_SECONDS = 180
INVESTIGATION_EXPIRY_SECONDS = 86400
INTERPRET_TIMEOUT_SECONDS = 20
CHECK_TIMEOUT_SECONDS = 5

# Name in common.schema.json $defs -> constant above (used by the drift test).
SCHEMA_ENUMS = {
    "currency": CURRENCIES, "asset_class": ASSET_CLASSES, "objective_kind": OBJECTIVE_KINDS,
    "objective_source": OBJECTIVE_SOURCES, "rule_type": RULE_TYPES, "rule_status": RULE_STATUSES,
    "rule_origin": RULE_ORIGINS, "threshold_kind": THRESHOLD_KINDS, "threshold_source": THRESHOLD_SOURCES,
    "exclusion_definition_kind": EXCLUSION_DEFINITION_KINDS, "scenario_id": SCENARIO_IDS,
    "controversy_nature": CONTROVERSY_NATURES, "verdict_status": VERDICT_STATUSES,
    "execution_status": EXECUTION_STATUSES, "execution_code": EXECUTION_CODES,
    "feasibility_status": FEASIBILITY_STATUSES, "consistency_status": CONSISTENCY_STATUSES,
    "conflict_type": CONFLICT_TYPES, "coverage_status": COVERAGE_STATUSES, "unknown_cause": UNKNOWN_CAUSES,
    "scenario_status": SCENARIO_STATUSES, "max_compliant_status": MAX_COMPLIANT_STATUSES,
    "binding_constraint_type": BINDING_CONSTRAINT_TYPES, "headline": HEADLINES,
    "goal_context_type": GOAL_CONTEXT_TYPES, "evidence_label": EVIDENCE_LABELS, "evidence_unit": EVIDENCE_UNITS,
    "metric_id": METRIC_IDS, "subject_kind": SUBJECT_KINDS, "portfolio_state": PORTFOLIO_STATES,
    "job_status": JOB_STATUSES, "tool_name": TOOL_NAMES, "step_status": STEP_STATUSES,
    "step_initiator": STEP_INITIATORS, "agent_mode": AGENT_MODES, "rendered_by": RENDERED_BY,
    "failure_code": FAILURE_CODES, "challenge_type": CHALLENGE_TYPES, "correction_status": CORRECTION_STATUSES,
    "unsupported_code": UNSUPPORTED_CODES, "ui_stage": UI_STAGES, "error_code": ERROR_CODES,
}
