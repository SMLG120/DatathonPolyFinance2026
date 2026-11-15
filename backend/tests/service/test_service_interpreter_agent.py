"""The interpretation agent: themes, sector focus, company lookups and the bounded tool loop (ia01-ia14).

Same harness as ``test_service_interpreter.py``: a scripted fake model, the real route, and the contract checks of
``interpret`` (nothing stored, every draft PROPOSED, no number the investor did not write, no model prose).
"""

import json

import pytest

from backend.agents import interpreter as itp
from backend.agents.prompts import DESCRIBE_SECTOR_TOOL_NAME, FIND_COMPANIES_TOOL_NAME, INTERPRETER_TOOL_NAME
from service_fakes import final_response, tool_use_response
from test_service_interpreter import EMPTY, PROSE, all_rules, answer, interpret, options_of, service

MATEO_SECTORS = ["Energy", "Financials", "Industrials", "Information Technology", "Utilities"]


def lookup(name, arguments, tool_use_id="tooluse_lookup"):
    return tool_use_response(name, arguments, tool_use_id=tool_use_id)


def theme(words, code="ENVIRONMENTAL", polarity="ONLY", **extra):
    return dict(EMPTY, ambiguous=[dict({"words": words, "topic": "THEME", "theme": code, "polarity": polarity}, **extra)])


# --------------------------------------------------------------------------- themes


def test_ia01_only_environmental_investments_is_a_question_with_the_checkable_definitions():
    text = "I want only environmental investments"
    status, draft = interpret(service(answer(theme("only environmental investments"))), text)
    assert status == 200 and draft["proposed_rules"] == []
    options = options_of(draft, "only environmental investments")
    assert list(options) == ["energy-sector-label", "recorded-controversies", "named-sectors", "named-companies",
                             "green-classification", "keep-qualitative"]
    energy = options["energy-sector-label"]["proposed_rule"]
    assert energy["parameters"] == {"definition": {"kind": "fund_reported_sector", "sector": "Energy"}} and energy["threshold"] is None
    controversy = options["recorded-controversies"]["proposed_rule"]
    assert controversy["rule_type"] == "controversy_exclusion" and controversy["threshold"] is None
    assert options["green-classification"]["supported"] is False and options["green-classification"]["proposed_rule"] is None
    [clarification] = draft["clarifications"]
    assert "can only be checked by leaving out" in clarification["question"]


@pytest.mark.parametrize("text, words, code, polarity", [
    ("Nothing that hurts the planet, please.", "Nothing that hurts the planet", "ENVIRONMENTAL", "AVOID"),
    ("I'd like my money in greener companies.", "greener companies", "ENVIRONMENTAL", "PREFER"),
    ("Keep it ethical and responsible.", "Keep it ethical and responsible", "ESG", "PREFER"),
    ("No firms with child labour.", "No firms with child labour", "SOCIAL", "AVOID"),
])
def test_ia02_paraphrased_values_wishes_become_theme_questions(text, words, code, polarity):
    status, draft = interpret(service(answer(theme(words, code, polarity))), text)
    assert status == 200
    options = options_of(draft, words)
    assert options[itp._THEME_UNSUPPORTED[code][0]]["supported"] is False
    assert ("energy-sector-label" in options) == (code == "ENVIRONMENTAL"), "the Energy stand-in is offered for environmental wishes only"
    assert all(rule["threshold"] is None and rule["origin"] == "SYSTEM_PROPOSED" for rule in all_rules(draft))


@pytest.mark.parametrize("text, about", [
    ("I want only environmental investments", "only environmental investments"),
    ("Please invest exclusively in green companies.", "exclusively in green companies"),
    ("I want to avoid polluters.", "avoid polluters"),
])
def test_ia03_the_server_asks_the_theme_question_when_the_model_gives_no_code(text, about):
    """A weak answer (only an objective, or nothing) still yields the question: the safety net reads the request text."""
    for extraction in (EMPTY, dict(EMPTY, objectives=[{"words": text.rstrip("."), "kind": "preference"}])):
        status, draft = interpret(service(answer(extraction)), text)
        assert status == 200 and [c["about_words"] for c in draft["clarifications"]] == [about]
        assert "recorded-controversies" in options_of(draft, about)


def test_ia04_the_safety_net_needs_a_cue_and_never_overrides_the_model_or_the_oil_question():
    # A plain mention is context, not a request (Mateo's "ESG matters to me").
    status, draft = interpret(service(answer(EMPTY)), "ESG matters to me.")
    assert status == 200 and draft["clarifications"] == []
    # The model already gave the words a code: no second question.
    text = "Only green companies."
    rule = {"words": "Only green companies", "rule_type": "controversy_exclusion"}
    status, draft = interpret(service(answer(dict(EMPTY, rules=[rule]))), text)
    assert status == 200 and draft["clarifications"] == [] and [r["rule_type"] for r in draft["proposed_rules"]] == ["controversy_exclusion"]
    # Oil keeps its own question.
    status, draft = interpret(service(answer(EMPTY)), "Only oil-free, environmentally friendly holdings.")
    assert status == 200 and any(c["about_words"] == "oil" for c in draft["clarifications"])


def test_ia05_an_unknown_theme_or_polarity_code_is_rejected_then_502():
    bad = answer(theme("only environmental investments", code="GREEN"))
    status, body = interpret(service(bad, bad), "I want only environmental investments")
    assert (status, body["error"]["code"]) == (502, "INTERPRETER_FAILED")
    bad = answer(theme("only environmental investments", polarity="MOSTLY"))
    status, _ = interpret(service(bad, bad), "I want only environmental investments")
    assert status == 502


# --------------------------------------------------------------------------- sector focus


@pytest.mark.parametrize("text, words, keep", [
    ("I only want tech stocks.", "only want tech stocks", ["Information Technology"]),
    ("Just banks and utilities for me.", "Just banks and utilities", ["Financials", "Utilities"]),
    ("Only Energy.", "Only Energy", ["Energy"]),
])
def test_ia06_only_some_sectors_drafts_one_exclusion_per_other_sector_without_a_number(text, words, keep):
    extraction = dict(EMPTY, ambiguous=[{"words": words, "topic": "SECTOR_FOCUS", "sectors": keep}])
    status, draft = interpret(service(answer(extraction)), text)
    assert status == 200 and draft["clarifications"] == [] and draft["unsupported"] == []
    excluded = [rule["parameters"]["definition"]["sector"] for rule in draft["proposed_rules"]]
    assert excluded == [label for label in MATEO_SECTORS if label not in keep]
    assert all(rule["rule_type"] == "exclusion" and rule["threshold"] is None and rule["original_words"] == words for rule in draft["proposed_rules"])
    assert len({rule["rule_id"] for rule in draft["proposed_rules"]}) == len(excluded)


def test_ia07_a_sector_focus_the_investor_did_not_write_is_unsupported_not_guessed():
    """The model maps "environmental" to Utilities: the server does not accept a sector the words do not name."""
    text = "I want only environmental investments"
    extraction = dict(EMPTY, ambiguous=[{"words": "only environmental investments", "topic": "SECTOR_FOCUS", "sectors": ["Utilities"]}])
    status, draft = interpret(service(answer(extraction)), text)
    assert status == 200 and draft["proposed_rules"] == []
    [unsupported] = draft["unsupported"]
    assert unsupported["code"] == "UNSUPPORTED_DEFINITION" and "Utilities" in unsupported["reason"] and "could not be matched" in unsupported["reason"]


def test_ia08_a_sector_focus_label_outside_the_snapshot_is_rejected():
    extraction = dict(EMPTY, ambiguous=[{"words": "only tech", "topic": "SECTOR_FOCUS", "sectors": ["Crypto"]}])
    status, _ = interpret(service(answer(extraction), answer(extraction)), "I want only tech.")
    assert status == 502


# --------------------------------------------------------------------------- companies


def test_ia09_common_company_names_resolve_without_a_lookup():
    reference = itp._Reference(service(answer(EMPTY)).api._snapshot())
    assert reference.companies_in("No more than 5% in RBC") == ["ROYAL_BANK_OF_CANADA"]
    assert reference.companies_in("avoid Exxon") == ["EXXON_MOBIL"]
    assert reference.companies_in("I said no more than that") == [], "aliases match whole words only"


def test_ia10_the_agent_looks_up_a_misspelled_company_and_may_then_use_it():
    text = "At most 5% in Microsft."
    rule = {"words": "At most 5% in Microsft", "rule_type": "max_issuer_exposure", "issuer_id": "MICROSOFT"}
    svc = service(lookup(FIND_COMPANIES_TOOL_NAME, {"words": "Microsft"}), answer(dict(EMPTY, rules=[rule])))
    status, draft = interpret(svc, text)
    assert status == 200 and len(svc.bedrock.calls) == 2
    [result] = svc.bedrock.calls[1]["messages"][2]["content"]
    assert result["toolResult"]["status"] == "success"
    assert result["toolResult"]["content"][0]["json"]["matches"][0]["issuer_id"] == "MICROSOFT"
    [drafted] = draft["proposed_rules"]
    assert drafted["parameters"] == {"issuer_scope": "MICROSOFT"} and drafted["threshold"] == 0.05 and drafted["threshold_quote"] == "5%"
    schema = svc.bedrock.calls[1]["toolConfig"]["tools"][0]["toolSpec"]["inputSchema"]["json"]
    assert "MICROSOFT" in schema["properties"]["rules"]["items"]["properties"]["issuer_id"]["enum"]


def test_ia11_a_lookup_for_words_the_investor_never_wrote_finds_nothing_and_gives_no_company():
    text = "At most 5% in one company."
    rule = {"words": "At most 5% in one company", "rule_type": "max_issuer_exposure", "issuer_id": "MICROSOFT"}
    svc = service(lookup(FIND_COMPANIES_TOOL_NAME, {"words": "Microsoft"}), answer(dict(EMPTY, rules=[rule])), answer(dict(EMPTY, rules=[rule])))
    status, _ = interpret(svc, text)
    assert status == 502, "MICROSOFT was never resolved from the investor's words"
    assert svc.bedrock.calls[1]["messages"][2]["content"][0]["toolResult"]["status"] == "error"


def test_ia12_describe_sector_returns_snapshot_names_only():
    svc = service(lookup(DESCRIBE_SECTOR_TOOL_NAME, {"sector": "Energy"}), answer(EMPTY))
    status, _ = interpret(svc, "Something about energy.")
    assert status == 200
    result = svc.bedrock.calls[1]["messages"][2]["content"][0]["toolResult"]["content"][0]["json"]
    assert result["sector"] == "Energy" and "Enbridge" in result["example_companies"]


# --------------------------------------------------------------------------- loop bounds


def test_ia13_lookups_are_bounded_and_an_unknown_tool_is_rejected():
    endless = [lookup(FIND_COMPANIES_TOOL_NAME, {"words": "Exxon"}, tool_use_id=f"t{n}") for n in range(6)]
    svc = service(*endless)
    status, body = interpret(svc, "Avoid Exxon.")
    assert (status, body["error"]["code"]) == (502, "INTERPRETER_FAILED")
    assert len(svc.bedrock.calls) <= 2 * 4, "two attempts, each at most max_lookup_rounds + 2 calls"
    told = [block for call in svc.bedrock.calls for message in call["messages"] for block in message["content"] if block.get("text") == itp.INTERPRETER_LOOKUP_DONE_NOTE]
    assert told, "the model is told to submit once lookups are used up"
    rogue = lookup("check_rules", {"words": "Exxon"})
    status, _ = interpret(service(rogue, rogue), "Avoid Exxon.")
    assert status == 502


def test_ia14_a_slow_lookup_round_that_leaves_no_time_is_504_and_prose_never_leaks():
    svc = service(tool_use_response(FIND_COMPANIES_TOOL_NAME, {"words": "Exxon"}, text=PROSE), answer(EMPTY))
    svc.bedrock.on_call = lambda n: svc.clock.advance(8)  # 12 s left after the lookup: less than one call may take
    status, body = interpret(svc, "Avoid Exxon.")
    assert (status, body["error"]["code"]) == (504, "INTERPRETER_TIMEOUT") and len(svc.bedrock.calls) == 1
    svc = service(tool_use_response(FIND_COMPANIES_TOOL_NAME, {"words": "Exxon"}, text=PROSE),
                  answer(dict(EMPTY, rules=[{"words": "Avoid Exxon", "rule_type": "exclusion", "issuer_ids": ["EXXON_MOBIL"]}])))
    status, draft = interpret(svc, "Avoid Exxon.")
    assert status == 200 and PROSE not in json.dumps(draft) and draft["proposed_rules"][0]["parameters"]["definition"]["issuer_ids"] == ["EXXON_MOBIL"]
