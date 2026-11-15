"""Explanation statements (``investigation_job.schema.json#/$defs/statement``).

Decisive sentences are TEMPLATE statements: the engine's own ``reason`` strings with the evidence
ids the engine attached to them. The model may add context statements, kept only when they pass
``accept_model_statements``:

* the model never types a figure. It writes ``[[evidence_id]]`` where a value belongs, and the
  server prints that record's value from the engine result. A statement with any other digit is
  rejected. So a number shown always comes from the record cited next to it (BUILD_BRIEF section 6:
  explanations are not validated by searching for a matching number);
* every cited id exists in ``result.evidence`` and every placeholder is among the cited ids;
* plain text only, bounded length and count, no markup, no links, no advice wording.

A rejected statement is dropped (the template statements already say everything decisive) and the
rejection is recorded in the trace.
"""

from __future__ import annotations

import json
import re
from typing import Any

from backend.engine.text import num, pct

MAX_MODEL_STATEMENTS = 3
MAX_STATEMENT_CHARS = 600
DISCLOSURE = "This is a simulation on a fictional portfolio. It is not advice, and no trade is made."

_PLACEHOLDER_RE = re.compile(r"\[\[([A-Za-z0-9][A-Za-z0-9._:-]{0,127})\]\]")
_FORBIDDEN_RE = re.compile(r"[<>`\[\]{}\\\x00-\x1f\x7f]|https?:|www\.", re.IGNORECASE)
_ADVICE_RE = re.compile(
    r"\b(recommend\w*|advis\w*|you should|should (buy|sell|hold)|i suggest|we suggest|guarantee\w*|will (rise|fall|go up|go down|outperform)|"
    r"expected return|price target)\b", re.IGNORECASE)


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


def accept_model_statements(candidates: list[Any], result: dict[str, Any], first_index: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(accepted statements, rejections for the trace)."""
    records = {record["evidence_id"]: record for record in result.get("evidence", [])}
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
        placeholders = _PLACEHOLDER_RE.findall(raw)
        if any(p not in ids for p in placeholders):
            reject(index, "a placeholder is not among the cited evidence ids")
            continue
        outside = _PLACEHOLDER_RE.sub(" ", raw)
        if re.search(r"\d", outside):
            reject(index, "a figure was typed instead of cited")
            continue
        if _FORBIDDEN_RE.search(outside) or _ADVICE_RE.search(outside):
            reject(index, "markup, a link or advice wording")
            continue
        values = {p: _render_value(records[p]) for p in placeholders}
        if any(v is None for v in values.values()):
            reject(index, "a placeholder cites a record without a printable number")
            continue
        text = " ".join(_PLACEHOLDER_RE.sub(lambda m: values[m.group(1)], raw).split())
        if not text or len(text) > MAX_STATEMENT_CHARS:
            reject(index, "empty or too long")
            continue
        accepted.append(_statement(first_index + len(accepted), text, ids, "MODEL_VALIDATED"))
    return accepted, rejected
