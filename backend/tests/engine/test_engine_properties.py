"""Property-style checks: boundaries, no double counting, determinism, purity, validation outcomes."""

import ast
import copy
import json
import sys
from pathlib import Path

import pytest
from byb_contracts import EPS, check_result_errors, compute_content_hash

from backend import engine
from engine_helpers import (
    CASE_IDS, REPO_ROOT, all_pass_and_funded, case, make_policy, portfolio, request, rule, run_case, universe,
)

STEP = 1e-6  # far above EPS = 1e-9, so "just above the boundary" is a real difference
def _expected_maximum(case_id):
    return (case(case_id)["expected"]["max_compliant"] or {}).get("status")


SUPPORTED = [c for c in CASE_IDS if _expected_maximum(c) == "SUPPORTED"]
NO_PURCHASE = [c for c in CASE_IDS if _expected_maximum(c) == "NO_FEASIBLE_PURCHASE"]
WITHHELD_UNKNOWN = ["E05", "E06", "E17", "E19", "E20"]
OK_CASES = [c for c in CASE_IDS if case(c)["expected"]["execution"]["status"] == "OK"]


def funded_targets(result, count=40):
    """Evenly spaced targets in (w0, w0 + cash]: used to CHECK the closed form, never to find it."""
    start, cash = result["feasibility"]["starting_direct_weight"], result["feasibility"]["cash_before"]
    return [start + cash * (k + 1) / count for k in range(count)]


# --------------------------------------------------------------------------- boundary

@pytest.mark.parametrize("case_id", SUPPORTED)
def test_boundary_passes_at_the_boundary_and_not_just_above(case_id):
    result = run_case(case_id)
    maximum = result["max_compliant"]
    assert maximum["status"] == "SUPPORTED" and maximum["verified_by_rerun"] is True
    final = maximum["final_direct_weight"]
    assert final == round(final, 9)
    assert maximum["additional_purchase"] == pytest.approx(final - result["feasibility"]["starting_direct_weight"], abs=1e-12)

    at = run_case(case_id, target=final)
    assert all_pass_and_funded(at)
    assert at["max_compliant"]["final_direct_weight"] == final  # the boundary does not depend on the requested target

    above = run_case(case_id, target=final + STEP)
    assert not all_pass_and_funded(above)
    binding = maximum["binding_constraint"]
    if binding["type"] == "CASH":
        assert above["feasibility"]["status"] == "INSUFFICIENT_CASH"
    else:
        status = {entry["rule_id"]: entry["status"] for entry in above["rule_results"]}
        assert status[binding["rule_id"]] != "PASS"
        earlier = [entry["rule_id"] for entry in above["rule_results"]]
        for rule_id in earlier[: earlier.index(binding["rule_id"])]:
            assert status[rule_id] == "PASS"  # the binding rule is the FIRST one to stop passing


@pytest.mark.parametrize("case_id", SUPPORTED)
def test_no_funded_target_above_the_boundary_passes(case_id):
    result = run_case(case_id)
    final = result["max_compliant"]["final_direct_weight"]
    for target in funded_targets(result):
        if target > final + STEP:
            assert not all_pass_and_funded(run_case(case_id, target=target))


@pytest.mark.parametrize("case_id", NO_PURCHASE)
def test_no_feasible_purchase_means_every_funded_target_fails(case_id):
    result = run_case(case_id)
    maximum = result["max_compliant"]
    assert maximum["status"] == "NO_FEASIBLE_PURCHASE" and maximum["final_direct_weight"] is None
    if maximum["binding_constraint"]["type"] == "CASH":
        assert result["feasibility"]["cash_before"] <= EPS
        return
    for target in funded_targets(result):
        statuses = [entry["status"] for entry in run_case(case_id, target=target)["rule_results"]]
        assert "FAIL" in statuses
    just_above = run_case(case_id, target=result["feasibility"]["starting_direct_weight"] + STEP)
    status = {entry["rule_id"]: entry["status"] for entry in just_above["rule_results"]}
    assert status[maximum["binding_constraint"]["rule_id"]] == "FAIL"


@pytest.mark.parametrize("case_id", WITHHELD_UNKNOWN)
def test_withheld_when_unknown_data_prevents_a_proof(case_id):
    result = run_case(case_id)
    maximum = result["max_compliant"]
    assert maximum["status"] == "WITHHELD" and maximum["final_direct_weight"] is None and maximum["binding_constraint"] is None
    assert maximum["reason"].startswith("Withheld")
    outcomes = [run_case(case_id, target=target) for target in funded_targets(result)]
    assert not any(all_pass_and_funded(outcome) for outcome in outcomes)  # nothing is proven to pass
    assert not all("FAIL" in [e["status"] for e in outcome["rule_results"]] for outcome in outcomes)  # not all proven to fail


def test_max_compliant_amount_matches_check_rules():
    for case_id in ("E01", "E08", "E12", "E21", "R1", "R2", "M1", "E05", "E10"):
        fixture = case(case_id)
        data = universe(fixture["universe"])
        inputs = fixture["inputs"]
        section = engine.max_compliant_amount(
            inputs["portfolio"], inputs["policy"], inputs["purchase_request"],
            data["instruments"], data["holdings"], data["market_data"], data["controversies"],
        )
        full = run_case(case_id)["max_compliant"]
        for key in ("status", "final_direct_weight", "additional_purchase", "binding_constraint", "verified_by_rerun", "reason"):
            assert section[key] == full[key]


def test_boundary_when_buying_reduces_the_loss():
    """A positive-return instrument: the budget is breached BELOW a weight, not above it. Still a closed form."""
    data = universe("robert_synthetic_universe.json")
    fixture = case("R1")
    budget = rule("budget", "scenario_loss_budget", {"scenario_id": "replay_2022"}, 0.06)
    policy = make_policy("robert", [], [budget])
    args = (data["instruments"], data["holdings"], data["market_data"], data["controversies"])
    result = engine.check_rules(fixture["inputs"]["portfolio"], policy, request("JNJ", 0.10), *args)
    assert check_result_errors(result) == []
    entry = result["rule_results"][0]
    assert entry["starting"]["measured"]["lower"] == pytest.approx(0.065)
    assert entry["measured"]["lower"] == pytest.approx(0.065 - 0.05 * 0.04) and entry["status"] == "FAIL"
    # loss(w) = 0.065 - 0.04 (w - 0.05) <= 0.06 needs w >= 0.175; cash allows w <= 0.35.
    maximum = result["max_compliant"]
    assert maximum["status"] == "SUPPORTED" and maximum["final_direct_weight"] == pytest.approx(0.35)
    assert maximum["binding_constraint"] == {"type": "CASH", "rule_id": None}
    assert engine.check_rules(fixture["inputs"]["portfolio"], policy, request("JNJ", 0.175), *args)["rule_results"][0]["status"] == "PASS"
    assert engine.check_rules(fixture["inputs"]["portfolio"], policy, request("JNJ", 0.175 - STEP), *args)["rule_results"][0]["status"] == "FAIL"


def test_out_of_scope_purchase_is_limited_by_cash_only():
    data = universe("synthetic_universe.json")
    policy = make_policy("tester", [], [rule("cap", "max_issuer_exposure", {"issuer_scope": "any"}, 0.25)])
    holdings = portfolio(0.50, {"FUND_A": 0.40, "SYN_A": 0.10})
    result = engine.check_rules(holdings, policy, request("BOND_X", 0.20), data["instruments"], data["holdings"], data["market_data"], data["controversies"])
    assert check_result_errors(result) == []
    entry = result["rule_results"][0]
    assert entry["measured"] == entry["starting"]["measured"]  # a bond fund changes no company exposure
    assert entry["out_of_scope"] == [{"instrument_id": "BOND_X", "weight": 0.2, "reason": entry["out_of_scope"][0]["reason"]}]
    assert result["max_compliant"]["final_direct_weight"] == pytest.approx(0.50)
    assert result["max_compliant"]["binding_constraint"]["type"] == "CASH"


def test_buying_a_fund_uses_the_fund_slope():
    """FUND_A holds ISS_D at 0.40: buying the fund moves ISS_D by 0.40 per unit, and the cap binds there."""
    data = universe("synthetic_universe.json")
    policy = make_policy("tester", [], [rule("cap", "max_issuer_exposure", {"issuer_scope": "any"}, 0.25)])
    holdings = portfolio(0.50, {"FUND_A": 0.40, "SYN_A": 0.10})
    args = (data["instruments"], data["holdings"], data["market_data"], data["controversies"])
    result = engine.check_rules(holdings, policy, request("FUND_A", 0.45), *args)
    # ISS_A: 0.10 + 0.20 w <= 0.25 -> w <= 0.75; ISS_D: 0.40 w <= 0.25 -> w <= 0.625; cash: w <= 0.90.
    assert result["max_compliant"]["final_direct_weight"] == pytest.approx(0.625)
    assert all_pass_and_funded(engine.check_rules(holdings, policy, request("FUND_A", 0.625), *args))
    assert not all_pass_and_funded(engine.check_rules(holdings, policy, request("FUND_A", 0.625 + STEP), *args))


# --------------------------------------------------------------------------- exposure

def states_of(case_id):
    fixture = case(case_id)
    data = universe(fixture["universe"])
    sim = engine.simulate_change(fixture["inputs"]["portfolio"], fixture["inputs"]["purchase_request"], data["instruments"])
    return data, sim


@pytest.mark.parametrize("case_id", OK_CASES)
def test_exposure_never_double_counts(case_id):
    data, sim = states_of(case_id)
    registry = data["instruments"]["instruments"]
    for state in ("starting_portfolio", "proposed_portfolio"):
        held = sim[state]
        exposure = engine.compute_exposure(held, data["instruments"], data["holdings"])
        in_scope = sum(p["weight"] for p in held["positions"] if registry[p["instrument_id"]]["equity_scope"])
        outside = sum(p["weight"] for p in held["positions"] if not registry[p["instrument_id"]]["equity_scope"])
        # Known exposure plus the unattributed part is exactly the in-scope weight: nothing counted twice, nothing dropped.
        assert sum(exposure["lower"].values()) + exposure["possible_extra"] == pytest.approx(in_scope, abs=1e-12)
        assert exposure["in_scope_weight"] == pytest.approx(in_scope, abs=1e-12)
        assert sum(entry["weight"] for entry in exposure["out_of_scope"]) == pytest.approx(outside, abs=1e-12)
        labelled = sum(sum(bucket.values()) for bucket in exposure["sector_exposure"].values())
        assert labelled + exposure["unclassified_weight"] == pytest.approx(sum(exposure["lower"].values()), abs=1e-12)
        assert sum(path["weight"] for path in exposure["paths"]) == pytest.approx(sum(exposure["lower"].values()), abs=1e-12)
        for issuer, lower in exposure["lower"].items():
            assert lower <= in_scope + 1e-12
            assert exposure["upper"][issuer] == pytest.approx(lower + exposure["possible_extra"], abs=1e-12)
            assert lower == pytest.approx(exposure["direct"].get(issuer, 0.0) + sum(exposure["via_fund"].get(issuer, {}).values()), abs=1e-12)
        assert not set(exposure["lower"]) & {i for i, entry in registry.items() if entry["is_fund"]}  # funds are looked through


def test_share_classes_are_aggregated_once():
    data = universe("synthetic_universe.json")
    held = portfolio(0.40, {"FUND_A": 0.40, "SYN_B1": 0.10, "SYN_B2": 0.10})
    exposure = engine.compute_exposure(held, data["instruments"], data["holdings"])
    assert exposure["direct"]["ISS_B"] == pytest.approx(0.20)
    assert exposure["via_fund"]["ISS_B"] == {"FUND_A": pytest.approx(0.06)}
    assert exposure["lower"]["ISS_B"] == pytest.approx(0.26)
    assert "SYN_B1" not in exposure["lower"] and "SYN_B2" not in exposure["lower"]


def test_coverage_is_never_rescaled_and_missing_is_never_zero():
    data = universe("synthetic_universe.json")
    exposure = engine.compute_exposure(portfolio(0.0, {"FUND_B": 0.50, "FUND_C": 0.50}), data["instruments"], data["holdings"])
    assert exposure["lower"]["ISS_A"] == pytest.approx(0.15)  # 0.50 x 0.30, not 0.50 x 0.30 / 0.60
    assert exposure["uncovered_by_fund"] == {"FUND_B": pytest.approx(0.20), "FUND_C": pytest.approx(0.50)}
    assert exposure["possible_extra"] == pytest.approx(0.70)
    assert [fund["status"] for fund in exposure["funds"]] == ["PARTIAL", "MISSING"]


@pytest.mark.parametrize("case_id", OK_CASES)
def test_exposure_is_linear_in_the_purchased_weight(case_id):
    data, sim = states_of(case_id)
    feasibility = sim["feasibility"]
    start = engine.compute_exposure(sim["starting_portfolio"], data["instruments"], data["holdings"])
    after = engine.compute_exposure(sim["proposed_portfolio"], data["instruments"], data["holdings"])
    unit = engine.compute_exposure(
        {"cash_weight": 0.0, "positions": [{"instrument_id": case(case_id)["inputs"]["purchase_request"]["instrument_id"], "weight": 1.0}]},
        data["instruments"], data["holdings"],
    )
    added = feasibility["additional_purchase"]
    for issuer in set(start["lower"]) | set(after["lower"]) | set(unit["lower"]):
        assert after["lower"].get(issuer, 0.0) == pytest.approx(start["lower"].get(issuer, 0.0) + added * unit["lower"].get(issuer, 0.0), abs=1e-12)
    assert after["possible_extra"] == pytest.approx(start["possible_extra"] + added * unit["possible_extra"], abs=1e-12)


# --------------------------------------------------------------------------- scenario replay

@pytest.mark.parametrize("case_id", ["E12", "R1", "R2"])
def test_terminal_return_is_linear_in_the_target_weight(case_id):
    result = run_case(case_id)
    scenario, feasibility = result["scenario"], result["feasibility"]
    expected = scenario["starting"]["scenario_terminal_return"] + feasibility["additional_purchase"] * scenario["target_instrument_return"]
    assert scenario["proposed"]["scenario_terminal_return"] == pytest.approx(expected, abs=1e-12)


def test_replay_period_reports_return_and_drawdown_separately():
    data = universe("synthetic_universe.json")
    held = {"cash_weight": 0.40, "positions": [{"instrument_id": "SYN_A", "weight": 0.40}, {"instrument_id": "SYN_C", "weight": 0.20}]}
    replay = engine.replay_period(held, data["market_data"])
    assert replay["status"] == "COMPUTED" and replay["missing_instruments"] == []
    assert replay["scenario_terminal_return"] == pytest.approx(-0.044)
    assert replay["scenario_max_drawdown"] == pytest.approx(-0.12944)
    assert replay["max_drawdown_date"] == "2022-09-30"
    rows = {row["instrument_id"]: row for row in replay["instrument_returns"]}
    assert rows["SYN_C"]["return_cad"] == pytest.approx(-0.12)
    assert (rows["SYN_C"]["base_fx_date"], rows["SYN_C"]["base_fx_age_days"]) == ("2021-12-30", 1)  # backward-matched FX, age reported
    assert (rows["SYN_A"]["base_price_date"], rows["SYN_A"]["base_price_age_days"]) == ("2021-12-30", 1)
    assert rows["SYN_A"]["base_fx_date"] is None


def test_replay_period_never_substitutes_a_proxy():
    data = universe("synthetic_universe.json")
    stale = engine.replay_period({"cash_weight": 0.8, "positions": [{"instrument_id": "SYN_E", "weight": 0.2}]}, data["market_data"])
    assert stale["status"] == "INSUFFICIENT_HISTORY" and stale["missing_instruments"] == ["SYN_E"]
    assert stale["scenario_terminal_return"] is None and stale["scenario_max_drawdown"] is None
    required = engine.replay_period({"cash_weight": 1.0, "positions": []}, data["market_data"], required_instruments=["SYN_D"])
    assert required["missing_instruments"] == ["SYN_D"]
    all_cash = engine.replay_period({"cash_weight": 1.0, "positions": []}, data["market_data"])
    assert (all_cash["scenario_terminal_return"], all_cash["scenario_max_drawdown"], all_cash["max_drawdown_date"]) == (0.0, 0.0, None)


# --------------------------------------------------------------------------- determinism and purity

@pytest.mark.parametrize("case_id", CASE_IDS)
def test_results_are_identical_on_repeated_runs_and_inputs_are_untouched(case_id):
    fixture = case(case_id)
    data = universe(fixture["universe"])
    inputs = fixture["inputs"]
    before = copy.deepcopy((inputs, data))
    runs = [
        engine.check_rules(inputs["portfolio"], inputs["policy"], inputs["purchase_request"],
                           data["instruments"], data["holdings"], data["market_data"], data["controversies"])
        for _ in range(3)
    ]
    assert (inputs, data) == before
    encoded = [json.dumps(run, sort_keys=True) for run in runs]
    assert encoded[0] == encoded[1] == encoded[2]
    assert encoded[0] == json.dumps(run_case(case_id), sort_keys=True)  # fresh copies of the inputs give the same bytes


def test_engine_imports_only_the_standard_library_and_the_contracts():
    allowed = set(sys.stdlib_module_names) | {"byb_contracts"}
    for path in sorted((REPO_ROOT / "backend" / "engine").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                roots = [] if node.level else [node.module.split(".")[0]]
            else:
                continue
            assert set(roots) <= allowed, f"{path.name} imports {roots}"
            assert not set(roots) & {"os", "io", "pathlib", "socket", "subprocess", "time", "random", "urllib", "http"}, path.name
        source = path.read_text(encoding="utf-8")
        assert "reference_calc" not in source and "open(" not in source and "datetime.now" not in source and "date.today" not in source


def test_single_calculation_version_constant():
    assert isinstance(engine.CALCULATION_VERSION, str) and engine.CALCULATION_VERSION
    result = run_case("R1")
    assert {record["calculation_version"] for record in result["evidence"]} == {engine.CALCULATION_VERSION}


# --------------------------------------------------------------------------- validation outcomes and rule lifecycle

def invalid(result, code):
    assert check_result_errors(result) == []
    assert (result["execution"]["status"], result["execution"]["code"]) == ("INVALID_REQUEST", code)
    assert result["feasibility"] is None and result["rule_results"] == [] and result["max_compliant"] is None
    assert result["policy_consistency"] == {"status": "NOT_ASSESSED", "conflicts": []}
    assert result["summary"]["headline"] == "INVALID_REQUEST"


def test_request_validation_outcomes_in_contract_order():
    invalid(run_case("E01", target=-0.01), "TARGET_NEGATIVE")
    invalid(run_case("E01", target=1.01), "TARGET_ABOVE_ONE")
    invalid(run_case("E01", target=0.05), "TARGET_BELOW_CURRENT_WEIGHT")
    invalid(run_case("E01", instrument_id="NOPE", target=-0.5), "UNSUPPORTED_INSTRUMENT")  # checked before the sign

    fixture = case("E01")
    broken = copy.deepcopy(fixture["inputs"]["portfolio"])
    broken["cash_weight"] = 0.60  # weights no longer add up to 1
    invalid(run_case("E01", portfolio=broken, instrument_id="NOPE"), "INVALID_PORTFOLIO")  # first match wins
    unknown_holding = copy.deepcopy(fixture["inputs"]["portfolio"])
    unknown_holding["positions"][0]["instrument_id"] = "GHOST"
    invalid(run_case("E01", portfolio=unknown_holding), "INVALID_PORTFOLIO")
    tampered = copy.deepcopy(fixture["inputs"]["policy"])
    tampered["rules"][0]["threshold"] = 0.99  # content hash no longer matches
    invalid(run_case("E01", policy=tampered, instrument_id="NOPE"), "INVALID_POLICY")


def test_a_no_op_request_is_valid_and_buys_nothing():
    result = run_case("E01", target=0.10)
    assert result["execution"]["status"] == "OK"
    assert result["feasibility"]["additional_purchase"] == 0.0 and result["feasibility"]["cash_after"] == 0.5
    entry = result["rule_results"][0]
    assert entry["measured"] == entry["starting"]["measured"]


def test_insufficient_cash_is_not_a_rule_failure_or_a_conflict():
    result = run_case("E07")
    assert result["feasibility"]["status"] == "INSUFFICIENT_CASH"
    assert [entry["status"] for entry in result["rule_results"]] == ["PASS"]
    assert result["policy_consistency"]["status"] == "CONSISTENT"
    assert result["summary"]["headline"] == "ALL_PASS" and result["summary"]["feasibility_status"] == "INSUFFICIENT_CASH"


def test_only_confirmed_rules_with_a_number_are_evaluated():
    fixture = case("R1")
    data = universe(fixture["universe"])
    rules = copy.deepcopy(fixture["inputs"]["policy"]["rules"])
    rules[1].update(status="PROPOSED", confirmed_at=None, confirmed_by=None)
    policy = make_policy("robert", fixture["inputs"]["policy"]["objectives"], rules, policy_id="pol-robert-demo")
    result = engine.check_rules(fixture["inputs"]["portfolio"], policy, fixture["inputs"]["purchase_request"],
                                data["instruments"], data["holdings"], data["market_data"], data["controversies"])
    assert check_result_errors(result) == []
    assert [entry["rule_id"] for entry in result["rule_results"]] == ["robert-issuer-cap-1"]
    assert [(entry["rule_id"], entry["status"]) for entry in result["rules_not_evaluated"]] == [("robert-loss-budget-1", "PROPOSED")]
    assert result["scenario"] is None  # no evaluated rule needs the replay
    assert result["max_compliant"]["final_direct_weight"] == pytest.approx(0.086)


def test_preview_evaluates_drafts_and_stores_nothing():
    fixture = case("R1")
    data = universe(fixture["universe"])
    drafts = copy.deepcopy(fixture["inputs"]["policy"]["rules"])
    drafts[0].update(status="PROPOSED", confirmed_at=None, confirmed_by=None, threshold=0.20,
                     origin="USER_STATED", threshold_source="USER_ENTERED")
    policy_before = copy.deepcopy(fixture["inputs"]["policy"])
    result = engine.check_rules(fixture["inputs"]["portfolio"], fixture["inputs"]["policy"], fixture["inputs"]["purchase_request"],
                                data["instruments"], data["holdings"], data["market_data"], data["controversies"], draft_rules=drafts)
    assert check_result_errors(result) == []
    assert result["preview"] is True and result["policy_id"] is None and result["policy_version"] is None
    assert {record["policy_version"] for record in result["evidence"]} == {None}
    assert fixture["inputs"]["policy"] == policy_before
    cap = result["rule_results"][0]
    assert (cap["status"], cap["limit"]) == ("FAIL", 0.20) and cap["gap"] == pytest.approx(0.062)
    assert result["max_compliant"]["final_direct_weight"] == pytest.approx(0.10)
    assert result["max_compliant"]["binding_constraint"] == {"type": "RULE", "rule_id": "robert-loss-budget-1"}
    threshold = next(r for r in result["evidence"] if r["metric_id"] == "rule_threshold" and r["subject"]["id"] == "robert-issuer-cap-1")
    assert threshold["label"] == "ASSUMPTION"  # a draft value, not a confirmed fact


def test_goal_context_never_carries_a_status():
    result = run_case("R1")
    kinds = [entry["context_type"] for entry in result["goal_context"]]
    assert kinds == ["LINKED_RULE_RESULTS", "CONCENTRATION", "SCENARIO_DRAWDOWN"]
    assert all("status" not in entry for entry in result["goal_context"])


def test_market_data_sources_label_price_evidence():
    labelled = run_case("E12", data_sources={"prices": "SYNTHETIC_FIXTURE", "fx_usdcad": "SYNTHETIC_FIXTURE"})
    assert check_result_errors(labelled) == []
    prices = [r for r in labelled["evidence"] if r["metric_id"] in ("price_adj_close", "fx_usdcad")]
    assert prices and all(r["label"] == "FACT" and r["source_ids"] == ["SYNTHETIC_FIXTURE"] for r in prices)
    unlabelled = [r for r in run_case("E12")["evidence"] if r["metric_id"] in ("price_adj_close", "fx_usdcad")]
    assert unlabelled and all(r["label"] == "ASSUMPTION" and r["assumptions"] for r in unlabelled)


def test_an_unexpected_failure_is_reported_as_engine_error():
    fixture = case("E12")
    data = universe(fixture["universe"])
    data["market_data"]["prices"]["SYN_A"]["series"] = "not a series"
    result = engine.check_rules(fixture["inputs"]["portfolio"], fixture["inputs"]["policy"], fixture["inputs"]["purchase_request"],
                                data["instruments"], data["holdings"], data["market_data"], data["controversies"])
    assert (result["execution"]["status"], result["execution"]["code"]) == ("ERROR", "ENGINE_ERROR")
    assert check_result_errors(result) == []
    assert result["summary"]["headline"] == "EXECUTION_ERROR"


def test_weights_that_add_up_within_tolerance_still_give_a_valid_result():
    """cash + positions may equal 1 within 1e-9; shares typed as fractions must not leave [0, 1] because of it."""
    data = universe("synthetic_universe.json")
    policy = make_policy("tester", [], [rule("cap", "max_issuer_exposure", {"issuer_scope": "any"}, 0.25)])
    held = portfolio(0.0, {"SYN_B1": 0.5, "SYN_B2": 0.5000000005})
    result = engine.check_rules(held, policy, request("SYN_B2", 0.5000000005), data["instruments"], data["holdings"], data["market_data"], data["controversies"])
    assert check_result_errors(result) == []
    assert result["rule_results"][0]["status"] == "FAIL"
    assert result["rule_results"][0]["breaching_subjects"][0]["upper"] == 1.0
    assert result["max_compliant"]["binding_constraint"] == {"type": "CASH", "rule_id": None}


def test_callers_errors_are_raised_not_reported():
    from byb_contracts import ContractError
    data = universe("synthetic_universe.json")
    held = portfolio(0.50, {"FUND_A": 0.40, "SYN_A": 0.10})
    args = (data["instruments"], data["holdings"], data["market_data"], data["controversies"])
    with pytest.raises(ContractError):
        engine.check_rules(held, case("E01")["inputs"]["policy"], {"instrument_id": "SYN_A", "target_direct_weight": "a lot", "funding": "CASH", "original_words": None}, *args)
    with pytest.raises(ValueError):
        engine.check_rules(held, None, request("SYN_A", 0.15), *args)
    with pytest.raises(ValueError):
        engine.max_compliant_amount(held, case("E01")["inputs"]["policy"], request("NOPE", 0.15), *args)
