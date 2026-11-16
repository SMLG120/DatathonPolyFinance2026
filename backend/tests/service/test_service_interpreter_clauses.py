"""Several limits in one request, everyday comparatives, and conflicts inside one request.

The model is a scripted fake; every number in a draft must still be traced to the investor's own sentence by the server.
Ported from the interpreter-3 extraction shape (PR #22) to the clause reading of interpreter-4: the behaviours are the same
unless a comment names an intentional change (docs/INTERPRETER.md).
"""

from __future__ import annotations

import pytest

from reading_fixtures import answer, cap_each, company, reading
from test_service_interpreter import all_rules, interpret, service


def read(text, *clauses, **kw):
    status, draft = interpret(service(answer(reading(*clauses, **kw))), text)
    assert status == 200
    return draft


def min_exxon(id, evidence, quantity):
    return company(id, evidence, "LIMIT", "AT_LEAST", "Exxon Mobil", ["EXXON_MOBIL"], quantity_mention=quantity)


def test_cl01_two_limits_in_two_sentences_each_keep_their_own_number():
    text = "I want less than 10% in any one company. But at least 5% in Exxon Mobil."
    draft = read(text, cap_each("c1", "less than 10% in any one company", "10%", "less than"),
                 min_exxon("c2", "at least 5% in Exxon Mobil", "5%"))
    assert [(r["rule_type"], r["threshold"], r["threshold_quote"]) for r in draft["proposed_rules"]] == [
        ("max_issuer_exposure", 0.1, "10%"), ("min_issuer_exposure", 0.05, "5%")]
    assert draft["clarifications"] == []


@pytest.mark.parametrize("text, words, cue", [
    ("Keep any single company below 10%.", "Keep any single company below 10%", "below"),
    ("Less than 10% in any one company.", "Less than 10% in any one company", "Less than"),
    ("Under 10% in each company please.", "Under 10% in each company", "Under"),
    ("I don't want more than 10% in any company.", "I don't want more than 10% in any company", "don't want more than"),
])
def test_cl02_everyday_maximum_wording_is_a_maximum(text, words, cue):
    [rule] = read(text, cap_each("c1", words, "10%", cue))["proposed_rules"]
    assert rule["threshold"] == 0.1 and rule["origin"] == "USER_STATED"


@pytest.mark.parametrize("text, cue", [("More than 10% in any one company.", "More than"),
                                       ("Above 10% in any one company is what I want.", "Above")])
def test_cl03_a_minimum_wording_is_never_drafted_as_a_maximum(text, cue):
    """A model that reads a minimum wording as AT_MOST is vetoed by the words it quotes as the direction."""
    draft = read(text, cap_each("c1", text.rstrip("."), "10%", cue))
    assert draft["proposed_rules"] == [] and all(r["threshold"] is None for r in all_rules(draft))


@pytest.mark.parametrize("text, words, quantity", [
    ("Max 10% or 15% per company.", "Max 10% or 15% per company", "10% or 15%"),
    ("Keep each company under 10% and 15%.", "Keep each company under 10% and 15%", "10%"),
    ("I lost 30% in 2022, so keep each company under 10%.", "I lost 30% in 2022, so keep each company under 10%", "10%"),
])
def test_cl04_when_the_rules_own_words_hold_two_numbers_none_is_chosen(text, words, quantity):
    draft = read(text, cap_each("c1", words, quantity, "under" if "under" in words else "Max"))
    assert draft["proposed_rules"] == [] and all(r["threshold"] is None for r in all_rules(draft))
    assert draft["clarifications"], "a number is asked for"


def test_cl04b_a_number_in_another_clause_no_longer_blocks_this_clauses_own_number():
    # Intentional change (plan keep_compatible 3): the clause's evidence holds only its own number, so 10% is kept.
    text = "Less than 10% in any company, but at least 5% in Exxon Mobil."
    draft = read(text, cap_each("c1", "Less than 10% in any company", "10%", "Less than"))
    assert [(r["rule_type"], r["threshold"]) for r in draft["proposed_rules"]] == [("max_issuer_exposure", 0.1)]


def test_cl05_a_number_from_another_clause_is_never_attached():
    """The model puts the minimum's 20% on the cap: the amount lies outside the cap's own words, so that clause is
    dropped on its own (not the whole answer), and 20% is never a cap. The minimum keeps its own number."""
    text = "At most 10% in any company and at least 20% in Exxon Mobil."
    draft = read(text, cap_each("c1", "At most 10% in any company", "20%", "At most"),
                 min_exxon("c2", "at least 20% in Exxon Mobil", "20%"))
    assert not [r for r in all_rules(draft) if r["rule_type"] == "max_issuer_exposure" and r["threshold"] is not None]
    assert [(r["rule_type"], r["threshold"]) for r in draft["proposed_rules"]] == [("min_issuer_exposure", 0.2)]


@pytest.mark.parametrize("text, other, minimum", [
    ("At most 5% in any company. At least 10% in Exxon Mobil.",
     cap_each("c1", "At most 5% in any company", "5%", "At most"), min_exxon("c2", "At least 10% in Exxon Mobil", "10%")),
    ("Avoid Exxon Mobil. Keep at least 10% in Exxon Mobil.",
     company("c1", "Avoid Exxon Mobil", "EXCLUDE", "NONE_AT_ALL", "Exxon Mobil", ["EXXON_MOBIL"]),
     min_exxon("c2", "Keep at least 10% in Exxon Mobil", "10%")),
])
def test_cl06_a_minimum_no_portfolio_can_meet_with_another_limit_is_a_question_not_two_drafts(text, other, minimum):
    draft = read(text, other, minimum)
    assert draft["proposed_rules"] == []
    [question] = draft["clarifications"]
    assert "cannot both hold" in question["question"]
    kept = {o["option_id"]: o["proposed_rule"] for o in question["options"]}
    # interpreter-4's CONFLICT template numbers its sides keep-1, keep-2 (render.py), in the order the investor wrote them.
    assert kept["keep-1"]["rule_type"] == ("max_issuer_exposure" if other["intent"] == "LIMIT" else "exclusion")
    assert kept["keep-2"]["rule_type"] == "min_issuer_exposure" and kept["keep-qualitative"] is None
    assert all(r["status"] == "PROPOSED" for r in all_rules(draft)), "nothing is confirmed by the interpreter"


def test_cl07_equal_limits_are_not_a_conflict():
    text = "At most 5% in any company. At least 5% in Exxon Mobil."
    draft = read(text, cap_each("c1", "At most 5% in any company", "5%", "At most"), min_exxon("c2", "At least 5% in Exxon Mobil", "5%"))
    assert len(draft["proposed_rules"]) == 2 and draft["clarifications"] == []
