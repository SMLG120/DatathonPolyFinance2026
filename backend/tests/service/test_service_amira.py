"""Amira, the third persona, through the real handlers on the real data snapshot.

These tests need the git-ignored ``data/processed`` files and are skipped with a reason when they are
absent. Amira's portfolio, objective wording, thresholds and requests are fictional-scenario values
(contracts/scenarios/amira.json); the model is a scripted fake, so no real Bedrock call is made.
"""

from __future__ import annotations

import json

import pytest
from byb_contracts import validate_api_body, validate_interpretation

from backend.agents.prompts import INTERPRETER_TOOL_NAME
from service_fakes import REAL_DATA_PRESENT, REAL_DATA_REASON, Service, api_fixture, confirm_body, engine_direct, scenario, tool_use_response

API = "api.schema.json#/$defs/"
needs_real_data = pytest.mark.skipif(not REAL_DATA_PRESENT, reason=REAL_DATA_REASON)
SENTENCE = "I want maximum growth and strict diversification."
# What a careful model marks in Amira's sentence (the same extraction as test_service_interpreter.AMIRA_EXTRACTION).
EXTRACTION = {
    "objectives": [{"words": "maximum growth", "kind": "goal"}, {"words": "strict diversification", "kind": "preference"}],
    "rules": [],
    "ambiguous": [{"words": "strict diversification", "topic": "DIVERSIFICATION", "objective": 1}],
    "unsupported": [{"words": "maximum growth", "reason": "GROWTH_OR_RETURN"}],
}


@needs_real_data
def test_am01_get_portfolio_amira_is_her_fictional_scenario_with_every_position_in_the_registry():
    svc = Service(None)
    status, body = svc.call("GET /portfolios/{persona_id}", path={"persona_id": "amira"})
    assert status == 200
    validate_api_body(API + "portfolio_response", body)
    assert body["scenario"] == scenario("amira") and body["scenario"]["fictional"] is True
    positions = body["scenario"]["portfolio"]["positions"]
    assert all(position["instrument_id"] in body["instruments"] for position in positions)
    assert all(rule["status"] == "PROPOSED" and rule["origin"] == "FICTIONAL_SCENARIO" for rule in body["scenario"]["scenario_rules"])
    # Crypto assets are outside company-exposure rules.
    assert body["instruments"]["BTC-USD"]["equity_scope"] is False and body["instruments"]["ETH-USD"]["equity_scope"] is False
    # The recorded fixture the frontend replays carries exactly the registry entries the service returns for her positions.
    recorded = api_fixture("portfolio_amira")["response_body"]
    assert recorded["scenario"] == body["scenario"]
    for instrument_id, entry in recorded["instruments"].items():
        assert body["instruments"][instrument_id] == entry, instrument_id
    assert svc.bedrock.calls == []


@needs_real_data
def test_am02_her_sentence_is_a_clarification_with_no_number_and_nothing_stored():
    svc = Service(None, bedrock_script=[tool_use_response(INTERPRETER_TOOL_NAME, EXTRACTION)])
    before = dict(svc.s3.objects)
    status, draft = svc.call("POST /rules/interpret", {"persona_id": "amira", "text": SENTENCE, "policy_id": None, "policy_version": None})
    assert status == 200
    validate_interpretation(draft)
    assert svc.s3.objects == before, "interpreting stores nothing"
    assert draft["original_words"] == SENTENCE and draft["persona_id"] == "amira" and draft["proposed_rules"] == []
    [question] = draft["clarifications"]
    assert question["about_words"] == "strict diversification"
    drafts = [option["proposed_rule"] for option in question["options"] if option["proposed_rule"]]
    assert drafts and all(rule["threshold"] is None and rule["status"] == "PROPOSED" for rule in drafts)
    assert [u["code"] for u in draft["unsupported"]] == ["UNSUPPORTED_RULE_TYPE"]
    text = json.dumps(draft).lower().replace("not a proven contradiction", "")
    assert "contradict" not in text and "proven_conflict" not in text


@needs_real_data
def test_am03_her_scenario_rule_is_checked_by_the_engine_alone():
    svc = Service(None)
    status, confirmed = svc.call("POST /rules/confirm", confirm_body("amira"))
    assert status == 201
    policy = confirmed["policy"]
    assert policy["version"] == 1 and [r["status"] for r in policy["rules"]] == ["CONFIRMED"]
    for demo in scenario("amira")["demo_requests"]:
        request = demo["purchase_request"]
        status, check = svc.call("POST /check", {"persona_id": "amira", "policy_id": policy["policy_id"], "policy_version": 1,
                                                 "purchase_request": request, "draft_rules": None})
        assert status == 200
        validate_api_body("check_result.schema.json", check)
        assert check == engine_direct(None, "amira", policy, request), request["instrument_id"]
    assert svc.bedrock.calls == [], "/check and /rules/confirm never call a model"
