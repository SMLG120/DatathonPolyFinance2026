"""The reading: tool schema, span resolution and parse_reading's shape checks and per-clause degradation. No network."""

from __future__ import annotations

import json

import pytest

from backend.agents import reading as rd
from backend.agents.prompts import DESCRIBE_SECTOR_TOOL_NAME, FIND_COMPANIES_TOOL_NAME, INTERPRETER_TOOL_NAME

SECTORS = ["Energy", "Financials"]
IDS = ["ENBRIDGE", "MICROSOFT"]


def clause(id="c1", evidence="Max 10% per company", intent="LIMIT", subject_kind="EACH_COMPANY", direction="AT_MOST", **extra):
    return {"id": id, "evidence": evidence, "intent": intent, "polarity": "ASSERTED", "subject_kind": subject_kind,
            "direction": direction, "confidence": "HIGH", **extra}


def raw(*clauses, **lists):
    return {"objectives": lists.get("objectives", []), "clauses": list(clauses), "conflicts": lists.get("conflicts", []),
            "non_quantity": lists.get("non_quantity", [])}


def _members(schema):
    """Every property name at every level of a JSON schema, with its schema."""
    if isinstance(schema, dict):
        for name, sub in (schema.get("properties") or {}).items():
            yield name, sub
            yield from _members(sub)
        if "items" in schema:
            yield from _members(schema["items"])


# --------------------------------------------------------------------------- schema and tools


def test_schema_has_no_number_or_prose_member_and_is_closed_everywhere():
    names = {name for name, _ in _members(rd.READING_SCHEMA)}
    assert not {"threshold", "status", "origin", "rule_id", "question", "reason", "label"} & names
    numeric = {name for name, sub in _members(rd.READING_SCHEMA) if "integer" in str(sub.get("type")) or "number" in str(sub.get("type"))}
    assert numeric == {"objective"}, "the objective index is the only integer; there is no numeric amount anywhere"

    def closed(schema):
        if isinstance(schema, dict):
            if schema.get("type") == "object":
                assert schema.get("additionalProperties") is False
            for sub in (schema.get("properties") or {}).values():
                closed(sub)
            closed(schema.get("items"))
    closed(rd.READING_SCHEMA)


def test_schema_matches_the_ir_spec():
    props = rd.READING_SCHEMA["properties"]
    assert rd.READING_SCHEMA["required"] == ["objectives", "clauses", "conflicts", "non_quantity"]
    items = props["clauses"]["items"]
    assert items["required"] == ["id", "evidence", "intent", "polarity", "subject_kind", "direction", "confidence"]
    assert props["clauses"]["maxItems"] == 12 and props["objectives"]["maxItems"] == 8
    assert props["conflicts"]["maxItems"] == 6 and props["non_quantity"]["maxItems"] == 8
    clause_props = items["properties"]
    assert clause_props["company_ids"]["maxItems"] == 8 and clause_props["sectors"]["maxItems"] == 14
    assert clause_props["intent"]["enum"] == list(rd.INTENTS) and clause_props["direction"]["enum"] == list(rd.DIRECTIONS)
    assert clause_props["ambiguity"]["uniqueItems"] is True
    assert set(clause_props) == set(rd.SUB_SPANS) | set(rd.CLAUSE_REFS) | set(items["required"]) | {
        "company_ids", "sectors", "activity", "theme", "natures", "distribution", "objective", "unsupported_reason", "ambiguity"}


def test_reading_schema_fills_the_enums_and_leaves_the_template_alone():
    schema = rd.reading_schema(SECTORS, IDS)
    clause_props = schema["properties"]["clauses"]["items"]["properties"]
    assert clause_props["company_ids"]["items"] == {"type": "string", "enum": IDS}
    assert clause_props["sectors"]["items"] == {"type": "string", "enum": SECTORS}
    assert rd.READING_SCHEMA["properties"]["clauses"]["items"]["properties"]["company_ids"]["items"] == {"type": "string"}


def test_more_ids_than_the_enum_limit_give_a_plain_string():
    ids = [f"ID_{n}" for n in range(rd.MAX_ENUM_COMPANIES + 1)]
    clause_props = rd.reading_schema(SECTORS, ids)["properties"]["clauses"]["items"]["properties"]
    assert clause_props["company_ids"]["items"] == {"type": "string"}
    assert rd.reading_schema(SECTORS, [])["properties"]["clauses"]["items"]["properties"]["company_ids"]["items"] == {"type": "string"}


def test_tool_config_has_the_three_tools_and_is_deterministic():
    config = rd.tool_config(SECTORS, IDS)
    assert [t["toolSpec"]["name"] for t in config["tools"]] == [INTERPRETER_TOOL_NAME, FIND_COMPANIES_TOOL_NAME, DESCRIBE_SECTOR_TOOL_NAME]
    assert config["tools"][1]["toolSpec"]["inputSchema"]["json"] == rd.FIND_COMPANIES_SCHEMA
    assert config["tools"][2]["toolSpec"]["inputSchema"]["json"]["properties"]["sector"]["enum"] == SECTORS
    assert json.dumps(config, sort_keys=True) == json.dumps(rd.tool_config(SECTORS, IDS), sort_keys=True)


# --------------------------------------------------------------------------- spans


@pytest.mark.parametrize("text, value, expected", [
    ("Max 10% per company", "10%", ("10%", 4, 7)),
    ("Max 10% per company", "  max 10%   per COMPANY ", ("Max 10% per company", 0, 19)),
    ("I don’t want Exxon", "I don't want Exxon", ("I don’t want Exxon", 0, 18)),
    ("Say “no” to oil", 'Say "no" to oil', ("Say “no” to oil", 0, 15)),
    ("Évitez Énbridge", "Évitez Énbridge", ("Évitez Énbridge", 0, 15)),
])
def test_resolve_span_returns_the_original_characters(text, value, expected):
    assert rd.resolve_span(text, value) == expected


@pytest.mark.parametrize("value", [None, "", "   ", 10, "Max 10% per firm", "Max 10 % per company"])
def test_resolve_span_refuses_what_is_not_the_text(value):
    assert rd.resolve_span("Max 10% per company", value) is None


def test_resolve_span_prefers_the_evidence_and_skips_taken_occurrences():
    text = "Max 10% in Exxon. Max 10% per company."
    assert rd.resolve_span(text, "10%", within=(18, 38)) == ("10%", 22, 25)
    assert rd.resolve_span(text, "10%") == ("10%", 4, 7)
    assert rd.resolve_span(text, "Max 10%", taken={(0, 7)}) == ("Max 10%", 18, 25)
    assert rd.resolve_span(text, "Max 10%", taken={(0, 7), (18, 25)}) == ("Max 10%", 0, 7), "all taken: the first"


# --------------------------------------------------------------------------- parse_reading


def test_a_clean_reading_is_pinned_to_offsets():
    text = "Over 5 years, max 10% per company."
    reading = rd.parse_reading(raw(clause(evidence="max 10% per company", quantity_mention="10%", direction_mention="max",
                                          scope_mention="per company", ambiguity=[], objective=0),
                                   objectives=[{"words": "Over 5 years", "kind": "goal"}],
                                   non_quantity=[{"mention": "5 years", "kind": "HORIZON"}]), text)
    [c] = reading.clauses
    assert c.evidence == ("max 10% per company", 14, 33) and c.quantity_mention == ("10%", 18, 21)
    assert c.direction_mention == ("max", 14, 17) and c.scope_mention == ("per company", 22, 33)
    assert c.problems == [] and c.objective == 0 and c.distribution == "UNSPECIFIED"
    assert reading.objectives == [rd.Objective(("Over 5 years", 0, 12), "goal")]
    assert reading.non_quantity == [rd.NonQuantity(("5 years", 5, 12), "HORIZON")] and reading.dropped == []


@pytest.mark.parametrize("answer, reason", [
    ([], "reading_not_an_object"),
    ({"clauses": [], "objectives": [], "conflicts": [], "non_quantity": [], "rules": []}, "reading_unknown_member"),
    ({"objectives": [], "conflicts": [], "non_quantity": []}, "clauses_missing"),
    ({"clauses": "c1"}, "clauses_not_a_list"),
    ({"clauses": ["c1"]}, "clauses_item_not_an_object"),
    (raw({k: v for k, v in clause().items() if k != "confidence"}), "clause_confidence_missing"),
    (raw(clause(intent="CAP")), "clause_intent_unknown"),
    (raw(clause(direction="BELOW")), "clause_direction_unknown"),
    (raw(dict(clause(), evidence=["Max"])), "clause_evidence_not_a_string"),
    (raw(clause(), objectives=[{"words": "Max", "kind": "wish"}]), "objective_kind_unknown"),
    (raw(clause(), conflicts=[{"a": "c1", "b": "c1", "kind": "CLASH"}]), "conflict_kind_unknown"),
    (raw(clause(), non_quantity=[{"mention": "10", "kind": "PRICE"}]), "non_quantity_kind_unknown"),
])
def test_shape_errors_reject_the_whole_answer(answer, reason):
    with pytest.raises(rd._Rejected) as caught:
        rd.parse_reading(answer, "Max 10% per company")
    assert caught.value.reason == reason


@pytest.mark.parametrize("extra, problem", [
    ({"quantity_mention": "25%"}, "quantity_mention_not_in_text"),
    ({"subject_mention": "Exxon"}, "subject_mention_outside_evidence"),
    ({"activity": "COAL"}, "activity_unknown"),
    ({"natures": ["RUMOUR"]}, "natures_invalid"),
    ({"company_ids": "MICROSOFT"}, "company_ids_invalid"),
    ({"distribution": "SOME"}, "distribution_unknown"),
    ({"supersedes": "c1"}, "supersedes_invalid"),
    ({"quantity_from": "x9"}, "quantity_from_invalid"),
    ({"objective": -1}, "objective_invalid"),
    ({"threshold": 0.1}, "unknown_member_threshold"),
    ({"id": "clause-1"}, "id_invalid"),
])
def test_a_bad_member_degrades_its_clause_only(extra, problem):
    text = "Max 10% per company. Avoid Exxon."
    good = clause(id="c2", evidence="Avoid Exxon", intent="EXCLUDE", subject_kind="NAMED_COMPANIES", direction="NONE_AT_ALL")
    reading = rd.parse_reading(raw({**clause(), **extra}, good), text)
    bad, ok = reading.clauses
    assert problem in bad.problems and bad.evidence == ("Max 10% per company", 0, 19)
    assert ok.problems == []


def test_a_clause_whose_evidence_is_not_in_the_text_is_dropped_and_counted():
    text = "Max 10% per company. Avoid Exxon."
    reading = rd.parse_reading(raw(clause(), clause(id="c2", evidence="Avoid Enbridge")), text)
    assert [c.id for c in reading.clauses] == ["c1"] and reading.dropped == ["clause_evidence_not_in_text"]


def test_more_than_half_of_the_clauses_failing_rejects_but_half_does_not():
    text = "Max 10% per company. Avoid Exxon."
    one_bad = raw(clause(quantity_mention="25%"), clause(id="c2", evidence="Avoid Exxon"))
    assert len(rd.parse_reading(one_bad, text).clauses) == 2
    with pytest.raises(rd._Rejected) as caught:
        rd.parse_reading(raw(clause(quantity_mention="25%"), clause(id="c2", evidence="Avoid Enbridge"), clause(id="c3", evidence="Avoid Exxon")), text)
    assert caught.value.reason == "most_clauses_unusable"
    assert rd.parse_reading(raw(), text).clauses == [], "an empty reading is an answer (nothing to draft)"


def test_duplicate_ids_and_duplicate_evidence():
    text = "Max 10% here. Max 10% there."
    reading = rd.parse_reading(raw(clause(evidence="Max 10%"), clause(evidence="Max 10%")), text)
    first, second = reading.clauses
    assert (first.start, second.start) == (0, 14), "the same words twice point at two places"
    assert second.problems == ["id_duplicate"]


def test_conflicts_must_name_two_usable_clauses_and_lists_are_capped():
    text = "Max 10% per company. Avoid Exxon."
    reading = rd.parse_reading(raw(clause(), clause(id="c2", evidence="Avoid Exxon"),
                                   conflicts=[{"a": "c1", "b": "c2", "kind": "TENSION"}, {"a": "c1", "b": "c9", "kind": "CORRECTION"}],
                                   objectives=[{"words": "Avoid Exxon", "kind": "constraint"}] * 9), text)
    assert reading.conflicts == [rd.Conflict("c1", "c2", "TENSION")] and reading.dropped == ["conflict_reference_unknown"]
    assert len(reading.objectives) == rd.MAX_OBJECTIVES


def test_optional_members_may_be_null_and_lists_dedup():
    text = "Avoid Exxon and Enbridge"
    reading = rd.parse_reading(raw(clause(evidence=text, intent="EXCLUDE", subject_kind="NAMED_COMPANIES", direction="NONE_AT_ALL",
                                          company_ids=["ENBRIDGE", "ENBRIDGE", "EXXON_MOBIL"], activity=None, theme=None,
                                          quantity_mention=None, ambiguity=None, natures=None)), text)
    [c] = reading.clauses
    assert c.problems == [] and c.company_ids == ["ENBRIDGE", "EXXON_MOBIL"] and c.ambiguity == []
