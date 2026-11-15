"""Explanation statements (``investigation_job.schema.json#/$defs/statement``).

No sentence written by the model is ever returned to the client.

* Decisive sentences are the engine's own ``reason`` strings with the evidence ids the engine
  attached to them (``template_statements``). They never depend on the model.
* The model can only SELECT: its final answer is ``{"highlights": [{"template": "<id>",
  "evidence_id": "<id>"}]}``. ``template`` is one of the closed set ``HIGHLIGHT_TEMPLATES`` and
  ``evidence_id`` must be a record of the engine result. There is no text slot. An item with any
  other member, an unknown template, an unknown evidence id, or a record the template cannot print
  is dropped. The server then writes the sentence itself, from the record alone: what the record
  measures (metric, subject, portfolio state, period) and its value.

Such a sentence is ``rendered_by: TEMPLATE``: the contract defines TEMPLATE as deterministic text
and MODEL_VALIDATED as model-written text, and this text is not model-written. Raw model output is
kept only in the private trace (``traces/<id>.json``).
"""

from __future__ import annotations

import json
from typing import Any

from backend.engine.text import num, pct

DISCLOSURE = "This is a simulation on a fictional portfolio. It is not advice, and no trade is made."

MAX_HIGHLIGHTS = 3
HIGHLIGHT_VALUE = "HIGHLIGHT_VALUE"
# template id -> sentence. The only slots are filled by the server from one evidence record.
HIGHLIGHT_TEMPLATES = {HIGHLIGHT_VALUE: "Evidence looked at during the investigation: {description}: {value}."}
_ITEM_KEYS = {"template", "evidence_id"}

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


def parse_model_answer(text: str) -> list[Any]:
    """The model's final text must be one JSON object ``{"highlights": [...]}``. Anything else yields nothing."""
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return []
    try:
        document = json.loads(text[start:end + 1])
    except (ValueError, RecursionError):
        return []
    highlights = document.get("highlights") if isinstance(document, dict) else None
    return highlights if isinstance(highlights, list) else []


def render_highlights(candidates: list[Any], result: dict[str, Any], first_index: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(server-written statements for the model's valid selections, rejections for the trace)."""
    records = {record["evidence_id"]: record for record in result.get("evidence", [])}
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, candidate in enumerate(candidates):
        if len(accepted) >= MAX_HIGHLIGHTS:
            rejected.append({"index": index, "reason": "more selections than allowed"})
            continue
        if not isinstance(candidate, dict) or set(candidate) != _ITEM_KEYS:
            rejected.append({"index": index, "reason": "not exactly a template id and an evidence id"})
            continue
        template, evidence_id = candidate["template"], candidate["evidence_id"]
        if not isinstance(template, str) or template not in HIGHLIGHT_TEMPLATES:
            rejected.append({"index": index, "reason": "unknown template id"})
            continue
        if not isinstance(evidence_id, str) or evidence_id not in records or evidence_id in seen:
            rejected.append({"index": index, "reason": "unknown or repeated evidence id"})
            continue
        record = records[evidence_id]
        value, description = _render_value(record), describe(record)
        if value is None or description is None:
            rejected.append({"index": index, "reason": "the template cannot print this kind of record"})
            continue
        seen.add(evidence_id)
        text = HIGHLIGHT_TEMPLATES[template].format(description=description, value=value)
        accepted.append(_statement(first_index + len(accepted), text, [evidence_id], "TEMPLATE"))
    return accepted, rejected
