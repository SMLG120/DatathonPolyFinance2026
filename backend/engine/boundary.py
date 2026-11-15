"""Maximum compliant final direct weight: a closed form, verified by re-running the evaluator.

Targets considered are ``T = (w0, w0 + cash_before]``. With ``d = w - w0``
every measured bound is affine in ``d`` (exposure is linear in the position
weights; the scenario loss is linear by the D6 identity
``R(w) = R(w0) + (w - w0) x r``), so for each rule the targets where it PASSES
form an interval and the targets where it is a proven FAIL form rays. Their
ends solve a linear equation: there is no search of any kind.

The ends are the exact solutions of the inequalities (the comparison tolerance
EPS is not spent as extra budget); EPS only absorbs floating-point noise.
"""

from __future__ import annotations

from typing import Any, Optional

from byb_contracts import EPS

from . import rules as R
from .core import compute_exposure
from .text import eq, num, pct

INF = float("inf")


def _withheld(reason: str) -> dict:
    return {"status": "WITHHELD", "final_direct_weight": None, "additional_purchase": None, "binding_constraint": None,
            "verified_by_rerun": False, "reason": reason, "evidence_ids": []}


def _no_purchase(kind: str, rule_id: Optional[str], reason: str) -> dict:
    return {"status": "NO_FEASIBLE_PURCHASE", "final_direct_weight": None, "additional_purchase": None,
            "binding_constraint": {"type": kind, "rule_id": rule_id}, "verified_by_rerun": False, "reason": reason, "evidence_ids": []}


def _at_most(a: float, b: float, limit: float) -> Optional[tuple[float, float]]:
    """Interval of d where a + b d <= limit; None when empty."""
    if b == 0:
        return (-INF, INF) if a <= limit + EPS else None
    edge = (limit - a) / b
    return (-INF, edge) if b > 0 else (edge, INF)


def _above(a: float, b: float, limit: float) -> Optional[tuple[str, float]]:
    """Where a + b d > limit: ("ALL", 0), ("UP", x) meaning d > x, ("DOWN", x) meaning d < x, or None."""
    if b == 0:
        return ("ALL", 0.0) if a > limit + EPS else None
    edge = (limit - a) / b
    return ("UP", edge) if b > 0 else ("DOWN", edge)


def linear_components(rule: dict, start: dict, unit: dict, flagged: Optional[dict], loss_start: Optional[float], unit_return: Optional[float]) -> Optional[list]:
    """The rule's bounds as affine functions of d: a list of (issuer, lower a, lower b, upper a, upper b).

    ``issuer`` names the company a component of the any-issuer cap is about; it is None otherwise.

    ``start`` is the exposure of the starting portfolio, ``unit`` the exposure of
    one unit of the requested instrument. A max-type rule PASSES when every
    component's upper is within the limit and FAILS when any component's lower
    is above it. None means the bounds are not computable (no usable history).
    """
    kind = R.rule_kind(rule)
    if kind == "SCENARIO":
        if loss_start is None or unit_return is None:
            return None
        return [(None, loss_start, -unit_return, loss_start, -unit_return)]
    extra_a, extra_b = start["possible_extra"], unit["possible_extra"]
    if kind == "ANY_ISSUER":
        components = [(None, 0.0, 0.0, extra_a, extra_b)]
        for issuer in sorted(set(start["lower"]) | set(unit["lower"])):
            a, b = start["lower"].get(issuer, 0.0), unit["lower"].get(issuer, 0.0)
            components.append((issuer, a, b, a + extra_a, b + extra_b))
        return components
    a = R.exposure_bounds(rule, start, flagged)
    b = R.exposure_bounds(rule, unit, flagged)
    return [(None, a["lower"], b["lower"], a["upper"], b["upper"])]


def solve_max_compliant(analysis: dict, portfolio, policy, request, instruments, holdings, market_data, controversies,
                        draft_rules=None, data_sources=None) -> tuple[dict, dict]:
    """(max_compliant section, detail). ``analysis`` is ``check.analyse`` of the same inputs."""
    evaluated = analysis["evaluated"]
    feasibility = analysis["sim"]["feasibility"]
    instrument_id = request["instrument_id"]
    start_weight, cash = feasibility["starting_direct_weight"], feasibility["cash_before"]
    detail: dict = {"formula": None, "rules": {}}
    if analysis["conflicts"]:
        return _withheld("Withheld: the policy contains a proven conflict between rules, so no weight can satisfy every rule."), detail
    if not evaluated:
        return _withheld("Withheld: no confirmed rule with a numeric threshold was evaluated, so there is nothing to be compliant with."), detail
    if cash <= EPS:
        return _no_purchase("CASH", None, "No purchase can be funded: the portfolio holds no cash and the purchase path is cash only."), detail

    start = analysis["exposure"]["starting"]
    unit = compute_exposure({"cash_weight": 0.0, "positions": [{"instrument_id": instrument_id, "weight": 1.0}]}, analysis["registry"], holdings)
    loss_start, unit_return = None, None
    replay = analysis["replay"]
    if replay is not None:
        histories = replay["histories"]
        usable = all(histories.get(p["instrument_id"]) is not None for p in analysis["sim"]["starting_portfolio"]["positions"] if p["weight"] > 0)
        if usable and replay["target"] is not None:
            unit_return = replay["target"]["return_cad"]
            starting = analysis["sim"]["starting_portfolio"]
            loss_start = 0.0 - sum(p["weight"] * histories[p["instrument_id"]]["return_cad"] for p in starting["positions"] if p["weight"] > 0)

    pass_low, pass_high = 0.0, cash
    unknown_rules, rule_high = [], {}
    fail_rays: dict[str, list] = {}
    for rule in evaluated:
        rule_id, limit = rule["rule_id"], rule["threshold"]
        components = linear_components(rule, start, unit, analysis["flagged"].get(rule_id), loss_start, unit_return)
        if components is None:
            unknown_rules.append(rule_id)
            rule_high[rule_id] = None
            fail_rays[rule_id] = []
            continue
        low, high, rays, limiting = -INF, INF, [], None
        for issuer, lower_a, lower_b, upper_a, upper_b in components:
            if rule["rule_type"] == "min_issuer_exposure":
                passing = _at_most(-lower_a, -lower_b, -limit)
                failing = _above(-upper_a, -upper_b, -limit)
            else:
                passing = _at_most(upper_a, upper_b, limit)
                failing = _above(lower_a, lower_b, limit)
            if passing is None:
                low, high = INF, -INF
            else:
                if passing[1] < high and rule["rule_type"] != "min_issuer_exposure":
                    # The component whose upper bound reaches the limit first: it sets this rule's upper end.
                    limiting = {"issuer": issuer, "start_upper": upper_a, "slope": upper_b}
                low, high = max(low, passing[0]), min(high, passing[1])
            if failing is not None:
                rays.append(failing)
        rule_high[rule_id] = (low, high) if low <= high + EPS else None
        fail_rays[rule_id] = rays
        if rule_high[rule_id] is None:
            pass_low, pass_high = INF, -INF
        else:
            pass_low, pass_high = max(pass_low, low), min(pass_high, high)
        detail["rules"][rule_id] = {"pass_interval": rule_high[rule_id], "fail_rays": rays, "limiting": limiting}

    # SUPPORTED: some funded target more than EPS above w0 where every rule is PASS.
    if not unknown_rules and pass_high > EPS and pass_low <= pass_high + EPS:
        final = min(1.0, round(start_weight + pass_high, 9))
        additional = final - start_weight
        binding = next((r["rule_id"] for r in evaluated if rule_high[r["rule_id"]][1] <= pass_high + EPS), None)
        from .check import check_rules
        rerun = check_rules(portfolio, policy, {**request, "target_direct_weight": final}, instruments, holdings, market_data,
                            controversies, draft_rules=draft_rules, data_sources=data_sources, include_max_compliant=False)
        confirmed = (
            rerun["execution"]["status"] == "OK"
            and rerun["feasibility"]["status"] == "FEASIBLE"
            and len(rerun["rule_results"]) == len(evaluated)
            and all(entry["status"] == "PASS" for entry in rerun["rule_results"])
        )
        if not confirmed or additional <= EPS:
            return _withheld("Withheld: the closed-form boundary was not confirmed when the same checks were re-run at that weight."), detail
        ends = []
        for rule in evaluated:
            limiting = detail["rules"][rule["rule_id"]]["limiting"]
            if limiting is None:
                ends.append(f"{rule['rule_id']}: passes at every funded weight above its lower end, no upper end")
                continue
            who = f" ({limiting['issuer']})" if limiting["issuer"] else ""
            ends.append(
                f"{rule['rule_id']}{who}: {num(start_weight)} + ({num(rule['threshold'])} - {num(limiting['start_upper'])}) / {num(limiting['slope'])} "
                f"{eq(start_weight + rule_high[rule['rule_id']][1])}"
            )
        ends.append(f"cash: {num(start_weight)} + {num(cash)} {eq(start_weight + cash)}")
        detail["formula"] = (
            "upper end of each constraint, as starting direct weight + (limit - measured value before the purchase) / "
            "(change of that value per unit of weight bought): " + "; ".join(ends)
            + f". Largest final direct weight at which every evaluated rule passes: the smallest of these, rounded to 9 decimals {eq(final)}"
        )
        what = f"the rule {binding} stops passing just above it" if binding else "cash runs out there"
        return {
            "status": "SUPPORTED",
            "final_direct_weight": final,
            "additional_purchase": additional,
            "binding_constraint": {"type": "RULE", "rule_id": binding} if binding else {"type": "CASH", "rule_id": None},
            "verified_by_rerun": True,
            "reason": (
                f"The largest final direct weight of {instrument_id} at which every evaluated rule passes with cash funding is "
                f"{num(final)} of the portfolio ({pct(final)}), an additional purchase of {num(additional)} ({pct(additional)}); {what}. "
                "Verified by re-running the same checks at that weight."
            ),
            "evidence_ids": [],
        }, detail

    # NO_FEASIBLE_PURCHASE: every funded target has at least one proven FAIL.
    everywhere = False
    up = min((edge for rays in fail_rays.values() for kind, edge in rays if kind == "UP"), default=INF)
    down = max((edge for rays in fail_rays.values() for kind, edge in rays if kind == "DOWN"), default=-INF)
    if any(kind == "ALL" for rays in fail_rays.values() for kind, _ in rays) or up <= EPS or down > cash + EPS or up < down:
        everywhere = True
    if everywhere:
        for rule in evaluated:
            for kind, edge in fail_rays[rule["rule_id"]]:
                if kind == "ALL" or (kind == "UP" and edge <= EPS) or (kind == "DOWN" and edge > EPS):
                    return _no_purchase(
                        "RULE", rule["rule_id"],
                        f"No purchase of {instrument_id} that cash can fund avoids a proven failure: the rule {rule['rule_id']} "
                        "already fails for any target just above the current weight.",
                    ), detail

    if unknown_rules:
        why = "no usable price history for the scenario rule(s) " + ", ".join(unknown_rules)
    else:
        why = "missing or partial data leaves at least one rule UNKNOWN at every target that is not a proven failure"
    return _withheld(f"Withheld: no target weight is proven to pass every evaluated rule, and not every target is proven to fail ({why}). Unknown data never yields a number."), detail


def max_compliant_amount(
    portfolio: dict,
    policy: Optional[dict],
    purchase_request: dict,
    instruments: Any,
    holdings: Any,
    market_data: Any,
    controversies: Any,
    *,
    draft_rules: Optional[list] = None,
) -> dict:
    """The ``max_compliant`` section for the requested instrument (SEMANTICS section 11).

    It depends on the instrument, not on the requested target. A request that is
    not executed (``execution.status`` other than OK) raises ``ValueError``.
    ``evidence_ids`` is empty here; ``check_rules`` attaches the evidence.
    """
    from .check import analyse
    if policy is None and draft_rules is None:
        raise ValueError("max_compliant_amount needs a policy, or draft_rules for a preview")
    analysis = analyse(portfolio, policy, purchase_request, instruments, holdings, market_data, controversies, draft_rules)
    if not analysis["ok"]:
        execution = analysis["sim"]["execution"]
        raise ValueError(f"the request was not executed ({execution['code']}): {execution['message']}")
    section, _ = solve_max_compliant(analysis, portfolio, policy, purchase_request, instruments, holdings, market_data, controversies, draft_rules)
    return section
