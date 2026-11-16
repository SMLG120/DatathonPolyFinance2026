"""The model's answer as a *reading* of the investor's text, and the tool schema it is written in (standard library only).

The model does not draft rules. It splits the text into clauses and labels each one with closed codes (intent,
polarity, subject kind, direction, confidence, ambiguity) and with spans: exact copies of the investor's characters
that point at the evidence, the subject, the direction words, the amount, the scope, the date. The deterministic
compiler (``backend.agents.compiler``) turns a reading into an interpretation and may only *lower* what a clause
becomes; this module only checks the reading's shape and pins every span to offsets of the request text.

Frozen interface (WP3 writes the prompt against it; change it only together with WP3 and WP5)
------------------------------------------------------------------------------------------
``READING_SCHEMA``
    The ``submit_reading`` input schema with plain-string company ids and sector labels. ``reading_schema(sectors,
    ids)`` is the same schema with those two lists as enums. It has no numeric member except the ``objective``
    index, and no member named threshold, status, origin, rule_id, question, reason or label.

``tool_config(sectors, ids) -> dict``
    The three tools of one request (``submit_reading``, ``find_companies``, ``describe_sector``). Build it ONCE per
    request and pass the same object on every call, retry included: Bedrock checks a reasoning block's signature
    against the tools it was created with. ``ids`` become an enum when there are 1 to ``MAX_ENUM_COMPANIES``.

``parse_reading(raw: dict, text: str) -> Reading``
    Raises ``_Rejected`` for a shape error (not an object, ``clauses`` missing, an unknown top-level member, a missing
    required clause member or an unknown code in one) and when more than half of a non-empty clause list fails.
    Anything else is degraded per clause: a clause with a span that is not in the text, or a sub-span outside its
    evidence, keeps its evidence and lists ``problems`` (the compiler reports it as not measurable); a clause whose
    evidence is not in the text is dropped and counted in ``Reading.dropped``.

``resolve_span(text, value, within=None, taken=()) -> Span | None``
    Where ``value`` is in ``text``, as ``(original characters, start, end)``.

``Span = tuple[str, int, int]``; ``Clause``, ``Objective``, ``Conflict``, ``NonQuantity``, ``Reading``: dataclasses
below. The code lists (``INTENTS`` ... ``AMBIGUITY_CODES``) are the schema's enums.
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from typing import Any, Collection

from byb_contracts.constants import CONTROVERSY_NATURES, OBJECTIVE_KINDS

from backend.agents.prompts import DESCRIBE_SECTOR_TOOL_NAME, FIND_COMPANIES_TOOL_NAME, INTERPRETER_TOOL_NAME
from backend.agents.render import UNSUPPORTED_REASONS
from backend.agents.themes import THEME_CODES

# --------------------------------------------------------------------------- codes

INTENTS = ("LIMIT", "EXCLUDE", "KEEP_ONLY", "HOLD", "CAUTION", "PERMISSION", "PREFERENCE", "GOAL", "OUT_OF_SCOPE_ASK",
           "INSTRUCTION_TO_SYSTEM", "OTHER")
POLARITY_CODES = ("ASSERTED", "NEGATED")
SUBJECT_KINDS = ("EACH_COMPANY", "NAMED_COMPANIES", "SECTOR", "CONTROVERSY", "ACTIVITY", "THEME", "PORTFOLIO_LOSS",
                 "WHOLE_PORTFOLIO", "UNCLEAR")
ACTIVITIES = ("OIL", "FOSSIL", "TOBACCO", "WEAPONS", "GAMBLING", "ALCOHOL", "OTHER_ACTIVITY")
DIRECTIONS = ("AT_MOST", "AT_LEAST", "NONE_AT_ALL", "BETWEEN", "EXACTLY", "UNSPECIFIED")
DISTRIBUTIONS = ("EACH", "TOTAL", "UNSPECIFIED")
CONFIDENCES = ("HIGH", "MEDIUM", "LOW")
AMBIGUITY_CODES = ("VAGUE_SCOPE", "HEDGED", "UNIT_UNCLEAR", "NUMBER_LOOKS_MISTYPED", "SEVERAL_READINGS", "UNKNOWN_COMPANY",
                   "UNKNOWN_SECTOR", "DIRECTION_UNCLEAR", "SCOPE_UNCLEAR")
CONFLICT_KINDS = ("DIRECT_CONTRADICTION", "INFEASIBLE_TOGETHER", "CORRECTION", "TENSION")
NON_QUANTITY_KINDS = ("HORIZON", "YEAR", "COUNT", "NAME_PART", "OTHER")

MAX_OBJECTIVES = 8
MAX_CLAUSES = 12
MAX_CONFLICTS = 6
MAX_NON_QUANTITY = 8
MAX_CLAUSE_COMPANIES = 8
MAX_CLAUSE_SECTORS = 14
# Up to this many snapshot ids the schema lists them as an enum; a larger universe gets a plain string (the enum would
# bloat every call). Either way the compiler grounds every id on the investor's words.
MAX_ENUM_COMPANIES = 400

_CLAUSE_ID = r"^c([1-9]|1[0-2])$"
_CLAUSE_ID_RE = re.compile(_CLAUSE_ID)

# Clause members that are spans, in the order they are resolved (all must lie inside the evidence).
SUB_SPANS = ("subject_mention", "unresolved_company", "direction_mention", "quantity_mention", "scope_mention",
             "exclusivity_mention", "date_mention")
CLAUSE_REFS = ("quantity_from", "exception_of", "supersedes")
_REQUIRED = {"id": None, "evidence": None, "intent": INTENTS, "polarity": POLARITY_CODES, "subject_kind": SUBJECT_KINDS,
             "direction": DIRECTIONS, "confidence": CONFIDENCES}
_OPTIONAL_CODES = {"activity": ACTIVITIES, "theme": THEME_CODES, "unsupported_reason": tuple(UNSUPPORTED_REASONS)}

# --------------------------------------------------------------------------- the tool schema

# Members carry no descriptions: the system prompt defines every member and code once, and repeating it here only
# made every call longer (validation is the same: types, enums, patterns and closed objects).
_SPAN = {"type": "string"}
_OPTIONAL_SPAN = {"type": ["string", "null"]}
_CLAUSE_REF = {"type": ["string", "null"], "pattern": _CLAUSE_ID}


def _enum(values: Collection[str], nullable: bool = False) -> dict[str, Any]:
    if nullable:
        return {"type": ["string", "null"], "enum": [*values, None]}
    return {"type": "string", "enum": list(values)}


def _closed(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {"type": "object", "required": required, "additionalProperties": False, "properties": properties}


READING_SCHEMA: dict[str, Any] = _closed({
    "objectives": {"type": "array", "maxItems": MAX_OBJECTIVES, "items": _closed(
        {"words": _SPAN, "kind": _enum(OBJECTIVE_KINDS)}, ["words", "kind"])},
    "clauses": {"type": "array", "maxItems": MAX_CLAUSES, "items": _closed({
        "id": {"type": "string", "pattern": _CLAUSE_ID},
        "evidence": _SPAN,
        "intent": _enum(INTENTS),
        "polarity": _enum(POLARITY_CODES),
        "subject_kind": _enum(SUBJECT_KINDS),
        "subject_mention": _OPTIONAL_SPAN,
        "company_ids": {"type": "array", "maxItems": MAX_CLAUSE_COMPANIES, "items": {"type": "string"}},
        "unresolved_company": _OPTIONAL_SPAN,
        "sectors": {"type": "array", "maxItems": MAX_CLAUSE_SECTORS, "items": {"type": "string"}},
        "activity": _enum(ACTIVITIES, nullable=True),
        "theme": _enum(THEME_CODES, nullable=True),
        "natures": {"type": "array", "items": _enum(CONTROVERSY_NATURES)},
        "direction": _enum(DIRECTIONS),
        "direction_mention": _OPTIONAL_SPAN,
        "quantity_mention": _OPTIONAL_SPAN,
        "quantity_from": _CLAUSE_REF,
        "distribution": _enum(DISTRIBUTIONS),
        "scope_mention": _OPTIONAL_SPAN,
        "exclusivity_mention": _OPTIONAL_SPAN,
        "date_mention": _OPTIONAL_SPAN,
        "exception_of": _CLAUSE_REF,
        "supersedes": _CLAUSE_REF,
        "objective": {"type": ["integer", "null"]},
        "unsupported_reason": _enum(UNSUPPORTED_REASONS, nullable=True),
        "confidence": _enum(CONFIDENCES),
        "ambiguity": {"type": "array", "uniqueItems": True, "items": _enum(AMBIGUITY_CODES)},
    }, list(_REQUIRED))},
    "conflicts": {"type": "array", "maxItems": MAX_CONFLICTS, "items": _closed(
        {"a": {"type": "string", "pattern": _CLAUSE_ID}, "b": {"type": "string", "pattern": _CLAUSE_ID}, "kind": _enum(CONFLICT_KINDS)},
        ["a", "b", "kind"])},
    "non_quantity": {"type": "array", "maxItems": MAX_NON_QUANTITY, "items": _closed(
        {"mention": _SPAN,
         "kind": _enum(NON_QUANTITY_KINDS)}, ["mention", "kind"])},
}, ["objectives", "clauses", "conflicts", "non_quantity"])

FIND_COMPANIES_SCHEMA = _closed({"words": {"type": "string", "minLength": 2, "maxLength": 80,
                                           "description": "The company as the investor wrote it, copied from their text."}}, ["words"])


def reading_schema(sectors: list[str], ids: list[str]) -> dict[str, Any]:
    """``READING_SCHEMA`` with the snapshot's sector labels and (up to ``MAX_ENUM_COMPANIES``) issuer ids as enums."""
    schema = copy.deepcopy(READING_SCHEMA)
    clause = schema["properties"]["clauses"]["items"]["properties"]
    if ids and len(ids) <= MAX_ENUM_COMPANIES:
        clause["company_ids"]["items"] = _enum(ids)
    if sectors:
        clause["sectors"]["items"] = _enum(sectors)
    return schema


def tool_config(sectors: list[str], ids: list[str]) -> dict[str, Any]:
    """The three tools of one request. Build once per request (see the module docstring)."""
    return {"tools": [
        {"toolSpec": {
            "name": INTERPRETER_TOOL_NAME,
            "description": "Submit your reading of the investor's text. Codes and exact copies of their characters only: "
                           "nothing written here is shown to anyone.",
            "inputSchema": {"json": reading_schema(sectors, ids)},
        }},
        {"toolSpec": {
            "name": FIND_COMPANIES_TOOL_NAME,
            "description": "Look up which companies in the data snapshot the investor's words refer to (common names, misspellings, "
                           "partial names). Use it only for a company the investor wrote that is not in reference_data.companies.",
            "inputSchema": {"json": FIND_COMPANIES_SCHEMA},
        }},
        {"toolSpec": {
            "name": DESCRIBE_SECTOR_TOOL_NAME,
            "description": "List example companies the data labels with one sector, to check which sector label the investor's words mean.",
            "inputSchema": {"json": _closed({"sector": _enum(sectors) if sectors else {"type": "string"}}, ["sector"])},
        }},
    ]}


# --------------------------------------------------------------------------- the parsed form

Span = tuple[str, int, int]  # (the investor's characters, start, end) in the request text


@dataclass(frozen=True)
class Objective:
    words: Span
    kind: str


@dataclass
class Clause:
    """One wish. Span members are resolved against the request text; ``problems`` lists why the clause cannot be used
    (empty for a usable clause). A clause with problems is only ever reported as not measurable on its evidence."""

    id: str
    evidence: Span
    intent: str
    polarity: str
    subject_kind: str
    direction: str
    confidence: str
    subject_mention: Span | None = None
    company_ids: list[str] = field(default_factory=list)
    unresolved_company: Span | None = None
    sectors: list[str] = field(default_factory=list)
    activity: str | None = None
    theme: str | None = None
    natures: list[str] = field(default_factory=list)
    direction_mention: Span | None = None
    quantity_mention: Span | None = None
    quantity_from: str | None = None
    distribution: str = "UNSPECIFIED"
    scope_mention: Span | None = None
    exclusivity_mention: Span | None = None
    date_mention: Span | None = None
    exception_of: str | None = None
    supersedes: str | None = None
    objective: int | None = None
    unsupported_reason: str | None = None
    ambiguity: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)

    @property
    def start(self) -> int:
        return self.evidence[1]

    @property
    def end(self) -> int:
        return self.evidence[2]


@dataclass(frozen=True)
class Conflict:
    a: str
    b: str
    kind: str


@dataclass(frozen=True)
class NonQuantity:
    mention: Span
    kind: str


@dataclass
class Reading:
    objectives: list[Objective]
    clauses: list[Clause]
    conflicts: list[Conflict]
    non_quantity: list[NonQuantity]
    dropped: list[str] = field(default_factory=list)  # reason codes of items left out entirely (for the log, never shown)


class _Rejected(Exception):
    """The model's answer is unusable. ``reason`` is a fixed server code, never model text."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


# --------------------------------------------------------------------------- spans

_QUOTE_CLASSES = {"'": "['‘’`´]", "‘": "['‘’`´]", "’": "['‘’`´]", "`": "['‘’`´]", "´": "['‘’`´]",
                  '"': '["“”«»]', "“": '["“”«»]', "”": '["“”«»]', "«": '["“”«»]', "»": '["“”«»]'}


def _tolerant_pattern(value: str) -> re.Pattern[str]:
    """Matches ``value`` up to curly vs straight quotes, runs of whitespace and case. Nothing else is forgiven: a
    translated, corrected or paraphrased span is not the investor's text."""
    parts = []
    for token in value.split():
        parts.append("".join(_QUOTE_CLASSES.get(char) or re.escape(char) for char in token))
    return re.compile(r"\s+".join(parts), re.IGNORECASE)


def _occurrences(text: str, value: str, lo: int, hi: int) -> list[tuple[int, int]]:
    found = []
    start = text.find(value, lo, hi)
    while start >= 0:
        found.append((start, start + len(value)))
        start = text.find(value, start + 1, hi)
    if found:
        return found
    pattern = _tolerant_pattern(value)
    return [m.span() for m in pattern.finditer(text, lo, hi) if m.end() > m.start()]


def resolve_span(text: str, value: Any, within: tuple[int, int] | None = None,
                 taken: Collection[tuple[int, int]] = ()) -> Span | None:
    """Where ``value`` occurs in ``text``: exact match first, then the tolerant match. The result always holds the
    ORIGINAL characters and their offsets, so what is echoed is the investor's text, never the model's string.

    With ``within`` (the clause's evidence) an occurrence inside it is preferred; otherwise the first occurrence that
    is not already ``taken`` by another clause wins, so two clauses quoting the same words point at different places.
    """
    if not isinstance(value, str) or not value.strip():
        return None
    wanted = value.strip()
    candidates: list[tuple[int, int]] = []
    if within is not None:
        candidates = _occurrences(text, wanted, within[0], within[1])
    if not candidates:
        candidates = _occurrences(text, wanted, 0, len(text))
    if not candidates:
        return None
    start, end = next((span for span in candidates if span not in taken), candidates[0])
    return text[start:end], start, end


def _inside(span: Span, evidence: Span) -> bool:
    return evidence[1] <= span[1] and span[2] <= evidence[2]


# --------------------------------------------------------------------------- parsing

def _list(raw: dict[str, Any], name: str, limit: int, required: bool = False) -> list[dict[str, Any]]:
    value = raw.get(name)
    if value is None and not required:
        return []
    if not isinstance(value, list):
        raise _Rejected(f"{name}_missing" if value is None else f"{name}_not_a_list")
    if not all(isinstance(item, dict) for item in value):
        raise _Rejected(f"{name}_item_not_an_object")
    return value[:limit]


def _required_code(item: dict[str, Any], name: str, allowed: Collection[str], what: str) -> str:
    value = item.get(name)
    if not isinstance(value, str) or value not in allowed:
        raise _Rejected(f"{what}_{name}_unknown")
    return value


def _strings(value: Any, limit: int, allowed: Collection[str] | None = None) -> list[str] | None:
    """A list of distinct strings in first-seen order, or None when the value is not such a list."""
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        return None
    if allowed is not None and not set(value) <= set(allowed):
        return None
    return list(dict.fromkeys(value))[:limit]


def _clause(item: dict[str, Any], text: str, taken: set[tuple[int, int]]) -> Clause | None:
    """One clause, or None when its evidence is not in the text. Raises ``_Rejected`` on a shape error."""
    for name, allowed in _REQUIRED.items():
        if name not in item:
            raise _Rejected(f"clause_{name}_missing")
        if allowed is not None:
            _required_code(item, name, allowed, "clause")
    unknown = set(item) - set(READING_SCHEMA["properties"]["clauses"]["items"]["properties"])
    if not isinstance(item["evidence"], str):
        raise _Rejected("clause_evidence_not_a_string")
    evidence = resolve_span(text, item["evidence"], taken=taken)
    if evidence is None:
        return None
    taken.add((evidence[1], evidence[2]))
    problems = [f"unknown_member_{name}" for name in sorted(unknown)]
    clause_id = item["id"] if isinstance(item["id"], str) else ""
    if not _CLAUSE_ID_RE.match(clause_id):
        problems.append("id_invalid")
    clause = Clause(id=clause_id, evidence=evidence, intent=item["intent"], polarity=item["polarity"],
                    subject_kind=item["subject_kind"], direction=item["direction"], confidence=item["confidence"])
    for name in SUB_SPANS:
        value = item.get(name)
        if value is None:
            continue
        span = resolve_span(text, value, within=(evidence[1], evidence[2]))
        if span is None:
            problems.append(f"{name}_not_in_text")
        elif not _inside(span, evidence):
            problems.append(f"{name}_outside_evidence")
        else:
            setattr(clause, name, span)
    for name, allowed in _OPTIONAL_CODES.items():
        value = item.get(name)
        if value is not None and value not in allowed:
            problems.append(f"{name}_unknown")
        elif value is not None:
            setattr(clause, name, value)
    for name, limit, allowed in (("company_ids", MAX_CLAUSE_COMPANIES, None), ("sectors", MAX_CLAUSE_SECTORS, None),
                                 ("natures", len(CONTROVERSY_NATURES), CONTROVERSY_NATURES),
                                 ("ambiguity", len(AMBIGUITY_CODES), AMBIGUITY_CODES)):
        values = _strings(item.get(name), limit, allowed)
        if values is None:
            problems.append(f"{name}_invalid")
        else:
            setattr(clause, name, values)
    distribution = item.get("distribution")
    if distribution is not None:
        if distribution in DISTRIBUTIONS:
            clause.distribution = distribution
        else:
            problems.append("distribution_unknown")
    for name in CLAUSE_REFS:
        value = item.get(name)
        if value is None:
            continue
        if isinstance(value, str) and _CLAUSE_ID_RE.match(value) and value != clause_id:
            setattr(clause, name, value)
        else:
            problems.append(f"{name}_invalid")
    objective = item.get("objective")
    if isinstance(objective, int) and not isinstance(objective, bool) and objective >= 0:
        clause.objective = objective
    elif objective is not None:
        problems.append("objective_invalid")
    clause.problems = problems
    return clause


def parse_reading(raw: Any, text: str) -> Reading:
    """The model's reading, checked and pinned to the request text (see the module docstring for what fails how)."""
    if not isinstance(raw, dict):
        raise _Rejected("reading_not_an_object")
    unknown = set(raw) - set(READING_SCHEMA["properties"])
    if unknown:
        raise _Rejected("reading_unknown_member")
    dropped: list[str] = []

    objectives = []
    for item in _list(raw, "objectives", MAX_OBJECTIVES):
        kind = _required_code(item, "kind", OBJECTIVE_KINDS, "objective")
        words = resolve_span(text, item.get("words"))
        if words is None:
            dropped.append("objective_not_in_text")
        else:
            objectives.append(Objective(words, kind))

    taken: set[tuple[int, int]] = set()
    clauses: list[Clause] = []
    items = _list(raw, "clauses", MAX_CLAUSES, required=True)
    for item in items:
        clause = _clause(item, text, taken)
        if clause is None:
            dropped.append("clause_evidence_not_in_text")
        else:
            clauses.append(clause)
    seen: set[str] = set()
    for clause in clauses:
        if clause.id in seen:
            clause.problems.append("id_duplicate")
        seen.add(clause.id)
    failed = len(items) - len(clauses) + sum(1 for c in clauses if c.problems)
    if items and 2 * failed > len(items):
        raise _Rejected("most_clauses_unusable")

    usable = {c.id for c in clauses if not c.problems}
    conflicts = []
    for item in _list(raw, "conflicts", MAX_CONFLICTS):
        kind = _required_code(item, "kind", CONFLICT_KINDS, "conflict")
        a, b = item.get("a"), item.get("b")
        if a in usable and b in usable and a != b:
            conflicts.append(Conflict(a, b, kind))
        else:
            dropped.append("conflict_reference_unknown")

    non_quantity = []
    for item in _list(raw, "non_quantity", MAX_NON_QUANTITY):
        kind = _required_code(item, "kind", NON_QUANTITY_KINDS, "non_quantity")
        mention = resolve_span(text, item.get("mention"))
        if mention is None:
            dropped.append("non_quantity_not_in_text")
        else:
            non_quantity.append(NonQuantity(mention, kind))
    return Reading(objectives, clauses, conflicts, non_quantity, dropped)
