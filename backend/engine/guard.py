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
"""

from __future__ import annotations

import math
from typing import Any

from byb_contracts import COVERAGE_SUM_TOLERANCE

MAX_REPORTED = 3


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
                if isinstance(weight, bool) or not isinstance(weight, (int, float)) or weight < 0:
                    problems.append(f"holdings.funds.{fund_id}.holdings[{index}].weight_fraction is not a non-negative number")
                    break
                total += weight
            else:
                declared = fund.get("coverage_fraction")
                if isinstance(declared, bool) or not isinstance(declared, (int, float)) or abs(total - declared) > COVERAGE_SUM_TOLERANCE:
                    problems.append(f"holdings.funds.{fund_id}.coverage_fraction differs from the sum of its reported rows")
    return problems[:limit]
