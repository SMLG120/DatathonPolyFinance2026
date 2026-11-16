"""Builders for scripted ``submit_reading`` answers (the IR of backend/agents/reading.py), shared by the route tests.

A fake model answer is a *reading*: clauses that mark spans of the investor's text and pick closed codes. These
builders keep each test's reading short and in the schema's shape; every member they write is a real schema member,
so an answer they build is exactly what a well-behaved model could send.
"""

from __future__ import annotations

from typing import Any

from backend.agents.prompts import INTERPRETER_TOOL_NAME
from service_fakes import tool_use_response


def clause(id: str, evidence: str, intent: str, subject_kind: str, direction: str, **members: Any) -> dict[str, Any]:
    """One clause, read with HIGH confidence and ASSERTED unless ``members`` override it."""
    return {"id": id, "evidence": evidence, "intent": intent, "polarity": "ASSERTED", "subject_kind": subject_kind,
            "direction": direction, "confidence": "HIGH", **members}


def objective(words: str, kind: str) -> dict[str, str]:
    return {"words": words, "kind": kind}


def reading(*clauses: dict[str, Any], objectives=(), conflicts=(), non_quantity=()) -> dict[str, Any]:
    """A whole ``submit_reading`` input."""
    return {"objectives": list(objectives), "clauses": list(clauses), "conflicts": list(conflicts), "non_quantity": list(non_quantity)}


def answer(document: dict[str, Any], **options: Any) -> dict[str, Any]:
    """The Converse response of a model that submits ``document`` with the submit_reading tool."""
    return tool_use_response(INTERPRETER_TOOL_NAME, document, **options)


EMPTY = reading()

# --------------------------------------------------------------------------- common clauses


def cap_each(id: str, evidence: str, quantity: str | None, direction_mention: str | None = None, **members: Any) -> dict[str, Any]:
    """'No more than 10% in any one company': a cap on every company."""
    return clause(id, evidence, "LIMIT", "EACH_COMPANY", "AT_MOST", quantity_mention=quantity, direction_mention=direction_mention, **members)


def company(id: str, evidence: str, intent: str, direction: str, subject: str, ids: list[str], **members: Any) -> dict[str, Any]:
    """A clause about companies the investor named (``subject`` is their words, ``ids`` the model's snapshot ids)."""
    return clause(id, evidence, intent, "NAMED_COMPANIES", direction, subject_mention=subject, company_ids=ids, **members)


def oil(id: str, evidence: str = "avoid oil", subject: str = "oil", **members: Any) -> dict[str, Any]:
    """'avoid oil': an activity exclusion, which the server's catalog question always answers."""
    return clause(id, evidence, "EXCLUDE", "ACTIVITY", "NONE_AT_ALL", subject_mention=subject, activity="OIL", **members)


def controversies(id: str, evidence: str, **members: Any) -> dict[str, Any]:
    return clause(id, evidence, "EXCLUDE", "CONTROVERSY", "NONE_AT_ALL", **members)


# --------------------------------------------------------------------------- the personas' sentences

# "Balanced growth over 8 to 12 years; ESG matters to me; I want to avoid oil and companies involved in significant
# controversies." The horizon is an objective only: a GOAL clause on it would add an unsupported entry the contract
# fixture does not have.
MATEO_READING = reading(
    oil("c1", objective=2),
    controversies("c2", "companies involved in significant controversies", objective=2),
    objectives=[objective("Balanced growth over 8 to 12 years", "goal"), objective("ESG matters to me", "preference"),
                objective("I want to avoid oil and companies involved in significant controversies", "constraint")],
)

# "... maximum growth ... strict diversification ...": a diversification wish (asked) and a return goal (unsupported).
AMIRA_READING = reading(
    clause("c1", "strict diversification", "PREFERENCE", "EACH_COMPANY", "UNSPECIFIED", objective=1),
    clause("c2", "maximum growth", "GOAL", "WHOLE_PORTFOLIO", "UNSPECIFIED", unsupported_reason="GROWTH_OR_RETURN", objective=0),
    objectives=[objective("maximum growth", "goal"), objective("strict diversification", "preference")],
)
