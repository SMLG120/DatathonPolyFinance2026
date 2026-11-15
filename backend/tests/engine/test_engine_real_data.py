"""Robert and Mateo on the real processed data.

Skipped when ``data/processed/holdings.json``, ``instruments.json`` or
``market_data.json`` are absent (they are gitignored). The key numbers are
printed even without ``-s``. Assertions cover statuses, validity and internal
consistency only: the data files are rebuilt from live sources, so exact
values are reported, not pinned.
"""

import json

import pytest
from byb_contracts import check_result_errors

from backend import engine
from engine_helpers import PROCESSED, SCENARIOS, all_pass_and_funded, boundary_from_its_evidence, confirm, load, make_policy

REQUIRED = ("holdings.json", "instruments.json", "market_data.json")
pytestmark = pytest.mark.skipif(
    not all((PROCESSED / name).exists() for name in REQUIRED),
    reason="data/processed/{holdings,instruments,market_data}.json are not present (gitignored)",
)
DATA_SOURCES = {"prices": "starter_prices_daily", "fx_usdcad": "starter_fx_usdcad"}


@pytest.fixture(scope="module")
def data():
    controversies = PROCESSED / "controversies.json"
    return {
        "instruments": load(PROCESSED / "instruments.json"),
        "holdings": load(PROCESSED / "holdings.json"),
        "market_data": load(PROCESSED / "market_data.json"),
        "controversies": load(controversies) if controversies.exists() else {"records": []},
    }


def check(data, held, policy, purchase_request):
    result = engine.check_rules(held, policy, purchase_request, data["instruments"], data["holdings"], data["market_data"],
                                data["controversies"], data_sources=DATA_SOURCES)
    assert check_result_errors(result) == []
    assert result["execution"]["status"] == "OK"
    return result


def report(capsys, title, result):
    lines = [f"\n== {title}: headline {result['summary']['headline']}, feasibility {result['feasibility']['status']}, "
             f"cash after {result['feasibility']['cash_after']:.4f}"]
    for entry in result["rule_results"]:
        measured, start = entry["measured"], entry["starting"]["measured"]
        lines.append(
            f"  {entry['rule_id']} limit {entry['limit']}: start {entry['starting']['status']} "
            f"[{start['lower']:.5f}, {start['upper']:.5f}] -> after {entry['status']} [{measured['lower']:.5f}, {measured['upper']:.5f}] "
            f"gap {entry['gap'] if entry['gap'] is None else round(entry['gap'], 5)} causes {entry['unknown_causes']}"
        )
        for subject in entry["breaching_subjects"][:3]:
            lines.append(f"      breaching {subject['subject_id']} [{subject['lower']:.5f}, {subject['upper']:.5f}]")
    scenario = result["scenario"]
    if scenario:
        lines.append(
            f"  2022 replay {scenario['status']}: terminal return {scenario['starting']['scenario_terminal_return']:.5f} -> "
            f"{scenario['proposed']['scenario_terminal_return']:.5f}; max drawdown {scenario['starting']['scenario_max_drawdown']:.5f} "
            f"({scenario['starting']['max_drawdown_date']}) -> {scenario['proposed']['scenario_max_drawdown']:.5f} "
            f"({scenario['proposed']['max_drawdown_date']}); target instrument return {scenario['target_instrument_return']:.5f}"
        )
    for fund in result["data_coverage"]:
        lines.append(f"  coverage {fund['fund_id']}: {fund['status']} {fund['coverage_fraction']:.6f}, sector-labelled {fund['sector_labelled_fraction']:.4f}, "
                     f"uncovered {fund['uncovered_portfolio_weight']:.6f}")
    maximum = result["max_compliant"]
    lines.append(f"  max compliant: {maximum['status']} final {maximum['final_direct_weight']} additional {maximum['additional_purchase']} "
                 f"binding {maximum['binding_constraint']} verified {maximum['verified_by_rerun']}")
    with capsys.disabled():
        print("\n".join(lines))


def by_id(result):
    return {entry["rule_id"]: entry for entry in result["rule_results"]}


def test_robert_nvda_to_25_percent_then_cap_raised_to_30(data, capsys):
    scenario = load(SCENARIOS / "robert.json")
    held = scenario["portfolio"]
    purchase = scenario["demo_requests"][0]["purchase_request"]
    assert (purchase["instrument_id"], purchase["target_direct_weight"]) == ("NVDA", 0.25)
    cap, budget = (confirm(r) for r in scenario["scenario_rules"])
    version_1 = make_policy("robert", scenario["objectives"], [cap, budget], policy_id="pol-robert-real")

    first = check(data, held, version_1, purchase)
    report(capsys, "Robert v1 (issuer cap 0.10, 2022 loss budget 0.10), NVDA to 0.25", first)
    rules = by_id(first)
    cap_result, budget_result = rules["robert-issuer-cap-1"], rules["robert-loss-budget-1"]
    assert cap_result["starting"]["status"] == "PASS" and cap_result["status"] == "FAIL"
    assert [s["subject_id"] for s in cap_result["breaching_subjects"]] == ["NVIDIA"]
    assert budget_result["starting"]["status"] == "PASS" and budget_result["status"] == "FAIL"
    assert first["starting_portfolio_findings"] == [] and first["policy_consistency"]["status"] == "CONSISTENT"
    assert first["summary"]["headline"] == "HAS_FAIL"
    scn = first["scenario"]
    assert scn["status"] == "COMPUTED"
    linear = scn["starting"]["scenario_terminal_return"] + 0.25 * scn["target_instrument_return"]
    assert scn["proposed"]["scenario_terminal_return"] == pytest.approx(linear, abs=1e-12)  # D6 linearity on real prices
    assert all(row["base_fx_age_days"] is None or row["base_fx_age_days"] <= 7 for row in scn["instrument_returns"])

    # Challenge: the cap is raised to 0.30 -> a new policy version; the old rule stays as SUPERSEDED.
    challenge = scenario["demo_challenge"]["payload"]
    assert challenge["new_threshold"] == 0.30
    old_cap = dict(cap, status="SUPERSEDED", superseded_by_rule_id="robert-issuer-cap-2")
    new_cap = dict(cap, rule_id="robert-issuer-cap-2", threshold=0.30, origin="USER_STATED", threshold_source="USER_ENTERED",
                   supersedes_rule_id="robert-issuer-cap-1", original_words=challenge["user_note"])
    version_2 = make_policy("robert", scenario["objectives"], [old_cap, new_cap, budget], version=2, parent_version=1, policy_id="pol-robert-real")
    second = check(data, held, version_2, purchase)
    report(capsys, "Robert v2 (issuer cap raised to 0.30), NVDA to 0.25", second)
    rules = by_id(second)
    assert rules["robert-issuer-cap-2"]["status"] == "PASS" and rules["robert-issuer-cap-2"]["measured"] == cap_result["measured"]
    assert rules["robert-loss-budget-1"]["status"] == "FAIL"  # still evaluated, still reported with loss, budget and gap
    assert rules["robert-loss-budget-1"]["gap"] == pytest.approx(budget_result["gap"], abs=1e-12)
    assert [(e["rule_id"], e["status"]) for e in second["rules_not_evaluated"]] == [("robert-issuer-cap-1", "SUPERSEDED")]
    assert second["policy_consistency"]["status"] == "CONSISTENT" and second["policy_version"] == 2

    for result, policy in ((first, version_1), (second, version_2)):
        maximum = result["max_compliant"]
        if maximum["status"] != "SUPPORTED":
            continue
        final = maximum["final_direct_weight"]
        # The boundary evidence cites every input of the closed form: recomputing from those records alone gives the value.
        records = {record["evidence_id"]: record for record in result["evidence"]}
        final_record, added_record = (records[i] for i in maximum["evidence_ids"])
        assert boundary_from_its_evidence(result) == final == final_record["value"]
        assert set(final_record["derived_from"]) <= set(added_record["derived_from"])
        for dropped in [i for i in final_record["derived_from"] if records[i]["metric_id"] not in ("exposure_lower", "exposure_upper")]:
            with pytest.raises(AssertionError):
                boundary_from_its_evidence(result, [i for i in final_record["derived_from"] if i != dropped])
        assert f"{final:.9f}".rstrip("0") in maximum["reason"] and f"= {final:.9f}".rstrip("0") in final_record["formula"]
        assert all_pass_and_funded(check(data, held, policy, dict(purchase, target_direct_weight=final)))
        assert not all_pass_and_funded(check(data, held, policy, dict(purchase, target_direct_weight=final + 1e-6)))


def test_mateo_spy_to_15_percent(data, capsys):
    scenario = load(SCENARIOS / "mateo.json")
    held = scenario["portfolio"]
    purchase = scenario["demo_requests"][0]["purchase_request"]
    assert (purchase["instrument_id"], purchase["target_direct_weight"]) == ("SPY", 0.15)
    policy = make_policy("mateo", scenario["objectives"], [confirm(r) for r in scenario["scenario_rules"]], policy_id="pol-mateo-real")
    result = check(data, held, policy, purchase)
    report(capsys, "Mateo (Energy-label exclusion 0, controversy exclusion 0), SPY to 0.15", result)
    rules = by_id(result)
    energy = rules["mateo-excl-energy-1"]
    assert energy["starting"]["status"] == "FAIL" and energy["status"] == "FAIL"  # breached before the purchase
    assert "MISSING_HOLDINGS" in energy["unknown_causes"]  # ESGV has no holdings file: unknown, never zero
    assert energy["measured"]["upper"] > energy["measured"]["lower"]
    assert "mateo-excl-energy-1" in [f["rule_id"] for f in result["starting_portfolio_findings"]]
    controversy = rules["mateo-controversy-1"]
    assert controversy["status"] in ("FAIL", "UNKNOWN")  # never PASS while equity weight is unassessed
    assert "REGISTRY_ABSENCE" in controversy["unknown_causes"]
    assert result["max_compliant"]["status"] == "NO_FEASIBLE_PURCHASE"
    statuses = {fund["fund_id"]: fund["status"] for fund in result["data_coverage"]}
    assert statuses["ESGV"] == "MISSING"


def test_real_exposure_does_not_double_count_and_is_deterministic(data):
    registry = data["instruments"]["instruments"]
    for name in ("robert.json", "mateo.json"):
        scenario = load(SCENARIOS / name)
        purchase = scenario["demo_requests"][0]["purchase_request"]
        sim = engine.simulate_change(scenario["portfolio"], purchase, data["instruments"])
        for state in ("starting_portfolio", "proposed_portfolio"):
            exposure = engine.compute_exposure(sim[state], data["instruments"], data["holdings"])
            in_scope = sum(p["weight"] for p in sim[state]["positions"] if registry[p["instrument_id"]]["equity_scope"])
            covered_more_than_all = sum(
                fund["portfolio_weight"] * max(0.0, fund["coverage_fraction"] - 1.0) for fund in exposure["funds"])
            assert sum(exposure["lower"].values()) + exposure["possible_extra"] == pytest.approx(in_scope + covered_more_than_all, abs=1e-9)
        policy = make_policy(scenario["persona"]["persona_id"], scenario["objectives"], [confirm(r) for r in scenario["scenario_rules"]])
        runs = [json.dumps(check(data, scenario["portfolio"], policy, purchase), sort_keys=True) for _ in range(2)]
        assert runs[0] == runs[1]
