"""Shared loaders for the engine tests."""

from __future__ import annotations

import copy
import json
from functools import lru_cache
from pathlib import Path

from byb_contracts import compute_content_hash, validate_policy

from backend import engine

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURES = REPO_ROOT / "contracts" / "fixtures" / "engine"
SCENARIOS = REPO_ROOT / "contracts" / "scenarios"
PROCESSED = REPO_ROOT / "data" / "processed"
CASE_IDS = [f"E{n:02d}" for n in range(1, 23)] + ["R1", "R2", "M1"]


@lru_cache(maxsize=None)
def _read(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load(path) -> dict:
    """A fresh copy each time, so a test can never leak a mutation into another."""
    return copy.deepcopy(_read(str(path)))


def case(case_id: str) -> dict:
    return load(FIXTURES / f"{case_id}.json")


def universe(name: str) -> dict:
    return load(FIXTURES / name)


def run_case(case_id: str, **overrides) -> dict:
    """check_rules on a fixture's inputs; ``target=`` overrides the requested final weight."""
    fixture = case(case_id)
    data = universe(fixture["universe"])
    inputs = fixture["inputs"]
    request = dict(inputs["purchase_request"])
    if "target" in overrides:
        request["target_direct_weight"] = overrides.pop("target")
    if "instrument_id" in overrides:
        request["instrument_id"] = overrides.pop("instrument_id")
    return engine.check_rules(
        overrides.pop("portfolio", inputs["portfolio"]), overrides.pop("policy", inputs["policy"]), request,
        data["instruments"], data["holdings"], data["market_data"], data["controversies"], **overrides,
    )


def make_policy(persona_id: str, objectives: list, rules: list, version: int = 1, parent_version=None, policy_id=None) -> dict:
    policy = {
        "schema_version": "1.0.0",
        "policy_id": policy_id or f"pol-{persona_id}-test",
        "persona_id": persona_id,
        "version": version,
        "parent_version": parent_version,
        "created_at": "2026-11-14T15:00:00Z",
        "objectives": objectives,
        "rules": rules,
        "change_note": "Built by the engine tests.",
        "content_hash": "sha256:" + "0" * 64,
    }
    policy["content_hash"] = compute_content_hash(policy)
    validate_policy(policy)
    return policy


def confirm(rule: dict, **changes) -> dict:
    """The stored form of a scenario rule the user accepted unchanged."""
    rule = dict(rule)
    rule.update(status="CONFIRMED", confirmed_at="2026-11-14T15:00:00Z", confirmed_by="demo_user")
    rule.update(changes)
    return rule


def rule(rule_id: str, rule_type: str, parameters: dict, threshold: float, **changes) -> dict:
    kind = {"min_issuer_exposure": "min_fraction", "scenario_loss_budget": "max_loss_fraction"}.get(rule_type, "max_fraction")
    built = {
        "rule_id": rule_id, "rule_type": rule_type, "parameters": parameters, "threshold": threshold, "threshold_kind": kind,
        "threshold_source": "FICTIONAL_SCENARIO", "threshold_quote": None, "unit": "fraction", "status": "CONFIRMED",
        "origin": "FICTIONAL_SCENARIO", "original_words": "Synthetic test rule.", "objective_id": None,
        "scope_description": "Synthetic test rule.", "confirmed_at": "2026-11-14T15:00:00Z", "confirmed_by": "demo_user",
        "supersedes_rule_id": None, "superseded_by_rule_id": None,
    }
    built.update(changes)
    return built


def portfolio(cash: float, positions: dict, portfolio_id: str = "pf-test") -> dict:
    return {
        "schema_version": "1.0.0", "portfolio_id": portfolio_id, "persona_id": "tester", "fictional": True,
        "valuation_date": "2026-11-12", "base_currency": "CAD", "cash_weight": cash,
        "positions": [{"instrument_id": i, "weight": w} for i, w in positions.items()],
    }


def request(instrument_id: str, target: float) -> dict:
    return {"instrument_id": instrument_id, "target_direct_weight": target, "funding": "CASH", "original_words": None}


def all_pass_and_funded(result: dict) -> bool:
    return (
        result["execution"]["status"] == "OK"
        and result["feasibility"]["status"] == "FEASIBLE"
        and bool(result["rule_results"])
        and all(entry["status"] == "PASS" for entry in result["rule_results"])
    )
