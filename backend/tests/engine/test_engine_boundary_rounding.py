"""Regression tests for the boundary rounding defect fixed in byb-engine-1.0.2.

Before the fix the maximum compliant weight was ``round(exact end, 9)``: rounding to the NEAREST 9-decimal number.
With an exact end of 0.0860000006 that returned 0.086000001, which is above the end and passed the re-run only
because comparisons allow ``EPS = 1e-9``; the rule's PASS then carried a positive gap of 4e-10.

The contract (boundary.py header, docs/PLAN.md P8): the returned weight is rounded DOWN and is feasible without
using the tolerance.

Tolerances used here, stated once:

* ``NOISE = 1e-12``: floating-point representation error only. It is 1000 times smaller than EPS, so a pass
  "within NOISE" is a pass without the EPS budget.
* ``GRID = 1e-9``: the serialized precision of a weight; "the next step" is one GRID above the returned weight.
"""

import random

import pytest
from byb_contracts import EPS, check_result_errors, compute_content_hash

from backend import engine
from backend.engine.boundary import FLOAT_NOISE, floor_to_grid
from engine_helpers import all_pass_and_funded, case, run_case

NOISE = 1e-12
GRID = 1e-9
CAP, BUDGET = "robert-issuer-cap-1", "robert-loss-budget-1"


def _policy(cap=None, budget=None):
    """R1's policy with other thresholds; the content hash is recomputed, as the server would."""
    policy = case("R1")["inputs"]["policy"]
    for entry in policy["rules"]:
        if entry["rule_id"] == CAP and cap is not None:
            entry["threshold"] = cap
        if entry["rule_id"] == BUDGET and budget is not None:
            entry["threshold"] = budget
    policy["content_hash"] = compute_content_hash(policy)
    return policy


def _entry(result, rule_id):
    return next(entry for entry in result["rule_results"] if entry["rule_id"] == rule_id)


def test_tolerances_are_what_this_file_says():
    assert FLOAT_NOISE == NOISE and NOISE * 1000 == pytest.approx(EPS)


@pytest.mark.parametrize("value, expected", [
    (0.0860000006, 0.086),              # the defect: nearest is 0.086000001
    (0.0860000004, 0.086),
    (0.08599999999999999, 0.086),       # float noise below an exact 0.086 must not lose a whole step
    (0.086, 0.086),
    (0.08600000099, 0.086),               # 1e-11 below the next grid point: more than noise, so rounded down
    (0.08600000099999999, 0.086000001), # float noise below an exact 0.086000001
    (0.086000001, 0.086000001),
    (0.3, 0.3),
    (0.1 + 0.2, 0.3),                   # 0.30000000000000004
    (1e-9, 1e-9),
    (0.9999999999, 0.999999999),
])
def test_floor_to_grid(value, expected):
    assert floor_to_grid(value) == expected
    assert floor_to_grid(value) <= value + NOISE


def test_reproduction_issuer_cap_just_above_a_grid_point():
    """R1 with the loss budget loosened to 0.9 so the issuer cap binds, cap = 0.1000000006.

    Exact end = 0.1000000006 - 0.014 (NVIDIA through the funds, upper bound) = 0.0860000006.
    Version 1.0.1 returned 0.086000001 with measured upper 0.100000001 (4e-10 above the cap, PASS by EPS).
    """
    limit = 0.1000000006
    policy = _policy(cap=limit, budget=0.9)
    result = run_case("R1", policy=policy)
    assert check_result_errors(result) == []
    maximum = result["max_compliant"]
    assert maximum["status"] == "SUPPORTED" and maximum["verified_by_rerun"] is True
    assert maximum["binding_constraint"] == {"type": "RULE", "rule_id": CAP}
    assert maximum["final_direct_weight"] == 0.086

    at = run_case("R1", policy=policy, target=maximum["final_direct_weight"])
    assert all_pass_and_funded(at)
    cap = _entry(at, CAP)
    assert cap["status"] == "PASS"
    assert cap["measured"]["upper"] <= limit + NOISE  # within the limit WITHOUT the EPS tolerance
    assert cap["gap"] <= NOISE                        # a PASS at the boundary carries no positive gap

    # The weight version 1.0.1 returned: it is above the exact end.
    wrong = run_case("R1", policy=policy, target=0.086000001)
    assert _entry(wrong, CAP)["measured"]["upper"] > limit + NOISE


def test_cap_just_below_the_rounding_midpoint_is_unchanged():
    result = run_case("R1", policy=_policy(cap=0.1000000004, budget=0.9))
    assert result["max_compliant"]["final_direct_weight"] == 0.086


def test_a_boundary_exactly_on_the_grid_is_returned_exactly():
    """Cap 0.1: the exact end is 0.086, computed in floats as 0.08600000000000001 or 0.08599999999999999."""
    result = run_case("R1", policy=_policy(cap=0.1, budget=0.9))
    assert result["max_compliant"]["final_direct_weight"] == 0.086
    at = run_case("R1", policy=_policy(cap=0.1, budget=0.9), target=0.086)
    assert abs(_entry(at, CAP)["gap"]) <= NOISE


def _thresholds(seed, count, low, high):
    """Deterministic pseudo-random limits with 11 decimals whose digits after the ninth are 05..95.

    That keeps every exact end at least 5e-11 away from a grid point, so "one step above the returned weight
    is beyond the limit" is decidable with NOISE = 1e-12 and no appeal to EPS.
    """
    generator = random.Random(seed)
    values = []
    for _ in range(count):
        grid = generator.randrange(int(low * 1e9), int(high * 1e9))
        tail = generator.randrange(5, 96)
        values.append((grid * 100 + tail) / 1e11)
    return values


@pytest.mark.parametrize("binding_rule", [CAP, BUDGET])
def test_returned_weight_is_within_the_limit_without_eps_and_one_step_more_is_not(binding_rule):
    """300 seeded thresholds per binding rule (issuer cap: slope 1; loss budget: slope 0.35 in the synthetic universe)."""
    if binding_rule == CAP:
        limits = _thresholds(20261114, 300, 0.07, 0.30)
        policies = [(limit, _policy(cap=limit, budget=0.9)) for limit in limits]
    else:
        limits = _thresholds(20261115, 300, 0.07, 0.16)
        policies = [(limit, _policy(cap=0.9, budget=limit)) for limit in limits]

    checked = 0
    for limit, policy in policies:
        result = run_case("R1", policy=policy)
        maximum = result["max_compliant"]
        assert maximum["status"] == "SUPPORTED", limit
        if maximum["binding_constraint"]["type"] == "CASH":
            continue  # a limit so loose that cash runs out first: the step-above property is about rules
        assert maximum["binding_constraint"]["rule_id"] == binding_rule, limit
        final = maximum["final_direct_weight"]
        assert final == round(final, 9)

        at = run_case("R1", policy=policy, target=final)
        assert all_pass_and_funded(at), limit
        entry = _entry(at, binding_rule)
        assert entry["measured"]["upper"] <= limit + NOISE, (limit, final, entry["measured"])
        assert all(other["gap"] <= NOISE for other in at["rule_results"]), limit
        assert at["feasibility"]["cash_after"] >= -NOISE

        above = run_case("R1", policy=policy, target=round(final + GRID, 9))
        beyond = _entry(above, binding_rule)
        # One grid step more exceeds the limit itself (it may still be labelled PASS by the EPS comparison
        # tolerance; that label is exactly what the returned maximum must never rely on).
        assert beyond["measured"]["upper"] > limit + NOISE, (limit, final, beyond["measured"])
        checked += 1
    assert checked >= 200


def test_cash_bound_boundary_never_exceeds_cash():
    """Rules loose, cash 0.3: the end is the cash, and cash after the purchase is not negative beyond float noise."""
    policy = _policy(cap=0.9, budget=0.9)
    result = run_case("R1", policy=policy)
    maximum = result["max_compliant"]
    assert maximum["binding_constraint"] == {"type": "CASH", "rule_id": None}
    assert maximum["final_direct_weight"] == 0.3
    at = run_case("R1", policy=policy, target=0.3)
    assert at["feasibility"]["status"] == "FEASIBLE" and at["feasibility"]["cash_after"] >= -NOISE


def test_version_was_bumped_for_the_formula_change():
    assert engine.CALCULATION_VERSION == "byb-engine-1.0.2"
