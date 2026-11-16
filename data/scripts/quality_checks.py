#!/usr/bin/env python3
"""Quality checks for data/processed/ (standard library only). Exits non-zero on any FAIL.

    python3 -I data/scripts/quality_checks.py [--processed-dir DIR] [--allow-missing-raw] [--openpyxl]

Where it can, a check recomputes from the raw issuer file or the starter CSVs
instead of trusting the processed output. ``--openpyxl`` adds an independent
read of the SPY spreadsheet with the third-party openpyxl package:

    uv run --no-project --with openpyxl python3 -I data/scripts/quality_checks.py --openpyxl

When contracts/python/byb_contracts exists, the five contract files are also validated with the
contracts' own validators (Q28); without it that check is reported as SKIP.

Statuses: PASS, FAIL (exit 1), WARN (reported, does not fail), SKIP (could not run; says why).
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import re
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import (PROCESSED_DIR, RAW_MANIFEST, REPO_ROOT, SCHEMA_VERSION, STARTER_DIR, VALUATION_DATE,  # noqa: E402
                     load_json, read_csv_dicts, sha256_file)
from _holdings_parsers import (EQUITY, parse_ishares_holdings_csv, parse_ssga_daily_holdings,  # noqa: E402
                               read_xlsx_first_sheet)
from _terms import REUSE_STATEMENTS, TERMS_ITEM_FOR, quotations  # noqa: E402
from acquire_evidence import normalise, visible_text  # noqa: E402  (text helpers only; no I/O on import)

HOLDING_KEYS = {"fund_id", "issuer_id", "instrument_id", "name", "weight_fraction", "sector", "sector_source"}
FUND_KEYS = {"fund_id", "holdings_date", "publication_date", "retrieval_date", "source_id", "coverage_fraction",
             "non_constituent_weight", "non_constituent_note", "n_holdings", "holdings"}
INSTRUMENT_KEYS = {"instrument_id", "issuer_id", "name", "asset_class", "currency", "is_fund", "equity_scope",
                   "sector", "sector_source"}
SOURCE_KEYS = {"source_id", "publisher", "title", "url", "relevant_date", "retrieval_date", "sha256", "processing",
               "terms", "limitations"}
CONTROVERSY_KEYS = {"record_id", "issuer_id", "event_date", "nature", "summary", "source_ids", "coverage_note"}
NATURES = {"ALLEGATION", "REGULATORY_FINDING", "COURT_RULING", "SETTLEMENT", "COMPANY_DISCLOSURE"}

FULL_REPLICATION_INDEX_FUNDS = {"SPY", "XIU.TO"}
COVERAGE_RANGE = (0.95, 1.0005)
# Multi-instrument issuers documented in docs/data-sources.md for the 2026-11-12 snapshots.
# A different snapshot may legitimately change this list: then update the document and this table together.
DOCUMENTED_SHARE_CLASS_GROUPS = {
    "ALPHABET": {"GOOG", "GOOGL"},
    "FOX": {"FOX", "FOXA"},
    "NEWS": {"NWS", "NWSA"},
}
# Sanity bounds only (wide on purpose): they catch a wrong scale or a wrong row, not a market move.
PLAUSIBLE_SPY_WEIGHTS = {"NVDA": (0.01, 0.15), "XOM": (0.002, 0.03)}
# Direct and look-through exposure to these must join on one instrument_id and one issuer_id.
CROSS_LISTING = {
    "XIU.TO": {"RY.TO": "ROYAL_BANK_OF_CANADA", "TD.TO": "TORONTO_DOMINION_BANK", "SHOP.TO": "SHOPIFY",
               "CNQ.TO": "CANADIAN_NATURAL_RESOURCES", "ENB.TO": "ENBRIDGE", "CNR.TO": "CANADIAN_NATIONAL_RAILWAY",
               "FTS.TO": "FORTIS"},
    "SPY": {"NVDA": "NVIDIA", "MSFT": "MICROSOFT", "JNJ": "JOHNSON_AND_JOHNSON", "XOM": "EXXON_MOBIL",
            "GOOGL": "ALPHABET", "GOOG": "ALPHABET"},
}
RAW_PARSERS = {
    "SPY": lambda payload: parse_ssga_daily_holdings(payload, "SPY"),
    "XIU.TO": lambda payload: parse_ishares_holdings_csv(payload, "XIU"),
}
RAW_SUFFIX = {"SPY": "", "XIU.TO": ".TO"}

RESULTS: list[tuple[str, str, str]] = []


def record(status: str, check_id: str, message: str) -> None:
    RESULTS.append((status, check_id, message))
    print(f"[{status:<4}] {check_id}: {message}")


def check(condition: bool, check_id: str, message: str, detail: str = "") -> bool:
    record("PASS" if condition else "FAIL", check_id, message + (f" -- {detail}" if detail and not condition else ""))
    return condition


def dsum(values) -> Decimal:
    return sum((Decimal(repr(v)) for v in values), Decimal(0))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--processed-dir", default=str(PROCESSED_DIR))
    parser.add_argument("--allow-missing-raw", action="store_true",
                        help="raw files are git-ignored: on a clone without them, skip the raw-file checks")
    parser.add_argument("--openpyxl", action="store_true", help="independent xlsx read with openpyxl")
    args = parser.parse_args()
    processed = Path(args.processed_dir)
    today = dt.datetime.now(dt.timezone.utc).date().isoformat()

    # ------------------------------------------------------------ load files
    names = ["holdings.json", "instruments.json", "sources.json", "controversies.json", "market_data.json",
             "fund_sector_breakdowns.json"]
    loaded = {}
    for name in names:
        path = processed / name
        try:
            loaded[name] = load_json(path)
        except (OSError, ValueError) as exc:
            record("FAIL", "Q01", f"{name} cannot be read: {exc}")
    if len(loaded) != len(names):
        return summary()
    check(all(doc.get("schema_version") == SCHEMA_VERSION for doc in loaded.values()), "Q01",
          f"all {len(names)} processed files load and carry schema_version {SCHEMA_VERSION}")
    holdings, instruments = loaded["holdings.json"]["funds"], loaded["instruments.json"]["instruments"]
    sources, controversies = loaded["sources.json"]["sources"], loaded["controversies.json"]
    market, breakdowns = loaded["market_data.json"], loaded["fund_sector_breakdowns.json"]["funds"]
    manifest = load_json(RAW_MANIFEST)
    manifest_by_id = {entry["source_id"]: entry for entry in manifest["files"]}
    universe = read_csv_dicts(STARTER_DIR / "assets_universe.csv")

    # ------------------------------------------------------- holdings shape
    bad_fund_keys = {f: sorted(set(fund) ^ FUND_KEYS) for f, fund in holdings.items() if set(fund) != FUND_KEYS}
    bad_rows = [(f, row.get("instrument_id")) for f, fund in holdings.items() for row in fund["holdings"]
                if set(row) != HOLDING_KEYS or row["fund_id"] != f or fund["fund_id"] != f]
    check(not bad_fund_keys and not bad_rows, "Q02",
          f"holdings.json: {len(holdings)} fund(s) {sorted(holdings)}; fund and holding records have exactly the agreed fields",
          f"fund key differences {bad_fund_keys}; bad rows {bad_rows[:5]}")

    all_rows = [(f, row) for f, fund in holdings.items() for row in fund["holdings"]]
    out_of_range = [(f, r["instrument_id"], r["weight_fraction"]) for f, r in all_rows
                    if not isinstance(r["weight_fraction"], float) or not 0.0 <= r["weight_fraction"] <= 1.0]
    check(not out_of_range, "Q03", f"all {len(all_rows)} constituent weights are fractions in [0, 1]", str(out_of_range[:5]))

    dupes = [key for key, n in collections.Counter((f, r["instrument_id"]) for f, r in all_rows).items() if n > 1]
    check(not dupes, "Q04", "no duplicate (fund, instrument)", str(dupes[:5]))

    for fund_id, fund in holdings.items():
        total = dsum(r["weight_fraction"] for r in fund["holdings"])
        consistent = (fund["n_holdings"] == len(fund["holdings"])
                      and abs(total - Decimal(repr(fund["coverage_fraction"]))) < Decimal("1e-9"))
        check(consistent, "Q05", f"{fund_id}: n_holdings={fund['n_holdings']} and coverage_fraction="
              f"{fund['coverage_fraction']} equal the count and the sum of the listed weights (sum={total}); "
              "weights were not rescaled to 1", f"len={len(fund['holdings'])}")
        low, high = COVERAGE_RANGE
        in_range = low <= fund["coverage_fraction"] <= high
        if fund_id in FULL_REPLICATION_INDEX_FUNDS:
            check(in_range, "Q06", f"{fund_id}: coverage {fund['coverage_fraction']} is within [{low}, {high}] "
                  "(full-replication equity index fund)")
        else:
            record("PASS" if in_range else "WARN", "Q06",
                   f"{fund_id}: coverage {fund['coverage_fraction']} {'is within' if in_range else 'is OUTSIDE'} [{low}, {high}] (flag only)")
        biggest = max(r["weight_fraction"] for r in fund["holdings"])
        check(0.001 < biggest < 0.5 and 0 <= fund["non_constituent_weight"] < 0.05, "Q07",
              f"{fund_id}: scale is fractions (largest weight {biggest}, non-constituent weight "
              f"{fund['non_constituent_weight']}; neither percent nor basis points)")

    # --------------------------------------------- registry and issuer joins
    registry_problems = []
    for key, inst in instruments.items():
        if set(inst) != INSTRUMENT_KEYS or inst["instrument_id"] != key or not inst["issuer_id"]:
            registry_problems.append(key)
    check(not registry_problems, "Q08", f"instruments.json: {len(instruments)} records keyed by instrument_id with the agreed fields",
          str(registry_problems[:5]))
    missing_issuer = [(f, r["instrument_id"]) for f, r in all_rows
                      if r["instrument_id"] not in instruments
                      or instruments[r["instrument_id"]]["issuer_id"] != r["issuer_id"] or not r["issuer_id"]]
    check(not missing_issuer, "Q09", "every holding's instrument and issuer exist in instruments.json with the same issuer_id",
          str(missing_issuer[:5]))

    by_issuer = collections.defaultdict(set)
    for key, inst in instruments.items():
        by_issuer[inst["issuer_id"]].add(key)
    actual_groups = {issuer: ids for issuer, ids in by_issuer.items() if len(ids) > 1}
    check(actual_groups == DOCUMENTED_SHARE_CLASS_GROUPS, "Q10",
          f"multi-instrument issuers are exactly the documented share-class groups {sorted(DOCUMENTED_SHARE_CLASS_GROUPS)}",
          f"actual {dict((k, sorted(v)) for k, v in actual_groups.items())}")
    company_ids = {inst["issuer_id"] for inst in instruments.values() if inst["asset_class"] == "equity"}
    non_company_ids = {inst["issuer_id"] for inst in instruments.values() if inst["asset_class"] != "equity"}
    check(not company_ids & non_company_ids, "Q10", "no company issuer_id collides with a fund or crypto id",
          str(sorted(company_ids & non_company_ids)))

    # ------------------------------------------------------------ raw files
    raw_parsed = {}
    raw_problem = False
    used_source_ids = {fund["source_id"] for fund in holdings.values()} | {b["source_id"] for b in breakdowns.values()}
    used_source_ids |= {sid for rec in controversies["records"] for sid in rec["source_ids"]}
    for entry in manifest["files"]:
        path = REPO_ROOT / entry["path"]
        used = entry["source_id"] in used_source_ids
        if not path.exists():
            if used and not args.allow_missing_raw:
                record("FAIL", "Q11", f"raw file missing: {entry['path']} (used by processed outputs). Re-acquire it, "
                       "or pass --allow-missing-raw on a clone that only has the processed files")
                raw_problem = True
            else:
                record("SKIP", "Q11", f"raw file not present, hash not verifiable: {entry['path']}")
            continue
        digest = sha256_file(path)
        if not check(digest == entry["sha256"] and path.stat().st_size == entry["bytes"], "Q11",
                     f"raw file matches the manifest: {entry['path']} sha256={digest[:16]}... bytes={entry['bytes']}",
                     f"manifest sha256 {entry['sha256']}"):
            raw_problem = True
    for fund_id, fund in holdings.items():
        entry = manifest_by_id.get(fund["source_id"])
        if entry is None:
            record("FAIL", "Q11", f"{fund_id}: source_id {fund['source_id']} is not in the raw manifest")
            raw_problem = True
            continue
        path = REPO_ROOT / entry["path"]
        if path.exists() and sha256_file(path) == entry["sha256"]:
            raw_parsed[fund_id] = RAW_PARSERS[fund_id](path.read_bytes())
    starter_hash_ok = all(
        sources[sid]["sha256"] == sha256_file(STARTER_DIR / file_name)
        for sid, file_name in (("starter_assets_universe", "assets_universe.csv"), ("starter_prices_daily", "prices_daily.csv"),
                               ("starter_fx_usdcad", "fx_usdcad_daily.csv"), ("starter_corporate_actions", "corporate_actions.csv"),
                               ("starter_macro_rates", "macro_rates.csv")) if sid in sources)
    check(starter_hash_ok, "Q11", "starter file hashes in sources.json match data/starter/")

    # ----------------------------------- recompute from the raw issuer files
    for fund_id, fund in holdings.items():
        parsed = raw_parsed.get(fund_id)
        if parsed is None:
            record("SKIP", "Q12", f"{fund_id}: raw file unavailable, weights not re-derived from the issuer file")
            continue
        raw_equity = {line["ticker"] + RAW_SUFFIX[fund_id]: line for line in parsed["lines"] if line["kind"] == EQUITY}
        mismatches = []
        for row in fund["holdings"]:
            line = raw_equity.get(row["instrument_id"])
            if line is None or abs(Decimal(repr(row["weight_fraction"])) * 100 - line["weight_percent"]) > Decimal("1e-9"):
                mismatches.append(row["instrument_id"])
        raw_total = sum((line["weight_percent"] for line in parsed["lines"]), Decimal(0))
        check(not mismatches and len(raw_equity) == len(fund["holdings"]) and Decimal(95) <= raw_total <= Decimal("100.5"),
              "Q12", f"{fund_id}: every weight equals the percent printed in the issuer file / 100 "
              f"({len(raw_equity)} equity lines; all printed lines sum to {raw_total} percent)", str(mismatches[:5]))
        raw_other = sum((line["weight_percent"] for line in parsed["lines"] if line["kind"] != EQUITY), Decimal(0))
        check(abs(Decimal(repr(fund["non_constituent_weight"])) * 100 - raw_other) < Decimal("1e-9"), "Q12",
              f"{fund_id}: non_constituent_weight equals the cash/derivative/other lines of the issuer file ({raw_other} percent)")
        if all(line["market_value"] is not None for line in parsed["lines"]):
            total_mv = sum((line["market_value"] for line in parsed["lines"]), Decimal(0))
            worst = max(abs(line["weight_percent"] - 100 * line["market_value"] / total_mv) for line in parsed["lines"])
            check(worst <= Decimal("0.006"), "Q13", f"{fund_id}: printed weights agree with market value / total market value "
                  f"(largest gap {worst:.6f} percentage points; the file rounds to 0.01)")

    spy = holdings.get("SPY")
    if spy is None:
        record("FAIL", "Q14", "SPY holdings are absent")
    else:
        spy_weights = {r["instrument_id"]: r["weight_fraction"] for r in spy["holdings"]}
        for ticker, (low, high) in PLAUSIBLE_SPY_WEIGHTS.items():
            weight = spy_weights.get(ticker)
            check(weight is not None and low <= weight <= high, "Q14",
                  f"SPY holds {ticker} with a plausible weight: {weight} (sanity bounds {low}-{high})")
        for issuer, members in DOCUMENTED_SHARE_CLASS_GROUPS.items():
            by_issuer_sum = dsum(r["weight_fraction"] for r in spy["holdings"] if r["issuer_id"] == issuer)
            by_ticker_sum = dsum(spy_weights.get(t, 0.0) for t in members)
            parsed = raw_parsed.get("SPY")
            raw_sum = (sum((line["weight_percent"] for line in parsed["lines"] if line["ticker"] in members), Decimal(0)) / 100
                       if parsed else None)
            ok = by_issuer_sum == by_ticker_sum and all(t in spy_weights for t in members) and (
                raw_sum is None or abs(raw_sum - by_issuer_sum) < Decimal("1e-9"))
            check(ok, "Q15", f"SPY: issuer {issuer} aggregates {sorted(members)} = {by_issuer_sum}"
                  + (f" (issuer file, by ticker: {raw_sum})" if raw_sum is not None else " (raw file unavailable)"))

    for fund_id, expected in CROSS_LISTING.items():
        fund = holdings.get(fund_id)
        if fund is None:
            record("FAIL", "Q16", f"{fund_id} holdings are absent: cross-listing joins cannot be checked")
            continue
        rows = {r["instrument_id"]: r for r in fund["holdings"]}
        wrong = [i for i, issuer in expected.items()
                 if i not in rows or rows[i]["issuer_id"] != issuer or instruments.get(i, {}).get("issuer_id") != issuer]
        check(not wrong, "Q16", f"{fund_id}: direct and look-through exposure join on one instrument_id and issuer_id for "
              f"{sorted(expected)}", str(wrong))
    starter_equities = [row["ticker"] for row in universe if row["asset_class"] == "equity"]
    held_somewhere = {r["instrument_id"] for _, r in all_rows}
    not_held = [t for t in starter_equities if t not in held_somewhere]
    record("PASS" if not not_held else "WARN", "Q16",
           f"{len(starter_equities) - len(not_held)} of {len(starter_equities)} starter equities appear as constituents "
           f"under their starter instrument_id (not held by any acquired fund: {not_held or 'none'})")

    # ----------------------------------------------------------- sector rules
    sector_problems = []
    for fund_id, fund in holdings.items():
        parsed = raw_parsed.get(fund_id)
        raw_sector = ({line["ticker"] + RAW_SUFFIX[fund_id]: line["sector_raw"] for line in parsed["lines"]} if parsed else {})
        for row in fund["holdings"]:
            if (row["sector"] is None) != (row["sector_source"] is None):
                sector_problems.append((fund_id, row["instrument_id"], "sector and sector_source must be null together"))
            elif row["sector"] is not None and row["sector_source"] != fund["source_id"]:
                sector_problems.append((fund_id, row["instrument_id"], "sector_source is not the fund's issuer file"))
            elif row["sector"] is not None and "broad market" in row["sector"].lower():
                sector_problems.append((fund_id, row["instrument_id"], "ETF-level label used as a constituent sector"))
            elif parsed:
                printed = raw_sector.get(row["instrument_id"], "")
                expected = None if printed in ("", "-") else printed
                if row["sector"] != expected:
                    sector_problems.append((fund_id, row["instrument_id"], f"sector {row['sector']!r} != printed {printed!r}"))
    check(not sector_problems, "Q17", "constituent sectors are exactly what each issuer file prints (null when it prints none); "
          "none comes from an ETF-level label", str(sector_problems[:5]))
    for fund_id, fund in holdings.items():
        with_sector = sum(1 for r in fund["holdings"] if r["sector"] is not None)
        record("PASS" if with_sector == len(fund["holdings"]) else "WARN", "Q17",
               f"{fund_id}: {with_sector} of {len(fund['holdings'])} constituents have an issuer-printed sector"
               + ("" if with_sector == len(fund["holdings"]) else " -> sector-based rules are UNKNOWN for the rest"))
    starter_problems = [row["ticker"] for row in universe
                        if row["ticker"] not in instruments
                        or instruments[row["ticker"]]["sector"] != row["sector"]
                        or instruments[row["ticker"]]["sector_source"] != "starter_assets_universe"
                        or instruments[row["ticker"]]["currency"] != row["currency"]
                        or instruments[row["ticker"]]["asset_class"] != row["asset_class"]]
    check(not starter_problems and len(universe) == 31, "Q18",
          "the 31 starter instruments are registered with the organizer-assigned sector (sector_source starter_assets_universe)",
          str(starter_problems))
    flag_problems = [k for k, inst in instruments.items()
                     if inst["equity_scope"] != (inst["asset_class"] in ("equity", "etf_equity"))
                     or inst["is_fund"] != inst["asset_class"].startswith("etf_")]
    check(not flag_problems, "Q18", "equity_scope is true only for equities and equity ETFs; is_fund only for ETFs", str(flag_problems[:5]))

    # ---------------------------------------------------------------- sources
    referenced = set(used_source_ids)
    referenced |= {r["sector_source"] for _, r in all_rows if r["sector_source"]}
    referenced |= {inst["sector_source"] for inst in instruments.values() if inst["sector_source"]}
    unknown = sorted(referenced - set(sources))
    check(not unknown, "Q19", f"every referenced source_id ({len(referenced)}) exists in sources.json", str(unknown))
    bad_sources = [sid for sid, src in sources.items()
                   if set(src) != SOURCE_KEYS or src["source_id"] != sid or not re.fullmatch(r"[0-9a-f]{64}", src["sha256"] or "")
                   or not src["publisher"] or not src["terms"] or not src["limitations"] or not src["processing"]
                   or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", src["retrieval_date"] or "")
                   or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", src["relevant_date"] or "")]
    check(not bad_sources, "Q19", f"all {len(sources)} source records are complete (publisher, dates, sha256, processing, terms, limitations)",
          str(bad_sources))
    no_url = sorted(sid for sid, src in sources.items() if not src["url"])
    check(no_url in ([], ["starter_assets_universe"]), "Q19",
          "every source has a URL except the organizer-compiled universe file", str(no_url))
    hash_mismatch = [sid for sid, src in sources.items() if sid in manifest_by_id and src["sha256"] != manifest_by_id[sid]["sha256"]]
    check(not hash_mismatch, "Q19", "sources.json hashes equal the raw manifest hashes", str(hash_mismatch))

    # ------------------------------------------------------------------ dates
    for fund_id, fund in holdings.items():
        entry = manifest_by_id.get(fund["source_id"], {})
        parsed = raw_parsed.get(fund_id)
        file_date = parsed["holdings_date"] if parsed else entry.get("as_of_date_in_file")
        date_in_name = re.search(r"_(\d{4}-\d{2}-\d{2})\.", entry.get("path", ""))
        ok = (fund["holdings_date"] == file_date == entry.get("as_of_date_in_file")
              and fund["retrieval_date"] == entry.get("retrieval_date") == (date_in_name.group(1) if date_in_name else None)
              and entry.get("retrieved_at_utc", "")[:10] == fund["retrieval_date"]
              and fund["holdings_date"] <= fund["retrieval_date"] <= today
              and (fund["publication_date"] is None or fund["holdings_date"] <= fund["publication_date"] <= fund["retrieval_date"]))
        check(ok, "Q20", f"{fund_id}: holdings_date {fund['holdings_date']} is the as-of date printed in the issuer file"
              f"{'' if parsed else ' (per manifest; raw file unavailable)'}, retrieval_date {fund['retrieval_date']} is the "
              f"manifest's UTC retrieval date, holdings_date <= retrieval_date <= today ({today}); publication_date="
              f"{fund['publication_date']}")
        if fund["holdings_date"] == fund["retrieval_date"]:
            record("WARN", "Q20", f"{fund_id}: holdings_date equals retrieval_date; confirm against the file text")
        # Q29: no look-ahead. The portfolio is valued on VALUATION_DATE; a fund composition printed for a later date
        # is information nobody had on that date, so it may not be used for the look-through of that portfolio.
        check(fund["holdings_date"] <= VALUATION_DATE, "Q29",
              f"{fund_id}: holdings_date {fund['holdings_date']} is on or before the valuation date {VALUATION_DATE} (no look-ahead)",
              "the holdings file is dated AFTER the valuation date: use the issuer file as of the valuation date or earlier")

    # ------------------------------------------------------------ market data
    prices_csv = read_csv_dicts(STARTER_DIR / "prices_daily.csv")
    fx_csv = read_csv_dicts(STARTER_DIR / "fx_usdcad_daily.csv")
    csv_series = collections.defaultdict(list)
    for row in prices_csv:
        csv_series[row["ticker"]].append([row["date"], float(row["adj_close"])])
    market_ok = (market["valuation_date"] == VALUATION_DATE and set(market["prices"]) == {row["ticker"] for row in universe}
                 and all(market["prices"][t]["series"] == csv_series[t] for t in csv_series)
                 and all(market["prices"][row["ticker"]]["currency"] == row["currency"] for row in universe)
                 and market["fx_usdcad"] == [[row["date"], float(row["usdcad"])] for row in fx_csv])
    points = sum(len(v["series"]) for v in market["prices"].values())
    check(market_ok, "Q21", f"market_data.json: {len(market['prices'])} instruments, {points} adj_close points and "
          f"{len(market['fx_usdcad'])} FX points identical to data/starter/ (no forward-fill, no alignment); valuation_date {market['valuation_date']}")
    positive = all(value > 0 for v in market["prices"].values() for _, value in v["series"]) and all(r > 0 for _, r in market["fx_usdcad"])
    ascending = all([d for d, _ in v["series"]] == sorted({d for d, _ in v["series"]}) for v in market["prices"].values())
    last_ok = max(v["series"][-1][0] for v in market["prices"].values()) == VALUATION_DATE
    check(positive and ascending and last_ok, "Q21", "market_data.json: all values positive, dates strictly ascending, last date = valuation date")

    # ---------------------------------------------------------- controversies
    scope = controversies.get("registry_scope", {})
    records = controversies.get("records", [])
    structure_ok = (isinstance(records, list) and len(records) <= 5 and len({r["issuer_id"] for r in records}) <= 3
                    and all(set(r) == CONTROVERSY_KEYS and r["nature"] in NATURES and r["source_ids"] for r in records)
                    and len({r["record_id"] for r in records}) == len(records))
    check(structure_ok, "Q22", f"controversies.json: {len(records)} record(s) for {len({r['issuer_id'] for r in records})} issuer(s) "
          "(limits 5 and 3), agreed fields, known nature values, at least one source each")
    scope_ok = ("not assessed" in scope.get("absence_meaning", "").lower()
                and re.fullmatch(r"\d{4}-\d{2}-\d{2}", scope.get("research_date", "")) is not None
                and isinstance(scope.get("issuers_researched"), list)
                and all(r["issuer_id"] in scope["issuers_researched"] for r in records)
                and all(i in by_issuer for i in scope["issuers_researched"]))
    check(scope_ok, "Q22", f"registry_scope names the issuers researched {scope.get('issuers_researched')}, the research date "
          f"{scope.get('research_date')} and states that absence means 'not assessed'")
    evidence_ok = all(sid in sources and sid in manifest_by_id and manifest_by_id[sid]["kind"] == "controversy_evidence"
                      for r in records for sid in r["source_ids"])
    dates_ok = all(re.fullmatch(r"\d{4}-\d{2}-\d{2}", r["event_date"]) and r["event_date"] <= scope.get("research_date", "")
                   for r in records)
    check(evidence_ok and dates_ok, "Q22", "every controversy record cites retrieved, hashed evidence and a past event date")

    # ------------------------------------- evidence pages and terms quotations
    for entry in manifest["files"]:
        if entry["kind"] not in ("controversy_evidence", "terms_of_use", "regulatory_reference"):
            continue
        path = REPO_ROOT / entry["path"]
        if not path.exists() or sha256_file(path) != entry["sha256"]:
            record("SKIP", "Q26", f"{entry['path']}: raw page unavailable, recorded sentences not re-checked")
            continue
        text = visible_text(path.read_bytes())
        absent = [phrase for phrase in entry["verified_phrases"] if normalise(phrase) not in text]
        check(bool(entry["verified_phrases"]) and not absent, "Q26",
              f"{entry['source_id']}: all {len(entry['verified_phrases'])} sentences recorded as verified are literally "
              "present in the raw page", str(absent[:1]))
    for item in records:
        cited = [manifest_by_id[sid] for sid in item["source_ids"] if sid in manifest_by_id]
        printed = sorted(e.get("document_date") or "" for e in cited)
        ok = (len(cited) == len(item["source_ids"]) and item["event_date"] in printed
              and all(sources.get(e["source_id"], {}).get("relevant_date") == e.get("document_date") for e in cited)
              and all(e["retrieval_date"] <= scope.get("research_date", "") for e in cited))
        check(ok, "Q26", f"{item['record_id']}: event_date {item['event_date']} is a date printed on a cited page "
              f"{printed}; sources.json carries the same dates; evidence retrieved by the research date")
    for terms_item, statement in REUSE_STATEMENTS.items():
        pages = [e for e in manifest["files"] if e["kind"] == "terms_of_use" and e.get("item") == terms_item]
        if not pages:
            record("FAIL", "Q27", f"terms page {terms_item} is not registered in the raw manifest")
            continue
        page = max(pages, key=lambda e: e["retrieved_at_utc"])
        quoted = quotations(statement)
        unverified = [q for q in quoted if q not in page["verified_phrases"]]
        check(bool(quoted) and not unverified, "Q27",
              f"{terms_item}: the {len(quoted)} quotation(s) in the reuse statement are sentences verified in "
              f"{page['path']} (sha256 {page['sha256'][:16]}...)", str(unverified[:1]))
    retrieved = {sid: src for sid, src in sources.items() if sid in manifest_by_id}
    stale = [sid for sid, src in retrieved.items()
             if REUSE_STATEMENTS[TERMS_ITEM_FOR[manifest_by_id[sid]["item"]]] not in src["terms"]]
    check(not stale, "Q27", f"the terms field of the {len(retrieved)} retrieved sources carries the current reuse "
          "statement of its publisher", str(stale))

    # -------------------------------------------------- fund sector breakdowns
    for fund_id, block in breakdowns.items():
        total = dsum(s["weight_fraction"] for s in block["sectors"])
        ok = (Decimal("0.99") <= total <= Decimal("1.01") and block["source_id"] in sources
              and block["as_of_date"] <= block["retrieval_date"] <= today and block["level"] == "fund"
              and len({s["sector"] for s in block["sectors"]}) == len(block["sectors"]))
        energy = next((s["weight_fraction"] for s in block["sectors"] if s["sector"] == "Energy"), None)
        check(ok, "Q23", f"fund_sector_breakdowns.json: {fund_id} issuer-published fund-level sectors sum to {total} "
              f"(as of {block['as_of_date']}; Energy = {energy})")

    # ------------------------------------------------------------- git ignore
    try:
        ignored = subprocess.run(["git", "-C", str(REPO_ROOT), "check-ignore", "data/processed/market_data.json",
                                  "data/raw/etf_holdings/x", "data/starter/prices_daily.csv"],
                                 capture_output=True, text=True, timeout=30)
        if ignored.returncode not in (0, 1):  # 128: not a git work tree
            raise OSError(f"git check-ignore exited {ignored.returncode}: {ignored.stderr.strip()[:120]}")
        listed = set(ignored.stdout.split())
        check({"data/processed/market_data.json", "data/raw/etf_holdings/x", "data/starter/prices_daily.csv"} <= listed, "Q24",
              "git ignores data/processed/market_data.json, data/raw/ and the Yahoo-derived starter prices", str(sorted(listed)))
        derived = ["data/processed/holdings.json", "data/processed/instruments.json",
                   "data/processed/fund_sector_breakdowns.json", "data/processed/build_report.json"]
        state = subprocess.run(["git", "-C", str(REPO_ROOT), "check-ignore", *derived], capture_output=True, text=True, timeout=30)
        ignored_derived = sorted(set(state.stdout.split()))
        record("PASS" if len(ignored_derived) in (0, len(derived)) else "WARN", "Q24",
               f"issuer-derived processed files currently git-ignored: {len(ignored_derived)} of {len(derived)} "
               "(redistribution is the lead's decision, see docs/data-sources.md; all or none is expected)")
    except (OSError, subprocess.SubprocessError) as exc:
        record("SKIP", "Q24", f"git ignore rules not checked: {exc}")

    # ------------------------------------------------ independent xlsx reading
    if args.openpyxl:
        spy_entry = manifest_by_id.get(holdings["SPY"]["source_id"]) if "SPY" in holdings else None
        spy_path = REPO_ROOT / spy_entry["path"] if spy_entry else None
        if spy_path is None or not spy_path.exists():
            record("SKIP", "Q25", "SPY raw file unavailable for the openpyxl cross-check")
        else:
            try:
                import openpyxl  # type: ignore
            except ImportError:
                record("FAIL", "Q25", "openpyxl is not importable: run through `uv run --no-project --with openpyxl ...`")
            else:
                sheet = openpyxl.load_workbook(spy_path, read_only=True, data_only=True).worksheets[0]
                theirs = {}
                for row in sheet.iter_rows():
                    for cell in row:
                        if cell.value is not None:
                            theirs[cell.coordinate] = cell.value
                ours = {f"{col}{number}": text for number, cells in read_xlsx_first_sheet(spy_path.read_bytes())
                        for col, text in cells.items()}
                diffs = []
                for ref in sorted(set(ours) | set(theirs)):
                    a, b = ours.get(ref), theirs.get(ref)
                    same = (a is not None and b is not None
                            and (a == b or (isinstance(b, (int, float)) and Decimal(a) == Decimal(repr(b)))
                                 or str(b).replace("\r\n", "\n") == a.replace("\r\n", "\n")))
                    if not same:
                        diffs.append((ref, a, b))
                check(not diffs, "Q25", f"openpyxl {openpyxl.__version__} reads the same {len(theirs)} cells from the SPY "
                      f"spreadsheet as the standard-library reader ({len(ours)} cells)", str(diffs[:5]))

    # ---------------------------------------------------------------- contracts
    contracts_python = REPO_ROOT / "contracts" / "python"
    if not (contracts_python / "byb_contracts" / "validators.py").exists():
        record("SKIP", "Q28", "contracts/python/byb_contracts is not present: outputs not validated against contracts/schemas")
    else:
        sys.path.insert(0, str(contracts_python))
        sys.dont_write_bytecode = True  # do not write __pycache__ into a directory this script does not own
        try:
            from byb_contracts import validators as contract  # type: ignore
        except Exception as exc:  # noqa: BLE001 - any import problem is a finding, not a crash
            record("FAIL", "Q28", f"the contracts validators cannot be imported: {exc!r}")
        else:
            jobs = [
                ("holdings.json", lambda: contract.validate_holdings_snapshot(loaded["holdings.json"])),
                ("instruments.json", lambda: contract.validate_instrument_registry(loaded["instruments.json"])),
                ("market_data.json", lambda: contract.validate_market_data(loaded["market_data.json"])),
                ("sources.json", lambda: contract.validate_source_registry(loaded["sources.json"])),
                ("controversies.json", lambda: contract.validate_controversy_registry(
                    loaded["controversies.json"], loaded["sources.json"]["sources"].keys())),
            ]
            for name, job in jobs:
                try:
                    job()
                    record("PASS", "Q28", f"{name} satisfies contracts/schemas (byb_contracts.validators)")
                except Exception as exc:  # noqa: BLE001
                    record("FAIL", "Q28", f"{name} does not satisfy the contracts: {' '.join(str(exc).split())[:700]}")
    return summary()


def summary() -> int:
    counts = collections.Counter(status for status, _, _ in RESULTS)
    print()
    print(f"QUALITY CHECKS: {counts['PASS']} passed, {counts['FAIL']} failed, {counts['WARN']} warning(s), {counts['SKIP']} skipped")
    for status, check_id, message in RESULTS:
        if status in ("FAIL", "WARN", "SKIP"):
            print(f"  {status} {check_id}: {message}")
    return 1 if counts["FAIL"] else 0


if __name__ == "__main__":
    sys.exit(main())
