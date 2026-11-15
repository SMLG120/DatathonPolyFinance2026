"""The validator's own synthetic universe "VU" and document builders.

EVERY NUMBER HERE IS INVENTED so that each expected value can be worked out by
hand. None of it is real market, issuer or fund data.

Instruments
-----------
=========  ===========  ====  ========  =========================================
id         asset class  ccy   issuer    note
=========  ===========  ====  ========  =========================================
AAA        equity       CAD   ALPHA     share class 1 of ALPHA, sector "Tech"
AAB        equity       USD   ALPHA     share class 2 of ALPHA, no sector label
BBB        equity       CAD   BETA      sector "Energy"
CCC        equity       USD   GAMMA     sector "Health"
F1         etf_equity   CAD   F1        holdings file, coverage 1.00, all labelled
F2         etf_equity   USD   F2        holdings file, coverage 0.80, partly labelled
F3         etf_equity   CAD   F3        NO holdings file
BND        etf_bond     CAD   BND       outside the scope of the exposure rules
NOHIST     equity       CAD   OMEGA     no price series at all
STALE      equity       CAD   SIGMA     base price 11 days old (limit is 7)
=========  ===========  ====  ========  =========================================

Fund holdings (fractions of the fund)
-------------------------------------
F1 (coverage 1.00): AAA 0.20 "Tech", AAB 0.10 "Tech", BBB 0.30 "Energy", CCC 0.40 "Health"
    -> ALPHA 0.30 (two share classes), BETA 0.30, GAMMA 0.40
F2 (coverage 0.80): AAA 0.50 (no label), DDD 0.30 "Energy" (issuer DELTA)
    -> ALPHA 0.50, DELTA 0.30, uncovered 0.20

Prices (adj_close, listing currency) and FX (CAD per USD)
---------------------------------------------------------
fx:   2021-12-30 1.20 | 2021-12-31 1.25 | 2022-06-30 1.30 | 2022-12-28 1.36   (no row on 2022-12-30)
AAA:  2021-12-31 100  | 2022-06-30  80  | 2022-12-30  90
AAB:  2021-12-30  50  | 2022-06-30  40  | 2022-12-30  55      (base price 1 day old)
BBB:  2021-12-31 100  | 2022-06-30 120  | 2022-12-30 130
CCC:  2021-12-31 200  | 2022-06-30 150  | 2022-12-30 180
F1:   2021-12-31  50  | 2022-06-30  40  | 2022-12-30  45
F2:   2021-12-31 100  | 2022-06-30  70  | 2022-12-30  80
F3:   2021-12-31  20  | 2022-06-30  18  | 2022-12-30  19
BND:  2021-12-31  10  | 2022-06-30   9  | 2022-12-30   9.5
STALE:2021-12-20  10  | 2022-12-30  12
NOHIST: (absent)

CAD returns 2021-12-31 -> 2022-12-30 under SEMANTICS section 7 (FX matched to
the valuation date t, latest rate on or before t; base fx 1.25, end fx 1.36):

AAA  90/100 - 1                        = -0.10
AAB  (55 x 1.36) / (50 x 1.25) - 1     = 74.8 / 62.5 - 1   = +0.1968
BBB  130/100 - 1                       = +0.30
CCC  (180 x 1.36) / (200 x 1.25) - 1   = 244.8 / 250 - 1   = -0.0208
F1   45/50 - 1                         = -0.10
F2   (80 x 1.36) / (100 x 1.25) - 1    = 108.8 / 125 - 1   = -0.1296
F3   19/20 - 1                         = -0.05
BND  9.5/10 - 1                        = -0.05
"""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Optional

SCHEMA_VERSION = "1.0.0"
SRC = "VALIDATOR_SYNTHETIC"
CONFIRMED_AT = "2026-11-14T12:00:00Z"

# CAD returns worked out by hand in the module docstring.
HAND_RETURNS = {
    "AAA": -0.10, "AAB": 0.1968, "BBB": 0.30, "CCC": -0.0208,
    "F1": -0.10, "F2": -0.1296, "F3": -0.05, "BND": -0.05,
}


def _instrument(instrument_id: str, issuer: str, asset_class: str, currency: str, sector: Optional[str]) -> dict:
    is_fund = asset_class.startswith("etf")
    return {
        "instrument_id": instrument_id, "issuer_id": issuer, "name": f"{instrument_id} (validator synthetic)",
        "asset_class": asset_class, "currency": currency, "is_fund": is_fund,
        "equity_scope": asset_class in ("equity", "etf_equity"),
        "sector": sector, "sector_source": SRC if sector is not None else None,
    }


def instruments() -> dict:
    rows = [
        _instrument("AAA", "ALPHA", "equity", "CAD", "Tech"),
        _instrument("AAB", "ALPHA", "equity", "USD", None),
        _instrument("BBB", "BETA", "equity", "CAD", "Energy"),
        _instrument("CCC", "GAMMA", "equity", "USD", "Health"),
        _instrument("DDD", "DELTA", "equity", "CAD", "Energy"),
        _instrument("F1", "F1", "etf_equity", "CAD", "Broad market"),
        _instrument("F2", "F2", "etf_equity", "USD", "Broad market"),
        _instrument("F3", "F3", "etf_equity", "CAD", "Broad market"),
        _instrument("BND", "BND", "etf_bond", "CAD", "Bonds"),
        _instrument("NOHIST", "OMEGA", "equity", "CAD", None),
        _instrument("STALE", "SIGMA", "equity", "CAD", None),
    ]
    return {"schema_version": SCHEMA_VERSION, "instruments": {row["instrument_id"]: row for row in rows}}


def _row(fund: str, instrument_id: str, issuer: str, weight: float, sector: Optional[str]) -> dict:
    return {
        "fund_id": fund, "issuer_id": issuer, "instrument_id": instrument_id, "name": f"{issuer} (validator synthetic)",
        "weight_fraction": weight, "sector": sector, "sector_source": SRC if sector is not None else None,
    }


def fund_entry(fund: str, rows: list[dict], coverage: Optional[float] = None) -> dict:
    total = sum(row["weight_fraction"] for row in rows)
    return {
        "fund_id": fund, "holdings_date": "2026-11-12", "publication_date": None, "retrieval_date": "2026-11-14",
        "source_id": SRC, "coverage_fraction": total if coverage is None else coverage, "non_constituent_weight": 0.0,
        "n_holdings": len(rows), "holdings": rows,
    }


def holdings() -> dict:
    f1 = [
        _row("F1", "AAA", "ALPHA", 0.20, "Tech"),
        _row("F1", "AAB", "ALPHA", 0.10, "Tech"),
        _row("F1", "BBB", "BETA", 0.30, "Energy"),
        _row("F1", "CCC", "GAMMA", 0.40, "Health"),
    ]
    f2 = [
        _row("F2", "AAA", "ALPHA", 0.50, None),
        _row("F2", "DDD", "DELTA", 0.30, "Energy"),
    ]
    return {"schema_version": SCHEMA_VERSION, "funds": {"F1": fund_entry("F1", f1, 1.0), "F2": fund_entry("F2", f2, 0.8)}}


def market_data() -> dict:
    def series(currency: str, *rows: tuple) -> dict:
        return {"currency": currency, "series": [[day, price] for day, price in rows]}

    return {
        "schema_version": SCHEMA_VERSION,
        "valuation_date": "2026-11-12",
        "prices": {
            "AAA": series("CAD", ("2021-12-31", 100.0), ("2022-06-30", 80.0), ("2022-12-30", 90.0)),
            "AAB": series("USD", ("2021-12-30", 50.0), ("2022-06-30", 40.0), ("2022-12-30", 55.0)),
            "BBB": series("CAD", ("2021-12-31", 100.0), ("2022-06-30", 120.0), ("2022-12-30", 130.0)),
            "CCC": series("USD", ("2021-12-31", 200.0), ("2022-06-30", 150.0), ("2022-12-30", 180.0)),
            "DDD": series("CAD", ("2021-12-31", 10.0), ("2022-06-30", 10.0), ("2022-12-30", 10.0)),
            "F1": series("CAD", ("2021-12-31", 50.0), ("2022-06-30", 40.0), ("2022-12-30", 45.0)),
            "F2": series("USD", ("2021-12-31", 100.0), ("2022-06-30", 70.0), ("2022-12-30", 80.0)),
            "F3": series("CAD", ("2021-12-31", 20.0), ("2022-06-30", 18.0), ("2022-12-30", 19.0)),
            "BND": series("CAD", ("2021-12-31", 10.0), ("2022-06-30", 9.0), ("2022-12-30", 9.5)),
            "STALE": series("CAD", ("2021-12-20", 10.0), ("2022-12-30", 12.0)),
        },
        "fx_usdcad": [["2021-12-30", 1.20], ["2021-12-31", 1.25], ["2022-06-30", 1.30], ["2022-12-28", 1.36]],
    }


def controversies(records: Optional[list] = None) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "registry_scope": {
            "purpose": "Validator synthetic registry. Not real research.",
            "issuers_researched": sorted({r["issuer_id"] for r in (records or [])}),
            "research_date": "2026-11-14",
            "absence_meaning": "Absence means NOT ASSESSED.",
            "source_policy": "Synthetic.", "not_evidence": "A sector label is never evidence of a controversy.", "limits": "Synthetic.",
        },
        "records": list(records or []),
    }


def universe() -> dict:
    """Fresh copies of every data input, so a test may corrupt its own copy."""
    return {"instruments": instruments(), "holdings": holdings(), "market_data": market_data(), "controversies": controversies()}


# --------------------------------------------------------------------------- documents

def portfolio(cash: float, positions: dict[str, float], portfolio_id: str = "pf-validator") -> dict:
    return {
        "schema_version": SCHEMA_VERSION, "portfolio_id": portfolio_id, "persona_id": "robert", "fictional": True,
        "valuation_date": "2026-11-12", "base_currency": "CAD", "cash_weight": cash,
        "positions": [{"instrument_id": i, "weight": w} for i, w in positions.items()],
    }


_KIND = {
    "max_issuer_exposure": "max_fraction", "min_issuer_exposure": "min_fraction", "exclusion": "max_fraction",
    "controversy_exclusion": "max_fraction", "scenario_loss_budget": "max_loss_fraction",
}


def rule(rule_id: str, rule_type: str, parameters: dict, threshold: Optional[float], *, status: str = "CONFIRMED",
         origin: Optional[str] = None, objective_id: Optional[str] = None, supersedes: Optional[str] = None,
         superseded_by: Optional[str] = None) -> dict:
    if origin is None:
        origin = "SYSTEM_PROPOSED" if threshold is None else "USER_STATED"
    source = {"SYSTEM_PROPOSED": None, "USER_STATED": "USER_ENTERED", "FICTIONAL_SCENARIO": "FICTIONAL_SCENARIO"}[origin]
    confirmed = status in ("CONFIRMED", "SUPERSEDED")
    return {
        "rule_id": rule_id, "rule_type": rule_type, "parameters": parameters, "threshold": threshold,
        "threshold_kind": _KIND[rule_type], "threshold_source": source, "threshold_quote": None, "unit": "fraction",
        "status": status, "origin": origin, "original_words": f"validator rule {rule_id}", "objective_id": objective_id,
        "scope_description": f"validator scope text for {rule_type}",
        "confirmed_at": CONFIRMED_AT if confirmed else None, "confirmed_by": "demo_user" if confirmed else None,
        "supersedes_rule_id": supersedes, "superseded_by_rule_id": superseded_by,
    }


def cap_any(rule_id: str, limit: Optional[float], **kw: Any) -> dict:
    return rule(rule_id, "max_issuer_exposure", {"issuer_scope": "any"}, limit, **kw)


def cap_one(rule_id: str, issuer: str, limit: Optional[float], **kw: Any) -> dict:
    return rule(rule_id, "max_issuer_exposure", {"issuer_scope": issuer}, limit, **kw)


def floor_one(rule_id: str, issuer: str, limit: Optional[float], **kw: Any) -> dict:
    return rule(rule_id, "min_issuer_exposure", {"issuer_id": issuer}, limit, **kw)


def exclude_named(rule_id: str, issuers: list[str], limit: Optional[float], **kw: Any) -> dict:
    return rule(rule_id, "exclusion", {"definition": {"kind": "named_issuers", "issuer_ids": issuers}}, limit, **kw)


def exclude_sector(rule_id: str, sector: str, limit: Optional[float], **kw: Any) -> dict:
    return rule(rule_id, "exclusion", {"definition": {"kind": "fund_reported_sector", "sector": sector}}, limit, **kw)


def exclude_controversy(rule_id: str, natures: list[str], limit: Optional[float], since: Optional[str] = None, **kw: Any) -> dict:
    return rule(rule_id, "controversy_exclusion", {"criteria": {"natures": natures, "event_date_from": since}}, limit, **kw)


def loss_budget(rule_id: str, limit: Optional[float], **kw: Any) -> dict:
    return rule(rule_id, "scenario_loss_budget", {"scenario_id": "replay_2022"}, limit, **kw)


def content_hash(policy_body: dict) -> str:
    """The validator's own implementation of the documented formula (policy.schema.json description):
    'sha256:' + SHA-256 of the canonical JSON (sorted keys, no spaces, UTF-8) of the policy without content_hash."""
    body = {k: v for k, v in policy_body.items() if k != "content_hash"}
    text = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def policy(rules: list[dict], *, version: int = 1, parent: Optional[int] = None, objectives: Optional[list] = None,
           policy_id: str = "pol-validator") -> dict:
    body = {
        "schema_version": SCHEMA_VERSION, "policy_id": policy_id, "persona_id": "robert", "version": version,
        "parent_version": parent, "created_at": CONFIRMED_AT, "objectives": list(objectives or []),
        "rules": copy.deepcopy(rules), "change_note": "validator policy",
    }
    body["content_hash"] = content_hash(body)
    return body


def objective(objective_id: str = "obj-1", words: str = "Preserve my capital.", kind: str = "goal") -> dict:
    return {"objective_id": objective_id, "original_words": words, "kind": kind, "source": "FICTIONAL_SCENARIO", "case_reference": None}


def request(instrument_id: str, target: float, words: Optional[str] = None) -> dict:
    return {"instrument_id": instrument_id, "target_direct_weight": target, "funding": "CASH", "original_words": words}


def controversy_record(record_id: str, issuer: str, nature: str, event_date: str) -> dict:
    return {
        "record_id": record_id, "issuer_id": issuer, "event_date": event_date, "nature": nature,
        "summary": "Validator synthetic record.", "source_ids": [SRC], "coverage_note": "Synthetic.",
    }
