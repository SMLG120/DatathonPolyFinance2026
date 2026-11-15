"""Task 3: Mateo's interpretation fixtures (``POST /rules/interpret`` and the CLARIFY_PREFERENCE challenge).

They must show: a clarification question for "oil" whose options are the supported definitions (with the draft
each leads to) and the unsupported ones refused; no invented threshold; the user's words preserved; every
proposed rule inactive. ``interpretation_problems`` is the same check ``live_check.py`` applies to a live draft.
"""

import copy

import pytest
from byb_contracts import api_body_errors, interpretation_errors, rule_is_evaluated, validate_api_body

from live_check import interpretation_problems, mateo_oil_clarification_problems
from mateo_helpers import api_fixture, run, scenario, synthetic_universe
from mateo_invariants import MATEO_OBJECTIVE


@pytest.fixture()
def interpret():
    return api_fixture("interpret_mateo_clarification")


@pytest.fixture()
def draft(interpret):
    return interpret["response_body"]


def every_draft_rule(interpretation):
    rules = list(interpretation["proposed_rules"])
    for clarification in interpretation["clarifications"]:
        rules += [option["proposed_rule"] for option in clarification["options"] if option["proposed_rule"]]
    return rules


def test_fixture_is_a_valid_interpretation_of_mateos_sentence(interpret, draft):
    assert interpret["route"] == "POST /rules/interpret" and interpret["http_status"] == 200
    validate_api_body("api.schema.json#/$defs/interpret_request", interpret["request_body"])
    assert interpretation_errors(draft) == [] and api_body_errors("interpretation.schema.json", draft) == []
    assert interpret["request_body"]["text"] == MATEO_OBJECTIVE == scenario()["demo_phrases"][0]["original_words"]
    assert interpretation_problems(draft, MATEO_OBJECTIVE) == [] and mateo_oil_clarification_problems(draft) == []


def test_original_words_are_preserved_verbatim(draft):
    assert draft["original_words"] == MATEO_OBJECTIVE
    for objective in draft["objectives"]:
        assert objective["original_words"] in MATEO_OBJECTIVE and objective["source"] == "USER_STATED"
    assert [o["kind"] for o in draft["objectives"]] == ["goal", "preference", "constraint"]  # goals, preferences, constraints kept apart
    for rule in every_draft_rule(draft):
        assert rule["original_words"] in MATEO_OBJECTIVE
    for clarification in draft["clarifications"]:
        assert clarification["about_words"] in MATEO_OBJECTIVE


def test_oil_produces_a_clarification_question_not_a_rule(draft):
    assert len(draft["clarifications"]) == 1
    clarification = draft["clarifications"][0]
    assert clarification["about_words"] == "oil"
    assert "?" in clarification["question"]
    # nothing about oil / Energy is proposed outright: the user must choose a definition first
    assert [r["rule_type"] for r in draft["proposed_rules"]] == ["controversy_exclusion"]
    assert not [r for r in draft["proposed_rules"] if r["rule_type"] == "exclusion"]
    assert len(clarification["options"]) >= 2


def test_supported_options_are_the_d3_definitions_and_carry_their_draft(draft):
    options = {o["option_id"]: o for o in draft["clarifications"][0]["options"]}
    supported = {i for i, o in options.items() if o["supported"]}
    assert supported == {"energy-sector-label", "named-companies"}  # LEAD_DECISIONS D3: fund_reported_sector, named_issuers
    energy = options["energy-sector-label"]["proposed_rule"]
    assert energy["rule_type"] == "exclusion" and energy["parameters"] == {"definition": {"kind": "fund_reported_sector", "sector": "Energy"}}
    wanted = scenario()["scenario_rules"][0]
    assert energy["parameters"] == wanted["parameters"] and energy["threshold_kind"] == wanted["threshold_kind"]
    assert energy["scope_description"] == wanted["scope_description"]
    assert "Broader than oil" in options["energy-sector-label"]["description"]  # the label is not a list of oil producers
    assert options["named-companies"]["proposed_rule"] is None  # no company was named, so none is invented


def test_unsupported_definitions_are_refused_not_approximated(draft):
    options = {o["option_id"]: o for o in draft["clarifications"][0]["options"]}
    refused = {i: o for i, o in options.items() if not o["supported"]}
    assert set(refused) == {"oil-producers", "fossil-fuels"}  # D3: unsupported until a sourced classification is held
    for option in refused.values():
        assert option["proposed_rule"] is None and option["purchase_request"] is None
        assert "Not supported" in option["description"] and "sourced" in option["description"]
    # a draft that smuggled a rule into a refused option is rejected by the contract validator
    broken = copy.deepcopy(draft)
    target = next(o for o in broken["clarifications"][0]["options"] if o["option_id"] == "oil-producers")
    target["proposed_rule"] = copy.deepcopy(options["energy-sector-label"]["proposed_rule"])
    assert interpretation_errors(broken) != [] and interpretation_problems(broken, MATEO_OBJECTIVE) != []


def test_no_threshold_is_invented(draft):
    rules = every_draft_rule(draft)
    assert len(rules) == 2
    for rule in rules:
        assert rule["threshold"] is None and rule["threshold_source"] is None and rule["threshold_quote"] is None
        assert rule["origin"] == "SYSTEM_PROPOSED"
    assert not any(ch.isdigit() for ch in MATEO_OBJECTIVE.replace("8 to 12 years", ""))  # the sentence states no tolerance
    for invented in (0.0, 0.05):  # even the scenario's own 0 would be an invented number here
        broken = copy.deepcopy(draft)
        broken["proposed_rules"][0]["threshold"] = invented
        assert interpretation_errors(broken) != [] and interpretation_problems(broken, MATEO_OBJECTIVE) != []
    scenario_number = copy.deepcopy(draft)
    scenario_number["proposed_rules"][0].update(threshold=0.0, origin="FICTIONAL_SCENARIO", threshold_source="FICTIONAL_SCENARIO")
    assert interpretation_errors(scenario_number) != []  # the interpreter never emits FICTIONAL_SCENARIO rules


def test_proposed_rules_are_inactive(draft):
    rules = every_draft_rule(draft)
    for rule in rules:
        assert rule["status"] == "PROPOSED" and rule["confirmed_at"] is None and rule["confirmed_by"] is None
        assert rule_is_evaluated(rule) is False and rule_is_evaluated(rule, preview=True) is False  # no number: not even in a preview
    confirmed = copy.deepcopy(draft)
    confirmed["proposed_rules"][0].update(status="CONFIRMED", confirmed_at="2026-11-14T15:00:00Z", confirmed_by="demo_user")
    assert interpretation_errors(confirmed) != [] and interpretation_problems(confirmed, MATEO_OBJECTIVE) != []
    # the engine agrees: handed the interpreter's drafts as they are, it evaluates nothing
    result = run(synthetic_universe(), None, draft_rules=rules)
    assert result["rule_results"] == [] and result["summary"]["headline"] == "NO_RULES_EVALUATED"
    assert sorted(e["rule_id"] for e in result["rules_not_evaluated"]) == sorted(r["rule_id"] for r in rules)
    assert result["max_compliant"]["status"] == "WITHHELD"


def test_controversy_draft_is_kept_separate_from_the_oil_question(draft):
    rule = draft["proposed_rules"][0]
    assert rule["rule_type"] == "controversy_exclusion" and rule["original_words"] == "companies involved in significant controversies"
    assert rule["parameters"] == scenario()["scenario_rules"][1]["parameters"]
    assert "absence from the registry is unknown, never a pass" in rule["scope_description"]
    assert draft["unsupported"] == []


def test_clarify_preference_challenge_refuses_oil_producers_and_changes_nothing():
    fixture = api_fixture("challenge_clarify_preference")
    body = fixture["response_body"]
    assert fixture["http_status"] == 200 and api_body_errors("api.schema.json#/$defs/challenge_response", body) == []
    assert body["policy"] is None and body["investigation"] is None and body["proposed_correction"] is None  # nothing stored changes
    draft = body["interpretation"]
    words = fixture["request_body"]["payload"]["text"]
    assert draft["original_words"] == words == scenario()["demo_challenge"]["payload"]["text"]
    assert interpretation_problems(draft, words) == []
    assert draft["proposed_rules"] == []
    assert [(u["words"], u["code"]) for u in draft["unsupported"]] == [("companies that produce oil", "UNSUPPORTED_DEFINITION")]
    assert "stays as it is until you confirm" in draft["unsupported"][0]["reason"]
    options = draft["clarifications"][0]["options"]
    assert all(o["supported"] for o in options) and len(options) >= 2
    for rule in every_draft_rule(draft):
        assert rule["status"] == "PROPOSED" and rule["threshold"] is None and rule["origin"] == "SYSTEM_PROPOSED"
