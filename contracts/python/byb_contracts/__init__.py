"""Before You Buy shared contracts (Python side). Standard library only.

    from byb_contracts import SCHEMA_VERSION, validate_portfolio, ContractError

The JSON Schemas in ``contracts/schemas`` are the source of truth; this package
interprets them and adds the semantic checks a schema cannot express.
"""

from .constants import *  # noqa: F401,F403
from .constants import SCHEMA_VERSION, EPS
from .derive import (
    canonical_json,
    compute_content_hash,
    coverage_status,
    derive_headline,
    derive_summary,
    feasibility_status,
    gap_from_bounds,
    rule_is_evaluated,
    status_from_bounds,
)
from .matching import subset_mismatches
from .schema import SchemaUsageError, load_schema, non_finite_errors, schema_dir, schema_errors, schema_files
from .validators import (
    ContractError,
    instrument_errors,
    policy_errors,
    portfolio_errors,
    rule_errors,
    validate_against,
    validate_controversy_record,
    validate_controversy_registry,
    validate_evidence_record,
    validate_holdings_snapshot,
    validate_instrument,
    validate_instrument_registry,
    validate_market_data,
    validate_objective,
    validate_policy,
    validate_portfolio,
    validate_purchase_request,
    validate_rule,
    validate_source,
    validate_source_registry,
    validate_unresolved_purchase_request,
)
from .result_validators import (
    api_body_errors,
    check_result_errors,
    interpretation_errors,
    investigation_job_errors,
    scenario_errors,
    validate_api_body,
    validate_challenge,
    validate_check_result,
    validate_error_response,
    validate_interpretation,
    validate_investigation_job,
    validate_proposed_correction,
    validate_scenario,
)

__version__ = SCHEMA_VERSION
