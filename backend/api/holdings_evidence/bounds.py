"""Conditional exposure bounds from a scan (LEAD_DECISIONS D4). Deterministic; no model, no I/O.

    minimum = verified category exposure                      (as if none of the unresolved weight were in the category)
    maximum = minimum + unclassified weight + unresolved weight   (as if all of it were)

Both ends are arithmetic on observed weights under a stated assumption. Neither is a forecast, and the maximum is
never the actual exposure. Fund-level numbers are shares of the FUND; portfolio-level numbers are shares of the
PORTFOLIO (fund share x the position's portfolio weight). The two are never compared with each other.
"""

from __future__ import annotations

from typing import Any

from backend.engine.core import compute_exposure, held_positions

from .scanner import pct


def _g(fraction: float) -> str:
    """A fraction as percentage text without float noise or a trailing ``.0``."""
    return f"{pct(fraction):g}"

EPS = 1e-9  # same absolute tolerance as the engine (LEAD_DECISIONS D2)

WITHIN = "within_limit_under_every_scenario"
EXCEEDS = "exceeds_limit_on_verified_data"
UNCONFIRMED = "cannot_be_confirmed"


def _scenarios(subject: str, of: str, low: float, high: float, unresolved: float) -> list[dict[str, Any]]:
    if unresolved <= EPS:
        return []
    return [
        {"id": "none_of_unresolved", "hypothetical": True,
         "assumption": f"None of the unresolved {_g(unresolved)}% of the {of} is {subject}.",
         "exposure_pct": pct(low),
         "text": f"If none of the unresolved weight is {subject}, exposure to {subject} stays at {_g(low)}% of the {of}."},
        {"id": "all_of_unresolved", "hypothetical": True,
         "assumption": f"All of the unresolved {_g(unresolved)}% of the {of} is {subject}.",
         "exposure_pct": pct(high),
         "text": f"If all of the unresolved weight is {subject}, exposure to {subject} could reach {_g(high)}% of the {of}. "
                 "This is a mathematical upper bound, not a measured or expected exposure."},
    ]


def fund_sector_bounds(scan: dict[str, Any], sector: str) -> dict[str, Any]:
    """Bounds for one sector label, as shares of the fund. ``None`` where the fund has no valid weight basis."""
    calc = scan["_calc"]
    base = {"level": "fund", "fund": scan["fund"], "category": sector, "unit": "percent of the fund"}
    if not calc["basis_valid"]:
        reason = ("No holdings file is held: nothing is verified, and anything from 0% to 100% of the fund could be in this sector."
                  if calc["no_file"] else "The fund's weights do not reconcile, so no bound is calculated for it.")
        return {**base, "verified_exposure_pct": None, "unclassified_weight_pct": None, "unresolved_weight_pct": 100.0 if calc["no_file"] else None,
                "conditional_min_pct": 0.0 if calc["no_file"] else None, "conditional_max_pct": 100.0 if calc["no_file"] else None,
                "scenarios": [], "basis": reason}
    low = calc["sectors"].get(sector, 0.0)
    open_weight = calc["unclassified"] + calc["unresolved"]
    high = min(1.0, low + open_weight)
    return {**base, "verified_exposure_pct": pct(low), "unclassified_weight_pct": pct(calc["unclassified"]),
            "unresolved_weight_pct": pct(calc["unresolved"]), "conditional_min_pct": pct(low), "conditional_max_pct": pct(high),
            "scenarios": _scenarios(sector, "fund", low, high, open_weight),
            "basis": "minimum = weight of holdings labelled with this sector; maximum = minimum + weight of holdings without a sector label "
                     "+ weight not attributed to any holding."}


def portfolio_sector_bounds(portfolio: dict, registry: dict, scans: dict[str, dict], sector: str) -> dict[str, Any]:
    """Bounds for one sector label, as shares of the portfolio. Each position is counted once, at its own weight."""
    low = unclassified = unresolved = 0.0
    contributions, out_of_scope = [], []
    for instrument_id, weight in held_positions(portfolio):
        instrument = registry.get(instrument_id) or {}
        if not instrument.get("equity_scope"):
            out_of_scope.append({"instrument_id": instrument_id, "portfolio_weight_pct": pct(weight)})
            continue
        if not instrument.get("is_fund"):
            label = instrument.get("sector")
            known = weight if label == sector else 0.0
            open_part = weight if label is None else 0.0
            low += known
            unclassified += open_part
            contributions.append({"position": instrument_id, "kind": "direct", "portfolio_weight_pct": pct(weight),
                                  "verified_pct": pct(known), "unclassified_pct": pct(open_part), "unresolved_pct": 0.0})
            continue
        calc = scans[instrument_id]["_calc"]
        if calc["basis_valid"]:
            known, open_class, open_hold = weight * calc["sectors"].get(sector, 0.0), weight * calc["unclassified"], weight * calc["unresolved"]
        else:  # no file, or weights that do not reconcile: the whole position is unresolved, never zero
            known, open_class, open_hold = 0.0, 0.0, weight
        low += known
        unclassified += open_class
        unresolved += open_hold
        contributions.append({"position": instrument_id, "kind": "fund", "portfolio_weight_pct": pct(weight), "verified_pct": pct(known),
                              "unclassified_pct": pct(open_class), "unresolved_pct": pct(open_hold),
                              "fund_basis": scans[instrument_id]["coverage_basis"]})
    open_weight = unclassified + unresolved
    high = low + open_weight
    return {"level": "portfolio", "category": sector, "unit": "percent of the portfolio",
            "verified_exposure_pct": pct(low), "unclassified_weight_pct": pct(unclassified), "unresolved_weight_pct": pct(unresolved),
            "conditional_min_pct": pct(low), "conditional_max_pct": pct(high),
            "scenarios": _scenarios(sector, "portfolio", low, high, open_weight),
            "contributions": contributions, "out_of_scope": out_of_scope,
            "basis": "Each fund's share is multiplied by the position's portfolio weight. Bond, commodity and crypto positions and cash are "
                     "outside the scope of sector rules and are not counted.",
            "_low": low, "_high": high}


def portfolio_issuer_bounds(portfolio: dict, instruments: Any, holdings: Any, issuer_scope: str = "any", top: int = 3) -> dict[str, Any]:
    """Per-company bounds from the engine's own look-through, so the same company held through several funds is added up once."""
    exposure = compute_exposure(portfolio, instruments, holdings)
    extra = exposure["possible_extra"]
    lower = exposure["lower"]
    names = exposure["row_names"]
    if issuer_scope != "any":
        ranked = [(issuer_scope, lower.get(issuer_scope, 0.0))]
    else:
        ranked = sorted(lower.items(), key=lambda item: (-item[1], item[0]))[:top]
    low = ranked[0][1] if ranked else 0.0
    return {"level": "portfolio", "category": "any single company" if issuer_scope == "any" else issuer_scope, "unit": "percent of the portfolio",
            "verified_exposure_pct": pct(low), "unclassified_weight_pct": 0.0, "unresolved_weight_pct": pct(extra),
            "conditional_min_pct": pct(low), "conditional_max_pct": pct(low + extra),
            "largest_verified": [{"issuer_id": issuer, "name": names.get(issuer), "verified_pct": pct(value), "conditional_max_pct": pct(value + extra)}
                                 for issuer, value in ranked],
            "scenarios": _scenarios("one single company", "portfolio", low, low + extra, extra),
            "basis": "Direct holdings plus look-through of every equity fund, share classes added up per company (the engine's calculation). "
                     "The unresolved weight of the funds could belong to any one company.",
            "_low": low, "_high": low + extra}


def assess_max_limit(low: float, high: float, limit: float) -> str:
    """Where a 'no more than' limit stands against the interval. Mirrors D4; it is not the engine's verdict on a purchase."""
    if high <= limit + EPS:
        return WITHIN
    if low > limit + EPS:
        return EXCEEDS
    return UNCONFIRMED


def rule_impacts(rules: list[dict], rule_basis: str, portfolio: dict, registry: dict, scans: dict[str, dict], instruments: Any, holdings: Any,
                 issuer_bounds_available: bool) -> list[dict[str, Any]]:
    """What the unresolved evidence means for each rule this investigator can analyse. Limits come from ``rules`` only."""
    impacts = []
    for rule in rules:
        limit = rule.get("threshold")
        if rule.get("status") not in ("CONFIRMED", "PROPOSED") or not isinstance(limit, (int, float)) or isinstance(limit, bool):
            continue
        base = {"rule_id": rule.get("rule_id"), "rule_type": rule.get("rule_type"), "rule_status": rule.get("status"), "rule_basis": rule_basis,
                "limit_pct": pct(limit), "category": None, "analysed": False, "assessment": None, "bounds": None, "text": None}
        definition = (rule.get("parameters") or {}).get("definition") or {}
        bounds = None
        if rule.get("rule_type") == "exclusion" and definition.get("kind") == "fund_reported_sector":
            bounds = portfolio_sector_bounds(portfolio, registry, scans, definition["sector"])
        elif rule.get("rule_type") == "max_issuer_exposure" and issuer_bounds_available:
            bounds = portfolio_issuer_bounds(portfolio, instruments, holdings, (rule.get("parameters") or {}).get("issuer_scope", "any"))
        if bounds is None:
            base["text"] = f"Rule {base['rule_id']} ({base['rule_type']}) is not analysed by the evidence investigator."
            impacts.append(base)
            continue
        assessment = assess_max_limit(bounds["_low"], bounds["_high"], float(limit))
        subject = bounds["category"]
        wording = {
            WITHIN: f"Even if all unresolved weight counted toward {subject}, exposure to {subject} would stay at or below the {_g(limit)}% limit "
                    f"(verified {_g(bounds['_low'])}%, at most {_g(bounds['_high'])}% of the portfolio).",
            EXCEEDS: f"The verified holdings alone put exposure to {subject} at {_g(bounds['_low'])}% of the portfolio, above the {_g(limit)}% limit.",
            UNCONFIRMED: f"Exposure to {subject} cannot currently be confirmed at or below the {_g(limit)}% limit: verified exposure is "
                         f"{_g(bounds['_low'])}% of the portfolio and the unresolved weight could raise it to as much as {_g(bounds['_high'])}%.",
        }[assessment]
        base.update(analysed=True, category=subject, assessment=assessment, bounds=strip(bounds),
                    text=wording + " This describes the current portfolio; a rule verdict on a purchase comes from the check, not from here.")
        impacts.append(base)
    return impacts


def strip(bounds: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in bounds.items() if not key.startswith("_")}
