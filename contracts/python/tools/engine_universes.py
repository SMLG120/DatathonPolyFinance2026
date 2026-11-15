"""The three synthetic universes used by contracts/fixtures/engine. All numbers are invented."""

from __future__ import annotations

from fixture_lib import SYNTHETIC_NOTE, SYNTHETIC_SOURCE_ID, fund_holdings, instrument, synthetic_sources

S = SYNTHETIC_SOURCE_ID
SCHEMA_VERSION = "1.0.0"


def _registry(entries):
    return {"schema_version": SCHEMA_VERSION, "instruments": {e["instrument_id"]: e for e in entries}}


def _universe(universe_id, note, instruments, funds, prices, fx, controversies):
    return {
        "fixture": True,
        "universe_id": universe_id,
        "synthetic": True,
        "synthetic_note": SYNTHETIC_NOTE + " " + note,
        "instruments": _registry(instruments),
        "holdings": {"schema_version": SCHEMA_VERSION, "funds": {f["fund_id"]: f for f in funds}},
        "market_data": {"schema_version": SCHEMA_VERSION, "valuation_date": "2026-11-12", "prices": prices, "fx_usdcad": fx},
        "controversies": controversies,
        "sources": synthetic_sources(),
    }


def _registry_scope(researched):
    return {
        "purpose": "SYNTHETIC registry for engine tests. Not real research.",
        "issuers_researched": researched,
        "research_date": "2026-11-14",
        "absence_meaning": "Absence from this registry means NOT ASSESSED, never 'no controversy'.",
        "source_policy": "Synthetic test data only.",
        "not_evidence": "A sector label is never evidence of a controversy.",
        "limits": "Synthetic.",
    }


def generic_universe():
    """SYN_* issuers, two share classes of ISS_B, a full fund, a partial fund, a fund with no file, a bond fund."""
    instruments = [
        instrument("SYN_A", "ISS_A", "Synthetic Company A", "equity", "CAD", "Technology", S),
        instrument("SYN_B1", "ISS_B", "Synthetic Company B (Class 1)", "equity", "CAD", "Financials", S),
        instrument("SYN_B2", "ISS_B", "Synthetic Company B (Class 2)", "equity", "CAD", "Financials", S),
        instrument("SYN_C", "ISS_C", "Synthetic Company C", "equity", "USD", "Energy", S),
        instrument("SYN_D", "ISS_D", "Synthetic Company D", "equity", "CAD", "Financials", S),
        instrument("SYN_E", "ISS_E", "Synthetic Company E", "equity", "USD"),
        instrument("FUND_A", "FUND_A", "Synthetic Equity Fund A (full holdings)", "etf_equity", "CAD", "Broad market (synthetic)", S),
        instrument("FUND_B", "FUND_B", "Synthetic Equity Fund B (partial holdings)", "etf_equity", "USD", "Broad market (synthetic)", S),
        instrument("FUND_C", "FUND_C", "Synthetic Equity Fund C (no holdings file)", "etf_equity", "USD", "Broad market (synthetic)", S),
        instrument("FUND_D", "FUND_D", "Synthetic Equity Fund D (full holdings)", "etf_equity", "CAD", "Broad market (synthetic)", S),
        instrument("BOND_X", "BOND_X", "Synthetic Bond Fund X", "etf_bond", "CAD", "Bonds (synthetic)", S),
    ]
    funds = [
        fund_holdings("FUND_A", [
            ("ISS_A", "SYN_A", "Synthetic Company A", 0.20, "Technology"),
            ("ISS_B", "SYN_B1", "Synthetic Company B (Class 1)", 0.10, "Financials"),
            ("ISS_B", "SYN_B2", "Synthetic Company B (Class 2)", 0.05, "Financials"),
            ("ISS_C", "SYN_C", "Synthetic Company C", 0.25, "Energy"),
            ("ISS_D", "SYN_D", "Synthetic Company D", 0.40, "Financials"),
        ]),
        fund_holdings("FUND_B", [
            ("ISS_A", "SYN_A", "Synthetic Company A", 0.30, "Technology"),
            ("ISS_C", "SYN_C", "Synthetic Company C", 0.10, "Energy"),
            ("ISS_E", "SYN_E", "Synthetic Company E", 0.20, None),
        ]),
        fund_holdings("FUND_D", [
            ("ISS_A", "SYN_A", "Synthetic Company A", 0.50, "Technology"),
            ("ISS_D", "SYN_D", "Synthetic Company D", 0.50, "Financials"),
        ]),
    ]
    prices = {
        "SYN_A": {"currency": "CAD", "series": [["2021-12-30", 100.0], ["2022-06-30", 90.0], ["2022-09-30", 85.0], ["2022-12-30", 95.0]]},
        "SYN_C": {"currency": "USD", "series": [["2021-12-31", 50.0], ["2022-06-30", 30.0], ["2022-12-30", 40.0]]},
        # Stops on 2022-06-30: at the scenario end date its latest price is 183 days old (case E20).
        "SYN_E": {"currency": "USD", "series": [["2021-12-31", 20.0], ["2022-06-30", 22.0]]},
    }
    fx = [["2021-12-30", 1.25], ["2022-06-30", 1.30], ["2022-09-30", 1.36], ["2022-12-30", 1.375]]
    controversies = {
        "schema_version": SCHEMA_VERSION,
        "registry_scope": _registry_scope(["ISS_C"]),
        "records": [{
            "record_id": "SYN-REC-1",
            "issuer_id": "ISS_C",
            "event_date": "2024-05-01",
            "nature": "REGULATORY_FINDING",
            "summary": "SYNTHETIC record used only to test the controversy rule. It does not describe a real event.",
            "source_ids": [S],
            "coverage_note": "Synthetic: only this one invented record exists for ISS_C.",
        }],
    }
    return _universe(
        "synthetic_universe",
        "FUND_A and FUND_D list 100% of their weight, FUND_B lists 60%, FUND_C has no holdings file. "
        "Only SYN_A, SYN_C and SYN_E have prices (used by the scenario replay cases); the SYN_E series deliberately "
        "stops on 2022-06-30.",
        instruments, funds, prices, fx, controversies,
    )


def _fillers(prefix, issuer_prefix, count, currency, name):
    return [instrument(f"{prefix}{i}", f"{issuer_prefix}{i}", f"{name} {i}", "equity", currency) for i in range(1, count + 1)]


def robert_universe():
    """Robert's real D7 instrument ids with INVENTED fund weights and INVENTED 2022 prices."""
    instruments = [
        instrument("XBB.TO", "XBB.TO", "iShares Core Canadian Universe Bond Index ETF", "etf_bond", "CAD", "Bonds (Canada aggregate)", S),
        instrument("SPY", "SPY", "SPDR S&P 500 ETF Trust", "etf_equity", "USD", "Broad market (U.S.)", S),
        instrument("XIU.TO", "XIU.TO", "iShares S&P/TSX 60 Index ETF", "etf_equity", "CAD", "Broad market (Canada)", S),
        instrument("RY.TO", "ROYAL_BANK_OF_CANADA", "Royal Bank of Canada", "equity", "CAD", "Financials", S),
        instrument("JNJ", "JOHNSON_AND_JOHNSON", "Johnson & Johnson", "equity", "USD", "Health Care", S),
        instrument("NVDA", "NVIDIA", "NVIDIA", "equity", "USD", "Information Technology", S),
        instrument("AAPL", "APPLE", "Apple", "equity", "USD", "Information Technology", S),
        instrument("MSFT", "MICROSOFT", "Microsoft", "equity", "USD", "Information Technology", S),
    ] + _fillers("SYN_US", "SYN_US_ISSUER_", 4, "USD", "Synthetic U.S. filler company") + _fillers("SYN_CA", "SYN_CA_ISSUER_", 3, "CAD", "Synthetic Canadian filler company")
    funds = [
        fund_holdings("SPY", [
            ("NVIDIA", "NVDA", "NVIDIA (synthetic weight)", 0.06, None),
            ("APPLE", "AAPL", "Apple (synthetic weight)", 0.07, None),
            ("MICROSOFT", "MSFT", "Microsoft (synthetic weight)", 0.06, None),
            ("JOHNSON_AND_JOHNSON", "JNJ", "Johnson & Johnson (synthetic weight)", 0.01, None),
        ] + [(f"SYN_US_ISSUER_{i}", f"SYN_US{i}", f"Synthetic U.S. filler company {i}", 0.20, None) for i in range(1, 5)]),
        fund_holdings("XIU.TO", [
            ("ROYAL_BANK_OF_CANADA", "RY.TO", "Royal Bank of Canada (synthetic weight)", 0.08, None),
        ] + [(f"SYN_CA_ISSUER_{i}", f"SYN_CA{i}", f"Synthetic Canadian filler company {i}", 0.30, None) for i in range(1, 4)]),
    ]
    prices = {
        "XBB.TO": {"currency": "CAD", "series": [["2021-12-31", 30.0], ["2022-06-30", 26.4], ["2022-12-30", 27.0]]},
        "SPY": {"currency": "USD", "series": [["2021-12-31", 400.0], ["2022-06-30", 300.0], ["2022-12-30", 325.0]]},
        "XIU.TO": {"currency": "CAD", "series": [["2021-12-31", 30.0], ["2022-06-30", 27.0], ["2022-12-30", 28.5]]},
        "RY.TO": {"currency": "CAD", "series": [["2021-12-31", 100.0], ["2022-06-30", 95.0], ["2022-12-30", 98.0]]},
        "JNJ": {"currency": "USD", "series": [["2021-12-31", 150.0], ["2022-06-30", 150.0], ["2022-12-30", 150.0]]},
        "NVDA": {"currency": "USD", "series": [["2021-12-31", 80.0], ["2022-06-30", 40.0], ["2022-12-30", 50.0]]},
    }
    fx = [["2021-12-31", 1.25], ["2022-06-30", 1.25], ["2022-12-30", 1.30]]
    controversies = {"schema_version": SCHEMA_VERSION, "registry_scope": _registry_scope([]), "records": []}
    return _universe(
        "robert_synthetic_universe",
        "The instrument ids are Robert's real D7 holdings, but the SPY and XIU.TO constituent weights and every 2022 price "
        "and FX rate here are INVENTED. They are NOT the real holdings or prices of SPY, XIU.TO or any company.",
        instruments, funds, prices, fx, controversies,
    )


def mateo_universe():
    """Mateo's real D7 instrument ids with INVENTED fund weights and sector rows. ESGV has no holdings file (D7)."""
    instruments = [
        instrument("XBB.TO", "XBB.TO", "iShares Core Canadian Universe Bond Index ETF", "etf_bond", "CAD", "Bonds (Canada aggregate)", S),
        instrument("XIU.TO", "XIU.TO", "iShares S&P/TSX 60 Index ETF", "etf_equity", "CAD", "Broad market (Canada)", S),
        instrument("ESGV", "ESGV", "Vanguard ESG U.S. Stock ETF", "etf_equity", "USD", "Broad market (U.S., ESG-screened)", S),
        instrument("SPY", "SPY", "SPDR S&P 500 ETF Trust", "etf_equity", "USD", "Broad market (U.S.)", S),
        instrument("MSFT", "MICROSOFT", "Microsoft", "equity", "USD", "Information Technology", S),
        instrument("CNR.TO", "CANADIAN_NATIONAL_RAILWAY", "Canadian National Railway", "equity", "CAD", "Industrials", S),
        instrument("FTS.TO", "FORTIS", "Fortis", "equity", "CAD", "Utilities", S),
        instrument("ENB.TO", "ENBRIDGE", "Enbridge", "equity", "CAD", "Energy", S),
        instrument("CNQ.TO", "CANADIAN_NATURAL_RESOURCES", "Canadian Natural Resources", "equity", "CAD", "Energy", S),
        instrument("RY.TO", "ROYAL_BANK_OF_CANADA", "Royal Bank of Canada", "equity", "CAD", "Financials", S),
        instrument("XOM", "EXXON_MOBIL", "Exxon Mobil", "equity", "USD", "Energy", S),
    ] + _fillers("SYN_US", "SYN_US_ISSUER_", 4, "USD", "Synthetic U.S. filler company") + _fillers("SYN_CA", "SYN_CA_ISSUER_", 4, "CAD", "Synthetic Canadian filler company")
    funds = [
        fund_holdings("XIU.TO", [
            ("ENBRIDGE", "ENB.TO", "Enbridge (synthetic weight)", 0.04, "Energy"),
            ("CANADIAN_NATURAL_RESOURCES", "CNQ.TO", "Canadian Natural Resources (synthetic weight)", 0.03, "Energy"),
            ("ROYAL_BANK_OF_CANADA", "RY.TO", "Royal Bank of Canada (synthetic weight)", 0.08, "Financials"),
            ("CANADIAN_NATIONAL_RAILWAY", "CNR.TO", "Canadian National Railway (synthetic weight)", 0.03, "Industrials"),
        ] + [(f"SYN_CA_ISSUER_{i}", f"SYN_CA{i}", f"Synthetic Canadian filler company {i}", 0.20, "Financials") for i in range(1, 5)]),
        fund_holdings("SPY", [
            ("EXXON_MOBIL", "XOM", "Exxon Mobil (synthetic weight)", 0.02, "Energy"),
            ("MICROSOFT", "MSFT", "Microsoft (synthetic weight)", 0.06, "Information Technology"),
        ] + [(f"SYN_US_ISSUER_{i}", f"SYN_US{i}", f"Synthetic U.S. filler company {i}", 0.23, "Industrials") for i in range(1, 5)]),
    ]
    controversies = {"schema_version": SCHEMA_VERSION, "registry_scope": _registry_scope([]), "records": []}
    universe = _universe(
        "mateo_synthetic_universe",
        "The instrument ids are Mateo's real D7 holdings, but the XIU.TO and SPY constituent weights and sector rows here are "
        "INVENTED. ESGV deliberately has no holdings file. The controversy registry is empty. "
        "No prices are needed (no scenario rule); the single FX row is a schema placeholder.",
        instruments, funds, {}, [["2026-11-12", 1.4]], controversies,
    )
    return universe
