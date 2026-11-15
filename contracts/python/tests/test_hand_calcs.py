"""Re-derive every expected number in contracts/fixtures/engine independently of how it was typed in.

One test per engine fixture. The reference derivation is in reference_calc.py
(plain loops plus a brute-force boundary scan). A mismatch means the fixture or
HAND_CALCS.md is wrong; it is never resolved by loosening this test.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import reference_calc as ref

ENGINE = Path(__file__).resolve().parents[2] / "fixtures" / "engine"
TOL = 1e-9
CASES = sorted(p for p in ENGINE.glob("*.json") if "universe" not in p.name)


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def close(a, b):
    return abs(a - b) <= TOL


def assert_bounds(label, expected, computed):
    if expected is None:
        assert computed is None, f"{label}: expected no measurement, computed {computed}"
        return
    assert computed is not None, f"{label}: expected {expected}, computed nothing"
    assert close(expected["lower"], computed[0]) and close(expected["upper"], computed[1]), f"{label}: expected {expected}, computed {computed}"


def assert_subjects(label, expected, computed):
    got = {i: (lo, up) for (i, lo, up) in computed}
    want = {s["subject_id"]: (s["lower"], s["upper"]) for s in expected}
    assert set(got) == set(want), f"{label}: breaching subjects expected {sorted(want)}, computed {sorted(got)}"
    for issuer, (lo, up) in want.items():
        assert close(lo, got[issuer][0]) and close(up, got[issuer][1]), f"{label} {issuer}: expected {(lo, up)}, computed {got[issuer]}"


def gap_for(rule_type, status, measured, limit):
    if status == "UNKNOWN" or measured is None:
        return None
    lower, upper = measured
    if rule_type == "min_issuer_exposure":
        return limit - upper if status == "FAIL" else limit - lower
    return lower - limit if status == "FAIL" else upper - limit


@pytest.mark.parametrize("path", CASES, ids=[p.stem for p in CASES])
def test_expected_numbers_are_rederived(path):
    case = load(path)
    check_case(case, load(ENGINE / case["universe"]))


# (fixture, path into `expected`, wrong value): each must make the re-derivation fail.
MUTATIONS = [
    ("E01", ("rule_results", 0, "measured", "lower"), 0.24),
    ("E02", ("rule_results", 0, "status"), "FAIL"),
    ("E03", ("rule_results", 0, "gap"), 0.02),
    ("E04", ("max_compliant", "final_direct_weight"), 0.19),
    ("E05", ("rule_results", 0, "status"), "PASS"),
    ("E05", ("max_compliant", "status"), "NO_FEASIBLE_PURCHASE"),
    ("E06", ("rule_results", 1, "status"), "PASS"),
    ("E07", ("feasibility", "status"), "FEASIBLE"),
    ("E07", ("max_compliant", "binding_constraint"), {"type": "RULE", "rule_id": "e07-cap"}),
    ("E09", ("max_compliant", "status"), "WITHHELD"),
    ("E10", ("policy_consistency", "status"), "CONSISTENT"),
    ("E12", ("scenario", "proposed", "scenario_terminal_return"), -0.05),
    ("E12", ("scenario", "starting", "scenario_max_drawdown"), -0.1152),
    ("E12", ("scenario", "instrument_returns", 1, "base_fx_age_days"), 0),
    ("E15", ("starting_portfolio_findings", 0, "purchase_effect", "upper_change"), 0.05),
    ("E17", ("rule_results", 0, "status"), "PASS"),
    ("E18", ("summary", "headline"), "ALL_PASS"),
    ("R1", ("max_compliant", "final_direct_weight"), 0.088),
    ("R2", ("rule_results", 1, "gap"), 0.05),
    ("M1", ("rule_results", 1, "status"), "PASS"),
    ("E19", ("rule_results", 0, "status"), "PASS"),
    ("E19", ("rule_results", 0, "starting", "status"), "PASS"),
    ("E19", ("scenario", "missing_instruments"), []),
    ("E20", ("scenario", "status"), "COMPUTED"),
    ("E20", ("scenario", "target_instrument_return"), None),
    ("E20", ("max_compliant", "status"), "NO_FEASIBLE_PURCHASE"),
    ("E21", ("max_compliant", "binding_constraint"), {"type": "RULE", "rule_id": "e21-cap"}),
    ("E21", ("feasibility", "status"), "FEASIBLE"),
    ("E22", ("max_compliant", "final_direct_weight"), 0.12),
    ("E22", ("rule_results", 0, "gap"), -0.01),
]


@pytest.mark.parametrize("fixture_id,where,wrong", MUTATIONS, ids=[f"{m[0]}:{'.'.join(map(str, m[1]))}" for m in MUTATIONS])
def test_a_wrong_expected_value_is_caught(fixture_id, where, wrong):
    case = load(ENGINE / f"{fixture_id}.json")
    node = case["expected"]
    for key in where[:-1]:
        node = node[key]
    assert node[where[-1]] != wrong
    node[where[-1]] = wrong
    with pytest.raises(AssertionError):
        check_case(case, load(ENGINE / case["universe"]))


def check_case(case, universe):
    expected = case["expected"]
    portfolio, policy, request = case["inputs"]["portfolio"], case["inputs"]["policy"], case["inputs"]["purchase_request"]
    instruments = universe["instruments"]["instruments"]
    start_positions = {p["instrument_id"]: p["weight"] for p in portfolio["positions"]}
    start_weight = start_positions.get(request["instrument_id"], 0.0)
    target = request["target_direct_weight"]

    # ---- execution (LEAD_DECISIONS D5)
    code = None
    if request["instrument_id"] not in instruments:
        code = "UNSUPPORTED_INSTRUMENT"
    elif target < 0:
        code = "TARGET_NEGATIVE"
    elif target > 1 + ref.EPS:
        code = "TARGET_ABOVE_ONE"
    elif target < start_weight - ref.EPS:
        code = "TARGET_BELOW_CURRENT_WEIGHT"
    assert expected["execution"]["code"] == code
    assert expected["execution"]["status"] == ("OK" if code is None else "INVALID_REQUEST")
    if code is not None:
        assert expected["summary"]["headline"] == "INVALID_REQUEST"
        assert expected["rule_results"] == [] and expected["feasibility"] is None and expected["max_compliant"] is None
        return

    # ---- feasibility
    positions, _, cash_after = ref.with_target(portfolio, request["instrument_id"], target)
    feasibility = expected["feasibility"]
    assert close(feasibility["starting_direct_weight"], start_weight)
    assert close(feasibility["additional_purchase"], target - start_weight)
    assert close(feasibility["cash_before"], portfolio["cash_weight"])
    assert close(feasibility["cash_after"], cash_after)
    assert feasibility["status"] == ("INSUFFICIENT_CASH" if cash_after < -ref.EPS else "FEASIBLE")

    # ---- per rule, proposed and starting portfolio
    rules = ref.evaluated_rules(policy)
    assert [r["rule_id"] for r in expected["rule_results"]] == [r["rule_id"] for r in rules]
    statuses, start_fail = [], []
    for rule, want in zip(rules, expected["rule_results"]):
        label = f"{case['fixture_id']} {rule['rule_id']}"
        now = ref.evaluate_rule(rule, positions, universe)
        before = ref.evaluate_rule(rule, start_positions, universe, required=list(positions))  # one replay universe per check
        assert want["status"] == now["status"], f"{label}: expected {want['status']}, computed {now['status']} from {now['measured']}"
        assert_bounds(label, want["measured"], now["measured"])
        assert want["starting"]["status"] == before["status"], f"{label} starting: expected {want['starting']['status']}, computed {before['status']}"
        assert_bounds(label + " starting", want["starting"]["measured"], before["measured"])
        assert close(want["limit"], rule["threshold"])
        gap = gap_for(rule["rule_type"], now["status"], now["measured"], rule["threshold"])
        assert (want["gap"] is None) == (gap is None) and (gap is None or close(want["gap"], gap)), f"{label}: gap expected {want['gap']}, computed {gap}"
        assert_subjects(label, want["breaching_subjects"], now["breaching"])
        assert set(want["unknown_causes"]) == now["causes"], f"{label}: causes expected {want['unknown_causes']}, computed {sorted(now['causes'])}"
        if "out_of_scope" in want:
            computed_out = [] if rule["rule_type"] == "scenario_loss_budget" else sorted(now["lt"]["out_of_scope"])
            assert sorted((o["instrument_id"], o["weight"]) for o in want["out_of_scope"]) == computed_out
        statuses.append(now["status"])
        if before["status"] == "FAIL":
            start_fail.append((rule, before, now))

    # ---- starting portfolio findings
    assert [f["rule_id"] for f in expected["starting_portfolio_findings"]] == [r["rule_id"] for r, _, _ in start_fail]
    for want, (rule, before, now) in zip(expected["starting_portfolio_findings"], start_fail):
        label = f"{case['fixture_id']} finding {rule['rule_id']}"
        assert_bounds(label, want["measured"], before["measured"])
        assert close(want["gap"], gap_for(rule["rule_type"], "FAIL", before["measured"], rule["threshold"]))
        assert_subjects(label, want["breaching_subjects"], before["breaching"])
        assert close(want["purchase_effect"]["lower_change"], now["measured"][0] - before["measured"][0])
        assert close(want["purchase_effect"]["upper_change"], now["measured"][1] - before["measured"][1])

    # ---- rules not evaluated
    if "rules_not_evaluated" in expected:
        skipped = [(r["rule_id"], r["status"]) for r in policy["rules"] if r not in rules]
        assert [(e["rule_id"], e["status"]) for e in expected["rules_not_evaluated"]] == skipped

    # ---- policy consistency (min above max for the same issuer)
    conflicts = []
    for low in rules:
        for high in rules:
            if low["rule_type"] == "min_issuer_exposure" and high["rule_type"] == "max_issuer_exposure":
                scope = high["parameters"]["issuer_scope"]
                if scope in ("any", low["parameters"]["issuer_id"]) and low["threshold"] > high["threshold"] + ref.EPS:
                    conflicts.append([low["rule_id"], high["rule_id"]])
    assert [c["rule_ids"] for c in expected["policy_consistency"]["conflicts"]] == conflicts
    assert expected["policy_consistency"]["status"] == ("PROVEN_CONFLICT" if conflicts else "CONSISTENT")

    # ---- data coverage
    if "data_coverage" in expected:
        computed = {f: (w, c, lab, gap, status) for (f, w, c, lab, gap, status) in ref.look_through(positions, universe)["coverage"]}
        assert {e["fund_id"] for e in expected["data_coverage"]} == set(computed)
        for entry in expected["data_coverage"]:
            w, c, lab, gap, status = computed[entry["fund_id"]]
            assert entry["status"] == status
            for name, value in (("portfolio_weight", w), ("coverage_fraction", c), ("sector_labelled_fraction", lab), ("uncovered_portfolio_weight", gap)):
                assert close(entry[name], value), f"{entry['fund_id']} {name}: expected {entry[name]}, computed {value}"

    # ---- exposure chart rows
    if "exposure" in expected:
        for state, pos in (("starting", start_positions), ("proposed", positions)):
            lt = ref.look_through(pos, universe)
            assert close(expected["exposure"]["possible_extra"][state], lt["uncovered"])
            for row in expected["exposure"]["issuers"]:
                part, issuer = row[state], row["issuer_id"]
                assert close(part["direct"], lt["direct"].get(issuer, 0.0))
                for path_row in part["indirect_by_fund"]:
                    assert close(path_row["known"], lt["via"][(issuer, path_row["fund_id"])])
                assert close(part["lower"], lt["lower"].get(issuer, 0.0))
                assert close(part["upper"], lt["lower"].get(issuer, 0.0) + lt["uncovered"])

    # ---- scenario replay
    scenario_rules = [r for r in rules if r["rule_type"] == "scenario_loss_budget"]
    if "scenario" in expected:
        assert (expected["scenario"] is not None) == bool(scenario_rules)
    if scenario_rules and expected.get("scenario"):
        want = expected["scenario"]
        assert (want["base_date"], want["end_date"]) == ref.SCENARIO[want["scenario_id"]]
        proposed_replay = ref.replay(positions, universe, want["scenario_id"])
        rows = {r["instrument_id"]: r for r in proposed_replay["rows"]}
        assert sorted(want["missing_instruments"]) == sorted(proposed_replay["missing"]), f"missing instruments: computed {proposed_replay['missing']}"
        assert sorted(r["instrument_id"] for r in want["instrument_returns"]) == sorted(rows), "one row per instrument with usable history"
        for row in want["instrument_returns"]:
            got = rows[row["instrument_id"]]
            for key, value in row.items():
                if key == "return_cad":
                    assert close(value, got[key]), f"{row['instrument_id']} return: expected {value}, computed {got[key]}"
                else:
                    assert value == got[key], f"{row['instrument_id']} {key}: expected {value}, computed {got[key]}"
        target_row = rows.get(request["instrument_id"])
        if target_row is None:
            assert want["target_instrument_return"] is None
        else:
            assert want["target_instrument_return"] is not None and close(want["target_instrument_return"], target_row["return_cad"])
        if proposed_replay["missing"]:
            assert want["status"] == "INSUFFICIENT_HISTORY", "an instrument without usable history makes the whole replay unknown"
            assert want["starting"] is None and want["proposed"] is None
        else:
            assert want["status"] == "COMPUTED"
            for state, pos in (("starting", start_positions), ("proposed", positions)):
                got = ref.replay(pos, universe, want["scenario_id"], required=list(positions))
                assert close(want[state]["scenario_terminal_return"], got["terminal"]), f"{state} terminal: expected {want[state]['scenario_terminal_return']}, computed {got['terminal']}"
                assert close(want[state]["scenario_max_drawdown"], got["drawdown"]), f"{state} drawdown: expected {want[state]['scenario_max_drawdown']}, computed {got['drawdown']}"
                assert want[state]["max_drawdown_date"] == got["drawdown_date"]
            # D6 linearity: R(w) = R(w0) + (w - w0) x r_instrument
            start_r = ref.replay(start_positions, universe, want["scenario_id"], required=list(positions))["terminal"]
            assert close(want["proposed"]["scenario_terminal_return"], start_r + (target - start_weight) * want["target_instrument_return"])

    # ---- summary (derived, contracts/SEMANTICS.md section 9)
    summary = expected["summary"]
    if conflicts:
        headline = "POLICY_CONFLICT"
    elif not statuses:
        headline = "NO_RULES_EVALUATED"
    elif "FAIL" in statuses:
        headline = "HAS_FAIL"
    elif "UNKNOWN" in statuses:
        headline = "NO_FAIL_BUT_UNKNOWN"
    else:
        headline = "ALL_PASS"
    assert summary["headline"] == headline
    assert summary["counts"] == {"pass": statuses.count("PASS"), "fail": statuses.count("FAIL"), "unknown": statuses.count("UNKNOWN")}
    assert summary["rules_evaluated"] == len(statuses)
    assert summary["rules_not_evaluated"] == len(policy["rules"]) - len(rules)
    assert summary["starting_portfolio_breaches"] == len(start_fail)
    assert summary["feasibility_status"] == feasibility["status"]

    # ---- maximum compliant weight, confirmed by brute force
    maximum = expected["max_compliant"]
    best, some_not_fail, step = ref.scan_boundary(case, universe)
    if conflicts or not rules:
        assert maximum["status"] == "WITHHELD"
    elif maximum["status"] == "SUPPORTED":
        final = maximum["final_direct_weight"]
        assert close(maximum["additional_purchase"], final - start_weight)
        assert ref.all_pass_and_funded(case, universe, final)[0], "the evaluator re-run at the boundary must pass everything"
        assert not ref.all_pass_and_funded(case, universe, final + 1e-6)[0], "just above the boundary something must stop passing"
        assert best is not None and final - step - TOL <= best <= final + TOL, f"scan found {best}, fixture says {final}"
        beyond = ref.with_target(portfolio, request["instrument_id"], final + 1e-6)
        binding = maximum["binding_constraint"]
        stops = [r["rule_id"] for r in rules if ref.evaluate_rule(r, beyond[0], universe)["status"] != "PASS"]
        if binding["type"] == "CASH":
            assert beyond[2] < -ref.EPS, "CASH is binding only if cash runs out just above the boundary"
            assert not stops, f"a rule ({stops}) stops passing at the same point: the rule is reported, not CASH"
        else:
            assert stops and stops[0] == binding["rule_id"], f"the first rule in policy order that stops passing is {stops[:1]}, fixture says {binding['rule_id']}"
    elif maximum["status"] == "NO_FEASIBLE_PURCHASE":
        assert best is None and not some_not_fail, "every positive purchase must have a proven FAIL or be unfunded"
        assert maximum["final_direct_weight"] is None and maximum["additional_purchase"] is None
        binding = maximum["binding_constraint"]
        if portfolio["cash_weight"] <= ref.EPS:
            assert binding == {"type": "CASH", "rule_id": None}, "with no cash, CASH is the constraint"
        else:
            just_above = ref.with_target(portfolio, request["instrument_id"], start_weight + min(portfolio["cash_weight"], 1e-6))[0]
            failing = [r["rule_id"] for r in rules if ref.evaluate_rule(r, just_above, universe)["status"] == "FAIL"]
            assert failing and binding == {"type": "RULE", "rule_id": failing[0]}, f"first rule failing just above the starting weight: {failing[:1]}"
    else:
        assert best is None and some_not_fail, "WITHHELD: nothing proven to pass, yet not everything proven to fail"
        assert maximum["final_direct_weight"] is None and maximum["binding_constraint"] is None
    assert maximum["verified_by_rerun"] == (maximum["status"] == "SUPPORTED")
