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


# --------------------------------------------------------------------------- the engine's own range checks (P0)

from engine_helpers import make_policy, portfolio as make_portfolio, request as make_request, rule as make_rule  # noqa: E402

UNUSABLE = [NAN, INF, -INF, -0.01, -1e-6, 1.5, 100.0, "0.2", None, True, [0.2]]
UNUSABLE_IDS = ["nan", "+inf", "-inf", "-0.01", "-1e-6", "1.5", "100", "string", "null", "bool", "list"]


def synthetic():
    return universe("synthetic_universe.json")


def cap_policy(threshold=0.10):
    return make_policy("tester", [], [make_rule("cap", "max_issuer_exposure", {"issuer_scope": "any"}, threshold)])


def run_synthetic(held, policy=None, purchase=None, data=None, **options):
    data = data or synthetic()
    return engine.check_rules(held, policy or cap_policy(), purchase or make_request("SYN_C", 0.05),
                              data["instruments"], data["holdings"], data["market_data"], data["controversies"], **options)


def accept_everything(monkeypatch):
    """Replace every contract validator the engine calls by one that accepts anything."""
    import backend.engine.check as check_module
    import backend.engine.core as core_module

    for module in (core_module, check_module):
        for name in ("portfolio_errors", "policy_errors", "rule_errors"):
            if hasattr(module, name):
                monkeypatch.setattr(module, name, lambda *args, **kwargs: [])
        if hasattr(module, "validate_purchase_request"):
            monkeypatch.setattr(module, "validate_purchase_request", lambda *args, **kwargs: None)


def test_the_reported_false_pass_a_nan_position_holding_20_percent_of_an_issuer_under_a_10_percent_cap(monkeypatch):
    """Reported defect: the NaN position was dropped ("NaN > 0" is false), the issuer's exposure became 0 and the cap PASSED.

    With a real 0.20 the cap fails. With NaN the request is refused: no PASS, no maximum, no exposure, no dropped position.
    """
    honest = run_synthetic(make_portfolio(0.80, {"SYN_A": 0.20}))
    assert honest["execution"]["status"] == "OK" and honest["rule_results"][0]["status"] == "FAIL"
    assert honest["rule_results"][0]["breaching_subjects"][0]["subject_id"] == "ISS_A"

    for bad in (NAN, INF, -INF):
        held = make_portfolio(0.80, {"SYN_A": bad})
        for independent in (False, True):
            if independent:
                accept_everything(monkeypatch)  # the engine refuses it even if every contract validator says yes
            result = run_synthetic(held)
            assert_no_verdict(result, "INVALID_REQUEST", "INVALID_PORTFOLIO")
            assert "portfolio.positions[0].weight is not a finite number" in result["execution"]["message"]
            assert result["summary"]["headline"] == "INVALID_REQUEST" and "PASS" not in json.dumps(result["summary"])
            simulated = engine.simulate_change(held, make_request("SYN_C", 0.05), synthetic()["instruments"], cap_policy())
            assert simulated["execution"]["code"] == "INVALID_PORTFOLIO" and simulated["starting_portfolio"] is None
            with pytest.raises(ValueError):
                data = synthetic()
                engine.max_compliant_amount(held, cap_policy(), make_request("SYN_C", 0.05), data["instruments"], data["holdings"],
                                            data["market_data"], data["controversies"])
        monkeypatch.undo()


@pytest.mark.parametrize("bad", UNUSABLE, ids=UNUSABLE_IDS)
@pytest.mark.parametrize("field", ["position", "cash"])
def test_an_unusable_portfolio_weight_is_refused_by_the_engine_itself(monkeypatch, field, bad):
    accept_everything(monkeypatch)
    held = make_portfolio(0.80, {"SYN_A": 0.20})
    if field == "position":
        held["positions"][0]["weight"] = bad
    else:
        held["cash_weight"] = bad
    result = run_synthetic(held)
    assert_no_verdict(result, "INVALID_REQUEST", "INVALID_PORTFOLIO")
    where = "portfolio.positions[0].weight" if field == "position" else "portfolio.cash_weight"
    assert where in result["execution"]["message"]


@pytest.mark.parametrize("bad", [b for b in UNUSABLE if b is not None], ids=[i for i in UNUSABLE_IDS if i != "null"])
@pytest.mark.parametrize("draft", [False, True])
def test_an_unusable_threshold_is_refused_by_the_engine_itself(monkeypatch, draft, bad):
    accept_everything(monkeypatch)
    policy = cap_policy()
    rules = [dict(policy["rules"][0], threshold=bad)]
    held = make_portfolio(0.80, {"SYN_A": 0.20})
    result = run_synthetic(held, draft_rules=rules) if draft else run_synthetic(held, policy=dict(policy, rules=rules))
    assert_no_verdict(result, "INVALID_REQUEST", "INVALID_POLICY")
    assert ("draft_rules[0].threshold" if draft else "policy.rules[0].threshold") in result["execution"]["message"]


@pytest.mark.parametrize("bad", [NAN, INF, -INF, "0.05", None, True], ids=["nan", "+inf", "-inf", "string", "null", "bool"])
def test_an_unusable_target_raises_before_anything_is_evaluated(monkeypatch, bad):
    accept_everything(monkeypatch)
    with pytest.raises(byb_contracts.ContractError):
        run_synthetic(make_portfolio(0.80, {"SYN_A": 0.20}), purchase=dict(make_request("SYN_C", 0.05), target_direct_weight=bad))


@pytest.mark.parametrize("target, code", [(-0.01, "TARGET_NEGATIVE"), (1.5, "TARGET_ABOVE_ONE")])
def test_a_target_outside_zero_to_one_is_an_explicit_invalid_request(monkeypatch, target, code):
    accept_everything(monkeypatch)
    assert_no_verdict(run_synthetic(make_portfolio(0.80, {"SYN_A": 0.20}), purchase=make_request("SYN_C", target)), "INVALID_REQUEST", code)


DATA_FIELDS = {
    "row_weight": ([NAN, INF, -INF, -0.01, 1.5, "0.1", None], lambda d, bad: d["holdings"]["funds"]["FUND_A"]["holdings"][0].__setitem__("weight_fraction", bad)),
    "coverage": ([NAN, INF, -INF, -0.1, 1.5, "1.0", None], lambda d, bad: d["holdings"]["funds"]["FUND_A"].__setitem__("coverage_fraction", bad)),
    "price": ([NAN, INF, -INF, -1.0, 0.0, "12.5", None], lambda d, bad: d["market_data"]["prices"]["SYN_A"]["series"][0].__setitem__(1, bad)),
    "fx": ([NAN, INF, -INF, -1.0, 0.0, "1.35", None], lambda d, bad: d["market_data"]["fx_usdcad"][0].__setitem__(1, bad)),
}


@pytest.mark.parametrize("field, index", [(field, i) for field, (values, _) in DATA_FIELDS.items() for i in range(len(values))],
                         ids=[f"{field}={value!r}" for field, (values, _) in DATA_FIELDS.items() for value in values])
def test_unusable_data_values_are_an_explicit_error(monkeypatch, field, index):
    accept_everything(monkeypatch)
    values, change = DATA_FIELDS[field]
    data = synthetic()
    change(data, values[index])
    # A portfolio that holds the fund, so the changed holdings would be used; a scenario rule is not needed for the refusal.
    result = run_synthetic(make_portfolio(0.50, {"FUND_A": 0.30, "SYN_A": 0.20}), data=data)
    assert_no_verdict(result, "ERROR", "ENGINE_ERROR")
    assert "data cannot be trusted" in result["execution"]["message"]
    with pytest.raises(ValueError):
        engine.max_compliant_amount(make_portfolio(0.50, {"FUND_A": 0.30, "SYN_A": 0.20}), cap_policy(), make_request("SYN_C", 0.05),
                                    data["instruments"], data["holdings"], data["market_data"], data["controversies"])


def test_boundary_values_that_are_valid_are_still_accepted():
    """0 and 1 are weights; a null threshold is a draft without a number; rounding may put a coverage slightly above 1."""
    assert run_synthetic(make_portfolio(1.0, {}))["execution"]["status"] == "OK"
    assert guard.portfolio_problems({"cash_weight": 1.0, "positions": [{"instrument_id": "A", "weight": 0}]}) == []  # the guard itself accepts 0
    assert run_synthetic(make_portfolio(0.0, {"SYN_A": 1.0}), purchase=make_request("SYN_A", 1.0))["execution"]["status"] == "OK"
    assert guard.threshold_problems([{"threshold": None}, {"threshold": 0}, {"threshold": 1}, {"threshold": 0.25}], "rules") == []
    assert guard.number_problem(1.005, high=guard.MAX_COVERAGE) is None and guard.number_problem(1.02, high=guard.MAX_COVERAGE) is not None
    assert guard.portfolio_problems({"cash_weight": 0.5, "positions": [{"instrument_id": "A", "weight": 0.5}]}) == []
    assert guard.portfolio_problems("x") and guard.portfolio_problems({"cash_weight": 1.0, "positions": "x"})
