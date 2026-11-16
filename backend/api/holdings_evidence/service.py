"""One investigation: scan the funds, bound the exposure, answer the question. Pure apart from the optional model call."""

from __future__ import annotations

import re
from typing import Any

from backend.agents.themes import sectors_written_in
from backend.engine.core import held_positions

from . import bounds as bounds_module
from . import wording as explain
from .scanner import (BASIS_ISSUER_FILE, EVIDENCE_UNAVAILABLE, LOCAL_ONLY_LIMITATION, STATUS_INSUFFICIENT, STATUS_PARTIAL, STATUS_SUFFICIENT,
                      UnknownFund, pct, public, scan_fund)

RESPONSE_VERSION = "evidence-investigator/1"
MAX_SECTORS_PER_QUESTION = 2
UNCONFIRMED_RULES = "fictional scenario offer — not confirmed by the investor"


def _sector_labels(registry: dict, funds: dict) -> list[str]:
    labels = {instrument.get("sector") for instrument in registry.values() if not instrument.get("is_fund")}
    for fund in funds.values():
        labels.update(row.get("sector") for row in fund.get("holdings", []) if isinstance(row, dict))
    return sorted(label for label in labels if isinstance(label, str) and label)


_COMPANY_RE = re.compile(r"\b(compan(?:y|ies)|issuers?|single (?:name|stock|company)|one stock)\b", re.IGNORECASE)
_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9]*(?:\.[A-Za-z]{1,3})?")


def fund_named_in(question: str, registry: dict) -> str | None:
    """The one fund of the registry whose identifier (``XIU.TO`` or its ticker ``XIU``) is written in the question, else ``None``.

    Recognition only: the identifier must already be in the snapshot. Two different funds named -> no focus is guessed.
    """
    tickers: dict[str, str] = {}
    for instrument_id, instrument in registry.items():
        if instrument.get("is_fund"):
            tickers[instrument_id.upper()] = instrument_id
            tickers.setdefault(instrument_id.split(".")[0].upper(), instrument_id)
    # An identifier counts when written in capitals ("SPY"), so an ordinary word is never taken for a ticker.
    found = {tickers[token] for token in _TOKEN_RE.findall(question) if token.isupper() and token in tickers}
    return next(iter(found)) if len(found) == 1 else None


def portfolio_coverage(portfolio: dict, registry: dict, scans: dict[str, dict]) -> dict[str, Any]:
    """Shares of the PORTFOLIO: verified (cash, direct holdings, looked-through fund holdings), unresolved, and not looked through."""
    cash = portfolio.get("cash_weight") or 0.0
    verified, unresolved, out_of_scope = cash, 0.0, 0.0
    funds = []
    for instrument_id, weight in held_positions(portfolio):
        instrument = registry.get(instrument_id) or {}
        if not instrument.get("is_fund"):
            verified += weight
            continue
        scan = scans[instrument_id]
        calc = scan["_calc"]
        if not instrument.get("equity_scope"):
            out_of_scope += weight
            part_verified, part_unresolved = None, None
        elif calc["basis_valid"]:
            part_verified, part_unresolved = weight * calc["verified"], weight * calc["unresolved"]
            verified += part_verified
            unresolved += part_unresolved
        else:
            part_verified, part_unresolved = None, weight
            unresolved += weight
        funds.append({"fund": instrument_id, "portfolio_weight_pct": pct(weight), "in_rule_scope": bool(instrument.get("equity_scope")),
                      "coverage_basis": scan["coverage_basis"], "status": scan["status"], "snapshot_date": scan["snapshot_date"],
                      "fund_verified_weight_pct": scan["verified_weight_pct"], "fund_unresolved_weight_pct": scan["unresolved_weight_pct"],
                      "verified_portfolio_pct": pct(part_verified), "unresolved_portfolio_pct": pct(part_unresolved)})
    return {"verified_weight_pct": pct(verified), "unresolved_weight_pct": pct(unresolved), "not_looked_through_weight_pct": pct(out_of_scope),
            "cash_weight_pct": pct(cash), "funds": funds,
            "basis": "Shares of the portfolio. Verified = cash + direct holdings + each equity fund's verified share x its portfolio weight. "
                     "Unresolved = fund weight not attributed to a holding (a fund without a usable holdings file counts in full). "
                     "Bond and commodity funds are not looked through (outside the rules' scope) and are shown separately."}


def _overall(statuses: list[str]) -> str:
    if not statuses:
        return STATUS_SUFFICIENT
    if STATUS_INSUFFICIENT in statuses:
        return STATUS_INSUFFICIENT
    return STATUS_PARTIAL if STATUS_PARTIAL in statuses else STATUS_SUFFICIENT


def investigate(*, snapshot: Any, scenario: dict, policy: dict | None, fund_id: str | None, question: str, explainer: Any = None) -> dict[str, Any]:
    """The structured answer. Raises ``UnknownFund`` when ``fund_id`` is not a fund of the snapshot.

    ``policy`` is a stored, confirmed policy version (or ``None``); limits are read from it or, without one, from the
    scenario's own offers (labelled as not confirmed). Nothing the caller sends is used as a number.
    """
    registry = snapshot.registry
    funds = snapshot.holdings.get("funds", {})
    sources = snapshot.sources.get("sources", {})
    portfolio = scenario["portfolio"]
    valuation_date = portfolio.get("valuation_date")

    held_funds = [instrument_id for instrument_id, _ in held_positions(portfolio) if (registry.get(instrument_id) or {}).get("is_fund")]
    scans = {held: scan_fund(held, registry, funds, sources, valuation_date) for held in held_funds}
    focus = None
    fund_recognised = None
    if fund_id is None:
        fund_recognised = fund_id = fund_named_in(question, registry)
    if fund_id is not None:
        focus = scans.get(fund_id) or scan_fund(fund_id, registry, funds, sources, valuation_date)
    coverage = portfolio_coverage(portfolio, registry, scans)
    weights = dict(held_positions(portfolio))

    topic = explain.classify(question)
    labels = _sector_labels(registry, funds)
    asked_sectors = sorted(sectors_written_in(question, labels))[:MAX_SECTORS_PER_QUESTION] if topic != "unsupported" else []

    # ---- rule context: stored policy, else the scenario's offers, never the request
    if policy is not None:
        rules = [rule for rule in policy.get("rules", []) if rule.get("status") == "CONFIRMED"]
        rule_basis = f"confirmed policy {policy.get('policy_id')} version {policy.get('version')}"
    else:
        rules = list(scenario.get("scenario_rules", []))
        rule_basis = UNCONFIRMED_RULES
    issuer_ok = all(scan["_calc"]["basis_valid"] or scan["_calc"]["no_file"] for scan in scans.values())
    impacts = bounds_module.rule_impacts(rules, rule_basis, portfolio, registry, scans, snapshot.instruments, snapshot.holdings, issuer_ok)

    sector_bounds = []
    for sector in asked_sectors:
        sector_bounds.append(bounds_module.portfolio_sector_bounds(portfolio, registry, scans, sector))
        if focus is not None:
            sector_bounds.append(bounds_module.fund_sector_bounds(focus, sector))

    # ---- statements
    know, missing, hypothetical, nxt = [], [], [], []
    shown = [focus] if focus is not None else [scans[name] for name in held_funds if scans[name]["in_rule_scope"]]
    if focus is None:
        know.append(explain.statement(explain.VERIFIED,
                                      f"{coverage['verified_weight_pct']:g}% of the portfolio is verified (cash, direct holdings and fund holdings "
                                      f"looked through); {coverage['unresolved_weight_pct']:g}% is fund weight not attributed to any holding; "
                                      f"{coverage['not_looked_through_weight_pct']:g}% is in bond or commodity funds that are not looked through."))
    elif fund_id in weights:
        know.append(explain.statement(explain.VERIFIED, f"{fund_id} is {pct(weights[fund_id]):g}% of the portfolio."))
    else:
        know.append(explain.statement(explain.VERIFIED, f"{fund_id} is not held in this portfolio; the figures below describe the fund itself."))
    for scan in shown:
        parts = explain.fund_statements(scan)
        know += parts["know"]
        missing += parts["missing"]
        nxt += parts["next"]
    for item in sector_bounds:
        of = "portfolio" if item["level"] == "portfolio" else f"fund {item['fund']}"
        if item["verified_exposure_pct"] is not None:
            know.append(explain.statement(explain.VERIFIED, f"Verified exposure to {item['category']}: {item['verified_exposure_pct']:g}% of the {of}."))
        if item["unclassified_weight_pct"] or item["unresolved_weight_pct"]:
            missing.append(explain.statement(
                explain.UNRESOLVED,
                f"For {item['category']}, {explain._fmt(item['unclassified_weight_pct'])} of the {of} is in holdings without a sector label and "
                f"{explain._fmt(item['unresolved_weight_pct'])} is not attributed to any holding."))
        hypothetical += [explain.statement(explain.HYPOTHETICAL, scenario_["text"]) for scenario_ in item["scenarios"]]
        if not item["scenarios"] and item["conditional_max_pct"] == 100.0 and item["verified_exposure_pct"] is None:
            hypothetical.append(explain.statement(explain.HYPOTHETICAL, item["basis"]))
    asked = set(asked_sectors)
    for impact in impacts:
        # Rules appear in the answer when the question is about rules (or names their category); all are in constraint_impacts.
        if not impact["analysed"] or not (topic in ("constraint", "overview") or impact["category"] in asked):
            continue
        label = f"Rule {impact['rule_id']} ({impact['rule_basis']}): {impact['text']}"
        if impact["assessment"] == bounds_module.UNCONFIRMED:
            hypothetical.append(explain.statement(explain.HYPOTHETICAL, label))
        else:
            know.append(explain.statement(explain.VERIFIED, label))
    if not nxt and not missing:
        nxt.append(explain.statement(explain.NEXT, "Nothing further is needed for the checks made here."))
    sections = {"what_we_know": know, "what_is_missing": missing, "hypothetical": hypothetical, "verify_next": nxt}

    # ---- summary for the selected scope
    if focus is not None:
        summary = {"scope": "fund", "scope_label": f"fund {fund_id}", "verified_weight_pct": focus["verified_weight_pct"],
                   "unresolved_weight_pct": focus["unresolved_weight_pct"], "coverage_basis": focus["coverage_basis"],
                   "coverage_basis_label": "issuer holdings file, share of the fund" if focus["coverage_basis"] == BASIS_ISSUER_FILE else focus["coverage_basis"].replace("_", " "),
                   "data_quality_status": focus["status"], "last_verified_holdings_date": focus["snapshot_date"],
                   "source_confidence": focus["source_confidence"]["level"]}
        observations = list(focus["evidence_sources"])
        retrieval_message = focus["retrieval"]["message"]
    else:
        dates = sorted({scan["snapshot_date"] for scan in scans.values() if scan["snapshot_date"]})
        summary = {"scope": "portfolio", "scope_label": "the portfolio", "verified_weight_pct": coverage["verified_weight_pct"],
                   "unresolved_weight_pct": coverage["unresolved_weight_pct"], "coverage_basis": "portfolio_weight",
                   "coverage_basis_label": "share of the portfolio",
                   "data_quality_status": _overall([scan["status"] for scan in scans.values() if scan["in_rule_scope"]]),
                   "last_verified_holdings_date": dates[-1] if dates else None,
                   "source_confidence": None}
        observations = [item for name in held_funds for item in scans[name]["evidence_sources"]]
        retrieval_message = EVIDENCE_UNAVAILABLE if any(scan["retrieval"]["message"] for scan in scans.values() if scan["in_rule_scope"]) else None
        if len(dates) > 1:
            missing.append(explain.statement(explain.UNRESOLVED, "The fund holdings files have different 'as of' dates (" + ", ".join(dates) +
                                             "); they are combined without adjustment."))
    seen, unique = set(), []
    for item in observations:
        key = (item["source_id"], item["subject"], item["observed"].get("kind"))
        if key not in seen:
            seen.add(key)
            unique.append(item)
    summary["sources_investigated"] = len(unique)

    if topic == "unsupported":
        sections = {"what_we_know": [], "what_is_missing": [], "hypothetical": [], "verify_next": []}
    headline_impacts = impacts
    if topic == "constraint" and not asked_sectors and _COMPANY_RE.search(question):
        headline_impacts = [impact for impact in impacts if impact["rule_type"] == "max_issuer_exposure"]
    head = explain.headline(topic, sections, summary, headline_impacts, len(unique), sector_bounds)
    if headline_impacts is not impacts and not any(impact["analysed"] for impact in headline_impacts):
        head = ("No company exposure limit is on record for this investor, so there is no limit to compare with. "
                "The rules that are on record are listed under constraint impacts.")
    template = explain.render(head, sections) if topic != "unsupported" else head
    explanation, explanation_source, model_status = template, "template", "not_configured"
    if explainer is not None and topic != "unsupported":
        text, model_status = explainer.explain(question, head, sections)
        if text is not None:
            explanation, explanation_source = text, "model"

    limitations = [LOCAL_ONLY_LIMITATION,
                   "Conditional ranges are arithmetic bounds under a stated assumption. They are not forecasts and not actual exposure.",
                   "This investigation describes the current portfolio. It issues no rule verdict; verdicts come from the check engine."]
    if policy is None:
        limitations.append("No confirmed policy version was supplied: limits are the scenario's offered rules, which the investor has not confirmed.")
    return {
        "schema_version": RESPONSE_VERSION,
        "status": summary["data_quality_status"],
        "snapshot_id": snapshot.snapshot_id,
        "persona_id": scenario["persona"]["persona_id"],
        "fund_id": fund_id,
        "question": {"topic": topic, "supported": topic != "unsupported", "sectors_recognised": asked_sectors, "fund_recognised": fund_recognised},
        "summary": summary,
        "fund": public(focus) if focus is not None else None,
        "portfolio": coverage,
        "verified_findings": sections["what_we_know"],
        "missing_evidence": sections["what_is_missing"],
        "hypothetical_scenarios": sections["hypothetical"],
        "next_evidence": sections["verify_next"],
        "exposure_bounds": [bounds_module.strip(item) for item in sector_bounds],
        "constraint_impacts": impacts,
        "rules_basis": rule_basis,
        "rules_confirmed": policy is not None,
        "headline": head,
        "explanation": explanation,
        "explanation_source": explanation_source,
        "model_status": model_status,
        "template_explanation": template,
        "sources": unique,
        "retrieval": {"external_retrieval": "not_configured", "message": retrieval_message},
        "limitations": limitations,
    }


__all__ = ["investigate", "portfolio_coverage", "UnknownFund"]
