"""Every fixture and every scenario validates with the standard-library validators (byb_contracts).

The same documents are validated a second time with the `jsonschema` package
in test_jsonschema.py when that package is importable.
"""

from __future__ import annotations

import json

import pytest

import byb_contracts as byb
from byb_contracts.schema import _errors_for, resolve_ref
from paths import API, API_FIXTURES, CASES, ENGINE, REQUEST_SCHEMAS, SCENARIOS, UNIVERSES, all_rules, load


def test_the_expected_files_exist():
    """Guards against a glob that silently matches nothing."""
    assert [p.stem for p in UNIVERSES] == ["mateo_synthetic_universe", "robert_synthetic_universe", "synthetic_universe"]
    assert [p.stem for p in CASES] == [f"E{i:02d}" for i in range(1, 23)] + ["M1", "R1", "R2"]
    assert [p.stem for p in SCENARIOS] == ["amira", "mateo", "robert"]
    assert len(API_FIXTURES) >= 20
    assert (ENGINE / "HAND_CALCS.md").is_file()


# ------------------------------------------------------------------------------------ engine universes

@pytest.mark.parametrize("path", UNIVERSES, ids=[p.stem for p in UNIVERSES])
def test_engine_universe_validates(path):
    universe = load(path)
    assert byb.schema_errors(universe, "fixture.schema.json#/$defs/engine_universe") == []
    assert universe["fixture"] is True and universe["synthetic"] is True and universe["synthetic_note"].startswith("SYNTHETIC")
    assert universe["universe_id"] == path.stem
    byb.validate_instrument_registry(universe["instruments"])
    byb.validate_holdings_snapshot(universe["holdings"])
    byb.validate_market_data(universe["market_data"])
    byb.validate_source_registry(universe["sources"])
    sources = set(universe["sources"]["sources"])
    byb.validate_controversy_registry(universe["controversies"], known_source_ids=sources)
    instruments = universe["instruments"]["instruments"]
    for fund_id, fund in universe["holdings"]["funds"].items():
        assert fund_id in instruments and instruments[fund_id]["is_fund"], f"{fund_id}: holdings for something that is not a registered fund"
        assert fund["source_id"] in sources
        for row in fund["holdings"]:
            assert row["sector_source"] is None or row["sector_source"] in sources
            if row["instrument_id"] is not None and row["instrument_id"] in instruments:
                assert instruments[row["instrument_id"]]["issuer_id"] == row["issuer_id"], f"{fund_id}: {row['instrument_id']} maps to another issuer in the registry"
    for instrument_id in universe["market_data"]["prices"]:
        assert instrument_id in instruments
        assert universe["market_data"]["prices"][instrument_id]["currency"] == instruments[instrument_id]["currency"]


# ------------------------------------------------------------------------------------ engine cases

def partial_errors(value, schema, file_name, path="expected"):
    """Validate a PARTIAL document: the schema with every `required` list ignored. Catches misspelled keys and bad enum values."""
    if "$ref" in schema:
        target, target_file = resolve_ref(schema["$ref"], file_name)
        return partial_errors(value, target, target_file, path)
    for word in ("anyOf", "oneOf"):
        if word in schema:
            return min((partial_errors(value, alternative, file_name, path) for alternative in schema[word]), key=len)
    if isinstance(value, dict):
        if "type" in schema and "object" not in ([schema["type"]] if isinstance(schema["type"], str) else schema["type"]):
            return [f"{path}: an object is not allowed here"]
        errors, properties = [], schema.get("properties", {})
        for key, item in value.items():
            if key in properties:
                errors.extend(partial_errors(item, properties[key], file_name, f"{path}.{key}"))
            elif schema.get("additionalProperties") is False:
                errors.append(f"{path}: '{key}' is not a property of the contract")
        return errors
    if isinstance(value, list):
        if "type" in schema and "array" not in ([schema["type"]] if isinstance(schema["type"], str) else schema["type"]):
            return [f"{path}: an array is not allowed here"]
        errors, items = [], schema.get("items")
        if isinstance(items, dict):
            for i, item in enumerate(value):
                errors.extend(partial_errors(item, items, file_name, f"{path}[{i}]"))
        return errors
    return _errors_for(value, schema, file_name, path)


@pytest.mark.parametrize("path", CASES, ids=[p.stem for p in CASES])
def test_engine_case_validates(path):
    case = load(path)
    assert byb.schema_errors(case, "fixture.schema.json#/$defs/engine_fixture") == []
    assert case["fixture"] is True and case["synthetic"] is True and case["synthetic_note"].startswith("SYNTHETIC")
    assert case["fixture_id"] == path.stem
    universe = load(ENGINE / case["universe"])
    byb.validate_portfolio(case["inputs"]["portfolio"])
    byb.validate_policy(case["inputs"]["policy"])
    byb.validate_purchase_request(case["inputs"]["purchase_request"])
    assert case["inputs"]["portfolio"]["persona_id"] == case["inputs"]["policy"]["persona_id"]
    for position in case["inputs"]["portfolio"]["positions"]:
        assert position["instrument_id"] in universe["instruments"]["instruments"]
    assert partial_errors(case["expected"], byb.load_schema("check_result.schema.json"), "check_result.schema.json") == []
    headings = [line[3:].split(" ")[0] for line in (ENGINE / "HAND_CALCS.md").read_text(encoding="utf-8").splitlines() if line.startswith("## ")]
    assert case["hand_calc"] in headings, f"HAND_CALCS.md has no '## {case['hand_calc']}' section"


def test_partial_validation_catches_a_misspelled_key_and_a_bad_enum():
    case = load(ENGINE / "E01.json")
    schema = byb.load_schema("check_result.schema.json")
    wrong_key = json.loads(json.dumps(case["expected"]))
    wrong_key["rule_results"][0]["mesured"] = wrong_key["rule_results"][0].pop("measured")
    assert partial_errors(wrong_key, schema, "check_result.schema.json")
    wrong_enum = json.loads(json.dumps(case["expected"]))
    wrong_enum["rule_results"][0]["status"] = "COMPLIANT"
    assert partial_errors(wrong_enum, schema, "check_result.schema.json")


# ------------------------------------------------------------------------------------ scenarios

@pytest.mark.parametrize("path", SCENARIOS, ids=[p.stem for p in SCENARIOS])
def test_scenario_validates(path):
    scenario = load(path)
    byb.validate_scenario(scenario)
    assert scenario["fictional"] is True and scenario["portfolio"]["fictional"] is True
    assert scenario["persona"]["persona_id"] == path.stem
    assert scenario["persona"]["case_reference"].startswith("Case p.")
    for fact in scenario["persona"]["facts"]:
        assert fact["case_reference"].startswith("Case p."), "every persona fact cites a case page"
    for request in scenario["demo_requests"]:
        byb.validate_purchase_request(request["purchase_request"])


# ------------------------------------------------------------------------------------ API fixtures

@pytest.mark.parametrize("path", API_FIXTURES, ids=[p.stem for p in API_FIXTURES])
def test_api_fixture_validates(path):
    fixture = load(path)
    assert byb.schema_errors(fixture, "fixture.schema.json#/$defs/api_fixture") == []
    assert fixture["fixture"] is True and fixture["fixture_id"] == path.stem
    assert fixture["synthetic_note"].startswith("SYNTHETIC") == fixture["synthetic"]
    assert byb.api_body_errors(fixture["response_schema"], fixture["response_body"]) == []
    is_error = fixture["response_schema"].endswith("error_response")
    assert is_error == (fixture["http_status"] >= 400), "error bodies go with 4xx/5xx statuses and nothing else"
    request_schema = REQUEST_SCHEMAS.get(fixture["route"])
    if fixture["route"].startswith("GET "):
        assert fixture["request_body"] is None
    elif fixture["http_status"] != 400:
        assert byb.schema_errors(fixture["request_body"], request_schema) == [], "the example request must itself be valid"
    else:
        assert byb.schema_errors(fixture["request_body"], request_schema) != [], "a 400 example must show a body that really is malformed"
    if fixture["http_status"] != 401:
        assert fixture["request_headers"].get("Authorization", "").startswith("Bearer ")
    if fixture["route"] == "POST /investigations" or (fixture["route"].endswith("/challenge") and fixture["request_body"]["type"] == "CHANGE_RULE"):
        assert byb.schema_errors(fixture["request_headers"].get("Idempotency-Key"), "investigation_job.schema.json#/properties/idempotency_key") == []


def test_every_route_has_an_example():
    routes = {load(p)["route"] for p in API_FIXTURES}
    assert routes == {"GET /portfolios/{persona_id}", "POST /rules/interpret", "POST /rules/confirm", "POST /check", "POST /investigations",
                      "GET /investigations/{id}", "POST /investigations/{id}/challenge"}


def test_the_lead_s_required_examples_are_present():
    job = lambda name: load(API / f"{name}.json")["response_body"]  # noqa: E731
    assert job("investigation_robert_queued")["status"] == "QUEUED"
    running = job("investigation_robert_running")
    assert running["status"] == "RUNNING" and running["steps"] and running["steps"][-1]["status"] == "RUNNING"
    first = job("investigation_robert_succeeded")
    assert first["status"] == "SUCCEEDED" and first["result"]["summary"]["headline"] == "HAS_FAIL"
    assert first["result"]["max_compliant"]["status"] == "SUPPORTED" and first["result"]["max_compliant"]["final_direct_weight"] is not None
    after = job("investigation_robert_after_challenge_succeeded")
    statuses = {r["rule_type"]: r for r in after["result"]["rule_results"]}
    assert statuses["max_issuer_exposure"]["status"] == "PASS"
    assert statuses["scenario_loss_budget"]["status"] == "FAIL" and statuses["scenario_loss_budget"]["gap"] > 0
    assert after["policy_version"] == 2 and after["parent_investigation_id"] == first["id"]
    assert job("investigation_failed")["status"] == "FAILED"
    mateo = job("investigation_mateo_succeeded")["result"]
    assert any(c["status"] == "MISSING" for c in mateo["data_coverage"]) and any(r["status"] == "UNKNOWN" for r in mateo["rule_results"])
    assert len(mateo["starting_portfolio_findings"]) == 1
    assert job("interpret_mateo_clarification")["clarifications"]
    assert "error" in job("error_validation")


def test_the_api_results_are_the_hand_calculated_ones():
    """The Robert and Mateo API examples carry exactly the numbers of engine fixtures R1, R2 and M1."""
    pairs = (("R1", "investigation_robert_succeeded"), ("R2", "investigation_robert_after_challenge_succeeded"), ("M1", "investigation_mateo_succeeded"))
    for case_id, fixture_id in pairs:
        expected = load(ENGINE / f"{case_id}.json")["expected"]
        result = load(API / f"{fixture_id}.json")["response_body"]["result"]
        assert byb.subset_mismatches(expected, result) == []
        broken = json.loads(json.dumps(result))
        broken["rule_results"][0]["measured"]["lower"] += 1e-6
        assert byb.subset_mismatches(expected, broken) != []


# ------------------------------------------------------------------------------------ acceptance criteria

def test_no_confirmed_rule_has_a_null_threshold_and_no_system_proposed_rule_has_a_number():
    seen = 0
    for path in CASES + SCENARIOS + API_FIXTURES:
        for where, rule in all_rules(load(path)):
            seen += 1
            assert byb.rule_errors(rule) == [], f"{path.name} {where}"
            if rule["status"] in ("CONFIRMED", "SUPERSEDED"):
                assert isinstance(rule["threshold"], (int, float)), f"{path.name} {where}: {rule['status']} rule without a number"
            if rule["origin"] == "SYSTEM_PROPOSED":
                assert rule["threshold"] is None and rule["threshold_source"] is None, f"{path.name} {where}: SYSTEM_PROPOSED rule carries a number"
            if rule["threshold"] is not None:
                assert 0 <= rule["threshold"] <= 1 and rule["unit"] == "fraction", f"{path.name} {where}: thresholds are fractions"
    # Counted from the specs when this was written: 30 rules in engine cases, 7 in scenarios, 15 in API fixtures.
    assert seen >= 50, f"the rule walker found only {seen} rules; it should find every rule in every fixture"


def test_all_rules_finds_rules_wherever_they_are_nested():
    document = {"a": [{"b": {"rule_id": "r1", "rule_type": "exclusion", "threshold": None, "origin": "SYSTEM_PROPOSED"}}], "rule_id": "not-a-rule"}
    assert [where for where, _ in all_rules(document)] == ["$.a[0].b"]
