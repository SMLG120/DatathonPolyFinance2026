"""Per-rule measurement on one portfolio state, and the proven-conflict check.

Statuses and gaps are never derived here by hand: ``status_from_bounds`` and
``gap_from_bounds`` from the contracts package are the single definition.
"""

from __future__ import annotations

from typing import Any, Optional

from byb_contracts import (
    EPS,
    ISSUER_SCOPE_ANY,
    MAX_BREACHING_SUBJECTS,
    gap_from_bounds,
    status_from_bounds,
)



def as_fraction(value: float) -> float:
    """Keep a share inside [0, 1] when only tolerance-sized noise takes it out.

    Portfolio weights may add up to 1 within EPS, so a sum of shares can exceed
    1 by that much; fields the schema types as a fraction are clipped by at
    most EPS. Anything further out is left alone so that it is noticed.
    """
    if 1.0 < value <= 1.0 + EPS:
        return 1.0
    if -EPS <= value < 0.0:
        return 0.0
    return value


def flagged_issuers(criteria: dict, records: list) -> dict[str, list]:
    """issuer_id -> matching registry records (nature in the list, event on or after the optional date)."""
    natures = set(criteria["natures"])
    since = criteria.get("event_date_from")
    flagged: dict[str, list] = {}
    for record in records:
        if record["nature"] in natures and (since is None or record["event_date"] >= since):
            flagged.setdefault(record["issuer_id"], []).append(record)
    return flagged


def rule_kind(rule: dict) -> str:
    """ANY_ISSUER, ONE_ISSUER, NAMED, SECTOR, CONTROVERSY or SCENARIO."""
    rule_type = rule["rule_type"]
    if rule_type == "max_issuer_exposure":
        return "ANY_ISSUER" if rule["parameters"]["issuer_scope"] == ISSUER_SCOPE_ANY else "ONE_ISSUER"
    if rule_type == "min_issuer_exposure":
        return "ONE_ISSUER"
    if rule_type == "exclusion":
        return "NAMED" if rule["parameters"]["definition"]["kind"] == "named_issuers" else "SECTOR"
    if rule_type == "controversy_exclusion":
        return "CONTROVERSY"
    if rule_type == "scenario_loss_budget":
        return "SCENARIO"
    raise ValueError(f"unsupported rule_type {rule_type!r}")


def rule_issuer(rule: dict) -> Optional[str]:
    """The single issuer a ONE_ISSUER rule is about."""
    if rule["rule_type"] == "min_issuer_exposure":
        return rule["parameters"]["issuer_id"]
    if rule["rule_type"] == "max_issuer_exposure" and rule["parameters"]["issuer_scope"] != ISSUER_SCOPE_ANY:
        return rule["parameters"]["issuer_scope"]
    return None


def named_issuers(rule: dict) -> list[str]:
    """Issuers named in the rule's parameters (for the exposure chart)."""
    kind = rule_kind(rule)
    if kind == "ONE_ISSUER":
        return [rule_issuer(rule)]
    if kind == "NAMED":
        return list(rule["parameters"]["definition"]["issuer_ids"])
    return []


def path_filter(rule: dict, flagged: Optional[dict]):
    """Predicate over look-through paths: does this known exposure count toward the rule's lower bound?"""
    kind = rule_kind(rule)
    if kind == "ONE_ISSUER":
        issuer = rule_issuer(rule)
        return lambda path: path["issuer_id"] == issuer
    if kind == "NAMED":
        names = set(rule["parameters"]["definition"]["issuer_ids"])
        return lambda path: path["issuer_id"] in names
    if kind == "SECTOR":
        label = rule["parameters"]["definition"]["sector"]
        return lambda path: path["sector"] == label  # exact, case-sensitive; null never matches
    if kind == "CONTROVERSY":
        return lambda path: path["issuer_id"] in flagged
    raise ValueError(f"no path filter for rule kind {kind}")


def exposure_bounds(rule: dict, exposure: dict, flagged: Optional[dict]) -> dict:
    """Lower and upper bound of an exposure rule on one state (SEMANTICS section 6 table).

    Also returns what the evidence and the boundary need: the issuers that
    count (``contributors``: issuer -> counted known exposure), the per-position
    contributions (``parts``) and, for the any-issuer cap, the issuer that
    carries the maximum (``top_issuer``).
    """
    kind = rule_kind(rule)
    extra = exposure["possible_extra"]
    lower_by_issuer = exposure["lower"]
    if kind == "ANY_ISSUER":
        top = None
        for issuer in sorted(lower_by_issuer):
            if top is None or lower_by_issuer[issuer] > lower_by_issuer[top]:
                top = issuer
        lower = lower_by_issuer[top] if top is not None else 0.0
        return {"lower": lower, "upper": lower + extra, "top_issuer": top, "contributors": dict(lower_by_issuer), "parts": []}

    counts = path_filter(rule, flagged)
    contributors: dict[str, float] = {}
    by_position: dict[str, dict] = {}
    for path in exposure["paths"]:
        if not counts(path):
            continue
        contributors[path["issuer_id"]] = contributors.get(path["issuer_id"], 0.0) + path["weight"]
        part = by_position.setdefault(path["position_id"], {"position_id": path["position_id"], "kind": path["kind"], "known": 0.0, "fund_fraction": 0.0})
        part["known"] += path["weight"]
        if path["kind"] == "FUND":
            part["fund_fraction"] += path["fund_fraction"]
    parts = list(by_position.values())
    lower = sum((part["known"] for part in parts), 0.0)
    if kind == "SECTOR":
        upper = lower + extra + exposure["unclassified_weight"]
    elif kind == "CONTROVERSY":
        upper = exposure["in_scope_weight"]
    else:
        upper = lower + extra
    return {"lower": lower, "upper": max(upper, lower), "top_issuer": None, "contributors": contributors, "parts": parts}


def breaching_subjects(rule: dict, status: str, bounds: dict, exposure: dict) -> list[dict]:
    """Issuers whose proven exposure causes a FAIL, each with its own bounds; empty otherwise."""
    if status != "FAIL" or rule["rule_type"] not in ("max_issuer_exposure", "exclusion", "controversy_exclusion"):
        return []
    kind = rule_kind(rule)
    limit = rule["threshold"]
    lower_by_issuer = exposure["lower"]
    if kind == "ANY_ISSUER":
        issuers = [issuer for issuer, value in lower_by_issuer.items() if value > limit + EPS]
    elif kind == "ONE_ISSUER":
        issuers = [rule_issuer(rule)]
    else:
        issuers = [issuer for issuer, value in bounds["contributors"].items() if value > 0]
    subjects = [
        {
            "subject_kind": "ISSUER",
            "subject_id": issuer,
            "lower": as_fraction(lower_by_issuer.get(issuer, 0.0)),
            "upper": as_fraction(lower_by_issuer.get(issuer, 0.0) + exposure["possible_extra"]),
        }
        for issuer in issuers
    ]
    subjects.sort(key=lambda subject: (-subject["lower"], subject["subject_id"]))
    return subjects[:MAX_BREACHING_SUBJECTS]


def unknown_causes(rule: dict, bounds: Optional[dict], exposure: dict) -> list[str]:
    """Why lower != upper (or why nothing is computable) on the evaluated state."""
    if rule["rule_type"] == "scenario_loss_budget":
        return [] if bounds is not None else ["INSUFFICIENT_HISTORY"]
    causes = []
    statuses = {fund["status"] for fund in exposure["funds"]}
    if "PARTIAL" in statuses:
        causes.append("PARTIAL_HOLDINGS")
    if "MISSING" in statuses:
        causes.append("MISSING_HOLDINGS")
    kind = rule_kind(rule)
    if kind == "SECTOR" and exposure["unclassified_weight"] > 0:
        causes.append("UNCLASSIFIED_SECTOR")
    if kind == "CONTROVERSY" and bounds["upper"] > bounds["lower"]:
        causes.append("REGISTRY_ABSENCE")
    return causes


def evaluate(rule: dict, bounds: Optional[dict], exposure: Optional[dict]) -> dict:
    """Status, measured bounds, gap and breaching subjects of one rule on one state."""
    limit = rule["threshold"]
    rule_type = rule["rule_type"]
    lower = bounds["lower"] if bounds else None
    upper = bounds["upper"] if bounds else None
    status = status_from_bounds(rule_type, lower, upper, limit)
    return {
        "status": status,
        "measured": {"lower": lower, "upper": upper} if bounds else None,
        "gap": gap_from_bounds(rule_type, status, lower, upper, limit),
        "breaching_subjects": breaching_subjects(rule, status, bounds, exposure) if bounds and exposure else [],
        "bounds": bounds,
    }


def proven_conflicts(evaluated: list) -> list[dict]:
    """MIN_EXCEEDS_MAX_SAME_ISSUER: the only conflict schema version 1 can prove (SEMANTICS section 8)."""
    minimums = [rule for rule in evaluated if rule["rule_type"] == "min_issuer_exposure"]
    maximums = [rule for rule in evaluated if rule["rule_type"] == "max_issuer_exposure"]
    conflicts = []
    for minimum in minimums:
        issuer = minimum["parameters"]["issuer_id"]
        for maximum in maximums:
            scope = maximum["parameters"]["issuer_scope"]
            if scope not in (ISSUER_SCOPE_ANY, issuer):
                continue
            if minimum["threshold"] > maximum["threshold"] + EPS:
                conflicts.append({
                    "conflict_type": "MIN_EXCEEDS_MAX_SAME_ISSUER",
                    "rule_ids": [minimum["rule_id"], maximum["rule_id"]],
                    "issuer_id": issuer,
                    "min_fraction": minimum["threshold"],
                    "max_fraction": maximum["threshold"],
                    "calculation": (
                        f"minimum {minimum['threshold']:g} > maximum {maximum['threshold']:g} for issuer {issuer}: "
                        "no exposure satisfies both"
                    ),
                })
    return conflicts
