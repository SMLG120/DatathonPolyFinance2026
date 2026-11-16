"""Server-written output of the interpreter: every sentence the investor reads is built here (standard library only).

The model only marks spans and picks codes. This module turns validated codes, verbatim spans of the investor's
text and snapshot labels into the four lists of an ``interpretation`` (contracts/api.md section 3). Nothing here
reads the model's answer: callers pass it words that are already slices of the request text and codes that are
already checked against closed lists. Every rule is built by ``draft_rule``, so it is PROPOSED and carries a
number only as ``(fraction, verbatim quote)`` computed by the server from the investor's characters.

Frozen interface (WP2 and WP4 code against it; change it only together with them)
--------------------------------------------------------------------------------
``draft_rule(rule_id, rule_type, parameters, words, objective_id, number=None) -> dict``
    One PROPOSED rule. ``number`` is ``(fraction, quote)``: with it the rule is USER_STATED with
    ``threshold_source: USER_WORDS``; without it the threshold is null and the rule is SYSTEM_PROPOSED.

``draft_rule_over(rule_id, rule_type, parameters, text, span, objective_id, number=None) -> dict``
    ``draft_rule`` whose ``original_words`` is the verbatim slice ``text[span[0]:span[1]]``, which may cover more
    than one clause (a correction "Max 10%. Actually make that 8%.", or an ellipsis "Max 10% in Exxon. Same for
    Enbridge."). ``verbatim_slice(text, start, end, quote=None) -> str`` is the same slice for ``Renderer.add_rule``.

``Draft(rule_type, parameters, number=None, words=None)``
    A rule not yet drafted: what a question offers as an option. The Renderer drafts it (with its own rule id)
    only when the question is asked. ``words`` defaults to the question's words. Wherever a ``Draft`` is
    expected, a rule built by ``draft_rule`` and a ``(rule_type, parameters)`` pair are accepted too.

``Renderer(sectors: list[str], clarification_mode: bool, names: dict[str, str] | None = None)``
    ``sectors`` are the snapshot's labels (``_Reference.sectors``); they decide which options a question can offer.
    ``names`` maps issuer id -> snapshot display name (``_Reference.display``) for option labels; an id without a
    name is shown as the id. In ``clarification_mode`` every unsupported reason ends with ``_CLARIFICATION_SUFFIX``.

Lists (append only through the methods below; read freely):

* ``objectives``, ``rules``, ``unsupported``, ``clarifications``: the interpretation's four lists, in order.

Methods:

* ``add_objective(words: str, kind: str) -> None`` - a USER_STATED objective with the next ``obj-N`` id.
* ``add_rule(rule_type, parameters, words, objective_id, number=None) -> dict`` - drafts with the next rule id,
  appends and returns the rule.
* ``add_sector_exclusions(labels, words, objective_id) -> None`` - one numberless exclusion per sector label,
  skipping any whose parameters are already drafted.
* ``add_unsupported(words: str, reason_code: str) -> None`` - ``reason_code`` is a key of ``UNSUPPORTED_REASONS``
  (the model's closed list) or of ``SERVER_REASONS`` (raised by the server only). One entry per
  ``(words, contract code)``; a repeat is ignored.
* ``ask(topic, words, objective_id, **details) -> None`` - one clarification per ``(topic, words)``; a repeat is
  ignored. ``words`` (the ``about_words``) must be a verbatim span of the text. Every question has at least two
  options, every option rule is drafted by ``draft_rule`` and the last option is always keep-qualitative.
  Topics and their keyword-only details:

  - ``THEME``: ``theme``, ``polarity`` (``ONLY`` / ``AVOID`` / ``PREFER``).
  - ``EXCLUSION_DEFINITION``: ``sectors`` (labels offered in order; ``sector`` is the one-label form), unless the
    words are about oil (then Energy only).
  - ``DIVERSIFICATION``, ``LOSS_LIMIT``: none.
  - ``NUMBER_NEEDED``: ``pending`` (the ``Draft`` offered without a number, or a list of them: one pair of options
    per company of the clause, ids suffixed ``-1``, ``-2`` ...), ``reason`` (a key of
    ``NUMBER_REASONS``; None keeps the original same-sentence sentence), ``number`` (``(value, quote)``: offered
    first as 'use-number'; the compiler passes it for reason ``FRACTION`` only).
  - ``COMPANY_WHICH``: ``candidates`` (issuer ids, at most ``MAX_COMPANY_OPTIONS`` are offered), ``rule_type``,
    ``parameters_builder`` (issuer id -> parameters). Each candidate is offered as a numberless draft.
  - ``COMPANY_INTENT``: ``kind`` (``HOLD``: minimum + maximum; ``CAUTION``: maximum + exclusion; ``EXACTLY``:
    minimum + maximum), ``ids`` (issuer ids), ``number`` (``(value, quote)`` or None, carried by every
    min/max option, or only by those of ``direction`` when it is AT_MOST or AT_LEAST).
  - ``CONFLICT``: ``sides`` (``[(evidence, Draft | None)]`` or ``[(evidence, [Draft], whole)]``, at least two; at most
    ``MAX_CONFLICT_SIDES`` rules are offered as 'keep-N', sides with rules first). The question quotes every evidence;
    keep-qualitative reads as "neither". See ``_conflict``.
  - ``EXCEPTION``: ``base_draft`` (or a list: one 'every-company-N' option each), ``exception_words`` (verbatim), ``sector`` (set when the base excludes that
    sector label and every excepted company carries it), ``remaining_ids`` (the sector's snapshot members minus
    the exception; offered as a named exclusion when 1 to ``MAX_EXCEPTION_REMAINING`` ids).
  - ``ELLIPSIS``: ``draft`` (carrying the reused number), ``source_quote`` (verbatim words the number is
    reused from).
  - ``SCOPE_NEEDED``: ``number`` (or None), carried by the any-company cap and the 2022 loss budget options.
  - ``PER_COMPANY_OR_TOTAL``: ``draft`` (the aggregate controversy exclusion carrying the investor's number).
* ``finish(*, text, persona_id, interpretation_id, created_at, model_id) -> dict`` - the interpretation document.

Rule ids are ``draft-<slug>-N`` with one counter per Renderer, so ids follow drafting order.
"""

from __future__ import annotations

import json
import re
from typing import Any, Callable, NamedTuple

from byb_contracts import SCHEMA_VERSION
from byb_contracts.constants import SCENARIO_IDS
from byb_contracts.templates import scope_description

from backend.agents.themes import CATALOG_RE, THEMES

DEFAULT_NATURES = ("REGULATORY_FINDING", "COURT_RULING", "SETTLEMENT")
NUMBER_NEEDED = "NUMBER_NEEDED"  # a topic raised by the server only, never offered to the model

_NO_FORECAST = "This tool checks a proposed purchase against rules you confirmed. "
# reason code -> (contract unsupported code, server-written reason). The keys are the model's closed list.
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
_FOCUS_TOO_WIDE = ("UNSUPPORTED_DEFINITION", "Keeping only these sectors would need more exclusion rules than one request can draft. "
                   "Name the sectors to leave out instead.")
# Reasons only the server raises. Kept apart from UNSUPPORTED_REASONS so they never enter the model's enum.
# SECTOR_NOT_MATCHED's text lists the snapshot's labels, filled in by the Renderer.
SERVER_REASONS: dict[str, tuple[str, str]] = {
    "SECTOR_NOT_MATCHED": _SECTOR_NOT_MATCHED,
    "FOCUS_TOO_WIDE": _FOCUS_TOO_WIDE,
    # A focus or preference with no 'only'-type cue: excluding every other label would be stricter than the words.
    # An amount for several named companies together ("under 15% combined"): one rule per company would allow more.
    "GROUP_TOTAL": ("UNSUPPORTED_RULE_TYPE", "No rule type checks an amount shared by several companies together, so no rule was drafted. "
                    "Writing the amount for each company (for example 'at most 5% in each') drafts one rule per company."),
    "FOCUS_NOT_ONLY": ("UNSUPPORTED_RULE_TYPE", "A focus is kept as a qualitative objective and is not checked. "
                       "Writing 'only' followed by the sector labels to keep drafts exclusions of the other labels."),
}

_THRESHOLD_KIND = {"max_issuer_exposure": "max_fraction", "min_issuer_exposure": "min_fraction", "exclusion": "max_fraction",
                   "controversy_exclusion": "max_fraction", "scenario_loss_budget": "max_loss_fraction"}
_RULE_SLUG = {"max_issuer_exposure": "issuer-cap", "min_issuer_exposure": "issuer-min", "exclusion": "excl",
              "controversy_exclusion": "controversy", "scenario_loss_budget": "loss"}

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

# NUMBER_NEEDED reason -> the sentence that says why no number was taken. Each follows "Which number should apply to
# '<words>'?". Reason None keeps the original sentence, which the same-sentence check still uses.
NUMBER_REASONS: dict[str, str] = {
    "MISSING": "Your words give no percentage that can be used for this rule, so none was taken.",
    "UNIT_UNCLEAR": "The number is written without a percent sign, so it is not clear what share it means; none was taken.",
    "RANGE": "Your words give a range or more than one number, so no single number was taken.",
    "HEDGED": "The number is written as an approximation, so it was not taken as a firm limit.",
    "MISTYPED": "The number could not be read as a percentage between 0% and 100%, so none was taken.",
    "UNOWNED_NUMBER": "Your words contain a number that may not belong to this rule, so none was taken.",
    "DIRECTION_UNCLEAR": "It is not clear whether the number is a maximum or a minimum, so none was taken.",
    "LOW_CONFIDENCE": "The reading of these words is uncertain, so no number was taken without your confirmation.",
    "INSTRUCTION": "These words also read as an instruction to the system, so no number was taken from them.",
    "FRACTION": "The amount is written as a fraction, so it is offered as a percentage for you to confirm.",
}
_NUMBER_NEEDED_DEFAULT = ("A number is taken from your words only when it is written as one percentage "
                          "in the same sentence as the rule, so none was taken here.")
_ENTER_NUMBER = ("enter-number", "I will enter the number myself",
                 "The rule is drafted without a number. It stays inactive until you enter one and confirm it.")
_NEITHER = ("keep-qualitative", "Neither: keep them as qualitative preferences only",
            "Nothing will be checked numerically for them; they stay visible as context.")
_LOOK_THROUGH_NOTE = "Counts direct holdings and holdings through equity funds."
_REPLAY_NOTE = "A historical replay of an assumed allocation: not a forecast and not a maximum future loss."
MAX_COMPANY_OPTIONS = 5  # COMPANY_WHICH: more candidates than this means the words do not pick a company
MAX_CONFLICT_SIDES = 4
MAX_EXCEPTION_REMAINING = 20  # a longer named list would be unreadable on a card; the whole-sector option remains
COMPANY_INTENT_KINDS = ("HOLD", "CAUTION", "EXACTLY")


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


def verbatim_slice(text: str, start: int, end: int, quote: str | None = None) -> str:
    """``text[start:end]`` trimmed, for an ``original_words`` wider than one clause. It is a slice, so it is verbatim
    by construction; a quote outside it would make the rule card show a number its words do not contain."""
    if not 0 <= start < end <= len(text):
        raise ValueError(f"span ({start}, {end}) is not inside the text")
    words = text[start:end].strip()
    if not words or (quote is not None and quote not in words):
        raise ValueError("the slice is blank or does not contain the threshold quote")
    return words


def draft_rule_over(rule_id: str, rule_type: str, parameters: dict[str, Any], text: str, span: tuple[int, int],
                    objective_id: str | None, number: tuple[float, str] | None = None) -> dict[str, Any]:
    """``draft_rule`` whose words are the verbatim slice ``span`` of ``text`` (a correction or an ellipsis)."""
    words = verbatim_slice(text, span[0], span[1], number[1] if number else None)
    return draft_rule(rule_id, rule_type, parameters, words, objective_id, number)


class Draft(NamedTuple):
    """A rule a question offers, drafted only when the question is asked so that ids follow drafting order."""

    rule_type: str
    parameters: dict[str, Any]
    number: tuple[float, str] | None = None
    words: str | None = None

    @classmethod
    def of(cls, value: Draft | dict[str, Any] | tuple[Any, ...]) -> Draft:
        """A Draft from a rule built by ``draft_rule`` (its number and words kept) or a ``(rule_type, parameters)``."""
        if isinstance(value, dict):
            number = (value["threshold"], value["threshold_quote"]) if value["threshold"] is not None else None
            return cls(value["rule_type"], value["parameters"], number, value["original_words"])
        return cls(*value)


def _percent(value: float) -> str:
    """A fraction as the percentage a label shows: 0.07 -> '7%', 0.025 -> '2.5%', 1/3 -> '33.33%'."""
    return f"{round(value * 100, 2):g}%"


def _number_note(number: tuple[float, str] | None) -> str:
    """Where an option's number comes from, so the investor sees which of their words it was read from."""
    if number is None:
        return "Drafted without a number: it stays inactive until you enter one and confirm it."
    return f"Drafted with {_percent(number[0])} from your words '{number[1]}'."


def _rule_number(rule: dict[str, Any]) -> tuple[float, str] | None:
    """The ``(value, quote)`` a drafted rule carries, or None. A 0% exclusion carries a number too."""
    return (rule["threshold"], rule["threshold_quote"]) if rule["threshold"] is not None else None


def _and_list(items: list[str]) -> str:
    return items[0] if len(items) == 1 else f"{', '.join(items[:-1])} and {items[-1]}"


def _named_parameters(issuer_ids: list[str]) -> dict[str, Any]:
    return {"definition": {"kind": "named_issuers", "issuer_ids": list(issuer_ids)}}


def _option(option_id: str, label: str, description: str, supported: bool = True, rule: dict[str, Any] | None = None) -> dict[str, Any]:
    """One clarification option. An unsupported option never carries a rule, so it cannot be chosen into a draft."""
    return {"option_id": option_id, "label": label, "description": description, "supported": supported,
            "proposed_rule": rule if supported else None, "purchase_request": None}


def _sector_parameters(sector: str) -> dict[str, Any]:
    return {"definition": {"kind": "fund_reported_sector", "sector": sector}}


class Renderer:
    """Collects the interpretation's four lists. See the module docstring for the frozen interface."""

    def __init__(self, sectors: list[str], clarification_mode: bool, names: dict[str, str] | None = None) -> None:
        self.sectors = sectors
        self.names = names or {}
        self.clarification_mode = clarification_mode
        self.objectives: list[dict[str, Any]] = []
        self.rules: list[dict[str, Any]] = []
        self.unsupported: list[dict[str, Any]] = []
        self.clarifications: list[dict[str, Any]] = []
        self._rule_count = 0
        self._asked: set[tuple[str, str]] = set()
        self._unsupported_seen: set[tuple[str, str]] = set()

    def _rule_id(self, rule_type: str) -> str:
        """The next draft id. Options of a question consume ids too, so ids follow drafting order, not list order."""
        self._rule_count += 1
        return f"draft-{_RULE_SLUG[rule_type]}-{self._rule_count}"

    def _draft(self, rule_type: str, parameters: dict[str, Any], words: str, objective_id: str | None,
               number: tuple[float, str] | None = None) -> dict[str, Any]:
        return draft_rule(self._rule_id(rule_type), rule_type, parameters, words, objective_id, number)

    def _sector_exclusion(self, sector: str, words: str, objective_id: str | None) -> dict[str, Any]:
        return self._draft("exclusion", _sector_parameters(sector), words, objective_id)

    def _offer(self, draft: Draft | dict[str, Any] | tuple[Any, ...] | None, words: str, objective_id: str | None,
               number: tuple[float, str] | None = None) -> dict[str, Any]:
        """Draft what an option offers. ``number`` overrides the draft's own (None keeps it)."""
        d = Draft.of(draft)
        return self._draft(d.rule_type, d.parameters, d.words or words, objective_id, number or d.number)

    def _company(self, issuer_id: str) -> str:
        """A company as an option shows it: the snapshot name and the id the rule card will use."""
        name = self.names.get(issuer_id)
        return f"{name} ({issuer_id})" if name and name != issuer_id else issuer_id

    # -- the four lists

    def add_objective(self, words: str, kind: str) -> None:
        self.objectives.append({"objective_id": f"obj-{len(self.objectives) + 1}", "original_words": words, "kind": kind,
                                "source": "USER_STATED", "case_reference": None})

    def add_rule(self, rule_type: str, parameters: dict[str, Any], words: str, objective_id: str | None,
                 number: tuple[float, str] | None = None) -> dict[str, Any]:
        rule = self._draft(rule_type, parameters, words, objective_id, number)
        self.rules.append(rule)
        return rule

    def add_sector_exclusions(self, labels: list[str], words: str, objective_id: str | None) -> None:
        """'Only tech stocks' kept as one exclusion per other label. A label already excluded is not drafted twice
        (its id is still consumed, which keeps ids stable whatever was drafted before)."""
        drafted = {(r["rule_type"], json.dumps(r["parameters"], sort_keys=True)) for r in self.rules}
        for label in labels:
            rule = self._sector_exclusion(label, words, objective_id)
            if ("exclusion", json.dumps(rule["parameters"], sort_keys=True)) not in drafted:
                self.rules.append(rule)

    def add_unsupported(self, words: str, reason_code: str) -> None:
        """One unsupported entry per ``(words, contract code)``: two reasons for the same words and code say nothing
        more to the investor than one."""
        code, reason = UNSUPPORTED_REASONS.get(reason_code) or SERVER_REASONS[reason_code]
        if (words, code) in self._unsupported_seen:
            return
        self._unsupported_seen.add((words, code))
        if reason_code == "SECTOR_NOT_MATCHED":
            reason = reason.format(labels=", ".join(self.sectors) or "none")
        self.unsupported.append({"words": words, "code": code, "reason": reason + (_CLARIFICATION_SUFFIX if self.clarification_mode else "")})

    def ask(self, topic: str, words: str, objective_id: str | None, *, sector: str | None = None,
            sectors: list[str] | None = None, direction: str | None = None,
            pending: Draft | tuple[Any, ...] | list[Any] | None = None, theme: str | None = None, polarity: str | None = None,
            reason: str | None = None, number: tuple[float, str] | None = None, candidates: list[str] | None = None,
            rule_type: str | None = None, parameters_builder: Callable[[str], dict[str, Any]] | None = None,
            kind: str | None = None, ids: list[str] | None = None, sides: list[tuple[str, Any]] | None = None,
            base_draft: Draft | dict[str, Any] | None = None, exception_words: str | None = None,
            remaining_ids: list[str] | None = None, draft: Draft | dict[str, Any] | None = None,
            source_quote: str | None = None) -> None:
        """One clarification about ``words``. Its question and options are templates; ``words`` is quoted verbatim.
        The details each topic reads are listed in the module docstring; a topic ignores the others."""
        if (topic, words) in self._asked:
            return
        quoted = f"'{words}'"
        if topic == "THEME":
            question, options = self._theme(quoted, words, objective_id, theme, polarity)
        elif topic == "EXCLUSION_DEFINITION":
            question, options = self._exclusion_definition(quoted, words, objective_id, sectors if sectors is not None else [sector])
        elif topic == "DIVERSIFICATION":
            question, options = self._diversification(quoted, words, objective_id)
        elif topic == "LOSS_LIMIT":
            question, options = self._loss_limit(quoted, words, objective_id)
        elif topic == NUMBER_NEEDED:
            question, options = self._number_needed(quoted, words, objective_id, pending, reason, number)
        elif topic == "COMPANY_WHICH":
            question, options = self._company_which(quoted, words, objective_id, candidates or [], rule_type, parameters_builder)
        elif topic == "COMPANY_INTENT":
            question, options = self._company_intent(quoted, words, objective_id, kind, ids or [], number, direction)
        elif topic == "CONFLICT":
            question, options = self._conflict(objective_id, sides or [])
        elif topic == "EXCEPTION":
            question, options = self._exception(quoted, words, objective_id, base_draft, exception_words, sector, remaining_ids or [])
        elif topic == "ELLIPSIS":
            question, options = self._ellipsis(quoted, words, objective_id, draft, source_quote)
        elif topic == "SCOPE_NEEDED":
            question, options = self._scope_needed(quoted, words, objective_id, number)
        elif topic == "PER_COMPANY_OR_TOTAL":
            question, options = self._per_company_or_total(quoted, words, objective_id, draft)
        else:
            raise ValueError(f"unknown clarification topic {topic!r}")
        if len(options) < 2:  # the contract needs two: a lone option would be a choice the investor cannot refuse
            raise ValueError(f"{topic} question with fewer than two options")
        self._asked.add((topic, words))
        self.clarifications.append({"clarification_id": f"clar-{len(self.clarifications) + 1}", "about_words": words, "question": question, "options": options})

    # -- the topics: each returns (question, options); options are drafted in display order, so ids follow it

    def _theme(self, quoted: str, words: str, objective_id: str | None, theme: str | None,
               polarity: str | None) -> tuple[str, list[dict[str, Any]]]:
        theme = theme or "ESG"
        noun = THEMES[theme][0]
        options = []
        if theme == "ENVIRONMENTAL" and "Energy" in self.sectors:
            options.append(_option(
                "energy-sector-label", "Leave out holdings labelled Energy in what the funds report",
                "The closest definition the data can check: oil, gas and pipeline companies as labelled by each fund issuer. "
                "It does not show that the other holdings are environmentally friendly.",
                rule=self._sector_exclusion("Energy", words, objective_id)))
        options.append(_option(*_CONTROVERSY_OPTION, rule=self._draft(
            "controversy_exclusion", {"criteria": {"natures": list(DEFAULT_NATURES), "event_date_from": None}}, words, objective_id)))
        options.append(_option(*_NAMED_SECTORS))
        options.append(_option(*_NAMED_COMPANIES))
        options.append(_option(*_THEME_UNSUPPORTED[theme], False))
        options.append(_option(*_KEEP_QUALITATIVE))
        if polarity == "ONLY":
            question = (f"What should {quoted} mean as a rule you can check? The data holds no list of {noun} holdings, "
                        "so it can only be checked by leaving out what you do not want.")
        else:
            question = f"What should {quoted} mean as a rule you can check? We hold no sourced {noun} rating, so only the definitions below can be checked."
        return question, options

    def _exclusion_definition(self, quoted: str, words: str, objective_id: str | None,
                              sectors: list[str | None]) -> tuple[str, list[dict[str, Any]]]:
        oil = CATALOG_RE.search(words) is not None  # the same catalog that asks the question (EN/FR/ES)
        if oil:
            # For oil the offered label is never the model's choice: Energy when the snapshot has it, else none.
            sectors = ["Energy"] if "Energy" in self.sectors else []
        options = []
        for sector in dict.fromkeys(s for s in sectors if s is not None):
            slug = re.sub(r"[^a-z0-9]+", "-", sector.lower()).strip("-") or "sector"
            options.append(_option(
                f"{slug}-sector-label", f"Holdings labelled {sector} in what the funds report",
                "Uses the sector label in each fund issuer's holdings file (and the registry label for direct holdings)."
                + (" Broader than oil: it also covers pipelines and gas." if oil and sector == "Energy" else " A sector label can be broader or narrower than what you mean."),
                rule=self._sector_exclusion(sector, words, objective_id)))
        options.append(_option(*_NAMED_COMPANIES))
        if oil:
            options.append(_option("oil-producers", "Companies that produce oil",
                                   "Not supported yet: we hold no sourced classification of oil producers, so this cannot be checked honestly.", False))
            options.append(_option("fossil-fuels", "All fossil fuels", "Not supported yet: we hold no sourced fossil-fuel classification.", False))
        else:
            options.append(_option("activity-classification", "Companies classified by what they produce or do",
                                   "Not supported yet: we hold no sourced classification of business activities, so this cannot be checked honestly.", False))
        question = f"What should {quoted} cover? Only definitions we hold sourced data for can be checked."
        return question, options

    def _diversification(self, quoted: str, words: str, objective_id: str | None) -> tuple[str, list[dict[str, Any]]]:
        options = [
            _option("single-company-cap", "A maximum share of the portfolio in any single company",
                    "Counts direct holdings and holdings through equity funds. You choose the number.",
                    rule=self._draft("max_issuer_exposure", {"issuer_scope": "any"}, words, objective_id)),
            _option("sector-cap", "A maximum share in any single sector", "Not supported yet: there is no sector-cap rule type in this version.", False),
            _option(*_KEEP_QUALITATIVE),
        ]
        question = f"What should {quoted} mean as a rule you can check? Wishes that pull in different directions are not a proven contradiction."
        return question, options

    def _loss_limit(self, quoted: str, words: str, objective_id: str | None) -> tuple[str, list[dict[str, Any]]]:
        options = [
            _option("replay-loss-budget", "A maximum loss when the allocation is replayed through calendar 2022",
                    "A historical replay of an assumed allocation: not a forecast and not a maximum future loss. You choose the number.",
                    rule=self._draft("scenario_loss_budget", {"scenario_id": SCENARIO_IDS[0]}, words, objective_id)),
            _option("no-loss-guarantee", "A guarantee that the portfolio never loses value",
                    "Not supported: the tool does not forecast and nothing can guarantee future results.", False),
            _option(*_KEEP_QUALITATIVE),
        ]
        question = f"What should {quoted} mean as a rule you can check?"
        return question, options

    def _number_needed(self, quoted: str, words: str, objective_id: str | None, pending: Draft | tuple[Any, ...] | None,
                       reason: str | None, number: tuple[float, str] | None) -> tuple[str, list[dict[str, Any]]]:
        """The rule offered without a number. A number computed from the investor's own words (a fraction) is
        offered first, quoted, so choosing it is the investor's decision, never the server's."""
        pendings = [Draft.of(p) for p in (pending if isinstance(pending, list) else [pending])]
        several = len(pendings) > 1
        options = []
        for index, draft in enumerate(pendings, start=1):
            # Several companies in one clause: one pair of options per company, so none of them is lost.
            suffix, subject = (f"-{index}", f" for {self._subject(draft)}") if several else ("", "")
            if number is not None:
                options.append(_option(f"use-number{suffix}", f"Use {_percent(number[0])} (from your words '{number[1]}'){subject}",
                                       "The number is read from your words. It stays inactive until you confirm it.",
                                       rule=self._offer(draft, words, objective_id, number)))
            options.append(_option(f"{_ENTER_NUMBER[0]}{suffix}", f"{_ENTER_NUMBER[1]}{subject}", _ENTER_NUMBER[2],
                                   rule=self._offer(draft._replace(number=None), words, objective_id)))
        options.append(_option(*_KEEP_QUALITATIVE))
        why = _NUMBER_NEEDED_DEFAULT if reason is None else NUMBER_REASONS[reason]
        return f"Which number should apply to {quoted}? {why}", options

    def _company_which(self, quoted: str, words: str, objective_id: str | None, candidates: list[str], rule_type: str | None,
                       parameters_builder: Callable[[str], dict[str, Any]] | None) -> tuple[str, list[dict[str, Any]]]:
        """The words name a company the snapshot holds under several possible ids: the investor picks one."""
        if rule_type is None or parameters_builder is None:
            raise ValueError("COMPANY_WHICH needs rule_type and parameters_builder")
        options = [_option(f"company-{issuer_id}", self._company(issuer_id),
                           "The rule is drafted for this company as the data snapshot lists it. " + _number_note(None),
                           rule=self._draft(rule_type, parameters_builder(issuer_id), words, objective_id))
                   for issuer_id in list(dict.fromkeys(candidates))[:MAX_COMPANY_OPTIONS]]
        options.append(_option(*_KEEP_QUALITATIVE))
        return f"Which company do you mean by {quoted}? Only companies in the data snapshot can be checked.", options

    def _company_intent(self, quoted: str, words: str, objective_id: str | None, kind: str | None, ids: list[str],
                        number: tuple[float, str] | None, direction: str | None = None) -> tuple[str, list[dict[str, Any]]]:
        """A wish about named companies that no single rule type matches: holding, caution, or an exact share. With a
        ``direction`` (AT_MOST / AT_LEAST) the number pre-fills only the options of that direction."""
        if kind not in COMPANY_INTENT_KINDS or not ids:
            raise ValueError(f"COMPANY_INTENT needs a kind in {COMPANY_INTENT_KINDS} and at least one issuer id")
        ids = list(dict.fromkeys(ids))
        low = None if direction == "AT_MOST" else number
        high = None if direction == "AT_LEAST" else number
        minimums = [_option(f"min-{i}", f"A minimum share of the portfolio in {self._company(i)}", f"{_LOOK_THROUGH_NOTE} {_number_note(low)}",
                            rule=self._draft("min_issuer_exposure", {"issuer_id": i}, words, objective_id, low)) for i in ids] if kind != "CAUTION" else []
        maximums = [_option(f"cap-{i}", f"A maximum share of the portfolio in {self._company(i)}", f"{_LOOK_THROUGH_NOTE} {_number_note(high)}",
                            rule=self._draft("max_issuer_exposure", {"issuer_scope": i}, words, objective_id, high)) for i in ids]
        options = minimums + maximums
        if kind == "CAUTION":
            options.append(_option("exclude-named", f"Leave out {_and_list([self._company(i) for i in ids])}",
                                   f"A named-company exclusion. {_LOOK_THROUGH_NOTE}",
                                   rule=self._draft("exclusion", _named_parameters(ids), words, objective_id)))
        options.append(_option(*_KEEP_QUALITATIVE))
        question = {
            "HOLD": f"What should {quoted} mean as a rule you can check? Holding a company can be checked as a minimum or a maximum share of the portfolio.",
            "CAUTION": f"What should {quoted} mean as a rule you can check? Caution about a company can be checked as a maximum share or by leaving it out.",
            "EXACTLY": f"What should {quoted} mean as a rule you can check? An exact share is not a rule type, so the number can be checked as a minimum or as a maximum.",
        }[kind]
        return question, options

    def _conflict(self, objective_id: str | None, sides: list[tuple[Any, ...]]) -> tuple[str, list[dict[str, Any]]]:
        """Wishes that cannot all hold: none is drafted directly, the investor keeps one or neither. The question
        quotes each side's own evidence and never calls it a contradiction (the contract reserves that word).

        A side is ``(evidence, draft or None)`` or ``(evidence, [drafts], whole)``: the rules one clause would draft.
        A side with no draft (a permission such as "No limit per company") is quoted but offers no rule: keeping it is
        what "neither" means. A side with several rules offers one option per rule, each naming its subject, unless
        ``whole`` says the rules only mean the wish together (the exclusions of an "only" wish): one option cannot
        carry them, so that side is shown as an option that needs the wish written again on its own. Sides that carry
        rules come first; at most ``MAX_CONFLICT_SIDES`` rule options are offered, and every side is quoted."""
        normal = []
        for side in sides:
            evidence, drafts = side[0], side[1]
            whole = bool(side[2]) if len(side) > 2 else False
            drafts = [] if drafts is None else (list(drafts) if isinstance(drafts, list) else [drafts])
            normal.append((evidence, drafts, whole))
        if len(normal) < 2:
            raise ValueError("CONFLICT needs at least two sides")
        options: list[dict[str, Any]] = []
        offered = 0
        for evidence, drafts, whole in sorted(normal, key=lambda side: not side[1]):
            if not drafts:
                continue
            if whole and len(drafts) > 1:
                options.append(_option(f"keep-{len(options) + 1}", f"Draft the rules for '{evidence}'",
                                       f"These words need {len(drafts)} rules together, which one option cannot draft. "
                                       "Write them again on their own, without the other wishes, to draft them.", False))
                continue
            for draft in drafts:
                if offered >= MAX_CONFLICT_SIDES:
                    break
                offered += 1
                rule = self._offer(draft, evidence, objective_id)
                label = f"Draft the rule for '{evidence}'" + (f" on {self._subject(draft)}" if len(drafts) > 1 else "")
                options.append(_option(f"keep-{len(options) + 1}", label,
                                       f"{_number_note(_rule_number(rule))} The other wishes are not drafted.", rule=rule))
        options.append(_option(*_NEITHER))
        quotes = list(dict.fromkeys(f"'{evidence}'" for evidence, _, _ in normal))
        both = "both" if len(quotes) == 2 else "all"
        return f"{_and_list(quotes)} cannot {both} hold as rules. Which should be drafted?", options

    def _subject(self, draft: Draft | dict[str, Any] | tuple[Any, ...]) -> str:
        """What one rule is about, as an option names it."""
        d = Draft.of(draft)
        definition = d.parameters.get("definition") or {}
        if definition.get("kind") == "fund_reported_sector":
            return f"holdings labelled {definition['sector']}"
        if definition.get("kind") == "named_issuers":
            return _and_list([self._company(i) for i in definition["issuer_ids"]])
        issuer = d.parameters.get("issuer_scope") or d.parameters.get("issuer_id")
        if issuer == "any":
            return "every company"
        if issuer:
            return self._company(issuer)
        return "the 2022 replay" if d.rule_type == "scenario_loss_budget" else "companies with a recorded controversy"

    def _exception(self, quoted: str, words: str, objective_id: str | None, base_draft: Draft | dict[str, Any] | list[Any] | None,
                   exception_words: str | None, sector: str | None, remaining_ids: list[str]) -> tuple[str, list[dict[str, Any]]]:
        """No rule type can carve an exception out of another rule, so the base rule is offered only in forms that
        say plainly how they differ from the words: a named list without the exception, or the stricter whole rule."""
        if base_draft is None or not exception_words:
            raise ValueError("EXCEPTION needs base_draft and exception_words")
        options = []
        if sector is not None:
            if 1 <= len(remaining_ids) <= MAX_EXCEPTION_REMAINING:
                names = ", ".join(self._company(i) for i in remaining_ids)
                options.append(_option(
                    "named-without-exception", f"Leave out the other companies labelled {sector}, not '{exception_words}'",
                    f"A named-company exclusion of: {names}. These are the companies the data snapshot labels {sector}, "
                    f"without your exception. A holding labelled {sector} that is not in this list is not left out.",
                    rule=self._draft("exclusion", _named_parameters(remaining_ids), words, objective_id)))
            options.append(_option("whole-sector", f"Leave out every holding labelled {sector}, including '{exception_words}'",
                                   "Stricter than you wrote: the exception is not applied.",
                                   rule=self._offer(base_draft, words, objective_id)))
            question = (f"How should {quoted} be drafted? A sector exclusion cannot make an exception for '{exception_words}', "
                        "so only the options below can be checked.")
        else:
            # A base of several rules (two companies, two labels) offers each of them, named, so none is lost.
            drafts = base_draft if isinstance(base_draft, list) else [base_draft]
            for index, draft in enumerate(drafts, start=1):
                rule = self._offer(draft, words, objective_id)
                several = len(drafts) > 1
                options.append(_option("every-company" + (f"-{index}" if several else ""),
                                       "Apply it to every company, including the exception you wrote"
                                       + (f" ({self._subject(draft)})" if several else ""),
                                       f"{_number_note(_rule_number(rule))} "
                                       f"Stricter than you wrote: '{exception_words}' is not left out of the rule.", rule=rule))
            question = (f"How should {quoted} be drafted? No rule type can make an exception for '{exception_words}', "
                        "so only the options below can be checked.")
        options.append(_option(*_KEEP_QUALITATIVE))
        return question, options

    def _ellipsis(self, quoted: str, words: str, objective_id: str | None, draft: Draft | dict[str, Any] | None,
                  source_quote: str | None) -> tuple[str, list[dict[str, Any]]]:
        """'Same for Enbridge': the earlier number is offered, never applied, because the words do not write it."""
        reuse = Draft.of(draft) if draft is not None else None
        if reuse is None or reuse.number is None or not source_quote:
            raise ValueError("ELLIPSIS needs a draft carrying the reused number and its source_quote")
        options = [
            _option("reuse-number", f"Use {_percent(reuse.number[0])} (from your words '{reuse.number[1]}')",
                    f"The number written in '{source_quote}' is used for this rule too. It stays inactive until you confirm it.",
                    rule=self._offer(reuse, words, objective_id)),
            _option(*_ENTER_NUMBER, rule=self._offer(reuse._replace(number=None, words=None), words, objective_id)),
            _option(*_KEEP_QUALITATIVE),
        ]
        return (f"Which number should apply to {quoted}? It seems to reuse the number written in '{source_quote}', "
                "which is not taken without your confirmation."), options

    def _scope_needed(self, quoted: str, words: str, objective_id: str | None,
                      number: tuple[float, str] | None) -> tuple[str, list[dict[str, Any]]]:
        """'No more than 10%' with no subject: the number is kept, what it limits is the investor's choice."""
        options = [
            _option("single-company-cap", "A maximum share of the portfolio in any single company",
                    f"{_LOOK_THROUGH_NOTE} {_number_note(number)}",
                    rule=self._draft("max_issuer_exposure", {"issuer_scope": "any"}, words, objective_id, number)),
            _option("replay-loss-budget", "A maximum loss when the allocation is replayed through calendar 2022",
                    f"{_REPLAY_NOTE} {_number_note(number)}",
                    rule=self._draft("scenario_loss_budget", {"scenario_id": SCENARIO_IDS[0]}, words, objective_id, number)),
            _option(*_KEEP_QUALITATIVE),
        ]
        return (f"What should {quoted} limit? The number can be checked as a maximum share in any single company "
                "or as a maximum loss when the allocation is replayed through calendar 2022."), options

    def _per_company_or_total(self, quoted: str, words: str, objective_id: str | None,
                              draft: Draft | dict[str, Any] | None) -> tuple[str, list[dict[str, Any]]]:
        """A per-company limit on flagged companies has no rule type; only the stricter total can be offered."""
        if draft is None:
            raise ValueError("PER_COMPANY_OR_TOTAL needs the aggregate controversy draft")
        rule = self._offer(draft, words, objective_id)
        number = _rule_number(rule)
        label = (f"At most {_percent(number[0])} in total across all flagged companies" if number
                 else "A maximum share in total across all flagged companies")
        options = [
            _option("total-across-flagged", label,
                    f"The number applies to the sum of every company with a recorded controversy, not to each one, so it is "
                    f"stricter than a limit per company. {_number_note(number)}", rule=rule),
            _option(*_KEEP_QUALITATIVE),
        ]
        return (f"Should {quoted} apply to each company or to the total? There is no per-company controversy limit, "
                "so the number can only be checked as a total across all flagged companies."), options

    def finish(self, *, text: str, persona_id: str, interpretation_id: str, created_at: str, model_id: str | None) -> dict[str, Any]:
        """The interpretation document. Contract validation is the caller's job (it decides retry or 502)."""
        return {
            "schema_version": SCHEMA_VERSION, "interpretation_id": interpretation_id, "persona_id": persona_id, "created_at": created_at,
            "model_id": model_id, "original_words": text, "objectives": self.objectives, "proposed_rules": self.rules,
            "unsupported": self.unsupported, "clarifications": self.clarifications,
        }
