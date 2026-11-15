#!/usr/bin/env python3
"""Build data/processed/ from data/starter/, the raw issuer files and the curated registry.

Standard library only:

    python3 -I data/scripts/build_processed.py [--use SOURCE_ID ...] [--allow-missing-fund FUND ...]
                                                [--allow-missing-evidence]

Inputs
* data/starter/*.csv                          (organizer-supplied, read-only)
* data/manifests/raw_files_manifest.json      (written by acquire_*.py)
* data/raw/...                                (git-ignored; hashes re-verified here)
* data/curated/controversy_records.json       (hand-written, reviewed)
* data/scripts/_terms.py                      (reuse statements; quotations checked against the
                                               terms pages registered by acquire_evidence.py)

Outputs (deterministic: same inputs give byte-identical files)
* holdings.json, instruments.json, sources.json, controversies.json
* market_data.json           (Yahoo-derived, git-ignored, regenerated from data/starter/)
* fund_sector_breakdowns.json  supplementary: issuer-published FUND-LEVEL sector totals
* build_report.json            supplementary: the numbers quoted in docs/data-sources.md

Rules enforced here (docs/BUILD_BRIEF.md section 4)
* Weights become fractions (issuer files print percent). The scale is asserted:
  all lines of a fund must sum to about 1, never about 100 or 0.01.
* Weights are NEVER rescaled. coverage_fraction = sum of the reported weights of
  equity constituents; cash / derivative / other lines are kept out of the
  constituents and summed in non_constituent_weight.
* sector is only what the fund's own issuer file prints (null when it prints
  none). Nothing is inferred from an ETF's "Broad market" label.
* Constituents are not restricted to the 31 starter assets.
* The build stops rather than guess when a file layout, a line type, the
  weight scale or the issuer grouping is not what it expects.
"""
from __future__ import annotations

import argparse
import collections
import re
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import (DATA_DIR, PROCESSED_DIR, RAW_MANIFEST, REPO_ROOT, SCHEMA_VERSION, STARTER_DIR,  # noqa: E402
                     VALUATION_DATE, dump_json, load_json, read_csv_dicts, rel, sha256_file, write_bytes_atomic)
from _holdings_parsers import (CASH, DERIVATIVE, EQUITY, OTHER, parse_ishares_holdings_csv,  # noqa: E402
                               parse_ssga_daily_holdings, parse_ssga_fund_sector_breakdown)
from _terms import REUSE_STATEMENTS, TERMS_ITEM_FOR, quotations  # noqa: E402

CURATED_CONTROVERSIES = DATA_DIR / "curated" / "controversy_records.json"
STARTER_SOURCE_ID = "starter_assets_universe"

# fund_id (= the fund's instrument_id) -> acquisition item, parser and conventions.
FUNDS = {
    "SPY": {
        "item": "SPY",
        "parser": lambda payload: parse_ssga_daily_holdings(payload, "SPY"),
        "instrument_suffix": "",          # US tickers as printed (BRK.B, BF.B)
        "expected_currency": "USD",
        "expected_exchange": None,        # the SSGA file has no exchange column
        "full_replication_index_fund": True,
    },
    "XIU.TO": {
        "item": "XIU",
        "parser": lambda payload: parse_ishares_holdings_csv(payload, "XIU"),
        # Every Toronto-listed constituent gets "<ticker as printed>.TO". The starter universe already
        # uses that form (RY.TO), and without it XIU's T (TELUS), L (Loblaw) and PPL (Pembina) would
        # collide with SPY's T (AT&T), L (Loews) and PPL (PPL Corp) in one instrument registry.
        "instrument_suffix": ".TO",
        "expected_currency": "CAD",
        "expected_exchange": "Toronto Stock Exchange",
        "full_replication_index_fund": True,
    },
}
SECTOR_PAGE_ITEMS = {"SPY": "SPY_PAGE"}
# Equity ETFs of the starter universe for which no holdings are acquired in the core phase.
FUNDS_WITHOUT_HOLDINGS = {
    "ESGV": "Deliberately not acquired in the core phase (LEAD_DECISIONS D7): demonstrates unknown coverage.",
    "QQQ": "Not needed by the core demos; not acquired.",
}

# ------------------------------------------------------------ issuer identity
# Share-class / voting-right designators as printed at the END of issuer-file names.
_CLASS_SUFFIXES = [
    r"\s+CL(?:ASS)?\s+[A-Z](?:\s+SHARES)?$",        # ALPHABET INC CL A, FOX CORP CLASS B, VISA INC CLASS A SHARES
    r"\s+SUBORDINATE\s+VOTING$",                     # TECK RESOURCES SUBORDINATE VOTING
    r"\s+SUB\s+VOT$",                                # FAIRFAX FINANCIAL HOLDINGS SUB VOT
    r"\s+NON[- ]VOTING(?:\s+[A-Z]{1,3})?$",          # ROGERS COMMUNICATIONS NON-VOTING I (truncated in the file)
    r"\s+NON\s+VTG\s+SHRS$",                         # MCCORMICK + CO NON VTG SHRS
    r"\s+VOTING$",                                   # BROOKFIELD ASSET MANAGEMENT VOTING
    r"\s+[ABC]$",                                    # MASTERCARD INC   A, DELL TECHNOLOGIES  C
    r"\s*\(CLASS\s+[A-Z]\)$",                        # starter universe: Alphabet (Class A)
]
# Legal-form words removed from the end of a name (repeatedly).
_LEGAL_FORMS = {"INC", "CORP", "CORPORATION", "CO", "COMPANY", "COS", "COMPANIES", "LTD", "LIMITED",
                "PLC", "NV", "SA", "LLC", "LP", "THE", "DE", "AND"}
# Reviewed, explicit joins for one company printed under names that do not normalise to the same
# key in two files. Key and value are name keys as produced by name_key(). Empty: none needed for
# the 2026-11-12 snapshots (no company appears in both SPY and XIU).
MANUAL_NAME_KEY_ALIASES: dict[str, str] = {}


def name_key(printed_name: str) -> str:
    """Company key: upper-case name without share-class designator or legal form."""
    text = printed_name.upper().strip()
    changed = True
    while changed:
        changed = False
        for pattern in _CLASS_SUFFIXES:
            stripped = re.sub(pattern, "", text)
            if stripped != text and stripped.strip():
                text, changed = stripped.strip(), True
    text = text.replace("&", " AND ").replace("+", " AND ")
    text = re.sub(r"[^A-Z0-9 ]", " ", text)
    tokens = text.split()
    while len(tokens) > 1 and tokens[-1] in _LEGAL_FORMS:
        tokens.pop()
    if len(tokens) > 1 and tokens[0] == "THE":
        tokens.pop(0)
    key = " ".join(tokens)
    return MANUAL_NAME_KEY_ALIASES.get(key, key)


def fraction(percent: Decimal) -> float:
    return float(round(percent / Decimal(100), 12))


def clean_name(printed: str) -> str:
    return re.sub(r"\s+", " ", printed).strip()


# Every starter file the build reads or hashes (two of them are git-ignored: see the root .gitignore).
STARTER_INPUTS = ("assets_universe.csv", "prices_daily.csv", "fx_usdcad_daily.csv", "corporate_actions.csv",
                  "macro_rates.csv", "sources_metadata.csv")


class BuildError(RuntimeError):
    pass


# ------------------------------------------------------------------- inputs
def load_manifest() -> dict:
    if not RAW_MANIFEST.exists():
        raise BuildError(f"{rel(RAW_MANIFEST)} not found: run data/scripts/acquire_holdings.py first")
    return load_json(RAW_MANIFEST)


def pick_record(manifest: dict, item: str, pinned: set[str]):
    candidates = [entry for entry in manifest["files"] if entry.get("item") == item]
    pinned_here = [entry for entry in candidates if entry["source_id"] in pinned]
    if pinned_here:
        candidates = pinned_here
    if not candidates:
        return None
    return max(candidates, key=lambda entry: (entry["as_of_date_in_file"], entry["retrieved_at_utc"]))


def read_verified(record: dict) -> bytes:
    path = REPO_ROOT / record["path"]
    if not path.exists():
        raise BuildError(f"raw file missing: {record['path']} (manifest source_id {record['source_id']}). "
                         "Raw files are git-ignored; re-acquire them with data/scripts/acquire_*.py.")
    digest = sha256_file(path)
    if digest != record["sha256"]:
        raise BuildError(f"hash mismatch for {record['path']}: manifest {record['sha256']}, file {digest}")
    return path.read_bytes()


# ---------------------------------------------------------------- normalise
def normalise_fund(fund_id: str, record: dict, parsed: dict, starter_tickers: set[str]) -> dict:
    cfg = FUNDS[fund_id]
    if parsed["holdings_date"] != record["as_of_date_in_file"]:
        raise BuildError(f"{fund_id}: as-of date in file {parsed['holdings_date']} != manifest {record['as_of_date_in_file']}")
    total_percent = sum((line["weight_percent"] for line in parsed["lines"]), Decimal(0))
    if Decimal("0.95") <= total_percent <= Decimal("1.005"):
        raise BuildError(f"{fund_id}: weights sum to {total_percent}: the file seems to print fractions, not percent")
    if not Decimal("95") <= total_percent <= Decimal("100.5"):
        raise BuildError(f"{fund_id}: weights sum to {total_percent} percent; expected about 100")

    constituents, others = [], []
    seen_instruments = set()
    for line in parsed["lines"]:
        weight = line["weight_percent"]
        if weight < 0 or weight > 100:
            raise BuildError(f"{fund_id}: weight out of range on {line['name']!r}: {weight}")
        if line["kind"] != EQUITY:
            others.append({"kind": line["kind"], "ticker_as_printed": line["ticker"], "name": clean_name(line["name"]),
                           "asset_class_as_printed": line["asset_class_raw"], "weight_fraction": fraction(weight)})
            continue
        if line["currency"] != cfg["expected_currency"]:
            raise BuildError(f"{fund_id}: {line['ticker']} trades in {line['currency']}, expected {cfg['expected_currency']}")
        if cfg["expected_exchange"] and line["exchange"] != cfg["expected_exchange"]:
            raise BuildError(f"{fund_id}: {line['ticker']} is listed on {line['exchange']!r}, expected {cfg['expected_exchange']!r}")
        instrument_id = line["ticker"] + cfg["instrument_suffix"]
        if instrument_id in seen_instruments:
            raise BuildError(f"{fund_id}: duplicate constituent {instrument_id}")
        seen_instruments.add(instrument_id)
        sector = line["sector_raw"].strip() if line["sector_raw"] else ""
        sector = None if sector in ("", "-") else sector
        constituents.append({
            "instrument_id": instrument_id,
            "ticker_as_printed": line["ticker"],
            "name": clean_name(line["name"]),
            "name_key": name_key(line["name"]),
            "weight_percent": weight,
            "sector": sector,
            "currency": line["currency"],
            "cusip6": line["identifier"][:6] if line["identifier"] else None,
            "market_value": line["market_value"],
            "in_starter_universe": instrument_id in starter_tickers,
        })
    equity_percent = sum((c["weight_percent"] for c in constituents), Decimal(0))
    other_percent = sum((line["weight_percent"] for line in parsed["lines"] if line["kind"] != EQUITY), Decimal(0))
    return {
        "fund_id": fund_id, "record": record, "parsed": parsed, "constituents": constituents, "others": others,
        "equity_percent": equity_percent, "other_percent": other_percent, "total_percent": total_percent,
    }


def assign_issuers(funds: dict[str, dict], universe: list[dict]) -> tuple[dict, dict, list]:
    """Return (issuer_id by name_key, issuer_id by starter ticker, starter equities held by no acquired fund)."""
    starter_issuer = {}
    for row in universe:
        if row["asset_class"] == "equity":
            starter_issuer[row["ticker"]] = name_key(row["name"]).replace(" ", "_")
        else:  # funds and crypto assets are not companies: they are their own bucket
            starter_issuer[row["ticker"]] = row["ticker"]

    key_to_starter_ids = collections.defaultdict(set)
    all_keys = set()
    for fund in funds.values():
        for c in fund["constituents"]:
            all_keys.add(c["name_key"])
            if c["in_starter_universe"]:
                key_to_starter_ids[c["name_key"]].add(starter_issuer[c["instrument_id"]])
    issuer_by_key = {}
    for key in sorted(all_keys):
        starter_ids = key_to_starter_ids.get(key, set())
        if len(starter_ids) > 1:
            raise BuildError(f"name key {key!r} joins starter instruments with different issuers: {sorted(starter_ids)}")
        issuer_by_key[key] = next(iter(starter_ids)) if starter_ids else key.replace(" ", "_")
    owners = collections.defaultdict(set)
    for key, issuer_id in issuer_by_key.items():
        owners[issuer_id].add(key)
    clashes = {issuer_id: sorted(keys) for issuer_id, keys in owners.items() if len(keys) > 1}
    if clashes:
        raise BuildError(f"one issuer_id for different name keys (add a reviewed alias or fix the rule): {clashes}")
    non_company = {starter_issuer[row["ticker"]] for row in universe if row["asset_class"] != "equity"}
    overlap = non_company & set(issuer_by_key.values())
    if overlap:
        raise BuildError(f"company issuer_id collides with a fund/crypto id: {sorted(overlap)}")
    unlinked = [t for t, issuer in starter_issuer.items()
                if issuer not in set(issuer_by_key.values()) and issuer != t]
    return issuer_by_key, starter_issuer, unlinked


def cusip_cross_check(fund: dict) -> dict:
    """SSGA prints CUSIPs: the first six characters identify the issuer. Compare with the name grouping."""
    by_name, by_cusip = collections.defaultdict(set), collections.defaultdict(set)
    for c in fund["constituents"]:
        if not c["cusip6"]:
            return {"available": False}
        by_name[c["name_key"]].add(c["instrument_id"])
        by_cusip[c["cusip6"]].add(c["instrument_id"])
    name_groups = {frozenset(v) for v in by_name.values()}
    cusip_groups = {frozenset(v) for v in by_cusip.values()}
    return {
        "available": True,
        "groups_by_name": len(name_groups),
        "groups_by_cusip6": len(cusip_groups),
        "identical": name_groups == cusip_groups,
        "only_in_name_grouping": sorted(sorted(g) for g in name_groups - cusip_groups),
        "only_in_cusip_grouping": sorted(sorted(g) for g in cusip_groups - name_groups),
    }


# ------------------------------------------------------------------ outputs
def build_market_data(universe: list[dict]) -> tuple[dict, dict]:
    prices = read_csv_dicts(STARTER_DIR / "prices_daily.csv")
    fx_rows = read_csv_dicts(STARTER_DIR / "fx_usdcad_daily.csv")
    currency = {row["ticker"]: row["currency"] for row in universe}
    series = {row["ticker"]: [] for row in universe}
    for row in prices:
        ticker = row["ticker"]
        if ticker not in series:
            raise BuildError(f"prices_daily.csv has a ticker outside the universe: {ticker}")
        if row["currency"] != currency[ticker]:
            raise BuildError(f"currency mismatch for {ticker} on {row['date']}")
        value = float(row["adj_close"])
        if not value > 0:
            raise BuildError(f"non-positive adj_close for {ticker} on {row['date']}")
        series[ticker].append([row["date"], value])
    for ticker, points in series.items():
        if not points:
            raise BuildError(f"no prices for {ticker}")
        dates = [d for d, _ in points]
        if dates != sorted(dates) or len(set(dates)) != len(dates):
            raise BuildError(f"{ticker}: dates not strictly ascending")
    last_dates = {points[-1][0] for points in series.values()}
    if max(last_dates) != VALUATION_DATE:
        raise BuildError(f"last price date {max(last_dates)} != valuation date {VALUATION_DATE}")
    fx = [[row["date"], float(row["usdcad"])] for row in fx_rows]
    if [d for d, _ in fx] != sorted({d for d, _ in fx}):
        raise BuildError("FX dates not strictly ascending")
    data = {
        "schema_version": SCHEMA_VERSION,
        "valuation_date": VALUATION_DATE,
        "prices": {t: {"currency": currency[t], "series": series[t]} for t in series},
        "fx_usdcad": fx,
    }
    stats = {"instruments": len(series), "price_points": sum(len(p) for p in series.values()), "fx_points": len(fx),
             "first_date": min(p[0][0] for p in series.values()), "last_date": max(last_dates)}
    return data, stats


def starter_sources() -> dict:
    meta = read_csv_dicts(STARTER_DIR / "sources_metadata.csv")
    by_file = collections.defaultdict(list)
    for row in meta:
        by_file[row["file"]].append(row)

    def joined(file_name: str, column: str) -> str:
        values = []
        for row in by_file[file_name]:
            if row[column] and row[column] not in values:
                values.append(row[column])
        return " | ".join(values)

    def record(source_id, file_name, publisher, title, url, relevant_date, used_for, extra_limitations=""):
        path = STARTER_DIR / file_name
        limitations = joined(file_name, "limitations")
        if extra_limitations:
            limitations = f"{limitations} | {extra_limitations}"
        return {
            "source_id": source_id,
            "publisher": publisher,
            "title": title,
            "url": url,
            "relevant_date": relevant_date,
            "retrieval_date": by_file[file_name][0]["retrieved_on"],
            "sha256": sha256_file(path),
            "processing": (f"File: {rel(path)} (hash is of this file as supplied by the organizers; retrieval_date is "
                           f"the organizers' retrieval date). Organizers' processing: {joined(file_name, 'processing')}. "
                           f"Our use: {used_for}"),
            "terms": joined(file_name, "terms_of_use"),
            "limitations": limitations,
        }

    organizers = "PolyFinances AlphaForge AI datathon organizers (starter dataset)"
    return {
        STARTER_SOURCE_ID: record(
            STARTER_SOURCE_ID, "assets_universe.csv", organizers,
            "assets_universe.csv - 31-asset starter universe with organizer-assigned sector labels",
            None, "2026-11-13",
            "names, asset class, currency and sector of the 31 starter instruments in instruments.json. "
            "The sector labels are organizer-assigned and simplified, not an official classification."),
        "starter_prices_daily": record(
            "starter_prices_daily", "prices_daily.csv",
            "Yahoo Finance via the yfinance library, compiled by the datathon organizers",
            "prices_daily.csv - daily OHLC, close, adjusted close and volume, 2021-11-12 to 2026-11-12",
            "https://finance.yahoo.com", VALUATION_DATE,
            "adj_close only, copied unchanged into market_data.json (no forward-fill, no calendar alignment, "
            "no re-adjustment). market_data.json is git-ignored and regenerated from data/starter/.",
            "Audit: CNQ.TO adj_close across 2022-08-22 appears to count one special distribution twice (see "
            "docs/data-sources.md); CNQ.TO is not in the core demo portfolios."),
        "starter_fx_usdcad": record(
            "starter_fx_usdcad", "fx_usdcad_daily.csv",
            "Bank of Canada (Valet API, series FXUSDCAD), compiled by the datathon organizers",
            "fx_usdcad_daily.csv - USD/CAD daily exchange rate, 2021-11-12 to 2026-11-12",
            "https://www.bankofcanada.ca/valet/observations/FXUSDCAD/json", VALUATION_DATE,
            "usdcad copied unchanged into market_data.json; the engine matches each price date to the latest "
            "rate on or before it (maximum observed rate age: 4 calendar days)."),
        "starter_corporate_actions": record(
            "starter_corporate_actions", "corporate_actions.csv",
            "Yahoo Finance via the yfinance library, compiled by the datathon organizers",
            "corporate_actions.csv - dividends and splits by ex-date, 2021-11-12 to 2026-11-12",
            "https://finance.yahoo.com", VALUATION_DATE,
            "audit only (audit_starter.py). Never applied to prices: adj_close already includes splits and dividends."),
        "starter_macro_rates": record(
            "starter_macro_rates", "macro_rates.csv",
            "Bank of Canada (Valet API) and FRED, Federal Reserve Bank of St. Louis, compiled by the datathon organizers",
            "macro_rates.csv - policy rates, 2y/10y yields, CPI, unemployment (Canada and U.S.)",
            "https://www.bankofcanada.ca/valet/docs ; https://fred.stlouisfed.org", VALUATION_DATE,
            "audit only (row counts, duplicates). Not used by any processed output or calculation."),
    }


def reuse_statement(manifest: dict, item: str) -> str:
    """The publisher's reuse terms for an acquisition item (_terms.py). Every quotation in the statement
    must be among the sentences verified in the registered terms page (raw manifest), else the build stops."""
    terms_item = TERMS_ITEM_FOR[item]
    statement = REUSE_STATEMENTS[terms_item]
    pages = [e for e in manifest["files"] if e["kind"] == "terms_of_use" and e["item"] == terms_item]
    if not pages:
        raise BuildError(f"the terms page {terms_item} is not registered in the raw manifest; run "
                         "data/scripts/acquire_evidence.py (see its docstring)")
    page = max(pages, key=lambda e: e["retrieved_at_utc"])
    unverified = [q for q in quotations(statement) if q not in page["verified_phrases"]]
    if unverified:
        raise BuildError(f"{terms_item}: quotation not verified in {page['path']}: {unverified[0]!r}; run "
                         "data/scripts/acquire_evidence.py --reverify")
    return (f"{statement} [Terms page retrieved {page['retrieved_at_utc']}; source_id {page['source_id']}; "
            f"sha256 {page['sha256']}.]")


def holdings_source(manifest: dict, record: dict, processing: str, limitations: str) -> dict:
    return {
        "source_id": record["source_id"],
        "publisher": record["publisher"],
        "title": record["title"],
        "url": record["url_requested"],
        "relevant_date": record["as_of_date_in_file"],
        "retrieval_date": record["retrieval_date"],
        "sha256": record["sha256"],
        "processing": f"File: {record['path']} (git-ignored). Retrieved {record['retrieved_at_utc']}: "
                      f"{record['retrieval_method']}. {processing}",
        "terms": reuse_statement(manifest, record["item"]),
        "limitations": limitations,
    }


def build_controversies(manifest: dict, instruments: dict, sources: dict, allow_missing_evidence: bool = False) -> dict:
    if not CURATED_CONTROVERSIES.exists():
        raise BuildError(f"{rel(CURATED_CONTROVERSIES)} not found")
    curated = load_json(CURATED_CONTROVERSIES)
    scope = curated["registry_scope"]
    records = curated["records"]
    evidence = {entry["source_id"]: entry for entry in manifest["files"] if entry["kind"] == "controversy_evidence"}
    known_issuers = {entry["issuer_id"] for entry in instruments.values()}
    natures = {"ALLEGATION", "REGULATORY_FINDING", "COURT_RULING", "SETTLEMENT", "COMPANY_DISCLOSURE"}
    required = {"record_id", "issuer_id", "event_date", "nature", "summary", "source_ids", "coverage_note"}
    if len(records) > 5:
        raise BuildError("controversy registry is limited to 5 records in this phase")
    if len({r["issuer_id"] for r in records}) > 3:
        raise BuildError("controversy registry is limited to 3 issuers in this phase")
    seen = set()
    for item in records:
        if set(item) != required:
            raise BuildError(f"controversy record fields {sorted(item)} != {sorted(required)}")
        if item["record_id"] in seen:
            raise BuildError(f"duplicate record_id {item['record_id']}")
        seen.add(item["record_id"])
        if item["nature"] not in natures:
            raise BuildError(f"{item['record_id']}: unknown nature {item['nature']!r}")
        if item["issuer_id"] not in known_issuers:
            raise BuildError(f"{item['record_id']}: issuer {item['issuer_id']!r} is not in instruments.json")
        if item["issuer_id"] not in scope["issuers_researched"]:
            raise BuildError(f"{item['record_id']}: issuer not listed in registry_scope.issuers_researched")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", item["event_date"]) or item["event_date"] > scope["research_date"]:
            raise BuildError(f"{item['record_id']}: bad event_date {item['event_date']!r}")
        if not item["source_ids"]:
            raise BuildError(f"{item['record_id']}: a record needs at least one retrieved source")
        for source_id in item["source_ids"]:
            if source_id not in evidence:
                raise BuildError(f"{item['record_id']}: source {source_id!r} was not retrieved (not in the raw manifest)")
            entry = evidence[source_id]
            if allow_missing_evidence and not (REPO_ROOT / entry["path"]).exists():
                # The registry is built from the curated file and the committed manifest; the raw page only
                # allows the hash to be re-verified. A file that IS present must still match.
                print(f"WARNING: raw evidence page not present, hash not re-verified: {entry['path']}")
            else:
                read_verified(entry)  # the evidence file must exist locally with the recorded hash
            sources[source_id] = {
                "source_id": source_id,
                "publisher": entry["publisher"],
                "title": entry["title"],
                "url": entry["url_requested"],
                "relevant_date": entry["document_date"],
                "retrieval_date": entry["retrieval_date"],
                "sha256": entry["sha256"],
                "processing": f"File: {entry['path']} (git-ignored). Retrieved {entry['retrieved_at_utc']}: "
                              f"{entry['retrieval_method']}. The page was accepted only because the "
                              f"{len(entry['verified_phrases'])} sentences the registry relies on are literally "
                              "present in it (raw manifest, field verified_phrases). Date printed on the page: "
                              f"{entry['document_date_text']}; page last updated: {entry['page_last_updated']}. "
                              "The registry summary is our own neutral wording, not a quotation.",
                "terms": reuse_statement(manifest, entry["item"]),
                "limitations": entry["limitations"],
            }
    for issuer in scope["issuers_researched"]:
        if issuer not in known_issuers:
            raise BuildError(f"registry_scope lists unknown issuer {issuer!r}")
    return {"schema_version": SCHEMA_VERSION, "registry_scope": scope, "records": records}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--use", action="append", default=[], metavar="SOURCE_ID",
                        help="pin a specific raw snapshot from the manifest (default: latest per fund)")
    parser.add_argument("--allow-missing-fund", action="append", default=[], choices=sorted(FUNDS), metavar="FUND",
                        help="build without this fund's holdings (it is then simply absent = unknown coverage)")
    parser.add_argument("--allow-missing-evidence", action="store_true",
                        help="build controversies.json even if a raw evidence page is not on disk (fresh clone: "
                             "data/raw/ is git-ignored); the committed manifest hashes are then not re-verified")
    args = parser.parse_args()

    absent = [name for name in STARTER_INPUTS if not (STARTER_DIR / name).exists()]
    if absent:
        raise BuildError(f"starter file(s) missing in {rel(STARTER_DIR)}: {absent}. The Yahoo-derived files "
                         "(prices_daily.csv, corporate_actions.csv) are git-ignored: copy the organizers' starter "
                         "package into data/starter/ first.")
    universe = read_csv_dicts(STARTER_DIR / "assets_universe.csv")
    starter_tickers = {row["ticker"] for row in universe}
    manifest = load_manifest()
    pinned = set(args.use)
    unknown_pins = pinned - {entry["source_id"] for entry in manifest["files"]}
    if unknown_pins:
        raise BuildError(f"--use: not in the manifest: {sorted(unknown_pins)}")

    # ----------------------------------------------------------- fund files
    funds = {}
    missing = []
    for fund_id, cfg in FUNDS.items():
        record = pick_record(manifest, cfg["item"], pinned)
        if record is None:
            if fund_id in args.allow_missing_fund:
                missing.append(fund_id)
                continue
            raise BuildError(f"no raw holdings file registered for {fund_id}. Acquire it, or pass "
                             f"--allow-missing-fund {fund_id} to build without it (unknown coverage).")
        payload = read_verified(record)
        funds[fund_id] = normalise_fund(fund_id, record, cfg["parser"](payload), starter_tickers)

    issuer_by_key, starter_issuer, unlinked_starter = assign_issuers(funds, universe)

    # ----------------------------------------------------- instruments.json
    instruments = {}
    for row in universe:
        is_fund = row["asset_class"].startswith("etf_")
        instruments[row["ticker"]] = {
            "instrument_id": row["ticker"],
            "issuer_id": starter_issuer[row["ticker"]],
            "name": row["name"],
            "asset_class": row["asset_class"],
            "currency": row["currency"],
            "is_fund": is_fund,
            "equity_scope": row["asset_class"] in ("equity", "etf_equity"),
            "sector": row["sector"],
            "sector_source": STARTER_SOURCE_ID,
        }
    holdings_out = {"schema_version": SCHEMA_VERSION, "funds": {}}
    report_funds = {}
    for fund_id, fund in funds.items():
        record = fund["record"]
        source_id = record["source_id"]
        rows = []
        for c in fund["constituents"]:
            issuer_id = issuer_by_key[c["name_key"]]
            sector_source = source_id if c["sector"] is not None else None
            rows.append({
                "fund_id": fund_id,
                "issuer_id": issuer_id,
                "instrument_id": c["instrument_id"],
                "name": c["name"],
                "weight_fraction": fraction(c["weight_percent"]),
                "sector": c["sector"],
                "sector_source": sector_source,
            })
            existing = instruments.get(c["instrument_id"])
            if existing is None:
                instruments[c["instrument_id"]] = {
                    "instrument_id": c["instrument_id"],
                    "issuer_id": issuer_id,
                    "name": c["name"],
                    "asset_class": "equity",
                    "currency": c["currency"],
                    "is_fund": False,
                    "equity_scope": True,
                    "sector": c["sector"],
                    "sector_source": sector_source,
                }
            else:
                if existing["issuer_id"] != issuer_id:
                    raise BuildError(f"{c['instrument_id']}: issuer {issuer_id} in {fund_id} but "
                                     f"{existing['issuer_id']} in the registry")
                if existing["currency"] != c["currency"]:
                    raise BuildError(f"{c['instrument_id']}: currency differs between {fund_id} and the registry")
                if existing["asset_class"] != "equity":
                    raise BuildError(f"{c['instrument_id']}: constituent of {fund_id} is not an equity in the registry")
        kinds = collections.Counter(o["kind"] for o in fund["others"])
        parts = [f"{kinds[k]} {k}" for k in (CASH, DERIVATIVE, OTHER) if kinds[k]]
        remainder = Decimal(100) - fund["total_percent"]
        note = (f"Sum of the reported weights of the {len(fund['others'])} non-constituent line(s) in the issuer file "
                f"({', '.join(parts)}); they are not look-through holdings. All printed lines sum to "
                f"{fraction(fund['total_percent'])}; coverage_fraction + non_constituent_weight is therefore not "
                f"exactly 1 (difference {fraction(remainder)}: unlisted net assets and/or rounding by the issuer). "
                "Nothing is rescaled.")
        holdings_out["funds"][fund_id] = {
            "fund_id": fund_id,
            "holdings_date": fund["parsed"]["holdings_date"],
            "publication_date": fund["parsed"]["publication_date"],
            "retrieval_date": record["retrieval_date"],
            "source_id": source_id,
            "coverage_fraction": fraction(fund["equity_percent"]),
            "non_constituent_weight": fraction(fund["other_percent"]),
            "non_constituent_note": note,
            "n_holdings": len(rows),
            "holdings": rows,
        }
        sector_totals = collections.defaultdict(Decimal)
        for c in fund["constituents"]:
            sector_totals[c["sector"] if c["sector"] is not None else "(no sector printed)"] += c["weight_percent"]
        mv_check = None
        if all(line["market_value"] is not None for line in fund["parsed"]["lines"]):
            total_mv = sum((line["market_value"] for line in fund["parsed"]["lines"]), Decimal(0))
            deviations = [abs(line["weight_percent"] - Decimal(100) * line["market_value"] / total_mv)
                          for line in fund["parsed"]["lines"]]
            mv_check = {"sum_market_value": str(total_mv),
                        "max_abs_difference_percentage_points": float(round(max(deviations), 6)),
                        "note": "printed weight (%) versus 100 x market value / sum of all market values"}
        report_funds[fund_id] = {
            "source_id": source_id,
            "holdings_date": fund["parsed"]["holdings_date"],
            "holdings_date_text_in_file": fund["parsed"]["holdings_date_text"],
            "retrieved_at_utc": record["retrieved_at_utc"],
            "lines_in_file": len(fund["parsed"]["lines"]),
            "n_constituents": len(rows),
            "coverage_fraction": fraction(fund["equity_percent"]),
            "non_constituent_weight": fraction(fund["other_percent"]),
            "all_lines_weight": fraction(fund["total_percent"]),
            "one_minus_all_lines": fraction(remainder),
            "non_constituent_lines": fund["others"],
            "weight_decimals_in_file": max(-c["weight_percent"].as_tuple().exponent for c in fund["constituents"]),
            "largest_weight": max(r["weight_fraction"] for r in rows),
            "smallest_weight": min(r["weight_fraction"] for r in rows),
            "sector_labels_printed": sorted({c["sector"] for c in fund["constituents"] if c["sector"] is not None}),
            "constituents_without_sector": sum(1 for c in fund["constituents"] if c["sector"] is None),
            "weight_by_printed_sector": {k: fraction(v) for k, v in sorted(sector_totals.items(), key=lambda kv: -kv[1])},
            "cusip6_cross_check": cusip_cross_check(fund),
            "market_value_cross_check": mv_check,
            "starter_instruments_held": sorted(c["instrument_id"] for c in fund["constituents"] if c["in_starter_universe"]),
        }

    # ------------------------------------------------------ issuer groupings
    by_issuer = collections.defaultdict(list)
    for instrument in instruments.values():
        by_issuer[instrument["issuer_id"]].append(instrument["instrument_id"])
    weights = collections.defaultdict(dict)
    for fund_id, fund in holdings_out["funds"].items():
        for row in fund["holdings"]:
            weights[row["instrument_id"]][fund_id] = row["weight_fraction"]
    multi_class = []
    for issuer_id, ids in sorted(by_issuer.items()):
        if len(ids) < 2:
            continue
        per_fund = collections.defaultdict(Decimal)
        for instrument_id in ids:
            for fund_id, weight in weights[instrument_id].items():
                per_fund[fund_id] += Decimal(str(weight))
        multi_class.append({
            "issuer_id": issuer_id,
            "instruments": [{"instrument_id": i, "name": instruments[i]["name"], "weights": weights[i]} for i in sorted(ids)],
            "aggregated_weight_by_fund": {f: float(v) for f, v in per_fund.items()},
        })
    name_keys_by_fund = {f: {c["name_key"] for c in fund["constituents"]} for f, fund in funds.items()}
    cross_exact, first_token = [], []
    fund_ids = list(funds)
    for i, left in enumerate(fund_ids):
        for right in fund_ids[i + 1:]:
            cross_exact += sorted(name_keys_by_fund[left] & name_keys_by_fund[right])
            left_first = collections.defaultdict(list)
            for key in name_keys_by_fund[left]:
                left_first[key.split()[0]].append(key)
            for key in sorted(name_keys_by_fund[right]):
                token = key.split()[0]
                if token in left_first and key not in name_keys_by_fund[left]:
                    first_token.append({right: key, left: sorted(left_first[token])})
    starter_links = []
    for row in universe:
        if row["asset_class"] != "equity":
            continue
        held = [{"fund_id": f, "ticker_as_printed": c["ticker_as_printed"], "name_as_printed": c["name"],
                 "weight_fraction": fraction(c["weight_percent"])}
                for f, fund in funds.items() for c in fund["constituents"] if c["instrument_id"] == row["ticker"]]
        starter_links.append({"instrument_id": row["ticker"], "starter_name": row["name"],
                              "issuer_id": starter_issuer[row["ticker"]], "held_via": held})

    # ---------------------------------------------- fund sector breakdowns
    breakdowns = {
        "schema_version": SCHEMA_VERSION,
        "note": ("Supplementary, optional. FUND-LEVEL sector totals as published by the fund issuer on its product "
                 "page. They do not say which constituent belongs to which sector, so they cannot be attributed to "
                 "individual issuers. Provided because the SPY daily holdings file prints no sector ('-' on every "
                 "line). Weights are fractions, as published (two decimals in percent), never rescaled."),
        "funds": {},
    }
    sources = starter_sources()
    for fund_id, item in SECTOR_PAGE_ITEMS.items():
        record = pick_record(manifest, item, pinned)
        if record is None or fund_id not in funds:
            continue
        page = parse_ssga_fund_sector_breakdown(read_verified(record))
        if page["as_of_date"] != record["as_of_date_in_file"]:
            raise BuildError(f"{item}: as-of date differs from the manifest")
        total = sum((s["weight_percent"] for s in page["sectors"]), Decimal(0))
        breakdowns["funds"][fund_id] = {
            "fund_id": fund_id,
            "level": "fund",
            "as_of_date": page["as_of_date"],
            "retrieval_date": record["retrieval_date"],
            "source_id": record["source_id"],
            "sum_weight_fraction": fraction(total),
            "same_as_of_date_as_holdings": page["as_of_date"] == holdings_out["funds"][fund_id]["holdings_date"],
            "sectors": [{"sector": s["sector"], "weight_fraction": fraction(s["weight_percent"])} for s in page["sectors"]],
        }
        sources[record["source_id"]] = holdings_source(
            manifest, record,
            "The 'Fund Sector Breakdown' block embedded in the page is parsed into fund_sector_breakdowns.json "
            "(percent to fraction; not rescaled).",
            "Fund-level totals only: no constituent-level sector. The eleven sectors sum to "
            f"{fraction(total)}, so the issuer appears to show the breakdown without the cash position. Two "
            "decimals in percent. The page is dynamic HTML; a layout change stops the parser.")

    for fund_id, fund in funds.items():
        info = report_funds[fund_id]
        if fund_id == "SPY":
            processing = ("Parsed with a standard-library xlsx reader. Percent weights divided by 100; never rescaled. "
                          f"{info['n_constituents']} equity constituents kept; {len(fund['others'])} non-constituent "
                          "line(s) (cash 'US DOLLAR'; an unlisted contingent value right) summed separately. Share "
                          "classes of one company share an issuer_id (name-based grouping, cross-checked against the "
                          "CUSIP issuer prefix).")
            limitations = ("The Sector column prints '-' on every line: no constituent-level sector is available "
                           "from this file. Holdings as of one date only: a current snapshot, not a historical "
                           f"composition. All printed lines sum to {info['all_lines_weight']}, not 1 (the remainder "
                           "is not itemised). No publication date is printed in the file; the HTTP Last-Modified "
                           f"header was {fund['record']['http_last_modified']!r}. Company names are truncated by the issuer.")
        else:
            processing = ("Parsed with the csv module. Percent weights divided by 100; never rescaled. "
                          f"{info['n_constituents']} equity constituents kept; {len(fund['others'])} non-constituent "
                          "line(s) (cash, cash collateral, an index future, an unlisted zero-value rights line) summed "
                          "separately. Toronto-listed constituents get '<ticker as printed>.TO' as instrument_id.")
            limitations = ("Weights are printed with two decimals in percent, so each weight carries up to 0.005 "
                           f"percentage points of rounding and all printed lines sum to {info['all_lines_weight']}. "
                           "Sector labels are BlackRock's sector names (e.g. 'Communication'), sector level only: "
                           "they cannot separate oil producers from pipelines or other Energy companies. The index "
                           "future's notional exposure is not looked through. A current snapshot, not a historical "
                           "composition. No publication date is printed in the file.")
        sources[fund["record"]["source_id"]] = holdings_source(manifest, fund["record"], processing, limitations)

    controversies = build_controversies(manifest, instruments, sources, args.allow_missing_evidence)
    market_data, market_stats = build_market_data(universe)

    report = {
        "schema_version": SCHEMA_VERSION,
        "note": "Supplementary numbers behind docs/data-sources.md. Not read by the engine.",
        "valuation_date": VALUATION_DATE,
        "funds": report_funds,
        "funds_built_without_holdings": missing,
        "equity_funds_in_starter_universe_without_holdings": FUNDS_WITHOUT_HOLDINGS,
        "multi_instrument_issuers": multi_class,
        "cross_fund_identical_name_keys": cross_exact,
        "cross_fund_first_word_matches_for_review": first_token,
        "starter_equity_links": starter_links,
        "starter_equities_not_held_by_any_acquired_fund": unlinked_starter,
        "instrument_count": len(instruments),
        "issuer_count": len(by_issuer),
        "market_data": market_stats,
        "controversy_records": len(controversies["records"]),
        "controversy_evidence_files": [
            {k: e[k] for k in ("source_id", "path", "url_requested", "http_status", "retrieved_at_utc", "bytes",
                               "sha256", "document_date", "page_last_updated")}
            | {"sentences_verified": len(e["verified_phrases"])}
            for e in manifest["files"] if e["kind"] == "controversy_evidence"],
        "terms_pages": [
            {k: e[k] for k in ("source_id", "item", "path", "url_requested", "http_status", "retrieved_at_utc",
                               "bytes", "sha256", "retrieval_method")}
            | {"sentences_verified": len(e["verified_phrases"])}
            for e in manifest["files"] if e["kind"] == "terms_of_use"],
    }

    outputs = [
        ("holdings.json", dump_json(holdings_out)),
        ("instruments.json", dump_json({"schema_version": SCHEMA_VERSION, "instruments": instruments})),
        ("sources.json", dump_json({"schema_version": SCHEMA_VERSION, "sources": sources})),
        ("controversies.json", dump_json(controversies)),
        ("fund_sector_breakdowns.json", dump_json(breakdowns)),
        ("build_report.json", dump_json(report)),
        ("market_data.json", dump_json(market_data, compact=True)),
    ]
    for name, payload in outputs:
        write_bytes_atomic(PROCESSED_DIR / name, payload, overwrite=True)
        print(f"wrote {rel(PROCESSED_DIR / name)} ({len(payload)} bytes)")

    print()
    for fund_id, info in report_funds.items():
        print(f"{fund_id}: holdings_date={info['holdings_date']} n_holdings={info['n_constituents']} "
              f"coverage={info['coverage_fraction']} non_constituent={info['non_constituent_weight']} "
              f"all_lines={info['all_lines_weight']}")
    for fund_id in missing:
        print(f"{fund_id}: NO HOLDINGS (built with --allow-missing-fund): unknown coverage")
    print(f"instruments={len(instruments)} issuers={len(by_issuer)} "
          f"multi-instrument issuers={[g['issuer_id'] for g in multi_class]}")
    print(f"controversy records={len(controversies['records'])} sources={len(sources)}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BuildError as exc:
        print(f"BUILD FAILED - no output file was changed by this step: {exc}", file=sys.stderr)
        sys.exit(2)
