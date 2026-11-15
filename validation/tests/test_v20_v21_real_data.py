"""V20-V21: the engine on the real (git-ignored) data files.

V20  Robert (LEAD_DECISIONS D7): NVDA to 25%; exposure recomputed in exact rationals from holdings.json; the 2022
     replay recomputed by the validator from data/starter/prices_daily.csv and fx_usdcad_daily.csv (adj_close,
     backward-matched FX) and compared with the engine, which reads data/processed/market_data.json.
V21  Mateo (D7): SPY to 15% under an Energy-label exclusion and a controversy exclusion; ESGV has no holdings.

Tests skip, with the missing path in the reason, when a real data file is absent.
"""

from __future__ import annotations

import csv
import math
from fractions import Fraction

import pytest

from backend.engine import replay_period
from byb_contracts import validate_holdings_snapshot, validate_instrument_registry, validate_market_data

from validation.support import realdata as RD
from validation.support import reference as ref
from validation.support import universe as U
from validation.support.run import by_rule, check, close

ROBERT_RULES = lambda: [U.cap_any("cap", 0.10, origin="FICTIONAL_SCENARIO"), U.loss_budget("budget", 0.10, origin="FICTIONAL_SCENARIO")]  # noqa: E731


def _robert():
    return U.portfolio(RD.ROBERT["cash"], RD.ROBERT["positions"], "pf-robert-validator")


def _mateo():
    portfolio = U.portfolio(RD.MATEO["cash"], RD.MATEO["positions"], "pf-mateo-validator")
    portfolio["persona_id"] = "mateo"
    return portfolio


# --------------------------------------------------------------------------- data provenance sanity

@pytest.mark.vcase("V20")
def test_v20_real_snapshots_satisfy_the_data_contracts():
    data = RD.real_universe()
    validate_instrument_registry(data["instruments"])
    validate_holdings_snapshot(data["holdings"])
    validate_market_data(data["market_data"])


@pytest.mark.vcase("V20")
def test_v20_holdings_match_the_documented_figures_and_are_not_rescaled():
    """docs/data-sources.md section 5.1 and 5.2 (numbers typed here from the document)."""
    funds = RD.processed("holdings.json")["funds"]
    assert set(funds) == {"SPY", "XIU.TO"}, "ESGV and QQQ are deliberately absent: unknown, never zero"
    spy, xiu = funds["SPY"], funds["XIU.TO"]
    assert (spy["coverage_fraction"], spy["n_holdings"], spy["holdings_date"]) == (0.99871325, 503, "2026-11-12")
    assert (xiu["coverage_fraction"], xiu["n_holdings"], xiu["holdings_date"]) == (0.9977, 60, "2026-11-12")
    for fund in (spy, xiu):
        total = sum(Fraction(repr(row["weight_fraction"])) for row in fund["holdings"])
        assert total == Fraction(repr(fund["coverage_fraction"])), "coverage_fraction must be the plain sum of the printed weights"
        assert total < 1, "weights were rescaled to 100%"
    spy_by_instrument = {row["instrument_id"]: row for row in spy["holdings"]}
    assert spy_by_instrument["NVDA"]["weight_fraction"] == 0.06137977
    assert spy_by_instrument["GOOGL"]["issuer_id"] == spy_by_instrument["GOOG"]["issuer_id"] == "ALPHABET"
    alphabet = Fraction(repr(spy_by_instrument["GOOGL"]["weight_fraction"])) + Fraction(repr(spy_by_instrument["GOOG"]["weight_fraction"]))
    assert alphabet == Fraction("0.04817949")
    assert all(row["sector"] is None for row in spy["holdings"]), "SPY prints no constituent sector: nothing may be inferred"
    energy = sum(Fraction(repr(row["weight_fraction"])) for row in xiu["holdings"] if row["sector"] == "Energy")
    assert energy == Fraction("0.1666")


@pytest.mark.vcase("V20")
def test_v20_processed_market_data_equals_the_starter_adj_close_and_fx():
    """market_data.json must be the starter files' adj_close and usdcad, row for row: no forward fill, no re-adjustment."""
    tickers = list(RD.ROBERT["positions"]) + ["NVDA", "MSFT", "ESGV", "CNR.TO", "FTS.TO"]
    prices = ref.load_prices_csv(RD.need(RD.STARTER / "prices_daily.csv"), tickers)
    fx = ref.load_fx_csv(RD.need(RD.STARTER / "fx_usdcad_daily.csv"))
    market = RD.processed("market_data.json")
    for ticker in tickers:
        assert market["prices"][ticker]["currency"] == prices[ticker]["currency"]
        assert market["prices"][ticker]["series"] == prices[ticker]["series"], ticker
    assert market["fx_usdcad"] == fx


# --------------------------------------------------------------------------- V20 Robert

@pytest.mark.vcase("V20")
def test_v20_robert_nvda_exposure_direct_and_look_through():
    """NVIDIA after the purchase: 0.25 direct + 0.20 x 0.06137977 through SPY = 0.262275954.
    Uncovered: 0.20 x (1 - 0.99871325) + 0.10 x (1 - 0.9977) = 0.00025735 + 0.00023 = 0.00048735 -> upper 0.262763304.
    Royal Bank: 0.05 direct + 0.10 x 0.0958 through XIU.TO = 0.05958."""
    data = RD.real_universe()
    result = check(_robert(), ROBERT_RULES(), U.request("NVDA", 0.25), data)
    cap = by_rule(result)["cap"]
    assert cap["status"] == "FAIL"
    assert close(cap["measured"]["lower"], 0.262275954) and close(cap["measured"]["upper"], 0.262763304)
    assert close(cap["gap"], 0.162275954)
    assert [s["subject_id"] for s in cap["breaching_subjects"]] == ["NVIDIA"]
    assert cap["unknown_causes"] == ["PARTIAL_HOLDINGS"]
    assert [o["instrument_id"] for o in cap["out_of_scope"]] == ["XBB.TO"]
    assert cap["starting"]["status"] == "PASS"

    exact = ref.exposure(ref.proposed(_robert(), "NVDA", 0.25), data["instruments"], data["holdings"])
    assert exact["lower"]["NVIDIA"] == Fraction("0.262275954") and exact["U"] == Fraction("0.00048735")
    assert exact["lower"]["ROYAL_BANK_OF_CANADA"] == Fraction("0.05958")
    for row in result["exposure"]["issuers"]:
        assert close(row["proposed"]["lower"], float(exact["lower"][row["issuer_id"]]), 1e-12), row["issuer_id"]
    nvidia = next(row for row in result["exposure"]["issuers"] if row["issuer_id"] == "NVIDIA")
    assert close(nvidia["proposed"]["direct"], 0.25)
    assert [(p["fund_id"], round(p["known"], 12)) for p in nvidia["proposed"]["indirect_by_fund"]] == [("SPY", 0.012275954)]
    assert close(result["feasibility"]["cash_after"], 0.05)
    coverage = {row["fund_id"]: row["status"] for row in result["data_coverage"]}
    assert coverage == {"SPY": "PARTIAL", "XIU.TO": "PARTIAL"}


@pytest.mark.vcase("V20")
def test_v20_robert_2022_replay_recomputed_from_the_starter_csv_files():
    data = RD.real_universe()
    tickers = list(RD.ROBERT["positions"]) + ["NVDA"]
    prices = ref.load_prices_csv(RD.need(RD.STARTER / "prices_daily.csv"), tickers)
    fx = ref.load_fx_csv(RD.need(RD.STARTER / "fx_usdcad_daily.csv"))

    for label, positions in (("starting", dict(RD.ROBERT["positions"])), ("proposed", {**RD.ROBERT["positions"], "NVDA": 0.25})):
        cash = 1.0 - sum(positions.values())
        own = ref.replay(cash, positions, prices, fx)
        assert own["status"] == "COMPUTED"
        engine = replay_period({"cash_weight": cash, "positions": [{"instrument_id": k, "weight": v} for k, v in positions.items()]}, data["market_data"])
        assert close(engine["scenario_terminal_return"], own["terminal_return"], 1e-12), label
        assert close(engine["scenario_max_drawdown"], own["max_drawdown"], 1e-12), label
        assert engine["max_drawdown_date"] == own["max_drawdown_date"], label
        rows = {row["instrument_id"]: row for row in engine["instrument_returns"]}
        for instrument, value in own["returns"].items():
            assert close(rows[instrument]["return_cad"], value, 1e-12), instrument
            seen_base, seen_end = own["base"][instrument], own["end"][instrument]
            assert rows[instrument]["base_price_date"] == seen_base["price_date"] <= "2021-12-31"
            assert rows[instrument]["end_price_date"] == seen_end["price_date"] <= "2022-12-30"
            assert rows[instrument]["base_fx_date"] == seen_base["fx_date"] and rows[instrument]["end_fx_date"] == seen_end["fx_date"]
            if seen_base["fx_date"] is not None:
                assert seen_base["fx_date"] <= "2021-12-31" and seen_end["fx_date"] <= "2022-12-30", "FX must be matched backward"
                assert rows[instrument]["base_fx_age_days"] == seen_base["fx_age"] and rows[instrument]["end_fx_age_days"] == seen_end["fx_age"]

    # Sanity of the recomputation itself, by hand for one CAD and one USD instrument.
    def row(ticker, day):
        return next(r for r in prices[ticker]["series"] if r[0] == day)[1]

    usd = {r[0]: r[1] for r in fx}
    own = ref.replay(0.05, {**RD.ROBERT["positions"], "NVDA": 0.25}, prices, fx)
    assert close(own["returns"]["RY.TO"], row("RY.TO", "2022-12-30") / row("RY.TO", "2021-12-31") - 1, 1e-15)
    nvda = row("NVDA", "2022-12-30") * usd["2022-12-30"] / (row("NVDA", "2021-12-31") * usd["2021-12-31"]) - 1
    assert close(own["returns"]["NVDA"], nvda, 1e-15)
    by_hand = sum(weight * own["returns"][i] for i, weight in {**RD.ROBERT["positions"], "NVDA": 0.25}.items())
    assert close(own["terminal_return"], by_hand, 1e-12), "cash earns 0, buy and hold"


@pytest.mark.vcase("V20")
def test_v20_robert_replay_uses_adj_close_not_close_and_does_not_reapply_dividends():
    """With `close` instead of `adj_close` the 2022 CAD return of SPY, RY.TO and XBB.TO is clearly lower (dividends):
    the engine must agree with adj_close and disagree with close."""
    data = RD.real_universe()
    raw = {}
    with open(RD.need(RD.STARTER / "prices_daily.csv"), newline="", encoding="utf-8") as handle:
        for line in csv.DictReader(handle):
            if line["ticker"] in ("RY.TO", "XBB.TO", "XIU.TO") and line["date"] in ("2021-12-31", "2022-12-30"):
                raw[(line["ticker"], line["date"])] = (float(line["close"]), float(line["adj_close"]))
    engine = replay_period(_robert(), data["market_data"])
    rows = {row["instrument_id"]: row["return_cad"] for row in engine["instrument_returns"]}
    for ticker in ("RY.TO", "XBB.TO", "XIU.TO"):
        with_close = raw[(ticker, "2022-12-30")][0] / raw[(ticker, "2021-12-31")][0] - 1
        with_adj = raw[(ticker, "2022-12-30")][1] / raw[(ticker, "2021-12-31")][1] - 1
        assert close(rows[ticker], with_adj, 1e-12)
        assert abs(rows[ticker] - with_close) > 0.01, f"{ticker}: the engine's return looks like a price-only return"


@pytest.mark.vcase("V20")
def test_v20_robert_loss_budget_verdict_and_maximum_compliant_weight():
    data = RD.real_universe()
    tickers = list(RD.ROBERT["positions"]) + ["NVDA"]
    prices = ref.load_prices_csv(RD.need(RD.STARTER / "prices_daily.csv"), tickers)
    fx = ref.load_fx_csv(RD.need(RD.STARTER / "fx_usdcad_daily.csv"))
    start = ref.replay(0.30, dict(RD.ROBERT["positions"]), prices, fx)
    after = ref.replay(0.05, {**RD.ROBERT["positions"], "NVDA": 0.25}, prices, fx)

    result = check(_robert(), ROBERT_RULES(), U.request("NVDA", 0.25), data)
    budget = by_rule(result)["budget"]
    assert budget["status"] == "FAIL"
    assert close(budget["measured"]["lower"], -after["terminal_return"], 1e-12)
    assert close(budget["gap"], -after["terminal_return"] - 0.10, 1e-12)
    assert budget["starting"]["status"] == "PASS" and close(budget["starting"]["measured"]["lower"], -start["terminal_return"], 1e-12)
    assert result["summary"]["headline"] == "HAS_FAIL" and result["summary"]["counts"] == {"pass": 0, "fail": 2, "unknown": 0}
    # linearity (D6): loss(0.25) = loss(0) - 0.25 x r(NVDA)
    assert close(-after["terminal_return"], -start["terminal_return"] - 0.25 * after["returns"]["NVDA"], 1e-12)

    # Maximum: cap -> 0.10 - (0.20 x 0.06137977 + 0.00048735) = 0.087236696 ; budget -> (0.10 - L0) / (-r) ; cash 0.30.
    cap_end = 0.10 - (0.20 * 0.06137977 + 0.00048735)
    budget_end = (0.10 - (-start["terminal_return"])) / (-after["returns"]["NVDA"])
    expected = min(cap_end, budget_end, 0.30)
    maximum = result["max_compliant"]
    assert maximum["status"] == "SUPPORTED" and maximum["verified_by_rerun"] is True
    assert abs(maximum["final_direct_weight"] - expected) <= 1e-9
    assert maximum["binding_constraint"] == {"type": "RULE", "rule_id": "budget" if budget_end < cap_end else "cap"}
    assert maximum["final_direct_weight"] < 0.25, "the maximum is below the requested 25%"

    rerun = check(_robert(), ROBERT_RULES(), U.request("NVDA", maximum["final_direct_weight"]), data)
    assert [r["status"] for r in rerun["rule_results"]] == ["PASS", "PASS"]
    above = check(_robert(), ROBERT_RULES(), U.request("NVDA", maximum["final_direct_weight"] + 1e-6), data)
    assert by_rule(above)[maximum["binding_constraint"]["rule_id"]]["status"] == "FAIL"


@pytest.mark.vcase("V20")
def test_v20_robert_raising_the_cap_to_30_percent_leaves_the_budget_breach_visible():
    """D7 challenge: cap 0.10 -> 0.30 in a new version. NVIDIA upper 0.262763304 <= 0.30 -> PASS;
    the separately confirmed 2022 budget still FAILS with the same measured loss, budget and gap."""
    data = RD.real_universe()
    v1 = U.policy(ROBERT_RULES())
    v2 = U.policy([U.cap_any("cap", 0.10, origin="FICTIONAL_SCENARIO", status="SUPERSEDED", superseded_by="cap-2"),
                   U.cap_any("cap-2", 0.30, supersedes="cap"), U.loss_budget("budget", 0.10, origin="FICTIONAL_SCENARIO")], version=2, parent=1)
    first = check(_robert(), v1, U.request("NVDA", 0.25), data)
    second = check(_robert(), v2, U.request("NVDA", 0.25), data)
    assert by_rule(second)["cap-2"]["status"] == "PASS" and close(by_rule(second)["cap-2"]["gap"], 0.262763304 - 0.30)
    assert by_rule(second)["budget"]["status"] == "FAIL"
    for key in ("measured", "limit", "gap"):
        assert by_rule(second)["budget"][key] == by_rule(first)["budget"][key]
    assert second["summary"]["headline"] == "HAS_FAIL" and second["policy_consistency"]["status"] == "CONSISTENT"
    assert check(_robert(), v1, U.request("NVDA", 0.25), data) == first, "the earlier report is reproducible"


# --------------------------------------------------------------------------- V21 Mateo

def _mateo_rules():
    return [U.exclude_sector("energy", "Energy", 0.0), U.exclude_controversy("contro", ["SETTLEMENT", "REGULATORY_FINDING"], 0.0)]


@pytest.mark.vcase("V21")
def test_v21_mateo_energy_exclusion_starting_breach_is_separated_from_the_purchase_effect():
    """XIU.TO 0.20 x Energy 0.1666 = 0.03332 known Energy BEFORE the purchase (tolerance 0 -> already FAIL).
    Buying SPY to 0.15 proves nothing more (SPY prints no sector): lower unchanged; upper grows by the whole 0.15.
    Upper before = 0.03332 + U (ESGV 0.15 + XIU 0.20 x 0.0023 = 0.15046) = 0.18378 ; after = 0.33378."""
    data = RD.real_universe()
    result = check(_mateo(), _mateo_rules(), U.request("SPY", 0.15), data)
    energy = by_rule(result)["energy"]
    assert energy["status"] == "FAIL"
    assert close(energy["measured"]["lower"], 0.03332) and close(energy["measured"]["upper"], 0.33378)
    assert close(energy["starting"]["measured"]["lower"], 0.03332) and close(energy["starting"]["measured"]["upper"], 0.18378)
    assert {"PARTIAL_HOLDINGS", "MISSING_HOLDINGS", "UNCLASSIFIED_SECTOR"} <= set(energy["unknown_causes"])
    finding = next(f for f in result["starting_portfolio_findings"] if f["rule_id"] == "energy")
    assert close(finding["purchase_effect"]["lower_change"], 0.0), "the purchase is not proven to add Energy exposure"
    assert close(finding["purchase_effect"]["upper_change"], 0.15), "but the whole SPY position is possible Energy exposure"
    subjects = {s["subject_id"] for s in energy["breaching_subjects"]}
    assert {"ENBRIDGE", "CANADIAN_NATURAL_RESOURCES"} <= subjects and len(energy["breaching_subjects"]) == 9

    exact = ref.exposure(ref.proposed(_mateo(), "SPY", 0.15), data["instruments"], data["holdings"])
    assert exact["sector"]["Energy"] == Fraction("0.03332")
    lower, upper = ref.rule_bounds(_mateo_rules()[0], exact)
    assert close(energy["measured"]["upper"], float(upper), 1e-12)
    coverage = {row["fund_id"]: row["status"] for row in result["data_coverage"]}
    assert coverage == {"XIU.TO": "PARTIAL", "ESGV": "MISSING", "SPY": "PARTIAL"}
    assert result["max_compliant"]["status"] == "NO_FEASIBLE_PURCHASE" and result["max_compliant"]["final_direct_weight"] is None


@pytest.mark.vcase("V21")
def test_v21_mateo_controversy_rule_known_exposure_fails_and_the_rest_stays_unassessed():
    """docs/data-sources.md section 7: 0.20 x (0.0359 + 0.0345) = 0.01408 through XIU.TO before the purchase;
    SPY adds Exxon Mobil 0.15 x 0.01065439 = 0.0015981585 -> 0.0156781585. Upper = all in-scope equity = 0.75 - 0.25(XBB) ... = 0.65."""
    data = RD.real_universe()
    result = check(_mateo(), _mateo_rules(), U.request("SPY", 0.15), data)
    contro = by_rule(result)["contro"]
    assert contro["status"] == "FAIL"
    assert close(contro["starting"]["measured"]["lower"], 0.01408)
    assert close(contro["measured"]["lower"], 0.0156781585)
    in_scope = 0.20 + 0.15 + 0.05 + 0.05 + 0.05 + 0.15  # XIU, ESGV, MSFT, CNR, FTS, SPY (XBB.TO is a bond fund)
    assert close(contro["measured"]["upper"], in_scope)
    assert "REGISTRY_ABSENCE" in contro["unknown_causes"]
    assert {s["subject_id"] for s in contro["breaching_subjects"]} == {"ENBRIDGE", "CANADIAN_NATURAL_RESOURCES", "EXXON_MOBIL"}
    records = [r for r in result["evidence"] if r["metric_id"] == "controversy_record"]
    assert len(records) == 3 and all(r["source_ids"] and r["unit"] == "text" for r in records)
    assert result["summary"]["headline"] == "HAS_FAIL" and result["summary"]["starting_portfolio_breaches"] == 2


@pytest.mark.vcase("V21")
def test_v21_mateo_missing_esgv_holdings_make_an_issuer_cap_unknown_not_pass():
    """Cap 0.20 on any company: largest known exposure is far below 0.20, but ESGV (0.15, no file) could be one
    company: upper = lower + 0.15 + ... > 0.20 -> UNKNOWN, never PASS."""
    data = RD.real_universe()
    result = check(_mateo(), [U.cap_any("cap", 0.20)], U.request("SPY", 0.15), data)
    cap = by_rule(result)["cap"]
    exact = ref.exposure(ref.proposed(_mateo(), "SPY", 0.15), data["instruments"], data["holdings"])
    lower, upper = ref.rule_bounds(U.cap_any("cap", 0.20), exact)
    assert close(cap["measured"]["lower"], float(lower), 1e-12) and close(cap["measured"]["upper"], float(upper), 1e-12)
    assert float(lower) < 0.20 < float(upper)
    assert cap["status"] == "UNKNOWN" and cap["gap"] is None and "MISSING_HOLDINGS" in cap["unknown_causes"]
    assert result["summary"]["headline"] == "NO_FAIL_BUT_UNKNOWN"
    assert result["max_compliant"]["status"] == "WITHHELD"


@pytest.mark.vcase("V21")
def test_v21_real_data_share_classes_are_aggregated_for_alphabet():
    """GOOGL direct 0.05 plus SPY 0.20 x (0.02675267 + 0.02142682) = 0.059635898 for the company ALPHABET;
    upper = + 0.20 x 0.00128675 = 0.059893248. A cap of 0.0597 lies between them -> UNKNOWN; 0.06 -> PASS; 0.0596 -> FAIL."""
    data = RD.real_universe()
    portfolio = U.portfolio(0.75, {"SPY": 0.20, "GOOGL": 0.05})
    for limit, expected in ((0.0597, "UNKNOWN"), (0.06, "PASS"), (0.0596, "FAIL")):
        cap = by_rule(check(portfolio, [U.cap_one("cap", "ALPHABET", limit)], U.request("GOOGL", 0.05), data))["cap"]
        assert close(cap["measured"]["lower"], 0.059635898)
        assert close(cap["measured"]["upper"], 0.059893248)
        assert cap["status"] == expected, limit


@pytest.mark.vcase("V21")
@pytest.mark.parametrize("persona, instrument", [("robert", "NVDA"), ("robert", "SPY"), ("robert", "XIU.TO"), ("mateo", "SPY"), ("mateo", "ESGV"), ("mateo", "XOM")])
def test_v21_real_data_properties_hold(persona, instrument):
    """Conservation, bound ordering, documented status function and summary consistency on the real files."""
    data = RD.real_universe()
    portfolio = _robert() if persona == "robert" else _mateo()
    start = next((p["weight"] for p in portfolio["positions"] if p["instrument_id"] == instrument), 0.0)
    rules = [U.cap_any("cap", 0.10), U.exclude_sector("energy", "Energy", 0.02), U.exclude_named("named", ["NVIDIA", "EXXON_MOBIL"], 0.05),
             U.exclude_controversy("contro", ["SETTLEMENT"], 0.01), U.floor_one("floor", "NVIDIA", 0.01), U.loss_budget("budget", 0.10)]
    for target in (start, start + 0.05, start + 0.20):
        request = U.request(instrument, target)
        result = check(portfolio, rules, request, data)
        exact = ref.exposure(ref.proposed(portfolio, instrument, target), data["instruments"], data["holdings"])
        total = sum(exact["lower"].values(), Fraction(0)) + exact["U"]
        assert abs(float(total - exact["in_scope"])) < 1e-12, "known + uncovered must equal the in-scope equity weight"
        statuses = []
        for entry, rule in zip(result["rule_results"], rules):
            measured = entry["measured"]
            if rule["rule_type"] != "scenario_loss_budget":
                flagged = ["EXXON_MOBIL", "ENBRIDGE"]
                lower, upper = ref.rule_bounds(rule, exact, flagged=flagged)
                assert close(measured["lower"], float(lower), 1e-12) and close(measured["upper"], float(upper), 1e-12), entry["rule_id"]
            assert measured["lower"] <= measured["upper"] + 1e-15
            assert entry["status"] == ref.status(entry["rule_type"], measured["lower"], measured["upper"], entry["limit"])
            statuses.append(entry["status"])
        assert result["summary"]["headline"] == ref.headline("OK", result["policy_consistency"]["status"], statuses)
        maximum = result["max_compliant"]
        if maximum["status"] == "SUPPORTED":
            rerun = check(portfolio, rules, U.request(instrument, maximum["final_direct_weight"]), data)
            assert all(r["status"] == "PASS" for r in rerun["rule_results"]) and rerun["feasibility"]["status"] == "FEASIBLE"
        else:
            assert maximum["final_direct_weight"] is None
        assert math.isfinite(result["feasibility"]["cash_after"])
