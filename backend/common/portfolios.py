"""Which fictional portfolio a request is checked against (contracts/api.md, section 2a).

Pure: no storage, no clock, no model. A request either names no portfolio (the persona's scenario
portfolio is used, unchanged) or carries ``custom_portfolio``: weights only, edited by the user.
The server checks those weights and builds the portfolio document itself; the client never
supplies a persona, a date, a currency or an id.

Weights are portfolio fractions (10% = 0.10) and are never rescaled: a total that is not 1 is
refused, so leverage (a total above 1) and shorting (a negative weight) cannot be expressed.
Holdings coverage is not touched here: a fund without a holdings file stays unknown in the engine.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any, Iterable

from byb_contracts import EPS, ContractError, canonical_json, validate_portfolio

MAX_POSITIONS = 40  # api.schema.json#/$defs/custom_portfolio
ROOT = "custom_portfolio"
_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")  # common.schema.json#/$defs/id


class InvalidCustomPortfolio(Exception):
    """The submitted weights cannot be used. ``problems`` is a list of ``(path, issue)``; nothing was calculated."""

    def __init__(self, problems: list[tuple[str, str]]) -> None:
        super().__init__("; ".join(f"{path}: {issue}" for path, issue in problems))
        self.problems = list(problems)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def shape_problems(custom: Any) -> list[tuple[str, str]]:
    """Rule 1 (the shape the schema also requires), with a path and a plain reason for each problem.

    The routes report these instead of the schema's generic message for the optional member, so a refused
    weight says why (shorting, leverage, a zero weight) and where.
    """
    if not isinstance(custom, dict):
        return [(ROOT, "must be an object with cash_weight and positions, or null")]
    problems: list[tuple[str, str]] = []
    for name in sorted(set(custom) - {"cash_weight", "positions"}):
        problems.append((f"{ROOT}.{name}", "is not a member of custom_portfolio (only cash_weight and positions are accepted)"))
    cash = custom.get("cash_weight")
    if not _is_number(cash) or not math.isfinite(cash):
        problems.append((f"{ROOT}.cash_weight", "must be a finite number (a portfolio fraction, 10% = 0.10)"))
    elif not 0 <= cash <= 1:
        problems.append((f"{ROOT}.cash_weight", "must be between 0 and 1; negative cash (leverage) is not supported"))
    positions = custom.get("positions")
    if not isinstance(positions, list):
        problems.append((f"{ROOT}.positions", "must be a list of positions"))
        return problems
    if len(positions) > MAX_POSITIONS:
        problems.append((f"{ROOT}.positions", f"has {len(positions)} positions; at most {MAX_POSITIONS} are accepted"))
    for index, position in enumerate(positions):
        path = f"{ROOT}.positions[{index}]"
        if not isinstance(position, dict) or set(position) != {"instrument_id", "weight"}:
            problems.append((path, "must be an object with exactly instrument_id and weight"))
            continue
        if not isinstance(position["instrument_id"], str):
            problems.append((f"{path}.instrument_id", "must be an instrument id"))
        weight = position["weight"]
        if not _is_number(weight) or not math.isfinite(weight):
            problems.append((f"{path}.weight", "must be a finite number (a portfolio fraction, 10% = 0.10)"))
        elif weight < 0:
            problems.append((f"{path}.weight", "is negative; shorting is not supported"))
        elif weight == 0:
            problems.append((f"{path}.weight", "is 0; a position that is not held is left out, not listed with a zero weight"))
        elif weight > 1:
            problems.append((f"{path}.weight", "is above 1; leverage is not supported"))
    return problems


def _semantic_problems(custom: dict[str, Any], purchasable: frozenset[str]) -> list[tuple[str, str]]:
    problems: list[tuple[str, str]] = []
    seen: set[str] = set()
    for index, position in enumerate(custom["positions"]):
        instrument_id = position["instrument_id"]
        path = f"{ROOT}.positions[{index}].instrument_id"
        if instrument_id in seen:
            problems.append((path, f"{instrument_id} appears more than once; each instrument is listed once"))
        elif instrument_id not in purchasable:
            problems.append((path, f"{instrument_id} is not one of purchasable_instrument_ids; no other asset can be held"))
        seen.add(instrument_id)
    # The same expression as byb_contracts.portfolio_errors, so the two can never disagree about a total.
    total = custom["cash_weight"] + sum(position["weight"] for position in custom["positions"])
    if not math.isfinite(total) or abs(total - 1.0) > EPS:
        if math.isfinite(total) and total > 1.0:
            why = "a total above 1 is leverage, which is not supported"
        else:
            why = "a total below 1 leaves part of the portfolio unaccounted for"
        problems.append((ROOT, f"cash_weight + sum(positions.weight) = {total!r}, must equal 1 (fractions, 10% = 0.10); {why}. "
                               "The weights are never rescaled: correct them and send the request again"))
    return problems


def _same_weights(custom: dict[str, Any], scenario_portfolio: dict[str, Any]) -> bool:
    """Rule 5: the same instruments, each weight and the cash within EPS. The order does not matter."""
    ours = {position["instrument_id"]: position["weight"] for position in custom["positions"]}
    theirs = {position["instrument_id"]: position["weight"] for position in scenario_portfolio["positions"]}
    return (ours.keys() == theirs.keys() and abs(custom["cash_weight"] - scenario_portfolio["cash_weight"]) <= EPS
            and all(abs(ours[instrument_id] - theirs[instrument_id]) <= EPS for instrument_id in ours))


def weights_digest(cash_weight: float, positions: Iterable[dict[str, Any]]) -> str:
    """SHA-256 (hex) of the canonical JSON of the cash weight and the positions sorted by instrument.

    Numbers are hashed as floats, so ``1`` and ``1.0`` (and ``-0.0`` and ``0``) are the same weight.
    """
    content = {
        "cash_weight": float(cash_weight) + 0.0,
        "positions": sorted(({"instrument_id": position["instrument_id"], "weight": float(position["weight"]) + 0.0} for position in positions),
                            key=lambda position: position["instrument_id"]),
    }
    return hashlib.sha256(json.dumps(content, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def custom_portfolio_id(persona_id: str, cash_weight: float, positions: Iterable[dict[str, Any]]) -> str:
    """``pf-<persona_id>-custom-<12 hex>``. The contract id pattern has no "_", which a persona id may contain."""
    return f"pf-{persona_id.replace('_', '-')}-custom-{weights_digest(cash_weight, positions)[:12]}"


def resolve_portfolio(scenario_portfolio: dict[str, Any], custom_portfolio: Any, purchasable_instrument_ids: Iterable[str]) -> dict[str, Any]:
    """The full portfolio document a request is checked against.

    ``custom_portfolio`` absent or ``None``: the scenario portfolio, the same object, unchanged.
    Otherwise the weights are checked (rules 1 to 3 of api.md 2a) and either the scenario portfolio
    is returned (equal weights, rule 5) or a new document is built (rule 4). Raises
    ``InvalidCustomPortfolio``; in that case nothing may be calculated or stored.
    """
    if custom_portfolio is None:
        return scenario_portfolio
    problems = shape_problems(custom_portfolio)
    if not problems:
        problems = _semantic_problems(custom_portfolio, frozenset(purchasable_instrument_ids))
    if problems:
        raise InvalidCustomPortfolio(problems)
    if _same_weights(custom_portfolio, scenario_portfolio):
        return scenario_portfolio
    positions = [{"instrument_id": position["instrument_id"], "weight": position["weight"]} for position in custom_portfolio["positions"]]
    portfolio = {
        "schema_version": scenario_portfolio["schema_version"],
        "portfolio_id": custom_portfolio_id(scenario_portfolio["persona_id"], custom_portfolio["cash_weight"], positions),
        "persona_id": scenario_portfolio["persona_id"],
        "fictional": True,
        "valuation_date": scenario_portfolio["valuation_date"],
        "base_currency": scenario_portfolio["base_currency"],
        "cash_weight": custom_portfolio["cash_weight"],
        "positions": positions,
    }
    if _ID_RE.fullmatch(portfolio["portfolio_id"]) is None:
        raise InvalidCustomPortfolio([(ROOT, "a portfolio id could not be derived for this persona")])
    try:
        validate_portfolio(portfolio)
    except ContractError as error:  # not reachable through the checks above; never hand the engine a document the contract refuses
        raise InvalidCustomPortfolio([(ROOT, str(issue)) for issue in list(error.errors)[:5]] or [(ROOT, "is not a valid portfolio")]) from error
    return portfolio


def is_customized(portfolio: dict[str, Any], scenario_portfolio: dict[str, Any]) -> bool:
    """True exactly when ``portfolio`` is not the persona's scenario portfolio (its ``portfolio_id`` differs).

    Weights equal to the scenario's resolve to the scenario portfolio itself (rule 5), and a job stored without a
    portfolio is checked against the scenario's, so both are not customized.
    """
    return portfolio["portfolio_id"] != scenario_portfolio["portfolio_id"]


def content_sha256(portfolio: dict[str, Any]) -> str:
    """SHA-256 (hex) of the whole portfolio document, recorded with an investigation outcome."""
    return hashlib.sha256(canonical_json(portfolio)).hexdigest()
