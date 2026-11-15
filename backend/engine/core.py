"""Purchase simulation, look-through exposure and the historical replay.

Pure functions over plain dicts in the contract shapes. Standard library only;
no I/O, no clock, no AWS, no model. Every quantity is a portfolio fraction
(10% = 0.10) unless a field name says otherwise.
"""

from __future__ import annotations

from bisect import bisect_right
from datetime import date
from typing import Any, Iterable, Optional

from byb_contracts import (
    EPS,
    ContractError,
    FUNDING,
    MAX_PRICE_AGE_DAYS,
    SCENARIOS,
    coverage_status,
    feasibility_status,
    policy_errors,
    portfolio_errors,
    rule_errors,
    validate_purchase_request,
)

from .guard import non_finite_paths, portfolio_problems, target_problem, threshold_problems

OUT_OF_SCOPE_REASONS = {
    "etf_bond": "Bond fund: outside the scope of the company-exposure rules; not assessed.",
    "etf_commodity": "Commodity fund: outside the scope of the company-exposure rules; not assessed.",
    "crypto": "Crypto asset: outside the scope of the company-exposure rules; not assessed.",
}
OUT_OF_SCOPE_DEFAULT = "Outside the scope of the company-exposure rules; not assessed."


# --------------------------------------------------------------------------- input shapes

def registry_of(instruments: Any) -> dict:
    """Accept the registry file shape ({'instruments': {...}}) or the bare mapping."""
    if isinstance(instruments, dict) and isinstance(instruments.get("instruments"), dict):
        return instruments["instruments"]
    return instruments or {}


def funds_of(holdings: Any) -> dict:
    if isinstance(holdings, dict) and isinstance(holdings.get("funds"), dict):
        return holdings["funds"]
    return holdings or {}


def records_of(controversies: Any) -> list:
    if isinstance(controversies, dict):
        return list(controversies.get("records") or [])
    return list(controversies or [])


def held_positions(portfolio: dict) -> list[tuple[str, float]]:
    """Positions with a positive weight, in portfolio order."""
    return [(p["instrument_id"], p["weight"]) for p in portfolio.get("positions", []) if p["weight"] > 0]


# --------------------------------------------------------------------------- purchase simulation

def refuse_unusable_request(purchase_request: Any) -> None:
    """Raise ContractError for a request no result can carry: a target that is not a finite number, or any NaN."""
    why = target_problem(purchase_request)
    problems = [f"purchase_request.target_direct_weight: {why}"] if why else []
    problems += [f"{path}: is not a finite number" for path in non_finite_paths(purchase_request, "purchase_request")]
    if problems:  # NaN passes a schema bound; the result would carry it and could not be serialized
        raise ContractError("purchase request", list(dict.fromkeys(problems)))


def _execution(status: str, code: Optional[str], message: Optional[str]) -> dict:
    return {"status": status, "code": code, "message": message}


def simulate_change(
    portfolio: dict,
    purchase_request: dict,
    instruments: Any,
    policy: Optional[dict] = None,
    *,
    draft_rules: Optional[list] = None,
) -> dict:
    """Cash-funded purchase to a FINAL direct target weight (SEMANTICS section 4).

    Returns ``{"execution", "feasibility", "starting_portfolio", "proposed_portfolio"}``.
    When ``execution.status`` is not ``OK`` the other three members are None.
    The policy (or the draft rules of a preview) is only validated here.
    A purchase request that does not match its schema raises ``ContractError``:
    no valid result can carry it.
    """
    refuse_unusable_request(purchase_request)
    validate_purchase_request(purchase_request)
    registry = registry_of(instruments)
    invalid = {"feasibility": None, "starting_portfolio": None, "proposed_portfolio": None}

    # The engine's own checks first (guard.py); the contract validators second. Neither replaces the other.
    errors = (portfolio_problems(portfolio)
              or [f"{path} is not a finite number" for path in non_finite_paths(portfolio, "portfolio")]
              or portfolio_errors(portfolio))
    if not errors:
        errors = [
            f"position {p['instrument_id']!r} is not in the instrument registry"
            for p in portfolio["positions"]
            if p["instrument_id"] not in registry
        ]
    if errors:
        return {"execution": _execution("INVALID_REQUEST", "INVALID_PORTFOLIO", "The portfolio is not valid: " + "; ".join(errors[:3])), **invalid}

    if draft_rules is not None:
        errors = threshold_problems(draft_rules, "draft_rules") or [f"{path} is not a finite number" for path in non_finite_paths(draft_rules, "draft_rules")]
    else:
        rules = policy.get("rules") if isinstance(policy, dict) else None
        errors = threshold_problems(rules, "policy.rules") or [f"{path} is not a finite number" for path in non_finite_paths(policy, "policy")]
    if errors:
        pass
    elif draft_rules is not None:
        seen = set()
        for i, rule in enumerate(draft_rules):
            errors.extend(f"draft_rules[{i}]: {e}" for e in rule_errors(rule))
            rule_id = rule.get("rule_id") if isinstance(rule, dict) else None
            if rule_id in seen:
                errors.append(f"draft_rules[{i}]: rule_id {rule_id!r} appears more than once")
            seen.add(rule_id)
    elif policy is not None:
        errors = policy_errors(policy)
    if errors:
        return {"execution": _execution("INVALID_REQUEST", "INVALID_POLICY", "The policy is not valid: " + "; ".join(errors[:3])), **invalid}

    instrument_id = purchase_request["instrument_id"]
    target = purchase_request["target_direct_weight"]
    if instrument_id not in registry:
        return {"execution": _execution("INVALID_REQUEST", "UNSUPPORTED_INSTRUMENT", f"{instrument_id} is not in the instrument registry; it cannot be simulated."), **invalid}
    if target < -EPS:
        return {"execution": _execution("INVALID_REQUEST", "TARGET_NEGATIVE", "The target direct weight is negative. Short positions are not supported."), **invalid}
    if target > 1 + EPS:
        return {"execution": _execution("INVALID_REQUEST", "TARGET_ABOVE_ONE", "The target direct weight is above 1 (100% of the portfolio). Leverage is not supported."), **invalid}
    starting_weight = 0.0
    for position in portfolio["positions"]:
        if position["instrument_id"] == instrument_id:
            starting_weight = position["weight"]
    if target < starting_weight - EPS:
        return {
            "execution": _execution(
                "INVALID_REQUEST", "TARGET_BELOW_CURRENT_WEIGHT",
                f"The target direct weight {target:g} is below the current direct weight {starting_weight:g} of {instrument_id}. "
                "Reaching it would require selling, which the cash-funded purchase path does not support.",
            ),
            **invalid,
        }

    # Inside the tolerance band the request is a no-op or sits on the [0, 1] edge.
    target = min(1.0, max(0.0, target, starting_weight))
    additional = target - starting_weight
    cash_before = portfolio["cash_weight"]
    cash_after = cash_before - additional

    positions = []
    found = False
    for position in portfolio["positions"]:
        if position["instrument_id"] == instrument_id:
            positions.append({"instrument_id": instrument_id, "weight": target})
            found = True
        else:
            positions.append({"instrument_id": position["instrument_id"], "weight": position["weight"]})
    if not found and target > 0:
        positions.append({"instrument_id": instrument_id, "weight": target})

    return {
        "execution": _execution("OK", None, None),
        "feasibility": {
            "funding": FUNDING,
            "starting_direct_weight": starting_weight,
            "target_direct_weight": target,
            "additional_purchase": additional,
            "cash_before": cash_before,
            "cash_after": cash_after,
            "status": feasibility_status(cash_after),
        },
        "starting_portfolio": {
            "cash_weight": cash_before,
            "positions": [{"instrument_id": p["instrument_id"], "weight": p["weight"]} for p in portfolio["positions"]],
        },
        "proposed_portfolio": {"cash_weight": cash_after, "positions": positions},
    }


# --------------------------------------------------------------------------- look-through exposure

def compute_exposure(portfolio: dict, instruments: Any, holdings: Any) -> dict:
    """Direct plus look-through exposure of ONE portfolio state (SEMANTICS section 5).

    Each position is counted exactly once: an out-of-scope position adds to
    nothing; a direct equity adds its weight to its issuer; an equity fund adds
    ``weight x constituent weight`` per reported row (weights are never
    rescaled) and its unreported share to ``possible_extra``. Share classes are
    aggregated through ``issuer_id``. ``lower[issuer]`` is the known exposure,
    ``upper[issuer] = lower[issuer] + possible_extra``.
    """
    registry = registry_of(instruments)
    funds = funds_of(holdings)
    direct: dict[str, float] = {}
    via_fund: dict[str, dict[str, float]] = {}
    uncovered_by_fund: dict[str, float] = {}
    sector_exposure: dict[str, dict[str, float]] = {}
    paths: list[dict] = []
    out_of_scope: list[dict] = []
    coverage: list[dict] = []
    row_names: dict[str, str] = {}
    unclassified = 0.0
    in_scope = 0.0

    for instrument_id, weight in held_positions(portfolio):
        instrument = registry[instrument_id]
        if not instrument["equity_scope"]:
            out_of_scope.append({
                "instrument_id": instrument_id,
                "weight": weight,
                "reason": OUT_OF_SCOPE_REASONS.get(instrument["asset_class"], OUT_OF_SCOPE_DEFAULT),
            })
            continue
        in_scope += weight
        if not instrument["is_fund"]:
            issuer = instrument["issuer_id"]
            direct[issuer] = direct.get(issuer, 0.0) + weight
            sector = instrument["sector"]
            if sector is None:
                unclassified += weight
            else:
                bucket = sector_exposure.setdefault(sector, {})
                bucket[issuer] = bucket.get(issuer, 0.0) + weight
            paths.append({
                "position_id": instrument_id, "kind": "DIRECT", "issuer_id": issuer, "weight": weight,
                "fund_fraction": None, "sector": sector, "sector_source": instrument["sector_source"], "rows": 1,
            })
            continue
        entry = funds.get(instrument_id)
        if entry is None:
            uncovered_by_fund[instrument_id] = weight
            coverage.append({
                "fund_id": instrument_id, "portfolio_weight": weight, "coverage_fraction": 0.0,
                "sector_labelled_fraction": 0.0, "uncovered_portfolio_weight": weight,
                "holdings_date": None, "source_id": None, "status": coverage_status(False, 0.0),
            })
            continue
        covered = entry["coverage_fraction"]
        labelled_fraction = 0.0
        merged: dict[tuple, dict] = {}
        for row in entry["holdings"]:
            issuer = row["issuer_id"]
            fraction = row["weight_fraction"]
            row_names.setdefault(issuer, row["name"])
            known = weight * fraction
            issuer_paths = via_fund.setdefault(issuer, {})
            issuer_paths[instrument_id] = issuer_paths.get(instrument_id, 0.0) + known
            sector = row["sector"]
            if sector is None:
                unclassified += known
            else:
                labelled_fraction += fraction
                bucket = sector_exposure.setdefault(sector, {})
                bucket[issuer] = bucket.get(issuer, 0.0) + known
            key = (issuer, sector)
            reported = (row.get("instrument_id") or row.get("name") or "unnamed row", fraction)  # kept so evidence can cite each row
            if key in merged:
                merged[key]["weight"] += known
                merged[key]["fund_fraction"] += fraction
                merged[key]["rows"] += 1
                merged[key]["reported_rows"].append(reported)
            else:
                merged[key] = {
                    "position_id": instrument_id, "kind": "FUND", "issuer_id": issuer, "weight": known,
                    "fund_fraction": fraction, "sector": sector, "sector_source": row["sector_source"], "rows": 1,
                    "reported_rows": [reported],
                }
        paths.extend(merged.values())
        uncovered = weight * max(0.0, 1.0 - covered)
        uncovered_by_fund[instrument_id] = uncovered
        coverage.append({
            "fund_id": instrument_id, "portfolio_weight": weight, "coverage_fraction": covered,
            "sector_labelled_fraction": labelled_fraction, "uncovered_portfolio_weight": uncovered,
            "holdings_date": entry["holdings_date"], "source_id": entry["source_id"],
            "status": coverage_status(True, covered),
        })

    possible_extra = sum(uncovered_by_fund.values())
    lower: dict[str, float] = {}
    for issuer in list(direct) + [i for i in via_fund if i not in direct]:
        lower[issuer] = direct.get(issuer, 0.0) + sum(via_fund.get(issuer, {}).values())
    return {
        "direct": direct,
        "via_fund": via_fund,
        "lower": lower,
        "upper": {issuer: value + possible_extra for issuer, value in lower.items()},
        "possible_extra": possible_extra,
        "uncovered_by_fund": uncovered_by_fund,
        "in_scope_weight": in_scope,
        "unclassified_weight": unclassified,
        "sector_exposure": sector_exposure,
        "out_of_scope": out_of_scope,
        "funds": coverage,
        "paths": paths,
        "row_names": row_names,
    }


# --------------------------------------------------------------------------- scenario replay

def _days_between(earlier: str, later: str) -> int:
    return (date.fromisoformat(later) - date.fromisoformat(earlier)).days


class _Series:
    """Dated values with a backward match: the latest row on or before a date."""

    def __init__(self, rows: Iterable):
        self.dates = [row[0] for row in rows]
        self.values = [row[1] for row in rows]

    def at(self, day: str) -> Optional[tuple[str, float]]:
        i = bisect_right(self.dates, day)
        if i == 0:
            return None
        return self.dates[i - 1], self.values[i - 1]

    def dates_between(self, after: str, until: str) -> list[str]:
        return self.dates[bisect_right(self.dates, after):bisect_right(self.dates, until)]


class _Market:
    def __init__(self, market_data: Any):
        market_data = market_data or {}
        self.prices = market_data.get("prices") or {}
        self.fx = _Series(market_data.get("fx_usdcad") or [])
        self._series: dict[str, _Series] = {}

    def series(self, instrument_id: str) -> Optional[_Series]:
        if instrument_id not in self.prices:
            return None
        if instrument_id not in self._series:
            self._series[instrument_id] = _Series(self.prices[instrument_id]["series"])
        return self._series[instrument_id]

    def currency(self, instrument_id: str) -> str:
        return self.prices[instrument_id]["currency"]

    def observation(self, instrument_id: str, day: str) -> Optional[dict]:
        """Price (and FX for a USD instrument) on or before ``day``; the FX rate is matched to ``day``."""
        series = self.series(instrument_id)
        price = series.at(day) if series else None
        if price is None:
            return None
        result = {
            "price_date": price[0], "price": price[1], "price_age_days": _days_between(price[0], day),
            "fx_date": None, "fx": None, "fx_age_days": None, "value_cad": price[1],
        }
        if self.currency(instrument_id) != "CAD":
            rate = self.fx.at(day)
            if rate is None:
                return None
            result.update(fx_date=rate[0], fx=rate[1], fx_age_days=_days_between(rate[0], day), value_cad=price[1] * rate[1])
        return result

    def usable(self, instrument_id: str, day: str) -> Optional[dict]:
        seen = self.observation(instrument_id, day)
        if seen is None or seen["price_age_days"] > MAX_PRICE_AGE_DAYS:
            return None
        if seen["fx_age_days"] is not None and seen["fx_age_days"] > MAX_PRICE_AGE_DAYS:
            return None
        return seen

    def history(self, instrument_id: str, base_date: str, end_date: str) -> Optional[dict]:
        """The instrument's replay row, or None when it has no usable history (no proxy, ever)."""
        base = self.usable(instrument_id, base_date)
        end = self.usable(instrument_id, end_date)
        if base is None or end is None:
            return None
        return {
            "instrument_id": instrument_id,
            "currency": self.currency(instrument_id),
            "base_price_date": base["price_date"],
            "end_price_date": end["price_date"],
            "base_price_age_days": base["price_age_days"],
            "end_price_age_days": end["price_age_days"],
            "base_fx_date": base["fx_date"],
            "end_fx_date": end["fx_date"],
            "base_fx_age_days": base["fx_age_days"],
            "end_fx_age_days": end["fx_age_days"],
            "return_cad": end["value_cad"] / base["value_cad"] - 1.0,
            "_base": base,
            "_end": end,
        }


def public_row(history: dict) -> dict:
    return {key: value for key, value in history.items() if not key.startswith("_")}


def replay_state(market: _Market, portfolio: dict, histories: dict, base_date: str, end_date: str) -> dict:
    """Buy and hold from the base date, cash earning 0: terminal return and maximum drawdown.

    ``V(t) = cash + sum(weight x value(t) / value(base))`` so ``V(base) = 1``.
    The drawdown is taken over every date in (base, end] on which a held
    instrument has a price row, each instrument's last price carried forward
    and the FX rate of the day applied; the running maximum starts at 1.
    """
    positions = held_positions(portfolio)
    cash = portfolio["cash_weight"]
    end_value = cash + sum(weight * (1.0 + histories[i]["return_cad"]) for i, weight in positions)
    days = sorted({day for i, _ in positions for day in market.series(i).dates_between(base_date, end_date)})
    running_max = 1.0
    drawdown = 0.0
    drawdown_date = None
    trough_value = 1.0
    for day in days:
        value = cash
        for instrument_id, weight in positions:
            value += weight * market.observation(instrument_id, day)["value_cad"] / histories[instrument_id]["_base"]["value_cad"]
        if value > running_max:
            running_max = value
        fall = value / running_max - 1.0
        if fall < drawdown:
            drawdown, drawdown_date, trough_value = fall, day, value
    return {
        "scenario_terminal_return": end_value - 1.0,
        "scenario_max_drawdown": drawdown,
        "max_drawdown_date": drawdown_date,
        "_trough_value": trough_value,
    }


def replay_period(
    portfolio: dict,
    market_data: Any,
    scenario_id: str = "replay_2022",
    *,
    required_instruments: Optional[list] = None,
) -> dict:
    """Replay ONE allocation through a named historical scenario (SEMANTICS section 7).

    ``portfolio`` needs ``cash_weight`` and ``positions``. Usable history is
    required for every held instrument and for every id in
    ``required_instruments`` (one replay universe per check). Without it the
    status is ``INSUFFICIENT_HISTORY`` and the measures are None.
    ``scenario_terminal_return`` and ``scenario_max_drawdown`` are separate
    outputs; only the first is used by the loss-budget rule.
    """
    scenario = SCENARIOS[scenario_id]
    base_date, end_date = scenario["base_date"], scenario["end_date"]
    market = _Market(market_data)
    universe = [i for i, _ in held_positions(portfolio)]
    for instrument_id in required_instruments or []:
        if instrument_id not in universe:
            universe.append(instrument_id)
    histories = {i: market.history(i, base_date, end_date) for i in universe}
    missing = [i for i in universe if histories[i] is None]
    result = {
        "scenario_id": scenario_id,
        "label": scenario["label"],
        "base_date": base_date,
        "end_date": end_date,
        "status": "INSUFFICIENT_HISTORY" if missing else "COMPUTED",
        "scenario_terminal_return": None,
        "scenario_max_drawdown": None,
        "max_drawdown_date": None,
        "instrument_returns": [public_row(histories[i]) for i in universe if histories[i] is not None],
        "missing_instruments": missing,
        "assumptions": list(scenario["assumptions"]),
    }
    if not missing:
        state = replay_state(market, portfolio, histories, base_date, end_date)
        result.update({key: value for key, value in state.items() if not key.startswith("_")})
    return result
