"""Deterministic invariants of a ``check_result`` document. Standard library only.

Used by the acceptance tests (on engine output) and by ``live_check.py`` (on the deployed API's
output), so both assert the same things. Nothing here imports the engine or ``byb_contracts``:
the status, gap, summary and headline rules of ``contracts/SEMANTICS.md`` (sections 1, 5, 6, 9,
10, 11, 13) are restated independently, which makes this a second implementation to compare with.

Every function returns a list of human-readable problems; an empty list means "holds".
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

EPS = 1e-9
MAX_BREACHING_SUBJECTS = 10
MIN_TYPE = ("min_issuer_exposure",)
EXPOSURE_RULE_TYPES = ("max_issuer_exposure", "min_issuer_exposure", "exclusion", "controversy_exclusion")

MATEO_WEIGHTS = {"XBB.TO": 0.25, "XIU.TO": 0.20, "ESGV": 0.15, "MSFT": 0.05, "CNR.TO": 0.05, "FTS.TO": 0.05}
MATEO_CASH = 0.25
MATEO_OBJECTIVE = ("Balanced growth over 8 to 12 years; ESG matters to me; I want to avoid oil and companies "
                   "involved in significant controversies.")
MATEO_REQUEST = ("SPY", 0.15)


def close(a: Any, b: Any, tol: float = EPS) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return abs(a - b) <= tol


# ---------------------------------------------------------------- SEMANTICS sections 1 and 6, restated

def status_from_bounds(rule_type: str, lower: Optional[float], upper: Optional[float], limit: float) -> str:
    if lower is None or upper is None:
        return "UNKNOWN"
    if rule_type in MIN_TYPE:
        if lower >= limit - EPS:
            return "PASS"
        if upper < limit - EPS:
            return "FAIL"
        return "UNKNOWN"
    if upper <= limit + EPS:
        return "PASS"
    if lower > limit + EPS:
        return "FAIL"
    return "UNKNOWN"


def gap_from_bounds(rule_type: str, status: str, lower: Optional[float], upper: Optional[float], limit: float) -> Optional[float]:
    if status == "UNKNOWN" or lower is None or upper is None:
        return None
    if rule_type in MIN_TYPE:
        return limit - upper if status == "FAIL" else limit - lower
    return lower - limit if status == "FAIL" else upper - limit


def headline_of(result: dict) -> str:
    """SEMANTICS section 9, first match wins."""
    execution = result["execution"]["status"]
    if execution == "ERROR":
        return "EXECUTION_ERROR"
    if execution == "INVALID_REQUEST":
        return "INVALID_REQUEST"
    if result["policy_consistency"]["status"] == "PROVEN_CONFLICT":
        return "POLICY_CONFLICT"
    statuses = [entry["status"] for entry in result["rule_results"]]
    if not statuses:
        return "NO_RULES_EVALUATED"
    if "FAIL" in statuses:
        return "HAS_FAIL"
    if "UNKNOWN" in statuses:
        return "NO_FAIL_BUT_UNKNOWN"
    return "ALL_PASS"


# ---------------------------------------------------------------- sections of a result

def _snapshot_problems(where: str, rule_type: str, status: str, measured: Optional[dict], limit: float) -> list[str]:
    problems = []
    if status not in ("PASS", "FAIL", "UNKNOWN"):
        return [f"{where}: status {status!r} is not PASS, FAIL or UNKNOWN"]
    if measured is None:
        if status != "UNKNOWN":
            problems.append(f"{where}: no measured bounds, yet the status is {status}")
        return problems
    lower, upper = measured["lower"], measured["upper"]
    if lower > upper + EPS:
        problems.append(f"{where}: lower {lower} is above upper {upper}")
    wanted = status_from_bounds(rule_type, lower, upper, limit)
    if status != wanted:
        problems.append(f"{where}: status {status} but bounds [{lower}, {upper}] against limit {limit} give {wanted}")
    return problems


def rule_result_problems(result: dict) -> list[str]:
    problems = []
    for entry in result["rule_results"]:
        rule_id, rule_type, limit = entry["rule_id"], entry["rule_type"], entry["limit"]
        where = f"rule_results[{rule_id}]"
        if not isinstance(limit, (int, float)) or isinstance(limit, bool):
            problems.append(f"{where}: evaluated without a numeric limit ({limit!r})")
            continue
        problems += _snapshot_problems(where, rule_type, entry["status"], entry["measured"], limit)
        problems += _snapshot_problems(f"{where}.starting", rule_type, entry["starting"]["status"], entry["starting"]["measured"], limit)
        measured = entry["measured"] or {"lower": None, "upper": None}
        wanted_gap = gap_from_bounds(rule_type, entry["status"], measured["lower"], measured["upper"], limit)
        if not close(entry["gap"], wanted_gap):
            problems.append(f"{where}: gap {entry['gap']} but the bounds give {wanted_gap}")
        if entry["status"] == "UNKNOWN":
            if entry["gap"] is not None:
                problems.append(f"{where}: UNKNOWN with a gap")
            if not entry["unknown_causes"]:
                problems.append(f"{where}: UNKNOWN without any unknown cause")
        subjects = entry["breaching_subjects"]
        if entry["status"] != "FAIL" and subjects:
            problems.append(f"{where}: breaching subjects listed although the status is {entry['status']}")
        if len(subjects) > MAX_BREACHING_SUBJECTS:
            problems.append(f"{where}: more than {MAX_BREACHING_SUBJECTS} breaching subjects")
        order = [(-s["lower"], s["subject_id"]) for s in subjects]
        if order != sorted(order):
            problems.append(f"{where}: breaching subjects are not sorted by lower descending, then subject_id")
        for subject in subjects:
            if subject["lower"] > subject["upper"] + EPS:
                problems.append(f"{where}: breaching subject {subject['subject_id']} has lower above upper")
        if len(set(entry["unknown_causes"])) != len(entry["unknown_causes"]):
            problems.append(f"{where}: duplicate unknown causes")
    return problems


def summary_problems(result: dict) -> list[str]:
    problems = []
    summary, rules = result["summary"], result["rule_results"]
    counts = {name: sum(1 for entry in rules if entry["status"] == name.upper()) for name in ("pass", "fail", "unknown")}
    if summary["counts"] != counts:
        problems.append(f"summary.counts {summary['counts']} but rule_results give {counts}")
    if summary["rules_evaluated"] != len(rules):
        problems.append(f"summary.rules_evaluated {summary['rules_evaluated']} but {len(rules)} rule results")
    if summary["rules_not_evaluated"] != len(result["rules_not_evaluated"]):
        problems.append("summary.rules_not_evaluated does not match the rules_not_evaluated list")
    if summary["starting_portfolio_breaches"] != len(result["starting_portfolio_findings"]):
        problems.append("summary.starting_portfolio_breaches does not match starting_portfolio_findings")
    feasibility = result["feasibility"]["status"] if result["feasibility"] else None
    if summary["feasibility_status"] != feasibility:
        problems.append(f"summary.feasibility_status {summary['feasibility_status']} but feasibility says {feasibility}")
    wanted = headline_of(result)
    if summary["headline"] != wanted:
        problems.append(f"summary.headline {summary['headline']} but section 9 gives {wanted}")
    if summary["headline"] == "ALL_PASS" and (counts["unknown"] or counts["fail"]):
        problems.append("headline ALL_PASS although a rule is UNKNOWN or FAIL")
    evaluated = {entry["rule_id"] for entry in rules}
    skipped = {entry["rule_id"] for entry in result["rules_not_evaluated"]}
    if evaluated & skipped:
        problems.append(f"rules both evaluated and not evaluated: {sorted(evaluated & skipped)}")
    return problems


def feasibility_problems(result: dict) -> list[str]:
    f = result["feasibility"]
    if f is None:
        return ["feasibility is null although execution is OK"]
    problems = []
    if not close(f["additional_purchase"], f["target_direct_weight"] - f["starting_direct_weight"]):
        problems.append("feasibility.additional_purchase is not target - starting direct weight")
    if not close(f["cash_after"], f["cash_before"] - f["additional_purchase"]):
        problems.append("feasibility.cash_after is not cash_before - additional_purchase")
    wanted = "INSUFFICIENT_CASH" if f["cash_after"] < -EPS else "FEASIBLE"
    if f["status"] != wanted:
        problems.append(f"feasibility.status {f['status']} but cash_after {f['cash_after']} gives {wanted}")
    if f["funding"] != "CASH":
        problems.append("feasibility.funding is not CASH")
    return problems


def starting_finding_problems(result: dict) -> list[str]:
    """SEMANTICS section 10: one finding per evaluated rule whose starting status is FAIL, in policy order."""
    problems = []
    rules = {entry["rule_id"]: entry for entry in result["rule_results"]}
    wanted = [entry["rule_id"] for entry in result["rule_results"] if entry["starting"]["status"] == "FAIL"]
    got = [finding["rule_id"] for finding in result["starting_portfolio_findings"]]
    if got != wanted:
        problems.append(f"starting_portfolio_findings are {got}; rules that fail on the starting portfolio are {wanted}")
    for finding in result["starting_portfolio_findings"]:
        entry = rules.get(finding["rule_id"])
        where = f"starting_portfolio_findings[{finding['rule_id']}]"
        if entry is None:
            problems.append(f"{where}: no such evaluated rule")
            continue
        if finding["status"] != "FAIL":
            problems.append(f"{where}: status is {finding['status']}, a finding is a proven starting breach")
        start = entry["starting"]["measured"]
        for bound in ("lower", "upper"):
            if not close(finding["measured"][bound], start[bound]):
                problems.append(f"{where}: measured.{bound} differs from the rule's starting bounds")
            change = finding["purchase_effect"][f"{bound}_change"]
            if not close(change, entry["measured"][bound] - start[bound]):
                problems.append(f"{where}: purchase_effect.{bound}_change {change} is not proposed - starting "
                                f"({entry['measured'][bound]} - {start[bound]})")
        if not close(finding["limit"], entry["limit"]):
            problems.append(f"{where}: limit differs from the rule's limit")
        wanted_gap = gap_from_bounds(entry["rule_type"], "FAIL", start["lower"], start["upper"], entry["limit"])
        if not close(finding["gap"], wanted_gap):
            problems.append(f"{where}: gap {finding['gap']} but the starting bounds give {wanted_gap}")
    return problems


def coverage_problems(result: dict) -> list[str]:
    """SEMANTICS sections 5 and 10: coverage is the plain reported sum, never rescaled; the rest is reported."""
    problems = []
    for row in result["data_coverage"]:
        where = f"data_coverage[{row['fund_id']}]"
        weight, coverage = row["portfolio_weight"], row["coverage_fraction"]
        if not close(row["uncovered_portfolio_weight"], weight * max(0.0, 1.0 - coverage)):
            problems.append(f"{where}: uncovered weight {row['uncovered_portfolio_weight']} is not weight x max(0, 1 - coverage)")
        if row["status"] == "MISSING":
            if coverage != 0 or row["holdings_date"] is not None or row["source_id"] is not None:
                problems.append(f"{where}: MISSING must have coverage 0 and null holdings_date and source_id")
            if row["sector_labelled_fraction"] != 0:
                problems.append(f"{where}: MISSING with a sector-labelled fraction")
        else:
            wanted = "COVERED" if coverage >= 1.0 else "PARTIAL"
            if row["status"] != wanted:
                problems.append(f"{where}: status {row['status']} but coverage {coverage} gives {wanted}")
            if row["holdings_date"] is None or row["source_id"] is None:
                problems.append(f"{where}: a fund with a holdings file must carry its holdings_date and source_id")
        if row["sector_labelled_fraction"] > coverage + EPS:
            problems.append(f"{where}: sector-labelled fraction above the coverage fraction")
    statuses = {row["status"] for row in result["data_coverage"]}
    for entry in result["rule_results"]:
        if entry["rule_type"] not in EXPOSURE_RULE_TYPES:
            continue
        for status, cause in (("MISSING", "MISSING_HOLDINGS"), ("PARTIAL", "PARTIAL_HOLDINGS")):
            if (status in statuses) != (cause in entry["unknown_causes"]):
                problems.append(f"rule_results[{entry['rule_id']}]: cause {cause} does not match the coverage rows ({sorted(statuses)})")
    return problems


def max_compliant_problems(result: dict) -> list[str]:
    """SEMANTICS section 11. No number unless SUPPORTED; unknown data never yields a number."""
    m = result["max_compliant"]
    if m is None:
        return ["max_compliant is null although execution is OK"]
    problems = []
    status, binding = m["status"], m["binding_constraint"]
    numbers = (m["final_direct_weight"], m["additional_purchase"])
    if not m.get("reason"):
        problems.append("max_compliant: no reason text")
    if status == "SUPPORTED":
        if None in numbers:
            problems.append("max_compliant: SUPPORTED without both numbers")
        else:
            w0 = result["feasibility"]["starting_direct_weight"]
            if not close(m["additional_purchase"], m["final_direct_weight"] - w0):
                problems.append("max_compliant: additional_purchase is not final_direct_weight - starting direct weight")
            if m["final_direct_weight"] <= w0 + EPS:
                problems.append("max_compliant: SUPPORTED weight is not above the starting direct weight")
            if m["final_direct_weight"] > w0 + result["feasibility"]["cash_before"] + EPS:
                problems.append("max_compliant: SUPPORTED weight is more than cash can fund")
            if round(m["final_direct_weight"], 9) != m["final_direct_weight"]:
                problems.append("max_compliant: final_direct_weight is not rounded to 9 decimals")
        if m["verified_by_rerun"] is not True:
            problems.append("max_compliant: SUPPORTED but not verified by re-running the evaluator")
        if binding is None:
            problems.append("max_compliant: SUPPORTED without a binding constraint")
    else:
        if numbers != (None, None):
            problems.append(f"max_compliant: status {status} must not carry a number, got {numbers}")
        if m["verified_by_rerun"] is not False:
            problems.append(f"max_compliant: status {status} claims verification by re-run")
    if status == "WITHHELD" and binding is not None:
        problems.append("max_compliant: WITHHELD must have a null binding constraint")
    if status == "NO_FEASIBLE_PURCHASE" and binding is None:
        problems.append("max_compliant: NO_FEASIBLE_PURCHASE needs a binding constraint (a rule or CASH)")
    evaluated = [entry["rule_id"] for entry in result["rule_results"]]
    if binding is not None:
        if binding["type"] == "RULE" and binding["rule_id"] not in evaluated:
            problems.append(f"max_compliant: binding rule {binding['rule_id']!r} is not an evaluated rule")
        if binding["type"] == "CASH" and binding["rule_id"] is not None:
            problems.append("max_compliant: a CASH constraint names a rule")
    conflict = result["policy_consistency"]["status"] == "PROVEN_CONFLICT"
    if (conflict or not evaluated) and status != "WITHHELD":
        problems.append(f"max_compliant: {status} although " + ("a conflict is proven" if conflict else "no rule is evaluated"))
    if not conflict and evaluated:
        if result["feasibility"]["cash_before"] <= EPS:
            if status != "NO_FEASIBLE_PURCHASE" or binding is None or binding["type"] != "CASH":
                problems.append("max_compliant: without cash the answer is NO_FEASIBLE_PURCHASE with constraint CASH")
        else:
            # A cash-funded purchase only adds exposure. A max-type exposure rule whose starting lower bound is
            # already above its limit therefore fails at every target: NO_FEASIBLE_PURCHASE, never a number.
            repairable = ("min_issuer_exposure", "scenario_loss_budget")
            proven = [entry["rule_id"] for entry in result["rule_results"]
                      if entry["starting"]["status"] == "FAIL" and entry["rule_type"] not in repairable]
            if proven:
                if status != "NO_FEASIBLE_PURCHASE":
                    problems.append(f"max_compliant: {status} although {proven} already fail on the starting portfolio and buying cannot repair them")
                elif binding is None or binding["type"] != "RULE":
                    problems.append("max_compliant: the binding constraint must be the failing rule, not CASH")
            if status == "SUPPORTED":
                not_pass_at_start = [entry["rule_id"] for entry in result["rule_results"]
                                     if entry["starting"]["status"] == "UNKNOWN" and entry["rule_type"] not in repairable]
                if not_pass_at_start:
                    problems.append(f"max_compliant: a number is given although {not_pass_at_start} are UNKNOWN before any purchase")
    return problems


def consistency_problems(result: dict) -> list[str]:
    section = result["policy_consistency"]
    problems = []
    if (section["status"] == "PROVEN_CONFLICT") != bool(section["conflicts"]):
        problems.append("policy_consistency: PROVEN_CONFLICT must come with at least one conflict, and only then")
    limits = {entry["rule_id"]: entry for entry in result["rule_results"]}
    for conflict in section["conflicts"]:
        if conflict["conflict_type"] != "MIN_EXCEEDS_MAX_SAME_ISSUER":
            problems.append(f"policy_consistency: unsupported conflict type {conflict['conflict_type']}")
        if not conflict["min_fraction"] > conflict["max_fraction"] + EPS:
            problems.append("policy_consistency: a conflict needs minimum > maximum (equal limits are not a conflict)")
        if any(rule_id not in limits for rule_id in conflict["rule_ids"]):
            problems.append("policy_consistency: a conflict cites a rule that was not evaluated")
    return problems


def exposure_problems(result: dict) -> list[str]:
    exposure = result["exposure"]
    if exposure is None:
        return ["exposure is null although execution is OK"]
    problems = []
    for issuer in exposure["issuers"]:
        for state in ("starting", "proposed"):
            row = issuer[state]
            known = row["direct"] + sum(part["known"] for part in row["indirect_by_fund"])
            if not close(row["lower"], known):
                problems.append(f"exposure[{issuer['issuer_id']}].{state}: lower is not direct + known indirect (double count or omission)")
            if not close(row["upper"], row["lower"] + exposure["possible_extra"][state]):
                problems.append(f"exposure[{issuer['issuer_id']}].{state}: upper is not lower + possible_extra")
    order = [(-issuer["proposed"]["lower"], issuer["issuer_id"]) for issuer in exposure["issuers"]]
    if order != sorted(order):
        problems.append("exposure.issuers are not sorted by proposed lower descending, then issuer_id")
    uncovered = sum(row["uncovered_portfolio_weight"] for row in result["data_coverage"])
    if not close(exposure["possible_extra"]["proposed"], uncovered):
        problems.append(f"exposure.possible_extra.proposed {exposure['possible_extra']['proposed']} is not the sum of the uncovered fund weights {uncovered}")
    listed = {issuer["issuer_id"] for issuer in exposure["issuers"]}
    for entry in result["rule_results"]:
        for subject in entry["breaching_subjects"]:
            if subject["subject_id"] not in listed:
                problems.append(f"exposure: breaching subject {subject['subject_id']} of {entry['rule_id']} is not listed")
    return problems


def cited_evidence_ids(result: dict) -> list[tuple[str, str]]:
    cited = []
    for entry in result["rule_results"]:
        cited += [(f"rule_results[{entry['rule_id']}]", i) for i in entry["evidence_ids"]]
    for finding in result["starting_portfolio_findings"]:
        cited += [(f"starting_portfolio_findings[{finding['rule_id']}]", i) for i in finding["evidence_ids"]]
    for context in result["goal_context"]:
        cited += [(f"goal_context[{context['context_type']}]", i) for i in context["evidence_ids"]]
    if result["max_compliant"]:
        cited += [("max_compliant", i) for i in result["max_compliant"]["evidence_ids"]]
    return cited


def derivation_closure(records: dict, evidence_id: str) -> set:
    """Every record reachable through ``derived_from`` (the record itself included)."""
    seen, stack = set(), [evidence_id]
    while stack:
        current = stack.pop()
        if current in seen or current not in records:
            continue
        seen.add(current)
        stack.extend(records[current]["derived_from"])
    return seen


def evidence_problems(result: dict) -> list[str]:
    """SEMANTICS section 13: ids unique, every citation resolves, the calculation path is closed and acyclic,
    and each record says what its number is about (subject, unit, period, state, sources, versions)."""
    problems = []
    evidence = result["evidence"]
    ids = [record["evidence_id"] for record in evidence]
    if len(set(ids)) != len(ids):
        problems.append("evidence: duplicate evidence_id")
    records = {record["evidence_id"]: record for record in evidence}
    for where, evidence_id in cited_evidence_ids(result):
        if evidence_id not in records:
            problems.append(f"{where}: cites {evidence_id!r}, which is not in evidence[]")
    wanted_version = None if result["preview"] else result["policy_version"]
    for record in evidence:
        where = f"evidence[{record['evidence_id']}]"
        for parent in record["derived_from"]:
            if parent not in records:
                problems.append(f"{where}: derived_from {parent!r} does not exist")
        if record["policy_version"] != wanted_version:
            problems.append(f"{where}: policy_version {record['policy_version']} but the result is for {wanted_version}")
        if record["calculation_version"] != result["calculation_version"]:
            problems.append(f"{where}: calculation_version differs from the result's")
        value, unit = record["value"], record["unit"]
        if unit in ("fraction", "price", "fx_rate", "days", "count"):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                problems.append(f"{where}: unit {unit} with a non-numeric value")
        elif value is not None and not isinstance(value, str):
            problems.append(f"{where}: unit {unit} with a non-text value")
        if record["label"] == "CALCULATION" and not record["formula"]:
            problems.append(f"{where}: CALCULATION without a formula")
        if record["label"] == "FACT" and not record["source_ids"] and record["metric_id"] != "rule_threshold":
            problems.append(f"{where}: FACT without a source id")
        if record["label"] != "CALCULATION" and record["derived_from"]:
            problems.append(f"{where}: only a CALCULATION is derived from other records")
        if record["period"] is None or not record["period"].get("type"):
            problems.append(f"{where}: no period")
    # acyclic: a record must not be reachable from its own parents
    for record in evidence:
        for parent in record["derived_from"]:
            if record["evidence_id"] in derivation_closure(records, parent):
                problems.append(f"evidence[{record['evidence_id']}]: derived_from cycle through {parent}")
                break
    return problems


def _find(records: Iterable[dict], metric: str, state: str, value: float, kind: Optional[str] = None, subject: Optional[str] = None) -> list[dict]:
    return [r for r in records if r["metric_id"] == metric and r["subject"]["portfolio_state"] == state and r["unit"] == "fraction"
            and isinstance(r["value"], (int, float)) and close(r["value"], value)
            and (kind is None or r["subject"]["kind"] == kind) and (subject is None or r["subject"]["id"] == subject)]


def decisive_number_problems(result: dict) -> list[str]:
    """Every decisive number of a rule result is backed by a record the result itself cites, about the right
    metric, unit, portfolio state, date and (for the limit and the gap) the right rule."""
    problems = []
    records = {record["evidence_id"]: record for record in result["evidence"]}
    valuation = result["valuation_date"]

    def backing(where, cited_ids, metric, state, value, kind=None, subject=None):
        cited = [records[i] for i in cited_ids if i in records]
        found = _find(cited, metric, state, value, kind, subject)
        if not found:
            problems.append(f"{where}: no cited record backs {metric} = {value} ({state})")
        for record in found:
            if record["period"] != {"type": "AS_OF", "date": valuation}:
                problems.append(f"{where}: {record['evidence_id']} is not dated as of the valuation date {valuation}")
        return found

    for entry in result["rule_results"]:
        if entry["rule_type"] not in EXPOSURE_RULE_TYPES or entry["measured"] is None:
            continue
        where, rule_id, cited = f"rule_results[{entry['rule_id']}]", entry["rule_id"], entry["evidence_ids"]
        backing(where, cited, "exposure_lower", "PROPOSED", entry["measured"]["lower"])
        backing(where, cited, "exposure_upper", "PROPOSED", entry["measured"]["upper"])
        backing(where, cited, "exposure_lower", "STARTING", entry["starting"]["measured"]["lower"])
        backing(where, cited, "exposure_upper", "STARTING", entry["starting"]["measured"]["upper"])
        backing(where, cited, "rule_threshold", "NOT_APPLICABLE", entry["limit"], "RULE", rule_id)
        if entry["gap"] is not None:
            backing(where, cited, "gap_to_limit", "PROPOSED", entry["gap"], "RULE", rule_id)
        for subject in entry["breaching_subjects"]:
            backing(f"{where}.{subject['subject_id']}", cited, "exposure_lower", "PROPOSED", subject["lower"], "ISSUER", subject["subject_id"])
            backing(f"{where}.{subject['subject_id']}", cited, "exposure_upper", "PROPOSED", subject["upper"], "ISSUER", subject["subject_id"])
    for finding in result["starting_portfolio_findings"]:
        where, rule_id, cited = f"starting_portfolio_findings[{finding['rule_id']}]", finding["rule_id"], finding["evidence_ids"]
        backing(where, cited, "exposure_lower", "STARTING", finding["measured"]["lower"])
        backing(where, cited, "exposure_upper", "STARTING", finding["measured"]["upper"])
        backing(where, cited, "rule_threshold", "NOT_APPLICABLE", finding["limit"], "RULE", rule_id)
        backing(where, cited, "gap_to_limit", "STARTING", finding["gap"], "RULE", rule_id)
        for subject in finding["breaching_subjects"]:
            backing(f"{where}.{subject['subject_id']}", cited, "exposure_lower", "STARTING", subject["lower"], "ISSUER", subject["subject_id"])
            backing(f"{where}.{subject['subject_id']}", cited, "exposure_upper", "STARTING", subject["upper"], "ISSUER", subject["subject_id"])
    return problems


def preview_problems(result: dict) -> list[str]:
    problems = []
    if result["preview"]:
        if result["policy_id"] is not None or result["policy_version"] is not None:
            problems.append("preview: policy_id and policy_version must be null")
    elif result["policy_version"] is None:
        problems.append("stored-policy result without a policy_version")
    return problems


def check_result_problems(result: dict, strict_evidence: bool = True) -> list[str]:
    """All invariants of a result whose execution status is OK.

    ``strict_evidence=False`` skips ``decisive_number_problems`` (each decisive number backed by a record the
    section itself cites). Engine output satisfies it; the hand-written contract fixtures carry a shorter,
    illustrative evidence list and do not (see FINDINGS.md, L1)."""
    if result["execution"]["status"] != "OK":
        problems = [f"execution status is {result['execution']['status']} ({result['execution']['code']})"]
        if result["rule_results"] or result["max_compliant"] is not None or result["exposure"] is not None:
            problems.append("a refused request must evaluate nothing")
        return problems
    problems = []
    for check in (preview_problems, feasibility_problems, consistency_problems, rule_result_problems, summary_problems,
                  starting_finding_problems, coverage_problems, max_compliant_problems, exposure_problems,
                  evidence_problems):
        problems += check(result)
    if strict_evidence:
        problems += decisive_number_problems(result)
    return problems


# ---------------------------------------------------------------- Mateo's demonstration (LEAD_DECISIONS D7)

def mateo_portfolio_problems(portfolio: dict) -> list[str]:
    problems = []
    weights = {p["instrument_id"]: p["weight"] for p in portfolio["positions"]}
    if set(weights) != set(MATEO_WEIGHTS) or any(not close(weights[i], w) for i, w in MATEO_WEIGHTS.items() if i in weights):
        problems.append(f"portfolio positions {weights} are not Mateo's D7 weights {MATEO_WEIGHTS}")
    if not close(portfolio["cash_weight"], MATEO_CASH):
        problems.append(f"cash weight {portfolio['cash_weight']} is not {MATEO_CASH}")
    total = portfolio["cash_weight"] + sum(weights.values())
    if not close(total, 1.0):
        problems.append(f"weights sum to {total}, not 1")
    if portfolio.get("fictional") is not True:
        problems.append("the portfolio is not labelled fictional")
    return problems


def mateo_demo_problems(result: dict, in_scope_equity_weight: Optional[float] = None) -> list[str]:
    """What the frozen documents say Mateo's demonstration shows, whatever the data snapshot
    (LEAD_DECISIONS D7, scenario demo step 5, SEMANTICS sections 6, 10, 11). ``in_scope_equity_weight``
    is the proposed portfolio's equity weight, derived by the caller from the portfolio and the registry."""
    problems = []
    by_type = {}
    for entry in result["rule_results"]:
        by_type.setdefault((entry["rule_type"]), []).append(entry)
    sector = [e for e in by_type.get("exclusion", [])]
    controversy = by_type.get("controversy_exclusion", [])
    if len(sector) != 1 or len(controversy) != 1 or len(result["rule_results"]) != 2:
        return [f"expected exactly one exclusion and one controversy_exclusion result, got {[e['rule_type'] for e in result['rule_results']]}"]
    energy, registry = sector[0], controversy[0]
    added = result["feasibility"]["additional_purchase"]
    findings = {f["rule_id"]: f for f in result["starting_portfolio_findings"]}
    coverage = {row["fund_id"]: row for row in result["data_coverage"]}

    if energy["limit"] != 0 or registry["limit"] != 0:
        problems.append("both of Mateo's rules have a tolerance of 0")
    # Energy label: proven through XIU.TO before any purchase; nothing through ESGV or an unlabelled fund is zero.
    if energy["starting"]["status"] != "FAIL" or energy["status"] != "FAIL":
        problems.append(f"Energy exclusion: expected FAIL before and after (XIU.TO holds Energy-labelled issuers), got "
                        f"{energy['starting']['status']} -> {energy['status']}")
    if not energy["measured"]["lower"] > 0:
        problems.append("Energy exclusion: no proven Energy exposure")
    if "MISSING_HOLDINGS" not in energy["unknown_causes"]:
        problems.append("Energy exclusion: ESGV has no holdings file, MISSING_HOLDINGS must be a cause")
    if not energy["measured"]["upper"] >= energy["measured"]["lower"] + 0.15 - EPS:
        problems.append("Energy exclusion: the upper bound does not include the whole uncovered ESGV weight (missing is not zero)")
    if energy["rule_id"] not in findings:
        problems.append("Energy exclusion: the breach of the starting portfolio is not reported as a starting-portfolio finding")
    else:
        effect = findings[energy["rule_id"]]["purchase_effect"]
        if effect["lower_change"] < -EPS or effect["upper_change"] > added + EPS or effect["upper_change"] < effect["lower_change"] - EPS:
            problems.append(f"Energy exclusion: purchase effect {effect} is outside [0, {added}]")
        spy = coverage.get("SPY")
        if spy and spy["sector_labelled_fraction"] == 0:
            if "UNCLASSIFIED_SECTOR" not in energy["unknown_causes"]:
                problems.append("Energy exclusion: SPY rows carry no sector label, UNCLASSIFIED_SECTOR must be a cause")
            if not close(effect["lower_change"], 0.0) or not close(effect["upper_change"], added):
                problems.append(f"Energy exclusion: with an unlabelled SPY the purchase proves 0 and could add up to {added}; got {effect}")
    # Controversy: absence from the registry is not assessed, never a pass.
    if registry["status"] == "PASS":
        problems.append("controversy exclusion: PASS although equity weight is not assessed")
    if "REGISTRY_ABSENCE" not in registry["unknown_causes"]:
        problems.append("controversy exclusion: REGISTRY_ABSENCE must be a cause")
    if in_scope_equity_weight is not None and not close(registry["measured"]["upper"], in_scope_equity_weight):
        problems.append(f"controversy exclusion: upper bound {registry['measured']['upper']} is not the in-scope equity weight {in_scope_equity_weight}")
    if registry["status"] == "FAIL" and not registry["breaching_subjects"]:
        problems.append("controversy exclusion: FAIL without a flagged issuer")
    # Coverage: ESGV deliberately has no holdings file.
    esgv = coverage.get("ESGV")
    if esgv is None or esgv["status"] != "MISSING" or esgv["holdings_date"] is not None or esgv["source_id"] is not None \
            or not close(esgv["uncovered_portfolio_weight"], 0.15):
        problems.append(f"ESGV coverage row must be MISSING with null date and source and 0.15 uncovered, got {esgv}")
    if any(row["status"] != "MISSING" and row["coverage_fraction"] > 1 + EPS for row in coverage.values()):
        problems.append("a coverage fraction above 1")
    # Whole result.
    maximum = result["max_compliant"]
    if maximum["status"] != "NO_FEASIBLE_PURCHASE" or maximum["binding_constraint"] != {"type": "RULE", "rule_id": energy["rule_id"]}:
        problems.append(f"max_compliant must be NO_FEASIBLE_PURCHASE bound by the Energy exclusion (first failing rule in policy order), got "
                        f"{maximum['status']} / {maximum['binding_constraint']}")
    if result["summary"]["headline"] != "HAS_FAIL":
        problems.append(f"headline {result['summary']['headline']}, expected HAS_FAIL")
    if result["policy_consistency"]["status"] != "CONSISTENT":
        problems.append("Mateo's policy has no supported conflict")
    if result["scenario"] is not None:
        problems.append("no scenario rule exists, so the scenario section must be null")
    if result["feasibility"]["status"] != "FEASIBLE" or not close(result["feasibility"]["cash_after"], 0.10):
        problems.append("SPY to 0.15 leaves cash 0.10 and is feasible")
    return problems
