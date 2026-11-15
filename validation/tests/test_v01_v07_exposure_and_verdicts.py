"""V01-V07: exposure, thresholds, fund paths, missing data, mixed verdicts, cash, proven conflicts.

Every expected number is derived in the comment above the test from the
validator universe documented in ``validation/support/universe.py`` and is
cross-checked with the exact-rational reference in ``support/reference.py``.
"""

from __future__ import annotations

from fractions import Fraction

import pytest

from validation.support import reference as ref
from validation.support import universe as U
from validation.support.run import by_rule, check, close


def _issuer_row(result: dict, issuer: str) -> dict:
    return next(row for row in result["exposure"]["issuers"] if row["issuer_id"] == issuer)


# --------------------------------------------------------------------------- V01

@pytest.mark.vcase("V01")
def test_v01_direct_plus_indirect_exposure_and_cash_funding():
    """cash 0.40 | AAA 0.10 | F1 0.30 | BND 0.20; buy AAA to a FINAL weight of 0.15.

    ALPHA before = 0.10 + 0.30 x (0.20 + 0.10) = 0.19        (F1 holds two ALPHA share classes)
    ALPHA after  = 0.15 + 0.09               = 0.24
    BETA = 0.30 x 0.30 = 0.09, GAMMA = 0.30 x 0.40 = 0.12, uncovered U = 0 (F1 coverage 1.00)
    cash after   = 0.40 - (0.15 - 0.10)      = 0.35
    cap 0.25 -> PASS, gap = 0.24 - 0.25 = -0.01
    """
    portfolio = U.portfolio(0.40, {"AAA": 0.10, "F1": 0.30, "BND": 0.20})
    result = check(portfolio, [U.cap_any("cap", 0.25)], U.request("AAA", 0.15))

    feasibility = result["feasibility"]
    assert feasibility["funding"] == "CASH"
    assert close(feasibility["starting_direct_weight"], 0.10)
    assert close(feasibility["additional_purchase"], 0.05)
    assert close(feasibility["cash_after"], 0.35)
    assert feasibility["status"] == "FEASIBLE"

    rule = by_rule(result)["cap"]
    assert rule["status"] == "PASS"
    assert close(rule["measured"]["lower"], 0.24) and close(rule["measured"]["upper"], 0.24)
    assert close(rule["gap"], -0.01)
    assert rule["starting"]["status"] == "PASS" and close(rule["starting"]["measured"]["lower"], 0.19)
    assert [entry["instrument_id"] for entry in rule["out_of_scope"]] == ["BND"]

    alpha = _issuer_row(result, "ALPHA")
    assert close(alpha["proposed"]["direct"], 0.15)
    assert [(p["fund_id"], round(p["known"], 12)) for p in alpha["proposed"]["indirect_by_fund"]] == [("F1", 0.09)]
    assert close(alpha["starting"]["direct"], 0.10) and close(alpha["starting"]["lower"], 0.19)
    assert close(_issuer_row(result, "BETA")["proposed"]["lower"], 0.09)
    assert close(_issuer_row(result, "GAMMA")["proposed"]["lower"], 0.12)

    # Independent exact arithmetic agrees.
    data = U.universe()
    after = ref.proposed(portfolio, "AAA", 0.15)
    exact = ref.exposure(after, data["instruments"], data["holdings"])
    assert exact["lower"]["ALPHA"] == Fraction(24, 100) and exact["U"] == 0
    assert after["_cash_after"] == Fraction(35, 100)

    # The other positions are untouched by the purchase (BUILD_BRIEF section 2).
    assert result["summary"]["headline"] == "ALL_PASS"


@pytest.mark.vcase("V01")
def test_v01_no_double_counting_conservation():
    """Known exposure + uncovered weight must add up to exactly the in-scope equity weight.

    cash 0.20 | AAA 0.05 | AAB 0.05 | F1 0.30 | F2 0.20 | BND 0.20 -> in scope 0.60
    sum(lower) = ALPHA 0.29 + BETA 0.09 + GAMMA 0.12 + DELTA 0.06 = 0.56 ; U = 0.20 x 0.20 = 0.04 ; total 0.60
    A fund position counted both as a fund and through its constituents would break this identity.
    """
    from backend.engine import compute_exposure

    data = U.universe()
    portfolio = U.portfolio(0.20, {"AAA": 0.05, "AAB": 0.05, "F1": 0.30, "F2": 0.20, "BND": 0.20})
    measured = compute_exposure(portfolio, data["instruments"], data["holdings"])
    assert close(sum(measured["lower"].values()) + measured["possible_extra"], 0.60)
    assert close(measured["in_scope_weight"], 0.60)
    assert "F1" not in measured["lower"] and "F2" not in measured["lower"], "a fund must not appear as its own issuer exposure"
    assert "BND" not in measured["lower"]


# --------------------------------------------------------------------------- V02

@pytest.mark.vcase("V02")
@pytest.mark.parametrize(
    "target, expected",
    [
        (0.16, "PASS"),            # 0.16 + 0.09 = 0.25 == limit: equality passes (D2)
        (0.16 + 5e-10, "PASS"),    # inside the documented tolerance EPS = 1e-9
        (0.16 + 1e-8, "FAIL"),     # just above the limit
        (0.16 - 1e-8, "PASS"),     # just below
    ],
)
def test_v02_max_rule_exact_threshold(target, expected):
    portfolio = U.portfolio(0.40, {"AAA": 0.10, "F1": 0.30, "BND": 0.20})
    result = check(portfolio, [U.cap_any("cap", 0.25)], U.request("AAA", target))
    rule = by_rule(result)["cap"]
    assert rule["status"] == expected
    assert rule["status"] == ref.status("max_issuer_exposure", rule["measured"]["lower"], rule["measured"]["upper"], 0.25)
    if target == 0.16:
        assert abs(rule["gap"]) < 1e-12, "at equality the gap is zero, not a breach"
    if expected == "FAIL":
        assert rule["gap"] > 0


@pytest.mark.vcase("V02")
@pytest.mark.parametrize("target, expected", [(0.16, "PASS"), (0.16 - 1e-8, "FAIL"), (0.16 + 1e-8, "PASS")])
def test_v02_min_rule_exact_threshold(target, expected):
    """Minimum 0.25 of ALPHA; ALPHA = target + 0.09, no uncovered weight."""
    portfolio = U.portfolio(0.40, {"AAA": 0.10, "F1": 0.30, "BND": 0.20})
    result = check(portfolio, [U.floor_one("floor", "ALPHA", 0.25)], U.request("AAA", target))
    assert by_rule(result)["floor"]["status"] == expected


@pytest.mark.vcase("V02")
def test_v02_loss_budget_exact_threshold():
    """cash 0.50 | AAA 0.50 -> terminal return 0.50 x (-0.10) = -0.05, loss 0.05.
    budget 0.05 -> PASS (equality); budget 0.049 -> FAIL with gap 0.001."""
    portfolio = U.portfolio(0.50, {"AAA": 0.50})
    at_limit = check(portfolio, [U.loss_budget("budget", 0.05)], U.request("AAA", 0.50))
    assert by_rule(at_limit)["budget"]["status"] == "PASS"
    assert close(by_rule(at_limit)["budget"]["measured"]["lower"], 0.05)
    above = check(portfolio, [U.loss_budget("budget", 0.049)], U.request("AAA", 0.50))
    assert by_rule(above)["budget"]["status"] == "FAIL"
    assert close(by_rule(above)["budget"]["gap"], 0.001)


# --------------------------------------------------------------------------- V03

V03_PORTFOLIO = {"AAA": 0.05, "AAB": 0.05, "F1": 0.30, "F2": 0.20, "BND": 0.20}


@pytest.mark.vcase("V03")
def test_v03_two_fund_paths_and_two_share_classes_are_aggregated():
    """cash 0.20 | AAA 0.05 | AAB 0.05 | F1 0.30 | F2 0.20 | BND 0.20 ; buy CCC to 0.05.

    ALPHA: direct 0.05 (AAA) + 0.05 (AAB)              = 0.10
           via F1: 0.30 x (0.20 + 0.10)                = 0.09
           via F2: 0.20 x 0.50                         = 0.10
           lower 0.29 ; U = 0.20 x (1 - 0.80) = 0.04 ; upper 0.33
    GAMMA after: 0.05 + 0.30 x 0.40 = 0.17 ; BETA 0.09 ; DELTA 0.20 x 0.30 = 0.06
    """
    portfolio = U.portfolio(0.20, V03_PORTFOLIO)
    result = check(portfolio, [U.cap_any("cap", 0.35)], U.request("CCC", 0.05))
    alpha = _issuer_row(result, "ALPHA")["proposed"]
    assert close(alpha["direct"], 0.10)
    assert {p["fund_id"]: round(p["known"], 12) for p in alpha["indirect_by_fund"]} == {"F1": 0.09, "F2": 0.10}
    assert close(alpha["lower"], 0.29) and close(alpha["upper"], 0.33)
    assert close(_issuer_row(result, "GAMMA")["proposed"]["lower"], 0.17)
    assert close(_issuer_row(result, "DELTA")["proposed"]["lower"], 0.06)
    assert close(result["exposure"]["possible_extra"]["proposed"], 0.04)

    rule = by_rule(result)["cap"]
    assert rule["status"] == "PASS" and close(rule["measured"]["upper"], 0.33) and close(rule["gap"], -0.02)

    data = U.universe()
    exact = ref.exposure(ref.proposed(portfolio, "CCC", 0.05), data["instruments"], data["holdings"])
    assert exact["lower"]["ALPHA"] == Fraction(29, 100) and exact["U"] == Fraction(4, 100)


@pytest.mark.vcase("V03")
@pytest.mark.parametrize("limit, expected", [(0.35, "PASS"), (0.33, "PASS"), (0.30, "UNKNOWN"), (0.29, "UNKNOWN"), (0.28, "FAIL")])
def test_v03_status_across_the_interval(limit, expected):
    """lower 0.29, upper 0.33: PASS needs upper <= limit, FAIL needs lower > limit, between them UNKNOWN."""
    result = check(U.portfolio(0.20, V03_PORTFOLIO), [U.cap_any("cap", limit)], U.request("CCC", 0.05))
    rule = by_rule(result)["cap"]
    assert rule["status"] == expected
    if expected == "UNKNOWN":
        assert rule["gap"] is None and "PARTIAL_HOLDINGS" in rule["unknown_causes"]
    if expected == "FAIL":
        assert [s["subject_id"] for s in rule["breaching_subjects"]] == ["ALPHA"]
        assert close(rule["gap"], 0.29 - limit)


@pytest.mark.vcase("V03")
def test_v03_single_issuer_rule_counts_both_share_classes():
    result = check(U.portfolio(0.20, V03_PORTFOLIO), [U.cap_one("cap-alpha", "ALPHA", 0.40), U.exclude_named("no-alpha", ["ALPHA"], 0.0)],
                   U.request("CCC", 0.05))
    rules = by_rule(result)
    assert close(rules["cap-alpha"]["measured"]["lower"], 0.29) and rules["cap-alpha"]["status"] == "PASS"
    assert rules["no-alpha"]["status"] == "FAIL" and close(rules["no-alpha"]["gap"], 0.29)


# --------------------------------------------------------------------------- V04

V04_PORTFOLIO = {"F2": 0.20, "F3": 0.25, "AAA": 0.05, "BND": 0.20}


@pytest.mark.vcase("V04")
def test_v04_missing_and_partial_holdings_are_never_zero():
    """cash 0.30 | F2 0.20 (coverage 0.80) | F3 0.25 (no file) | AAA 0.05 | BND 0.20 ; buy BBB to 0.05.

    ALPHA lower = 0.05 + 0.20 x 0.50 = 0.15
    U = 0.20 x 0.20 + 0.25 = 0.29 ; ALPHA upper = 0.44
    cap 0.20 lies between the bounds -> UNKNOWN, gap null, both causes named. It must not be a PASS.
    """
    portfolio = U.portfolio(0.30, V04_PORTFOLIO)
    result = check(portfolio, [U.cap_any("cap", 0.20)], U.request("BBB", 0.05))
    rule = by_rule(result)["cap"]
    assert rule["status"] == "UNKNOWN" and rule["gap"] is None
    assert close(rule["measured"]["lower"], 0.15) and close(rule["measured"]["upper"], 0.44)
    assert set(rule["unknown_causes"]) == {"PARTIAL_HOLDINGS", "MISSING_HOLDINGS"}
    assert result["summary"]["headline"] == "NO_FAIL_BUT_UNKNOWN"
    assert result["summary"]["counts"] == {"pass": 0, "fail": 0, "unknown": 1}

    coverage = {row["fund_id"]: row for row in result["data_coverage"]}
    assert coverage["F3"]["status"] == "MISSING" and coverage["F3"]["coverage_fraction"] == 0
    assert close(coverage["F3"]["uncovered_portfolio_weight"], 0.25)
    assert coverage["F3"]["holdings_date"] is None and coverage["F3"]["source_id"] is None
    assert coverage["F2"]["status"] == "PARTIAL" and close(coverage["F2"]["uncovered_portfolio_weight"], 0.04)
    assert close(coverage["F2"]["coverage_fraction"], 0.80), "partial holdings must not be rescaled to 100%"

    # Unknown data never yields a maximum (BUILD_BRIEF section 2, SEMANTICS 11).
    assert result["max_compliant"]["status"] == "WITHHELD"
    assert result["max_compliant"]["final_direct_weight"] is None


@pytest.mark.vcase("V04")
def test_v04_partial_holdings_are_not_rescaled():
    """If F2's rows were rescaled to 100%, ALPHA via F2 would be 0.20 x 0.50 / 0.80 = 0.125 instead of 0.10."""
    result = check(U.portfolio(0.30, V04_PORTFOLIO), [U.cap_any("cap", 0.50)], U.request("BBB", 0.05))
    alpha = _issuer_row(result, "ALPHA")["proposed"]
    assert {p["fund_id"]: round(p["known"], 12) for p in alpha["indirect_by_fund"]} == {"F2": 0.10}
    rule = by_rule(result)["cap"]
    assert rule["status"] == "PASS" and close(rule["measured"]["upper"], 0.44)
    assert set(rule["unknown_causes"]) == {"PARTIAL_HOLDINGS", "MISSING_HOLDINGS"}, "the data gap is still disclosed on a PASS"


@pytest.mark.vcase("V04")
def test_v04_sector_rule_unlabelled_constituents_are_unknown_not_clean():
    """Energy exclusion, tolerance 0.02, on cash 0.50 | F2 0.20 | BND 0.30, buying CCC ("Health") to 0.05.

    Known Energy: DELTA via F2 = 0.20 x 0.30 = 0.06 -> FAIL at 0.02 (gap 0.04).
    With tolerance 0.10: lower 0.06 ; upper = 0.06 + U 0.04 + unlabelled (AAA row of F2: 0.20 x 0.50 = 0.10) = 0.20 -> UNKNOWN.
    """
    portfolio = U.portfolio(0.50, {"F2": 0.20, "BND": 0.30})
    strict = by_rule(check(portfolio, [U.exclude_sector("energy", "Energy", 0.02)], U.request("CCC", 0.05)))["energy"]
    assert strict["status"] == "FAIL" and close(strict["gap"], 0.04)
    loose = by_rule(check(portfolio, [U.exclude_sector("energy", "Energy", 0.10)], U.request("CCC", 0.05)))["energy"]
    assert loose["status"] == "UNKNOWN"
    assert close(loose["measured"]["lower"], 0.06) and close(loose["measured"]["upper"], 0.20)
    assert "UNCLASSIFIED_SECTOR" in loose["unknown_causes"] and "PARTIAL_HOLDINGS" in loose["unknown_causes"]


@pytest.mark.vcase("V04")
def test_v04_sector_label_is_exact_and_fund_label_is_not_inherited():
    """'energy' (lower case) matches nothing known; the fund's own label 'Broad market' is never applied to constituents."""
    portfolio = U.portfolio(0.50, {"F1": 0.20, "BND": 0.30})
    lower_case = by_rule(check(portfolio, [U.exclude_sector("x", "energy", 0.0)], U.request("CCC", 0.05)))["x"]
    assert close(lower_case["measured"]["lower"], 0.0) and lower_case["status"] == "PASS"  # F1 fully labelled, CCC is "Health"
    broad = by_rule(check(portfolio, [U.exclude_sector("x", "Broad market", 0.0)], U.request("CCC", 0.05)))["x"]
    assert close(broad["measured"]["lower"], 0.0), "a fund-level label must not classify the fund's constituents"


@pytest.mark.vcase("V04")
def test_v04_controversy_registry_absence_is_unknown_never_pass():
    """Empty registry, cash 0.50 | AAA 0.20 | BND 0.30, tolerance 0: no issuer is assessed -> UNKNOWN (upper = in-scope 0.25)."""
    portfolio = U.portfolio(0.50, {"AAA": 0.20, "BND": 0.30})
    rule = by_rule(check(portfolio, [U.exclude_controversy("contro", ["SETTLEMENT"], 0.0)], U.request("BBB", 0.05)))["contro"]
    assert rule["status"] == "UNKNOWN" and "REGISTRY_ABSENCE" in rule["unknown_causes"]
    assert close(rule["measured"]["lower"], 0.0) and close(rule["measured"]["upper"], 0.25)

    data = U.universe()
    data["controversies"] = U.controversies([U.controversy_record("rec-1", "ALPHA", "SETTLEMENT", "2020-05-01")])
    flagged = by_rule(check(portfolio, [U.exclude_controversy("contro", ["SETTLEMENT"], 0.0)], U.request("BBB", 0.05), data))["contro"]
    assert flagged["status"] == "FAIL" and close(flagged["measured"]["lower"], 0.20)
    # The date filter and the nature filter both exclude the record: back to UNKNOWN, never PASS.
    for rule_def in (U.exclude_controversy("contro", ["SETTLEMENT"], 0.0, since="2021-01-01"), U.exclude_controversy("contro", ["COURT_RULING"], 0.0)):
        assert by_rule(check(portfolio, [rule_def], U.request("BBB", 0.05), data))["contro"]["status"] == "UNKNOWN"


# --------------------------------------------------------------------------- V05

@pytest.mark.vcase("V05")
def test_v05_proven_failure_coexists_with_unknown_checks():
    """Portfolio of V04, buying BBB ("Energy", issuer BETA) to 0.05.

    cap any 0.10          : ALPHA lower 0.15 > 0.10                       -> FAIL (gap 0.05) although U = 0.29
    Energy tolerance 0    : DELTA via F2 0.06 + BBB direct 0.05 = 0.11    -> FAIL (gap 0.11)
    named [GAMMA] tol 0   : lower 0, upper 0 + U 0.29                     -> UNKNOWN
    cap any 0.50          : upper 0.44 <= 0.50                            -> PASS
    Headline HAS_FAIL ; counts 1 pass / 2 fail / 1 unknown.
    The cap and the sector rule already failed before the purchase (0.15 and 0.06): reported separately,
    with the purchase effect 0 on the cap and +0.05 on the sector rule.
    """
    rules = [U.cap_any("cap-tight", 0.10), U.exclude_sector("energy", "Energy", 0.0), U.exclude_named("no-gamma", ["GAMMA"], 0.0),
             U.cap_any("cap-loose", 0.50)]
    result = check(U.portfolio(0.30, V04_PORTFOLIO), rules, U.request("BBB", 0.05))
    got = by_rule(result)
    assert [got[k]["status"] for k in ("cap-tight", "energy", "no-gamma", "cap-loose")] == ["FAIL", "FAIL", "UNKNOWN", "PASS"]
    assert close(got["cap-tight"]["gap"], 0.05) and close(got["energy"]["gap"], 0.11)
    assert got["no-gamma"]["gap"] is None and close(got["no-gamma"]["measured"]["upper"], 0.29)
    assert got["cap-tight"]["unknown_causes"], "a FAIL still discloses the data gaps"
    assert result["summary"]["headline"] == "HAS_FAIL"
    assert result["summary"]["counts"] == {"pass": 1, "fail": 2, "unknown": 1}
    assert [r["rule_id"] for r in result["rule_results"]] == ["cap-tight", "energy", "no-gamma", "cap-loose"], "policy order"

    findings = {f["rule_id"]: f for f in result["starting_portfolio_findings"]}
    assert set(findings) == {"cap-tight", "energy"}
    assert close(findings["cap-tight"]["purchase_effect"]["lower_change"], 0.0)
    assert close(findings["energy"]["purchase_effect"]["lower_change"], 0.05)
    assert close(findings["energy"]["measured"]["lower"], 0.06)
    assert result["summary"]["starting_portfolio_breaches"] == 2
    assert result["max_compliant"]["status"] == "NO_FEASIBLE_PURCHASE"
    assert result["max_compliant"]["binding_constraint"] == {"type": "RULE", "rule_id": "cap-tight"}
    assert "compliant" not in result["summary"], "there is no overall compliant flag (SEMANTICS 9)"


# --------------------------------------------------------------------------- V06

@pytest.mark.vcase("V06")
def test_v06_insufficient_cash_is_feasibility_not_a_rule_result_or_conflict():
    """cash 0.05 | AAA 0.10 | BND 0.85 ; buy AAA to 0.30 -> additional 0.20, cash after -0.15.
    cap 0.50 still evaluated at the requested weight: 0.30 -> PASS. Maximum: min(cap 0.50, cash 0.10 + 0.05) = 0.15, binding CASH."""
    result = check(U.portfolio(0.05, {"AAA": 0.10, "BND": 0.85}), [U.cap_any("cap", 0.50)], U.request("AAA", 0.30))
    assert result["execution"]["status"] == "OK"
    assert result["feasibility"]["status"] == "INSUFFICIENT_CASH" and close(result["feasibility"]["cash_after"], -0.15)
    assert by_rule(result)["cap"]["status"] == "PASS"
    assert result["summary"]["headline"] == "ALL_PASS" and result["summary"]["feasibility_status"] == "INSUFFICIENT_CASH"
    assert result["policy_consistency"] == {"status": "CONSISTENT", "conflicts": []}
    maximum = result["max_compliant"]
    assert maximum["status"] == "SUPPORTED" and close(maximum["final_direct_weight"], 0.15)
    assert close(maximum["additional_purchase"], 0.05)
    assert maximum["binding_constraint"] == {"type": "CASH", "rule_id": None} and maximum["verified_by_rerun"] is True


@pytest.mark.vcase("V06")
def test_v06_no_cash_means_no_feasible_purchase():
    result = check(U.portfolio(0.0, {"AAA": 0.10, "BND": 0.90}), [U.cap_any("cap", 0.50)], U.request("AAA", 0.10))
    assert result["max_compliant"]["status"] == "NO_FEASIBLE_PURCHASE"
    assert result["max_compliant"]["binding_constraint"] == {"type": "CASH", "rule_id": None}
    assert result["max_compliant"]["final_direct_weight"] is None


@pytest.mark.vcase("V06")
def test_v06_rule_already_breached_means_no_feasible_purchase():
    """cash 0.20 | AAA 0.30 | BND 0.50, cap 0.25: every purchase of AAA or BBB leaves ALPHA at >= 0.30 > 0.25."""
    portfolio = U.portfolio(0.20, {"AAA": 0.30, "BND": 0.50})
    for instrument, target in (("AAA", 0.35), ("BBB", 0.05)):
        maximum = check(portfolio, [U.cap_any("cap", 0.25)], U.request(instrument, target))["max_compliant"]
        assert maximum["status"] == "NO_FEASIBLE_PURCHASE"
        assert maximum["binding_constraint"] == {"type": "RULE", "rule_id": "cap"}
        assert maximum["final_direct_weight"] is None and maximum["verified_by_rerun"] is False


@pytest.mark.vcase("V06")
@pytest.mark.parametrize(
    "instrument, target, code",
    [("AAA", 0.05, "TARGET_BELOW_CURRENT_WEIGHT"), ("AAA", -0.01, "TARGET_NEGATIVE"), ("AAA", 1.01, "TARGET_ABOVE_ONE"),
     ("ZZZ", 0.10, "UNSUPPORTED_INSTRUMENT")],
)
def test_v06_requests_outside_the_funding_path_evaluate_nothing(instrument, target, code):
    """Selling, shorting, leverage and unknown instruments are refused, not turned into a verdict."""
    result = check(U.portfolio(0.20, {"AAA": 0.30, "BND": 0.50}), [U.cap_any("cap", 0.90)], U.request(instrument, target))
    assert result["execution"]["status"] == "INVALID_REQUEST" and result["execution"]["code"] == code
    assert result["rule_results"] == [] and result["evidence"] == []
    assert result["feasibility"] is None and result["max_compliant"] is None and result["exposure"] is None
    assert result["summary"]["headline"] == "INVALID_REQUEST"
    assert result["policy_consistency"]["status"] == "NOT_ASSESSED"


# --------------------------------------------------------------------------- V07

@pytest.mark.vcase("V07")
def test_v07_minimum_above_maximum_on_one_issuer_is_a_proven_conflict():
    """min ALPHA 0.20 with max ALPHA 0.10: no exposure satisfies both (BUILD_BRIEF section 3)."""
    rules = [U.floor_one("floor", "ALPHA", 0.20), U.cap_one("cap", "ALPHA", 0.10)]
    result = check(U.portfolio(0.50, {"AAA": 0.15, "BND": 0.35}), rules, U.request("AAA", 0.15))
    consistency = result["policy_consistency"]
    assert consistency["status"] == "PROVEN_CONFLICT"
    conflict = consistency["conflicts"][0]
    assert conflict["conflict_type"] == "MIN_EXCEEDS_MAX_SAME_ISSUER" and conflict["rule_ids"] == ["floor", "cap"]
    assert conflict["issuer_id"] == "ALPHA" and conflict["min_fraction"] == 0.20 and conflict["max_fraction"] == 0.10
    assert result["summary"]["headline"] == "POLICY_CONFLICT"
    # Rules are still evaluated one by one: ALPHA = 0.15 -> floor FAIL (0.15 < 0.20), cap FAIL (0.15 > 0.10).
    assert [r["status"] for r in result["rule_results"]] == ["FAIL", "FAIL"]
    assert result["max_compliant"]["status"] == "WITHHELD" and result["max_compliant"]["final_direct_weight"] is None


@pytest.mark.vcase("V07")
@pytest.mark.parametrize(
    "rules, expected",
    [
        ([U.floor_one("floor", "ALPHA", 0.10), U.cap_one("cap", "ALPHA", 0.10)], "CONSISTENT"),       # equal limits
        ([U.floor_one("floor", "ALPHA", 0.20), U.cap_any("cap", 0.10)], "PROVEN_CONFLICT"),            # any-issuer cap covers ALPHA
        ([U.floor_one("floor", "ALPHA", 0.20), U.cap_one("cap", "BETA", 0.10)], "CONSISTENT"),         # different issuers
        ([U.floor_one("floor", "ALPHA", 0.20), U.cap_one("cap", "ALPHA", 0.10, status="PROPOSED")], "CONSISTENT"),  # unconfirmed cap proves nothing
        ([U.cap_any("cap", 0.10), U.loss_budget("budget", 0.0)], "CONSISTENT"),                         # hard to satisfy is not a contradiction
    ],
)
def test_v07_only_a_supported_calculation_proves_a_conflict(rules, expected):
    result = check(U.portfolio(0.50, {"AAA": 0.15, "BND": 0.35}), rules, U.request("AAA", 0.15))
    assert result["policy_consistency"]["status"] == expected
    assert (result["summary"]["headline"] == "POLICY_CONFLICT") == (expected == "PROVEN_CONFLICT")
