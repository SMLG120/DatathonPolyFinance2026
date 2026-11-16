""""Several limits in one request, everyday comparatives, and conflicts inside one request.

The model is a scripted fake; every number in a draft must still be traced to the investor's own sentence by the server.
"""

from __future__ import annotations

import pytest

from test_service_interpreter import EMPTY, all_rules, answer, interpret, service

CAP_ANY = {"rule_type": "max_issuer_exposure", "issuer_id": None}


def rules_of(text, *rules):
    status, draft = interpret(service(answer(dict(EMPTY, rules=list(rules)))), text)
    assert status == 200
    return draft


def test_cl01_two_limits_in_two_sentences_each_keep_their_own_number():
    text = "I want less than 10% in any one company. But at least 5% in Exxon Mobil."
    draft = rules_of(text, dict(CAP_ANY, words="less than 10% in any one company"),
                     {"words": "But at least 5% in Exxon Mobil", "rule_type": "min_issuer_exposure", "issuer_id": "EXXON_MOBIL"})
    assert [(r["rule_type"], r["threshold"], r["threshold_quote"]) for r in draft["proposed_rules"]] == [
        ("max_issuer_exposure", 0.1, "10%"), ("min_issuer_exposure", 0.05, "5%")]
    assert draft["clarifications"] == []


@pytest.mark.parametrize("text, words", [
    ("Keep any single company below 10%.", "Keep any single company below 10%"),
    ("Less than 10% in any one company.", "Less than 10% in any one company"),
    ("Under 10% in each company please.", "Under 10% in each company"),
    ("I don't want more than 10% in any company.", "more than 10% in any company"),
])
def test_cl02_everyday_maximum_wording_is_a_maximum(text, words):
    [rule] = rules_of(text, dict(CAP_ANY, words=words))["proposed_rules"]
    assert rule["threshold"] == 0.1 and rule["origin"] == "USER_STATED"


@pytest.mark.parametrize("text", ["More than 10% in any one company.", "Above 10% in any one company is what I want."])
def test_cl03_a_minimum_wording_is_never_drafted_as_a_maximum(text):
    draft = rules_of(text, dict(CAP_ANY, words=text.rstrip(".")))
    assert draft["proposed_rules"] == [] and all(r["threshold"] is None for r in all_rules(draft))


@pytest.mark.parametrize("text, words", [
    ("Max 10% or 15% per company.", "Max 10% or 15% per company"),
    ("Less than 10% in any company, but at least 5% in Exxon Mobil.", "Less than 10% in any company"),
    ("Keep each company under 10% and 15%.", "Keep each company under 10% and 15%"),
    ("I lost 30% in 2022, so keep each company under 10%.", "I lost 30% in 2022, so keep each company under 10%"),
])
def test_cl04_when_the_rules_own_words_hold_two_numbers_none_is_chosen(text, words):
    draft = rules_of(text, dict(CAP_ANY, words=words))
    assert draft["proposed_rules"] == [] and all(r["threshold"] is None for r in all_rules(draft))
    assert draft["clarifications"], "a number is asked for"


def test_cl05_a_number_from_another_clause_is_never_attached():
    text = "At most 10% in any company and at least 20% in Exxon Mobil."
    draft = rules_of(text, dict(CAP_ANY, words="At most 10% in any company", threshold_words="20%"))
    assert draft["proposed_rules"] == [] and all(r["threshold"] is None for r in all_rules(draft))


@pytest.mark.parametrize("text, other", [
    ("At most 5% in any company. At least 10% in Exxon Mobil.", dict(CAP_ANY, words="At most 5% in any company")),
    ("Avoid Exxon Mobil. Keep at least 10% in Exxon Mobil.", {"words": "Avoid Exxon Mobil", "rule_type": "exclusion", "issuer_ids": ["EXXON_MOBIL"]}),
])
def test_cl06_a_minimum_no_portfolio_can_meet_with_another_limit_is_a_question_not_two_drafts(text, other):
    minimum = {"words": text.split(". ")[-1].rstrip("."), "rule_type": "min_issuer_exposure", "issuer_id": "EXXON_MOBIL"}
    draft = rules_of(text, other, minimum)
    assert draft["proposed_rules"] == []
    [question] = draft["clarifications"]
    assert "cannot both hold" in question["question"]
    kept = {o["option_id"]: o["proposed_rule"] for o in question["options"]}
    assert kept["keep-first-limit"]["rule_type"] == other["rule_type"] and kept["keep-second-limit"]["rule_type"] == "min_issuer_exposure"
    assert kept["keep-qualitative"] is None
    assert all(r["status"] == "PROPOSED" for r in all_rules(draft)), "nothing is confirmed by the interpreter"


def test_cl07_equal_limits_are_not_a_conflict():
    text = "At most 5% in any company. At least 5% in Exxon Mobil."
    draft = rules_of(text, dict(CAP_ANY, words="At most 5% in any company"),
                     {"words": "At least 5% in Exxon Mobil", "rule_type": "min_issuer_exposure", "issuer_id": "EXXON_MOBIL"})
    assert len(draft["proposed_rules"]) == 2 and draft["clarifications"] == []
