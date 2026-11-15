"""Locations and small helpers shared by the contract tests."""

from __future__ import annotations

import json
from pathlib import Path

CONTRACTS = Path(__file__).resolve().parents[2]
REPO = CONTRACTS.parent
SCHEMAS = CONTRACTS / "schemas"
ENGINE = CONTRACTS / "fixtures" / "engine"
API = CONTRACTS / "fixtures" / "api"
SCENARIO_DIR = CONTRACTS / "scenarios"
UNIVERSES = sorted(ENGINE.glob("*universe.json"))
CASES = sorted(p for p in ENGINE.glob("*.json") if "universe" not in p.name)
SCENARIOS = sorted(SCENARIO_DIR.glob("*.json"))
API_FIXTURES = sorted(API.glob("*.json"))
REQUEST_SCHEMAS = {
    "POST /rules/interpret": "api.schema.json#/$defs/interpret_request",
    "POST /rules/confirm": "api.schema.json#/$defs/confirm_request",
    "POST /check": "api.schema.json#/$defs/check_request",
    "POST /investigations": "api.schema.json#/$defs/investigation_create_request",
    "POST /investigations/{id}/challenge": "api.schema.json#/$defs/challenge_request",
}
RULE_KEYS = {"rule_id", "rule_type", "threshold", "origin"}


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def all_rules(document, where="$"):
    """Yield (path, rule) for every rule object nested anywhere in a document."""
    if isinstance(document, dict):
        if RULE_KEYS <= set(document):
            yield where, document
            return
        for key, value in document.items():
            yield from all_rules(value, f"{where}.{key}")
    elif isinstance(document, list):
        for i, item in enumerate(document):
            yield from all_rules(item, f"{where}[{i}]")
