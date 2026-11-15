"""Policy interpreter: the investor's words -> a DRAFT ``interpretation`` (contracts/api.md section 3).

What the model does and does not do
-----------------------------------
The model is an *extractor*. After optional read-only lookups (``find_companies``, ``describe_sector``; see
``Interpreter``) it answers with one structured object (the ``submit_interpretation`` tool, or the same object as
JSON text) that only

* marks spans of the investor's text (``words``), and
* picks codes from closed lists: objective kind, rule type, clarification topic, unsupported reason, controversy
  nature, and company ids / sector labels taken from lists the server built from the data snapshot.

Nothing the model writes is ever returned to the client:

* every sentence of the interpretation (questions, option labels and descriptions, unsupported reasons, scope
  descriptions) is a template in this module or in ``byb_contracts.templates``, selected by the validated codes;
* a span is accepted only if it is found in the investor's text, and the text returned is the slice of the
  *request* text, never the model's string;
* members that are not in the tool schema (``status``, ``threshold``, ``origin``, ids, prose ...) are never read;
* ids, timestamps, ``status: PROPOSED``, ``origin``, ``model_id`` and ``original_words`` are set by the server.

Numbers
-------
The model cannot supply a number: there is no numeric member in the tool schema. A threshold is derived by the
server, from the request text alone, and only when all of this holds:

* the rule's span lies inside one sentence of the investor's text;
* the span the number is read from (``threshold_words``, else the rule's own span) lies inside the rule's own words;
* that sentence holds no other number, no hedge, a direction cue that agrees with the rule type, and no negation;
* that span contains exactly one number written as a percentage ("10%", "10 %", "10 percent", "2,5 %"), between
  0 and 100;
* the sentence does not address the system ("ignore ...", "confirm ...", "set the threshold ...").

The rule then carries ``threshold = percentage / 100``, ``threshold_source: USER_WORDS`` and the literal characters
of the number as ``threshold_quote``. In every other case where a number seems intended (a bare "0.10", "ten
percent", two percentages, a number in another sentence) the threshold stays ``null`` and the draft is offered
through a question, so the investor types the number. Refusing is always the safe direction: the heuristic for
"addresses the system" can only turn a number into a question, never the reverse.

Failure
-------
Unusable output (not JSON, truncated, unknown code, unknown company or sector, a span that is not in the text, or
a draft that fails ``byb_contracts.interpretation_errors``) is retried once if the time budget allows, then
``InterpreterFailed`` (502). A model error is ``InterpreterFailed``; running out of the time budget is
``InterpreterTimeout`` (504). Nothing is stored and no policy is read or written here, and the engine is never
called: this module cannot produce a verdict.
"""

from __future__ import annotations

import difflib
import json
import re
import uuid
from typing import Any, Callable

from byb_contracts import SCHEMA_VERSION, interpretation_errors
from byb_contracts.constants import CONTROVERSY_NATURES, INTERPRET_TIMEOUT_SECONDS, OBJECTIVE_KINDS, RULE_TYPES, SCENARIO_IDS
from byb_contracts.templates import scope_description

from backend.agents.bedrock_client import FAILURE_DEADLINE_EXCEEDED, ModelCallError
from backend.agents.prompts import (
    DESCRIBE_SECTOR_TOOL_NAME,
    FIND_COMPANIES_TOOL_NAME,
    INTERPRETER_LOOKUP_DONE_NOTE,
    INTERPRETER_PROMPT_VERSION,
    INTERPRETER_SYSTEM_PROMPT,
    INTERPRETER_TOOL_NAME,
    build_interpreter_message,
)
from backend.agents.schema import validate as schema_errors
from backend.agents.themes import (
    AVOID_CUE_RE,
    COMPANY_ALIASES,
    CUE_WINDOW,
    ONLY_CUE_RE,
    POLARITIES,
    PREFER_CUE_RE,
    THEME_CODES,
    THEME_TERM_RE,
    THEMES,
    TRAILING_NOUN_RE,
    sector_mentions,
    sectors_written_in,
)
from backend.common import log
from backend.common.clock import to_iso

MAX_ITEMS = 8  # per list of the model's answer; anything beyond is dropped
MAX_COMPANY_CANDIDATES = 40
MAX_SECTOR_LABELS = 120
DEFAULT_NATURES = ("REGULATORY_FINDING", "COURT_RULING", "SETTLEMENT")

TOPICS = ("EXCLUSION_DEFINITION", "DIVERSIFICATION", "LOSS_LIMIT", "THEME", "SECTOR_FOCUS")
MAX_FOCUS_SECTORS = 4  # sectors one "only ..." request may keep
MAX_FOCUS_RULES = 14  # exclusions one "only ..." request may draft (one per other sector label)
MAX_LOOKUP_MATCHES = 5
MAX_LOOKUPS_PER_ROUND = 6
_NUMBER_NEEDED = "NUMBER_NEEDED"  # raised by the server only

_NO_FORECAST = "This tool checks a proposed purchase against rules you confirmed. "
# reason code -> (contract unsupported code, server-written reason)
UNSUPPORTED_REASONS: dict[str, tuple[str, str]] = {
    "OIL_PRODUCERS": ("UNSUPPORTED_DEFINITION", "We hold no sourced classification of oil producers, so this cannot be checked honestly."),
    "FOSSIL_FUELS": ("UNSUPPORTED_DEFINITION", "We hold no sourced fossil-fuel classification, so this cannot be checked honestly."),
    "NO_SOURCED_DEFINITION": ("UNSUPPORTED_DEFINITION", "We hold no sourced data that defines this, so it cannot be checked honestly."),
    "COMPANY_NOT_IN_DATA": ("UNSUPPORTED_DEFINITION", "No company in the data snapshot could be matched to these words, so no rule was drafted for it."),
    "GROWTH_OR_RETURN": ("UNSUPPORTED_RULE_TYPE", "No rule type measures growth, and the tool does not forecast returns. It is kept as a qualitative objective."),
    "SECTOR_LIMIT": ("UNSUPPORTED_RULE_TYPE", "There is no sector-cap rule type in this version."),
    "NOT_MEASURABLE": ("UNSUPPORTED_RULE_TYPE", "No rule type in this version measures this. It is not checked numerically."),
    "RECOMMENDATION": ("OUT_OF_SCOPE", _NO_FORECAST + "It does not recommend what to buy or whether to buy."),
    "FORECAST": ("OUT_OF_SCOPE", _NO_FORECAST + "It does not forecast prices or returns."),
    "TRADE": ("OUT_OF_SCOPE", _NO_FORECAST + "It is a simulation: it places no order and executes no trade."),
    "OPTIMIZATION": ("OUT_OF_SCOPE", _NO_FORECAST + "It does not build or optimize a portfolio."),
    "INSTRUCTION": ("INSTRUCTION_IGNORED", "This reads as an instruction to the system. It was treated as text and not acted on."),
}
_CLARIFICATION_SUFFIX = " Stored rules stay as they are until you confirm a change."
_SECTOR_NOT_MATCHED = ("UNSUPPORTED_DEFINITION", "These words could not be matched to a sector label the funds report, so no rule was drafted. "
                       "Name the sector as it appears in the data: {labels}.")
# Unsupported codes a model may wrongly give to "only tech stocks"; the server re-reads such words as a sector focus.
_FOCUS_MISFILED = ("SECTOR_LIMIT", "NOT_MEASURABLE", "NO_SOURCED_DEFINITION")
_FOCUS_TOO_WIDE = ("UNSUPPORTED_DEFINITION", "Keeping only these sectors would need more exclusion rules than one request can draft. "
                   "Name the sectors to leave out instead.")

_THRESHOLD_KIND = {"max_issuer_exposure": "max_fraction", "min_issuer_exposure": "min_fraction", "exclusion": "max_fraction",
                   "controversy_exclusion": "max_fraction", "scenario_loss_budget": "max_loss_fraction"}
_RULE_SLUG = {"max_issuer_exposure": "issuer-cap", "min_issuer_exposure": "issuer-min", "exclusion": "excl",
              "controversy_exclusion": "controversy", "scenario_loss_budget": "loss"}

# One number written as a percentage. The look-behind keeps "110%" from being read as "10%".
# Only a plain unsigned percentage is read: no sign, range dash, comparison or currency before it, at most two
# decimals (so "1,000%" is not read as 1%), and nothing like "+", "-" or "~" straight after it.
_PERCENT_RE = re.compile(r"(?<![\w.,\-\u2212\u2013\u2014+~\u2248<>=$\u20ac\u00a3/])(\d{1,3}(?:[.,]\d{1,2})?)\s*(?:%|percent\b|per cent\b|pct\b|pour cent\b)"
                         r"(?!\s*[+\-\u2212\u2013~\u2248])", re.IGNORECASE)
# Any written number. A sentence with a second one (a range, an alternative, another percentage, a year) gives no threshold.
_NUMBER_TOKEN_RE = re.compile(r"\d[\d.,]*")
_YEAR_RE = re.compile(r"(?:19|20)\d\d[.,]?")  # a calendar year ("a year like 2022") is not a second quantity
# Words that make a number approximate, a range or an alternative. Used ONLY to refuse a number (safe direction).
_HEDGE_RE = re.compile(r"\b(roughly|about|around|approximately|approx|maybe|perhaps|probably|possibly|somewhere|between|or so|or more|or less|"
                       r"give or take|more or less|ish)\b|[~\u2248]", re.IGNORECASE)
# Direction cues, looked for in the investor's sentence. A maximum-type rule needs a maximum cue and no minimum cue, and the reverse.
# "I do not want to lose more than 10%" is a maximum: a negation followed closely by "more than", with no number between.
_MAX_CUE_RE = re.compile(r"\b(?:do not|don['\u2019]t|not|no|never)\b[^.;%\d]{0,30}?\bmore than\b|"
                         r"\b(at most|no greater than|not exceed|never exceed|maximum|max|cap|capped|limit|limited|up to|ceiling)\b", re.IGNORECASE)
_MIN_CUE_RE = re.compile(r"\b(at least|no less than|not less than|no fewer than|minimum|min|floor)\b", re.IGNORECASE)
# A negation left in the sentence once the cue phrases are removed ("I do not want a 10% limit").
_NEGATION_RE = re.compile(r"\b(not|no|never|without|neither|nor|none|cannot)\b|n['\u2019]t\b", re.IGNORECASE)
_LIMIT_TYPES = ("max_issuer_exposure", "min_issuer_exposure", "scenario_loss_budget")
_SEVERAL_COMPANIES = ("UNSUPPORTED_DEFINITION", "These words are in a sentence that names more than one company, so no rule was drafted for one of them. "
                      "Write one company per sentence.")
# Something that looks like a quantity, so a missing percentage deserves a question instead of silence.
_NUMBERISH_RE = re.compile(r"\d|%|\b(percent|per cent|pct|pour cent|half|third|quarter)\b", re.IGNORECASE)
# A sentence that talks to the system rather than about the portfolio. Used ONLY to refuse a number (safe direction).
_ADDRESSES_SYSTEM_RE = re.compile(
    r"\b(ignore|disregard|forget|override|bypass|instructions?|prompt|system|assistant|confirm\w*|approve\w*|activate\w*|"
    r"set\s+(the\s+|my\s+|a\s+|every\s+|all\s+)?(status|threshold|limit|rule)s?|you\s+(must|should|are|will)|pretend|jailbreak)\b", re.IGNORECASE)
_SENTENCE_BREAK_RE = re.compile(r"(?<=[.!?;])\s+|\n+")
_OIL_RE = re.compile(r"\b(oil|petroleum|fossil)\b", re.IGNORECASE)
# Ambiguity catalog scanned on the request text itself, independent of the model.
_CATALOG_RE = re.compile(r"\b(oil|petroleum|fossil fuels?|fossil)\b", re.IGNORECASE)
_NAME_NOISE_RE = re.compile(r"\([^)]*\)|\b(inc|corp|corporation|co|company|ltd|limited|plc|sa|nv|ag|class [a-c]|cl [a-c]|com|the)\b")


class InterpreterFailed(Exception):
    """No valid draft could be produced (model error, or output rejected after the bounded retry): 502."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class InterpreterTimeout(Exception):
    """The time budget ran out before a valid draft existed: 504."""


class _Rejected(Exception):
    """The model's answer is unusable. ``reason`` is a fixed server code, never model text."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


# --------------------------------------------------------------------------
# Reference data from the snapshot
# --------------------------------------------------------------------------


def _normalize(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text.lower()).split())


class _Reference:
    """Sector labels and company names of one snapshot, indexed once."""

    def __init__(self, snapshot: Any) -> None:
        sectors: set[str] = set()
        names: dict[str, set[str]] = {}
        tickers: dict[str, set[str]] = {}
        display: dict[str, str] = {}
        sector_of: dict[str, str] = {}

        def add(issuer_id: Any, name: Any, instrument_id: Any, sector: Any) -> None:
            if not isinstance(issuer_id, str) or not issuer_id:
                return
            phrases = names.setdefault(issuer_id, set())
            phrases.add(_normalize(issuer_id))
            if isinstance(name, str) and name:
                display.setdefault(issuer_id, name[:80])
                cleaned = _normalize(_NAME_NOISE_RE.sub(" ", name.lower()))
                if len(cleaned) >= 4:
                    phrases.add(cleaned)
            if isinstance(instrument_id, str) and instrument_id:
                tickers.setdefault(issuer_id, set()).update({instrument_id, instrument_id.split(".")[0]})
            if isinstance(sector, str) and sector:
                sector_of.setdefault(issuer_id, sector)

        for instrument in snapshot.registry.values():
            if instrument.get("is_fund"):
                continue
            equity_sector = instrument.get("sector") if instrument.get("equity_scope") else None
            add(instrument.get("issuer_id"), instrument.get("name"), instrument.get("instrument_id"), equity_sector)
            if isinstance(equity_sector, str) and equity_sector:
                sectors.add(equity_sector)
        for fund in (snapshot.holdings.get("funds") or {}).values():
            for row in fund.get("holdings") or []:
                add(row.get("issuer_id"), row.get("name"), row.get("instrument_id"), row.get("sector"))
                if isinstance(row.get("sector"), str) and row["sector"]:
                    sectors.add(row["sector"])

        # Common names ("Google" for Alphabet): an alias resolves only to a company whose cleaned name is in the data.
        by_name: dict[str, set[str]] = {}
        for issuer_id, phrases in names.items():
            for phrase in phrases:
                by_name.setdefault(phrase, set()).add(issuer_id)
        for alias, target in COMPANY_ALIASES.items():
            for issuer_id in by_name.get(target, ()):
                names[issuer_id].add(_normalize(alias))

        self.sectors = sorted(sectors)[:MAX_SECTOR_LABELS]
        self.display = display
        self.sector_of = sector_of
        self._phrases: dict[str, set[str]] = {}
        first_words: dict[str, set[str]] = {}
        for issuer_id, phrases in names.items():
            for phrase in phrases:
                if len(phrase) >= 3:
                    self._phrases.setdefault(phrase, set()).add(issuer_id)
            first = _normalize(issuer_id).split(" ")[0] if _normalize(issuer_id) else ""
            if len(first) >= 5:
                first_words.setdefault(first, set()).add(issuer_id)
        # The first word of a company id ("exxon" for EXXON_MOBIL) counts only when a single company starts with it.
        for first, issuers in first_words.items():
            if len(issuers) == 1:
                self._phrases.setdefault(first, set()).update(issuers)
        self._tickers: dict[str, set[str]] = {}
        for issuer_id, symbols in tickers.items():
            for symbol in symbols:
                if len(symbol) >= 2:
                    self._tickers.setdefault(symbol, set()).add(issuer_id)

    def companies_in(self, text: str) -> list[str]:
        """Issuer ids whose name, id or ticker is written in ``text`` (deterministic; no model involved)."""
        words = _normalize(text).split(" ")
        found: set[str] = set()
        for size in range(1, 7):
            for start in range(0, len(words) - size + 1):
                found.update(self._phrases.get(" ".join(words[start:start + size]), ()))
        for symbol in re.findall(r"(?<![A-Za-z0-9])[A-Z0-9][A-Z0-9.-]{1,11}(?![A-Za-z0-9])", text):  # tickers: upper case only
            found.update(self._tickers.get(symbol, ()))
            found.update(self._tickers.get(symbol.rstrip(".-"), ()))
        return sorted(found)[:MAX_COMPANY_CANDIDATES]

    def find(self, words: str) -> list[str]:
        """Issuer ids for words the investor wrote, for the agent's lookup tool: exact matches first, then close spellings
        ("Microsft") and name prefixes ("Royal"). Deterministic: the server matches, the model only chose the words."""
        exact = self.companies_in(words)
        if exact:
            return exact[:MAX_LOOKUP_MATCHES]
        wanted = _normalize(words)
        if len(wanted) < 3:
            return []
        found: list[str] = []
        close = difflib.get_close_matches(wanted, list(self._phrases), n=MAX_LOOKUP_MATCHES, cutoff=0.82)
        prefixed = [phrase for phrase in sorted(self._phrases) if len(wanted) >= 4 and phrase.startswith(wanted + " ")]
        for phrase in close + prefixed:
            for issuer_id in sorted(self._phrases[phrase]):
                if issuer_id not in found:
                    found.append(issuer_id)
        return found[:MAX_LOOKUP_MATCHES]

    def describe(self, issuer_id: str) -> dict[str, Any]:
        return {"issuer_id": issuer_id, "name": self.display.get(issuer_id, issuer_id), "sector": self.sector_of.get(issuer_id)}

    def sector_members(self, sector: str, limit: int = 8) -> list[str]:
        """Names of companies the data labels with ``sector`` (examples for the agent, not a definition)."""
        return sorted(self.display.get(i, i) for i, label in self.sector_of.items() if label == sector)[:limit]


# --------------------------------------------------------------------------
# Tool schema (the only shape the model may answer in)
# --------------------------------------------------------------------------


def tool_config(sectors: list[str], companies: list[str]) -> dict[str, Any]:
    words = {"type": "string", "description": "A contiguous part of the investor's text, copied character for character."}
    objective = {"type": ["integer", "null"], "description": "Index (from 0) of the objective this belongs to, or null."}
    sector = {"type": ["string", "null"], "enum": [*sectors, None]}
    company = {"type": "string", "enum": companies} if companies else {"type": "string"}
    schema = {
        "type": "object",
        "required": ["objectives", "rules", "ambiguous", "unsupported"],
        "additionalProperties": False,
        "properties": {
            "objectives": {"type": "array", "maxItems": MAX_ITEMS, "items": {
                "type": "object", "required": ["words", "kind"], "additionalProperties": False,
                "properties": {"words": words, "kind": {"type": "string", "enum": list(OBJECTIVE_KINDS)}}}},
            "rules": {"type": "array", "maxItems": MAX_ITEMS, "items": {
                "type": "object", "required": ["words", "rule_type"], "additionalProperties": False,
                "properties": {
                    "words": words,
                    "rule_type": {"type": "string", "enum": list(RULE_TYPES)},
                    "issuer_id": {"type": ["string", "null"], "enum": [*companies, None]},
                    "issuer_ids": {"type": "array", "items": company},
                    "sector": sector,
                    "natures": {"type": "array", "items": {"type": "string", "enum": list(CONTROVERSY_NATURES)}},
                    "threshold_words": {"type": ["string", "null"], "description": "The part of the same sentence that contains the investor's percentage, or null."},
                    "objective": objective}}},
            "ambiguous": {"type": "array", "maxItems": MAX_ITEMS, "items": {
                "type": "object", "required": ["words", "topic"], "additionalProperties": False,
                "properties": {"words": words, "topic": {"type": "string", "enum": list(TOPICS)}, "sector": sector,
                               "theme": {"type": ["string", "null"], "enum": [*THEME_CODES, None],
                                         "description": "For topic THEME: which values-based wish the words express."},
                               "polarity": {"type": ["string", "null"], "enum": [*POLARITIES, None],
                                            "description": "For topic THEME: ONLY (only/exclusively), AVOID (avoid/exclude) or PREFER."},
                               "sectors": {"type": "array", "maxItems": MAX_FOCUS_SECTORS, "items": {"type": "string", "enum": sectors} if sectors else {"type": "string"},
                                           "description": "For topic SECTOR_FOCUS: the sector labels the investor wants to keep."},
                               "objective": objective}}},
            "unsupported": {"type": "array", "maxItems": MAX_ITEMS, "items": {
                "type": "object", "required": ["words", "reason"], "additionalProperties": False,
                "properties": {"words": words, "reason": {"type": "string", "enum": list(UNSUPPORTED_REASONS)}}}},
        },
    }
    return {"tools": [
        {"toolSpec": {
            "name": INTERPRETER_TOOL_NAME,
            "description": "Submit the marked parts of the investor's text. Codes only: nothing written here is shown to anyone.",
            "inputSchema": {"json": schema},
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
            "inputSchema": {"json": {"type": "object", "required": ["sector"], "additionalProperties": False,
                                     "properties": {"sector": {"type": "string", "enum": sectors} if sectors else {"type": "string"}}}},
        }},
    ]}


FIND_COMPANIES_SCHEMA = {"type": "object", "required": ["words"], "additionalProperties": False,
                         "properties": {"words": {"type": "string", "minLength": 2, "maxLength": 80,
                                                  "description": "The company as the investor wrote it, copied from their text."}}}


# --------------------------------------------------------------------------
# Reading the model's answer
# --------------------------------------------------------------------------


def _extraction(response: dict[str, Any]) -> dict[str, Any]:
    """The structured answer: the tool input, else the text parsed as one JSON object."""
    if response.get("stopReason") == "max_tokens":
        raise _Rejected("output_truncated")
    content = ((response.get("output") or {}).get("message") or {}).get("content") or []
    texts = []
    for block in content if isinstance(content, list) else []:
        if not isinstance(block, dict):
            continue
        use = block.get("toolUse")
        if isinstance(use, dict) and use.get("name") == INTERPRETER_TOOL_NAME:
            if not isinstance(use.get("input"), dict):
                raise _Rejected("tool_input_not_an_object")
            return use["input"]
        if isinstance(block.get("text"), str):
            texts.append(block["text"])
    raw = "".join(texts).strip()
    if raw.startswith("```"):
        raw = raw.strip("`").strip()
        raw = raw[4:].strip() if raw[:4].lower() == "json" else raw
    try:
        parsed = json.loads(raw)
    except (ValueError, RecursionError) as error:
        raise _Rejected("output_not_json") from error
    if not isinstance(parsed, dict):
        raise _Rejected("output_not_an_object")
    return parsed


def _items(extraction: dict[str, Any], name: str) -> list[dict[str, Any]]:
    value = extraction.get(name)
    if not isinstance(value, list):
        raise _Rejected(f"{name}_missing")
    if not all(isinstance(item, dict) for item in value):
        raise _Rejected(f"{name}_item_not_an_object")
    return value[:MAX_ITEMS]


def _span(text: str, value: Any, what: str) -> tuple[int, int]:
    """Where ``value`` is in ``text``: ``(start, end)``. Tolerates case and spacing differences; the returned
    range always indexes the request text, so what is echoed is the investor's own characters."""
    if not isinstance(value, str) or not value.strip():
        raise _Rejected(f"{what}_words_missing")
    wanted = value.strip()
    start = text.find(wanted)
    if start >= 0:
        return start, start + len(wanted)
    pattern = r"\s+".join(re.escape(token) for token in wanted.split())
    match = re.search(pattern, text, re.IGNORECASE)
    if match is None or match.end() == match.start():
        raise _Rejected(f"{what}_words_not_in_text")
    return match.start(), match.end()


def _code(value: Any, allowed: Any, what: str) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise _Rejected(f"{what}_unknown")
    return value


def _sentence_of(text: str, start: int, end: int) -> tuple[int, int] | None:
    """The sentence that contains ``text[start:end]`` entirely, or None when the span crosses a sentence break."""
    begin = 0
    for match in _SENTENCE_BREAK_RE.finditer(text):
        if match.start() >= end:
            break
        if match.end() <= start:
            begin = match.end()
            continue
        return None  # a break lies inside the span
    following = _SENTENCE_BREAK_RE.search(text, end)
    return begin, (following.start() if following else len(text))


def negated(sentence: str) -> bool:
    """A negation remains in the sentence once the direction cue phrases ("no more than", "never exceed") are removed."""
    return _NEGATION_RE.search(_MIN_CUE_RE.sub(" ", _MAX_CUE_RE.sub(" ", sentence))) is not None


def direction_agrees(sentence: str, rule_type: str) -> bool:
    """The sentence carries a cue for the rule type's direction and none for the opposite one."""
    has_max, has_min = _MAX_CUE_RE.search(sentence) is not None, _MIN_CUE_RE.search(sentence) is not None
    if rule_type == "min_issuer_exposure":
        return has_min and not has_max
    if rule_type in ("exclusion", "controversy_exclusion"):
        return not has_min  # avoiding is a maximum by nature ("Exclude Energy completely, 0%")
    return has_max and not has_min


def user_number(text: str, rule_span: tuple[int, int], number_span: tuple[int, int], rule_type: str) -> tuple[float, str] | None:
    """``(fraction, quote)`` when the investor's own text states exactly one plain percentage for this rule, else None.

    The value is computed from the characters of the request text; no number from the model is involved, and the model
    cannot choose among numbers: the number lies inside the rule's own words and is the only number of its sentence.
    """
    sentence = _sentence_of(text, *rule_span)
    if sentence is None or not (rule_span[0] <= number_span[0] and number_span[1] <= rule_span[1]):
        return None
    sentence_text = text[sentence[0]:sentence[1]]
    if _ADDRESSES_SYSTEM_RE.search(sentence_text) or _HEDGE_RE.search(sentence_text):
        return None
    if len([token for token in _NUMBER_TOKEN_RE.findall(sentence_text) if not _YEAR_RE.fullmatch(token)]) != 1:
        return None  # a second number: another percentage, a range, an alternative, a year
    if not direction_agrees(sentence_text, rule_type) or negated(sentence_text):
        return None
    matches = list(_PERCENT_RE.finditer(text, number_span[0], number_span[1]))
    if len(matches) != 1:
        return None
    percentage = float(matches[0].group(1).replace(",", "."))
    if not 0 <= percentage <= 100:
        return None
    return round(percentage / 100, 10), matches[0].group(0)


# --------------------------------------------------------------------------
# Server-written drafts and questions
# --------------------------------------------------------------------------


def draft_rule(rule_id: str, rule_type: str, parameters: dict[str, Any], words: str, objective_id: str | None,
               number: tuple[float, str] | None = None) -> dict[str, Any]:
    """A PROPOSED, unconfirmed rule. With a number: quoted from the investor's words; without: SYSTEM_PROPOSED, null."""
    return {
        "rule_id": rule_id, "rule_type": rule_type, "parameters": parameters,
        "threshold": number[0] if number else None, "threshold_kind": _THRESHOLD_KIND[rule_type],
        "threshold_source": "USER_WORDS" if number else None, "threshold_quote": number[1] if number else None,
        "unit": "fraction", "status": "PROPOSED", "origin": "USER_STATED" if number else "SYSTEM_PROPOSED",
        "original_words": words, "objective_id": objective_id, "scope_description": scope_description(rule_type, parameters),
        "confirmed_at": None, "confirmed_by": None, "supersedes_rule_id": None, "superseded_by_rule_id": None,
    }


def _option(option_id: str, label: str, description: str, supported: bool = True, rule: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"option_id": option_id, "label": label, "description": description, "supported": supported,
            "proposed_rule": rule if supported else None, "purchase_request": None}


_KEEP_QUALITATIVE = ("keep-qualitative", "Keep it as a qualitative preference only",
                     "Nothing will be checked numerically for it; it stays visible as context.")
_NAMED_COMPANIES = ("named-companies", "Specific companies that I name",
                    "Supported once you name them: type the companies in a new sentence and a named-company exclusion will be drafted.")
_NAMED_SECTORS = ("named-sectors", "Sector labels that I name",
                  "Supported once you name them: write, for example, 'avoid Energy' or 'only Utilities and Health Care' and the exclusions will be drafted.")
_CONTROVERSY_OPTION = ("recorded-controversies", "Companies with a recorded controversy",
                       "Leaves out companies with a regulatory finding, court ruling or settlement in the controversy registry, which holds "
                       "environmental enforcement records. A company the registry has not researched is reported as unknown, never as clean.")
# theme -> (option id, label, description) of the definition the data cannot support
_THEME_UNSUPPORTED = {
    "ENVIRONMENTAL": ("green-classification", "Only companies rated or classified as environmentally friendly",
                      "Not supported: we hold no sourced environmental rating, carbon or green-revenue data, so this cannot be checked honestly."),
    "ESG": ("esg-score", "Companies with a good ESG score or rating",
            "Not supported: we hold no sourced ESG scores or ratings, so this cannot be checked honestly."),
    "SOCIAL": ("social-classification", "Companies classified by their social or labour practices",
               "Not supported: we hold no sourced classification of social or labour practices, so this cannot be checked honestly."),
}


class _Builder:
    """Turns one validated extraction into the interpretation. Every string it emits is a template or a slice of ``text``."""

    def __init__(self, text: str, reference: _Reference, companies: list[str], clarification_mode: bool) -> None:
        self.text = text
        self.reference = reference
        self.companies = set(companies)
        self.clarification_mode = clarification_mode
        self.objectives: list[dict[str, Any]] = []
        self.rules: list[dict[str, Any]] = []
        self.unsupported: list[dict[str, Any]] = []
        self.clarifications: list[dict[str, Any]] = []
        self._rule_count = 0
        self._asked: set[tuple[str, str]] = set()
        # Spans of the catalog terms ("oil", "fossil fuels") in the request text. The server's own question about
        # them always wins: nothing the model says about an overlapping span is used.
        self._catalog_spans: list[tuple[int, int]] = [match.span() for match in _CATALOG_RE.finditer(text)]
        # Spans the model gave a code to (rule, question or unsupported). The theme safety net only fills gaps.
        self._covered: list[tuple[int, int]] = []

    def _in_catalog(self, span: tuple[int, int]) -> bool:
        return any(span[0] < end and start < span[1] for start, end in self._catalog_spans)

    # -- helpers

    def _words(self, value: Any, what: str) -> tuple[str, tuple[int, int]]:
        span = _span(self.text, value, what)
        return self.text[span[0]:span[1]], span

    def _objective_id(self, index: Any, span: tuple[int, int]) -> str | None:
        if self.clarification_mode or not self.objectives:
            return None
        if isinstance(index, int) and not isinstance(index, bool) and 0 <= index < len(self.objectives):
            return self.objectives[index]["objective_id"]
        words = self.text[span[0]:span[1]]
        return next((o["objective_id"] for o in self.objectives if words in o["original_words"]), None)

    def _rule_id(self, rule_type: str) -> str:
        self._rule_count += 1
        return f"draft-{_RULE_SLUG[rule_type]}-{self._rule_count}"

    def _sector(self, value: Any) -> str | None:
        if value is None or value == "":
            return None
        if not isinstance(value, str) or value not in self.reference.sectors:
            raise _Rejected("sector_not_in_snapshot")
        return value

    def _company(self, value: Any) -> str:
        if not isinstance(value, str) or value not in self.companies:
            raise _Rejected("company_not_named_in_text_or_not_in_snapshot")
        return value

    # -- questions

    def _covers(self, span: tuple[int, int]) -> bool:
        return any(span[0] < end and start < span[1] for start, end in self._covered)

    def _sector_exclusion(self, sector: str, words: str, objective_id: str | None) -> dict[str, Any]:
        return draft_rule(self._rule_id("exclusion"), "exclusion", {"definition": {"kind": "fund_reported_sector", "sector": sector}}, words, objective_id)

    def ask(self, topic: str, words: str, objective_id: str | None, *, sector: str | None = None,
            pending: tuple[str, dict[str, Any]] | None = None, theme: str | None = None, polarity: str | None = None) -> None:
        if (topic, words) in self._asked:
            return
        self._asked.add((topic, words))
        quoted = f"'{words}'"
        if topic == "THEME":
            theme = theme or "ESG"
            noun = THEMES[theme][0]
            options = []
            if theme == "ENVIRONMENTAL" and "Energy" in self.reference.sectors:
                options.append(_option(
                    "energy-sector-label", "Leave out holdings labelled Energy in what the funds report",
                    "The closest definition the data can check: oil, gas and pipeline companies as labelled by each fund issuer. "
                    "It does not show that the other holdings are environmentally friendly.",
                    rule=self._sector_exclusion("Energy", words, objective_id)))
            options.append(_option(*_CONTROVERSY_OPTION, rule=draft_rule(
                self._rule_id("controversy_exclusion"), "controversy_exclusion",
                {"criteria": {"natures": list(DEFAULT_NATURES), "event_date_from": None}}, words, objective_id)))
            options.append(_option(*_NAMED_SECTORS))
            options.append(_option(*_NAMED_COMPANIES))
            options.append(_option(*_THEME_UNSUPPORTED[theme], False))
            options.append(_option(*_KEEP_QUALITATIVE))
            if polarity == "ONLY":
                question = (f"What should {quoted} mean as a rule you can check? The data holds no list of {noun} holdings, "
                            "so it can only be checked by leaving out what you do not want.")
            else:
                question = f"What should {quoted} mean as a rule you can check? We hold no sourced {noun} rating, so only the definitions below can be checked."
        elif topic == "EXCLUSION_DEFINITION":
            oil = _OIL_RE.search(words) is not None
            if oil:
                # For oil the offered label is never the model's choice: Energy when the snapshot has it, else none.
                sector = "Energy" if "Energy" in self.reference.sectors else None
            options = []
            if sector is not None:
                parameters = {"definition": {"kind": "fund_reported_sector", "sector": sector}}
                slug = re.sub(r"[^a-z0-9]+", "-", sector.lower()).strip("-") or "sector"
                options.append(_option(
                    f"{slug}-sector-label", f"Holdings labelled {sector} in what the funds report",
                    "Uses the sector label in each fund issuer's holdings file (and the registry label for direct holdings)."
                    + (" Broader than oil: it also covers pipelines and gas." if oil and sector == "Energy" else " A sector label can be broader or narrower than what you mean."),
                    rule=draft_rule(self._rule_id("exclusion"), "exclusion", parameters, words, objective_id)))
            options.append(_option(*_NAMED_COMPANIES))
            if oil:
                options.append(_option("oil-producers", "Companies that produce oil",
                                       "Not supported yet: we hold no sourced classification of oil producers, so this cannot be checked honestly.", False))
                options.append(_option("fossil-fuels", "All fossil fuels", "Not supported yet: we hold no sourced fossil-fuel classification.", False))
            else:
                options.append(_option("activity-classification", "Companies classified by what they produce or do",
                                       "Not supported yet: we hold no sourced classification of business activities, so this cannot be checked honestly.", False))
            question = f"What should {quoted} cover? Only definitions we hold sourced data for can be checked."
        elif topic == "DIVERSIFICATION":
            options = [
                _option("single-company-cap", "A maximum share of the portfolio in any single company",
                        "Counts direct holdings and holdings through equity funds. You choose the number.",
                        rule=draft_rule(self._rule_id("max_issuer_exposure"), "max_issuer_exposure", {"issuer_scope": "any"}, words, objective_id)),
                _option("sector-cap", "A maximum share in any single sector", "Not supported yet: there is no sector-cap rule type in this version.", False),
                _option(*_KEEP_QUALITATIVE),
            ]
            question = f"What should {quoted} mean as a rule you can check? Wishes that pull in different directions are not a proven contradiction."
        elif topic == "LOSS_LIMIT":
            options = [
                _option("replay-loss-budget", "A maximum loss when the allocation is replayed through calendar 2022",
                        "A historical replay of an assumed allocation: not a forecast and not a maximum future loss. You choose the number.",
                        rule=draft_rule(self._rule_id("scenario_loss_budget"), "scenario_loss_budget", {"scenario_id": SCENARIO_IDS[0]}, words, objective_id)),
                _option("no-loss-guarantee", "A guarantee that the portfolio never loses value",
                        "Not supported: the tool does not forecast and nothing can guarantee future results.", False),
                _option(*_KEEP_QUALITATIVE),
            ]
            question = f"What should {quoted} mean as a rule you can check?"
        else:  # NUMBER_NEEDED
            rule_type, parameters = pending  # type: ignore[misc]
            options = [
                _option("enter-number", "I will enter the number myself",
                        "The rule is drafted without a number. It stays inactive until you enter one and confirm it.",
                        rule=draft_rule(self._rule_id(rule_type), rule_type, parameters, words, objective_id)),
                _option(*_KEEP_QUALITATIVE),
            ]
            question = (f"Which number should apply to {quoted}? A number is taken from your words only when it is written as one percentage "
                        "in the same sentence as the rule, so none was taken here.")
        self.clarifications.append({"clarification_id": f"clar-{len(self.clarifications) + 1}", "about_words": words, "question": question, "options": options})

    # -- the four lists

    def add_objectives(self, items: list[dict[str, Any]]) -> None:
        seen: set[str] = set()
        for item in items:
            words, _ = self._words(item.get("words"), "objective")
            kind = _code(item.get("kind"), OBJECTIVE_KINDS, "objective_kind")
            if self.clarification_mode or words in seen:
                continue  # a clarification answers about an existing objective; it does not create objectives
            seen.add(words)
            self.objectives.append({"objective_id": f"obj-{len(self.objectives) + 1}", "original_words": words, "kind": kind,
                                    "source": "USER_STATED", "case_reference": None})

    def add_ambiguous(self, items: list[dict[str, Any]]) -> None:
        for item in items:
            words, span = self._words(item.get("words"), "ambiguous")
            topic = _code(item.get("topic"), TOPICS, "topic")
            sector = self._sector(item.get("sector")) if topic == "EXCLUSION_DEFINITION" else None
            theme = _code(item.get("theme") or "ESG", THEME_CODES, "theme") if topic == "THEME" else None
            polarity = _code(item.get("polarity") or "PREFER", POLARITIES, "polarity") if topic == "THEME" else None
            focus = self._focus_sectors(item.get("sectors")) if topic == "SECTOR_FOCUS" else []
            self._covered.append(span)
            if self._in_catalog(span):
                continue  # the catalog's own exclusion-definition question already covers these words
            objective_id = self._objective_id(item.get("objective"), span)
            if topic == "SECTOR_FOCUS":
                self.add_focus(words, focus, objective_id)
                continue
            self.ask(topic, words, objective_id, sector=sector, theme=theme, polarity=polarity)

    def _focus_sectors(self, value: Any) -> list[str]:
        if not isinstance(value, list) or not value:
            raise _Rejected("sector_focus_without_sectors")
        return sorted({self._sector(label) or "" for label in value[:MAX_FOCUS_SECTORS]} - {""})

    def add_focus(self, words: str, focus: list[str], objective_id: str | None) -> None:
        """'Only tech stocks': one exclusion per other sector label, drafted without a number. Which sectors are kept is
        not left to the model: each must be written in the investor's words (the label, or an everyday word for it)."""
        written = sectors_written_in(words, self.reference.sectors)
        suffix = _CLARIFICATION_SUFFIX if self.clarification_mode else ""
        if not focus or not set(focus) <= written:
            reason = _SECTOR_NOT_MATCHED[1].format(labels=", ".join(self.reference.sectors) or "none")
            self.unsupported.append({"words": words, "code": _SECTOR_NOT_MATCHED[0], "reason": reason + suffix})
            return
        others = [label for label in self.reference.sectors if label not in focus]
        if len(others) > MAX_FOCUS_RULES:
            self.unsupported.append({"words": words, "code": _FOCUS_TOO_WIDE[0], "reason": _FOCUS_TOO_WIDE[1] + suffix})
            return
        drafted = {(r["rule_type"], json.dumps(r["parameters"], sort_keys=True)) for r in self.rules}
        for label in others:
            rule = self._sector_exclusion(label, words, objective_id)
            if ("exclusion", json.dumps(rule["parameters"], sort_keys=True)) not in drafted:
                self.rules.append(rule)

    def focus_in(self, span: tuple[int, int]) -> tuple[tuple[int, int], list[str]] | None:
        """'Only tech stocks', read from the request text alone: an only-cue followed, in the same sentence, by sector
        labels or everyday words for them, with no number in the sentence (a stated share per sector is a sector limit,
        which is unsupported) and no theme word ("only green energy" is a theme, not the Energy label).
        Returns the span from the cue to the last sector word, and the sectors kept."""
        sentence = _sentence_of(self.text, *span)
        if sentence is None:
            return None
        sentence_text = self.text[sentence[0]:sentence[1]]
        if _NUMBERISH_RE.search(sentence_text) or negated(ONLY_CUE_RE.sub(" ", sentence_text)):
            return None
        window_start = max(sentence[0], span[0] - CUE_WINDOW)
        cues = [m for m in ONLY_CUE_RE.finditer(self.text, window_start, span[1])]
        if not cues:
            return None
        cue = cues[0]
        limit = min(max(span[1], cue.end()), sentence[1])  # sector words after the cue, inside the words and the sentence
        mentions = [m for m in sector_mentions(self.text, self.reference.sectors) if cue.end() <= m[0] and m[1] <= limit]
        if not mentions:
            return None
        end = max(m[1] for m in mentions)
        trailing = TRAILING_NOUN_RE.match(self.text, end)
        end = trailing.end() if trailing is not None else end
        found = (cue.start(), end)
        if self._in_catalog(found) or any(p.search(self.text, found[0], found[1]) for p in THEME_TERM_RE.values()):
            return None
        return found, sorted({m[2] for m in mentions})

    def scan_focus(self) -> None:
        """Safety net for a sector focus the model gave no code to: the server drafts it from the words alone."""
        for cue in ONLY_CUE_RE.finditer(self.text):
            sentence = _sentence_of(self.text, *cue.span())
            if sentence is None or self._covers(cue.span()):
                continue
            result = self.focus_in((cue.start(), sentence[1]))
            if result is None or self._covers(result[0]):
                continue
            span, sectors = result
            self._covered.append(span)
            self.add_focus(self.text[span[0]:span[1]], sectors, self._objective_id(None, span))

    def scan_themes(self) -> None:
        """Safety net: a theme word the model gave no code to, written right after an 'only', 'avoid' or 'prefer' cue,
        still gets the theme question ("I want only environmental investments"). It can only add a question."""
        for theme, pattern in THEME_TERM_RE.items():
            for match in pattern.finditer(self.text):
                if self._covers(match.span()) or self._in_catalog(match.span()):
                    continue
                sentence = _sentence_of(self.text, *match.span()) or match.span()
                window_start = max(sentence[0], match.start() - CUE_WINDOW)
                before = self.text[window_start:match.start()]
                cue = None
                for polarity, cue_re in (("ONLY", ONLY_CUE_RE), ("AVOID", AVOID_CUE_RE), ("PREFER", PREFER_CUE_RE)):
                    found = list(cue_re.finditer(before))
                    if found:
                        cue = (polarity, window_start + found[-1].start())
                        break
                if cue is None:
                    continue
                end = match.end()
                trailing = TRAILING_NOUN_RE.match(self.text, end)
                if trailing is not None:
                    end = trailing.end()
                span = (cue[1], end)
                self._covered.append(span)
                self.ask("THEME", self.text[span[0]:span[1]], self._objective_id(None, span), theme=theme, polarity=cue[0])

    def add_rules(self, items: list[dict[str, Any]]) -> None:
        asked_exclusions = [c["about_words"] for c in self.clarifications if any(o["option_id"] == "named-companies" for o in c["options"])]
        for item in items:
            words, span = self._words(item.get("words"), "rule")
            rule_type = _code(item.get("rule_type"), RULE_TYPES, "rule_type")
            self._covered.append(span)
            objective_id = self._objective_id(item.get("objective"), span)
            if rule_type == "max_issuer_exposure":
                parameters: dict[str, Any] = {"issuer_scope": "any" if item.get("issuer_id") in (None, "") else self._company(item.get("issuer_id"))}
            elif rule_type == "min_issuer_exposure":
                parameters = {"issuer_id": self._company(item.get("issuer_id"))}
            elif rule_type == "exclusion":
                issuer_ids = item.get("issuer_ids") or []
                if not isinstance(issuer_ids, list):
                    raise _Rejected("issuer_ids_not_a_list")
                issuer_ids = sorted({self._company(issuer_id) for issuer_id in issuer_ids})
                sector = self._sector(item.get("sector"))
                if issuer_ids and sector is not None:
                    raise _Rejected("exclusion_with_two_definitions")
                if self._in_catalog(span) or any(words in asked or asked in words for asked in asked_exclusions):
                    continue  # the question about these words is already asked; no exclusion is proposed outright
                if not issuer_ids:
                    # A sector rule is drafted outright only when the investor wrote that very label. Anything else
                    # ("oil" for Energy) is a guess about meaning, so it becomes a question.
                    if sector is None or sector.lower() not in words.lower():
                        self.ask("EXCLUSION_DEFINITION", words, objective_id, sector=sector)
                        asked_exclusions.append(words)
                        continue
                    parameters = {"definition": {"kind": "fund_reported_sector", "sector": sector}}
                else:
                    parameters = {"definition": {"kind": "named_issuers", "issuer_ids": issuer_ids}}
            elif rule_type == "controversy_exclusion":
                natures = item.get("natures") or list(DEFAULT_NATURES)
                if not isinstance(natures, list):
                    raise _Rejected("natures_not_a_list")
                chosen = {_code(nature, CONTROVERSY_NATURES, "controversy_nature") for nature in natures}
                parameters = {"criteria": {"natures": [n for n in CONTROVERSY_NATURES if n in chosen], "event_date_from": None}}
            else:
                parameters = {"scenario_id": SCENARIO_IDS[0]}

            if rule_type != "controversy_exclusion" and self._in_catalog(span):
                continue  # words about a catalog term are answered by the catalog's question only (after the item was validated)
            sentence = _sentence_of(self.text, *span)
            around = words if sentence is None else self.text[sentence[0]:sentence[1]]
            # Which written company is meant is not left to the model: several companies in the sentence means asking.
            named = set(self.reference.companies_in(around))
            if rule_type == "exclusion" and issuer_ids and len(named) > 1 and named != set(issuer_ids):
                self.ask("EXCLUSION_DEFINITION", words, objective_id)
                continue
            if rule_type in ("max_issuer_exposure", "min_issuer_exposure") and parameters.get("issuer_scope", "") != "any" and len(named) > 1:
                self.unsupported.append({"words": words, "code": _SEVERAL_COMPANIES[0],
                                         "reason": _SEVERAL_COMPANIES[1] + (_CLARIFICATION_SUFFIX if self.clarification_mode else "")})
                continue
            claimed = item.get("threshold_words")
            number_span = span if claimed in (None, "") else _span(self.text, claimed, "threshold")
            number = user_number(self.text, span, number_span, rule_type)
            # "I do not want a limit on any company": a negated limit is never drafted outright ("Not too much ..." has no cue and is).
            refused_wish = (rule_type in _LIMIT_TYPES and negated(around)
                            and (_MAX_CUE_RE.search(around) is not None or _MIN_CUE_RE.search(around) is not None))
            if number is None and (refused_wish or claimed not in (None, "") or _NUMBERISH_RE.search(words)):
                # A number seems intended but cannot be traced literally: no number, and a question instead.
                self.ask(_NUMBER_NEEDED, words, objective_id, pending=(rule_type, parameters))
                continue
            self.rules.append(draft_rule(self._rule_id(rule_type), rule_type, parameters, words, objective_id, number))

    def scan_catalog(self) -> None:
        """Words that are ambiguous whatever the model answers: "oil" always gets the exclusion-definition question, with Energy."""
        seen: set[str] = set()
        for match in _CATALOG_RE.finditer(self.text):
            word = match.group(0)
            if word.lower() in seen:
                continue
            seen.add(word.lower())
            self.ask("EXCLUSION_DEFINITION", word, self._objective_id(None, match.span()))

    def add_unsupported(self, items: list[dict[str, Any]]) -> None:
        seen: set[tuple[str, str]] = set()
        for item in items:
            words, span = self._words(item.get("words"), "unsupported")
            self._covered.append(span)
            reason_code = _code(item.get("reason"), UNSUPPORTED_REASONS, "unsupported_reason")
            if reason_code in _FOCUS_MISFILED:
                focus = self.focus_in(span)
                if focus is not None:  # "only tech stocks" filed as a sector limit: it is a focus the rules can check
                    self._covered.append(focus[0])
                    self.add_focus(self.text[focus[0][0]:focus[0][1]], focus[1], self._objective_id(None, focus[0]))
                    continue
            code, reason = UNSUPPORTED_REASONS[reason_code]
            if (words, code) in seen:
                continue
            seen.add((words, code))
            self.unsupported.append({"words": words, "code": code, "reason": reason + (_CLARIFICATION_SUFFIX if self.clarification_mode else "")})


def build_interpretation(extraction: dict[str, Any], *, text: str, persona_id: str, reference: _Reference, companies: list[str],
                         interpretation_id: str, created_at: str, model_id: str | None, clarification_mode: bool = False) -> dict[str, Any]:
    """The contract document for one extraction. Raises ``_Rejected`` when the extraction cannot be used."""
    lists = {name: _items(extraction, name) for name in ("objectives", "rules", "ambiguous", "unsupported")}
    builder = _Builder(text, reference, companies, clarification_mode)
    builder.add_objectives(lists["objectives"])
    builder.scan_catalog()  # first: the server's catalog wins over anything the model says about the same words
    builder.add_ambiguous(lists["ambiguous"])
    builder.add_rules(lists["rules"])
    builder.add_unsupported(lists["unsupported"])
    builder.scan_focus()  # last two: only fill what the model left without a code
    builder.scan_themes()
    return {
        "schema_version": SCHEMA_VERSION, "interpretation_id": interpretation_id, "persona_id": persona_id, "created_at": created_at,
        "model_id": model_id, "original_words": text, "objectives": builder.objectives, "proposed_rules": builder.rules,
        "unsupported": builder.unsupported, "clarifications": builder.clarifications,
    }


# --------------------------------------------------------------------------
# The interpreter
# --------------------------------------------------------------------------


class Interpreter:
    """``model`` is a ``BedrockConverse`` (or anything with its ``converse`` signature and ``model_id``).

    The interpreter is a small bounded agent. In one attempt the model may first call read-only lookup tools
    (``find_companies``, ``describe_sector``) that the server answers from the data snapshot, then submits its
    extraction with ``submit_interpretation``. Bounds: ``max_outputs`` submissions (an unusable one starts one fresh
    attempt with a retry note), ``max_lookup_rounds`` lookup turns in total, at most ``MAX_LOOKUPS_PER_ROUND`` tool
    calls per turn, and a model call is started only when ``call_budget_seconds`` remain before the deadline.
    """

    def __init__(self, model: Any, clock: Any, *, new_id: Callable[[], str] | None = None, max_tokens: int = 2048,
                 budget_seconds: float = float(INTERPRET_TIMEOUT_SECONDS), call_budget_seconds: float = 13.0, max_outputs: int = 2,
                 max_lookup_rounds: int = 2) -> None:
        self._model = model
        self._clock = clock
        self._new_id = new_id or (lambda: uuid.uuid4().hex)
        self._max_tokens = max_tokens
        self._budget = budget_seconds
        self._call_budget = call_budget_seconds  # the longest one model call can take (connect + read timeout)
        self._max_outputs = max_outputs
        self._max_lookup_rounds = max_lookup_rounds
        self._references: dict[str, _Reference] = {}

    def _reference(self, snapshot: Any) -> _Reference:
        reference = self._references.get(snapshot.snapshot_id)
        if reference is None:
            self._references.clear()
            reference = self._references[snapshot.snapshot_id] = _Reference(snapshot)
        return reference

    @staticmethod
    def _reference_data(reference: _Reference, companies: list[str]) -> dict[str, Any]:
        return {"sector_labels": reference.sectors,
                "companies": [{"issuer_id": issuer_id, "name": reference.display.get(issuer_id, issuer_id)} for issuer_id in companies]}

    def _lookup(self, use: dict[str, Any], text: str, reference: _Reference, found: list[str], allowed: bool) -> dict[str, Any]:
        """Run one lookup tool call. The answer is data from the snapshot; ids it returns become usable in the submission."""
        tool_use_id = use.get("toolUseId")

        def error(code: str) -> dict[str, Any]:
            return {"toolResult": {"toolUseId": tool_use_id, "status": "error", "content": [{"text": f"Lookup not completed ({code})."}]}}

        if not allowed:
            return error("no_lookups_left_submit_now")
        arguments = use.get("input")
        if use.get("name") == FIND_COMPANIES_TOOL_NAME:
            if not isinstance(arguments, dict) or schema_errors(arguments, FIND_COMPANIES_SCHEMA):
                return error("invalid_arguments")
            try:
                start, end = _span(text, arguments["words"], "lookup")
            except _Rejected:
                return error("words_not_in_the_investors_text")
            matches = reference.find(text[start:end])
            for issuer_id in matches:
                if issuer_id not in found:
                    found.append(issuer_id)
            result: dict[str, Any] = {"matches": [reference.describe(issuer_id) for issuer_id in matches]}
        else:
            sector = arguments.get("sector") if isinstance(arguments, dict) else None
            if not isinstance(sector, str) or sector not in reference.sectors:
                return error("unknown_sector")
            result = {"sector": sector, "example_companies": reference.sector_members(sector)}
        return {"toolResult": {"toolUseId": tool_use_id, "status": "success", "content": [{"json": result}]}}

    def interpret(self, *, text: str, persona_id: str, snapshot: Any, started: float | None = None, clarification_mode: bool = False) -> dict[str, Any]:
        started = self._clock.time() if started is None else started
        deadline = started + self._budget
        reference = self._reference(snapshot)
        companies = reference.companies_in(text)
        found: list[str] = []  # companies the lookup tool resolved from the investor's words
        interpretation_id = f"int-{self._new_id()[:12]}"
        rejected = None
        calls = 0
        lookup_rounds = 0
        lookup_tools = {FIND_COMPANIES_TOOL_NAME, DESCRIBE_SECTOR_TOOL_NAME}
        for attempt in range(1, self._max_outputs + 1):
            allowed = sorted(set(companies) | set(found))[:MAX_COMPANY_CANDIDATES]
            messages: list[dict[str, Any]] = [{"role": "user", "content": [
                {"text": build_interpreter_message(text, self._reference_data(reference, allowed), retry=attempt > 1)}]}]
            while True:
                if deadline - self._clock.time() < self._call_budget:
                    if rejected is None:
                        self._done("timeout", interpretation_id, text, calls, lookup_rounds=lookup_rounds)
                        raise InterpreterTimeout()
                    break  # an answer was received and rejected; there is no time for the retry
                allowed = sorted(set(companies) | set(found))[:MAX_COMPANY_CANDIDATES]
                try:
                    calls += 1
                    response, record = self._model.converse(system=INTERPRETER_SYSTEM_PROMPT, messages=messages,
                                                            tool_config=tool_config(reference.sectors, allowed),
                                                            max_tokens=self._max_tokens, deadline=deadline)
                except ModelCallError as error:
                    out_of_time = error.code == FAILURE_DEADLINE_EXCEEDED or deadline - self._clock.time() < self._call_budget
                    self._done("timeout" if out_of_time else "model_error", interpretation_id, text, calls, aws_error=error.aws_error)
                    if out_of_time:
                        raise InterpreterTimeout() from error
                    raise InterpreterFailed("model_error") from error
                if self._clock.time() > deadline:
                    self._done("timeout", interpretation_id, text, calls)
                    raise InterpreterTimeout()
                message = (response.get("output") or {}).get("message") or {}
                content = [block for block in (message.get("content") or []) if isinstance(block, dict)]
                uses = [block["toolUse"] for block in content if isinstance(block.get("toolUse"), dict)]
                submitted = any(use.get("name") == INTERPRETER_TOOL_NAME for use in uses)
                if uses and not submitted and response.get("stopReason") == "tool_use":
                    if any(use.get("name") not in lookup_tools for use in uses) or len(uses) > MAX_LOOKUPS_PER_ROUND:
                        rejected = "unknown_tool_or_too_many_lookups"
                        log.warning("interpreter_output_rejected", interpretation_id=interpretation_id, attempt=attempt, reason=rejected)
                        break
                    lookup_rounds += 1
                    if lookup_rounds > self._max_lookup_rounds + 1:
                        rejected = "lookup_rounds_exceeded"  # it was told to submit and asked again
                        log.warning("interpreter_output_rejected", interpretation_id=interpretation_id, attempt=attempt, reason=rejected)
                        break
                    more = lookup_rounds <= self._max_lookup_rounds
                    results = [self._lookup(use, text, reference, found, more) for use in uses]
                    if not more:
                        results.append({"text": INTERPRETER_LOOKUP_DONE_NOTE})
                    messages += [{"role": "assistant", "content": content}, {"role": "user", "content": results}]
                    log.info("interpreter_lookup", interpretation_id=interpretation_id, round=lookup_rounds, calls=len(uses), answered=more)
                    continue
                try:
                    draft = build_interpretation(
                        _extraction(response), text=text, persona_id=persona_id, reference=reference,
                        companies=sorted(set(companies) | set(found)), interpretation_id=interpretation_id,
                        created_at=to_iso(self._clock.time()), model_id=getattr(self._model, "model_id", None),
                        clarification_mode=clarification_mode)
                    if interpretation_errors(draft):
                        raise _Rejected("draft_fails_contract_validation")
                except _Rejected as error:
                    rejected = error.reason
                    log.warning("interpreter_output_rejected", interpretation_id=interpretation_id, attempt=attempt, reason=rejected,
                                stop_reason=record.get("stop_reason"), usage=record.get("usage"))
                    break
                self._done("ok", interpretation_id, text, calls, usage=record.get("usage"), wall_ms=record.get("wall_ms"),
                           lookup_rounds=lookup_rounds, objectives=len(draft["objectives"]), proposed_rules=len(draft["proposed_rules"]),
                           clarifications=len(draft["clarifications"]), unsupported=len(draft["unsupported"]))
                return draft
            if deadline - self._clock.time() < self._call_budget:
                break
        self._done("rejected", interpretation_id, text, calls, reason=rejected)
        raise InterpreterFailed(rejected or "rejected")

    @staticmethod
    def _done(outcome: str, interpretation_id: str, text: str, attempts: int, **fields: Any) -> None:
        # Lengths, ids and the outcome only: never the investor's text and never the model's answer.
        log.info("interpreter_finished", outcome=outcome, interpretation_id=interpretation_id, text_chars=len(text), attempts=attempts,
                 prompt_version=INTERPRETER_PROMPT_VERSION, **fields)
