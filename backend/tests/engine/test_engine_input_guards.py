"""Non-finite numbers and self-contradicting data are refused explicitly; they never produce a verdict.

NaN compares false with everything: without a guard a NaN weight is "not > 0" (the position vanishes) and a
NaN bound is "not above the limit" (the rule passes). Each case below must end as an explicit error with no
rule result and no maximum, and whatever is returned must be strict JSON.
"""

import copy
import json

import byb_contracts
import pytest

from backend import engine
from backend.engine import guard
from engine_helpers import CASE_IDS, case, run_case, universe

NAN, INF = float("nan"), float("inf")
BAD = [NAN, INF, -INF]


def inputs(case_id="R1"):
    fixture = case(case_id)
    return fixture["inputs"], universe(fixture["universe"])


def check(portfolio=None, policy=None, request=None, data=None, case_id="R1", **options):
    base, base_data = inputs(case_id)
    data = data or base_data
    return engine.check_rules(portfolio or base["portfolio"], policy or base["policy"], request or base["purchase_request"],
                              data["instruments"], data["holdings"], data["market_data"], data["controversies"], **options)


def assert_no_verdict(result, status, code):
    byb_contracts.validate_check_result(result)
    json.dumps(result, allow_nan=False)  # strict JSON: raises on NaN or infinity
    assert (result["execution"]["status"], result["execution"]["code"]) == (status, code)
    assert result["rule_results"] == [] and result["max_compliant"] is None and result["feasibility"] is None
    assert result["exposure"] is None and result["evidence"] == [] and result["starting_portfolio_findings"] == []
    assert result["summary"]["headline"] in ("INVALID_REQUEST", "EXECUTION_ERROR")


def test_the_baseline_case_is_a_normal_result():
    result = check()
    assert result["execution"]["status"] == "OK" and result["rule_results"]


@pytest.mark.parametrize("bad", BAD)
def test_non_finite_position_weight_is_an_invalid_portfolio(bad):
    """F-01: before the guard the position was dropped and the remaining portfolio could PASS with a SUPPORTED maximum."""
    base, _ = inputs()
    for index in range(len(base["portfolio"]["positions"])):
        portfolio = copy.deepcopy(base["portfolio"])
        portfolio["positions"][index]["weight"] = bad
        result = check(portfolio=portfolio)
        assert_no_verdict(result, "INVALID_REQUEST", "INVALID_PORTFOLIO")
        assert "not a finite number" in result["execution"]["message"] and f"positions[{index}].weight" in result["execution"]["message"]


@pytest.mark.parametrize("bad", BAD)
def test_non_finite_cash_weight_is_an_invalid_portfolio(bad):
    base, _ = inputs()
    portfolio = dict(copy.deepcopy(base["portfolio"]), cash_weight=bad)
    assert_no_verdict(check(portfolio=portfolio), "INVALID_REQUEST", "INVALID_PORTFOLIO")
    simulated = engine.simulate_change(portfolio, base["purchase_request"], inputs()[1]["instruments"], base["policy"])
    assert simulated["execution"]["code"] == "INVALID_PORTFOLIO" and simulated["proposed_portfolio"] is None


@pytest.mark.parametrize("bad", BAD)
def test_non_finite_target_is_refused_before_anything_is_evaluated(bad):
    base, data = inputs()
    request = dict(base["purchase_request"], target_direct_weight=bad)
    with pytest.raises(byb_contracts.ContractError):
        check(request=request)
    with pytest.raises(byb_contracts.ContractError):
        engine.simulate_change(base["portfolio"], request, data["instruments"], base["policy"])
    with pytest.raises(ValueError):
        engine.max_compliant_amount(base["portfolio"], base["policy"], request, data["instruments"], data["holdings"], data["market_data"], data["controversies"])


@pytest.mark.parametrize("bad", BAD)
def test_non_finite_threshold_is_an_invalid_policy(bad):
    base, _ = inputs()
    policy = copy.deepcopy(base["policy"])
    policy["rules"][0]["threshold"] = bad
    assert_no_verdict(check(policy=policy), "INVALID_REQUEST", "INVALID_POLICY")
    drafts = copy.deepcopy(base["policy"]["rules"])
    drafts[-1]["threshold"] = bad
    result = check(draft_rules=drafts)
    assert_no_verdict(result, "INVALID_REQUEST", "INVALID_POLICY")
    assert result["preview"] is True and "draft_rules" in result["execution"]["message"]


def _first_price(data):
    instrument_id = sorted(data["market_data"]["prices"])[0]
    return data["market_data"]["prices"][instrument_id]["series"]


@pytest.mark.parametrize("bad", BAD)
@pytest.mark.parametrize("where", ["price", "fx", "row_weight", "coverage", "instrument"])
def test_non_finite_data_is_an_explicit_error_not_a_result(where, bad):
    """F-05/F-06: a NaN price used to put NaN into the result; a NaN weight used to vanish from the exposure."""
    base, data = inputs()
    fund = data["holdings"]["funds"][sorted(data["holdings"]["funds"])[0]]
    if where == "price":
        for point in _first_price(data):
            point[1] = bad
    elif where == "fx":
        data["market_data"]["fx_usdcad"][0][1] = bad
    elif where == "row_weight":
        fund["holdings"][0]["weight_fraction"] = bad
    elif where == "coverage":
        fund["coverage_fraction"] = bad
    else:
        data["instruments"]["instruments"][base["purchase_request"]["instrument_id"]]["extra_number"] = bad
    result = check(data=data)
    assert_no_verdict(result, "ERROR", "ENGINE_ERROR")
    assert "data cannot be trusted" in result["execution"]["message"] and "nan" not in result["execution"]["message"].lower().replace("finite", "")
    with pytest.raises(ValueError):
        engine.max_compliant_amount(base["portfolio"], base["policy"], base["purchase_request"], data["instruments"], data["holdings"],
                                    data["market_data"], data["controversies"])


def test_declared_coverage_above_the_reported_rows_is_refused():
    """F-07: rows summing to 0.30 with a declared coverage of 1.0 used to give PASS / COVERED / SUPPORTED."""
    base, data = inputs()
    for fund in data["holdings"]["funds"].values():
        fund["holdings"] = fund["holdings"][:1]
        fund["holdings"][0]["weight_fraction"] = 0.30
        fund["n_holdings"] = 1
        fund["coverage_fraction"] = 1.0
    result = check(data=data)
    assert_no_verdict(result, "ERROR", "ENGINE_ERROR")
    assert "coverage_fraction differs from the sum of its reported rows" in result["execution"]["message"]
    # The same rows with the coverage they really add up to are accepted, and the rest of the fund is unknown, not zero.
    for fund in data["holdings"]["funds"].values():
        fund["coverage_fraction"] = 0.30
    honest = check(data=data)
    assert honest["execution"]["status"] == "OK"
    assert all(entry["status"] == "PARTIAL" and entry["uncovered_portfolio_weight"] > 0 for entry in honest["data_coverage"])


@pytest.mark.parametrize("issuer", ["", "   ", None])
def test_a_row_or_an_instrument_without_an_issuer_is_refused(issuer):
    """F-07: an empty issuer_id used to be counted as a company of its own."""
    base, data = inputs()
    fund_id = sorted(data["holdings"]["funds"])[0]
    data["holdings"]["funds"][fund_id]["holdings"][0]["issuer_id"] = issuer
    result = check(data=data)
    assert_no_verdict(result, "ERROR", "ENGINE_ERROR")
    assert f"holdings.funds.{fund_id}.holdings[0] has no issuer_id" in result["execution"]["message"]
    base, data = inputs()
    held = base["portfolio"]["positions"][0]["instrument_id"]
    data["instruments"]["instruments"][held]["issuer_id"] = issuer
    result = check(data=data)
    assert_no_verdict(result, "ERROR", "ENGINE_ERROR")
    assert f"instruments.{held} has no issuer_id" in result["execution"]["message"]


def test_a_negative_row_weight_is_refused():
    _, data = inputs()
    fund = data["holdings"]["funds"][sorted(data["holdings"]["funds"])[0]]
    fund["holdings"][0]["weight_fraction"] = -0.01
    assert_no_verdict(check(data=data), "ERROR", "ENGINE_ERROR")


def test_an_unexpected_failure_is_reported_without_exception_text(monkeypatch):
    """F-14: the message is fixed text; class names, paths and exception messages stay out of the result."""
    import backend.engine.check as module

    def explode(*args, **kwargs):
        raise RuntimeError("secret internal detail /var/task/backend/engine/core.py line 42")

    monkeypatch.setattr(module, "analyse", explode)
    result = check()
    assert_no_verdict(result, "ERROR", "ENGINE_ERROR")
    message = result["execution"]["message"]
    assert message == "The check could not be completed because of an internal error. Nothing was calculated."
    for leaked in ("secret", "RuntimeError", "/var/task", "line 42", "Traceback"):
        assert leaked not in json.dumps(result)


def test_a_non_finite_computed_value_never_leaves_the_engine(monkeypatch):
    import backend.engine.check as module

    real = module._build

    def poisoned(*args, **kwargs):
        result = real(*args, **kwargs)
        result["rule_results"][0]["gap"] = NAN
        return result

    monkeypatch.setattr(module, "_build", poisoned)
    assert_no_verdict(check(), "ERROR", "ENGINE_ERROR")


def test_non_finite_paths_reports_where_and_is_bounded():
    document = {"a": [1.0, NAN, {"b": INF}], "c": -INF, "d": True, "e": 10**400, "f": "nan", "g": None}
    assert guard.non_finite_paths(document, "doc", 10) == ["doc.a[1]", "doc.a[2].b", "doc.c"]
    assert len(guard.non_finite_paths(document, "doc", 2)) == 2
    assert guard.non_finite_paths({"a": 1, "b": 0.5, "c": [0.0, -0.0]}, "doc") == []


@pytest.mark.parametrize("case_id", CASE_IDS)
def test_every_fixture_result_is_strict_json_and_its_data_is_accepted(case_id):
    result = run_case(case_id)
    json.dumps(result, allow_nan=False)
    data = universe(case(case_id)["universe"])
    assert guard.data_problems(data["instruments"], data["holdings"], data["market_data"], data["controversies"]) == []
