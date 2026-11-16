"""validate_* functions for engine results, jobs, challenges, interpretations and scenarios.

Standard library only. Beyond the JSON Schema shape these check that a result
is internally consistent: statuses follow from the measured bounds, the summary
follows from the per-rule statuses, every cited evidence id exists, and the
arithmetic identities of contracts/SEMANTICS.md hold within 1e-9.
"""

from __future__ import annotations

from typing import Any

from .constants import EPS
from .derive import coverage_status, derive_summary, feasibility_status, gap_from_bounds, status_from_bounds
from .schema import schema_errors
from .validators import ContractError, _duplicates, _raise, policy_errors, portfolio_errors

_TOL = 1e-9


def _close(a: float, b: float) -> bool:
    return abs(a - b) <= _TOL


def _snapshot_errors(where: str, rule_type: str, status: str, measured: Any, limit: float) -> list[str]:
    errors = []
    lower = measured["lower"] if measured else None
    upper = measured["upper"] if measured else None
    if measured and lower > upper + _TOL:
        errors.append(f"{where}: measured.lower {lower} > measured.upper {upper}")
    expected = status_from_bounds(rule_type, lower, upper, limit)
    if status != expected:
        errors.append(f"{where}: status {status} does not follow from measured {measured} and limit {limit} (expected {expected})")
    return errors


def check_result_errors(result: Any) -> list[str]:
    errors = schema_errors(result, "check_result.schema.json")
    if errors:
        return errors
    ok = result["execution"]["status"] == "OK"
    if ok and result["execution"]["code"] is not None:
        errors.append("execution.code: must be null when status is OK")
    if not ok:
        if result["execution"]["code"] is None or not result["execution"]["message"]:
            errors.append("execution: code and message are required when status is not OK")
        for name in ("feasibility", "scenario", "max_compliant", "exposure"):
            if result[name] is not None:
                errors.append(f"{name}: must be null when execution.status is {result['execution']['status']}")
        for name in ("rule_results", "rules_not_evaluated", "starting_portfolio_findings", "data_coverage", "goal_context", "evidence"):
            if result[name]:
                errors.append(f"{name}: must be empty when execution.status is {result['execution']['status']}")
        if result["policy_consistency"]["status"] != "NOT_ASSESSED" or result["policy_consistency"]["conflicts"]:
            errors.append("policy_consistency: must be NOT_ASSESSED with no conflicts when execution.status is not OK")
    else:
        for name in ("feasibility", "max_compliant", "exposure"):
            if result[name] is None:
                errors.append(f"{name}: required when execution.status is OK")
        if result["policy_consistency"]["status"] == "NOT_ASSESSED":
            errors.append("policy_consistency.status: NOT_ASSESSED is only for results whose execution.status is not OK")

    if result["preview"] and (result["policy_version"] is not None or result["policy_id"] is not None):
        errors.append("preview: a preview carries policy_id null and policy_version null")
    if not result["preview"] and ok and (result["policy_version"] is None or result["policy_id"] is None):
        errors.append("policy_id / policy_version: required when preview is false")

    evidence_ids = [e["evidence_id"] for e in result["evidence"]]
    for dup in _duplicates(evidence_ids):
        errors.append(f"evidence: evidence_id {dup!r} appears more than once")
    known = set(evidence_ids)

    def refs(where: str, ids: list) -> None:
        for evidence_id in ids:
            if evidence_id not in known:
                errors.append(f"{where}: evidence_id {evidence_id!r} is not in evidence[]")

    for i, record in enumerate(result["evidence"]):
        if record["policy_version"] != result["policy_version"]:
            errors.append(f"evidence[{i}]: policy_version {record['policy_version']!r} != result policy_version {result['policy_version']!r}")
        if record["calculation_version"] != result["calculation_version"]:
            errors.append(f"evidence[{i}]: calculation_version differs from the result's")
        refs(f"evidence[{i}].derived_from", record["derived_from"])
        if record["label"] == "CALCULATION" and not record["derived_from"] and not record["source_ids"]:
            errors.append(f"evidence[{i}]: a CALCULATION record needs derived_from or source_ids")
        if record["label"] == "FACT" and not record["source_ids"] and record["metric_id"] != "rule_threshold":
            errors.append(f"evidence[{i}]: a FACT record needs at least one source_id")

    feasibility = result["feasibility"]
    if feasibility:
        if not _close(feasibility["additional_purchase"], feasibility["target_direct_weight"] - feasibility["starting_direct_weight"]):
            errors.append("feasibility.additional_purchase != target_direct_weight - starting_direct_weight")
        if not _close(feasibility["cash_after"], feasibility["cash_before"] - feasibility["additional_purchase"]):
            errors.append("feasibility.cash_after != cash_before - additional_purchase")
        if feasibility["status"] != feasibility_status(feasibility["cash_after"]):
            errors.append(f"feasibility.status {feasibility['status']} does not follow from cash_after {feasibility['cash_after']}")
        if not _close(feasibility["target_direct_weight"], result["purchase_request"]["target_direct_weight"]):
            errors.append("feasibility.target_direct_weight != purchase_request.target_direct_weight")

    consistency = result["policy_consistency"]
    if (consistency["status"] == "PROVEN_CONFLICT") != bool(consistency["conflicts"]):
        errors.append("policy_consistency: status is PROVEN_CONFLICT if and only if conflicts is non-empty")
    for i, conflict in enumerate(consistency["conflicts"]):
        if not conflict["min_fraction"] > conflict["max_fraction"] + EPS:
            errors.append(f"policy_consistency.conflicts[{i}]: min_fraction must exceed max_fraction for a proven conflict")

    for dup in _duplicates(r["rule_id"] for r in result["rule_results"]):
        errors.append(f"rule_results: rule_id {dup!r} appears more than once")
    findings = {f["rule_id"]: f for f in result["starting_portfolio_findings"]}
    for i, entry in enumerate(result["rule_results"]):
        where = f"rule_results[{i}] ({entry['rule_id']})"
        errors.extend(_snapshot_errors(where, entry["rule_type"], entry["status"], entry["measured"], entry["limit"]))
        errors.extend(_snapshot_errors(where + ".starting", entry["rule_type"], entry["starting"]["status"], entry["starting"]["measured"], entry["limit"]))
        measured = entry["measured"]
        expected_gap = gap_from_bounds(entry["rule_type"], entry["status"], measured["lower"] if measured else None, measured["upper"] if measured else None, entry["limit"])
        if (expected_gap is None) != (entry["gap"] is None) or (expected_gap is not None and not _close(expected_gap, entry["gap"])):
            errors.append(f"{where}: gap {entry['gap']!r} does not follow from the bounds (expected {expected_gap!r})")
        if entry["status"] != "FAIL" and entry["breaching_subjects"]:
            errors.append(f"{where}: breaching_subjects must be empty unless status is FAIL")
        if entry["status"] == "UNKNOWN" and not entry["unknown_causes"]:
            errors.append(f"{where}: an UNKNOWN result must name at least one unknown_cause")
        if measured and not _close(measured["lower"], measured["upper"]) and not entry["unknown_causes"]:
            errors.append(f"{where}: lower != upper requires at least one unknown_cause")
        refs(where, entry["evidence_ids"])
        finding = findings.get(entry["rule_id"])
        if (entry["starting"]["status"] == "FAIL") != (finding is not None):
            errors.append(f"{where}: starting_portfolio_findings must list this rule if and only if starting.status is FAIL")
        if finding is not None and entry["starting"]["measured"]:
            start = entry["starting"]["measured"]
            if not (_close(finding["measured"]["lower"], start["lower"]) and _close(finding["measured"]["upper"], start["upper"])):
                errors.append(f"{where}: the starting finding's measured bounds differ from starting.measured")
            if not _close(finding["limit"], entry["limit"]):
                errors.append(f"{where}: the starting finding's limit differs from the rule's limit")
            start_gap = gap_from_bounds(entry["rule_type"], "FAIL", start["lower"], start["upper"], entry["limit"])
            if not _close(finding["gap"], start_gap):
                errors.append(f"{where}: the starting finding's gap {finding['gap']} != {start_gap}")
            if measured and not (
                _close(finding["purchase_effect"]["lower_change"], measured["lower"] - start["lower"])
                and _close(finding["purchase_effect"]["upper_change"], measured["upper"] - start["upper"])
            ):
                errors.append(f"{where}: purchase_effect != proposed bounds - starting bounds")
    evaluated = {r["rule_id"] for r in result["rule_results"]}
    for rule_id in findings:
        if rule_id not in evaluated:
            errors.append(f"starting_portfolio_findings: rule_id {rule_id!r} has no entry in rule_results")
    for i, finding in enumerate(result["starting_portfolio_findings"]):
        refs(f"starting_portfolio_findings[{i}]", finding["evidence_ids"])
    for entry in result["rules_not_evaluated"]:
        if entry["rule_id"] in evaluated:
            errors.append(f"rules_not_evaluated: rule_id {entry['rule_id']!r} is also in rule_results")

    for i, fund in enumerate(result["data_coverage"]):
        where = f"data_coverage[{i}] ({fund['fund_id']})"
        missing = fund["status"] == "MISSING"
        if missing and (fund["coverage_fraction"] != 0 or fund["holdings_date"] is not None or fund["source_id"] is not None):
            errors.append(f"{where}: a MISSING fund has coverage_fraction 0 and null holdings_date and source_id")
        if not missing and fund["status"] != coverage_status(True, fund["coverage_fraction"]):
            errors.append(f"{where}: status {fund['status']} does not follow from coverage_fraction {fund['coverage_fraction']}")
        if not _close(fund["uncovered_portfolio_weight"], fund["portfolio_weight"] * max(0.0, 1 - fund["coverage_fraction"])):
            errors.append(f"{where}: uncovered_portfolio_weight != portfolio_weight x max(0, 1 - coverage_fraction)")
        if fund["sector_labelled_fraction"] > fund["coverage_fraction"] + 1e-8:
            errors.append(f"{where}: sector_labelled_fraction exceeds coverage_fraction")

    scenario = result["scenario"]
    if scenario:
        computed = scenario["status"] == "COMPUTED"
        if computed != (scenario["starting"] is not None and scenario["proposed"] is not None and not scenario["missing_instruments"]):
            errors.append("scenario: COMPUTED needs starting and proposed measures and no missing_instruments; INSUFFICIENT_HISTORY needs the opposite")
        if not computed and (scenario["starting"] is not None or scenario["proposed"] is not None or not scenario["missing_instruments"]):
            errors.append("scenario: INSUFFICIENT_HISTORY carries null measures and lists the missing instruments")
        refs("scenario", scenario["evidence_ids"])
        if scenario["base_date"] >= scenario["end_date"]:
            errors.append("scenario: base_date must be before end_date")
    for i, entry in enumerate(result["rule_results"]):
        if entry["rule_type"] == "scenario_loss_budget":
            if not scenario:
                errors.append(f"rule_results[{i}]: a scenario_loss_budget result requires the scenario section")
            elif scenario["status"] == "INSUFFICIENT_HISTORY":
                if entry["status"] != "UNKNOWN" or entry["measured"] is not None or entry["starting"]["status"] != "UNKNOWN" or entry["starting"]["measured"] is not None:
                    errors.append(f"rule_results[{i}]: without usable history both the proposed and the starting evaluation are UNKNOWN with measured null")
                if "INSUFFICIENT_HISTORY" not in entry["unknown_causes"]:
                    errors.append(f"rule_results[{i}]: unknown_causes must include INSUFFICIENT_HISTORY")
            else:
                for state, snapshot in (("proposed", entry["measured"]), ("starting", entry["starting"]["measured"])):
                    if scenario[state] is None or snapshot is None or not _close(snapshot["lower"], -scenario[state]["scenario_terminal_return"]):
                        errors.append(f"rule_results[{i}]: measured loss must equal -scenario.{state}.scenario_terminal_return")
            if entry["out_of_scope"] or entry["breaching_subjects"]:
                errors.append(f"rule_results[{i}]: scenario_loss_budget has no out_of_scope and no breaching_subjects")

    for i, context in enumerate(result["goal_context"]):
        refs(f"goal_context[{i}]", context["evidence_ids"])

    maximum = result["max_compliant"]
    if maximum:
        refs("max_compliant", maximum["evidence_ids"])
        if maximum["status"] == "SUPPORTED":
            if feasibility:
                if not _close(maximum["additional_purchase"], maximum["final_direct_weight"] - feasibility["starting_direct_weight"]):
                    errors.append("max_compliant.additional_purchase != final_direct_weight - starting direct weight")
                if maximum["final_direct_weight"] > feasibility["starting_direct_weight"] + feasibility["cash_before"] + EPS:
                    errors.append("max_compliant.final_direct_weight exceeds what cash can fund")
                if maximum["additional_purchase"] <= EPS:
                    errors.append("max_compliant: SUPPORTED requires a positive additional purchase; otherwise NO_FEASIBLE_PURCHASE")
            if consistency["status"] == "PROVEN_CONFLICT" or not result["rule_results"]:
                errors.append("max_compliant: must be WITHHELD when the policy has a proven conflict or no rule was evaluated")
        binding = maximum["binding_constraint"]
        if binding and (binding["type"] == "RULE") != (binding["rule_id"] is not None):
            errors.append("max_compliant.binding_constraint: rule_id is set if and only if type is RULE")
        if binding and binding["rule_id"] is not None and binding["rule_id"] not in evaluated:
            errors.append("max_compliant.binding_constraint.rule_id is not an evaluated rule")

    exposure = result["exposure"]
    if exposure:
        for dup in _duplicates(entry["issuer_id"] for entry in exposure["issuers"]):
            errors.append(f"exposure.issuers: issuer_id {dup!r} appears more than once")
        for i, entry in enumerate(exposure["issuers"]):
            for state in ("starting", "proposed"):
                part = entry[state]
                known_exposure = part["direct"] + sum(path["known"] for path in part["indirect_by_fund"])
                if not _close(part["lower"], known_exposure):
                    errors.append(f"exposure.issuers[{i}].{state}: lower != direct + sum(indirect known)")
                if not _close(part["upper"], part["lower"] + exposure["possible_extra"][state]):
                    errors.append(f"exposure.issuers[{i}].{state}: upper != lower + possible_extra.{state}")

    expected_summary = derive_summary(result)
    if result["summary"] != expected_summary:
        errors.append(f"summary: {result['summary']} is not the derived summary {expected_summary}")
    return errors


def validate_check_result(result: Any) -> None:
    _raise("check_result", check_result_errors(result))


def validate_challenge(challenge: Any) -> None:
    _raise("challenge", schema_errors(challenge, "challenge.schema.json"))


def validate_proposed_correction(correction: Any) -> None:
    _raise("proposed_correction", schema_errors(correction, "challenge.schema.json#/$defs/proposed_correction"))


def interpretation_errors(interpretation: Any) -> list[str]:
    errors = schema_errors(interpretation, "interpretation.schema.json")
    if errors:
        return errors
    words = interpretation["original_words"]

    def draft(where: str, rule: dict) -> None:
        if rule["status"] != "PROPOSED":
            errors.append(f"{where}: the interpreter only produces PROPOSED rules, got {rule['status']}")
        if rule["origin"] == "FICTIONAL_SCENARIO":
            errors.append(f"{where}: the interpreter never emits FICTIONAL_SCENARIO rules")
        if rule["threshold"] is not None:
            if rule["threshold_source"] != "USER_WORDS":
                errors.append(f"{where}: a number is allowed only when the user's own words contained it (threshold_source USER_WORDS)")
            elif rule["threshold_quote"] not in words:
                errors.append(f"{where}: threshold_quote {rule['threshold_quote']!r} is not a verbatim span of original_words")

    for i, rule in enumerate(interpretation["proposed_rules"]):
        draft(f"proposed_rules[{i}]", rule)
    for dup in _duplicates(r["rule_id"] for r in interpretation["proposed_rules"]):
        errors.append(f"proposed_rules: rule_id {dup!r} appears more than once")
    objective_ids = {o["objective_id"] for o in interpretation["objectives"]}
    for i, rule in enumerate(interpretation["proposed_rules"]):
        if rule["objective_id"] is not None and rule["objective_id"] not in objective_ids:
            errors.append(f"proposed_rules[{i}]: objective_id {rule['objective_id']!r} is not in objectives")
    for i, item in enumerate(interpretation["unsupported"]):
        if item["words"] not in words:
            errors.append(f"unsupported[{i}]: words must be a verbatim span of original_words")
    for i, clarification in enumerate(interpretation["clarifications"]):
        errors.extend(_clarification_errors(f"clarifications[{i}]", clarification, words, draft))
    return errors


def _clarification_errors(where: str, clarification: dict, words: Any, draft: Any) -> list[str]:
    errors = []
    if words is not None and clarification["about_words"] not in words:
        errors.append(f"{where}: about_words must be a verbatim span of the original words")
    for dup in _duplicates(o["option_id"] for o in clarification["options"]):
        errors.append(f"{where}: option_id {dup!r} appears more than once")
    for j, option in enumerate(clarification["options"]):
        if not option["supported"] and (option["proposed_rule"] or option["purchase_request"]):
            errors.append(f"{where}.options[{j}]: an unsupported option carries no draft")
        if option["proposed_rule"] and draft is not None:
            draft(f"{where}.options[{j}].proposed_rule", option["proposed_rule"])
    return errors


def validate_interpretation(interpretation: Any) -> None:
    _raise("interpretation", interpretation_errors(interpretation))


def investigation_job_errors(job: Any) -> list[str]:
    errors = schema_errors(job, "investigation_job.schema.json")
    if errors:
        return errors
    if not (job["created_at"] <= job["updated_at"]):
        errors.append("updated_at is before created_at")
    if not (job["created_at"] < job["deadline_at"] <= job["expires_at"]):
        errors.append("expected created_at < deadline_at <= expires_at")
    terminal = job["status"] in ("SUCCEEDED", "FAILED")
    for i, step in enumerate(job["steps"]):
        if step["seq"] != i + 1:
            errors.append(f"steps[{i}]: seq must be {i + 1}, got {step['seq']}")
        if terminal and step["status"] == "RUNNING":
            errors.append(f"steps[{i}]: a terminal job cannot have a RUNNING step")
    result = job["result"]
    known = {e["evidence_id"] for e in result["evidence"]} if result else set()
    if result:
        errors.extend(f"result: {e}" for e in check_result_errors(result))
        if result["preview"]:
            errors.append("result.preview: an investigation never returns a preview")
        if result["policy_version"] != job["policy_version"] or result["policy_id"] != job["policy_id"]:
            errors.append("result policy_id / policy_version differ from the job's")
        if result["persona_id"] != job["persona_id"]:
            errors.append("result.persona_id differs from the job's")
        if job["resolved_request"] != result["purchase_request"]:
            errors.append("resolved_request must equal result.purchase_request")
    portfolio = job.get("portfolio")  # optional member: the exact portfolio the job is checked against (api.md section 2a)
    if portfolio is not None:
        errors.extend(f"portfolio: {e}" for e in portfolio_errors(portfolio))
        if portfolio["persona_id"] != job["persona_id"]:
            errors.append("portfolio.persona_id differs from the job's")
        if result and result["portfolio_id"] != portfolio["portfolio_id"]:
            errors.append("result.portfolio_id differs from the portfolio stored with the job")
    if job["request"]["instrument_id"] is not None and job["resolved_request"] is not None and job["resolved_request"] != job["request"]:
        errors.append("resolved_request: a structured request is authoritative and cannot be altered")
    if terminal:
        for i, step in enumerate(job["steps"]):
            for evidence_id in step["evidence_ids"]:
                if evidence_id not in known:
                    errors.append(f"steps[{i}]: evidence_id {evidence_id!r} is not in result.evidence")
    for dup in _duplicates(s["statement_id"] for s in job["explanation"]):
        errors.append(f"explanation: statement_id {dup!r} appears more than once")
    for i, statement in enumerate(job["explanation"]):
        if statement["rendered_by"] == "MODEL_VALIDATED" and not statement["evidence_ids"]:
            errors.append(f"explanation[{i}]: a MODEL_VALIDATED statement must cite at least one evidence record")
        for evidence_id in statement["evidence_ids"]:
            if evidence_id not in known:
                errors.append(f"explanation[{i}]: evidence_id {evidence_id!r} is not in result.evidence")
    if job["agent"]["mode"] == "DETERMINISTIC_FALLBACK":
        if any(s["rendered_by"] != "TEMPLATE" for s in job["explanation"]):
            errors.append("explanation: DETERMINISTIC_FALLBACK allows TEMPLATE statements only")
        if any(s["initiated_by"] != "SERVER" for s in job["steps"]):
            errors.append("steps: DETERMINISTIC_FALLBACK allows SERVER-initiated steps only")
    if job["clarification"]:
        errors.extend(_clarification_errors("clarification", job["clarification"], job["request"]["original_words"], None))
    if job["challenge"]:
        if job["challenge"]["type"] != "CHANGE_RULE":
            errors.append("challenge: only a CHANGE_RULE challenge creates an investigation")
        if job["challenge"]["investigation_id"] != job["parent_investigation_id"]:
            errors.append("challenge.investigation_id must equal parent_investigation_id")
    for i, correction in enumerate(job["proposed_corrections"]):
        if correction["investigation_id"] != job["id"]:
            errors.append(f"proposed_corrections[{i}]: investigation_id differs from the job id")
        if correction["evidence_id"] not in known:
            errors.append(f"proposed_corrections[{i}]: evidence_id {correction['evidence_id']!r} is not in result.evidence")
    return errors


def validate_investigation_job(job: Any) -> None:
    _raise("investigation_job", investigation_job_errors(job))


def scenario_errors(scenario: Any) -> list[str]:
    errors = schema_errors(scenario, "scenario.schema.json")
    if errors:
        return errors
    errors.extend(f"portfolio: {e}" for e in portfolio_errors(scenario["portfolio"]))
    if scenario["portfolio"]["persona_id"] != scenario["persona"]["persona_id"]:
        errors.append("portfolio.persona_id differs from persona.persona_id")
    objective_ids = {o["objective_id"] for o in scenario["objectives"]}
    for objective in scenario["objectives"]:
        if objective["source"] != "FICTIONAL_SCENARIO":
            errors.append(f"objectives ({objective['objective_id']}): scenario wording must be flagged FICTIONAL_SCENARIO")
    groups = [("scenario_rules", scenario["scenario_rules"])]
    groups += [(f"alternative_rule_sets[{i}].rules", s["rules"]) for i, s in enumerate(scenario["alternative_rule_sets"])]
    all_ids = [r["rule_id"] for _, rules in groups for r in rules]
    for dup in _duplicates(all_ids):
        errors.append(f"rule_id {dup!r} appears more than once in the scenario")
    for name, rules in groups:
        for i, rule in enumerate(rules):
            where = f"{name}[{i}] ({rule['rule_id']})"
            if rule["status"] != "PROPOSED" or rule["origin"] != "FICTIONAL_SCENARIO":
                errors.append(f"{where}: scenario rules are offered as PROPOSED with origin FICTIONAL_SCENARIO")
            if rule["objective_id"] is not None and rule["objective_id"] not in objective_ids:
                errors.append(f"{where}: objective_id {rule['objective_id']!r} is not an objective of the scenario")
    for dup in _duplicates(r["request_id"] for r in scenario["demo_requests"]):
        errors.append(f"demo_requests: request_id {dup!r} appears more than once")
    challenge = scenario["demo_challenge"]
    if challenge:
        errors.extend(f"demo_challenge: {e}" for e in schema_errors({"type": challenge["type"], "payload": challenge["payload"]}, "api.schema.json#/$defs/challenge_request"))
        if challenge["type"] == "CHANGE_RULE" and challenge["payload"].get("rule_id") not in all_ids:
            errors.append("demo_challenge: payload.rule_id is not a rule of the scenario")
    for i, step in enumerate(scenario["demo_steps"]):
        if step["seq"] != i + 1:
            errors.append(f"demo_steps[{i}]: seq must be {i + 1}")
    return errors


def validate_scenario(scenario: Any) -> None:
    _raise("scenario", scenario_errors(scenario))


def validate_error_response(body: Any) -> None:
    _raise("error response", schema_errors(body, "api.schema.json#/$defs/error_response"))


def api_body_errors(schema_ref: str, body: Any) -> list[str]:
    """Shape plus semantics for any API body, chosen by the schema it claims to follow."""
    errors = schema_errors(body, schema_ref)
    if errors:
        return errors
    name = schema_ref.rsplit("/", 1)[-1] if "#" in schema_ref else schema_ref
    if name == "check_result.schema.json":
        return check_result_errors(body)
    if name == "investigation_job.schema.json":
        return investigation_job_errors(body)
    if name == "interpretation.schema.json":
        return interpretation_errors(body)
    if name == "portfolio_response":
        errors = [f"scenario: {e}" for e in scenario_errors(body["scenario"])]
        for position in body["scenario"]["portfolio"]["positions"]:
            if position["instrument_id"] not in body["instruments"]:
                errors.append(f"instruments: position {position['instrument_id']!r} has no registry entry")
        for instrument_id in body["purchasable_instrument_ids"]:
            if instrument_id not in body["instruments"]:
                errors.append(f"purchasable_instrument_ids: {instrument_id!r} has no registry entry")
        return errors
    if name == "confirm_response":
        return [f"policy: {e}" for e in policy_errors(body["policy"])]
    if name == "challenge_response":
        kind = body["challenge"]["type"]
        wanted = {"CORRECT_FACT": {"proposed_correction"}, "CLARIFY_PREFERENCE": {"interpretation"}, "CHANGE_RULE": {"policy", "investigation"}}[kind]
        for member in ("proposed_correction", "interpretation", "policy", "investigation"):
            if (body[member] is not None) != (member in wanted):
                errors.append(f"{member}: must be {'set' if member in wanted else 'null'} for a {kind} challenge")
        if body["policy"]:
            errors.extend(f"policy: {e}" for e in policy_errors(body["policy"]))
        if body["interpretation"]:
            errors.extend(f"interpretation: {e}" for e in interpretation_errors(body["interpretation"]))
        return errors
    return errors


def validate_api_body(schema_ref: str, body: Any) -> None:
    _raise(f"API body ({schema_ref})", api_body_errors(schema_ref, body))


__all__ = [name for name in dir() if name.startswith("validate_") or name.endswith("_errors")] + ["ContractError"]
