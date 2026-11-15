"""Valid documents taken from the fixtures, and deliberately broken variants of them.

SCHEMA_NEGATIVES are broken in shape: the JSON Schema must reject them (both
the standard-library interpreter and `jsonschema`). SEMANTIC_NEGATIVES keep a
valid shape but break a rule a schema cannot express: the validate_* functions
must reject them with a message containing the given fragment.
"""

from __future__ import annotations

import byb_contracts as byb
from fixture_lib import max_issuer
from paths import API, ENGINE, SCENARIO_DIR, load


def put(*path_and_value):
    *path, value = path_and_value

    def mutate(document):
        node = document
        for key in path[:-1]:
            node = node[key]
        node[path[-1]] = value
    return mutate


def drop(*path):
    def mutate(document):
        node = document
        for key in path[:-1]:
            node = node[key]
        del node[path[-1]]
    return mutate


def update(**changes):
    return lambda document: document.update(changes)


def valid_documents():
    """label -> (schema reference, document)."""
    api = lambda name: load(API / f"{name}.json")  # noqa: E731
    universe = load(ENGINE / "synthetic_universe.json")
    robert = load(SCENARIO_DIR / "robert.json")
    r2 = load(ENGINE / "R2.json")
    result = api("investigation_robert_succeeded")["response_body"]["result"]
    return {
        "rule_confirmed": ("rule.schema.json", r2["inputs"]["policy"]["rules"][2]),
        "rule_superseded": ("rule.schema.json", r2["inputs"]["policy"]["rules"][0]),
        "rule_system_proposed": ("rule.schema.json", api("interpret_mateo_clarification")["response_body"]["proposed_rules"][0]),
        "rule_user_words": ("rule.schema.json", max_issuer(
            "r-user-words", 0.15, status="PROPOSED", origin="USER_STATED", threshold_source="USER_WORDS", quote="no more than 15%",
            words="Keep any single company at no more than 15% of my portfolio.")),
        "portfolio": ("portfolio.schema.json", robert["portfolio"]),
        "purchase_request": ("purchase_request.schema.json", robert["demo_requests"][0]["purchase_request"]),
        "policy": ("policy.schema.json", r2["inputs"]["policy"]),
        "check_result": ("check_result.schema.json", result),
        "check_result_mateo": ("check_result.schema.json", api("investigation_mateo_succeeded")["response_body"]["result"]),
        "check_result_invalid_request": ("check_result.schema.json", api("check_invalid_request")["response_body"]),
        "evidence_record": ("evidence_record.schema.json", result["evidence"][0]),
        "job_queued": ("investigation_job.schema.json", api("investigation_robert_queued")["response_body"]),
        "job_running": ("investigation_job.schema.json", api("investigation_robert_running")["response_body"]),
        "job_succeeded": ("investigation_job.schema.json", api("investigation_robert_succeeded")["response_body"]),
        "job_after_challenge": ("investigation_job.schema.json", api("investigation_robert_after_challenge_succeeded")["response_body"]),
        "job_failed": ("investigation_job.schema.json", api("investigation_failed")["response_body"]),
        "job_clarification": ("investigation_job.schema.json", api("investigation_amira_clarification")["response_body"]),
        "interpretation": ("interpretation.schema.json", api("interpret_mateo_clarification")["response_body"]),
        "interpretation_amira": ("interpretation.schema.json", api("interpret_amira_ambiguous")["response_body"]),
        "challenge": ("challenge.schema.json", api("challenge_change_rule")["response_body"]["challenge"]),
        "proposed_correction": ("challenge.schema.json#/$defs/proposed_correction", api("challenge_correct_fact")["response_body"]["proposed_correction"]),
        "challenge_response": ("api.schema.json#/$defs/challenge_response", api("challenge_change_rule")["response_body"]),
        "error_response": ("api.schema.json#/$defs/error_response", api("error_validation")["response_body"]),
        "investigation_accepted": ("api.schema.json#/$defs/investigation_accepted", api("investigation_accepted")["response_body"]),
        "portfolio_response": ("api.schema.json#/$defs/portfolio_response", api("portfolio_robert")["response_body"]),
        "interpret_request": ("api.schema.json#/$defs/interpret_request", api("interpret_mateo_clarification")["request_body"]),
        "confirm_request": ("api.schema.json#/$defs/confirm_request", api("confirm_robert_v1")["request_body"]),
        "check_request": ("api.schema.json#/$defs/check_request", api("check_robert_preview")["request_body"]),
        "investigation_create_request": ("api.schema.json#/$defs/investigation_create_request", api("investigation_accepted")["request_body"]),
        "challenge_request": ("api.schema.json#/$defs/challenge_request", api("challenge_change_rule")["request_body"]),
        "scenario": ("scenario.schema.json", robert),
        "instrument": ("instrument.schema.json", universe["instruments"]["instruments"]["SYN_A"]),
        "holdings": ("holdings_snapshot.schema.json", universe["holdings"]),
        "market_data": ("market_data.schema.json", universe["market_data"]),
        "controversies": ("controversy_record.schema.json#/$defs/registry", universe["controversies"]),
        "sources": ("source.schema.json#/$defs/registry", universe["sources"]),
    }


STATEMENT = {"statement_id": "st-x", "text": "x", "evidence_ids": [], "rendered_by": "TEMPLATE"}
FAILURE = {"code": "WORKER_ERROR", "message": "x", "retryable": False}

# (label, valid document it starts from, mutation)
SCHEMA_NEGATIVES = [
    ("confirmed rule with a null threshold", "rule_confirmed", put("threshold", None)),
    ("confirmed rule with a null threshold and no source", "rule_confirmed", update(threshold=None, threshold_source=None)),
    ("confirmed rule relabelled system-proposed", "rule_confirmed", update(threshold=None, threshold_source=None, origin="SYSTEM_PROPOSED")),
    ("superseded rule with a null threshold", "rule_superseded", update(threshold=None, threshold_source=None, origin="SYSTEM_PROPOSED")),
    ("system-proposed rule with a number", "rule_system_proposed", put("threshold", 0.10)),
    ("system-proposed rule with a number and a source", "rule_system_proposed", update(threshold=0.10, threshold_source="USER_ENTERED")),
    ("system-proposed rule with a source but no number", "rule_system_proposed", put("threshold_source", "USER_ENTERED")),
    ("threshold written as a percentage", "rule_confirmed", put("threshold", 10)),
    ("negative threshold", "rule_confirmed", put("threshold", -0.1)),
    ("unit other than fraction", "rule_confirmed", put("unit", "percent")),
    ("unknown rule status", "rule_confirmed", put("status", "ACTIVE")),
    ("unknown rule type", "rule_confirmed", put("rule_type", "max_sector_exposure")),
    ("number quoted from the user's words without the quote", "rule_user_words", put("threshold_quote", None)),
    ("quote on a number that did not come from the user's words", "rule_confirmed", put("threshold_quote", "10%")),
    ("fictional-scenario origin with a user-entered source", "rule_confirmed", put("threshold_source", "USER_ENTERED")),
    ("user-stated origin with a fictional-scenario source", "rule_user_words", update(threshold_source="FICTIONAL_SCENARIO", threshold_quote=None)),
    ("proposed rule carrying a confirmation time", "rule_user_words", put("confirmed_at", "2026-11-14T15:00:00Z")),
    ("confirmed rule without a confirmation time", "rule_confirmed", put("confirmed_at", None)),
    ("confirmed rule with superseded_by set", "rule_confirmed", put("superseded_by_rule_id", "other-rule")),
    ("parameters of another rule type", "rule_confirmed", put("parameters", {"issuer_scope": "any"})),
    ("threshold kind of another rule type", "rule_confirmed", put("threshold_kind", "min_fraction")),
    ("unknown scenario id", "rule_confirmed", put("parameters", {"scenario_id": "crash_2008"})),
    ("extra percentage field on a rule", "rule_confirmed", put("threshold_percent", 10)),
    ("rule without its scope description", "rule_confirmed", drop("scope_description")),
    ("portfolio weights written as percentages", "portfolio", put("cash_weight", 30)),
    ("portfolio not flagged fictional", "portfolio", put("fictional", False)),
    ("position with zero weight", "portfolio", put("positions", 0, "weight", 0)),
    ("lower-case instrument id", "portfolio", put("positions", 0, "instrument_id", "xbb.to")),
    ("base currency other than CAD", "portfolio", put("base_currency", "USD")),
    ("unsupported funding path", "purchase_request", put("funding", "SELL_BONDS")),
    ("target written as a percentage string", "purchase_request", put("target_direct_weight", "25%")),
    ("purchase request without original_words", "purchase_request", drop("original_words")),
    ("policy with a malformed hash", "policy", put("content_hash", "sha256:abc")),
    ("policy timestamp without Z", "policy", put("created_at", "2026-11-14T15:06:00")),
    ("policy version zero", "policy", put("version", 0)),
    ("single overall compliant boolean", "check_result", put("compliant", True)),
    ("headline outside the enumeration", "check_result", put("summary", "headline", "COMPLIANT")),
    ("verdict status outside PASS/FAIL/UNKNOWN", "check_result", put("rule_results", 0, "status", "WARNING")),
    ("wrong schema version", "check_result", put("schema_version", "2.0.0")),
    ("supported maximum that was not re-run", "check_result", put("max_compliant", "verified_by_rerun", False)),
    ("supported maximum without a number", "check_result", put("max_compliant", "final_direct_weight", None)),
    ("no-feasible-purchase carrying a number", "check_result_mateo", put("max_compliant", "final_direct_weight", 0.10)),
    ("goal context with a status", "check_result", put("goal_context", 0, "status", "FAIL")),
    ("starting finding that is not a FAIL", "check_result_mateo", put("starting_portfolio_findings", 0, "status", "UNKNOWN")),
    ("unknown cause outside the enumeration", "check_result_mateo", put("rule_results", 1, "unknown_causes", ["NO_DATA"])),
    ("drawdown above zero", "check_result", put("scenario", "starting", "scenario_max_drawdown", 0.05)),
    ("execution status outside the enumeration", "check_result_invalid_request", put("execution", "status", "REJECTED")),
    ("evidence with an unknown label", "evidence_record", put("label", "OPINION")),
    ("evidence with a percent unit", "evidence_record", put("unit", "percent")),
    ("evidence without sources field", "evidence_record", drop("source_ids")),
    ("queued job with a failure", "job_queued", put("failure", FAILURE)),
    ("queued job with an explanation", "job_queued", put("explanation", [STATEMENT])),
    ("running job with an explanation", "job_running", put("explanation", [STATEMENT])),
    ("running step with a finish time", "job_running", put("steps", -1, "finished_at", "2026-11-14T15:02:20Z")),
    ("succeeded job with a failure", "job_succeeded", put("failure", FAILURE)),
    ("succeeded job with neither result nor clarification", "job_succeeded", put("result", None)),
    ("finished step without a result summary", "job_succeeded", put("steps", 0, "result_summary", None)),
    ("tool outside the allowlist", "job_succeeded", put("steps", 0, "tool", "run_shell")),
    ("statement with an unknown renderer", "job_succeeded", put("explanation", 0, "rendered_by", "MODEL")),
    ("failed job without a failure", "job_failed", put("failure", None)),
    ("failed job with an explanation", "job_failed", put("explanation", [STATEMENT])),
    ("idempotency key too short", "job_queued", put("idempotency_key", "abc")),
    ("job timestamp without Z", "job_queued", put("created_at", "2026-11-14T15:02:00")),
    ("job status outside the enumeration", "job_queued", put("status", "PENDING")),
    ("correction applied to a calculation", "proposed_correction", put("applied_to_calculation", True)),
    ("correction marked verified", "proposed_correction", put("status", "VERIFIED")),
    ("correction not asserted by the user", "proposed_correction", put("provenance", "asserted_by", "SYSTEM")),
    ("challenge threshold written as a percentage", "challenge", put("payload", "new_threshold", 30)),
    ("challenge type that does not match its payload", "challenge", put("type", "CORRECT_FACT")),
    ("challenge type outside the enumeration", "challenge", put("type", "DELETE_EVIDENCE")),
    ("clarification with a single option", "interpretation", lambda d: d["clarifications"][0].update(options=d["clarifications"][0]["options"][:1])),
    ("unsupported item with an unknown code", "interpretation_amira", put("unsupported", 0, "code", "MAYBE")),
    ("interpretation without clarifications field", "interpretation", drop("clarifications")),
    ("error code outside the enumeration", "error_response", put("error", "code", "OOPS")),
    ("error without request_id", "error_response", drop("error", "request_id")),
    ("poll interval below 500 ms", "investigation_accepted", put("poll", "interval_ms", 100)),
    ("interpret request with empty text", "interpret_request", put("text", "")),
    ("confirmation without a number", "confirm_request", put("confirmations", 0, "threshold", None)),
    ("confirmation with a percentage", "confirm_request", put("confirmations", 0, "threshold", 10)),
    ("check request without draft_rules", "check_request", drop("draft_rules")),
    ("investigation request without a policy version", "investigation_create_request", put("policy_version", None)),
    ("half-resolved purchase request", "investigation_create_request", put("request", "target_direct_weight", None)),
    ("challenge request with a foreign payload", "challenge_request", put("payload", {"text": "x", "objective_id": None})),
    ("scenario not flagged fictional", "scenario", put("fictional", False)),
    ("instrument with an unknown asset class", "instrument", put("asset_class", "bond")),
    ("fund weight written as a percentage", "holdings", put("funds", "FUND_A", "holdings", 0, "weight_fraction", 20)),
    ("price row with an impossible date", "market_data", put("prices", "SYN_A", "series", 0, ["2021-13-01", 100.0])),
    ("price row with a third element", "market_data", put("prices", "SYN_A", "series", 0, ["2021-12-30", 100.0, 1])),
    ("non-positive FX rate", "market_data", put("fx_usdcad", 0, ["2021-12-30", 0])),
    ("controversy with an unknown nature", "controversies", put("records", 0, "nature", "RUMOUR")),
    ("controversy record without a source", "controversies", put("records", 0, "source_ids", [])),
    ("source without reuse terms", "sources", drop("sources", "SYNTHETIC_FIXTURE", "terms")),
    ("source with a malformed hash", "sources", put("sources", "SYNTHETIC_FIXTURE", "sha256", "not-a-hash")),
]


def _job_errors(document):
    return byb.investigation_job_errors(document)


def _holdings_errors(document):
    try:
        byb.validate_holdings_snapshot(document)
    except byb.ContractError as error:
        return error.errors
    return []


def _market_errors(document):
    try:
        byb.validate_market_data(document)
    except byb.ContractError as error:
        return error.errors
    return []


def _controversy_errors(document):
    try:
        byb.validate_controversy_registry(document, known_source_ids=["SYNTHETIC_FIXTURE"])
    except byb.ContractError as error:
        return error.errors
    return []


def _swap_first_two(key):
    def mutate(document):
        document[key][0], document[key][1] = document[key][1], document[key][0]
    return mutate


def _set_summary_fail_count(document):
    document["summary"]["counts"]["fail"] = 0


def _number_from_nowhere(document):
    rule = document["proposed_rules"][0]
    rule.update(threshold=0.05, threshold_source="USER_WORDS", threshold_quote="at most 5%", origin="USER_STATED")


def _fictional_rule_from_interpreter(document):
    document["proposed_rules"][0].update(threshold=0.05, threshold_source="FICTIONAL_SCENARIO", origin="FICTIONAL_SCENARIO")


# (label, valid document it starts from, mutation, function returning the error list, fragment the message must contain)
SEMANTIC_NEGATIVES = [
    ("weights that do not add up to 1", "portfolio", put("cash_weight", 0.25), byb.portfolio_errors, "must equal 1"),
    ("the same instrument twice", "portfolio", lambda d: d["positions"].__setitem__(1, dict(d["positions"][0])), byb.portfolio_errors, "more than once"),
    ("policy edited without re-hashing", "policy", put("change_note", "edited"), byb.policy_errors, "content_hash"),
    ("version 2 without a parent", "policy", put("parent_version", None), byb.policy_errors, "parent_version"),
    ("rule linked to an unknown objective", "policy", put("rules", 1, "objective_id", "obj-nowhere"), byb.policy_errors, "is not an objective"),
    ("supersede link that is not mutual", "policy", put("rules", 1, "supersedes_rule_id", "robert-loss-budget-1"), byb.policy_errors, "pointing back"),
    ("duplicate rule id", "policy", put("rules", 2, "rule_id", "robert-issuer-cap-2"), byb.policy_errors, "more than once"),
    ("summary that disagrees with the rule results", "check_result", _set_summary_fail_count, byb.check_result_errors, "not the derived summary"),
    ("summary headline upgraded to ALL_PASS", "check_result", put("summary", "headline", "ALL_PASS"), byb.check_result_errors, "not the derived summary"),
    ("status that does not follow from the bounds", "check_result", put("rule_results", 0, "status", "PASS"), byb.check_result_errors, "does not follow"),
    ("gap that does not follow from the bounds", "check_result", put("rule_results", 0, "gap", 0.15), byb.check_result_errors, "gap"),
    ("UNKNOWN without a cause", "check_result_mateo", put("rule_results", 1, "unknown_causes", []), byb.check_result_errors, "unknown_cause"),
    ("starting breach without a finding", "check_result_mateo", put("starting_portfolio_findings", []), byb.check_result_errors, "starting_portfolio_findings"),
    ("purchase effect that is not proposed minus starting", "check_result_mateo", put("starting_portfolio_findings", 0, "purchase_effect", "lower_change", 0.017),
     byb.check_result_errors, "purchase_effect"),
    ("cash after that does not follow", "check_result", put("feasibility", "cash_after", 0.10), byb.check_result_errors, "cash_after"),
    ("infeasible purchase reported feasible", "check_result", lambda d: d["feasibility"].update(cash_before=0.20, cash_after=-0.05), byb.check_result_errors, "does not follow from cash_after"),
    ("uncovered weight that does not follow from coverage", "check_result", put("data_coverage", 1, "uncovered_portfolio_weight", 0.0), byb.check_result_errors, "uncovered_portfolio_weight"),
    ("partial fund reported as covered", "check_result", put("data_coverage", 1, "status", "COVERED"), byb.check_result_errors, "does not follow from coverage_fraction"),
    ("evidence id that does not exist", "check_result", put("rule_results", 0, "evidence_ids", ["ev-nowhere"]), byb.check_result_errors, "is not in evidence"),
    ("calculation evidence with no inputs", "check_result", lambda d: next(e for e in d["evidence"] if e["label"] == "CALCULATION").update(derived_from=[], source_ids=[]),
     byb.check_result_errors, "needs derived_from or source_ids"),
    ("fact without a source", "check_result", lambda d: next(e for e in d["evidence"] if e["label"] == "FACT" and e["metric_id"] != "rule_threshold").update(source_ids=[]),
     byb.check_result_errors, "needs at least one source_id"),
    ("measured loss that is not the replayed return", "check_result", put("scenario", "proposed", "scenario_terminal_return", -0.14), byb.check_result_errors, "measured loss"),
    ("maximum beyond what cash can fund", "check_result", lambda d: d["max_compliant"].update(final_direct_weight=0.35, additional_purchase=0.35), byb.check_result_errors, "exceeds what cash can fund"),
    ("binding rule that was not evaluated", "check_result", put("max_compliant", "binding_constraint", "rule_id", "some-other-rule"), byb.check_result_errors, "not an evaluated rule"),
    ("chart row whose lower bound is not direct plus indirect", "check_result", put("exposure", "issuers", 0, "proposed", "lower", 0.25), byb.check_result_errors, "lower != direct"),
    ("stored-policy result without a policy version", "check_result", put("policy_version", None), byb.check_result_errors, "policy_version"),
    ("preview that names a stored policy", "check_result", put("preview", True), byb.check_result_errors, "preview"),
    ("invalid request that still carries rule results", "check_result", lambda d: d["execution"].update(status="INVALID_REQUEST", code="TARGET_NEGATIVE", message="x"),
     byb.check_result_errors, "must be"),
    ("interpreter inventing a number", "interpretation", _number_from_nowhere, byb.interpretation_errors, "not a verbatim span"),
    ("interpreter emitting a fictional-scenario rule", "interpretation", _fictional_rule_from_interpreter, byb.interpretation_errors, "never emits FICTIONAL_SCENARIO"),
    ("unsupported option that carries a draft", "interpretation", lambda d: d["clarifications"][0]["options"][0].update(supported=False), byb.interpretation_errors, "carries no draft"),
    ("clarification about words the user never wrote", "interpretation", put("clarifications", 0, "about_words", "tobacco"), byb.interpretation_errors, "verbatim span"),
    ("job step citing evidence that is not in the result", "job_succeeded", put("steps", 0, "evidence_ids", ["ev-nowhere"]), _job_errors, "is not in result.evidence"),
    ("model statement without evidence", "job_succeeded", put("explanation", 3, "evidence_ids", []), _job_errors, "must cite at least one evidence record"),
    ("steps out of sequence", "job_succeeded", _swap_first_two("steps"), _job_errors, "seq must be"),
    ("result for another policy version", "job_succeeded", put("policy_version", 2), _job_errors, "differ from the job's"),
    ("structured request altered by the investigator", "job_succeeded", put("request", "target_direct_weight", 0.20), _job_errors, "resolved_request"),
    ("fallback mode with a model statement", "job_succeeded", put("agent", "mode", "DETERMINISTIC_FALLBACK"), _job_errors, "DETERMINISTIC_FALLBACK"),
    ("child job whose challenge names another parent", "job_after_challenge", put("parent_investigation_id", "inv-other"), _job_errors, "parent_investigation_id"),
    ("deadline before creation", "job_queued", put("deadline_at", "2026-11-14T15:00:00Z"), _job_errors, "deadline_at"),
    ("scenario rule offered as confirmed", "scenario", lambda d: d["scenario_rules"][0].update(status="CONFIRMED", confirmed_at="2026-11-14T15:00:00Z", confirmed_by="demo_user"),
     byb.scenario_errors, "offered as PROPOSED"),
    ("scenario objective not flagged fictional", "scenario", put("objectives", 0, "source", "USER_STATED"), byb.scenario_errors, "FICTIONAL_SCENARIO"),
    ("scenario challenge naming an unknown rule", "scenario", put("demo_challenge", "payload", "rule_id", "nope"), byb.scenario_errors, "not a rule of the scenario"),
    ("instrument flags that contradict the asset class", "instrument", put("equity_scope", False), byb.instrument_errors, "requires is_fund"),
    ("sector label without a source", "instrument", put("sector_source", None), byb.instrument_errors, "both be set or both be null"),
    ("coverage that is not the sum of the weights", "holdings", put("funds", "FUND_B", "coverage_fraction", 1.0), _holdings_errors, "weights are never rescaled"),
    ("holding count that does not match", "holdings", put("funds", "FUND_A", "n_holdings", 3), _holdings_errors, "n_holdings"),
    ("price series out of order", "market_data", lambda d: d["prices"]["SYN_A"]["series"].reverse(), _market_errors, "strictly ascending"),
    ("record for an issuer that was not researched", "controversies", put("records", 0, "issuer_id", "ISS_A"), _controversy_errors, "issuers_researched"),
    ("record citing an unknown source", "controversies", put("records", 0, "source_ids", ["nowhere"]), _controversy_errors, "not in the source registry"),
]
