"""Policy interpreter: the investor's words -> a DRAFT ``interpretation`` (contracts/api.md section 3).

What the model does and does not do
-----------------------------------
The model is a *reader*. After optional read-only lookups (``find_companies``, ``describe_sector``) it answers with
one structured object, the ``submit_reading`` tool (or the same object as JSON text): a list of clauses that only

* mark spans of the investor's text (evidence, subject, direction, quantity, scope ...), and
* pick codes from closed lists (intent, polarity, subject kind, direction, confidence, ambiguity ...), plus company
  ids and sector labels taken from lists the server built from the data snapshot.

Nothing the model writes is ever returned to the client:

* every sentence of the interpretation is a template in ``backend.agents.render`` or ``byb_contracts.templates``;
* a span is accepted only if it is found in the investor's text, and the text returned is the slice of the
  *request* text, never the model's string (``backend.agents.reading``);
* members that are not in the tool schema are never read, and the schema has no numeric member;
* ids, timestamps, ``status: PROPOSED``, ``origin``, ``model_id`` and ``original_words`` are set by the server.

Numbers
-------
The model cannot supply a number. ``backend.agents.compiler`` computes a threshold from the characters of the
model's quantity span (``backend.agents.quantity``) and keeps it only when every check of its lattice passes;
every doubt can only turn a rule into a question or an unsupported entry, never the reverse.

Layout
------
``reference.py`` indexes the snapshot; ``reading.py`` holds the tool schema and parses the answer into a
``Reading``; ``compiler.py`` turns a ``Reading`` into the document; ``render.py`` writes every output item. This
module runs the bounded agent (``Interpreter``) and the final contract check.

Failure
-------
An answer whose shape is unusable (not JSON, truncated, a required member missing, more than half of its clauses
broken) or a draft that still fails ``byb_contracts.interpretation_errors`` after the offending items are dropped is
retried once if the time budget allows, then ``InterpreterFailed`` (502). A model error is ``InterpreterFailed``;
running out of the time budget is ``InterpreterTimeout`` (504). Nothing is stored and no policy is read or written
here, and the engine is never called: this module cannot produce a verdict.
"""

from __future__ import annotations

import json
import re
import uuid
from collections import Counter
from typing import Any, Callable

from byb_contracts import interpretation_errors
from byb_contracts.constants import INTERPRET_TIMEOUT_SECONDS, SCENARIO_IDS

from backend.agents.bedrock_client import FAILURE_DEADLINE_EXCEEDED, ModelCallError
from backend.agents.compiler import compile_reading
from backend.agents.prompts import (
    DESCRIBE_SECTOR_TOOL_NAME,
    FIND_COMPANIES_TOOL_NAME,
    INTERPRETER_LOOKUP_DONE_NOTE,
    INTERPRETER_PROMPT_VERSION,
    INTERPRETER_SYSTEM_PROMPT,
    INTERPRETER_TOOL_NAME,
    build_interpreter_message,
)
from backend.agents.reading import FIND_COMPANIES_SCHEMA, Reading, _Rejected, parse_reading, resolve_span, tool_config
from backend.agents.reference import MAX_COMPANY_CANDIDATES, _Reference
from backend.agents.render import (  # noqa: F401  (re-exported: tests and scripts import them from here)
    _THEME_UNSUPPORTED,
    UNSUPPORTED_REASONS,
    draft_rule,
)
from backend.agents.schema import validate as schema_errors
from backend.common import log
from backend.common.clock import to_iso

MAX_LOOKUPS_PER_ROUND = 6
# A contract error names the item it is about ("proposed_rules[2]: ...", "$.clarifications[0].options: ...").
_ITEM_PATH_RE = re.compile(r"\b(objectives|proposed_rules|unsupported|clarifications)\[(\d+)\]")


class InterpreterFailed(Exception):
    """No valid draft could be produced (model error, or output rejected after the bounded retry): 502."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class InterpreterTimeout(Exception):
    """The time budget ran out before a valid draft existed: 504."""


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


# --------------------------------------------------------------------------
# The final check of a compiled draft
# --------------------------------------------------------------------------


def _drop_items(draft: dict[str, Any], errors: list[str]) -> bool:
    """Remove every item an error names. False when an error names no item (the document itself is broken)."""
    doomed: dict[str, set[int]] = {}
    for error in errors:
        match = _ITEM_PATH_RE.search(error)
        if match is None:
            return False
        doomed.setdefault(match.group(1), set()).add(int(match.group(2)))
    for name, indexes in doomed.items():
        draft[name] = [item for index, item in enumerate(draft[name]) if index not in indexes]
    return True


def _validated(draft: dict[str, Any], interpretation_id: str) -> dict[str, Any]:
    """The draft once it passes the contract. The offending items are dropped once (each is a server bug, logged by
    path only) and the rest is checked again; a second failure rejects the answer."""
    errors = interpretation_errors(draft)
    if not errors:
        return draft
    log.error("interpreter_draft_items_dropped", interpretation_id=interpretation_id,
              paths=sorted({m.group(0) for m in map(_ITEM_PATH_RE.search, errors) if m}))
    if not _drop_items(draft, errors) or interpretation_errors(draft):
        raise _Rejected("draft_fails_contract_validation")
    return draft


def build_interpretation(raw: dict[str, Any], *, text: str, persona_id: str, reference: _Reference, interpretation_id: str,
                         created_at: str, model_id: str | None, clarification_mode: bool = False,
                         lookups: dict[str, list[str]] | None = None) -> dict[str, Any]:
    """The contract document for one raw reading (the ``submit_reading`` input), exactly as ``Interpreter`` builds
    it. For tests and scripts. Raises ``_Rejected`` when the reading cannot be used."""
    reading = parse_reading(raw, text)
    return _validated(compile_reading(reading, text=text, persona_id=persona_id, reference=reference, lookups=lookups or {},
                                      interpretation_id=interpretation_id, created_at=created_at, model_id=model_id,
                                      clarification_mode=clarification_mode), interpretation_id)


def _reading_counts(reading: Reading, downgrades: Counter) -> dict[str, Any]:
    """What the finish log says about a reading: sizes and reason codes, never text."""
    return {"clauses": len(reading.clauses), "dropped_clauses": len(reading.dropped), "downgrades": dict(sorted(downgrades.items()))}


# --------------------------------------------------------------------------
# The interpreter
# --------------------------------------------------------------------------


class Interpreter:
    """``model`` is a ``BedrockConverse`` (or anything with its ``converse`` signature and ``model_id``).

    The interpreter is a small bounded agent. In one attempt the model may first call read-only lookup tools
    (``find_companies``, ``describe_sector``) that the server answers from the data snapshot, then submits its
    reading with ``submit_reading``. Bounds: ``max_outputs`` submissions (an unusable one starts one fresh attempt
    with a retry note), ``max_lookup_rounds`` lookup turns in total, at most ``MAX_LOOKUPS_PER_ROUND`` tool calls per
    turn, and a model call is started only when ``call_budget_seconds`` remain before the deadline.
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
                "companies": [reference.describe(issuer_id) for issuer_id in companies],
                "scenario_ids": list(SCENARIO_IDS)}

    @staticmethod
    def _lookup(use: dict[str, Any], text: str, reference: _Reference, lookups: dict[str, list[str]], allowed: bool) -> dict[str, Any]:
        """Run one lookup tool call. The answer is data from the snapshot. A company lookup is recorded under the
        investor's own words it was made for, so the compiler can tie its ids to the clause those words are in."""
        tool_use_id = use.get("toolUseId")

        def error(code: str) -> dict[str, Any]:
            return {"toolResult": {"toolUseId": tool_use_id, "status": "error", "content": [{"text": f"Lookup not completed ({code})."}]}}

        if not allowed:
            return error("no_lookups_left_submit_now")
        arguments = use.get("input")
        if use.get("name") == FIND_COMPANIES_TOOL_NAME:
            if not isinstance(arguments, dict) or schema_errors(arguments, FIND_COMPANIES_SCHEMA):
                return error("invalid_arguments")
            span = resolve_span(text, arguments["words"])
            if span is None:
                return error("words_not_in_the_investors_text")
            words = span[0]
            matches = reference.find(words)
            lookups[words] = sorted(set(lookups.get(words, [])) | set(matches))
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
        hinted = reference.companies_in(text)
        lookups: dict[str, list[str]] = {}  # the investor's words -> ids find_companies resolved them to
        interpretation_id = f"int-{self._new_id()[:12]}"
        rejected = None
        calls = 0
        lookup_rounds = 0
        lookup_tools = {FIND_COMPANIES_TOOL_NAME, DESCRIBE_SECTOR_TOOL_NAME}
        # One tool config for every call of this request, the retry included: Bedrock checks a reasoning block's
        # signature against the tools it was made with, so tools that change between turns fail the next call.
        tools = tool_config(reference.sectors, reference.ids)
        for attempt in range(1, self._max_outputs + 1):
            found = {issuer_id for ids in lookups.values() for issuer_id in ids}
            listed = sorted(set(hinted) | found)[:MAX_COMPANY_CANDIDATES]
            messages: list[dict[str, Any]] = [{"role": "user", "content": [
                {"text": build_interpreter_message(text, self._reference_data(reference, listed), retry=attempt > 1)}]}]
            while True:
                if deadline - self._clock.time() < self._call_budget:
                    if rejected is None:
                        self._done("timeout", interpretation_id, text, calls, lookup_rounds=lookup_rounds)
                        raise InterpreterTimeout()
                    break  # an answer was received and rejected; there is no time for the retry
                try:
                    calls += 1
                    response, record = self._model.converse(system=INTERPRETER_SYSTEM_PROMPT, messages=messages, tool_config=tools,
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
                    results = [self._lookup(use, text, reference, lookups, more) for use in uses]
                    if not more:
                        results.append({"text": INTERPRETER_LOOKUP_DONE_NOTE})
                    messages += [{"role": "assistant", "content": content}, {"role": "user", "content": results}]
                    log.info("interpreter_lookup", interpretation_id=interpretation_id, round=lookup_rounds, calls=len(uses), answered=more)
                    continue
                downgrades: Counter = Counter()
                try:
                    reading = parse_reading(_extraction(response), text)
                    draft = _validated(compile_reading(
                        reading, text=text, persona_id=persona_id, reference=reference, lookups=lookups,
                        interpretation_id=interpretation_id, created_at=to_iso(self._clock.time()),
                        model_id=getattr(self._model, "model_id", None), clarification_mode=clarification_mode,
                        downgrades=downgrades), interpretation_id)
                except _Rejected as error:
                    rejected = error.reason
                    log.warning("interpreter_output_rejected", interpretation_id=interpretation_id, attempt=attempt, reason=rejected,
                                stop_reason=record.get("stop_reason"), usage=record.get("usage"))
                    break
                except (ValueError, KeyError, TypeError, IndexError) as error:
                    # A reading the compiler could not render is a server bug, never a reason to answer 500: the answer
                    # is treated as unusable (one fresh attempt, then 502), and the failure is logged without text.
                    rejected = "compiler_error"
                    log.error("interpreter_compiler_error", interpretation_id=interpretation_id, attempt=attempt,
                              error_type=type(error).__name__)
                    break
                self._done("ok", interpretation_id, text, calls, usage=record.get("usage"), wall_ms=record.get("wall_ms"),
                           lookup_rounds=lookup_rounds, objectives=len(draft["objectives"]), proposed_rules=len(draft["proposed_rules"]),
                           clarifications=len(draft["clarifications"]), unsupported=len(draft["unsupported"]), **_reading_counts(reading, downgrades))
                return draft
            if deadline - self._clock.time() < self._call_budget:
                break
        self._done("rejected", interpretation_id, text, calls, reason=rejected)
        raise InterpreterFailed(rejected or "rejected")

    @staticmethod
    def _done(outcome: str, interpretation_id: str, text: str, attempts: int, **fields: Any) -> None:
        # Lengths, ids, codes and the outcome only: never the investor's text and never the model's answer.
        log.info("interpreter_finished", outcome=outcome, interpretation_id=interpretation_id, text_chars=len(text), attempts=attempts,
                 prompt_version=INTERPRETER_PROMPT_VERSION, **fields)
