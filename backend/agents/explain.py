"""Explanation statements (``investigation_job.schema.json#/$defs/statement``).

Decisive sentences are TEMPLATE statements: the engine's own ``reason`` strings with the evidence
ids the engine attached to them. They are always present and never depend on the model.

The model may add context statements. One is kept (``MODEL_VALIDATED``) only when it passes every
check of ``accept_model_statements``; otherwise it is dropped - never returned, never flagged and
shown - and the rejection goes to the trace:

* it is a claim about evidence: it holds at least one ``[[evidence_id]]`` placeholder, every
  placeholder is among the ids it cites, and every cited id exists in ``result.evidence``;
* the model never types a figure (a statement with any other digit is rejected), and the server
  prints, in place of each placeholder, the record's value TOGETHER WITH what the record measures:
  metric, subject, portfolio state and period come from the record, not from the model's words.
  A value can therefore not be passed off as another metric, asset, unit or period
  (BUILD_BRIEF section 6: explanations are not validated by searching for a matching number);
* it names no instrument, fund or company other than the subjects of the records it cites;
* it uses no unit or period word of its own (currency, shares, days, months, years...);
* it states no verdict, comparison with a limit, reassurance, forecast or advice: those words are
  refused whatever the rest says, because verdicts are the engine's (``VERDICT_RE``, ``ADVICE_RE``);
* plain text only, bounded length and count, no markup, no links.

This is a filter on wording, not a proof of meaning. What it guarantees is narrower and checkable:
no model-typed number, no value without its server-printed description, no verdict vocabulary.
"""

from __future__ import annotations

import json
import re
from typing import Any

from backend.engine.text import num, pct

MAX_MODEL_STATEMENTS = 3
MAX_STATEMENT_CHARS = 400  # of model text; the server-printed descriptions come on top
DISCLOSURE = "This is a simulation on a fictional portfolio. It is not advice, and no trade is made."

_PLACEHOLDER_RE = re.compile(r"\[\[([A-Za-z0-9][A-Za-z0-9._:-]{0,127})\]\]")
_FORBIDDEN_RE = re.compile(r"[<>`\[\]{}\\\x00-\x1f\x7f]|https?:|www\.", re.IGNORECASE)
ADVICE_RE = re.compile(
    r"\b(recommend\w*|advis\w*|suggest\w*|should|ought|must|need to|better to|worth\w*|attractive|opportunit\w*|"
    r"buy|buying|sell|selling|hold|holding on|invest|go ahead|proceed|guarantee\w*|certain(ly)?|definitely|"
    r"will (rise|fall|go|outperform|underperform|recover|drop|grow)|expect\w*|forecast\w*|predict\w*|likely|unlikely|price target)\b",
    re.IGNORECASE)
# Verdicts, comparisons with a limit and reassurance belong to the engine's template statements.
VERDICT_RE = re.compile(
    r"\b(pass(es|ed|ing)?|fail(s|ed|ing|ure|ures)?|breach\w*|violat\w*|compl(y|ies|ied|iant|iance)|non-?compliant|conform\w*|"
    r"allow\w*|permit\w*|acceptable|accept(s|ed)?|approv\w*|reject\w*|satisf\w*|meet(s|ing)?|met|respect(s|ed)?|"
    r"safe\w*|risk-?free|risky|danger\w*|fine|ok|okay|good|bad|great|excellent|problem\w*|issue|issues|worr\w*|concern\w*|alarm\w*|"
    r"within|inside|exceed\w*|below|above|under|over|beyond|less|more|fewer|lower than|higher than|greater|smaller|"
    r"too (much|high|low|little|large|small)|enough|no rule|every rule|all rules|each rule|any rule|unknown|zero|none|nothing|no exposure)\b",
    re.IGNORECASE)
_UNIT_WORDS = {
    "price": re.compile(r"\b(shares?|units?|days?|bps|basis points?)\b", re.IGNORECASE),
    "fx_rate": re.compile(r"\b(shares?|units?|days?|bps|basis points?|dollars?)\b", re.IGNORECASE),
    "days": re.compile(r"[$€£]|\b(dollars?|usd|cad|eur|shares?|units?|bps|basis points?|per ?cent|percent\w*)\b", re.IGNORECASE),
    "count": re.compile(r"[$€£]|\b(dollars?|usd|cad|eur|days?|bps|basis points?|per ?cent|percent\w*)\b", re.IGNORECASE),
    "fraction": re.compile(r"[$€£]|\b(dollars?|usd|cad|eur|shares?|units?|days?|bps|basis points?)\b", re.IGNORECASE),
}
_PERIOD_RE = re.compile(
    r"\b(today|yesterday|tomorrow|currently|now|recent\w*|last|next|this (year|month|week|quarter)|years?|months?|weeks?|quarters?|annual\w*|"
    r"january|february|march|april|june|july|august|september|october|november|december)\b", re.IGNORECASE)
_ALLOWED_CAPITALS = {"I", "CAD", "USD", "ETF", "FX"}

METRIC_PHRASES = {
    "position_weight": "direct weight",
    "cash_weight": "cash weight",
    "cash_after_purchase": "cash weight after the purchase",
    "fund_constituent_weight": "weight inside the fund, as its holdings file reports it",
    "fund_coverage_fraction": "share of the fund that its holdings file reports",
    "unattributed_fund_weight": "portfolio weight held through the fund that its holdings file does not report",
    "issuer_direct_exposure": "exposure held directly",
    "issuer_exposure_via_fund": "exposure held through the fund",
    "exposure_lower": "lower bound of the measured exposure",
    "exposure_upper": "upper bound of the measured exposure",
    "rule_threshold": "limit set by the rule",
    "gap_to_limit": "measured value minus the limit",
    "scenario_instrument_return": "return over the replayed period",
    "scenario_terminal_return": "portfolio return over the replayed period",
    "scenario_max_drawdown": "largest drawdown over the replayed period",
    "scenario_loss": "portfolio loss over the replayed period",
    "price_adj_close": "adjusted closing price",
    "fx_usdcad": "USD/CAD exchange rate",
    "fx_rate_age_days": "age of the exchange rate, in days",
    "price_age_days": "age of the price, in days",
    "max_compliant_final_weight": "final direct weight computed by the boundary calculation",
    "max_compliant_additional_purchase": "additional purchase computed by the boundary calculation",
}
_STATE_PHRASES = {"STARTING": "before the purchase", "PROPOSED": "after the purchase"}
_KIND_PHRASES = {"INSTRUMENT": "instrument", "ISSUER": "company", "FUND": "fund", "PORTFOLIO": "portfolio", "RULE": "rule", "FX": "currency pair"}


def _statement(index: int, text: str, evidence_ids: list[str], rendered_by: str) -> dict[str, Any]:
    return {"statement_id": f"st-{index}", "text": text, "evidence_ids": list(dict.fromkeys(evidence_ids)), "rendered_by": rendered_by}


def template_statements(result: dict[str, Any]) -> list[dict[str, Any]]:
    """Every decisive sentence, from the engine. Order: execution, funding, rules, findings, gaps, maximum, disclosure."""
    known = {record["evidence_id"] for record in result.get("evidence", [])}
    out: list[tuple[str, list[str]]] = []
    execution = result["execution"]
    if execution["status"] != "OK":
        out.append((f"The request was not evaluated: {execution['message']}", []))
    feasibility = result.get("feasibility")
    if feasibility and feasibility["status"] == "INSUFFICIENT_CASH":
        cash = [r["evidence_id"] for r in result["evidence"] if r["metric_id"] in ("cash_after_purchase", "cash_weight")]
        out.append((
            f"The purchase cannot be funded from cash: it needs {pct(feasibility['additional_purchase'])} of the portfolio and "
            f"{pct(feasibility['cash_before'])} is held in cash. This is a funding result, not a rule result, and it does not show that the rules contradict each other.",
            cash,
        ))
    for conflict in result["policy_consistency"]["conflicts"]:
        out.append((str(conflict.get("reason") or "Two confirmed rules cannot both be satisfied."), list(conflict.get("evidence_ids", []))))
    for entry in result.get("rule_results", []):
        out.append((f"Rule {entry['rule_id']}: {entry['status']}. {entry['reason']}", entry["evidence_ids"]))
    for finding in result.get("starting_portfolio_findings", []):
        out.append((f"Before any purchase (rule {finding['rule_id']}): {finding['reason']}", finding["evidence_ids"]))
    for skipped in result.get("rules_not_evaluated", []):
        out.append((f"Rule {skipped['rule_id']} was not evaluated: {skipped['reason']}", []))
    maximum = result.get("max_compliant")
    if maximum:
        out.append((maximum["reason"], maximum["evidence_ids"]))
    out.append((DISCLOSURE, []))
    return [_statement(i + 1, text, [e for e in ids if e in known], "TEMPLATE") for i, (text, ids) in enumerate(out)]


def _render_value(record: dict[str, Any]) -> str | None:
    value, unit = record.get("value"), record.get("unit")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None  # dates and text are not printed inside model sentences
    if unit == "fraction":
        return pct(value)
    if unit in ("count", "days"):
        return str(int(value)) if float(value).is_integer() else None
    if unit in ("price", "fx_rate"):
        return num(value)
    return None


def describe(record: dict[str, Any]) -> str | None:
    """What a record measures, in the service's words: metric, subject, state, period. None if it has no phrase."""
    phrase = METRIC_PHRASES.get(record.get("metric_id"))
    subject = record.get("subject") or {}
    if phrase is None or subject.get("kind") not in _KIND_PHRASES:
        return None
    parts = [phrase, f"{_KIND_PHRASES[subject['kind']]} {subject['id']}"]
    if subject.get("via_fund_id"):
        parts.append(f"through {subject['via_fund_id']}")
    if subject.get("portfolio_state") in _STATE_PHRASES:
        parts.append(_STATE_PHRASES[subject["portfolio_state"]])
    period = record.get("period") or {}
    if period.get("type") == "AS_OF":
        parts.append(f"as of {period['date']}")
    elif period.get("type") == "RANGE":
        parts.append(f"{period['start_date']} to {period['end_date']}")
    if record.get("currency"):
        parts.append(str(record["currency"]))
    return ", ".join(parts)


def _render_cited(record: dict[str, Any]) -> str | None:
    """The value with its own description: what replaces a placeholder."""
    value, description = _render_value(record), describe(record)
    return None if value is None or description is None else f"{value} ({description})"


def known_subjects(result: dict[str, Any], extra_ids: Any = ()) -> dict[str, str]:
    """casefolded word -> subject id, for every instrument, fund and company the result or the data snapshot knows."""
    ids: set[str] = {i for i in extra_ids if isinstance(i, str) and i}
    for record in result.get("evidence", []):
        subject = record.get("subject") or {}
        if subject.get("kind") in ("INSTRUMENT", "ISSUER", "FUND"):
            ids.add(subject["id"])
        if subject.get("via_fund_id"):
            ids.add(subject["via_fund_id"])
    request = result.get("purchase_request") or {}
    if isinstance(request.get("instrument_id"), str):
        ids.add(request["instrument_id"])
    for fund in result.get("data_coverage") or []:
        ids.add(fund["fund_id"])
    words: dict[str, str] = {}
    for subject_id in ids:
        # Case-insensitive only for words of five letters or more: a short ticker such as CASH or META is also an
        # ordinary word, and is caught in capitals by the all-capitals net of _foreign_names.
        for word in (subject_id, re.split(r"[_.\s-]+", subject_id)[0]):  # "EXXON_MOBIL" is also written "Exxon"
            if len(word) >= 5:
                words.setdefault(word.casefold(), subject_id)
    return words


def parse_model_answer(text: str) -> list[Any]:
    """The model's final text must be one JSON object ``{"statements": [...]}``. Anything else yields nothing."""
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return []
    try:
        document = json.loads(text[start:end + 1])
    except (ValueError, RecursionError):
        return []
    statements = document.get("statements") if isinstance(document, dict) else None
    return statements if isinstance(statements, list) else []


def _foreign_names(outside: str, subjects: dict[str, str], about: set[str]) -> bool:
    """True when the text names an instrument, fund or company that the cited records are not about.

    Three nets, from precise to coarse: a word that is a known id or the first word of one; any all-capitals
    token (a ticker); any capitalised word that does not start a sentence (a proper noun).
    """
    allowed = {word for subject in about for word in (subject.casefold(), re.split(r"[_.\s-]+", subject)[0].casefold())}
    sentence_start = True
    for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9_.&'-]*|[.!?;:]", outside):
        if token in ".!?;:":
            sentence_start = True
            continue
        word = token.rstrip(".'").casefold()
        starts, sentence_start = sentence_start, False
        if word in allowed:
            continue
        if word in subjects:
            return True
        letters = re.sub(r"[^A-Za-z]", "", token)
        if len(letters) >= 2 and letters.isupper() and token.rstrip(".") not in _ALLOWED_CAPITALS:
            return True
        if not starts and token[0].isupper() and token not in _ALLOWED_CAPITALS:
            return True
    return False


def accept_model_statements(candidates: list[Any], result: dict[str, Any], first_index: int,
                            known_ids: Any = ()) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(accepted statements, rejections for the trace). A rejected statement is not returned anywhere else.

    ``known_ids``: instrument, fund and issuer ids of the data snapshot, so that a company the result does not
    mention is still recognised as "another company".
    """
    records = {record["evidence_id"]: record for record in result.get("evidence", [])}
    subjects = known_subjects(result, known_ids)
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    def reject(index: int, why: str) -> None:
        rejected.append({"index": index, "reason": why})

    for index, candidate in enumerate(candidates):
        if len(accepted) >= MAX_MODEL_STATEMENTS:
            reject(index, "more statements than allowed")
            continue
        if not isinstance(candidate, dict) or not isinstance(candidate.get("text"), str) or not isinstance(candidate.get("evidence_ids"), list):
            reject(index, "not an object with text and evidence_ids")
            continue
        ids = candidate["evidence_ids"]
        if not ids or not all(isinstance(i, str) and i in records for i in ids):
            reject(index, "cites no evidence, or an evidence id that is not in the result")
            continue
        raw = candidate["text"].strip()
        if len(raw) > MAX_STATEMENT_CHARS:
            reject(index, "too long")
            continue
        placeholders = _PLACEHOLDER_RE.findall(raw)
        if not placeholders:
            reject(index, "no value from an evidence record: a sentence without one is opinion, not evidence")
            continue
        if any(p not in ids for p in placeholders):
            reject(index, "a placeholder is not among the cited evidence ids")
            continue
        outside = _PLACEHOLDER_RE.sub(" ", raw)
        if re.search(r"\d", outside):
            reject(index, "a figure was typed instead of cited")
            continue
        if _FORBIDDEN_RE.search(outside):
            reject(index, "markup or a link")
            continue
        if ADVICE_RE.search(outside):
            reject(index, "advice or forecast wording")
            continue
        if VERDICT_RE.search(outside):
            reject(index, "verdict, comparison or reassurance wording: verdicts are the engine's")
            continue
        if _PERIOD_RE.search(outside):
            reject(index, "a period stated in the model's own words")
            continue
        cited = [records[i] for i in ids]
        if any(_UNIT_WORDS[records[p]["unit"]].search(outside) for p in placeholders if records[p]["unit"] in _UNIT_WORDS):
            reject(index, "a unit that is not the cited record's unit")
            continue
        about = {r["subject"]["id"] for r in cited} | {r["subject"]["via_fund_id"] for r in cited if r["subject"].get("via_fund_id")}
        if _foreign_names(outside, subjects, about):
            reject(index, "names an instrument, fund or company that no cited record is about")
            continue
        values = {p: _render_cited(records[p]) for p in placeholders}
        if any(v is None for v in values.values()):
            reject(index, "a placeholder cites a record without a printable number")
            continue
        text = " ".join(_PLACEHOLDER_RE.sub(lambda m: values[m.group(1)], raw).split())
        accepted.append(_statement(first_index + len(accepted), text, ids, "MODEL_VALIDATED"))
    return accepted, rejected
