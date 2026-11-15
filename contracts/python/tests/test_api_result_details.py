"""Independent checks of what the API example results add around the hand-calculated core.

The engine fixtures (R1, R2, M1) assert verdicts, bounds, gaps and boundaries.
The API examples also carry chart rows, coverage rows, a concentration context
and evidence records with formulas. They are re-derived here with the plain
reference implementation, and every arithmetic formula is evaluated.
"""

from __future__ import annotations

import ast
import operator
import re

import pytest

import reference_calc as ref
from paths import API, ENGINE, load

TOL = 1e-9
RESULTS = {
    "robert_v1": ("investigation_robert_succeeded", "R1"),
    "robert_v2": ("investigation_robert_after_challenge_succeeded", "R2"),
    "mateo": ("investigation_mateo_succeeded", "M1"),
}
OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}


def close(a, b):
    return abs(a - b) <= TOL


def setup(name):
    fixture_id, case_id = RESULTS[name]
    result = load(API / f"{fixture_id}.json")["response_body"]["result"]
    case = load(ENGINE / f"{case_id}.json")
    universe = load(ENGINE / case["universe"])
    portfolio, request = case["inputs"]["portfolio"], case["inputs"]["purchase_request"]
    start = {p["instrument_id"]: p["weight"] for p in portfolio["positions"]}
    proposed, _, _ = ref.with_target(portfolio, request["instrument_id"], request["target_direct_weight"])
    states = {"starting": ref.look_through(start, universe), "proposed": ref.look_through(proposed, universe)}
    return result, case, universe, states


def arithmetic(expression):
    """Evaluate a formula made only of numbers, + - x / and parentheses. Returns None for anything else."""
    if not re.fullmatch(r"[0-9.+\-x/() ]+", expression):
        return None

    def walk(node):
        if isinstance(node, ast.Expression):
            return walk(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in OPS:
            return OPS[type(node.op)](walk(node.left), walk(node.right))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            return -walk(node.operand)
        raise ValueError(expression)

    return walk(ast.parse(expression.replace("x", "*"), mode="eval"))


@pytest.mark.parametrize("name", sorted(RESULTS))
def test_chart_rows_follow_the_look_through_and_the_selection_rule(name):
    result, case, universe, states = setup(name)
    exposure = result["exposure"]
    for state, lt in states.items():
        assert close(exposure["possible_extra"][state], lt["uncovered"])
    for row in exposure["issuers"]:
        for state, lt in states.items():
            part, issuer = row[state], row["issuer_id"]
            assert close(part["direct"], lt["direct"].get(issuer, 0.0)), (issuer, state)
            paths = {fund: known for (i, fund), known in lt["via"].items() if i == issuer and known > 1e-12}
            assert {p["fund_id"] for p in part["indirect_by_fund"]} == set(paths), (issuer, state)
            for path in part["indirect_by_fund"]:
                assert close(path["known"], paths[path["fund_id"]]), (issuer, state, path["fund_id"])
            assert close(part["lower"], lt["lower"].get(issuer, 0.0))
            assert close(part["upper"], lt["lower"].get(issuer, 0.0) + lt["uncovered"])
    # Selection (SEMANTICS.md section 10): required issuers, then the largest by proposed lower bound, 10 at most,
    # the whole list sorted by proposed lower bound descending, then issuer_id.
    proposed = states["proposed"]["lower"]
    instruments = universe["instruments"]["instruments"]
    bought = instruments[case["inputs"]["purchase_request"]["instrument_id"]]
    required = set()
    if bought["equity_scope"] and not bought["is_fund"]:
        required.add(bought["issuer_id"])
    for rule in case["inputs"]["policy"]["rules"]:
        if rule["status"] != "CONFIRMED":
            continue
        parameters = rule["parameters"]
        if parameters.get("issuer_scope", "any") != "any":
            required.add(parameters["issuer_scope"])
        if "issuer_id" in parameters:
            required.add(parameters["issuer_id"])
        required.update(parameters.get("definition", {}).get("issuer_ids", []))
    for entry in result["rule_results"]:
        required.update(s["subject_id"] for s in entry["breaching_subjects"])
    for finding in result["starting_portfolio_findings"]:
        required.update(s["subject_id"] for s in finding["breaching_subjects"])
    ranked = sorted(proposed, key=lambda issuer: (-round(proposed[issuer], 12), issuer))
    chosen = set(required)
    for issuer in ranked:
        if len(chosen) >= 10:
            break
        chosen.add(issuer)
    expected_order = sorted(chosen, key=lambda issuer: (-round(proposed.get(issuer, 0.0), 12), issuer))
    assert [row["issuer_id"] for row in exposure["issuers"]] == expected_order
    assert len(exposure["issuers"]) <= 10


@pytest.mark.parametrize("name", sorted(RESULTS))
def test_coverage_rows_follow_the_look_through(name):
    result, _case, _universe, states = setup(name)
    computed = {fund: (weight, coverage, labelled, gap, status) for (fund, weight, coverage, labelled, gap, status) in states["proposed"]["coverage"]}
    assert [entry["fund_id"] for entry in result["data_coverage"]] == list(computed), "one row per equity fund of the proposed portfolio, in portfolio order"
    for entry in result["data_coverage"]:
        weight, coverage, labelled, gap, status = computed[entry["fund_id"]]
        assert entry["status"] == status
        assert close(entry["portfolio_weight"], weight) and close(entry["coverage_fraction"], coverage)
        assert close(entry["sector_labelled_fraction"], labelled) and close(entry["uncovered_portfolio_weight"], gap)


@pytest.mark.parametrize("name", sorted(RESULTS))
def test_concentration_context_cites_the_largest_single_company_exposure(name):
    result, _case, _universe, states = setup(name)
    context = [c for c in result["goal_context"] if c["context_type"] == "CONCENTRATION"]
    assert len(context) == 1
    evidence = {e["evidence_id"]: e for e in result["evidence"]}
    cited = [evidence[i] for i in context[0]["evidence_ids"]]
    for state, label in (("starting", "STARTING"), ("proposed", "PROPOSED")):
        lt = states[state]
        issuer = min(lt["lower"], key=lambda i: (-round(lt["lower"][i], 12), i))
        lower = [e for e in cited if e["metric_id"] == "exposure_lower" and e["subject"]["portfolio_state"] == label]
        upper = [e for e in cited if e["metric_id"] == "exposure_upper" and e["subject"]["portfolio_state"] == label]
        assert len(lower) == 1 and len(upper) == 1, f"{name} {state}: one lower and one upper record expected"
        assert lower[0]["subject"]["id"] == issuer and upper[0]["subject"]["id"] == issuer, f"{name} {state}: the largest exposure is {issuer}"
        assert close(lower[0]["value"], lt["lower"][issuer]) and close(upper[0]["value"], lt["lower"][issuer] + lt["uncovered"])


@pytest.mark.parametrize("name", sorted(RESULTS) + ["preview"])
def test_every_arithmetic_formula_in_the_evidence_is_correct(name):
    if name == "preview":
        result = load(API / "check_robert_preview.json")["response_body"]
    else:
        result = load(API / f"{RESULTS[name][0]}.json")["response_body"]["result"]
    checked = 0
    for record in result["evidence"]:
        formula = record["formula"]
        if record["label"] != "CALCULATION" or not formula or "=" not in formula:
            continue
        left, _, right = formula.rpartition("=")
        value = arithmetic(left.strip())
        if value is None:
            continue
        checked += 1
        stated = float(right.strip())
        assert abs(value - stated) <= 1e-9, f"{record['evidence_id']}: {left.strip()} is {value}, the formula says {stated}"
        assert abs(record["value"] - stated) <= 1e-9, f"{record['evidence_id']}: value {record['value']} differs from its formula result {stated}"
    assert checked >= 10, f"only {checked} formulas were arithmetic; the check would be close to vacuous"


def test_the_formula_evaluator_catches_a_wrong_formula():
    assert arithmetic("0.20 x (1 - 0.98)") == pytest.approx(0.004)
    assert arithmetic("0.25 - (0.15 - 0.00)") == pytest.approx(0.10)
    assert arithmetic("sum of the reported constituent weights") is None
    assert abs(arithmetic("0.014 + 0.004 + 0.15") - 0.169) > 1e-9
