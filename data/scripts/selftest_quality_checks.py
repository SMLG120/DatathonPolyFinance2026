#!/usr/bin/env python3
"""Prove that quality_checks.py detects seeded defects (standard library only).

    python3 -I data/scripts/selftest_quality_checks.py

For each mutation it copies data/processed/ to a temporary directory, breaks one
thing, runs quality_checks.py --processed-dir <copy> and requires (a) a non-zero
exit code and (b) a FAIL line for the expected check id. The real
data/processed/ is never touched. Exits non-zero if any defect goes undetected.
"""
from __future__ import annotations

import copy
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import PROCESSED_DIR, dump_json, load_json  # noqa: E402

CHECKER = Path(__file__).resolve().parent / "quality_checks.py"


def m_percent_scale(docs):
    for row in docs["holdings.json"]["funds"]["SPY"]["holdings"]:
        row["weight_fraction"] = round(row["weight_fraction"] * 100, 10)


def m_rescaled_to_one(docs):
    fund = docs["holdings.json"]["funds"]["SPY"]
    total = sum(row["weight_fraction"] for row in fund["holdings"])
    for row in fund["holdings"]:
        row["weight_fraction"] = row["weight_fraction"] / total
    fund["coverage_fraction"] = 1.0


def m_duplicate_holding(docs):
    fund = docs["holdings.json"]["funds"]["XIU.TO"]
    fund["holdings"].append(copy.deepcopy(fund["holdings"][0]))
    fund["n_holdings"] += 1


def m_unknown_issuer(docs):
    docs["holdings.json"]["funds"]["SPY"]["holdings"][3]["issuer_id"] = "NO_SUCH_ISSUER"


def m_split_share_classes(docs):
    for row in docs["holdings.json"]["funds"]["SPY"]["holdings"]:
        if row["instrument_id"] == "GOOG":
            row["issuer_id"] = "ALPHABET_CLASS_C"
    docs["instruments.json"]["instruments"]["GOOG"]["issuer_id"] = "ALPHABET_CLASS_C"


def m_future_holdings_date(docs):
    docs["holdings.json"]["funds"]["SPY"]["holdings_date"] = "2099-01-01"


def m_holdings_dated_after_the_valuation_date(docs):
    """One day of look-ahead: a composition printed for the day after the portfolio is valued."""
    docs["holdings.json"]["funds"]["SPY"]["holdings_date"] = "2026-11-13"


def m_holdings_date_is_retrieval_date(docs):
    fund = docs["holdings.json"]["funds"]["XIU.TO"]
    fund["holdings_date"] = fund["retrieval_date"]


def m_invented_sector(docs):
    fund = docs["holdings.json"]["funds"]["SPY"]
    for row in fund["holdings"]:
        if row["instrument_id"] == "XOM":
            row["sector"], row["sector_source"] = "Energy", fund["source_id"]


def m_etf_label_as_sector(docs):
    fund = docs["holdings.json"]["funds"]["SPY"]
    fund["holdings"][0]["sector"], fund["holdings"][0]["sector_source"] = "Broad market (U.S.)", fund["source_id"]


def m_nvda_missing(docs):
    fund = docs["holdings.json"]["funds"]["SPY"]
    fund["holdings"] = [row for row in fund["holdings"] if row["instrument_id"] != "NVDA"]
    fund["n_holdings"] = len(fund["holdings"])


def m_xom_implausible(docs):
    for row in docs["holdings.json"]["funds"]["SPY"]["holdings"]:
        if row["instrument_id"] == "XOM":
            row["weight_fraction"] = 0.5


def m_ticker_not_joined(docs):
    for row in docs["holdings.json"]["funds"]["XIU.TO"]["holdings"]:
        if row["instrument_id"] == "RY.TO":
            row["instrument_id"] = "RY"
    docs["instruments.json"]["instruments"]["RY"] = dict(docs["instruments.json"]["instruments"]["RY.TO"], instrument_id="RY")


def m_unknown_source(docs):
    docs["holdings.json"]["funds"]["SPY"]["source_id"] = "made_up_source"


def m_source_hash_changed(docs):
    sid = docs["holdings.json"]["funds"]["SPY"]["source_id"]
    docs["sources.json"]["sources"][sid]["sha256"] = "0" * 64


def m_low_coverage(docs):
    fund = docs["holdings.json"]["funds"]["XIU.TO"]
    fund["holdings"] = fund["holdings"][:20]
    fund["n_holdings"] = 20
    fund["coverage_fraction"] = round(sum(r["weight_fraction"] for r in fund["holdings"]), 10)


def m_forward_filled_price(docs):
    series = docs["market_data.json"]["prices"]["XIU.TO"]["series"]
    series.insert(1, ["2021-11-13", series[0][1]])


def m_starter_sector_changed(docs):
    docs["instruments.json"]["instruments"]["SPY"]["sector"] = "Energy"


def m_bond_fund_in_equity_scope(docs):
    docs["instruments.json"]["instruments"]["XBB.TO"]["equity_scope"] = True


def m_controversy_without_source(docs):
    docs["controversies.json"]["records"].append({
        "record_id": "X", "issuer_id": "EXXON_MOBIL", "event_date": "2020-01-01", "nature": "ALLEGATION",
        "summary": "seeded", "source_ids": [], "coverage_note": "seeded"})


def m_controversy_source_not_evidence(docs):
    docs["controversies.json"]["records"][0]["source_ids"] = ["starter_assets_universe"]


def m_controversy_issuer_not_researched(docs):
    docs["controversies.json"]["records"][0]["issuer_id"] = "NVIDIA"


def m_controversy_unknown_nature(docs):
    docs["controversies.json"]["records"][0]["nature"] = "PROVEN_GUILTY"


def m_controversy_event_date_is_retrieval_date(docs):
    registry = docs["controversies.json"]
    registry["records"][0]["event_date"] = registry["registry_scope"]["research_date"]


def m_controversy_source_date_changed(docs):
    sid = docs["controversies.json"]["records"][0]["source_ids"][0]
    docs["sources.json"]["sources"][sid]["relevant_date"] = "2020-01-01"


def m_too_many_controversy_records(docs):
    registry = docs["controversies.json"]
    for n in range(3):
        registry["records"].append(dict(copy.deepcopy(registry["records"][0]), record_id=f"extra-{n}"))


def m_terms_statement_removed(docs):
    sid = docs["holdings.json"]["funds"]["XIU.TO"]["source_id"]
    docs["sources.json"]["sources"][sid]["terms"] = "Free to use."


def m_record_id_breaks_contract(docs):
    docs["controversies.json"]["records"][0]["record_id"] = "has a space"  # the id pattern allows no space


def m_currency_breaks_contract(docs):
    docs["instruments.json"]["instruments"]["NVDA"]["currency"] = "EUR"


def m_absence_means_clean(docs):
    docs["controversies.json"]["registry_scope"]["absence_meaning"] = "Absence means no controversy."


def m_sector_breakdown_percent(docs):
    for item in docs["fund_sector_breakdowns.json"]["funds"]["SPY"]["sectors"]:
        item["weight_fraction"] *= 100


MUTATIONS = [
    ("weights left in percent", m_percent_scale, "Q03"),
    ("weights rescaled to 100%", m_rescaled_to_one, "Q12"),
    ("duplicate (fund, instrument)", m_duplicate_holding, "Q04"),
    ("holding with an issuer missing from the registry", m_unknown_issuer, "Q09"),
    ("share classes of Alphabet not aggregated", m_split_share_classes, "Q10"),
    ("holdings_date in the future", m_future_holdings_date, "Q20"),
    ("holdings dated after the valuation date (look-ahead)", m_holdings_dated_after_the_valuation_date, "Q29"),
    ("holdings_date confused with retrieval_date", m_holdings_date_is_retrieval_date, "Q20"),
    ("sector invented for a constituent whose file prints none", m_invented_sector, "Q17"),
    ("ETF 'Broad market' label used as a constituent sector", m_etf_label_as_sector, "Q17"),
    ("NVDA missing from SPY", m_nvda_missing, "Q14"),
    ("XOM weight implausible", m_xom_implausible, "Q14"),
    ("RY not joined to RY.TO", m_ticker_not_joined, "Q16"),
    ("fund points to an unknown source", m_unknown_source, "Q19"),
    ("source hash differs from the raw manifest", m_source_hash_changed, "Q19"),
    ("coverage below 0.95 for an index fund", m_low_coverage, "Q06"),
    ("forward-filled price inserted", m_forward_filled_price, "Q21"),
    ("starter sector overwritten", m_starter_sector_changed, "Q18"),
    ("bond ETF marked equity_scope", m_bond_fund_in_equity_scope, "Q18"),
    ("controversy record without a source", m_controversy_without_source, "Q22"),
    ("registry says absence means no controversy", m_absence_means_clean, "Q22"),
    ("fund sector breakdown left in percent", m_sector_breakdown_percent, "Q23"),
    ("controversy record cites a source that is not retrieved evidence", m_controversy_source_not_evidence, "Q22"),
    ("controversy record for an issuer not listed as researched", m_controversy_issuer_not_researched, "Q22"),
    ("controversy record with an unknown nature", m_controversy_unknown_nature, "Q22"),
    ("controversy event_date replaced by the retrieval date", m_controversy_event_date_is_retrieval_date, "Q26"),
    ("evidence source date differs from the date printed on the page", m_controversy_source_date_changed, "Q26"),
    ("more than five controversy records", m_too_many_controversy_records, "Q22"),
    ("issuer reuse terms replaced by an unsupported claim", m_terms_statement_removed, "Q27"),
]
# Only meaningful when the contracts package is present (Q28 is SKIP without it).
if (Path(__file__).resolve().parents[2] / "contracts" / "python" / "byb_contracts" / "validators.py").exists():
    MUTATIONS += [
        ("record_id that the contracts' id pattern rejects", m_record_id_breaks_contract, "Q28"),
        ("instrument currency outside the contracts' enum", m_currency_breaks_contract, "Q28"),
    ]


def run(directory: Path) -> tuple[int, str]:
    proc = subprocess.run([sys.executable, "-I", str(CHECKER), "--processed-dir", str(directory)],
                          capture_output=True, text=True, timeout=300)
    return proc.returncode, proc.stdout + proc.stderr


def main() -> int:
    names = sorted(p.name for p in PROCESSED_DIR.glob("*.json"))
    originals = {name: load_json(PROCESSED_DIR / name) for name in names}
    undetected = 0
    with tempfile.TemporaryDirectory(prefix="byb_qc_selftest_") as tmp:
        base = Path(tmp) / "baseline"
        shutil.copytree(PROCESSED_DIR, base)
        code, _ = run(base)
        print(f"baseline (unmodified copy): exit {code}  -> {'ok' if code == 0 else 'UNEXPECTED FAILURE'}")
        if code != 0:
            print("the self-test needs a passing baseline: run quality_checks.py to see what fails "
                  "(on a fresh clone the git-ignored processed and raw files are absent)")
            return 1
        for index, (label, mutate, expected_check) in enumerate(MUTATIONS, start=1):
            docs = copy.deepcopy(originals)
            mutate(docs)
            target = Path(tmp) / f"m{index:02d}"
            target.mkdir()
            for name, doc in docs.items():
                (target / name).write_bytes(dump_json(doc, compact=(name == "market_data.json")))
            code, output = run(target)
            failed_ids = sorted({line.split("]")[1].split(":")[0].strip()
                                 for line in output.splitlines() if line.startswith("[FAIL]")})
            detected = code != 0 and expected_check in failed_ids
            undetected += 0 if detected else 1
            print(f"{'DETECTED ' if detected else 'MISSED   '} {index:02d} {label:<58} exit {code}  "
                  f"expected {expected_check}  failing checks {failed_ids}")
    print()
    print(f"SELF-TEST: {len(MUTATIONS) - undetected} of {len(MUTATIONS)} seeded defects detected")
    return 1 if undetected else 0


if __name__ == "__main__":
    sys.exit(main())
