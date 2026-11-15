"""The validator's own reference arithmetic.

Written from docs/BUILD_BRIEF.md, docs/LEAD_DECISIONS.md (D4 to D6) and
contracts/SEMANTICS.md only. It does not import the engine, the contracts'
helpers or their reference calculator. Exposure is computed with exact
rationals (``fractions.Fraction`` built from the decimal text of each number)
so that a floating-point mistake cannot hide on both sides.
"""

from __future__ import annotations

import csv
from datetime import date
from fractions import Fraction
from pathlib import Path
from typing import Any, Iterable, Optional

EPS = 1e-9  # LEAD_DECISIONS D2
MAX_AGE_DAYS = 7  # SEMANTICS section 7
BASE_DATE = "2021-12-31"  # LEAD_DECISIONS D6
END_DATE = "2022-12-30"
MAX_TYPE = {"max_issuer_exposure", "exclusion", "controversy_exclusion", "scenario_loss_budget"}


def F(value: Any) -> Fraction:
    """Exact rational of the shortest decimal text of a number (0.1 -> 1/10)."""
    return Fraction(repr(value)) if isinstance(value, float) else Fraction(value)


# --------------------------------------------------------------------------- exposure (D4, SEMANTICS 5)

def exposure(portfolio: dict, instruments: dict, holdings: dict) -> dict:
    """lower per issuer, uncovered total U, in-scope weight, per-sector known weight, unclassified weight."""
    registry = instruments["instruments"]
    funds = holdings["funds"]
    lower: dict[str, Fraction] = {}
    direct: dict[str, Fraction] = {}
    sector: dict[str, Fraction] = {}
    uncovered = Fraction(0)
    unclassified = Fraction(0)
    in_scope = Fraction(0)
    out_of_scope = []
    for position in portfolio["positions"]:
        weight = F(position["weight"])
        if weight <= 0:
            continue
        info = registry[position["instrument_id"]]
        if not info["equity_scope"]:
            out_of_scope.append(position["instrument_id"])
            continue
        in_scope += weight
        if not info["is_fund"]:
            lower[info["issuer_id"]] = lower.get(info["issuer_id"], Fraction(0)) + weight
            direct[info["issuer_id"]] = direct.get(info["issuer_id"], Fraction(0)) + weight
            if info["sector"] is None:
                unclassified += weight
            else:
                sector[info["sector"]] = sector.get(info["sector"], Fraction(0)) + weight
            continue
        entry = funds.get(position["instrument_id"])
        if entry is None:
            uncovered += weight
            continue
        for row in entry["holdings"]:
            known = weight * F(row["weight_fraction"])
            lower[row["issuer_id"]] = lower.get(row["issuer_id"], Fraction(0)) + known
            if row["sector"] is None:
                unclassified += known
            else:
                sector[row["sector"]] = sector.get(row["sector"], Fraction(0)) + known
        gap = 1 - F(entry["coverage_fraction"])
        if gap > 0:
            uncovered += weight * gap
    return {"lower": lower, "direct": direct, "U": uncovered, "in_scope": in_scope, "sector": sector,
            "unclassified": unclassified, "out_of_scope": out_of_scope}


def proposed(portfolio: dict, instrument_id: str, target: float) -> dict:
    """Cash-funded purchase to a final direct weight (BUILD_BRIEF section 2)."""
    start = Fraction(0)
    positions = []
    seen = False
    for position in portfolio["positions"]:
        if position["instrument_id"] == instrument_id:
            start = F(position["weight"])
            positions.append({"instrument_id": instrument_id, "weight": float(F(target))})
            seen = True
        else:
            positions.append(dict(position))
    if not seen:
        positions.append({"instrument_id": instrument_id, "weight": float(F(target))})
    cash_after = F(portfolio["cash_weight"]) - (F(target) - start)
    return {"cash_weight": float(cash_after), "positions": positions, "_cash_after": cash_after, "_start": start}


def rule_bounds(rule: dict, exp: dict, flagged: Iterable[str] = ()) -> tuple[Fraction, Fraction]:
    """(lower, upper) of an exposure rule, per the table in SEMANTICS section 6."""
    kind = rule["rule_type"]
    params = rule["parameters"]
    lower_by = exp["lower"]
    if kind == "max_issuer_exposure":
        if params["issuer_scope"] == "any":
            low = max(lower_by.values(), default=Fraction(0))
        else:
            low = lower_by.get(params["issuer_scope"], Fraction(0))
        return low, low + exp["U"]
    if kind == "min_issuer_exposure":
        low = lower_by.get(params["issuer_id"], Fraction(0))
        return low, low + exp["U"]
    if kind == "exclusion":
        definition = params["definition"]
        if definition["kind"] == "named_issuers":
            low = sum((lower_by.get(i, Fraction(0)) for i in definition["issuer_ids"]), Fraction(0))
            return low, low + exp["U"]
        low = exp["sector"].get(definition["sector"], Fraction(0))
        return low, low + exp["U"] + exp["unclassified"]
    if kind == "controversy_exclusion":
        low = sum((lower_by.get(i, Fraction(0)) for i in set(flagged)), Fraction(0))
        return low, exp["in_scope"]
    raise ValueError(kind)


def status(rule_type: str, lower: Optional[float], upper: Optional[float], limit: float) -> str:
    """LEAD_DECISIONS D4 with the D2 tolerance."""
    if lower is None or upper is None:
        return "UNKNOWN"
    lower, upper, limit = float(lower), float(upper), float(limit)
    if rule_type in MAX_TYPE:
        if upper <= limit + EPS:
            return "PASS"
        return "FAIL" if lower > limit + EPS else "UNKNOWN"
    if lower >= limit - EPS:
        return "PASS"
    return "FAIL" if upper < limit - EPS else "UNKNOWN"


def gap(rule_type: str, verdict: str, lower: float, upper: float, limit: float) -> Optional[float]:
    """SEMANTICS section 6: positive = breach, zero or negative = headroom, None when UNKNOWN."""
    if verdict == "UNKNOWN":
        return None
    if rule_type in MAX_TYPE:
        return float(lower) - limit if verdict == "FAIL" else float(upper) - limit
    return limit - float(upper) if verdict == "FAIL" else limit - float(lower)


def headline(execution: str, consistency: str, statuses: list[str]) -> str:
    """SEMANTICS section 9, first match wins."""
    if execution == "ERROR":
        return "EXECUTION_ERROR"
    if execution == "INVALID_REQUEST":
        return "INVALID_REQUEST"
    if consistency == "PROVEN_CONFLICT":
        return "POLICY_CONFLICT"
    if not statuses:
        return "NO_RULES_EVALUATED"
    if "FAIL" in statuses:
        return "HAS_FAIL"
    return "NO_FAIL_BUT_UNKNOWN" if "UNKNOWN" in statuses else "ALL_PASS"


# --------------------------------------------------------------------------- replay (D6, SEMANTICS 7)

def _age(earlier: str, later: str) -> int:
    return (date.fromisoformat(later) - date.fromisoformat(earlier)).days


def latest_on_or_before(rows: list, day: str) -> Optional[tuple]:
    """Backward match by a plain scan (deliberately not a bisect): the last row dated <= day."""
    found = None
    for row in rows:
        if row[0] <= day:
            if found is None or row[0] > found[0]:
                found = (row[0], row[1])
    return found


def cad_value(prices: list, currency: str, fx: list, day: str, *, fx_matched_to: str = "valuation_date") -> Optional[dict]:
    """Value in CAD on ``day``.

    ``fx_matched_to="valuation_date"`` is SEMANTICS section 7 ("matched to t, not to the price date").
    ``fx_matched_to="price_date"`` is the wording of docs/data-sources.md section 4. Both are kept so the
    difference between the two documents can be measured.
    """
    price = latest_on_or_before(prices, day)
    if price is None:
        return None
    out = {"price_date": price[0], "price": price[1], "price_age": _age(price[0], day), "fx_date": None, "fx": None, "fx_age": None}
    value = price[1]
    if currency != "CAD":
        rate = latest_on_or_before(fx, day if fx_matched_to == "valuation_date" else price[0])
        if rate is None:
            return None
        out.update(fx_date=rate[0], fx=rate[1], fx_age=_age(rate[0], day))
        value = price[1] * rate[1]
    out["value"] = value
    return out


def usable(seen: Optional[dict]) -> bool:
    if seen is None or seen["price_age"] > MAX_AGE_DAYS:
        return False
    return seen["fx_age"] is None or seen["fx_age"] <= MAX_AGE_DAYS


def replay(cash: float, positions: dict[str, float], prices: dict[str, dict], fx: list, *,
           fx_matched_to: str = "valuation_date", base: str = BASE_DATE, end: str = END_DATE) -> dict:
    """Buy and hold from ``base`` to ``end``; cash earns 0; no rebalancing.

    ``prices`` maps instrument -> {"currency", "series": [[date, adj_close], ...]}.
    Returns terminal return, maximum drawdown with its date, per-instrument CAD returns and the missing list.
    """
    held = {i: w for i, w in positions.items() if w > 0}
    base_seen, end_seen, missing = {}, {}, []
    for instrument in held:
        entry = prices.get(instrument)
        b = cad_value(entry["series"], entry["currency"], fx, base, fx_matched_to=fx_matched_to) if entry else None
        e = cad_value(entry["series"], entry["currency"], fx, end, fx_matched_to=fx_matched_to) if entry else None
        if not (usable(b) and usable(e)):
            missing.append(instrument)
        else:
            base_seen[instrument], end_seen[instrument] = b, e
    if missing:
        return {"status": "INSUFFICIENT_HISTORY", "missing": missing, "terminal_return": None, "max_drawdown": None}
    returns = {i: end_seen[i]["value"] / base_seen[i]["value"] - 1.0 for i in held}
    terminal = cash + sum(w * (1.0 + returns[i]) for i, w in held.items()) - 1.0
    days = sorted({row[0] for i in held for row in prices[i]["series"] if base < row[0] <= end})
    peak, worst, worst_day = 1.0, 0.0, None
    for day in days:
        value = cash
        for instrument, weight in held.items():
            seen = cad_value(prices[instrument]["series"], prices[instrument]["currency"], fx, day, fx_matched_to=fx_matched_to)
            value += weight * seen["value"] / base_seen[instrument]["value"]
        peak = max(peak, value)
        fall = value / peak - 1.0
        if fall < worst:
            worst, worst_day = fall, day
    return {"status": "COMPUTED", "missing": [], "terminal_return": terminal, "max_drawdown": worst,
            "max_drawdown_date": worst_day, "returns": returns, "base": base_seen, "end": end_seen}


# --------------------------------------------------------------------------- starter CSV loaders (own parsing)

def load_prices_csv(path: Path, tickers: Iterable[str]) -> dict[str, dict]:
    """instrument -> {"currency", "series": [[date, adj_close]]} straight from prices_daily.csv (adj_close only)."""
    wanted = set(tickers)
    out: dict[str, dict] = {}
    with open(path, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["ticker"] not in wanted or row["adj_close"] in ("", None):
                continue
            entry = out.setdefault(row["ticker"], {"currency": row["currency"], "series": []})
            entry["series"].append([row["date"], float(row["adj_close"])])
    for entry in out.values():
        entry["series"].sort(key=lambda r: r[0])
    return out


def load_fx_csv(path: Path) -> list:
    """[[date, CAD per USD]] from fx_usdcad_daily.csv (column usdcad)."""
    rows = []
    with open(path, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["usdcad"] not in ("", None):
                rows.append([row["date"], float(row["usdcad"])])
    rows.sort(key=lambda r: r[0])
    return rows
