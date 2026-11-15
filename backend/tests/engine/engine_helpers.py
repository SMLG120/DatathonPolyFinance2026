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
CASE_IDS = [f"E{n:02d}" for n in range(1, 23)] + ["R1", "R2", "M1", "M2"]


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


def boundary_from_its_evidence(result: dict, derived_from=None) -> float:
    """Recompute the maximum compliant final weight from the records ``ev-max-final`` cites, and nothing else.

    Supports the Robert-shaped case: a direct equity purchase under any-issuer caps and scenario loss budgets.
    Raises AssertionError when a record the closed form needs is not cited, so a missing ``derived_from`` link
    fails the test that calls this.
    """
    records = {record["evidence_id"]: record for record in result["evidence"]}
    final_record = records[result["max_compliant"]["evidence_ids"][0]]
    assert final_record["metric_id"] == "max_compliant_final_weight"
    cited_ids = final_record["derived_from"] if derived_from is None else derived_from
    cited = [records[i] for i in cited_ids]

    def pick(metric, state=None, subject=None):
        return [r for r in cited if r["metric_id"] == metric and (state is None or r["subject"]["portfolio_state"] == state)
                and (subject is None or r["subject"]["id"] == subject)]

    def everywhere(metric, state, subject=None):
        return [r for r in result["evidence"] if r["metric_id"] == metric and r["subject"]["portfolio_state"] == state
                and (subject is None or r["subject"]["id"] == subject)]

    instrument_id = result["purchase_request"]["instrument_id"]
    added = result["feasibility"]["additional_purchase"]
    assert added > 0, "helper needs a request that buys something"
    issuer = next(e["issuer_id"] for e in result["exposure"]["issuers"] if abs(e["proposed"]["direct"] - e["starting"]["direct"] - added) < 1e-12)
    cash = pick("cash_weight", "STARTING")
    start_weight = pick("position_weight", "STARTING", instrument_id)
    assert len(cash) == 1, "starting cash is not cited"
    assert len(start_weight) == 1, "the starting direct weight is not cited"
    w0 = start_weight[0]["value"]
    ends = [w0 + cash[0]["value"]]
    for entry in result["rule_results"]:
        threshold = pick("rule_threshold", subject=entry["rule_id"])
        assert len(threshold) == 1, f"the threshold of {entry['rule_id']} is not cited"
        limit = threshold[0]["value"]
        if entry["rule_type"] == "scenario_loss_budget":
            start_return = pick("scenario_terminal_return", "STARTING")
            instrument_return = pick("scenario_instrument_return", subject=instrument_id)
            assert len(start_return) == 1, "the starting scenario return is not cited"
            assert len(instrument_return) == 1, "the instrument's scenario return is not cited"
            loss, slope = -start_return[0]["value"], -instrument_return[0]["value"]
            assert slope > 0, "helper supports a purchase that adds to the loss"
            ends.append(w0 + (limit - loss) / slope)
        elif entry["rule_type"] == "max_issuer_exposure":
            direct, via, extra = (pick(m, "STARTING", s) for m, s in (
                ("issuer_direct_exposure", issuer), ("issuer_exposure_via_fund", issuer), ("unattributed_fund_weight", None)))
            for cited_records, metric, subject, what in (
                (direct, "issuer_direct_exposure", issuer, "direct exposure"),
                (via, "issuer_exposure_via_fund", issuer, "look-through exposure"),
                (extra, "unattributed_fund_weight", None, "unattributed fund weight"),
            ):
                wanted = {r["evidence_id"] for r in everywhere(metric, "STARTING", subject)}
                assert {r["evidence_id"] for r in cited_records} == wanted, f"{what} records not cited: {sorted(wanted)}"
            known = sum(r["value"] for r in direct) + sum(r["value"] for r in via)
            ends.append(w0 + limit - known - sum(r["value"] for r in extra))
        else:
            raise AssertionError(f"helper does not support {entry['rule_type']}")
    return min(1.0, round(min(ends), 9))
