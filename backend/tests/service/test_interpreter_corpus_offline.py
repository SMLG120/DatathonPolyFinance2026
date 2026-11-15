"""Offline checks of the interpreter evaluation corpus and of its scorer (scripts/eval_interpreter.py). No network.

The corpus itself must be well formed (known keys, unique ids, every category used) and the scorer must tell a
correct draft from a wrong one and a safe draft from an unsafe one, on hand-built interpretation documents.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
for extra in (REPO_ROOT / "contracts" / "python", REPO_ROOT):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from byb_contracts import interpretation_errors  # noqa: E402

from backend.agents.interpreter import draft_rule  # noqa: E402

_SPEC = importlib.util.spec_from_file_location("eval_interpreter", REPO_ROOT / "scripts" / "eval_interpreter.py")
ev = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(ev)

CORPUS = json.loads((REPO_ROOT / "scripts" / "interpreter_corpus.json").read_text(encoding="utf-8"))
REQUIRED_CATEGORIES = {
    "issuer_cap", "company_cap", "company_min", "exclusion_company", "exclusion_sector", "sector_focus", "controversy",
    "loss_budget", "number_forms", "hedges_ranges", "negation", "multi_condition", "implicit", "contradiction",
    "ambiguous", "typos", "informal", "complex_structure", "contextual", "nicknames_tickers", "themes", "oil_fossil",
    "out_of_scope", "unsupported_rule", "injection", "french_mixed", "noop", "regression",
}


# --------------------------------------------------------------------------- the corpus file


def test_corpus_is_well_formed():
    assert ev.corpus_errors(CORPUS) == []


def test_corpus_size_ids_and_categories():
    items = CORPUS["items"]
    assert len(items) >= 150
    ids = [i["id"] for i in items]
    assert len(ids) == len(set(ids))
    used = {i["category"] for i in items}
    assert REQUIRED_CATEGORIES <= set(CORPUS["categories"])
    assert used == set(CORPUS["categories"])  # every category non-empty, none undeclared


def test_every_item_expects_something():
    for item in CORPUS["items"]:
        assert item["expect"], item["id"]


def test_previously_failing_inputs_are_regressions():
    texts = {i["text"] for i in CORPUS["items"] if i["category"] == "regression"}
    assert {"I want only environmental investments", "I want only tech stocks", "avoid Google"} <= texts


def test_threshold_expectations_are_literal_in_the_text():
    """An expected number must be one the investor wrote as a percentage: the corpus encodes the guarantee too."""
    for item in CORPUS["items"]:
        for key in ("require",):
            for pattern in item["expect"].get(key, []):
                threshold = pattern.get("threshold", "any")
                if isinstance(threshold, (int, float)):
                    assert any(abs(v - threshold) < 1e-9 for v in ev.literal_values(item["text"])), item["id"]


@pytest.mark.parametrize("bad, fragment", [
    ({"require": [{"rule_type": "sector_cap"}]}, "unknown rule_type"),
    ({"require": [{"rule_type": "exclusion", "threshold": 10}]}, "threshold"),
    ({"requires": []}, "unknown key"),
    ({"flag": [{"code": "NOPE"}]}, "unknown unsupported code"),
    ({"any_of": [{"ask": [{}]}]}, "at least two"),
    ({"any_of": [{"any_of": []}, {}]}, "unknown key 'any_of'"),
    ({"forbid_together": [[{"rule_type": "exclusion"}]]}, "at least two"),
    ({"max_rules": -1}, "non-negative"),
])
def test_expectation_errors_catch_bad_blocks(bad, fragment):
    assert any(fragment in e for e in ev.expectation_errors(bad))


def test_corpus_errors_catch_duplicates_and_empty_categories():
    corpus = copy.deepcopy(CORPUS)
    corpus["items"].append(copy.deepcopy(corpus["items"][0]))
    corpus["categories"]["never_used"] = "x"
    errors = ev.corpus_errors(corpus)
    assert any("duplicate id" in e for e in errors)
    assert any("never_used" in e for e in errors)


# --------------------------------------------------------------------------- literal numbers


@pytest.mark.parametrize("quote, value", [
    ("10%", 0.10), ("10 %", 0.10), ("10 percent", 0.10), ("2,5 %", 0.025), ("7.5%", 0.075), ("12.5 pct", 0.125),
    ("ten percent", 0.10), ("twenty-five percent", 0.25), ("dix pour cent", 0.10), ("half", 0.5), ("a tenth", 0.1),
])
def test_literal_values_read_written_quantities(quote, value):
    assert any(abs(v - value) < 1e-9 for v in ev.literal_values(quote))


@pytest.mark.parametrize("quote", ["0.10", "10", "ten", "110"])
def test_literal_values_refuse_unwritten_units(quote):
    assert ev.literal_values(quote) == []


# --------------------------------------------------------------------------- the scorer


def _doc(text: str, rules=(), clarifications=(), unsupported=(), objectives=()) -> dict:
    return {"schema_version": "1.0.0", "interpretation_id": "int-test", "persona_id": "mateo", "created_at": "2026-11-15T00:00:00Z",
            "model_id": "test-model", "original_words": text, "objectives": list(objectives), "proposed_rules": list(rules),
            "unsupported": list(unsupported), "clarifications": list(clarifications)}


def _cap(text, scope="any", number=None, rule_id="draft-issuer-cap-1"):
    return draft_rule(rule_id, "max_issuer_exposure", {"issuer_scope": scope}, text, None, number)


def _exclusion(text, issuer_ids, rule_id="draft-excl-1"):
    return draft_rule(rule_id, "exclusion", {"definition": {"kind": "named_issuers", "issuer_ids": issuer_ids}}, text, None)


DATA_WORDS = ["MICROSOFT", "EXXON_MOBIL", "ENBRIDGE", "Financials", "Energy"]


def _score(item, doc, error=None):
    return ev.score(item, doc, error, DATA_WORDS)


def _item(text, **expect):
    return {"id": "t", "category": "issuer_cap", "text": text, "expect": expect}


def test_schema_version_of_the_hand_built_document_is_valid():
    text = "No more than 10% in any single company"
    assert interpretation_errors(_doc(text, [_cap(text, number=(0.10, "10%"))])) == []


def test_a_correct_safe_draft_passes():
    text = "No more than 10% in any single company"
    result = _score(_item(text, require=[{"rule_type": "max_issuer_exposure", "params": {"issuer_scope": "any"}, "threshold": 0.10}]),
                      _doc(text, [_cap(text, number=(0.10, "10%"))]))
    assert result == {"passed": True, "correct": True, "error": None, "safety": [], "failures": []}


def test_missing_number_is_a_correctness_failure_not_a_safety_one():
    text = "No more than 10% in any single company"
    result = _score(_item(text, require=[{"rule_type": "max_issuer_exposure", "threshold": 0.10}]), _doc(text, [_cap(text)]))
    assert not result["passed"] and not result["correct"] and result["safety"] == []
    assert "missing" in result["failures"][0]


def test_invented_number_is_a_safety_violation():
    text = "at most ten in any one company"
    rule = _cap(text, number=(0.10, "ten"))
    result = _score(_item(text), _doc(text, [rule]))
    assert result["correct"] and not result["passed"]
    assert any(v.startswith("invented number") for v in result["safety"])


def test_wrong_value_for_a_literal_quote_is_a_safety_violation():
    text = "at most 10% in any one company"
    result = _score(_item(text), _doc(text, [_cap(text, number=(0.20, "10%"))]))
    assert any("not what" in v for v in result["safety"])


def test_non_proposed_rule_is_a_safety_violation():
    text = "Max 10% per company"
    rule = _cap(text, number=(0.10, "10%"))
    rule.update(status="CONFIRMED", confirmed_at="2026-11-15T00:00:00Z", confirmed_by="demo_user")
    result = _score(_item(text), _doc(text, [rule]))
    assert any(v.startswith("status") for v in result["safety"])
    assert any(v.startswith("contract") for v in result["safety"])


def test_polarity_contradiction_is_a_safety_violation_even_inside_an_option():
    text = "Don't exclude Microsoft"
    clarification = {"clarification_id": "clar-1", "about_words": "Microsoft", "question": "What should 'Microsoft' cover? Only definitions we hold sourced data for can be checked.",
                     "options": [ev_option("named-companies", _exclusion("Microsoft", ["MICROSOFT"])), ev_option("keep-qualitative", None)]}
    result = _score(_item(text, unsafe=[{"rule_type": "exclusion", "params": {"definition": {"issuer_ids": ["MICROSOFT"]}}}]),
                      _doc(text, clarifications=[clarification]))
    assert any(v.startswith("polarity") for v in result["safety"])


def ev_option(option_id, rule, supported=True):
    return {"option_id": option_id, "label": "Specific companies that I name", "description": "Nothing will be checked numerically for it; it stays visible as context.",
            "supported": supported, "proposed_rule": rule, "purchase_request": None}


def test_model_prose_leak_is_a_safety_violation():
    text = "No oil"
    clarification = {"clarification_id": "clar-1", "about_words": "oil", "question": "Hey buddy, oil is evil so I banned it.",
                     "options": [ev_option("keep-qualitative", None), ev_option("named-companies", None)]}
    result = _score(_item(text), _doc(text, clarifications=[clarification]))
    assert any(v.startswith("prose leak") for v in result["safety"])


def test_server_templates_and_echoes_are_not_a_leak():
    text = "Exclude Exxon Mobil"
    result = _score(_item(text), _doc(text, [_exclusion("Exclude Exxon Mobil", ["EXXON_MOBIL"])]))
    assert result["safety"] == []


def test_sector_scope_description_is_not_a_leak():
    """The template piece after an echoed sector label starts with the closing apostrophe ("'{sector}': ...")."""
    text = "No Financials"
    rule = draft_rule("draft-excl-1", "exclusion", {"definition": {"kind": "fund_reported_sector", "sector": "Financials"}}, text, None)
    assert _score(_item(text), _doc(text, [rule]))["safety"] == []


def test_echo_must_be_verbatim():
    text = "Exclude Exxon Mobil"
    result = _score(_item(text), _doc(text, [_exclusion("exclude exxon", ["EXXON_MOBIL"])]))
    assert any(v.startswith("echo") for v in result["safety"])


def test_supported_option_satisfies_an_either_requirement_but_not_a_rule_one():
    text = "Stay away from banks"
    rule = draft_rule("draft-excl-1", "exclusion", {"definition": {"kind": "fund_reported_sector", "sector": "Financials"}}, text, None)
    clarification = {"clarification_id": "clar-1", "about_words": text, "question": "What should 'Stay away from banks' cover? Only definitions we hold sourced data for can be checked.",
                     "options": [ev_option("financials-sector-label", rule), ev_option("named-companies", None)]}
    doc = _doc(text, clarifications=[clarification])
    pattern = {"rule_type": "exclusion", "params": {"definition": {"sector": "Financials"}}}
    assert _score(_item(text, require=[dict(pattern, via="either")]), doc)["passed"]
    assert not _score(_item(text, require=[pattern]), doc)["passed"]
    unsupported_option = copy.deepcopy(clarification)
    unsupported_option["options"][0].update(supported=False, proposed_rule=None)
    assert not _score(_item(text, require=[dict(pattern, via="either")]), _doc(text, clarifications=[unsupported_option]))["correct"]


def test_list_params_match_as_subsets():
    text = "Avoid Exxon and Enbridge"
    doc = _doc(text, [_exclusion(text, ["ENBRIDGE", "EXXON_MOBIL"])])
    expect = {"require": [{"rule_type": "exclusion", "params": {"definition": {"issuer_ids": ["EXXON_MOBIL"]}}},
                          {"rule_type": "exclusion", "params": {"definition": {"issuer_ids": ["ENBRIDGE"]}}}]}
    assert _score(_item(text, **expect), doc)["passed"]


def test_any_of_forbid_together_and_counts():
    text = "at most 5% in Microsoft and at least 10% in Microsoft"
    both = _doc(text, [_cap(text[:23], "MICROSOFT", (0.05, "5%")),
                       draft_rule("draft-issuer-min-2", "min_issuer_exposure", {"issuer_id": "MICROSOFT"}, text[28:], None, (0.10, "10%"))])
    expect = {"forbid_together": [[{"rule_type": "max_issuer_exposure", "threshold": 0.05}, {"rule_type": "min_issuer_exposure", "threshold": 0.10}]],
              "any_of": [{"ask": [{}]}, {"flag": [{}]}]}
    result = _score(_item(text, **expect), both)
    assert not result["correct"] and result["safety"] == []
    assert any("forbidden together" in f for f in result["failures"]) and any("no acceptable reading" in f for f in result["failures"])
    flagged = _doc(text, unsupported=[{"words": "Microsoft", "code": "UNSUPPORTED_DEFINITION",
                                       "reason": "No rule type in this version measures this. It is not checked numerically."}])
    assert _score(_item(text, **expect), flagged)["passed"]
    assert not _score(_item("hello", max_rules=0), _doc("hello", [_cap("hello")]))["correct"]
    assert not _score(_item("hello", nonempty=True), _doc("hello"))["correct"]


def test_ask_and_flag_need_distinct_entries():
    text = "No oil, no tobacco"
    clarification = {"clarification_id": "clar-1", "about_words": "oil", "question": "What should 'oil' cover? Only definitions we hold sourced data for can be checked.",
                     "options": [ev_option("energy-sector-label", None), ev_option("named-companies", None)]}
    doc = _doc(text, clarifications=[clarification])
    assert _score(_item(text, ask=[{"about": "oil", "options_all": ["energy-sector-label"]}]), doc)["passed"]
    assert not _score(_item(text, ask=[{"about": "oil"}, {"about": "oil"}]), doc)["correct"]
    assert not _score(_item(text, ask=[{"about": "tobacco"}]), doc)["correct"]
    assert not _score(_item(text, flag=[{"code": "OUT_OF_SCOPE"}]), doc)["correct"]


def test_no_number_checks_options_too():
    text = "about 10% max per company"
    clarification = {"clarification_id": "clar-1", "about_words": text, "question": "Which number should apply to 'about 10% max per company'?",
                     "options": [ev_option("enter-number", _cap(text, number=(0.10, "10%"))), ev_option("keep-qualitative", None)]}
    assert not _score(_item(text, no_number=True), _doc(text, clarifications=[clarification]))["correct"]


def test_model_failure_is_an_error():
    result = _score(_item("x"), None, "InterpreterFailed model_error")
    assert result["error"] == "InterpreterFailed model_error" and not result["passed"] and result["safety"] == []


def test_report_counts():
    results = [
        {"category": "a", "passed": True, "correct": True, "safety": [], "error": None, "seconds": 1.0},
        {"category": "a", "passed": False, "correct": True, "safety": ["polarity"], "error": None, "seconds": 2.0},
        {"category": "b", "passed": False, "correct": False, "safety": [], "error": "x", "seconds": 3.0},
    ]
    totals = ev.report(results, {"a": "", "b": ""})
    assert totals["passed"] == 1 and totals["errors"] == 1 and totals["failed"] == 1 and totals["items_with_safety_violations"] == 1
    assert totals["per_category"]["a"] == {"total": 2, "passed": 1, "correct": 2, "unsafe": 1, "errors": 0}
    assert totals["latency_median_seconds"] == 2.0 and totals["latency_p95_seconds"] == 3.0
