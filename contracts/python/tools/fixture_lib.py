"""Helpers that expand compact, hand-entered fixture specs into full contract objects.

Nothing here computes an expected financial result: every expected number in a
fixture is typed in by hand from contracts/fixtures/engine/HAND_CALCS.md and is
re-derived independently by contracts/python/tests/test_hand_calcs.py. The
helpers only add boilerplate (rule fields, policy hashes, envelopes).
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONTRACTS = HERE.parent.parent
sys.path.insert(0, str(HERE.parent))

from byb_contracts.constants import SCHEMA_VERSION, THRESHOLD_KIND_BY_RULE_TYPE  # noqa: E402
from byb_contracts.derive import compute_content_hash  # noqa: E402
from byb_contracts.templates import scope_description  # noqa: E402

VALUATION_DATE = "2026-11-12"
SYNTHETIC_SOURCE_ID = "SYNTHETIC_FIXTURE"
SYNTHETIC_NOTE = (
    "SYNTHETIC: every fund weight, price, FX rate and controversy record in this fixture is invented so the result can "
    "be checked by hand. None of it is real market, issuer or fund data."
)
T0 = "2026-11-14T15:00:00Z"


def rule(rule_id, rule_type, parameters, threshold, *, status, origin, words, objective_id=None,
         threshold_source=None, quote=None, confirmed_at=None, supersedes=None, superseded_by=None):
    if threshold is None:
        source = None
    elif threshold_source is not None:
        source = threshold_source
    else:
        source = {"FICTIONAL_SCENARIO": "FICTIONAL_SCENARIO", "USER_STATED": "USER_ENTERED"}[origin]
    confirmed = status in ("CONFIRMED", "SUPERSEDED")
    return {
        "rule_id": rule_id,
        "rule_type": rule_type,
        "parameters": parameters,
        "threshold": threshold,
        "threshold_kind": THRESHOLD_KIND_BY_RULE_TYPE[rule_type],
        "threshold_source": source,
        "threshold_quote": quote,
        "unit": "fraction",
        "status": status,
        "origin": origin,
        "original_words": words,
        "objective_id": objective_id,
        "scope_description": scope_description(rule_type, parameters),
        "confirmed_at": (confirmed_at or T0) if confirmed else None,
        "confirmed_by": "demo_user" if confirmed else None,
        "supersedes_rule_id": supersedes,
        "superseded_by_rule_id": superseded_by,
    }


def max_issuer(rule_id, threshold, scope="any", **kw):
    return rule(rule_id, "max_issuer_exposure", {"issuer_scope": scope}, threshold, **kw)


def min_issuer(rule_id, threshold, issuer_id, **kw):
    return rule(rule_id, "min_issuer_exposure", {"issuer_id": issuer_id}, threshold, **kw)


def exclude_sector(rule_id, threshold, sector, **kw):
    return rule(rule_id, "exclusion", {"definition": {"kind": "fund_reported_sector", "sector": sector}}, threshold, **kw)


def exclude_issuers(rule_id, threshold, issuer_ids, **kw):
    return rule(rule_id, "exclusion", {"definition": {"kind": "named_issuers", "issuer_ids": issuer_ids}}, threshold, **kw)


def controversy(rule_id, threshold, natures, event_date_from=None, **kw):
    return rule(rule_id, "controversy_exclusion", {"criteria": {"natures": natures, "event_date_from": event_date_from}}, threshold, **kw)


def loss_budget(rule_id, threshold, **kw):
    return rule(rule_id, "scenario_loss_budget", {"scenario_id": "replay_2022"}, threshold, **kw)


def objective(objective_id, words, kind="goal", source="FICTIONAL_SCENARIO", case_reference=None):
    return {"objective_id": objective_id, "original_words": words, "kind": kind, "source": source, "case_reference": case_reference}


def policy(policy_id, persona_id, version, rules, *, objectives=(), parent=None, created_at=T0, note="Initial confirmation."):
    body = {
        "schema_version": SCHEMA_VERSION,
        "policy_id": policy_id,
        "persona_id": persona_id,
        "version": version,
        "parent_version": parent,
        "created_at": created_at,
        "objectives": list(objectives),
        "rules": list(rules),
        "change_note": note,
    }
    body["content_hash"] = compute_content_hash(body)
    return body


def portfolio(portfolio_id, persona_id, cash, positions):
    return {
        "schema_version": SCHEMA_VERSION,
        "portfolio_id": portfolio_id,
        "persona_id": persona_id,
        "fictional": True,
        "valuation_date": VALUATION_DATE,
        "base_currency": "CAD",
        "cash_weight": cash,
        "positions": [{"instrument_id": k, "weight": v} for k, v in positions.items()],
    }


def purchase(instrument_id, target, words=None):
    return {"instrument_id": instrument_id, "target_direct_weight": target, "funding": "CASH", "original_words": words}


def instrument(instrument_id, issuer_id, name, asset_class, currency, sector=None, sector_source=None):
    is_fund = asset_class.startswith("etf_")
    return {
        "instrument_id": instrument_id, "issuer_id": issuer_id, "name": name, "asset_class": asset_class,
        "currency": currency, "is_fund": is_fund, "equity_scope": asset_class in ("equity", "etf_equity"),
        "sector": sector, "sector_source": sector_source if sector is not None else None,
    }


def fund_holdings(fund_id, rows, holdings_date="2026-11-12"):
    """rows: (issuer_id, instrument_id, name, weight_fraction, sector-or-None). coverage is the plain sum."""
    holdings = [
        {"fund_id": fund_id, "issuer_id": i, "instrument_id": t, "name": n, "weight_fraction": w,
         "sector": s, "sector_source": SYNTHETIC_SOURCE_ID if s is not None else None}
        for (i, t, n, w, s) in rows
    ]
    return {
        "fund_id": fund_id, "holdings_date": holdings_date, "publication_date": None, "retrieval_date": "2026-11-14",
        "source_id": SYNTHETIC_SOURCE_ID, "coverage_fraction": round(sum(r[3] for r in rows), 10),
        "non_constituent_weight": 0.0, "n_holdings": len(holdings), "holdings": holdings,
    }


def synthetic_sources():
    text = "Before You Buy synthetic fixture data (invented numbers, not a real source)"
    return {
        "schema_version": SCHEMA_VERSION,
        "sources": {
            SYNTHETIC_SOURCE_ID: {
                "source_id": SYNTHETIC_SOURCE_ID,
                "publisher": "Before You Buy team (synthetic test data)",
                "title": "Invented fixture numbers for hand calculation",
                "url": None,
                "relevant_date": "2026-11-12",
                "retrieval_date": "2026-11-14",
                "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "processing": f"None. Typed in by hand. The sha256 is the hash of the sentence: {text!r}.",
                "terms": "Team-authored test data; no third-party terms apply.",
                "limitations": "Not real data. Never display it as an issuer disclosure or as market data.",
            }
        },
    }


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def render_json(value) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False) + "\n"
