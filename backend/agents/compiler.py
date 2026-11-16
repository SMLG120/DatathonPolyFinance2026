"""The deterministic compiler: a checked reading -> a DRAFT interpretation (standard library only).

The model's reading (``backend.agents.reading``) says what each clause of the investor's text *is*: an intent, a
subject, a direction, spans for the amount and the subject, a confidence. This module decides what each clause
*becomes*, and every decision can only move a clause DOWN this lattice:

    RULE_WITH_NUMBER > RULE_NO_NUMBER > QUESTION > UNSUPPORTED > NOTHING

Nothing the model says can raise an outcome. A number is taken only from the investor's characters
(``quantity.parse`` over the model's ``quantity_mention``), only when the form is a plain percentage, the clause is
read with HIGH confidence and no ambiguity, the direction words agree, every digit in the clause is accounted for,
the subject, direction and amount sit in one sentence, and no instruction to the system overlaps the clause.
Company ids are kept only when the investor's words (or a lookup on them) name that company; sector labels only when
the label or an everyday word for it is written. Two rules that cannot both hold are never both drafted.

Stages, in order (the letters are those of the plan's compile rules):

* A. field filter: only the fields that fit the clause's subject kind are read;
* B. grounding of company ids and sector labels on the investor's words;
* C/D/I. ``_decide``: the amount, its ownership, the same-sentence check, the hedge and direction vetoes and the
  confidence lattice, giving a number or the reason no number is taken;
* E/F. polarity and the ``MAPPING`` table from ``(intent, subject_kind, direction)`` to a builder;
* G. corrections (``supersedes``), exceptions (``exception_of``) and ellipses (``quantity_from``);
* H. conflicts (``backend.agents.conflicts``);
* J. the catalog ("oil" always gets the server's question, or the EXCEPTION question that replaces it) and the theme
  and focus safety nets;
* K. dedup (the Renderer dedups questions and unsupported entries; rules here).

Every sentence comes from ``backend.agents.render``; every rule is drafted by ``draft_rule`` (PROPOSED).
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field, replace
from typing import Any

from byb_contracts.constants import CONTROVERSY_NATURES, SCENARIO_IDS

from backend.agents import quantity
from backend.agents.conflicts import EACH, LOSS, Candidate, find_conflicts, rule_subject
from backend.agents.reading import Clause, Reading, Span
from backend.agents.reference import _Reference
from backend.agents.render import DEFAULT_NATURES, NUMBER_NEEDED, Draft, Renderer, verbatim_slice
from backend.agents.themes import (
    AVOID_CUE_RE,
    CATALOG_RE,
    COMPARATIVE_NEGATION_RE,
    COMPARATIVE_VETO,
    CUE_WINDOW,
    DIRECTION_VETO,
    EACH_WORDS,
    INJECTION_RE,
    ONLY_CUE_RE,
    PREFER_CUE_RE,
    RESTRICTIVE_WORDS,
    THEME_TERM_RE,
    TRAILING_NOUN_RE,
    sector_mentions,
    sectors_written_in,
)

MAX_FOCUS_SECTORS = 4  # sectors one "only ..." wish may keep
MAX_FOCUS_RULES = 14  # exclusions one "only ..." wish may draft (one per other sector label)
MAX_WHICH_CANDIDATES = 5

# --------------------------------------------------------------------------- the mapping table (F)

# (intent, subject_kind, direction) -> builder. '*' matches anything. Lookup order: the exact key, then
# (intent, subject, '*'), then (intent, '*', direction), then (intent, '*', '*'); every intent has a last row, so every
# combination has exactly one outcome (tested). A direction no row expects is DIRECTION_UNCLEAR.
_OWN_SUBJECT_EXCLUSIONS = {"NAMED_COMPANIES": "exclude_named", "SECTOR": "exclude_sector", "CONTROVERSY": "exclude_controversy"}
_SOFT_INTENTS = ("LIMIT", "EXCLUDE", "KEEP_ONLY", "HOLD", "CAUTION", "PREFERENCE", "GOAL")
MAPPING: dict[tuple[str, str, str], str] = {
    # LIMIT
    ("LIMIT", "EACH_COMPANY", "AT_MOST"): "cap_each",
    ("LIMIT", "EACH_COMPANY", "AT_LEAST"): "not_measurable",
    ("LIMIT", "EACH_COMPANY", "NONE_AT_ALL"): "not_measurable",
    ("LIMIT", "EACH_COMPANY", "UNSPECIFIED"): "diversification",
    ("LIMIT", "EACH_COMPANY", "BETWEEN"): "range_question",
    ("LIMIT", "EACH_COMPANY", "*"): "direction_unclear",
    ("LIMIT", "NAMED_COMPANIES", "AT_MOST"): "cap_named",
    ("LIMIT", "NAMED_COMPANIES", "AT_LEAST"): "min_named",
    ("LIMIT", "NAMED_COMPANIES", "NONE_AT_ALL"): "exclude_named",
    ("LIMIT", "NAMED_COMPANIES", "BETWEEN"): "range_question",
    ("LIMIT", "NAMED_COMPANIES", "*"): "company_intent",
    ("LIMIT", "SECTOR", "NONE_AT_ALL"): "exclude_sector",
    ("LIMIT", "SECTOR", "*"): "sector_limit",
    ("LIMIT", "PORTFOLIO_LOSS", "AT_MOST"): "loss",
    ("LIMIT", "PORTFOLIO_LOSS", "UNSPECIFIED"): "loss_question",
    ("LIMIT", "PORTFOLIO_LOSS", "NONE_AT_ALL"): "loss_question",
    ("LIMIT", "PORTFOLIO_LOSS", "BETWEEN"): "range_question",
    ("LIMIT", "PORTFOLIO_LOSS", "*"): "direction_unclear",
    ("LIMIT", "CONTROVERSY", "AT_MOST"): "controversy_cap",
    ("LIMIT", "CONTROVERSY", "NONE_AT_ALL"): "exclude_controversy",
    # "Limit my exposure to controversial companies" says neither a ban nor an amount: asked, never drafted as a ban
    ("LIMIT", "CONTROVERSY", "UNSPECIFIED"): "controversy_question",
    ("LIMIT", "CONTROVERSY", "BETWEEN"): "range_question",
    ("LIMIT", "CONTROVERSY", "*"): "direction_unclear",
    ("LIMIT", "ACTIVITY", "NONE_AT_ALL"): "exclude_activity",
    ("LIMIT", "ACTIVITY", "UNSPECIFIED"): "exclude_activity",
    ("LIMIT", "ACTIVITY", "*"): "sector_limit",
    ("LIMIT", "WHOLE_PORTFOLIO", "AT_MOST"): "scope_needed",
    ("LIMIT", "UNCLEAR", "AT_MOST"): "scope_needed",
    ("LIMIT", "*", "*"): "not_measurable",
    # EXCLUDE: AT_MOST, NONE_AT_ALL and UNSPECIFIED are exclusions (an amount on them is checked by the builder)
    **{("EXCLUDE", subject, direction): builder for subject, builder in _OWN_SUBJECT_EXCLUSIONS.items()
       for direction in ("AT_MOST", "NONE_AT_ALL", "UNSPECIFIED")},
    ("EXCLUDE", "CONTROVERSY", "AT_MOST"): "controversy_cap",
    **{("EXCLUDE", subject, "*"): "direction_unclear" for subject in _OWN_SUBJECT_EXCLUSIONS},
    ("EXCLUDE", "ACTIVITY", "*"): "exclude_activity",
    # "I don't want railways": something is to be left out but what is unclear; asking what it covers (with no
    # sector guessed) says more than "not measurable"
    ("EXCLUDE", "UNCLEAR", "*"): "exclude_activity",
    ("EXCLUDE", "*", "*"): "not_measurable",
    # KEEP_ONLY
    ("KEEP_ONLY", "SECTOR", "*"): "keep_only",
    ("KEEP_ONLY", "*", "*"): "not_measurable",
    # HOLD and CAUTION
    ("HOLD", "NAMED_COMPANIES", "AT_LEAST"): "min_named",
    ("HOLD", "NAMED_COMPANIES", "*"): "company_intent",
    ("HOLD", "*", "*"): "not_measurable",
    ("CAUTION", "NAMED_COMPANIES", "*"): "company_intent",
    ("CAUTION", "EACH_COMPANY", "*"): "diversification",
    ("CAUTION", "PORTFOLIO_LOSS", "*"): "loss_question",
    ("CAUTION", "CONTROVERSY", "*"): "controversy_question",
    ("CAUTION", "*", "*"): "not_measurable",
    # Wishes that draft nothing by themselves
    ("PERMISSION", "*", "*"): "not_measurable",
    ("PREFERENCE", "EACH_COMPANY", "*"): "diversification",
    ("PREFERENCE", "PORTFOLIO_LOSS", "*"): "loss_question",
    ("PREFERENCE", "SECTOR", "*"): "focus_not_only",
    ("PREFERENCE", "*", "*"): "soft",
    ("GOAL", "EACH_COMPANY", "*"): "diversification",
    ("GOAL", "PORTFOLIO_LOSS", "*"): "loss_question",
    ("GOAL", "*", "*"): "soft",
    ("OUT_OF_SCOPE_ASK", "*", "*"): "out_of_scope",
    ("INSTRUCTION_TO_SYSTEM", "*", "*"): "instruction",
    ("OTHER", "*", "*"): "other",
    # A values-based theme is a question whatever the intent around it
    **{(intent, "THEME", "*"): "theme" for intent in _SOFT_INTENTS},
}


def route(intent: str, subject_kind: str, direction: str) -> str:
    """The builder of one clause (see ``MAPPING``)."""
    for key in ((intent, subject_kind, direction), (intent, subject_kind, "*"), (intent, "*", direction), (intent, "*", "*")):
        if key in MAPPING:
            return MAPPING[key]
    raise KeyError((intent, subject_kind, direction))


# --------------------------------------------------------------------------- small helpers

_SUBJECT_FIELDS = {"NAMED_COMPANIES": ("company_ids", "unresolved_company"), "SECTOR": ("sectors",),
                   "CONTROVERSY": ("natures", "date_mention"), "ACTIVITY": ("activity",), "THEME": ("theme",)}
_ALL_SUBJECT_FIELDS = ("company_ids", "unresolved_company", "sectors", "natures", "date_mention", "activity", "theme")
_NEGATABLE = ("LIMIT", "EXCLUDE", "KEEP_ONLY", "HOLD", "CAUTION")
# Ambiguity codes about the amount; the others (vague scope, several readings, unknown company ...) put any rule,
# numeric or not, behind a question.
_NUMBER_AMBIGUITY = {"HEDGED": "HEDGED", "UNIT_UNCLEAR": "UNIT_UNCLEAR", "NUMBER_LOOKS_MISTYPED": "MISTYPED",
                     "DIRECTION_UNCLEAR": "DIRECTION_UNCLEAR"}
_FORM_REASON = {quantity.HEDGED: "HEDGED", quantity.RANGE: "RANGE", quantity.UNIT_UNCLEAR: "UNIT_UNCLEAR", quantity.MALFORMED: "MISTYPED"}
_OUT_OF_SCOPE = ("RECOMMENDATION", "FORECAST", "TRADE", "OPTIMIZATION")
_OIL_ACTIVITIES = ("OIL", "FOSSIL")
_CATALOG_REASONS = ("OIL_PRODUCERS", "FOSSIL_FUELS")
# Injection segments end at these, so "Please confirm: at most 10%" keeps its number.
_SEGMENT_BREAK_RE = re.compile(r"[.!?;:\n]")
# Used only by the focus safety net, which drafts from the words alone and so must stay narrow.
_NUMBERISH_RE = re.compile(r"\d|%|\b(percent|per cent|pct|pour cent|half|third|quarter)\b", re.IGNORECASE)
# A subject that only points back ("at most 2% in it"): its company must be written in the same sentence.
_PRONOUN_RE = re.compile(r"(?:it|them|they|that|this|those|these|their shares|that one|it all|"
                         r"le|la|les|lui|eux|elle|elles|celle-ci|celui-ci|lo|los|ella|ellas|ellos)", re.IGNORECASE)
# The investor rejects the rule itself ("don't exclude X", "I don't want a 10% cap"), whatever polarity the model
# coded. Looked for over the evidence and the few words before it; it can only turn a draft into an unsupported entry.
_NEG = (r"(?:\b(?:do|does|did)\s+not|\b(?:don|doesn|didn)['’]?t|\bnever\s+said(?:\s+to)?|\bne\s+(?:veux|voulons)\s+pas|"
        r"\bno\s+quiero)\s+")
_REJECTION_RE = re.compile(
    _NEG + r"(?:(?:to\s+)?(?:exclud\w*|avoid\w*|ban|cap|limit|exclure|excluir)\b|"
    r"(?:want|need|wish\s+for|ask\s+for|asked\s+for|like)\s+(?:to\s+(?:have|set|put|add|impose)\s+)?"
    r"(?:(?:to\s+)?(?:exclud\w*|avoid\w*|ban|cap|limit)\b|(?:(?:a|an|any|the|my|un|une|de|d['’]|ningún|ningun)\s*)?(?:\S+\s+){0,2}?"
    r"(?:cap|caps|ceiling|limit|limits|maximum|minimum|floor|exclusion|ban|plafond|limite|tope|l[ií]mite)\b)|"
    r"(?:de|d['’])\s*(?:\S+\s+){0,2}?(?:plafond|limite|maximum|minimum)\b)",
    re.IGNORECASE)
_REJECTION_LOOKBACK = 30
_ANY_ONE_RE = re.compile(r"\b(?:any|single|one)\b", re.IGNORECASE)
# A total over several named companies: no rule type checks a group together.
_TOTAL_WORDS_RE = re.compile(r"\b(?:combined|together|in\s+total|total|altogether|overall|collectively|between\s+them|"
                             r"ensemble|au\s+total|en\s+tout|en\s+total|juntos|juntas|en\s+conjunto|zusammen|insgesamt)\b", re.IGNORECASE)
# Words that say a subject-less amount is about the portfolio itself ("no more than 10% overall").
_PORTFOLIO_WORDS_RE = re.compile(r"\b(?:portfolio|portefeuille|cartera|depot|everything|overall|anything|any|all)\b", re.IGNORECASE)
_NEGATION_RE = re.compile(r"\b(not|no|never|without|neither|nor|none|cannot|ne|pas|jamais|sans)\b|n['’]t\b", re.IGNORECASE)


def _overlaps(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return a[0] < b[1] and b[0] < a[1]


def _inside(span: tuple[int, int], outer: tuple[int, int]) -> bool:
    return outer[0] <= span[0] and span[1] <= outer[1]


def _offsets(span: Span) -> tuple[int, int]:
    return span[1], span[2]


def _key(rule_type: str, parameters: dict[str, Any]) -> str:
    """A measure, comparable across clauses (company ids are already sorted wherever they are a set)."""
    return rule_type + json.dumps(parameters, sort_keys=True)


def _named(ids: list[str]) -> dict[str, Any]:
    return {"definition": {"kind": "named_issuers", "issuer_ids": sorted(ids)}}


def _sector(label: str) -> dict[str, Any]:
    return {"definition": {"kind": "fund_reported_sector", "sector": label}}


def _excluded_sector_of(draft: Draft) -> str | None:
    """The sector label a draft leaves out, or None."""
    definition = draft.parameters.get("definition") or {}
    return definition.get("sector") if draft.rule_type == "exclusion" and definition.get("kind") == "fund_reported_sector" else None


def _controversy(natures: list[str], event_date_from: str | None) -> dict[str, Any]:
    chosen = [n for n in CONTROVERSY_NATURES if n in natures] or list(DEFAULT_NATURES)
    return {"criteria": {"natures": chosen, "event_date_from": event_date_from}}


_LOSS = ("scenario_loss_budget", {"scenario_id": SCENARIO_IDS[0]})
_CAP_ANY = ("max_issuer_exposure", {"issuer_scope": "any"})


@dataclass(frozen=True)
class _Decision:
    """What the clause's amount allows: ``number`` (USER_WORDS), nothing (``reason`` None: a numberless draft), or a
    question with ``reason``; ``offer`` is a value computed from the investor's words that a question may pre-fill."""

    number: tuple[float, str] | None = None
    reason: str | None = None
    offer: tuple[float, str] | None = None


@dataclass
class _Outcome:
    """What one clause compiles to, before structure and conflicts may still lower it."""

    clause: Clause
    objective_id: str | None
    drafts: list[Draft] = field(default_factory=list)  # direct rules (Draft.words = their original_words)
    asks: list[tuple[str, str, dict[str, Any]]] = field(default_factory=list)  # (topic, about_words, details)
    unsupported: list[tuple[str, str]] = field(default_factory=list)  # (words, reason code)
    measures: list[Draft] = field(default_factory=list)  # what the clause would draft, with its number if allowed
    permission: str | frozenset[str] | None = None  # a PERMISSION clause's subject, for the conflict check

    def clear(self) -> None:
        self.drafts, self.asks, self.unsupported = [], [], []


# --------------------------------------------------------------------------- the compiler


class _Compiler:
    def __init__(self, reading: Reading, text: str, reference: _Reference, lookups: dict[str, list[str]],
                 clarification_mode: bool, downgrades: Counter) -> None:
        self.reading = reading
        self.text = text
        self.reference = reference
        self.lookups = lookups
        self.clarification_mode = clarification_mode
        self.downgrades = downgrades
        self.out = Renderer(reference.sectors, clarification_mode, names=reference.display)
        self.sentences = quantity.sentence_spans(text)
        self.catalog = [m.span() for m in CATALOG_RE.finditer(text)]
        self.clauses = sorted(reading.clauses, key=lambda c: (c.start, c.end))
        self.by_id = {c.id: c for c in self.clauses if not c.problems}
        self.instructions = [_offsets(c.evidence) for c in self.by_id.values() if c.intent == "INSTRUCTION_TO_SYSTEM"]
        self.injection = self._injection_segments()
        self.objective_ids: dict[int, str] = {}
        self.ids = set(reference.ids)
        self.unhonoured: list[tuple[str, str, str]] = []  # corrections G could not honour: conflicts for H
        self.excepted_catalog: list[tuple[int, int]] = []  # catalog spans whose question an EXCEPTION question replaces
        self.honoured: set[tuple[str, str]] = set()

    # -- entry

    def run(self) -> Renderer:
        self._objectives()
        outcomes = [self._compile(c) for c in self.clauses]
        self._structure(outcomes)
        self._conflicts(outcomes)
        self._drop_redundant_diversification(outcomes)
        # Before every clause's output: the server's catalog question comes first, whatever the model said about the
        # same words. (Compiling drafts nothing yet, so rule and question ids follow this order.)
        self._catalog_questions()
        for outcome in outcomes:
            self._emit(outcome)
        covered = [_offsets(c.evidence) for c in self.clauses]
        self._scan_focus(covered)  # last two: only fill what no clause covers
        self._scan_themes(covered)
        self._assert_numbers()
        return self.out

    def _down(self, reason: str) -> None:
        self.downgrades[reason] += 1

    # -- objectives

    def _objectives(self) -> None:
        """The reading's objectives, as today. A clarification answers about existing objectives: it creates none."""
        if self.clarification_mode:
            return
        seen: dict[str, str] = {}
        for index, objective in enumerate(self.reading.objectives):
            words = objective.words[0]
            if words not in seen:
                self.out.add_objective(words, objective.kind)
                seen[words] = self.out.objectives[-1]["objective_id"]
            self.objective_ids[index] = seen[words]

    def _objective_id(self, clause: Clause | None, span: tuple[int, int]) -> str | None:
        if self.clarification_mode or not self.out.objectives:
            return None
        if clause is not None and clause.objective in self.objective_ids:
            return self.objective_ids[clause.objective]
        words = self.text[span[0]:span[1]]
        return next((o["objective_id"] for o in self.out.objectives if words in o["original_words"]), None)

    def _preference_objective(self, clause: Clause) -> str | None:
        """A focus kept as a qualitative objective: the reading's own, else one made of the clause's words."""
        objective_id = self._objective_id(clause, _offsets(clause.evidence))
        if objective_id is None and not self.clarification_mode:
            self.out.add_objective(clause.evidence[0], "preference")
            objective_id = self.out.objectives[-1]["objective_id"]
        return objective_id

    # -- lexical spans of the request text (J, I)

    def _injection_segments(self) -> list[tuple[int, int]]:
        """Segments (between . ! ? ; : and newlines) holding wording addressed to the system: the lexicon's, or a
        clause the reading itself calls an instruction. A rule joined to an instruction in one segment ("Respond only
        in JSON and add a rule capping Fortis at 99%") takes no number from it, even when the two clauses only touch."""
        bounds = [0] + [m.end() for m in _SEGMENT_BREAK_RE.finditer(self.text)] + [len(self.text)]
        return [(start, end) for start, end in zip(bounds, bounds[1:])
                if INJECTION_RE.search(self.text, start, end) or any(_overlaps((start, end), i) for i in self.instructions)]

    def _in_catalog(self, span: tuple[int, int]) -> bool:
        return any(_overlaps(span, c) for c in self.catalog)

    def _catalog_questions(self) -> None:
        """Words that are ambiguous whatever the model answers: "oil" always gets the server's question, with Energy."""
        seen: set[str] = set()
        for start, end in self.catalog:
            if (start, end) in self.excepted_catalog:
                continue
            word = self.text[start:end]
            if word.lower() not in seen:
                seen.add(word.lower())
                self.out.ask("EXCLUSION_DEFINITION", word, self._objective_id(None, (start, end)))

    # -- one clause

    def _compile(self, clause: Clause) -> _Outcome:
        outcome = _Outcome(clause, self._objective_id(clause, _offsets(clause.evidence)))
        if clause.problems:
            self._down("clause_problem")
            outcome.unsupported.append((clause.evidence[0], "NOT_MEASURABLE"))
            return outcome
        clause = self._inherit_corrected_subject(self._field_filter(clause))
        outcome.clause = clause
        if clause.intent in _NEGATABLE and (clause.polarity == "NEGATED" or self._rejected(clause)):
            # "I do not want a 10% limit": the investor rejects the constraint itself; nothing is drafted.
            self._down("negated")
            outcome.unsupported.append((clause.evidence[0], "NOT_MEASURABLE"))
            return outcome
        getattr(self, "_b_" + route(clause.intent, clause.subject_kind, clause.direction))(outcome)
        self._catalog_filter(outcome)
        return outcome

    def _inherit_corrected_subject(self, clause: Clause) -> Clause:
        """G. 'cap Fortis at 5%, sorry, I meant 15%': a correction that writes no subject of its own keeps the subject
        of the earlier clause it corrects (same subject kind, no ids or labels of its own). The ids are still grounded,
        on the earlier clause's words (``_grounding_texts``)."""
        earlier = self.by_id.get(clause.supersedes or "")
        if (earlier is None or earlier.start >= clause.start or clause.subject_mention is not None
                or clause.subject_kind != earlier.subject_kind or clause.company_ids or clause.sectors):
            return clause
        if earlier.company_ids or earlier.sectors:
            self._down("correction_keeps_subject")
            return replace(clause, company_ids=list(earlier.company_ids), sectors=list(earlier.sectors))
        return clause

    def _field_filter(self, clause: Clause) -> Clause:
        """A. Only the fields that fit the subject kind are read; the others are logged and cleared."""
        allowed = _SUBJECT_FIELDS.get(clause.subject_kind, ())
        cleared = {}
        for name in _ALL_SUBJECT_FIELDS:
            if name not in allowed and getattr(clause, name):
                self._down("ignored_field")
                cleared[name] = [] if isinstance(getattr(clause, name), list) else None
        return replace(clause, **cleared) if cleared else clause

    def _catalog_filter(self, outcome: _Outcome) -> None:
        """J. A clause about a catalog word ("no oil companies", or "avoid oil" misread as a cap or a loss budget) is
        answered by the catalog's question only, whatever subject kind the model gave it. A controversy rule keeps its
        draft, and so does a named company whose own mention avoids the word ("Exxon Mobil, the oil giant ...").

        The model's own "no sourced oil-producer data" entry repeats the question's unsupported options, so it is
        dropped, except in a clarification: there the investor is answering what they meant, and that entry is the
        answer (fixtures/api/challenge_clarify_preference.json)."""
        clause = outcome.clause
        if clause.subject_kind != "CONTROVERSY" and self._about_catalog(clause):
            if outcome.drafts or outcome.asks:
                self._down("catalog_suppressed")
            outcome.drafts, outcome.asks = [], []
        if not self.clarification_mode:
            outcome.unsupported = [(words, code) for words, code in outcome.unsupported
                                   if not (code in _CATALOG_REASONS and self._in_catalog(_offsets(clause.evidence)))]

    def _about_catalog(self, clause: Clause) -> bool:
        """The clause's subject is a catalog word. With no subject marked, the evidence counts, except for catalog
        words another clause is about ("At most 10% per company and no oil" with "no oil" its own clause keeps the cap)."""
        if clause.subject_mention is not None:
            return self._in_catalog(_offsets(clause.subject_mention))
        evidence = _offsets(clause.evidence)
        others = [_offsets(o.evidence) for o in self.by_id.values() if o.id != clause.id and o.subject_kind == "ACTIVITY"
                  and not _inside(evidence, _offsets(o.evidence))]
        return any(_overlaps(evidence, c) and not any(_inside(c, other) for other in others) for c in self.catalog)

    # -- B. grounding

    def _grounded_ids(self, clause: Clause) -> list[str]:
        """Model ids that the investor's words name: a server match on the subject (else the evidence) or a lookup
        made on words written there. An id for another company of the sentence is dropped. A lookup counts only when
        its words stand as whole words ("royal" is not in "royalty") and it found exactly one company: several
        candidates mean the words do not pick one, so the investor is asked."""
        named: set[str] = set()
        for words in self._grounding_texts(clause):
            named |= set(self.reference.find(words)) | set(self.reference.companies_in(words))
            for looked_up, ids in self.lookups.items():
                if len(ids) == 1 and looked_up.strip() and re.search(
                        rf"(?<!\w){re.escape(looked_up.strip())}(?!\w)", words, re.IGNORECASE):
                    named.update(ids)
        grounded = sorted({i for i in clause.company_ids if i in named and i in self.ids})
        if set(clause.company_ids) - set(grounded):
            self._down("ungrounded_company")
        return grounded

    def _grounding_texts(self, clause: Clause) -> list[str]:
        """The clause's own grounding words, plus, for a correction that writes no subject of its own ("cap Fortis at
        5%, sorry, I meant 15%"), the subject of the earlier clause it corrects: the correction is about that subject."""
        texts = [self._grounding_words(clause)]
        earlier = self.by_id.get(clause.supersedes or "")
        own = clause.subject_mention
        if earlier is not None and earlier.start < clause.start and own is None:
            texts.append(self._grounding_words(earlier))
        return texts

    def _grounding_words(self, clause: Clause) -> str:
        """The words a clause's company ids must be named in: its subject, else its evidence. A pronoun subject ("Since
        I work at Royal Bank of Canada ..., I want at most 2% in it") stands for a company written in the same
        sentence, so that sentence is used; a company named only in another sentence is still not grounded."""
        subject = clause.subject_mention
        if subject is not None and _PRONOUN_RE.fullmatch(subject[0].strip()):
            sentence = self._sentence_of(_offsets(clause.evidence)) or _offsets(clause.evidence)
            return self.text[sentence[0]:sentence[1]]
        return (subject or clause.evidence)[0]

    def _companies(self, outcome: _Outcome, rule_type: str, parameters_for) -> list[str]:
        """The clause's grounded ids. With none, the investor is asked which company (or told none matches)."""
        clause = outcome.clause
        ids = self._grounded_ids(clause)
        words = (clause.subject_mention or clause.evidence)[0]
        if clause.unresolved_company is not None:
            outcome.unsupported.append((clause.unresolved_company[0], "COMPANY_NOT_IN_DATA"))
        if ids:
            return ids
        candidates = self.reference.find(words)
        if clause.unresolved_company is None and candidates:
            outcome.asks.append(("COMPANY_WHICH", clause.evidence[0], {
                "candidates": candidates[:MAX_WHICH_CANDIDATES], "rule_type": rule_type, "parameters_builder": parameters_for}))
        elif clause.unresolved_company is None:
            outcome.unsupported.append((words, "COMPANY_NOT_IN_DATA"))
        return []

    def _labels(self, clause: Clause) -> tuple[list[str], list[str]]:
        """(grounded, ungrounded) sector labels: a label counts when it or an everyday word for it is written."""
        written = sectors_written_in(clause.evidence[0], self.reference.sectors)
        known = [label for label in clause.sectors if label in self.reference.sectors]
        grounded = [label for label in known if label in written]
        ungrounded = [label for label in known if label not in written]
        if len(grounded) < len(clause.sectors):
            self._down("ungrounded_sector")
        return grounded, ungrounded

    # -- C, D, I. the number

    def _unowned_tokens(self, clause: Clause) -> list[tuple[int, int]]:
        """D. Digits inside the evidence that nothing the server understood accounts for."""
        owners = [_offsets(span) for span in (clause.quantity_mention, clause.date_mention) if span is not None]
        owners += [_offsets(other.quantity_mention) for other in self.by_id.values()
                   if other.id != clause.id and other.quantity_mention is not None
                   and _inside(_offsets(other.evidence), _offsets(clause.evidence))]
        confirmed = [(_offsets(item.mention), item.kind) for item in self.reading.non_quantity]
        unowned = []
        for token in quantity.number_tokens(clause.evidence[0]):
            span = (clause.start + token[0], clause.start + token[1])
            if any(_inside(span, owner) for owner in owners):
                continue
            if any(_inside(span, mention) and self._kind_confirmed(kind, span) for mention, kind in confirmed):
                continue
            unowned.append(span)
        return unowned

    def _kind_confirmed(self, kind: str, span: tuple[int, int]) -> bool:
        """A non_quantity claim holds only when the characters agree: a year looks like one, a horizon has a time
        unit next to it, a name part touches letters, and a count is not written as a percentage."""
        if kind == "YEAR":
            return quantity.is_year(self.text[span[0]:span[1]])
        if kind == "HORIZON":
            return quantity.horizon_confirmed(self.text, span)
        if kind == "NAME_PART":
            return quantity.name_part_confirmed(self.text, span)
        return not quantity.followed_by_percent(self.text, span)

    def _sentence(self, span: tuple[int, int]) -> int | None:
        return next((i for i, s in enumerate(self.sentences) if _inside(span, s)), None)

    def _one_sentence(self, clause: Clause) -> bool:
        """Subject, direction and amount sit in one sentence. When the amount is the only one of them marked, the
        evidence itself must be one sentence: otherwise nothing ties the number to the sentence the wish is in
        ("Not too much in any one company. My friend holds 25% in bonds" marked as one clause)."""
        marked = [s for s in (clause.subject_mention, clause.direction_mention, clause.quantity_mention) if s is not None]
        spans = [_offsets(s) for s in marked]
        if len(spans) < 2:
            spans.append(_offsets(clause.evidence))
        found = {self._sentence(span) for span in spans}
        return None not in found and len(found) <= 1

    def _addressed_to_system(self, clause: Clause) -> bool:
        evidence = _offsets(clause.evidence)
        return any(_overlaps(evidence, s) for s in self.injection + [i for i in self.instructions if i != evidence])

    def _injected(self, clause: Clause) -> bool:
        """A rule with no number is still not drafted directly from words that also address the system: a segment
        the injection lexicon flags, or an instruction clause the evidence overlaps."""
        evidence = _offsets(clause.evidence)
        lexical = [(start, end) for start, end in self.injection if INJECTION_RE.search(self.text, start, end)]
        return any(_overlaps(evidence, s) for s in lexical + [i for i in self.instructions if i != evidence])

    def _decide(self, clause: Clause) -> _Decision:
        """The lattice for a numeric rule (C, D, E-veto, I). Checks run in a fixed order and the first that fails
        gives the reason; a FRACTION is offered only once every other check has passed."""
        unowned = self._unowned_tokens(clause)
        firm = clause.confidence == "HIGH" and not clause.ambiguity
        if clause.quantity_mention is None:
            if unowned:
                return _Decision(reason="UNOWNED_NUMBER")
            return _Decision() if firm else _Decision(reason="MISSING")
        if self._addressed_to_system(clause):
            return _Decision(reason="INSTRUCTION")
        if self._direction_vetoed(clause):
            return _Decision(reason="DIRECTION_UNCLEAR")
        if quantity.splits_a_number(self.text, _offsets(clause.quantity_mention)):
            return _Decision(reason="MISTYPED")  # "5%" marked inside "25%": not the number the investor wrote
        amount = quantity.parse(clause.quantity_mention[0])
        if amount.form in _FORM_REASON:
            return _Decision(reason=_FORM_REASON[amount.form])
        if quantity.hedged_near(self.text, _offsets(clause.quantity_mention), _offsets(clause.evidence)):
            return _Decision(reason="HEDGED")
        for code in clause.ambiguity:
            if code in _NUMBER_AMBIGUITY:
                return _Decision(reason=_NUMBER_AMBIGUITY[code])
        if unowned or not self._one_sentence(clause) or self._nested_ambiguity(clause):
            return _Decision(reason="UNOWNED_NUMBER")
        if not firm:
            return _Decision(reason="LOW_CONFIDENCE")
        number = (amount.value, amount.quote)
        if amount.form == quantity.FRACTION:
            return _Decision(reason="FRACTION", offer=number)
        return _Decision(number=number)  # type: ignore[arg-type]

    def _direction_vetoed(self, clause: Clause) -> bool:
        """E. Opposite-direction words in the direction words or the amount ("10% or more" read as a cap); with no
        direction words marked, anywhere in the evidence."""
        veto = DIRECTION_VETO.get(clause.direction)
        if veto is None:
            return False
        spans = [s for s in (clause.direction_mention, clause.quantity_mention) if s is not None]
        if clause.direction_mention is None:
            spans.append(clause.evidence)
        if any(veto.search(span[0]) for span in spans):
            return True
        # "I want more than 10% in X" read as a cap. Only on company shares: "lose more than 20%" is a loss limit.
        comparative = COMPARATIVE_VETO.get(clause.direction) if clause.subject_kind in ("EACH_COMPANY", "NAMED_COMPANIES") else None
        for span in spans:
            for match in comparative.finditer(span[0]) if comparative else ():
                # a negation anywhere before it in the sentence keeps the reading ("no company ever makes up more than")
                start = span[1] + match.start()
                sentence = self._sentence_of((start, start)) or (0, len(self.text))
                if not COMPARATIVE_NEGATION_RE.search(self.text[sentence[0]:start]):
                    return True
        return False

    def _nested_ambiguity(self, clause: Clause) -> bool:
        """D. A clause whose evidence holds another clause with its own amount ("Keep Energy below 30%, and no company
        above 5%" read as one cap plus a nested one) must mark its own subject, and its subject and amount must lie
        outside the nested clause; otherwise the amount may belong to another subject."""
        nested = [_offsets(o.evidence) for o in self.by_id.values()
                  if o.id != clause.id and o.quantity_mention is not None and _inside(_offsets(o.evidence), _offsets(clause.evidence))
                  and _offsets(o.evidence) != _offsets(clause.evidence)]
        if not nested:
            return False
        if clause.subject_mention is None:
            # Only a per-company cap can name its subject without a subject span ("At most 10% per company and at
            # least 3% in Fortis"): its own words, outside the nested clause, must still say per company.
            own = "".join(" " if any(i <= k < j for i, j in nested) else ch
                          for k, ch in enumerate(self.text[clause.start:clause.end], start=clause.start))
            return not (clause.subject_kind == "EACH_COMPANY" and (EACH_WORDS.search(own) or _ANY_ONE_RE.search(own)))
        return any(_overlaps(_offsets(span), inner) for inner in nested
                   for span in (clause.subject_mention, clause.quantity_mention) if span is not None)

    def _rejected(self, clause: Clause) -> bool:
        """E. The words reject the rule itself ("don't exclude X", "I don't want a 10% cap"), whatever the code."""
        sentence = self._sentence_of(_offsets(clause.evidence))
        start = max(sentence[0] if sentence else 0, clause.start - _REJECTION_LOOKBACK)
        return _REJECTION_RE.search(self.text[start:clause.end]) is not None

    def _firm(self, clause: Clause) -> bool:
        """Non-numeric rules are drafted directly only on a HIGH reading with no ambiguity about what is meant."""
        return clause.confidence == "HIGH" and not set(clause.ambiguity) - set(_NUMBER_AMBIGUITY)

    def _numeric(self, outcome: _Outcome, rules: list[tuple[str, dict[str, Any]]]) -> None:
        """Rules that need a number (caps, minimums, loss budgets): drafted, or asked about with the reason."""
        clause = outcome.clause
        decision = self._decide(clause)
        words = clause.evidence[0]
        outcome.measures = [Draft(rt, p, decision.number, words) for rt, p in rules]
        if decision.reason is None:
            outcome.drafts = list(outcome.measures)
            return
        self._down(f"number_{decision.reason}")
        # One question per clause: several companies in one clause share it, each with its own options.
        outcome.asks.append((NUMBER_NEEDED, words, {"pending": [Draft(rt, p) for rt, p in rules], "reason": decision.reason,
                                                    "number": decision.offer}))

    def _exclusion_number(self, outcome: _Outcome) -> tuple[bool, tuple[float, str] | None]:
        """(drafted directly?, number) for an exclusion: only a plain 0% is a number; any other amount, or a digit
        nothing accounts for, asks which number is meant."""
        clause = outcome.clause
        if clause.quantity_mention is None:
            if self._unowned_tokens(clause):
                return False, None
            return True, None
        decision = self._decide(clause)
        if decision.number is not None and decision.number[0] == 0:
            return True, decision.number
        return False, None

    def _exclusions(self, outcome: _Outcome, rules: list[tuple[str, dict[str, Any]]], question: tuple[str, dict[str, Any]]) -> None:
        """Exclusion-type rules: drafted on a firm reading, else ``question`` (topic, details) offers them."""
        clause = outcome.clause
        direct, number = self._exclusion_number(outcome)
        words = clause.evidence[0]
        outcome.measures = [Draft(rt, p, number, words) for rt, p in rules]
        if not direct:
            self._down("number_MISSING")
            outcome.asks.append((NUMBER_NEEDED, words, {"pending": [Draft(*r) for r in rules], "reason": "MISSING"}))
        elif self._firm(clause) and not self._injected(clause):
            outcome.drafts = list(outcome.measures)
        else:
            self._down("not_firm")
            outcome.asks.append((question[0], words, question[1]))

    # -- F. builders (one per MAPPING value)

    def _b_cap_each(self, outcome: _Outcome) -> None:
        self._numeric(outcome, [_CAP_ANY])

    def _group_total(self, outcome: _Outcome, ids: list[str]) -> bool:
        """'Under 15% combined' on several companies: no rule type checks a group together, and one rule per company
        with the whole amount would allow several times it. Reported, never drafted per company."""
        clause = outcome.clause
        if len(ids) < 2 or not (clause.distribution == "TOTAL" or _TOTAL_WORDS_RE.search(clause.evidence[0])):
            return False
        self._down("group_total")
        outcome.unsupported.append((clause.evidence[0], "GROUP_TOTAL"))
        return True

    def _b_cap_named(self, outcome: _Outcome) -> None:
        ids = self._companies(outcome, "max_issuer_exposure", lambda i: {"issuer_scope": i})
        if ids and not self._group_total(outcome, ids):
            self._numeric(outcome, [("max_issuer_exposure", {"issuer_scope": i}) for i in ids])

    def _b_min_named(self, outcome: _Outcome) -> None:
        clause = outcome.clause
        if clause.intent == "HOLD" and clause.quantity_mention is None:
            self._b_company_intent(outcome)  # "I want to hold Exxon" says neither a minimum nor a number
            return
        ids = self._companies(outcome, "min_issuer_exposure", lambda i: {"issuer_id": i})
        if ids and not self._group_total(outcome, ids):
            self._numeric(outcome, [("min_issuer_exposure", {"issuer_id": i}) for i in ids])

    def _b_loss(self, outcome: _Outcome) -> None:
        self._numeric(outcome, [_LOSS])

    def _b_exclude_named(self, outcome: _Outcome) -> None:
        ids = self._companies(outcome, "exclusion", lambda i: _named([i]))
        if ids:
            self._exclusions(outcome, [("exclusion", _named(ids))], ("COMPANY_INTENT", {"kind": "CAUTION", "ids": ids, "number": None}))

    def _b_exclude_sector(self, outcome: _Outcome) -> None:
        clause = outcome.clause
        grounded, ungrounded = self._labels(clause)
        if grounded:
            # Not drafted directly: one question offers every label, those the words name first.
            self._exclusions(outcome, [("exclusion", _sector(label)) for label in grounded],
                             ("EXCLUSION_DEFINITION", {"sectors": grounded + ungrounded}))
        if ungrounded and (outcome.drafts or not grounded):
            # A label the words do not name ("oil" for Energy) is a guess about meaning: offered, never drafted.
            outcome.asks.append(("EXCLUSION_DEFINITION", clause.evidence[0], {"sectors": ungrounded}))
        elif not grounded:
            outcome.asks.append(("EXCLUSION_DEFINITION", clause.evidence[0], {"sectors": []}))

    def _b_exclude_controversy(self, outcome: _Outcome) -> None:
        clause = outcome.clause
        date = None
        if clause.date_mention is not None:
            date = quantity.parse_date(clause.date_mention[0])
            if date is None:  # "before 2020", "in 2020": no rule says that; the undated registry is offered
                self._down("date_unparsed")
                outcome.asks.append(("THEME", clause.evidence[0], {"theme": "ESG", "polarity": "AVOID"}))
                return
        self._exclusions(outcome, [("controversy_exclusion", _controversy(clause.natures, date))],
                         ("THEME", {"theme": "ESG", "polarity": "AVOID"}))

    def _b_controversy_cap(self, outcome: _Outcome) -> None:
        """'At most 5% in controversial companies': the engine sums the flagged companies, so 'in each' is asked."""
        clause = outcome.clause
        if clause.quantity_mention is None:
            self._b_exclude_controversy(outcome)
            return
        date = quantity.parse_date(clause.date_mention[0]) if clause.date_mention is not None else None
        if clause.date_mention is not None and date is None:  # as on the exclusion path: never widened to every date
            self._down("date_unparsed")
            outcome.asks.append(("THEME", clause.evidence[0], {"theme": "ESG", "polarity": "AVOID"}))
            return
        rule = ("controversy_exclusion", _controversy(clause.natures, date))
        each = clause.distribution == "EACH" or (clause.scope_mention is not None and EACH_WORDS.search(clause.scope_mention[0]))
        if each:
            self._down("per_company_on_total")
            decision = self._decide(clause)
            outcome.measures = [Draft(*rule, decision.number)]
            outcome.asks.append(("PER_COMPANY_OR_TOTAL", clause.evidence[0], {"draft": Draft(*rule, decision.number)}))
            return
        self._numeric(outcome, [rule])

    def _b_exclude_activity(self, outcome: _Outcome) -> None:
        clause = outcome.clause
        sector = "Energy" if clause.activity in _OIL_ACTIVITIES and "Energy" in self.reference.sectors else None
        if sector is not None:  # never drafted (the words do not name the label), but an exception can be made of it
            outcome.measures = [Draft("exclusion", _sector(sector), None, clause.evidence[0])]
        outcome.asks.append(("EXCLUSION_DEFINITION", clause.evidence[0], {"sector": sector}))

    def _b_keep_only(self, outcome: _Outcome) -> None:
        """'Only tech stocks' drafts the exclusion of every other label, the widest rule this compiler writes, so it
        needs a HIGH, unambiguous reading whose exclusivity words really say 'only'. Anything less stays a focus."""
        clause = outcome.clause
        grounded, ungrounded = self._labels(clause)
        words = clause.evidence[0]
        if not grounded or ungrounded:
            # No label at all ("only healthcare" in a snapshot without one) has no sourced definition; a label the
            # words do not name is a guess, and the investor is shown the labels the data has.
            outcome.unsupported.append((words, "SECTOR_NOT_MATCHED" if clause.sectors else "NO_SOURCED_DEFINITION"))
            return
        if clause.quantity_mention is not None or self._unowned_tokens(clause):
            # "Only 20% in tech" is a share of a sector, not "nothing else": no sector-cap rule type says it.
            self._down("focus_with_number")
            outcome.unsupported.append((words, "SECTOR_LIMIT"))
            return
        restrictive = clause.exclusivity_mention is not None and RESTRICTIVE_WORDS.search(clause.exclusivity_mention[0])
        others = [label for label in self.reference.sectors if label not in grounded]
        if not (clause.confidence == "HIGH" and not clause.ambiguity and restrictive and len(grounded) <= MAX_FOCUS_SECTORS
                and not self._injected(clause)):
            self._down("focus_gate")
            outcome.objective_id = self._preference_objective(clause)
            outcome.unsupported.append((words, "FOCUS_NOT_ONLY"))
            return
        if len(others) > MAX_FOCUS_RULES:
            outcome.unsupported.append((words, "FOCUS_TOO_WIDE"))
            return
        outcome.measures = [Draft("exclusion", _sector(label), None, words) for label in others]
        outcome.drafts = list(outcome.measures)

    def _b_focus_not_only(self, outcome: _Outcome) -> None:
        outcome.objective_id = self._preference_objective(outcome.clause)
        outcome.unsupported.append((outcome.clause.evidence[0], "FOCUS_NOT_ONLY"))

    def _b_company_intent(self, outcome: _Outcome) -> None:
        """Holding, caution or an exact share of named companies: no rule type says it, so the investor chooses."""
        clause = outcome.clause
        kind = {"HOLD": "HOLD", "CAUTION": "CAUTION"}.get(clause.intent, "EXACTLY")
        rule_type = {"HOLD": "min_issuer_exposure", "CAUTION": "max_issuer_exposure"}.get(kind, "max_issuer_exposure")
        builder = (lambda i: {"issuer_id": i}) if rule_type == "min_issuer_exposure" else (lambda i: {"issuer_scope": i})
        ids = self._companies(outcome, rule_type, builder)
        if not ids:
            return
        # The number is carried by every option, so the direction veto does not apply: the investor picks the direction.
        number = self._decide(replace(clause, direction="UNSPECIFIED")).number if clause.quantity_mention is not None else None
        # A stated direction keeps the number on the options of that direction only ("hold it, but no more than 5%").
        direction = clause.direction if clause.direction in ("AT_MOST", "AT_LEAST") else None
        outcome.asks.append(("COMPANY_INTENT", clause.evidence[0], {"kind": kind, "ids": ids, "number": number, "direction": direction}))

    def _implied(self, outcome: _Outcome) -> list[tuple[str, dict[str, Any]]] | None:
        """The rules a clause's subject implies, whatever its direction: what a direction or range question offers."""
        clause = outcome.clause
        kind = clause.subject_kind
        if kind == "EACH_COMPANY":
            return [_CAP_ANY]
        if kind == "PORTFOLIO_LOSS":
            return [_LOSS]
        if kind == "CONTROVERSY":
            return [("controversy_exclusion", _controversy(clause.natures, None))]
        if kind == "NAMED_COMPANIES":
            if clause.intent == "EXCLUDE":
                ids = self._companies(outcome, "exclusion", lambda i: _named([i]))
                return [("exclusion", _named(ids))] if ids else []
            ids = self._companies(outcome, "max_issuer_exposure", lambda i: {"issuer_scope": i})
            return [("max_issuer_exposure", {"issuer_scope": i}) for i in ids]
        if kind == "SECTOR":
            grounded, _ = self._labels(clause)
            return [("exclusion", _sector(label)) for label in grounded]
        return None

    def _ask_number(self, outcome: _Outcome, reason: str) -> None:
        rules = self._implied(outcome)
        if rules is None:
            outcome.unsupported.append((outcome.clause.evidence[0], "NOT_MEASURABLE"))
            return
        self._down(f"number_{reason}")
        if rules:
            outcome.asks.append((NUMBER_NEEDED, outcome.clause.evidence[0], {"pending": Draft(*rules[0]), "reason": reason}))

    def _b_direction_unclear(self, outcome: _Outcome) -> None:
        self._ask_number(outcome, "DIRECTION_UNCLEAR")

    def _b_range_question(self, outcome: _Outcome) -> None:
        if outcome.clause.subject_kind == "NAMED_COMPANIES" and outcome.clause.intent != "EXCLUDE":
            self._range_company(outcome)
            return
        self._ask_number(outcome, "RANGE")

    def _range_company(self, outcome: _Outcome) -> None:
        """'Between 5% and 10% in Exxon': a minimum or a maximum, without a number."""
        clause = outcome.clause
        ids = self._companies(outcome, "max_issuer_exposure", lambda i: {"issuer_scope": i})
        if ids:
            self._down("number_RANGE")
            outcome.asks.append(("COMPANY_INTENT", clause.evidence[0], {"kind": "EXACTLY", "ids": ids, "number": None}))

    def _b_scope_needed(self, outcome: _Outcome) -> None:
        """'No more than 10%' with no subject: the number is kept, what it limits is the investor's choice."""
        clause = outcome.clause
        subject = clause.subject_mention
        if subject is not None and not _PORTFOLIO_WORDS_RE.search(subject[0]):
            # "Max 25% in Canadian stocks": the words name what is limited and no rule type measures it. Offering a
            # per-company cap or a loss budget instead would put a different constraint in its place.
            outcome.unsupported.append((clause.evidence[0], "NOT_MEASURABLE"))
            return
        number = self._decide(clause).number if clause.quantity_mention is not None else None
        outcome.asks.append(("SCOPE_NEEDED", clause.evidence[0], {"number": number}))

    def _b_diversification(self, outcome: _Outcome) -> None:
        outcome.asks.append(("DIVERSIFICATION", outcome.clause.evidence[0], {}))

    def _b_loss_question(self, outcome: _Outcome) -> None:
        outcome.asks.append(("LOSS_LIMIT", outcome.clause.evidence[0], {}))

    def _b_controversy_question(self, outcome: _Outcome) -> None:
        outcome.asks.append(("THEME", outcome.clause.evidence[0], {"theme": "ESG", "polarity": "AVOID"}))

    def _b_theme(self, outcome: _Outcome) -> None:
        clause = outcome.clause
        polarity = {"EXCLUDE": "AVOID", "KEEP_ONLY": "ONLY"}.get(clause.intent, "PREFER")
        outcome.asks.append(("THEME", clause.evidence[0], {"theme": clause.theme or "ESG", "polarity": polarity}))

    def _b_sector_limit(self, outcome: _Outcome) -> None:
        outcome.unsupported.append((outcome.clause.evidence[0], "SECTOR_LIMIT"))

    def _b_not_measurable(self, outcome: _Outcome) -> None:
        clause = outcome.clause
        if clause.intent == "PERMISSION" and clause.polarity == "ASSERTED":  # "X is not OK" agrees with a limit
            outcome.permission = self._permission_subject(clause)
        outcome.unsupported.append((clause.evidence[0], "NOT_MEASURABLE"))

    def _permission_subject(self, clause: Clause) -> str | frozenset[str] | None:
        if clause.subject_kind == "EACH_COMPANY":
            return EACH
        if clause.subject_kind == "PORTFOLIO_LOSS":
            return LOSS
        if clause.subject_kind == "NAMED_COMPANIES":
            ids = self._grounded_ids(clause)
            return frozenset(ids) if ids else None
        return None

    def _b_soft(self, outcome: _Outcome) -> None:
        """A preference or goal stays an objective; what it would need is said plainly."""
        clause = outcome.clause
        default = "GROWTH_OR_RETURN" if clause.intent == "GOAL" else "NOT_MEASURABLE"
        outcome.unsupported.append((clause.evidence[0], clause.unsupported_reason or default))

    def _b_out_of_scope(self, outcome: _Outcome) -> None:
        reason = outcome.clause.unsupported_reason
        outcome.unsupported.append((outcome.clause.evidence[0], reason if reason in _OUT_OF_SCOPE else "NOT_MEASURABLE"))

    def _b_instruction(self, outcome: _Outcome) -> None:
        outcome.unsupported.append((outcome.clause.evidence[0], "INSTRUCTION"))

    def _b_other(self, outcome: _Outcome) -> None:
        if outcome.clause.unsupported_reason is not None:
            outcome.unsupported.append((outcome.clause.evidence[0], outcome.clause.unsupported_reason))

    # -- G. structure

    def _structure(self, outcomes: list[_Outcome]) -> None:
        by_id = {o.clause.id: o for o in outcomes if not o.clause.problems}
        superseded_by = Counter(o.clause.supersedes for o in by_id.values() if o.clause.supersedes)
        for outcome in by_id.values():
            if outcome.clause.supersedes is not None:
                self._supersede(outcome, by_id, superseded_by)
        for outcome in by_id.values():
            if outcome.clause.exception_of is not None:
                self._exception(outcome, by_id)
        for outcome in by_id.values():
            if outcome.clause.quantity_from is not None:
                self._ellipsis(outcome, by_id)

    def _span_of(self, *clauses: Clause) -> tuple[int, int]:
        """The smallest span holding every given clause (whatever their order or nesting)."""
        return min(c.start for c in clauses), max(c.end for c in clauses)

    def _supersede(self, later: _Outcome, by_id: dict[str, _Outcome], superseded_by: Counter) -> None:
        """'Max 10% per company. Actually make that 8%.': the earlier clause is dropped and the later rule shows the
        whole correction. Only at a later position and one level deep (no chains, no cycles), and only when the later
        clause restates the same kind of rule: the same measures, the same rule type on the same subject kind ("Exclude
        Enbridge. Wait, I meant Exxon"), or another rule on the same companies ("Microsoft min 3%... scratch that, just
        a maximum of 10%"). Anything else is asked about."""
        earlier = by_id.get(later.clause.supersedes or "")
        if earlier is None:
            return
        valid = (earlier.clause.start < later.clause.start and earlier.clause.supersedes is None
                 and superseded_by[later.clause.id] == 0 and superseded_by[earlier.clause.id] == 1)
        if not (valid and self._restates(earlier, later)):
            self._down("correction_not_honoured")
            self.unhonoured.append((earlier.clause.id, later.clause.id, "CORRECTION"))
            if earlier.drafts and not later.drafts:
                # "Avoid Enbridge. Actually, scratch that, keep it.": the later words take something back even when
                # they draft nothing themselves, so the earlier rule is asked about, never drafted as if unsaid.
                words = self.text[slice(*self._span_of(earlier.clause, later.clause))]
                sides = [(earlier.clause.evidence[0], list(earlier.drafts)), (later.clause.evidence[0], [])]
                earlier.drafts = []
                earlier.asks.append(("CONFLICT", words, {"sides": sides}))
            return
        self.honoured.add((earlier.clause.id, later.clause.id))
        earlier.clear()
        earlier.measures = []
        span = self._span_of(earlier.clause, later.clause)
        later.drafts = [d._replace(words=verbatim_slice(self.text, *span, d.number[1] if d.number else None)) for d in later.drafts]

    @staticmethod
    def _restates(earlier: _Outcome, later: _Outcome) -> bool:
        if not earlier.measures or not later.measures:
            return False
        keys = lambda o: {_key(d.rule_type, d.parameters) for d in o.measures}  # noqa: E731
        if keys(earlier) == keys(later):
            return True
        types = lambda o: {d.rule_type for d in o.measures}  # noqa: E731
        if types(earlier) == types(later) and len(types(later)) == 1 and earlier.clause.subject_kind == later.clause.subject_kind:
            return True
        subjects = lambda o: {rule_subject(d.rule_type, d.parameters) for d in o.measures}  # noqa: E731
        return (earlier.clause.subject_kind == later.clause.subject_kind == "NAMED_COMPANIES"
                and subjects(earlier) == subjects(later) and None not in subjects(later))

    def _exception(self, exception: _Outcome, by_id: dict[str, _Outcome]) -> None:
        """'No energy but Enbridge is fine': no rule type carves an exception, so the base is never drafted directly
        and the investor chooses among forms that say how they differ from the words. The exception drafts nothing.

        Two cases need no question. A stricter cap on named companies under an any-company cap ("every company at 10%
        but Microsoft at 6%") is exactly both rules, so both are drafted. And the base's rules the excepted companies
        do not fall under ("No Energy or Utilities, but Enbridge is fine": the Utilities exclusion) stay drafted; only
        the rules the exception touches are asked about."""
        base = by_id.get(exception.clause.exception_of or "")
        if base is None or base is exception:
            return
        if not base.measures:
            # The base drafts nothing (unsupported, or already a question): the exception's own number is never used.
            if exception.drafts or exception.asks:
                self._down("exception_without_base")
                exception.clear()
                exception.measures = []
                exception.unsupported.append((exception.clause.evidence[0], "NOT_MEASURABLE"))
            return
        if self._stricter_named_caps(base, exception):
            self._down("exception_stricter")
            return
        start, end = self._span_of(base.clause, exception.clause)
        words = self.text[start:end]
        excepted = self._grounded_ids(exception.clause) if exception.clause.subject_kind == "NAMED_COMPANIES" else []
        affected = [d for d in base.measures if not excepted or self._touches(d, excepted)] or list(base.measures)
        untouched = [d for d in base.drafts if d not in affected and _key(d.rule_type, d.parameters) not in
                     {_key(a.rule_type, a.parameters) for a in affected}]
        sectors = [_excluded_sector_of(d) for d in affected]
        sector = sectors[0] if len(affected) == 1 else None
        details: dict[str, Any] = {"exception_words": exception.clause.evidence[0]}
        if sector is not None and excepted and all(self.reference.sector_of.get(i) == sector for i in excepted):
            members = sorted(i for i, label in self.reference.sector_of.items() if label == sector and i not in excepted)
            details.update(base_draft=Draft("exclusion", _sector(sector)), sector=sector, remaining_ids=members)
        else:
            details.update(base_draft=affected if len(affected) > 1 else affected[0])
        self._down("exception")
        if base.clause.subject_kind == "ACTIVITY":
            # "No oil companies but Enbridge is fine": this question replaces the catalog's oil question, whose
            # Energy option would also leave out the company the investor kept.
            self.excepted_catalog += [c for c in self.catalog if _overlaps(c, _offsets(base.clause.evidence))]
        for outcome in (base, exception):
            outcome.clear()
            outcome.measures = []
        base.drafts = untouched
        base.measures = list(untouched)
        base.asks.append(("EXCEPTION", words, details))

    def _touches(self, draft: Draft, excepted: list[str]) -> bool:
        """The excepted companies fall under this rule of the base."""
        definition = draft.parameters.get("definition") or {}
        if definition.get("kind") == "fund_reported_sector":
            return any(self.reference.sector_of.get(i) == definition["sector"] for i in excepted)
        if definition.get("kind") == "named_issuers":
            return bool(set(definition["issuer_ids"]) & set(excepted))
        issuer = draft.parameters.get("issuer_scope") or draft.parameters.get("issuer_id")
        return issuer == "any" or issuer in excepted or issuer is None

    @staticmethod
    def _stricter_named_caps(base: _Outcome, exception: _Outcome) -> bool:
        caps_any = [d for d in base.drafts if (d.rule_type, d.parameters) == _CAP_ANY and d.number is not None]
        own = exception.drafts
        return (bool(caps_any) and len(base.drafts) == len(caps_any) and bool(own)
                and all(d.rule_type == "max_issuer_exposure" and d.parameters.get("issuer_scope") not in (None, "any")
                        and d.number is not None and d.number[0] <= min(c.number[0] for c in caps_any) for d in own))

    def _ellipsis(self, outcome: _Outcome, by_id: dict[str, _Outcome]) -> None:
        """'At most 5% in Microsoft. The same for Enbridge.': the earlier number is offered, never applied."""
        clause = outcome.clause
        if not outcome.measures:
            return
        target = by_id.get(clause.quantity_from or "")
        amount = quantity.parse(target.clause.quantity_mention[0]) if target and target.clause.quantity_mention else None
        outcome.clear()
        pendings = [d._replace(number=None, words=None) for d in outcome.measures]
        outcome.measures = []
        words = None
        if not (target is None or target.clause.start >= clause.start or amount is None or amount.form not in quantity.THRESHOLD_FORMS):
            # Both clauses' span, whatever their nesting ("Microsoft, and the same for Enbridge, at most 5%").
            span = self._span_of(target.clause, clause)
            try:
                words = verbatim_slice(self.text, *span, amount.quote)
            except ValueError:
                words = None
        if words is None:
            self._down("number_MISSING")
            outcome.asks.append((NUMBER_NEEDED, clause.evidence[0], {"pending": pendings, "reason": "MISSING"}))
            return
        self._down("ellipsis")
        number = (amount.value, amount.quote)
        pending = pendings[0]
        outcome.asks.append(("ELLIPSIS", clause.evidence[0], {"draft": Draft(pending.rule_type, pending.parameters, number, words),
                                                               "source_quote": target.clause.evidence[0]}))
        if pendings[1:]:  # an ellipsis on several companies: the others are asked for their number
            outcome.asks.append((NUMBER_NEEDED, clause.evidence[0], {"pending": pendings[1:], "reason": "MISSING"}))

    def _drop_redundant_diversification(self, outcomes: list[_Outcome]) -> None:
        """A diversification wish next to a drafted any-company cap is already answered by that cap: asking which
        rule it means would only repeat it ("I care about diversification, at most 10% per company")."""
        capped = any((d.rule_type, d.parameters) == _CAP_ANY for o in outcomes for d in o.drafts)
        if not capped:
            return
        for outcome in outcomes:
            kept = [ask for ask in outcome.asks if ask[0] != "DIVERSIFICATION"]
            if len(kept) < len(outcome.asks):
                self._down("diversification_answered")
                outcome.asks = kept

    # -- H. conflicts

    def _conflicts(self, outcomes: list[_Outcome]) -> None:
        """Rules that cannot all hold are replaced by one question per set of clauses involved (see
        backend.agents.conflicts). Groups that share a clause are one question, so no question is lost to the
        Renderer's dedup; each clause is one side, with all of its conflicting rules."""
        nodes: list[tuple[_Outcome, Draft | None]] = []
        candidates = []
        for outcome in outcomes:
            for draft in outcome.drafts:
                candidates.append(Candidate(len(nodes), outcome.clause.id, draft.rule_type, draft.parameters,
                                            draft.number[0] if draft.number else None))
                nodes.append((outcome, draft))
            if outcome.permission is not None:
                candidates.append(Candidate(len(nodes), outcome.clause.id, None, {}, permission=outcome.permission))
                nodes.append((outcome, None))
        claims = [(c.a, c.b, c.kind) for c in self.reading.conflicts
                  if not (c.kind == "CORRECTION" and ((c.a, c.b) in self.honoured or (c.b, c.a) in self.honoured))]
        tensions = sum(1 for c in self.reading.conflicts if c.kind == "TENSION")
        if tensions:
            self._down("tension_not_a_conflict")
        groups = find_conflicts(candidates, self.reference.sector_of, claims + self.unhonoured + self._every_sector_excluded(candidates))
        merged: list[tuple[set[str], list[int]]] = []  # (clause ids, node indexes)
        for group in groups:
            for reason in group.reasons:
                self._down(f"conflict_{reason}")
            clause_ids = {c.clause_id for c in group.members}
            indexes = [c.index for c in group.members]
            touching = [m for m in merged if m[0] & clause_ids]
            for m in touching:
                merged.remove(m)
                clause_ids |= m[0]
                indexes = m[1] + indexes
            merged.append((clause_ids, sorted(set(indexes))))
        for clause_ids, indexes in merged:
            members = [nodes[i] for i in indexes]
            sides: dict[str, tuple[_Outcome, list[Draft]]] = {}
            for outcome, draft in members:
                side = sides.setdefault(outcome.clause.id, (outcome, []))
                if draft is not None:
                    side[1].append(draft)
            for outcome, drafts in sides.values():
                for draft in drafts:
                    if draft in outcome.drafts:
                        outcome.drafts.remove(draft)
            ordered = sorted(sides.values(), key=lambda side: side[0].clause.start)
            words = self.text[slice(*self._span_of(*(o.clause for o, _ in ordered)))]
            self._down("conflict")
            ordered[0][0].asks.append(("CONFLICT", words, {"sides": [
                (o.clause.evidence[0], drafts, o.clause.intent == "KEEP_ONLY") for o, drafts in ordered]}))

    def _every_sector_excluded(self, candidates: list[Candidate]) -> list[tuple[str, str, str]]:
        """'Only tech. No tech either.': exclusions from several clauses that together leave out every sector label
        leave nothing to hold, so those clauses cannot all hold."""
        by_clause: dict[str, set[str]] = {}
        for c in candidates:
            definition = c.parameters.get("definition") or {}
            if c.rule_type == "exclusion" and definition.get("kind") == "fund_reported_sector":
                by_clause.setdefault(c.clause_id, set()).add(definition["sector"])
        covered = set().union(*by_clause.values()) if by_clause else set()
        if len(by_clause) < 2 or not self.reference.sectors or not set(self.reference.sectors) <= covered:
            return []
        clause_ids = sorted(by_clause)
        return [(clause_ids[0], other, "INFEASIBLE_TOGETHER") for other in clause_ids[1:]]

    # -- emission and safety nets

    def _emit(self, outcome: _Outcome) -> None:
        for words, code in outcome.unsupported:
            self.out.add_unsupported(words, code)
        for topic, words, details in outcome.asks:
            self.out.ask(topic, words, outcome.objective_id, **details)
        drafted = {(r["rule_type"], json.dumps(r["parameters"], sort_keys=True), r["threshold"]) for r in self.out.rules}
        for draft in outcome.drafts:
            key = (draft.rule_type, json.dumps(draft.parameters, sort_keys=True), draft.number[0] if draft.number else None)
            if key not in drafted:  # K: one rule per (rule_type, parameters, threshold)
                drafted.add(key)
                self.out.add_rule(draft.rule_type, draft.parameters, draft.words or outcome.clause.evidence[0], outcome.objective_id, draft.number)

    def _sentence_of(self, span: tuple[int, int]) -> tuple[int, int] | None:
        index = self._sentence(span)
        return None if index is None else self.sentences[index]

    def _covers(self, covered: list[tuple[int, int]], span: tuple[int, int]) -> bool:
        return any(_overlaps(span, c) for c in covered)

    def _focus_in(self, span: tuple[int, int]) -> tuple[tuple[int, int], list[str]] | None:
        """'Only tech stocks', read from the request text alone: an only-cue followed, in the same sentence, by sector
        words, with no number (a share per sector is a sector limit), no negation and no theme word."""
        sentence = self._sentence_of(span)
        if sentence is None:
            return None
        sentence_text = self.text[sentence[0]:sentence[1]]
        if _NUMBERISH_RE.search(sentence_text) or _NEGATION_RE.search(ONLY_CUE_RE.sub(" ", sentence_text)):
            return None
        cue = ONLY_CUE_RE.search(self.text, max(sentence[0], span[0] - CUE_WINDOW), span[1])
        if cue is None:
            return None
        limit = min(max(span[1], cue.end()), sentence[1])
        mentions = [m for m in sector_mentions(self.text, self.reference.sectors) if cue.end() <= m[0] and m[1] <= limit]
        if not mentions:
            return None
        end = max(m[1] for m in mentions)
        trailing = TRAILING_NOUN_RE.match(self.text, end)
        found = (cue.start(), trailing.end() if trailing is not None else end)
        if self._in_catalog(found) or any(p.search(self.text, found[0], found[1]) for p in THEME_TERM_RE.values()):
            return None
        return found, sorted({m[2] for m in mentions})

    def _scan_focus(self, covered: list[tuple[int, int]]) -> None:
        """Safety net for an 'only' sector wish no clause covers: the server drafts it from the words alone."""
        for cue in ONLY_CUE_RE.finditer(self.text):
            sentence = self._sentence_of(cue.span())
            if sentence is None or self._covers(covered, cue.span()):
                continue
            result = self._focus_in((cue.start(), sentence[1]))
            if result is None or self._covers(covered, result[0]):
                continue
            span, kept = result
            covered.append(span)
            words = self.text[span[0]:span[1]]
            others = [label for label in self.reference.sectors if label not in kept]
            if len(kept) > MAX_FOCUS_SECTORS or len(others) > MAX_FOCUS_RULES:
                self.out.add_unsupported(words, "FOCUS_TOO_WIDE")
            else:
                self.out.add_sector_exclusions(others, words, self._objective_id(None, span))

    def _scan_themes(self, covered: list[tuple[int, int]]) -> None:
        """Safety net: a theme word no clause covers, right after an 'only', 'avoid' or 'prefer' cue, still gets the
        theme question ("I want only environmental investments"). It can only add a question."""
        for theme, pattern in THEME_TERM_RE.items():
            for match in pattern.finditer(self.text):
                if self._covers(covered, match.span()) or self._in_catalog(match.span()):
                    continue
                sentence = self._sentence_of(match.span()) or match.span()
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
                trailing = TRAILING_NOUN_RE.match(self.text, match.end())
                span = (cue[1], trailing.end() if trailing is not None else match.end())
                covered.append(span)
                self.out.ask("THEME", self.text[span[0]:span[1]], self._objective_id(None, span), theme=theme, polarity=cue[0])

    def _assert_numbers(self) -> None:
        """Final check: every threshold is what its quote literally says. A mismatch is a server bug; that rule is
        withdrawn and asked about instead, so a wrong number can never be proposed."""
        for rule in list(self.out.rules):
            if rule["threshold"] is None:
                continue
            amount = quantity.parse(rule["threshold_quote"] or "")
            if amount.form in quantity.THRESHOLD_FORMS and amount.value is not None and abs(amount.value - rule["threshold"]) < 1e-12 \
                    and rule["threshold_quote"] in self.text:
                continue
            self._down("number_assertion_failed")
            self.out.rules.remove(rule)
            self.out.ask(NUMBER_NEEDED, rule["original_words"], rule["objective_id"],
                         pending=Draft(rule["rule_type"], rule["parameters"]), reason="MISSING")


def compile_reading(reading: Reading, *, text: str, persona_id: str, reference: _Reference, lookups: dict[str, list[str]],
                    interpretation_id: str, created_at: str, model_id: str | None, clarification_mode: bool = False,
                    downgrades: Counter | None = None) -> dict[str, Any]:
    """The interpretation document for one checked reading. ``lookups`` maps words the investor wrote (and the model
    looked up with find_companies) to the ids found. ``downgrades``, when given, is filled with reason counts for the
    log. Contract validation is the caller's job."""
    compiler = _Compiler(reading, text, reference, lookups, clarification_mode, downgrades if downgrades is not None else Counter())
    return compiler.run().finish(text=text, persona_id=persona_id, interpretation_id=interpretation_id,
                                 created_at=created_at, model_id=model_id)
