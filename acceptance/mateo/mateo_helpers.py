"""Loaders, policy builders and an independent hand-style calculation for the Mateo acceptance tests.

``hand_*`` functions redo the look-through arithmetic of ``contracts/SEMANTICS.md`` sections 5 and 6 from the
raw input documents (portfolio, instrument registry, holdings snapshot, controversy registry). They never call
the engine and never use ``contracts/python/tests/reference_calc.py``; they are what the engine output and the
fixtures' expected values are compared with.
"""

from __future__ import annotations

import copy
import json
from functools import lru_cache
from pathlib import Path

from byb_contracts import check_result_errors, compute_content_hash, validate_policy

from backend import engine
from mateo_invariants import EPS, check_result_problems, status_from_bounds

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = REPO_ROOT / "contracts"
ENGINE_FIXTURES = CONTRACTS / "fixtures" / "engine"
API_FIXTURES = CONTRACTS / "fixtures" / "api"
SCENARIO = CONTRACTS / "scenarios" / "mateo.json"
PROCESSED = REPO_ROOT / "data" / "processed"
REAL_REQUIRED = ("holdings.json", "instruments.json", "market_data.json", "controversies.json")
DATA_SOURCES = {"prices": "starter_prices_daily", "fx_usdcad": "starter_fx_usdcad"}
CONFIRMED_AT = "2026-11-14T15:00:00Z"


@lru_cache(maxsize=None)
def _read(path: str):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load(path):
    """A fresh deep copy each time: no test can leak a mutation into another."""
    return copy.deepcopy(_read(str(path)))


def scenario() -> dict:
    return load(SCENARIO)


def engine_case(case_id: str) -> dict:
    return load(ENGINE_FIXTURES / f"{case_id}.json")


def api_fixture(name: str) -> dict:
    return load(API_FIXTURES / f"{name}.json")


def synthetic_universe() -> dict:
    return load(ENGINE_FIXTURES / "mateo_synthetic_universe.json")


def real_data_present() -> bool:
    return all((PROCESSED / name).exists() for name in REAL_REQUIRED)


def real_universe() -> dict:
    return {
        "instruments": load(PROCESSED / "instruments.json"),
        "holdings": load(PROCESSED / "holdings.json"),
        "market_data": load(PROCESSED / "market_data.json"),
        "controversies": load(PROCESSED / "controversies.json"),
    }


# ---------------------------------------------------------------- policies and requests

def confirm(rule: dict, **changes) -> dict:
    """The stored form of a scenario rule the user accepted unchanged (SEMANTICS section 14)."""
    stored = dict(rule, status="CONFIRMED", confirmed_at=CONFIRMED_AT, confirmed_by="demo_user")
    stored.update(changes)
    return stored


def make_rule(rule_id: str, rule_type: str, parameters: dict, threshold, **changes) -> dict:
    kind = {"min_issuer_exposure": "min_fraction", "scenario_loss_budget": "max_loss_fraction"}.get(rule_type, "max_fraction")
    built = {
        "rule_id": rule_id, "rule_type": rule_type, "parameters": parameters, "threshold": threshold, "threshold_kind": kind,
        "threshold_source": "USER_ENTERED", "threshold_quote": None, "unit": "fraction", "status": "CONFIRMED",
        "origin": "USER_STATED", "original_words": "Acceptance-test rule.", "objective_id": None,
        "scope_description": "Acceptance-test rule.", "confirmed_at": CONFIRMED_AT, "confirmed_by": "demo_user",
        "supersedes_rule_id": None, "superseded_by_rule_id": None,
    }
    built.update(changes)
    return built


def make_policy(rules: list, objectives=None, policy_id: str = "pol-mateo-acceptance", version: int = 1) -> dict:
    policy = {
        "schema_version": "1.0.0", "policy_id": policy_id, "persona_id": "mateo", "version": version, "parent_version": None,
        "created_at": CONFIRMED_AT, "objectives": scenario()["objectives"] if objectives is None else objectives, "rules": rules,
        "change_note": "Built by the Mateo acceptance tests.", "content_hash": "sha256:" + "0" * 64,
    }
    policy["content_hash"] = compute_content_hash(policy)
    validate_policy(policy)
    return policy


def demo_policy() -> dict:
    """Mateo's policy as the demonstration confirms it: both scenario rules accepted unchanged."""
    return make_policy([confirm(rule) for rule in scenario()["scenario_rules"]])


def demo_request(target: float = None) -> dict:
    request = scenario()["demo_requests"][0]["purchase_request"]
    if target is not None:
        request["target_direct_weight"] = target
    return request


def portfolio_of(cash: float, positions: dict) -> dict:
    return {
        "schema_version": "1.0.0", "portfolio_id": "pf-mateo-acceptance", "persona_id": "mateo", "fictional": True,
        "valuation_date": "2026-11-12", "base_currency": "CAD", "cash_weight": cash,
        "positions": [{"instrument_id": i, "weight": w} for i, w in positions.items()],
    }


def run(universe: dict, policy, request: dict = None, portfolio: dict = None, *, validate: bool = True, **kwargs) -> dict:
    """``backend.engine.check_rules`` on one universe. Every result must satisfy the contract validators and
    the invariants of ``mateo_invariants`` (when execution is OK)."""
    result = engine.check_rules(
        scenario()["portfolio"] if portfolio is None else portfolio, policy, demo_request() if request is None else request,
        universe["instruments"], universe["holdings"], universe["market_data"], universe["controversies"], **kwargs,
    )
    if validate:
        assert check_result_errors(result) == []
        if result["execution"]["status"] == "OK":
            assert check_result_problems(result) == []
    return result


def by_rule(result: dict) -> dict:
    return {entry["rule_id"]: entry for entry in result["rule_results"]}


def records_of(result: dict) -> dict:
    return {record["evidence_id"]: record for record in result["evidence"]}


# ---------------------------------------------------------------- independent hand-style arithmetic

def proposed_positions(portfolio: dict, request: dict) -> tuple[list, float]:
    """Starting positions with the requested instrument set to its final weight; cash pays the difference."""
    positions = [(p["instrument_id"], p["weight"]) for p in portfolio["positions"]]
    held = dict(positions)
    target, start = request["target_direct_weight"], held.get(request["instrument_id"], 0.0)
    if request["instrument_id"] in held:
        positions = [(i, target if i == request["instrument_id"] else w) for i, w in positions]
    else:
        positions.append((request["instrument_id"], target))
    return positions, portfolio["cash_weight"] - (target - start)


def hand_lookthrough(positions: list, instruments: dict, holdings: dict) -> dict:
    """SEMANTICS section 5 for one portfolio state, straight from the input files."""
    registry, funds = instruments["instruments"], holdings["funds"]
    lower, by_label, coverage, out_of_scope = {}, {}, [], []
    uncovered = unclassified = in_scope = 0.0
    for instrument_id, weight in positions:
        if weight <= 0:
            continue
        entry = registry[instrument_id]
        if not entry["equity_scope"]:
            out_of_scope.append((instrument_id, weight))
            continue
        in_scope += weight
        if not entry["is_fund"]:
            lower[entry["issuer_id"]] = lower.get(entry["issuer_id"], 0.0) + weight
            if entry["sector"] is None:
                unclassified += weight
            else:
                bucket = by_label.setdefault(entry["sector"], {})
                bucket[entry["issuer_id"]] = bucket.get(entry["issuer_id"], 0.0) + weight
            continue
        fund = funds.get(instrument_id)
        if fund is None:
            uncovered += weight
            coverage.append({"fund_id": instrument_id, "portfolio_weight": weight, "coverage_fraction": 0.0, "sector_labelled_fraction": 0.0,
                             "uncovered_portfolio_weight": weight, "status": "MISSING", "holdings_date": None, "source_id": None})
            continue
        reported = sum(row["weight_fraction"] for row in fund["holdings"])  # the plain sum; nothing is rescaled
        labelled = sum(row["weight_fraction"] for row in fund["holdings"] if row["sector"] is not None)
        for row in fund["holdings"]:
            known = weight * row["weight_fraction"]
            lower[row["issuer_id"]] = lower.get(row["issuer_id"], 0.0) + known
            if row["sector"] is None:
                unclassified += known
            else:
                bucket = by_label.setdefault(row["sector"], {})
                bucket[row["issuer_id"]] = bucket.get(row["issuer_id"], 0.0) + known
        fund_uncovered = weight * max(0.0, 1.0 - reported)
        uncovered += fund_uncovered
        coverage.append({"fund_id": instrument_id, "portfolio_weight": weight, "coverage_fraction": reported, "sector_labelled_fraction": labelled,
                         "uncovered_portfolio_weight": fund_uncovered, "status": "COVERED" if reported >= 1.0 else "PARTIAL",
                         "holdings_date": fund["holdings_date"], "source_id": fund["source_id"]})
    return {"lower": lower, "by_label": by_label, "U": uncovered, "unclassified": unclassified, "in_scope": in_scope,
            "coverage": coverage, "out_of_scope": out_of_scope}


def hand_flagged(criteria: dict, controversies: dict) -> dict:
    """Issuer -> matching registry records (SEMANTICS section 6, controversy)."""
    flagged = {}
    for record in controversies["records"]:
        if record["nature"] not in criteria["natures"]:
            continue
        if criteria["event_date_from"] is not None and record["event_date"] < criteria["event_date_from"]:
            continue
        flagged.setdefault(record["issuer_id"], []).append(record)
    return flagged


def hand_bounds(rule: dict, look: dict, controversies: dict) -> dict:
    """[lower, upper] of one rule on one state, plus the issuers with proven exposure that count toward it."""
    kind, parameters = rule["rule_type"], rule["parameters"]
    if kind == "exclusion" and parameters["definition"]["kind"] == "fund_reported_sector":
        subjects = dict(look["by_label"].get(parameters["definition"]["sector"], {}))
        lower = sum(subjects.values())
        return {"lower": lower, "upper": lower + look["U"] + look["unclassified"], "subjects": subjects}
    if kind == "exclusion":
        subjects = {i: look["lower"][i] for i in parameters["definition"]["issuer_ids"] if look["lower"].get(i, 0.0) > 0}
        lower = sum(subjects.values())
        return {"lower": lower, "upper": lower + look["U"], "subjects": subjects}
    if kind == "controversy_exclusion":
        flagged = hand_flagged(parameters["criteria"], controversies)
        subjects = {i: look["lower"][i] for i in flagged if look["lower"].get(i, 0.0) > 0}
        return {"lower": sum(subjects.values()), "upper": look["in_scope"], "subjects": subjects}
    if kind == "max_issuer_exposure" and parameters["issuer_scope"] == "any":
        lower = max(look["lower"].values(), default=0.0)
        return {"lower": lower, "upper": lower + look["U"], "subjects": {i: v for i, v in look["lower"].items() if v > rule["threshold"] + EPS}}
    issuer = parameters["issuer_scope"] if kind == "max_issuer_exposure" else parameters["issuer_id"]
    lower = look["lower"].get(issuer, 0.0)
    return {"lower": lower, "upper": lower + look["U"], "subjects": {issuer: lower}}


def hand_rule(rule: dict, portfolio: dict, request: dict, universe: dict) -> dict:
    """Both states of one rule, by hand: bounds, status, breaching subjects with their own bounds."""
    out = {}
    states = {"starting": [(p["instrument_id"], p["weight"]) for p in portfolio["positions"]],
              "proposed": proposed_positions(portfolio, request)[0]}
    for state, positions in states.items():
        look = hand_lookthrough(positions, universe["instruments"], universe["holdings"])
        bounds = hand_bounds(rule, look, universe["controversies"])
        status = status_from_bounds(rule["rule_type"], bounds["lower"], bounds["upper"], rule["threshold"])
        subjects = []
        if status == "FAIL" and rule["rule_type"] != "min_issuer_exposure":
            ranked = sorted(bounds["subjects"].items(), key=lambda item: (-item[1], item[0]))[:10]
            subjects = [{"subject_kind": "ISSUER", "subject_id": i, "lower": v, "upper": v + look["U"]} for i, v in ranked]
        out[state] = {"lower": bounds["lower"], "upper": bounds["upper"], "status": status, "subjects": subjects, "look": look}
    return out


def hand_max_compliant_status(rules: list, portfolio: dict, request: dict, universe: dict, steps: int = 500) -> str:
    """SEMANTICS section 11 by brute force over the fundable targets ``(w0, w0 + cash]`` (no closed form)."""
    held = {p["instrument_id"]: p["weight"] for p in portfolio["positions"]}
    w0, cash = held.get(request["instrument_id"], 0.0), portfolio["cash_weight"]
    if not rules:
        return "WITHHELD"
    if cash <= EPS:
        return "NO_FEASIBLE_PURCHASE"
    some_all_pass, every_target_fails = False, True
    for step in range(1, steps + 1):
        target = w0 + cash * step / steps
        positions = proposed_positions(portfolio, dict(request, target_direct_weight=target))[0]
        look = hand_lookthrough(positions, universe["instruments"], universe["holdings"])
        statuses = []
        for rule in rules:
            bounds = hand_bounds(rule, look, universe["controversies"])
            statuses.append(status_from_bounds(rule["rule_type"], bounds["lower"], bounds["upper"], rule["threshold"]))
        some_all_pass = some_all_pass or all(s == "PASS" for s in statuses)
        every_target_fails = every_target_fails and "FAIL" in statuses
    return "SUPPORTED" if some_all_pass else "NO_FEASIBLE_PURCHASE" if every_target_fails else "WITHHELD"
