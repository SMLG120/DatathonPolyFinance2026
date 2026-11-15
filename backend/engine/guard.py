"""Input guards: a number that is not finite, or data that contradicts itself, never reaches a verdict.

``NaN`` compares false with everything, so a schema bound such as ``minimum: 0`` lets it through and
every later comparison silently takes the wrong branch (a NaN weight is "not > 0" and the position
vanishes; a NaN bound is "not above the limit" and the rule passes). The engine therefore refuses such
input explicitly, before any calculation:

* in the portfolio, the policy or the draft rules -> ``execution.status`` ``INVALID_REQUEST``;
* in the purchase request -> ``ContractError`` (no valid result can carry the request);
* in the instrument registry, holdings, market data or controversy registry -> ``execution.status``
  ``ERROR``: nothing is calculated from data that cannot be trusted.

The data checks also cover what the look-through arithmetic takes on trust: a fund's declared
``coverage_fraction`` must equal the sum of its reported rows (weights are never rescaled, so a
declared coverage above the rows would hide unknown exposure), and every row and instrument must
name its issuer.

These checks are the engine's own. They do not call, and do not depend on, the contract validators:
if a validator lets a value through (or is replaced), the engine still refuses it. A weight - a
position, cash, a purchase target, a rule threshold, a holdings row - is a number in [0, 1]; a
coverage fraction is in [0, 1.01] (published weights are rounded, so their sum may pass 1 slightly);
a price or an exchange rate is a number above 0. A position is never dropped because its weight is
unusable: the whole request is refused.
"""

from __future__ import annotations

import math
from typing import Any

from byb_contracts import COVERAGE_SUM_TOLERANCE, EPS

MAX_REPORTED = 3
MAX_COVERAGE = 1.01


def number_problem(value: Any, low: float = 0.0, high: float = 1.0 + EPS, strictly_above_low: bool = False) -> str | None:
    """Why ``value`` is not a usable number in [low, high] (None when it is). Never echoes the value."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return "is not a number"
    if not math.isfinite(value):
        return "is not a finite number"
    if value < low or (strictly_above_low and value <= low):
        return "is negative" if low == 0.0 and not strictly_above_low else "is not above zero" if strictly_above_low else "is too low"
    if value > high:
        return "is above 1" if high <= 1.0 + EPS else "is too high"
    return None


def portfolio_problems(portfolio: Any, limit: int = MAX_REPORTED) -> list[str]:
    """Cash and every position weight must be a finite number in [0, 1]."""
    if not isinstance(portfolio, dict):
        return ["portfolio is not an object"]
    problems = []
    why = number_problem(portfolio.get("cash_weight"))
    if why:
        problems.append(f"portfolio.cash_weight {why}")
    positions = portfolio.get("positions")
    if not isinstance(positions, list):
        return (problems + ["portfolio.positions is not a list"])[:limit]
    for index, position in enumerate(positions):
        why = number_problem(position.get("weight")) if isinstance(position, dict) else "is not an object"
        if why:
            problems.append(f"portfolio.positions[{index}].weight {why}")
    return problems[:limit]


def threshold_problems(rules: Any, where: str, limit: int = MAX_REPORTED) -> list[str]:
    """A threshold is null (a draft without a number) or a finite number in [0, 1]."""
    if not isinstance(rules, list):
        return []
    problems = []
    for index, rule in enumerate(rules):
        threshold = rule.get("threshold") if isinstance(rule, dict) else None
        why = None if threshold is None else number_problem(threshold)
        if why:
            problems.append(f"{where}[{index}].threshold {why}")
    return problems[:limit]


def target_problem(request: Any) -> str | None:
    """Only what no result can carry: a target that is not a finite number. Range errors are execution codes."""
    target = request.get("target_direct_weight") if isinstance(request, dict) else None
    return number_problem(target, low=-math.inf, high=math.inf)


def non_finite_paths(value: Any, where: str, limit: int = MAX_REPORTED) -> list[str]:
    """Paths (at most ``limit``) of floats that are NaN or infinite inside a JSON-like value."""
    found: list[str] = []
    stack = [(where, value)]
    while stack and len(found) < limit:
        path, item = stack.pop()
        if isinstance(item, float):
            if not math.isfinite(item):
                found.append(path)
        elif isinstance(item, dict):
            stack.extend((f"{path}.{key}", child) for key, child in item.items())
        elif isinstance(item, (list, tuple)):
            stack.extend((f"{path}[{index}]", child) for index, child in enumerate(item))
    return sorted(found)


def _named(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def data_problems(instruments: Any, holdings: Any, market_data: Any, controversies: Any, limit: int = MAX_REPORTED) -> list[str]:
    """Why the data cannot be used for a check ([] when it can). Paths and field names only, never values."""
    from .core import funds_of, registry_of

    problems: list[str] = []
    for name, document in (("instruments", instruments), ("holdings", holdings), ("market_data", market_data), ("controversies", controversies)):
        problems += [f"{path} is not a finite number" for path in non_finite_paths(document, name, limit)]
    if problems:
        return problems[:limit]  # sums below would be meaningless
    registry = registry_of(instruments)
    if isinstance(registry, dict):
        for instrument_id, instrument in registry.items():
            if isinstance(instrument, dict) and not _named(instrument.get("issuer_id")):
                problems.append(f"instruments.{instrument_id} has no issuer_id")
    funds = funds_of(holdings)
    if isinstance(funds, dict):
        for fund_id, fund in funds.items():
            rows = fund.get("holdings") if isinstance(fund, dict) else None
            if not isinstance(rows, list):
                continue
            total = 0.0
            for index, row in enumerate(rows):
                weight = row.get("weight_fraction") if isinstance(row, dict) else None
                if not isinstance(row, dict) or not _named(row.get("issuer_id")):
                    problems.append(f"holdings.funds.{fund_id}.holdings[{index}] has no issuer_id")
                    break
                why = number_problem(weight)
                if why:
                    problems.append(f"holdings.funds.{fund_id}.holdings[{index}].weight_fraction {why}")
                    break
                total += weight
            else:
                declared = fund.get("coverage_fraction")
                why = number_problem(declared, high=MAX_COVERAGE)
                if why:
                    problems.append(f"holdings.funds.{fund_id}.coverage_fraction {why}")
                elif abs(total - declared) > COVERAGE_SUM_TOLERANCE:
                    problems.append(f"holdings.funds.{fund_id}.coverage_fraction differs from the sum of its reported rows")
    if isinstance(market_data, dict):
        prices = market_data.get("prices")
        for instrument_id, entry in (prices.items() if isinstance(prices, dict) else ()):
            problems += _series_problems(entry.get("series") if isinstance(entry, dict) else None, f"market_data.prices.{instrument_id}.series")
        if "fx_usdcad" in market_data:
            problems += _series_problems(market_data["fx_usdcad"], "market_data.fx_usdcad")
    return problems[:limit]


def _series_problems(series: Any, where: str) -> list[str]:
    """Rows are [date, value] with a value above zero (a price or a rate of zero or less is not a price)."""
    if not isinstance(series, list):
        return [f"{where} is not a list of dated values"]
    for index, row in enumerate(series):
        if not isinstance(row, (list, tuple)) or len(row) < 2:
            return [f"{where}[{index}] is not a dated value"]
        why = number_problem(row[1], high=math.inf, strictly_above_low=True)
        if why:
            return [f"{where}[{index}] {why}"]
    return []
