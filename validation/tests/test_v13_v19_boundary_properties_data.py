"""V13-V19: maximum compliant weight, metamorphic and differential properties, inaccessible or inconsistent data.

V13  maximum compliant weight under every rule type, verified by re-run
V14  KNOWN DEFECT: the boundary is rounded to the nearest 9th decimal, not down
V15  differential test against the validator's exact-rational reference (random portfolios)
V16  metamorphic properties of exposure and verdicts
V17  determinism, purity, summary consistency
V18  missing or unusable price history
V19  inconsistent or contradictory inputs
"""

from __future__ import annotations

import copy
import json
import random
import re
from pathlib import Path

import pytest

from backend.engine import check_rules, compute_exposure, max_compliant_amount
from byb_contracts import ContractError, validate_holdings_snapshot, validate_instrument_registry, validate_market_data

from validation.support import reference as ref
from validation.support import universe as U
from validation.support.run import by_rule, check, close

REPO_ROOT = Path(__file__).resolve().parents[2]
EPS = 1e-9


# --------------------------------------------------------------------------- V13

def _rerun_statuses(portfolio, rules, instrument, weight, data=None):
    return [r["status"] for r in check(portfolio, rules, U.request(instrument, weight), data)["rule_results"]]


@pytest.mark.vcase("V13")
@pytest.mark.parametrize(
    "label, cash, positions, rules, instrument, expected, binding",
    [
        # any-issuer cap: ALPHA = w + 0.30 x 0.30 -> w <= 0.25 - 0.09 = 0.16
        ("cap-any", 0.40, {"AAA": 0.10, "F1": 0.30, "BND": 0.20}, [U.cap_any("cap", 0.25)], "AAA", 0.16, "cap"),
        # one-issuer cap on the OTHER share class: buying AAB also raises ALPHA
        ("cap-one-share-class", 0.40, {"AAA": 0.10, "F1": 0.30, "BND": 0.20}, [U.cap_one("cap", "ALPHA", 0.25)], "AAB", 0.06, "cap"),
        # buying a fund: ALPHA = 0.10 + 0.30 w -> w <= (0.25 - 0.10) / 0.30 = 0.50, but cash is 0.40 and F1 starts at 0
        ("fund-cash-bound", 0.40, {"AAA": 0.10, "BND": 0.50}, [U.cap_any("cap", 0.25)], "F1", 0.40, None),
        # buying a fund with a tighter cap: GAMMA = 0.40 w <= 0.12 -> w <= 0.30 ; ALPHA 0.10 + 0.30 w <= 0.12 -> w <= 0.0666..
        ("fund-rule-bound", 0.40, {"AAA": 0.10, "BND": 0.50}, [U.cap_any("cap", 0.12)], "F1", (0.12 - 0.10) / 0.30, "cap"),
        # named exclusion with a tolerance: BETA = w + 0.30 x 0.30 <= 0.12 -> w <= 0.03
        ("named-exclusion", 0.40, {"AAA": 0.10, "F1": 0.30, "BND": 0.20}, [U.exclude_named("no-beta", ["BETA"], 0.12)], "BBB", 0.03, "no-beta"),
        # sector exclusion: Energy = 0.09 (BBB row of F1) + w <= 0.15 -> w <= 0.06
        ("sector-exclusion", 0.40, {"AAA": 0.10, "F1": 0.30, "BND": 0.20}, [U.exclude_sector("energy", "Energy", 0.15)], "BBB", 0.06, "energy"),
        # loss budget: loss = 0.30x0.10 (F1) + 0.20x0.05 (BND) + 0.10 x w(final AAA) = 0.04 + 0.10 w <= 0.06 -> final w <= 0.20
        ("loss-budget", 0.40, {"AAA": 0.10, "F1": 0.30, "BND": 0.20}, [U.loss_budget("budget", 0.06)], "AAA", 0.20, "budget"),
        # a purchase that IMPROVES the replay (BBB +30%): the budget never binds, cash does
        ("budget-never-binds", 0.40, {"AAA": 0.10, "F1": 0.30, "BND": 0.20}, [U.loss_budget("budget", 0.06)], "BBB", 0.40, None),
        # two rules: first in policy order that stops passing is reported
        ("two-rules", 0.40, {"AAA": 0.10, "F1": 0.30, "BND": 0.20}, [U.loss_budget("budget", 0.055), U.cap_any("cap", 0.25)], "AAA", 0.15, "budget"),
    ],
)
def test_v13_maximum_compliant_weight_closed_form_and_rerun(label, cash, positions, rules, instrument, expected, binding):
    portfolio = U.portfolio(cash, positions)
    start = positions.get(instrument, 0.0)
    result = check(portfolio, rules, U.request(instrument, start))
    maximum = result["max_compliant"]
    assert maximum["status"] == "SUPPORTED", maximum["reason"]
    assert close(maximum["final_direct_weight"], expected, 1e-9), f"{label}: expected {expected}, got {maximum['final_direct_weight']}"
    assert close(maximum["additional_purchase"], expected - start, 1e-9), "final weight and additional purchase must both be stated"
    assert maximum["verified_by_rerun"] is True
    assert maximum["binding_constraint"] == ({"type": "RULE", "rule_id": binding} if binding else {"type": "CASH", "rule_id": None})
    assert maximum["final_direct_weight"] <= start + cash + EPS, "the maximum can never exceed what cash funds"
    assert "final direct weight" in maximum["reason"].lower() and "additional purchase" in maximum["reason"].lower()

    # Independent re-run at the boundary and one step above it.
    at = check(portfolio, rules, U.request(instrument, maximum["final_direct_weight"]))
    assert all(r["status"] == "PASS" for r in at["rule_results"]) and at["feasibility"]["status"] == "FEASIBLE"
    above = check(portfolio, rules, U.request(instrument, maximum["final_direct_weight"] + 1e-6))
    if binding:
        assert by_rule(above)[binding]["status"] != "PASS", "one step above a rule-bound maximum the binding rule must not pass"
    else:
        assert above["feasibility"]["status"] == "INSUFFICIENT_CASH"


@pytest.mark.vcase("V13")
def test_v13_maximum_does_not_depend_on_the_requested_target():
    portfolio = U.portfolio(0.40, {"AAA": 0.10, "F1": 0.30, "BND": 0.20})
    rules = [U.cap_any("cap", 0.25), U.loss_budget("budget", 0.06)]
    seen = {json.dumps(check(portfolio, rules, U.request("AAA", target))["max_compliant"], sort_keys=True) for target in (0.10, 0.12, 0.16, 0.30, 0.60)}
    assert len(seen) == 1
    direct = max_compliant_amount(portfolio, U.policy(rules), U.request("AAA", 0.30), *[U.universe()[k] for k in ("instruments", "holdings", "market_data", "controversies")])
    assert close(direct["final_direct_weight"], 0.16, 1e-9)


@pytest.mark.vcase("V13")
@pytest.mark.parametrize(
    "label, cash, positions, rules, instrument",
    [
        ("partial-holdings", 0.30, {"F2": 0.20, "F3": 0.25, "AAA": 0.05, "BND": 0.20}, [U.cap_any("cap", 0.20)], "BBB"),
        ("registry-absence", 0.50, {"AAA": 0.20, "BND": 0.30}, [U.exclude_controversy("contro", ["SETTLEMENT"], 0.10)], "BBB"),
        ("no-history-for-target", 0.50, {"AAA": 0.20, "BND": 0.30}, [U.loss_budget("budget", 0.10)], "NOHIST"),
        ("no-history-in-portfolio", 0.50, {"STALE": 0.20, "BND": 0.30}, [U.loss_budget("budget", 0.10)], "AAA"),
        ("unlabelled-sector", 0.50, {"BND": 0.50}, [U.exclude_sector("energy", "Energy", 0.0)], "F2"),
    ],
)
def test_v13_unknown_data_never_yields_a_maximum(label, cash, positions, rules, instrument):
    result = check(U.portfolio(cash, positions), rules, U.request(instrument, positions.get(instrument, 0.0)))
    maximum = result["max_compliant"]
    assert maximum["status"] in ("WITHHELD", "NO_FEASIBLE_PURCHASE"), label
    assert maximum["final_direct_weight"] is None and maximum["additional_purchase"] is None
    assert maximum["verified_by_rerun"] is False and maximum["reason"]


@pytest.mark.vcase("V13")
def test_v13_minimum_rule_gives_a_lower_end_not_a_false_maximum():
    """min ALPHA 0.20 with ALPHA at 0.10: every funded target >= 0.20 passes; the maximum is cash-bound at 0.50.
    A target of 0.15 FAILS the minimum, so 'maximum' must not be read as 'any weight up to it passes'."""
    portfolio = U.portfolio(0.40, {"AAA": 0.10, "BND": 0.50})
    result = check(portfolio, [U.floor_one("floor", "ALPHA", 0.20)], U.request("AAA", 0.15))
    assert by_rule(result)["floor"]["status"] == "FAIL"
    maximum = result["max_compliant"]
    assert maximum["status"] == "SUPPORTED" and close(maximum["final_direct_weight"], 0.50, 1e-9)
    assert maximum["binding_constraint"] == {"type": "CASH", "rule_id": None}


# --------------------------------------------------------------------------- V14 (known defect)

@pytest.mark.vcase("V14")
@pytest.mark.xfail(strict=True, reason="V14: boundary.py rounds the maximum compliant weight to the NEAREST 9th decimal instead of down; "
                                       "the reported maximum exceeds the confirmed limit and is still labelled PASS with a positive gap")
def test_v14_reported_maximum_never_exceeds_the_limit_validator_universe():
    """cash 0.40 | AAA 0.10 | F1 0.30 | BND 0.20 ; cap = 0.25 + 6e-10.

    Exact largest weight: 0.2500000006 - 0.09 = 0.1600000006. The 9-decimal value that respects the cap is
    0.160000000 (rounded DOWN). Rounded to nearest it is 0.160000001, where ALPHA = 0.250000001 > 0.2500000006.
    BUILD_BRIEF section 2: the maximum must "respect ... every applicable supported rule"; SEMANTICS 6: a positive
    gap is "the size of the breach"; boundary.py's own docstring: "the comparison tolerance EPS is not spent as
    extra budget".
    """
    limit = 0.25 + 6e-10
    portfolio = U.portfolio(0.40, {"AAA": 0.10, "F1": 0.30, "BND": 0.20})
    rules = [U.cap_any("cap", limit)]
    maximum = check(portfolio, rules, U.request("AAA", 0.10))["max_compliant"]
    assert maximum["status"] == "SUPPORTED"
    exact_alpha = ref.F(maximum["final_direct_weight"]) + ref.F(0.30) * (ref.F(0.20) + ref.F(0.10))
    assert exact_alpha <= ref.F(limit), f"reported maximum {maximum['final_direct_weight']!r} puts ALPHA at {float(exact_alpha)!r} > limit {limit!r}"
    rerun = by_rule(check(portfolio, rules, U.request("AAA", maximum["final_direct_weight"])))["cap"]
    assert rerun["gap"] <= 0, f"re-run at the reported maximum shows a positive gap {rerun['gap']!r} (a breach) with status {rerun['status']}"


@pytest.mark.vcase("V14")
@pytest.mark.xfail(strict=True, reason="V14: same defect reproduced with the contract fixture R1 inputs (issuer cap 0.1000000006, loss budget loosened)")
def test_v14_reported_maximum_never_exceeds_the_limit_fixture_r1_inputs():
    """R1 inputs as published in contracts/fixtures/engine (read as data), cap moved to 0.1000000006 and the loss
    budget loosened to 0.50 so that the issuer cap binds. NVIDIA before the purchase: lower 0.012 via SPY, upper
    0.014 with the uncovered XIU.TO weight -> exact maximum 0.0860000006."""
    fixtures = REPO_ROOT / "contracts" / "fixtures" / "engine"
    inputs = json.loads((fixtures / "R1.json").read_text(encoding="utf-8"))["inputs"]
    data = json.loads((fixtures / "robert_synthetic_universe.json").read_text(encoding="utf-8"))
    limit = 0.1000000006
    rules = [U.cap_any("cap", limit), U.loss_budget("budget", 0.50)]
    maximum = check(inputs["portfolio"], rules, inputs["purchase_request"], data)["max_compliant"]
    assert maximum["status"] == "SUPPORTED"
    rerun = by_rule(check(inputs["portfolio"], rules, U.request("NVDA", maximum["final_direct_weight"]), data))["cap"]
    assert rerun["measured"]["upper"] <= limit, f"maximum {maximum['final_direct_weight']!r}: exposure {rerun['measured']['upper']!r} > limit {limit!r}"
    assert rerun["gap"] <= 0


@pytest.mark.vcase("V14")
def test_v14_rounding_defect_is_confined_to_sub_tolerance_overshoot():
    """Bounds the damage of V14 (so its severity can be judged): over a sweep of limits the overshoot of the reported
    maximum never exceeds 5e-10 (half a unit of the 9th decimal), which is below the comparison tolerance 1e-9."""
    portfolio = U.portfolio(0.40, {"AAA": 0.10, "F1": 0.30, "BND": 0.20})
    worst = 0.0
    for step in range(0, 40):
        limit = 0.25 + step * 0.25e-10
        maximum = check(portfolio, [U.cap_any("cap", limit)], U.request("AAA", 0.10))["max_compliant"]
        if maximum["status"] != "SUPPORTED":
            continue
        overshoot = float(ref.F(maximum["final_direct_weight"]) + ref.F(0.09) - ref.F(limit))
        worst = max(worst, overshoot)
    assert worst <= 5e-10 + 1e-15, f"overshoot {worst!r} is larger than the rounding half-step"


# --------------------------------------------------------------------------- V15 (differential, random)

POOL = ["AAA", "AAB", "BBB", "CCC", "F1", "F2", "F3", "BND"]


def _random_portfolio(rng: random.Random, pool: list = POOL, min_cash_units: int = 0) -> tuple[dict, dict]:
    names = rng.sample(pool, rng.randint(1, len(pool)))
    units = [rng.randint(1, 30) for _ in names]
    cash_units = rng.randint(min_cash_units, 40)
    total = sum(units) + cash_units
    # weights are multiples of 1/total; build them so the float sum is exactly within 1e-12 of 1
    weights = {name: unit / total for name, unit in zip(names, units)}
    cash = 1.0 - sum(weights.values())
    if cash < 0:
        cash = 0.0
    return U.portfolio(cash, weights), weights


def _random_rules(rng: random.Random) -> list[dict]:
    limit = lambda: rng.choice([0.0, 0.02, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.60])  # noqa: E731
    menu = [
        lambda i: U.cap_any(f"r{i}", limit()),
        lambda i: U.cap_one(f"r{i}", rng.choice(["ALPHA", "BETA", "GAMMA", "DELTA"]), limit()),
        lambda i: U.floor_one(f"r{i}", rng.choice(["ALPHA", "BETA", "GAMMA"]), limit()),
        lambda i: U.exclude_named(f"r{i}", rng.sample(["ALPHA", "BETA", "GAMMA", "DELTA"], rng.randint(1, 3)), limit()),
        lambda i: U.exclude_sector(f"r{i}", rng.choice(["Energy", "Tech", "Health", "Nope"]), limit()),
        lambda i: U.exclude_controversy(f"r{i}", ["SETTLEMENT"], limit()),
    ]
    return [rng.choice(menu)(i) for i in range(rng.randint(1, 4))]


def _random_case(seed: int):
    rng = random.Random(seed)
    portfolio, weights = _random_portfolio(rng)
    instrument = rng.choice(["AAA", "AAB", "BBB", "CCC", "F1", "F2", "F3"])
    start = weights.get(instrument, 0.0)
    target = min(1.0, start + rng.choice([0.0, 0.01, 0.05, 0.10, 0.25]))
    data = U.universe()
    data["controversies"] = U.controversies([U.controversy_record("rec-1", "BETA", "SETTLEMENT", "2020-01-01")])
    return portfolio, _random_rules(rng), U.request(instrument, target), data


SEEDS = list(range(150))


@pytest.mark.vcase("V15")
@pytest.mark.parametrize("seed", SEEDS)
def test_v15_engine_agrees_with_exact_rational_reference(seed):
    """Bounds, status and gap of every rule, on the proposed AND the starting portfolio, against arithmetic done in
    exact rationals by a separately written implementation."""
    portfolio, rules, request, data = _random_case(seed)
    result = check(portfolio, rules, request, data)
    assert result["execution"]["status"] == "OK"
    after = ref.proposed(portfolio, request["instrument_id"], request["target_direct_weight"])
    states = {"proposed": ref.exposure(after, data["instruments"], data["holdings"]),
              "starting": ref.exposure(portfolio, data["instruments"], data["holdings"])}
    assert close(result["feasibility"]["cash_after"], float(after["_cash_after"]), 1e-12)
    got = by_rule(result)
    for rule in rules:
        entry = got[rule["rule_id"]]
        for state, exposure in states.items():
            lower, upper = ref.rule_bounds(rule, exposure, flagged=["BETA"])
            measured = entry["measured"] if state == "proposed" else entry["starting"]["measured"]
            status = entry["status"] if state == "proposed" else entry["starting"]["status"]
            assert close(measured["lower"], float(lower), 1e-12), (rule["rule_id"], state, measured, float(lower))
            assert close(measured["upper"], float(upper), 1e-12), (rule["rule_id"], state, measured, float(upper))
            expected_status = ref.status(rule["rule_type"], float(lower), float(upper), rule["threshold"])
            # Only compare the verdict when the exact value is not inside the float noise band around a threshold.
            margins = [abs(float(b) - rule["threshold"]) for b in (lower, upper)]
            if all(abs(m - EPS) > 1e-12 for m in margins):
                assert status == expected_status, (rule["rule_id"], state, status, expected_status, float(lower), float(upper))
            if state == "proposed" and status == expected_status:
                assert close(entry["gap"], ref.gap(rule["rule_type"], status, lower, upper, rule["threshold"]), 1e-12)
    # exposure chart rows agree as well
    for row in result["exposure"]["issuers"]:
        assert close(row["proposed"]["lower"], float(states["proposed"]["lower"].get(row["issuer_id"], 0)), 1e-12)
        assert close(row["starting"]["lower"], float(states["starting"]["lower"].get(row["issuer_id"], 0)), 1e-12)
    assert close(result["exposure"]["possible_extra"]["proposed"], float(states["proposed"]["U"]), 1e-12)


# --------------------------------------------------------------------------- V16 (metamorphic)

@pytest.mark.vcase("V16")
@pytest.mark.parametrize("seed", range(40))
def test_v16_exposure_is_additive_and_linear_in_the_weights(seed):
    rng = random.Random(1000 + seed)
    data = U.universe()
    a, weights_a = _random_portfolio(rng)
    b, weights_b = _random_portfolio(rng)
    lam = rng.choice([0.0, 0.25, 0.5, 0.75, 1.0])
    mixed_weights = {name: lam * weights_a.get(name, 0.0) + (1 - lam) * weights_b.get(name, 0.0) for name in set(weights_a) | set(weights_b)}
    mixed_weights = {k: v for k, v in mixed_weights.items() if v > 0}
    mixed = {"cash_weight": 1.0 - sum(mixed_weights.values()), "positions": [{"instrument_id": k, "weight": v} for k, v in mixed_weights.items()]}
    ea, eb, em = (compute_exposure(p, data["instruments"], data["holdings"]) for p in (a, b, mixed))
    for issuer in set(ea["lower"]) | set(eb["lower"]) | set(em["lower"]):
        expected = lam * ea["lower"].get(issuer, 0.0) + (1 - lam) * eb["lower"].get(issuer, 0.0)
        assert close(em["lower"].get(issuer, 0.0), expected, 1e-12), issuer
    assert close(em["possible_extra"], lam * ea["possible_extra"] + (1 - lam) * eb["possible_extra"], 1e-12)
    assert close(em["in_scope_weight"], lam * ea["in_scope_weight"] + (1 - lam) * eb["in_scope_weight"], 1e-12)
    # conservation: nothing counted twice, nothing lost (coverage <= 1 everywhere in this universe)
    assert close(sum(em["lower"].values()) + em["possible_extra"], em["in_scope_weight"], 1e-12)
    # scaling a whole portfolio by k scales every figure by k
    half = {"cash_weight": 0.0, "positions": [{"instrument_id": p["instrument_id"], "weight": p["weight"] / 2} for p in a["positions"]]}
    eh = compute_exposure(half, data["instruments"], data["holdings"])
    for issuer, value in ea["lower"].items():
        assert close(eh["lower"][issuer], value / 2, 1e-12)
    assert close(eh["possible_extra"], ea["possible_extra"] / 2, 1e-12)


@pytest.mark.vcase("V16")
@pytest.mark.parametrize("seed", range(40))
def test_v16_adding_a_fund_without_holdings_never_lowers_an_upper_bound_nor_changes_a_lower_bound(seed):
    """Move x of cash into F3 (no holdings file). Every max-type rule: lower unchanged, upper not lower, and a verdict
    can only move toward UNKNOWN (PASS -> PASS/UNKNOWN, FAIL -> FAIL, UNKNOWN -> UNKNOWN)."""
    rng = random.Random(2000 + seed)
    portfolio, weights = _random_portfolio(rng, pool=[name for name in POOL if name != "F3"], min_cash_units=5)
    extra = portfolio["cash_weight"] * rng.choice([0.25, 0.5, 1.0])
    richer = U.portfolio(portfolio["cash_weight"] - extra, {**weights, "F3": extra})
    rules = [r for r in _random_rules(rng) if r["rule_type"] != "min_issuer_exposure"] or [U.cap_any("r0", 0.2)]
    instrument = rng.choice(["AAA", "BBB", "CCC"])
    request = U.request(instrument, weights.get(instrument, 0.0))
    before, after = by_rule(check(portfolio, rules, request)), by_rule(check(richer, rules, request))
    for rule in rules:
        b, a = before[rule["rule_id"]], after[rule["rule_id"]]
        assert close(a["measured"]["lower"], b["measured"]["lower"], 1e-12), "a fund without holdings must not change what is known"
        assert a["measured"]["upper"] >= b["measured"]["upper"] - 1e-12, "a fund without holdings must never lower an upper bound"
        assert (b["status"], a["status"]) in {("PASS", "PASS"), ("PASS", "UNKNOWN"), ("UNKNOWN", "UNKNOWN"), ("FAIL", "FAIL")}
        assert close(a["measured"]["upper"] - b["measured"]["upper"], extra, 1e-12), "the whole unknown weight is possible exposure"
        assert "MISSING_HOLDINGS" in a["unknown_causes"]


@pytest.mark.vcase("V16")
@pytest.mark.parametrize("seed", range(40))
def test_v16_raising_a_cap_never_changes_measured_exposure_and_never_turns_pass_into_fail(seed):
    rng = random.Random(3000 + seed)
    portfolio, weights = _random_portfolio(rng)
    instrument = rng.choice(["AAA", "BBB", "F1", "F2"])
    request = U.request(instrument, min(1.0, weights.get(instrument, 0.0) + 0.05))
    order = {"FAIL": 0, "UNKNOWN": 1, "PASS": 2}
    for make in (lambda limit: U.cap_any("r", limit), lambda limit: U.exclude_sector("r", "Energy", limit),
                 lambda limit: U.exclude_named("r", ["ALPHA", "BETA"], limit)):
        previous = None
        for limit in (0.0, 0.05, 0.10, 0.20, 0.35, 0.60, 1.0):
            entry = by_rule(check(portfolio, [make(limit)], request))["r"]
            if previous is not None:
                assert entry["measured"] == previous["measured"], "the limit must not influence what is measured"
                assert order[entry["status"]] >= order[previous["status"]], f"raising the cap to {limit} worsened the verdict"
            previous = entry
        assert previous["status"] == "PASS", "a cap of 100% can never fail or be unknown"


@pytest.mark.vcase("V16")
@pytest.mark.parametrize("seed", SEEDS[:60])
def test_v16_lower_is_never_above_upper_and_all_fractions_stay_in_range(seed):
    portfolio, rules, request, data = _random_case(seed)
    result = check(portfolio, rules + [U.loss_budget("budget", 0.10)], request, data)
    for entry in result["rule_results"]:
        for measured in (entry["measured"], entry["starting"]["measured"]):
            if measured is not None:
                assert measured["lower"] <= measured["upper"] + 1e-15
        for subject in entry["breaching_subjects"]:
            assert subject["lower"] <= subject["upper"] + 1e-15
    for row in result["exposure"]["issuers"]:
        for state in ("starting", "proposed"):
            cell = row[state]
            assert 0 <= cell["direct"] <= cell["lower"] + 1e-15 <= cell["upper"] + 2e-15 <= 1 + 1e-9
            assert close(cell["direct"] + sum(p["known"] for p in cell["indirect_by_fund"]), cell["lower"], 1e-12)
    for fund in result["data_coverage"]:
        assert 0 <= fund["uncovered_portfolio_weight"] <= fund["portfolio_weight"] + 1e-15


# --------------------------------------------------------------------------- V17

@pytest.mark.vcase("V17")
@pytest.mark.parametrize("seed", SEEDS[:60])
def test_v17_status_gap_summary_and_headline_are_the_documented_functions(seed):
    portfolio, rules, request, data = _random_case(seed)
    rules = rules + [U.loss_budget("budget", 0.03), U.cap_any("draft", 0.5, status="PROPOSED")]
    result = check(portfolio, rules, request, data)
    statuses = []
    for entry in result["rule_results"]:
        measured = entry["measured"]
        lower, upper = (measured["lower"], measured["upper"]) if measured else (None, None)
        assert entry["status"] == ref.status(entry["rule_type"], lower, upper, entry["limit"])
        expected_gap = ref.gap(entry["rule_type"], entry["status"], lower, upper, entry["limit"])
        assert close(entry["gap"], expected_gap, 1e-15)
        if entry["status"] == "UNKNOWN":
            assert entry["unknown_causes"], "an UNKNOWN result names at least one cause"
            assert entry["gap"] is None
        if entry["status"] != "FAIL":
            assert entry["breaching_subjects"] == []
        statuses.append(entry["status"])
    summary = result["summary"]
    assert summary["counts"] == {"pass": statuses.count("PASS"), "fail": statuses.count("FAIL"), "unknown": statuses.count("UNKNOWN")}
    assert summary["rules_evaluated"] == len(statuses) and summary["rules_not_evaluated"] == 1
    assert summary["headline"] == ref.headline(result["execution"]["status"], result["policy_consistency"]["status"], statuses)
    assert summary["feasibility_status"] == result["feasibility"]["status"]
    assert summary["starting_portfolio_breaches"] == len(result["starting_portfolio_findings"])
    failing_at_start = [e["rule_id"] for e in result["rule_results"] if e["starting"]["status"] == "FAIL"]
    assert [f["rule_id"] for f in result["starting_portfolio_findings"]] == failing_at_start
    if summary["headline"] == "ALL_PASS":
        assert statuses and set(statuses) == {"PASS"}, "ALL_PASS with a rule that is not PASS would be a false pass"


@pytest.mark.vcase("V17")
@pytest.mark.parametrize("seed", SEEDS[:40])
def test_v17_result_is_deterministic_and_inputs_are_not_mutated(seed):
    portfolio, rules, request, data = _random_case(seed)
    policy = U.policy(rules + [U.loss_budget("budget", 0.05)])
    snapshot = copy.deepcopy((portfolio, policy, request, data))
    args = (portfolio, policy, request, data["instruments"], data["holdings"], data["market_data"], data["controversies"])
    first = check_rules(*args)
    second = check_rules(*args)
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    assert (portfolio, policy, request, data) == snapshot, "the engine mutated one of its inputs"
    json.dumps(first, allow_nan=False)  # a result is plain, finite JSON


@pytest.mark.vcase("V17")
def test_v17_engine_is_pure_no_io_clock_network_or_model_imports():
    """LEAD_DECISIONS D2: the engine is pure: no I/O, no AWS, no model, no clock; standard library only."""
    banned = re.compile(r"^\s*(?:import|from)\s+(boto3|botocore|requests|urllib|http|socket|subprocess|time|datetime\s+import\s+datetime|random|os|pathlib|numpy|pandas)\b", re.M)
    offenders = []
    for path in sorted((REPO_ROOT / "backend" / "engine").glob("*.py")):
        text = path.read_text(encoding="utf-8")
        for match in banned.finditer(text):
            offenders.append((path.name, match.group(0).strip()))
        if re.search(r"\bopen\(|datetime\.now|date\.today|time\.time", text):
            offenders.append((path.name, "I/O or clock call"))
    assert offenders == [], offenders


# --------------------------------------------------------------------------- V18

@pytest.mark.vcase("V18")
@pytest.mark.parametrize(
    "label, positions, instrument, target, mutate, missing",
    [
        ("held instrument has no price series", {"NOHIST": 0.20, "BND": 0.30}, "AAA", 0.10, None, ["NOHIST"]),
        ("requested instrument has no price series", {"AAA": 0.20, "BND": 0.30}, "NOHIST", 0.10, None, ["NOHIST"]),
        ("base price is 11 days old (limit 7)", {"AAA": 0.20, "BND": 0.30}, "STALE", 0.10, None, ["STALE"]),
        ("USD instrument and no FX series", {"AAB": 0.20, "BND": 0.30}, "AAA", 0.10, lambda d: d["market_data"].update(fx_usdcad=[]), ["AAB"]),
        ("USD instrument and an FX rate 11 days old", {"AAB": 0.20, "BND": 0.30}, "AAA", 0.10,
         lambda d: d["market_data"].update(fx_usdcad=[["2021-12-20", 1.2], ["2022-12-30", 1.3]]), ["AAB"]),
        ("history starts after the base date", {"AAA": 0.20, "BND": 0.30}, "BBB", 0.10,
         lambda d: d["market_data"]["prices"]["BBB"].update(series=[["2022-03-01", 100.0], ["2022-12-30", 130.0]]), ["BBB"]),
        ("history ends before the end date", {"AAA": 0.20, "BND": 0.30}, "BBB", 0.10,
         lambda d: d["market_data"]["prices"]["BBB"].update(series=[["2021-12-31", 100.0], ["2022-06-30", 120.0]]), ["BBB"]),
    ],
)
def test_v18_missing_history_is_unknown_never_a_proxy_or_zero(label, positions, instrument, target, mutate, missing):
    data = U.universe()
    if mutate:
        mutate(data)
    result = check(U.portfolio(0.50, positions), [U.loss_budget("budget", 0.10), U.cap_any("cap", 0.90)], U.request(instrument, target), data)
    scenario = result["scenario"]
    assert scenario["status"] == "INSUFFICIENT_HISTORY" and scenario["missing_instruments"] == missing
    assert scenario["starting"] is None and scenario["proposed"] is None, "one replay universe per check: no partial number"
    budget = by_rule(result)["budget"]
    assert budget["status"] == "UNKNOWN" and budget["measured"] is None and budget["gap"] is None
    assert budget["starting"] == {"status": "UNKNOWN", "measured": None}
    assert budget["unknown_causes"] == ["INSUFFICIENT_HISTORY"]
    assert all(row["instrument_id"] not in missing for row in scenario["instrument_returns"]), "no return may be invented for a missing instrument"
    assert by_rule(result)["cap"]["status"] == "PASS", "the other rules are still evaluated"
    assert result["summary"]["headline"] == "NO_FAIL_BUT_UNKNOWN"
    assert result["max_compliant"]["status"] == "WITHHELD" and result["max_compliant"]["final_direct_weight"] is None
    assert not [r for r in result["evidence"] if r["metric_id"] in ("scenario_terminal_return", "scenario_loss", "scenario_max_drawdown")]
    assert not [g for g in result["goal_context"] if g["context_type"] == "SCENARIO_DRAWDOWN"]


@pytest.mark.vcase("V18")
def test_v18_a_price_exactly_seven_days_old_is_usable_and_eight_is_not():
    for age_date, usable in (("2021-12-24", True), ("2021-12-23", False)):
        data = U.universe()
        data["market_data"]["prices"]["BBB"]["series"] = [[age_date, 100.0], ["2022-12-30", 130.0]]
        result = check(U.portfolio(0.50, {"BBB": 0.20, "BND": 0.30}), [U.loss_budget("budget", 0.10)], U.request("AAA", 0.0), data)
        assert (result["scenario"]["status"] == "COMPUTED") is usable


# --------------------------------------------------------------------------- V19

@pytest.mark.vcase("V19")
@pytest.mark.parametrize(
    "label, build",
    [
        ("negative position weight", lambda: {**U.portfolio(0.90, {"AAA": 0.20, "BND": 0.30}), "positions": [{"instrument_id": "AAA", "weight": -0.20}, {"instrument_id": "BND", "weight": 0.30}]}),
        ("weights add up to 0.90", lambda: U.portfolio(0.50, {"AAA": 0.20, "BND": 0.20})),
        ("weights add up to 1.10", lambda: U.portfolio(0.50, {"AAA": 0.30, "BND": 0.30})),
        ("instrument missing from the registry", lambda: U.portfolio(0.50, {"QQQQ": 0.20, "BND": 0.30})),
        ("the same instrument twice", lambda: {**U.portfolio(0.50, {"AAA": 0.20, "BND": 0.30}), "positions": [{"instrument_id": "AAA", "weight": 0.25}, {"instrument_id": "AAA", "weight": 0.25}]}),
        ("a percentage instead of a fraction", lambda: {**U.portfolio(0.50, {"AAA": 0.20, "BND": 0.30}), "positions": [{"instrument_id": "AAA", "weight": 20}, {"instrument_id": "BND", "weight": 30}], "cash_weight": 50}),
        ("negative cash", lambda: U.portfolio(-0.10, {"AAA": 0.60, "BND": 0.50})),
        ("not marked fictional", lambda: {**U.portfolio(0.50, {"AAA": 0.20, "BND": 0.30}), "fictional": False}),
    ],
)
def test_v19_contradictory_portfolio_is_refused_with_a_reason_and_no_number(label, build):
    result = check(build(), [U.cap_any("cap", 0.90)], U.request("BBB", 0.05))
    assert result["execution"]["status"] == "INVALID_REQUEST" and result["execution"]["code"] == "INVALID_PORTFOLIO", label
    assert result["execution"]["message"]
    assert result["rule_results"] == [] and result["evidence"] == [] and result["exposure"] is None
    assert result["summary"]["headline"] == "INVALID_REQUEST" and result["summary"]["counts"] == {"pass": 0, "fail": 0, "unknown": 0}


@pytest.mark.vcase("V19")
@pytest.mark.parametrize("target", [True, "25%", None, "0.25", [0.25]])
def test_v19_purchase_request_with_the_wrong_type_is_rejected_before_any_calculation(target):
    with pytest.raises(ContractError):
        check_rules(U.portfolio(0.50, {"AAA": 0.20, "BND": 0.30}), U.policy([U.cap_any("cap", 0.9)]),
                    {"instrument_id": "BBB", "target_direct_weight": target, "funding": "CASH", "original_words": None},
                    *[U.universe()[k] for k in ("instruments", "holdings", "market_data", "controversies")])


@pytest.mark.vcase("V19")
@pytest.mark.parametrize("threshold", [float("inf"), True, "0.9", 90, -0.1])
def test_v19_draft_rule_with_a_wrong_threshold_is_refused(threshold):
    draft = U.cap_any("cap", 0.1, status="PROPOSED")
    draft["threshold"] = threshold
    result = check(U.portfolio(0.50, {"AAA": 0.20, "BND": 0.30}), [draft], U.request("BBB", 0.05), preview=True, validate=False)
    assert result["execution"]["code"] == "INVALID_POLICY" and result["rule_results"] == []


NAN = float("nan")


@pytest.mark.vcase("V19")
@pytest.mark.xfail(strict=True, reason="V19a: a NaN position weight passes validate_portfolio and the engine silently drops the position "
                                       "(weight > 0 is false): ALPHA 0.20 against a 0.10 cap is reported PASS / ALL_PASS")
def test_v19_nan_position_weight_must_not_produce_a_verdict():
    portfolio = U.portfolio(0.50, {"AAA": 0.20, "BND": 0.30})
    portfolio["positions"][0]["weight"] = NAN
    result = check(portfolio, [U.cap_any("cap", 0.10)], U.request("BBB", 0.05), validate=False)
    assert result["execution"]["status"] != "OK", f"NaN weight accepted; headline {result['summary']['headline']}"
    assert result["rule_results"] == []


@pytest.mark.vcase("V19")
@pytest.mark.xfail(strict=True, reason="V19b: NaN cash weight / NaN target weight are evaluated with execution OK instead of INVALID_REQUEST")
@pytest.mark.parametrize("where", ["cash", "target"])
def test_v19_nan_cash_or_target_must_not_be_evaluated(where):
    portfolio = U.portfolio(0.50, {"AAA": 0.20, "BND": 0.30})
    request = U.request("BBB", 0.05)
    if where == "cash":
        portfolio["cash_weight"] = NAN
    else:
        request["target_direct_weight"] = NAN
    result = check(portfolio, [U.cap_any("cap", 0.10)], request, validate=False)
    assert result["execution"]["status"] != "OK"


@pytest.mark.vcase("V19")
@pytest.mark.xfail(strict=True, reason="V19c: a NaN price or NaN draft threshold yields UNKNOWN with NaN/empty cause fields "
                                       "(result is not finite JSON; SEMANTICS 6 requires a named cause)")
@pytest.mark.parametrize("where", ["price", "threshold"])
def test_v19_nan_market_or_threshold_value_must_be_refused_or_explained(where):
    data = U.universe()
    portfolio = U.portfolio(0.50, {"AAA": 0.20, "BND": 0.30})
    if where == "price":
        data["market_data"]["prices"]["AAA"]["series"][2][1] = NAN
        result = check(portfolio, [U.loss_budget("budget", 0.10)], U.request("BBB", 0.05), data, validate=False)
    else:
        draft = U.cap_any("cap", 0.1, status="PROPOSED")
        draft["threshold"] = NAN
        result = check(portfolio, [draft], U.request("BBB", 0.05), data, preview=True, validate=False)
    json.dumps(result, allow_nan=False)
    assert all(entry["unknown_causes"] for entry in result["rule_results"] if entry["status"] == "UNKNOWN")


@pytest.mark.vcase("V19")
def test_v19_nan_never_produces_a_pass_from_a_price_or_a_threshold():
    """Whatever else is wrong with NaN handling (V19c), these two paths must at least not be a PASS."""
    data = U.universe()
    data["market_data"]["prices"]["AAA"]["series"][2][1] = NAN
    portfolio = U.portfolio(0.50, {"AAA": 0.20, "BND": 0.30})
    result = check(portfolio, [U.loss_budget("budget", 0.10)], U.request("BBB", 0.05), data, validate=False)
    assert by_rule(result)["budget"]["status"] != "PASS" and result["summary"]["headline"] != "ALL_PASS"
    draft = U.cap_any("cap", 0.1, status="PROPOSED")
    draft["threshold"] = NAN
    result = check(portfolio, [draft], U.request("BBB", 0.05), preview=True, validate=False)
    assert by_rule(result)["cap"]["status"] != "PASS"


def _bad_snapshots():
    def rows_missing(d):  # rows sum to 0.30 while coverage_fraction still says 1.00
        fund = d["holdings"]["funds"]["F1"]
        fund["holdings"] = fund["holdings"][:2]

    def over_one(d):  # one weight typed as 0.90: rows sum to 1.70
        fund = d["holdings"]["funds"]["F1"]
        fund["holdings"][0]["weight_fraction"] = 0.90
        fund["coverage_fraction"] = 1.70

    def understated(d):  # coverage_fraction says 0.50 while rows sum to 1.00
        d["holdings"]["funds"]["F1"]["coverage_fraction"] = 0.50

    def no_issuer(d):
        d["holdings"]["funds"]["F1"]["holdings"][2]["issuer_id"] = ""

    def null_issuer(d):
        d["holdings"]["funds"]["F1"]["holdings"][2]["issuer_id"] = None

    def negative_weight(d):
        d["holdings"]["funds"]["F1"]["holdings"][2]["weight_fraction"] = -0.30

    def percent_weights(d):
        fund = d["holdings"]["funds"]["F1"]
        for row in fund["holdings"]:
            row["weight_fraction"] *= 100
        fund["coverage_fraction"] = 100.0

    return [rows_missing, over_one, understated, no_issuer, null_issuer, negative_weight, percent_weights]


@pytest.mark.vcase("V19")
@pytest.mark.parametrize("corrupt", _bad_snapshots(), ids=lambda f: f.__name__)
def test_v19_contract_validator_rejects_an_inconsistent_holdings_snapshot(corrupt):
    data = U.universe()
    validate_holdings_snapshot(data["holdings"])  # the clean universe is valid
    corrupt(data)
    with pytest.raises(ContractError):
        validate_holdings_snapshot(data["holdings"])


@pytest.mark.vcase("V19")
def test_v19_validator_universe_is_contract_valid():
    data = U.universe()
    validate_instrument_registry(data["instruments"])
    validate_holdings_snapshot(data["holdings"])
    validate_market_data(data["market_data"])


@pytest.mark.vcase("V19")
def test_v19_market_data_validator_rejects_unsorted_or_duplicate_dates():
    data = U.universe()
    data["market_data"]["prices"]["AAA"]["series"].reverse()
    with pytest.raises(ContractError):
        validate_market_data(data["market_data"])
    data = U.universe()
    data["market_data"]["fx_usdcad"].append(["2022-12-28", 1.40])
    with pytest.raises(ContractError):
        validate_market_data(data["market_data"])


def _production_sources() -> dict[str, str]:
    out = {}
    for package in ("api", "worker", "agents", "common", "engine"):
        for path in sorted((REPO_ROOT / "backend" / package).rglob("*.py")):
            out[str(path.relative_to(REPO_ROOT))] = path.read_text(encoding="utf-8")
    return out


@pytest.mark.vcase("V19")
@pytest.mark.xfail(strict=True, reason="V19d: no production code path validates the data snapshots (holdings, instruments, market data, "
                                       "controversies) before the engine uses them; the engine trusts coverage_fraction and row contents, "
                                       "so an inconsistent snapshot yields PASS / COVERED / a SUPPORTED maximum")
def test_v19_production_code_validates_every_data_snapshot_before_use():
    """Static check with a behavioural witness in the report (REPORT.md, finding V19d).

    The contract validators reject every corrupted snapshot above, but in this checkout they are called only from
    tests. Whoever loads the snapshots for the engine (the worker's data loader, POST /check) must call them and turn
    a failure into DATA_UNAVAILABLE / an execution error, never into a verdict."""
    sources = _production_sources()
    needed = ["validate_holdings_snapshot", "validate_instrument_registry", "validate_market_data", "validate_controversy_registry"]
    missing = [name for name in needed if not any(name in text for text in sources.values())]
    assert missing == [], f"never called from backend/ production code: {missing}"


@pytest.mark.vcase("V19")
def test_v19_constituent_outside_the_instrument_registry_is_still_counted():
    """BUILD_BRIEF section 4: fund constituents are not restricted to the starter universe. An issuer that exists
    only as a holdings row (EPSILON, no registry entry) must count, not vanish."""
    data = U.universe()
    fund = data["holdings"]["funds"]["F1"]
    fund["holdings"][3].update(issuer_id="EPSILON", instrument_id="EPS", name="Epsilon (validator synthetic)")
    result = check(U.portfolio(0.50, {"F1": 0.50}), [U.cap_any("cap", 0.15)], U.request("AAA", 0.0), data)
    rule = by_rule(result)["cap"]
    assert rule["status"] == "FAIL" and close(rule["measured"]["lower"], 0.20)  # EPSILON = 0.50 x 0.40
    assert rule["breaching_subjects"][0]["subject_id"] == "EPSILON"


@pytest.mark.vcase("V19")
@pytest.mark.parametrize("corrupt", ["null_issuer", "missing_issuer_key", "zero_price"])
def test_v19_unusable_rows_end_in_a_visible_engine_error_not_a_verdict(corrupt):
    data = U.universe()
    rules = [U.cap_any("cap", 0.20), U.loss_budget("budget", 0.10)]
    if corrupt == "null_issuer":
        data["holdings"]["funds"]["F1"]["holdings"][2]["issuer_id"] = None
    elif corrupt == "missing_issuer_key":
        del data["holdings"]["funds"]["F1"]["holdings"][2]["issuer_id"]
    else:
        data["market_data"]["prices"]["F1"]["series"][0][1] = 0.0
    result = check(U.portfolio(0.50, {"F1": 0.50}), rules, U.request("CCC", 0.0), data)
    assert result["execution"]["status"] == "ERROR" and result["execution"]["code"] == "ENGINE_ERROR"
    assert result["rule_results"] == [] and result["max_compliant"] is None
    assert result["summary"]["headline"] == "EXECUTION_ERROR"
