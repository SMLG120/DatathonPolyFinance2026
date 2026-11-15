#!/usr/bin/env python3
"""Audit the organizer-supplied starter files in data/starter/ (read-only).

Standard library only. Run from anywhere:

    python3 -I data/scripts/audit_starter.py \
        [--also-search "/path/outside/the/repo"] [--json data/processed/audit_starter.json]

It prints real numbers for every check the data-evidence brief asks for and
exits non-zero if a HARD expectation fails (31 tickers, no duplicate
(date, ticker), no missing / non-positive adj_close, 2022 replay coverage).
Everything else is reported as information; nothing in data/starter/ is
modified.

``--also-search`` looks for ``build_dataset.py`` in extra directories **by file
name only**: no file is opened there.
"""
from __future__ import annotations

import argparse
import bisect
import collections
import datetime as dt
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import REPO_ROOT, STARTER_DIR, dump_json, read_csv_dicts, rel, sha256_file, write_bytes_atomic  # noqa: E402

STARTER_FILES = [
    "assets_universe.csv",
    "prices_daily.csv",
    "corporate_actions.csv",
    "fx_usdcad_daily.csv",
    "macro_rates.csv",
    "sources_metadata.csv",
    "data_quality_warnings.txt",
    "STARTER_README.md",
]
PRICE_COLUMNS = ["date", "ticker", "open", "high", "low", "close", "adj_close", "volume", "currency"]

# Lead decision D7 (fictional personas) + the instrument Robert asks for.
ROBERT = ["XBB.TO", "SPY", "XIU.TO", "RY.TO", "JNJ"]
MATEO = ["XBB.TO", "XIU.TO", "ESGV", "MSFT", "CNR.TO", "FTS.TO"]
MATEO_PROPOSED = ["SPY"]
ROBERT_PROPOSED = ["NVDA"]
# Lead decision D6.
REPLAY_BASE_CUTOFF = dt.date(2021, 12, 31)
REPLAY_END_CUTOFF = dt.date(2022, 12, 30)

FAILURES: list[str] = []
FINDINGS: dict = {}


def section(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def hard(condition: bool, message: str) -> None:
    status = "ok  " if condition else "FAIL"
    print(f"  [{status}] {message}")
    if not condition:
        FAILURES.append(message)


def parse_date(text: str) -> dt.date:
    return dt.date.fromisoformat(text)


def to_float(text: str):
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def latest_on_or_before(sorted_dates: list[dt.date], day: dt.date):
    idx = bisect.bisect_right(sorted_dates, day)
    return sorted_dates[idx - 1] if idx else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--also-search", action="append", default=[], metavar="DIR",
                        help="extra directory searched for build_dataset.py by file name only")
    parser.add_argument("--json", metavar="PATH", help="also write the findings as JSON")
    args = parser.parse_args()

    absent = [name for name in STARTER_FILES if not (STARTER_DIR / name).exists()]
    if absent:
        print(f"AUDIT NOT RUN - starter file(s) missing in {rel(STARTER_DIR)}: {absent}. The Yahoo-derived files "
              "(prices_daily.csv, corporate_actions.csv) are git-ignored: copy the organizers' starter package "
              "into data/starter/ first.", file=sys.stderr)
        return 2

    # ------------------------------------------------------------------ files
    section("1. Files, sizes, hashes, row counts")
    file_info = {}
    for name in STARTER_FILES:
        path = STARTER_DIR / name
        if not path.exists():
            hard(False, f"{name} is present")
            continue
        info = {"bytes": path.stat().st_size, "sha256": sha256_file(path)}
        if name.endswith(".csv"):
            info["data_rows"] = len(read_csv_dicts(path))
        file_info[name] = info
        rows = f"{info['data_rows']:>6} data rows" if "data_rows" in info else " " * 16
        print(f"  {name:<26} {info['bytes']:>9} bytes  {rows}  sha256={info['sha256']}")
    FINDINGS["files"] = file_info

    universe = read_csv_dicts(STARTER_DIR / "assets_universe.csv")
    prices = read_csv_dicts(STARTER_DIR / "prices_daily.csv")
    fx_rows = read_csv_dicts(STARTER_DIR / "fx_usdcad_daily.csv")
    actions = read_csv_dicts(STARTER_DIR / "corporate_actions.csv")
    macro = read_csv_dicts(STARTER_DIR / "macro_rates.csv")

    # --------------------------------------------------------------- universe
    section("2. assets_universe.csv")
    uni_by_ticker = {row["ticker"]: row for row in universe}
    hard(len(universe) == 31, f"31 assets expected, found {len(universe)}")
    hard(len(uni_by_ticker) == len(universe), "tickers are unique in the universe file")
    class_counts = collections.Counter(row["asset_class"] for row in universe)
    print(f"  asset_class counts: {dict(sorted(class_counts.items()))}")
    bad_ccy = [t for t, row in uni_by_ticker.items()
               if row["currency"] != ("CAD" if t.endswith(".TO") else "USD")]
    hard(not bad_ccy, f"currency is CAD for .TO tickers and USD otherwise (exceptions: {bad_ccy})")
    FINDINGS["universe"] = {"n_assets": len(universe), "asset_class_counts": dict(class_counts)}

    def group_of(ticker: str) -> str:
        row = uni_by_ticker[ticker]
        if row["asset_class"] == "crypto":
            return "CRYPTO"
        return "TSX" if row["market"] == "TSX" else "US"

    # ----------------------------------------------------------------- prices
    section("3. prices_daily.csv - structure, tickers, ranges, duplicates, bad values")
    header = list(prices[0].keys())
    hard(header == PRICE_COLUMNS, f"columns are {PRICE_COLUMNS} (found {header})")
    print(f"  total data rows: {len(prices)}")

    by_ticker: dict[str, list[tuple[dt.date, dict]]] = collections.defaultdict(list)
    seen = collections.Counter()
    unparsable_dates = 0
    for row in prices:
        try:
            day = parse_date(row["date"])
        except ValueError:
            unparsable_dates += 1
            continue
        by_ticker[row["ticker"]].append((day, row))
        seen[(row["date"], row["ticker"])] += 1
    hard(unparsable_dates == 0, f"all dates parse as ISO dates (unparsable: {unparsable_dates})")

    price_tickers = set(by_ticker)
    hard(len(price_tickers) == 31, f"31 tickers expected in prices, found {len(price_tickers)}")
    hard(price_tickers == set(uni_by_ticker),
         "price tickers == universe tickers "
         f"(only in prices: {sorted(price_tickers - set(uni_by_ticker))}, "
         f"only in universe: {sorted(set(uni_by_ticker) - price_tickers)})")

    duplicates = {key: n for key, n in seen.items() if n > 1}
    hard(not duplicates, f"no duplicate (date, ticker) rows (duplicates: {len(duplicates)})")

    unsorted_tickers = [t for t, rows in by_ticker.items()
                        if [d for d, _ in rows] != sorted(d for d, _ in rows)]
    print(f"  tickers whose rows are not in ascending date order in the file: {unsorted_tickers or 'none'}")
    for rows in by_ticker.values():
        rows.sort(key=lambda item: item[0])

    bad_adj = []
    bad_other = collections.Counter()
    ohlc_inconsistent = 0
    zero_volume = []
    missing_volume = 0
    ccy_mismatch = collections.Counter()
    weekend_rows = collections.Counter()
    for ticker, rows in by_ticker.items():
        for day, row in rows:
            adj = to_float(row["adj_close"])
            if adj is None or not adj > 0:
                bad_adj.append((row["date"], ticker, row["adj_close"]))
            values = {}
            for col in ("open", "high", "low", "close"):
                val = to_float(row[col])
                values[col] = val
                if val is None or not val > 0:
                    bad_other[col] += 1
            if None not in values.values():
                if not (values["low"] <= min(values["open"], values["close"]) + 1e-9
                        and values["high"] >= max(values["open"], values["close"]) - 1e-9):
                    ohlc_inconsistent += 1
            vol = to_float(row["volume"])
            if vol is None:
                missing_volume += 1
            elif vol == 0:
                zero_volume.append((row["date"], ticker))
            if ticker in uni_by_ticker and row["currency"] != uni_by_ticker[ticker]["currency"]:
                ccy_mismatch[ticker] += 1
            if day.weekday() >= 5 and ticker in uni_by_ticker and group_of(ticker) != "CRYPTO":
                weekend_rows[ticker] += 1
    hard(not bad_adj, f"no missing or non-positive adj_close (bad rows: {len(bad_adj)})")
    print(f"  missing or non-positive open/high/low/close: {dict(bad_other) or 'none'}")
    print(f"  rows where low <= open,close <= high does not hold: {ohlc_inconsistent}")
    print(f"  rows with missing volume: {missing_volume}")
    print(f"  rows with zero volume: {len(zero_volume)} -> {zero_volume}")
    print(f"  price rows whose currency differs from the universe file: {dict(ccy_mismatch) or 'none'}")
    print(f"  weekend rows for non-crypto tickers: {dict(weekend_rows) or 'none'}")

    print()
    print(f"  {'ticker':<9} {'group':<6} {'rows':>5}  {'first':<10}  {'last':<10}  {'max gap (days)':>14}")
    per_ticker = {}
    for ticker in sorted(by_ticker, key=lambda t: (group_of(t) if t in uni_by_ticker else "?", t)):
        days = [d for d, _ in by_ticker[ticker]]
        gaps = [(b - a).days for a, b in zip(days, days[1:])]
        max_gap = max(gaps) if gaps else 0
        grp = group_of(ticker) if ticker in uni_by_ticker else "?"
        per_ticker[ticker] = {"group": grp, "rows": len(days), "first": days[0].isoformat(),
                              "last": days[-1].isoformat(), "max_gap_days": max_gap}
        print(f"  {ticker:<9} {grp:<6} {len(days):>5}  {days[0]}  {days[-1]}  {max_gap:>14}")
    FINDINGS["prices"] = {
        "rows": len(prices), "n_tickers": len(price_tickers), "duplicates": len(duplicates),
        "bad_adj_close_rows": len(bad_adj), "zero_volume_rows": zero_volume, "per_ticker": per_ticker,
    }

    last_adj_ne_close = [t for t, rows in by_ticker.items()
                         if abs(to_float(rows[-1][1]["adj_close"]) - to_float(rows[-1][1]["close"])) > 1e-6]
    print()
    print("  tickers whose adj_close differs from close on their last row "
          f"(expected none if back-adjusted from the latest date): {last_adj_ne_close or 'none'}")

    # --------------------------------------------------------------- calendars
    section("4. Calendar differences (no forward-fill, no alignment in the file)")
    group_dates: dict[str, set[dt.date]] = collections.defaultdict(set)
    group_rowcounts: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for ticker, rows in by_ticker.items():
        grp = group_of(ticker)
        group_dates[grp].update(d for d, _ in rows)
        group_rowcounts[grp][len(rows)] += 1
    calendars = {}
    for grp in ("TSX", "US", "CRYPTO"):
        counts = dict(sorted(group_rowcounts[grp].items()))
        tickers_in_group = sorted(t for t in by_ticker if group_of(t) == grp)
        identical = all({d for d, _ in by_ticker[t]} == group_dates[grp] for t in tickers_in_group)
        calendars[grp] = {"n_tickers": len(tickers_in_group), "distinct_dates": len(group_dates[grp]),
                          "rows_per_ticker": counts, "all_tickers_share_one_date_set": identical}
        print(f"  {grp:<6} tickers={len(tickers_in_group):>2}  distinct dates={len(group_dates[grp]):>4}  "
              f"rows per ticker {{rows: n_tickers}}={counts}  identical date set across tickers={identical}")
    tsx_only = sorted(group_dates["TSX"] - group_dates["US"])
    us_only = sorted(group_dates["US"] - group_dates["TSX"])
    union_equity = group_dates["TSX"] | group_dates["US"]
    print(f"  dates with TSX rows but no US rows: {len(tsx_only)}")
    print(f"    {[d.isoformat() for d in tsx_only]}")
    print(f"  dates with US rows but no TSX rows: {len(us_only)}")
    print(f"    {[d.isoformat() for d in us_only]}")
    print(f"  union of TSX and US dates: {len(union_equity)}; crypto-only dates: "
          f"{len(group_dates['CRYPTO'] - union_equity)}")
    calendars["tsx_only_dates"] = [d.isoformat() for d in tsx_only]
    calendars["us_only_dates"] = [d.isoformat() for d in us_only]
    FINDINGS["calendars"] = calendars

    # ---------------------------------------------------------------------- FX
    section("5. fx_usdcad_daily.csv - gaps and rate age under backward matching")
    fx = {}
    fx_dupes = 0
    fx_bad = 0
    inverse_max_diff = 0.0
    for row in fx_rows:
        day = parse_date(row["date"])
        rate = to_float(row["usdcad"])
        inv = to_float(row["cadusd"])
        if day in fx:
            fx_dupes += 1
        if rate is None or not rate > 0:
            fx_bad += 1
            continue
        fx[day] = rate
        if inv is not None:
            inverse_max_diff = max(inverse_max_diff, abs(inv - 1.0 / rate))
    fx_dates = sorted(fx)
    print(f"  rows: {len(fx_rows)}  range: {fx_dates[0]} -> {fx_dates[-1]}  "
          f"min usdcad={min(fx.values())}  max usdcad={max(fx.values())}")
    hard(fx_dupes == 0, f"no duplicate FX dates (duplicates: {fx_dupes})")
    hard(fx_bad == 0, f"no missing or non-positive usdcad (bad rows: {fx_bad})")
    print(f"  max |cadusd - 1/usdcad| = {inverse_max_diff:.2e} (README: cadusd is 1/usdcad rounded to 6 decimals)")
    weekdays_missing = [d for d in (fx_dates[0] + dt.timedelta(days=i)
                                    for i in range((fx_dates[-1] - fx_dates[0]).days + 1))
                        if d.weekday() < 5 and d not in fx]
    print(f"  Mon-Fri dates inside the FX range with no FX row: {len(weekdays_missing)}")

    fx_findings = {"rows": len(fx_rows), "first": fx_dates[0].isoformat(), "last": fx_dates[-1].isoformat(),
                   "weekdays_without_rate": len(weekdays_missing), "by_calendar": {}}
    for label, dates in (("US (USD equities and ETFs - the series that need conversion)", group_dates["US"]),
                         ("TSX (CAD, no conversion needed - for information)", group_dates["TSX"]),
                         ("CRYPTO (USD, 7 days a week)", group_dates["CRYPTO"])):
        dates_sorted = sorted(dates)
        no_exact = [d for d in dates_sorted if d not in fx]
        before_first = [d for d in dates_sorted if d < fx_dates[0]]
        ages = [(d, (d - latest_on_or_before(fx_dates, d)).days) for d in dates_sorted if d >= fx_dates[0]]
        max_age = max(age for _, age in ages)
        max_age_dates = [d.isoformat() for d, age in ages if age == max_age]
        age_hist = dict(sorted(collections.Counter(age for _, age in ages).items()))
        key = label.split(" ")[0]
        fx_findings["by_calendar"][key] = {
            "price_dates": len(dates_sorted), "dates_without_exact_fx_row": len(no_exact),
            "dates_before_first_fx_row": len(before_first), "max_fx_age_days": max_age,
            "max_age_dates": max_age_dates, "age_histogram_days": age_hist,
        }
        print(f"  {label}")
        print(f"    price dates: {len(dates_sorted)}; without an exact FX row: {len(no_exact)}; "
              f"before the first FX row (no backward match possible): {len(before_first)}")
        if key != "CRYPTO":
            print(f"    dates without an exact FX row: {[d.isoformat() for d in no_exact]}")
        print(f"    FX age histogram {{age in days: n price dates}}: {age_hist}")
        print(f"    maximum FX age: {max_age} day(s), reached on {len(max_age_dates)} date(s): "
              f"{max_age_dates[:12]}{' ...' if len(max_age_dates) > 12 else ''}")
        hard(not before_first, f"{key}: every price date has an FX rate on or before it")
    fx_no_price = sorted(set(fx_dates) - group_dates["US"])
    print(f"  FX dates with no US price row: {len(fx_no_price)} -> {[d.isoformat() for d in fx_no_price]}")
    FINDINGS["fx"] = fx_findings

    # ------------------------------------------------------- corporate actions
    section("6. corporate_actions.csv - incl. the CNQ.TO 1.021 'split' on 2022-08-22")
    action_counts = collections.Counter(row["action"] for row in actions)
    action_dupes = [k for k, n in collections.Counter(
        (r["ex_date"], r["ticker"], r["action"]) for r in actions).items() if n > 1]
    unknown_tickers = sorted({r["ticker"] for r in actions} - set(uni_by_ticker))
    no_action_tickers = sorted(set(uni_by_ticker) - {r["ticker"] for r in actions})
    print(f"  rows: {len(actions)}  by action: {dict(action_counts)}")
    print(f"  duplicate (ex_date, ticker, action): {len(action_dupes)}  tickers not in universe: "
          f"{unknown_tickers or 'none'}")
    print(f"  universe tickers with no corporate-action row: {no_action_tickers}")
    splits = [(r["ex_date"], r["ticker"], r["value"]) for r in actions if r["action"] == "split"]
    print(f"  split rows: {splits}")

    cnq_actions = [r for r in actions if r["ticker"] == "CNQ.TO" and "2021-12-01" <= r["ex_date"] <= "2022-12-31"]
    print("  CNQ.TO actions, 2021-12 -> 2022-12:")
    for r in cnq_actions:
        print(f"    {r['ex_date']}  {r['action']:<8} {r['value']:>9}  {r['unit']}")
    cnq = {d: row for d, row in by_ticker.get("CNQ.TO", [])}
    cnq_days = sorted(cnq)
    ex = dt.date(2022, 8, 22)
    cnq_finding = {}
    if ex in cnq:
        prev = cnq_days[cnq_days.index(ex) - 1]
        c0, c1 = to_float(cnq[prev]["close"]), to_float(cnq[ex]["close"])
        a0, a1 = to_float(cnq[prev]["adj_close"]), to_float(cnq[ex]["adj_close"])
        div = next((to_float(r["value"]) for r in cnq_actions
                    if r["ex_date"] == "2022-08-22" and r["action"] == "dividend"), None)
        split = next((to_float(r["value"]) for r in cnq_actions
                      if r["ex_date"] == "2022-08-22" and r["action"] == "split"), None)
        cnq_finding = {
            "prev_date": prev.isoformat(), "close_prev": c0, "close_ex": c1, "adj_prev": a0, "adj_ex": a1,
            "close_return": c1 / c0 - 1, "adj_close_return": a1 / a0 - 1,
            "adj_over_close_step": (a1 / c1) / (a0 / c0),
            "dividend_row": div, "split_row": split,
        }
        print(f"  CNQ.TO {prev} -> {ex}: close {c0} -> {c1} ({c1 / c0 - 1:+.4%}); "
              f"adj_close {a0} -> {a1} ({a1 / a0 - 1:+.4%})")
        print(f"    step in adj_close/close across the ex-date = {(a1 / c1) / (a0 / c0):.6f}")
        if div is not None:
            print(f"    dividend-only back-adjustment 1/(1 - {div}/{c0}) = {1 / (1 - div / c0):.6f}")
        early = [to_float(r["value"]) for r in cnq_actions
                 if r["action"] == "dividend" and "2022-03-01" <= r["ex_date"] < "2022-08-22"]
        later = [to_float(r["value"]) for r in cnq_actions
                 if r["action"] == "dividend" and "2022-08-22" < r["ex_date"] <= "2022-09-30"]
        if early and later and split:
            print(f"    regular dividend before the date {early} x {split} = "
                  f"{[round(v * split, 6) for v in early]} vs first regular dividend after {later}")
            cnq_finding["pre_date_dividends_times_split"] = [round(v * split, 6) for v in early]
            cnq_finding["post_date_regular_dividend"] = later
        print("    Reading (from the file alone, not checked against CNQ investor relations here):")
        print("    earlier dividends are scaled by 1/1.021, so the 1.021 factor was applied to the")
        print("    pre-2022-08-22 history like a split, AND adj_close also back-adjusts for the 0.75")
        print("    dividend on the same date. If both rows describe one special distribution, CNQ.TO's")
        print("    adj_close return across 2022-08-22 counts it twice (about +2.1 percentage points).")
    FINDINGS["corporate_actions"] = {"rows": len(actions), "by_action": dict(action_counts),
                                     "splits": splits, "cnq_2022_08_22": cnq_finding}

    # ------------------------------------------------------------------- macro
    section("7. macro_rates.csv (not used by the prototype's pipeline)")
    macro_series = collections.defaultdict(list)
    for row in macro:
        macro_series[row["series_id"]].append(row["date"])
    macro_dupes = sum(len(v) - len(set(v)) for v in macro_series.values())
    print(f"  rows: {len(macro)}  series: {len(macro_series)}  duplicate (date, series_id): {macro_dupes}")
    for sid in sorted(macro_series):
        days = sorted(macro_series[sid])
        print(f"    {sid:<24} {len(days):>5} rows  {days[0]} -> {days[-1]}")
    FINDINGS["macro"] = {"rows": len(macro), "series": {k: len(v) for k, v in macro_series.items()}}

    # ------------------------------------------------------------- 2022 replay
    section("8. 2022 replay coverage (D6): last observation on or before 2021-12-31 and 2022-12-30")
    wanted = []
    for label, tickers in (("Robert", ROBERT), ("Robert proposed", ROBERT_PROPOSED),
                           ("Mateo", MATEO), ("Mateo proposed", MATEO_PROPOSED)):
        for ticker in tickers:
            wanted.append((label, ticker))
    roles = collections.defaultdict(list)
    for label, ticker in wanted:
        roles[ticker].append(label)
    print(f"  {'ticker':<8} {'ccy':<3} {'base obs':<10} {'base adj_close':>14}  {'end obs':<10} "
          f"{'end adj_close':>13}  {'obs in 2022':>11}  {'FX base (age)':<16} {'FX end (age)':<16} used by")
    replay = {}
    no_coverage = []
    for ticker in sorted(roles, key=lambda t: (group_of(t), t)):
        rows = by_ticker.get(ticker, [])
        days = [d for d, _ in rows]
        base = latest_on_or_before(days, REPLAY_BASE_CUTOFF)
        end = latest_on_or_before(days, REPLAY_END_CUTOFF)
        if not (base is not None and end is not None and end > base):
            no_coverage.append(ticker)
            continue
        lookup = dict(rows)
        base_px = to_float(lookup[base]["adj_close"])
        end_px = to_float(lookup[end]["adj_close"])
        n_2022 = sum(1 for d in days if base < d <= end)
        ccy = uni_by_ticker[ticker]["currency"]
        entry = {"currency": ccy, "base_date": base.isoformat(), "base_adj_close": base_px,
                 "end_date": end.isoformat(), "end_adj_close": end_px, "observations_after_base_to_end": n_2022,
                 "local_currency_return": end_px / base_px - 1, "used_by": roles[ticker]}
        fx_base_txt = fx_end_txt = "n/a (CAD)"
        if ccy == "USD":
            fb, fe = latest_on_or_before(fx_dates, base), latest_on_or_before(fx_dates, end)
            ages_2022 = [(d - latest_on_or_before(fx_dates, d)).days for d in days if base <= d <= end]
            entry.update({"fx_base_date": fb.isoformat(), "fx_base_rate": fx[fb], "fx_base_age_days": (base - fb).days,
                          "fx_end_date": fe.isoformat(), "fx_end_rate": fx[fe], "fx_end_age_days": (end - fe).days,
                          "max_fx_age_days_in_window": max(ages_2022),
                          "cad_return": (end_px * fx[fe]) / (base_px * fx[fb]) - 1})
            fx_base_txt = f"{fb} ({(base - fb).days}d)"
            fx_end_txt = f"{fe} ({(end - fe).days}d)"
        replay[ticker] = entry
        print(f"  {ticker:<8} {ccy:<3} {base}  {base_px:>14.6f}  {end}  {end_px:>13.6f}  {n_2022:>11}  "
              f"{fx_base_txt:<16} {fx_end_txt:<16} {', '.join(roles[ticker])}")
    hard(not no_coverage, f"all {len(roles)} instruments have an observation on or before 2021-12-31 and a later one "
         f"on or before 2022-12-30 (without coverage: {no_coverage})")
    print()
    print("  Informational only (the engine owns the calculation): buy-and-hold adj_close return base -> end")
    for ticker, entry in replay.items():
        extra = ""
        if entry["currency"] == "USD":
            extra = (f"   in CAD {entry['cad_return']:+.4%} (USDCAD {entry['fx_base_rate']} -> {entry['fx_end_rate']}; "
                     f"max FX age inside the window {entry['max_fx_age_days_in_window']}d)")
        print(f"    {ticker:<8} local {entry['local_currency_return']:+.4%}{extra}")
    FINDINGS["replay_2022"] = replay

    # -------------------------------------------------------- build_dataset.py
    section("9. build_dataset.py (referenced by STARTER_README.md)")
    search_roots = [REPO_ROOT] + [Path(p) for p in args.also_search]
    found = []
    searched = []
    for root in search_roots:
        if not root.is_dir():
            print(f"  {root}: not a directory, skipped")
            continue
        n_names = 0
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in (".git", "node_modules", ".venv")]
            n_names += len(filenames)
            for name in filenames:
                if name.lower().startswith("build_dataset"):
                    found.append(str(Path(dirpath) / name))
        searched.append({"root": str(root), "file_names_examined": n_names})
        print(f"  searched by file name only: {root} ({n_names} file names examined, no file opened)")
    print(f"  files named build_dataset*: {found or 'NONE FOUND'}")
    # Wording fixed by the lead (docs/PLAN.md, P5). This search lists file names only and never opens an
    # archive, so it cannot confirm or refute the user's report; organizer delivery is not verified here.
    print("  -> Not located in the current checkout; user reports it exists in alphaforge_starter." if not found
          else "  -> a candidate exists; inspect it manually.")
    FINDINGS["build_dataset_py"] = {"searched": searched, "found": found}

    # ------------------------------------------------------------------ result
    section("AUDIT RESULT")
    if FAILURES:
        print(f"  {len(FAILURES)} hard expectation(s) FAILED:")
        for message in FAILURES:
            print(f"   - {message}")
    else:
        print("  all hard expectations hold (see the informational findings above)")
    FINDINGS["hard_failures"] = FAILURES
    if args.json:
        out = Path(args.json)
        write_bytes_atomic(out, dump_json(FINDINGS), overwrite=True)
        print(f"  findings written to {rel(out) if out.resolve().is_relative_to(REPO_ROOT) else out}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
