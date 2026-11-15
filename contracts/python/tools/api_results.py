"""Full check_result bodies for the API fixtures, built on the hand-entered engine expectations.

The numbers are the ones in contracts/fixtures/engine/R1.json, R2.json and
M1.json (synthetic, see HAND_CALCS.md). This module adds what a complete result
carries around them: evidence records, template sentences, chart rows. The
summary is produced by byb_contracts.derive_summary, as it must be everywhere.
"""

from __future__ import annotations

import copy

import engine_cases as ec
from byb_contracts.constants import SCENARIOS
from byb_contracts.derive import derive_summary
from byb_contracts.result_validators import check_result_errors
from byb_contracts.templates import DISCLOSURES, EXPOSURE_SELECTION_NOTE
from fixture_lib import SYNTHETIC_SOURCE_ID, VALUATION_DATE

CALC = "fixture-calc-1.0.0"
S = [SYNTHETIC_SOURCE_ID]
AS_OF = {"type": "AS_OF", "date": VALUATION_DATE}
Y2022 = {"type": "RANGE", "start_date": "2021-12-31", "end_date": "2022-12-30"}
BOND_REASON = "Bond fund: outside the scope of the company-exposure rules; not assessed."


def ev(evidence_id, label, metric, value, kind, subject_id, state="NOT_APPLICABLE", *, period=None, sources=(), derived=(),
       formula=None, unit="fraction", via=None, assumptions=(), version=1):
    return {
        "evidence_id": evidence_id, "label": label, "metric_id": metric, "value": value, "unit": unit, "currency": None,
        "subject": {"kind": kind, "id": subject_id, "via_fund_id": via, "portfolio_state": state},
        "period": period or AS_OF, "source_ids": list(sources), "assumptions": list(assumptions),
        "derived_from": list(derived), "formula": formula, "calculation_version": CALC, "policy_version": version,
    }


def breakdown(direct, paths, extra):
    lower = round(direct + sum(k for _, k in paths), 10)
    return {"direct": direct, "indirect_by_fund": [{"fund_id": f, "known": k} for f, k in paths], "lower": lower, "upper": round(lower + extra, 10)}


def finish(core, *, persona_id, portfolio_id, policy_id, version, preview, request, rule_types, rule_text, coverage_meta,
           exposure, goal_context, evidence, max_text, finding_text=None, skipped_reason=None):
    """Complete a hand-entered core (engine_cases.*_expected) into a full, validated check_result."""
    result = {
        "schema_version": "1.0.0", "persona_id": persona_id, "portfolio_id": portfolio_id,
        "policy_id": None if preview else policy_id, "policy_version": None if preview else version, "preview": preview,
        "calculation_version": CALC, "valuation_date": VALUATION_DATE, "purchase_request": request,
        "execution": {"status": "OK", "code": None, "message": None},
        "feasibility": core["feasibility"], "policy_consistency": core["policy_consistency"],
    }
    rules = []
    for entry in core["rule_results"]:
        evidence_ids, reason = rule_text[entry["rule_id"]]
        full = {"rule_id": entry["rule_id"], "rule_type": rule_types[entry["rule_id"]], **{k: v for k, v in entry.items() if k != "rule_id"}}
        full["out_of_scope"] = [{**o, "reason": BOND_REASON} for o in entry.get("out_of_scope", [])]
        full["evidence_ids"], full["reason"] = evidence_ids, reason
        rules.append({k: full[k] for k in ("rule_id", "rule_type", "status", "measured", "limit", "gap", "breaching_subjects",
                                              "out_of_scope", "unknown_causes", "starting", "evidence_ids", "reason")})
    result["rule_results"] = rules
    result["rules_not_evaluated"] = [{**e, "reason": skipped_reason} for e in core.get("rules_not_evaluated", [])]
    result["starting_portfolio_findings"] = [
        {**f, "evidence_ids": finding_text[f["rule_id"]][0], "reason": finding_text[f["rule_id"]][1]} for f in core["starting_portfolio_findings"]]
    result["data_coverage"] = [
        {**c, "holdings_date": coverage_meta[c["fund_id"]][0], "source_id": coverage_meta[c["fund_id"]][1]} for c in core["data_coverage"]]
    scenario = core.get("scenario")
    if scenario:
        definition = SCENARIOS[scenario["scenario_id"]]
        scenario = {
            "scenario_id": scenario["scenario_id"], "label": definition["label"], "base_date": scenario["base_date"],
            "end_date": scenario["end_date"], "status": scenario["status"], "starting": scenario["starting"],
            "proposed": scenario["proposed"], "target_instrument_return": scenario["target_instrument_return"],
            "instrument_returns": scenario["instrument_returns"], "missing_instruments": scenario["missing_instruments"],
            "assumptions": list(definition["assumptions"]),
            "evidence_ids": ["ev-scn-start-return", "ev-scn-prop-return", "ev-scn-start-dd", "ev-scn-prop-dd", "ev-ret-nvda"],
        }
    result["scenario"] = scenario
    result["goal_context"] = goal_context
    result["max_compliant"] = {**core["max_compliant"], "reason": max_text[1], "evidence_ids": max_text[0]}
    result["exposure"] = exposure
    result["evidence"] = [{**e, "policy_version": None if preview else version} for e in evidence]
    result["summary"] = derive_summary(result)
    result["disclosures"] = list(DISCLOSURES)
    errors = check_result_errors(result)
    assert not errors, errors
    return result


# --------------------------------------------------------------------------------------------- Robert

def robert_evidence(cap_rule, cap_limit, cap_label, cap_gap, max_final):
    fx = "USD prices converted to CAD with the latest Bank of Canada rate on or before each date."
    return [
        ev("ev-w-nvda-start", "FICTIONAL_SCENARIO", "position_weight", 0.0, "INSTRUMENT", "NVDA", "STARTING"),
        ev("ev-w-nvda-target", "FICTIONAL_SCENARIO", "position_weight", 0.25, "INSTRUMENT", "NVDA", "PROPOSED",
           assumptions=["Hypothetical purchase requested by the user; not executed."]),
        ev("ev-w-spy", "FICTIONAL_SCENARIO", "position_weight", 0.20, "INSTRUMENT", "SPY", "STARTING"),
        ev("ev-w-xiu", "FICTIONAL_SCENARIO", "position_weight", 0.10, "INSTRUMENT", "XIU.TO", "STARTING"),
        ev("ev-w-ry", "FICTIONAL_SCENARIO", "position_weight", 0.05, "INSTRUMENT", "RY.TO", "STARTING"),
        ev("ev-cash-start", "FICTIONAL_SCENARIO", "cash_weight", 0.30, "PORTFOLIO", "pf-robert-fictional-1", "STARTING"),
        ev("ev-cash-after", "CALCULATION", "cash_after_purchase", 0.05, "PORTFOLIO", "pf-robert-fictional-1", "PROPOSED",
           derived=["ev-cash-start", "ev-w-nvda-start", "ev-w-nvda-target"], formula="0.30 - (0.25 - 0.00) = 0.05",
           assumptions=["Funded from cash; fees and taxes excluded."]),
        ev("ev-spy-nvda-weight", "FACT", "fund_constituent_weight", 0.06, "ISSUER", "NVIDIA", via="SPY", sources=S),
        ev("ev-xiu-ry-weight", "FACT", "fund_constituent_weight", 0.08, "ISSUER", "ROYAL_BANK_OF_CANADA", via="XIU.TO", sources=S),
        ev("ev-spy-coverage", "CALCULATION", "fund_coverage_fraction", 1.0, "FUND", "SPY", sources=S, formula="sum of the reported constituent weights = 1.00"),
        ev("ev-xiu-coverage", "CALCULATION", "fund_coverage_fraction", 0.98, "FUND", "XIU.TO", sources=S, formula="sum of the reported constituent weights = 0.98"),
        ev("ev-xiu-unattributed", "CALCULATION", "unattributed_fund_weight", 0.002, "FUND", "XIU.TO", "PROPOSED",
           derived=["ev-w-xiu", "ev-xiu-coverage"], formula="0.10 x (1 - 0.98) = 0.002",
           assumptions=["The part of a fund not covered by its holdings file could be any issuer; it is never treated as zero."]),
        ev("ev-nvda-via-spy", "CALCULATION", "issuer_exposure_via_fund", 0.012, "ISSUER", "NVIDIA", "PROPOSED", via="SPY",
           derived=["ev-w-spy", "ev-spy-nvda-weight"], formula="0.20 x 0.06 = 0.012"),
        ev("ev-nvda-lower", "CALCULATION", "exposure_lower", 0.262, "ISSUER", "NVIDIA", "PROPOSED",
           derived=["ev-w-nvda-target", "ev-nvda-via-spy"], formula="0.25 + 0.012 = 0.262"),
        ev("ev-nvda-upper", "CALCULATION", "exposure_upper", 0.264, "ISSUER", "NVIDIA", "PROPOSED",
           derived=["ev-nvda-lower", "ev-xiu-unattributed"], formula="0.262 + 0.002 = 0.264"),
        ev("ev-ry-lower-start", "CALCULATION", "exposure_lower", 0.058, "ISSUER", "ROYAL_BANK_OF_CANADA", "STARTING",
           derived=["ev-w-ry", "ev-w-xiu", "ev-xiu-ry-weight"], formula="0.05 + 0.10 x 0.08 = 0.058"),
        ev("ev-ry-upper-start", "CALCULATION", "exposure_upper", 0.060, "ISSUER", "ROYAL_BANK_OF_CANADA", "STARTING",
           derived=["ev-ry-lower-start", "ev-xiu-unattributed"], formula="0.058 + 0.002 = 0.060"),
        ev("ev-cap-threshold", cap_label, "rule_threshold", cap_limit, "RULE", cap_rule),
        ev("ev-cap-gap", "CALCULATION", "gap_to_limit", cap_gap, "RULE", cap_rule, "PROPOSED",
           derived=["ev-nvda-lower", "ev-nvda-upper", "ev-cap-threshold"],
           formula=(f"0.262 - {cap_limit:.2f} = {cap_gap:.3f}" if cap_gap > 0 else f"0.264 - {cap_limit:.2f} = {cap_gap:.3f}")),
        ev("ev-budget-threshold", "FICTIONAL_SCENARIO", "rule_threshold", 0.10, "RULE", "robert-loss-budget-1"),
        ev("ev-ret-nvda", "CALCULATION", "scenario_instrument_return", -0.35, "INSTRUMENT", "NVDA", period=Y2022, sources=S,
           formula="(50 x 1.30) / (80 x 1.25) - 1 = -0.35", assumptions=[fx]),
        ev("ev-scn-start-return", "CALCULATION", "scenario_terminal_return", -0.065, "PORTFOLIO", "pf-robert-fictional-1", "STARTING",
           period=Y2022, sources=S, formula="0.30 x (-0.10) + 0.20 x (-0.155) + 0.10 x (-0.05) + 0.05 x (-0.02) + 0.05 x 0.04 + 0.30 x 0 = -0.065",
           assumptions=list(SCENARIOS["replay_2022"]["assumptions"])),
        ev("ev-scn-prop-return", "CALCULATION", "scenario_terminal_return", -0.1525, "PORTFOLIO", "pf-robert-fictional-1", "PROPOSED",
           period=Y2022, derived=["ev-scn-start-return", "ev-ret-nvda", "ev-w-nvda-start", "ev-w-nvda-target"],
           formula="-0.065 + (0.25 - 0.00) x (-0.35) = -0.1525", assumptions=list(SCENARIOS["replay_2022"]["assumptions"])),
        ev("ev-scn-prop-loss", "CALCULATION", "scenario_loss", 0.1525, "PORTFOLIO", "pf-robert-fictional-1", "PROPOSED",
           period=Y2022, derived=["ev-scn-prop-return"], formula="-(-0.1525) = 0.1525"),
        ev("ev-budget-gap", "CALCULATION", "gap_to_limit", 0.0525, "RULE", "robert-loss-budget-1", "PROPOSED",
           derived=["ev-scn-prop-loss", "ev-budget-threshold"], formula="0.1525 - 0.10 = 0.0525"),
        ev("ev-scn-start-dd", "CALCULATION", "scenario_max_drawdown", -0.0985, "PORTFOLIO", "pf-robert-fictional-1", "STARTING",
           period=Y2022, sources=S, formula="lowest value 0.9015 on 2022-06-30 against a running maximum of 1.0000",
           assumptions=["Context only: drawdown is not a rule."]),
        ev("ev-scn-prop-dd", "CALCULATION", "scenario_max_drawdown", -0.2235, "PORTFOLIO", "pf-robert-fictional-1", "PROPOSED",
           period=Y2022, sources=S, formula="lowest value 0.7765 on 2022-06-30 against a running maximum of 1.0000",
           assumptions=["Context only: drawdown is not a rule."]),
        ev("ev-max-final", "CALCULATION", "max_compliant_final_weight", max_final, "INSTRUMENT", "NVDA", "PROPOSED",
           derived=["ev-cap-threshold", "ev-nvda-via-spy", "ev-xiu-unattributed", "ev-budget-threshold", "ev-scn-start-return", "ev-ret-nvda", "ev-cash-start"],
           formula=("min(cap: {0:.2f} - 0.012 - 0.002 = {1:.3f}; budget: (0.10 - 0.065) / 0.35 = 0.100; cash: 0.00 + 0.30 = 0.300) = {2:.3f}"
                    .format(cap_limit, cap_limit - 0.014, max_final))),
        ev("ev-max-added", "CALCULATION", "max_compliant_additional_purchase", max_final, "INSTRUMENT", "NVDA", "PROPOSED",
           derived=["ev-max-final", "ev-w-nvda-start"], formula=f"{max_final:.3f} - 0.000 = {max_final:.3f}"),
    ]


def robert_exposure():
    extra = 0.002
    def row(issuer, name, direct_start, direct_prop, paths):
        return {"issuer_id": issuer, "name": name, "starting": breakdown(direct_start, paths, extra), "proposed": breakdown(direct_prop, paths, extra)}
    return {
        "possible_extra": {"starting": extra, "proposed": extra},
        "issuers": [
            row("NVIDIA", "NVIDIA", 0.0, 0.25, [("SPY", 0.012)]),
            row("ROYAL_BANK_OF_CANADA", "Royal Bank of Canada", 0.05, 0.05, [("XIU.TO", 0.008)]),
            row("JOHNSON_AND_JOHNSON", "Johnson & Johnson", 0.05, 0.05, [("SPY", 0.002)]),
            row("SYN_US_ISSUER_1", "Synthetic U.S. filler company 1", 0.0, 0.0, [("SPY", 0.04)]),
            row("SYN_US_ISSUER_2", "Synthetic U.S. filler company 2", 0.0, 0.0, [("SPY", 0.04)]),
            row("SYN_US_ISSUER_3", "Synthetic U.S. filler company 3", 0.0, 0.0, [("SPY", 0.04)]),
            row("SYN_US_ISSUER_4", "Synthetic U.S. filler company 4", 0.0, 0.0, [("SPY", 0.04)]),
            row("SYN_CA_ISSUER_1", "Synthetic Canadian filler company 1", 0.0, 0.0, [("XIU.TO", 0.03)]),
            row("SYN_CA_ISSUER_2", "Synthetic Canadian filler company 2", 0.0, 0.0, [("XIU.TO", 0.03)]),
            row("SYN_CA_ISSUER_3", "Synthetic Canadian filler company 3", 0.0, 0.0, [("XIU.TO", 0.03)]),
        ],
        "selection_note": EXPOSURE_SELECTION_NOTE,
    }


def robert_result(variant):
    """variant: 'v1' (cap 0.10), 'v2' (cap raised to 0.30) or 'preview' (draft cap 0.20, nothing stored)."""
    request = {"instrument_id": "NVDA", "target_direct_weight": 0.25, "funding": "CASH", "original_words": ec.ROBERT_REQUEST_WORDS}
    budget_text = (["ev-scn-prop-loss", "ev-budget-threshold", "ev-budget-gap", "ev-scn-prop-return"],
                   "Replayed through 2022, the allocation after the purchase ends 15.25% lower; the confirmed budget is a 10.0% loss. "
                   "The rule fails by 5.25 percentage points. This replays an assumed allocation through history and is not a forecast.")
    if variant == "v1":
        core, cap_rule, cap_limit, cap_label, cap_gap, max_final, version = ec.robert_expected_v1(), "robert-issuer-cap-1", 0.10, "FICTIONAL_SCENARIO", 0.162, 0.086, 1
        cap_reason = ("Total exposure to NVIDIA after the purchase is between 26.2% and 26.4% of the portfolio (25.0% direct, 1.2% through SPY, "
                      "up to 0.2% that the incomplete XIU.TO holdings cannot rule out). The confirmed limit is 10.0%: the rule fails by 16.2 percentage points.")
        max_reason = ("The largest final direct weight of NVDA that passes every confirmed rule with cash funding is 8.6% (an additional purchase of 8.6%). "
                      "The single-company limit binds first. Verified by re-running the same checks at that weight.")
    elif variant == "v2":
        core, cap_rule, cap_limit, cap_label, cap_gap, max_final, version = ec.robert_expected_v2(), "robert-issuer-cap-2", 0.30, "FACT", -0.036, 0.10, 2
        cap_reason = ("Total exposure to NVIDIA after the purchase is between 26.2% and 26.4% of the portfolio. The confirmed limit is now 30.0%: "
                      "the rule passes with 3.6 percentage points of headroom.")
        max_reason = ("The largest final direct weight of NVDA that passes every confirmed rule with cash funding is 10.0% (an additional purchase of 10.0%). "
                      "The 2022 loss budget binds first. Verified by re-running the same checks at that weight.")
    else:
        core = ec.robert_expected_v1()
        cap_rule, cap_limit, cap_label, cap_gap, max_final, version = "robert-issuer-cap-1", 0.20, "ASSUMPTION", 0.062, 0.10, None
        core["rule_results"][0].update({"limit": 0.20, "gap": 0.062})
        core["max_compliant"] = ec.maxc("SUPPORTED", 0.10, 0.10, "robert-loss-budget-1")
        cap_reason = ("PREVIEW with a draft limit of 20.0%: total exposure to NVIDIA after the purchase would be between 26.2% and 26.4%, "
                      "6.2 percentage points above the draft limit. The confirmed policy is unchanged.")
        max_reason = ("PREVIEW: with a draft limit of 20.0%, the largest final direct weight of NVDA that passes every evaluated rule is 10.0%; "
                      "the 2022 loss budget binds first. Verified by re-running the same checks at that weight.")
    evidence = robert_evidence(cap_rule, cap_limit, cap_label, cap_gap, max_final)
    if variant == "preview":
        evidence[[e["evidence_id"] for e in evidence].index("ev-cap-threshold")]["assumptions"] = ["Draft threshold from a slider preview; not confirmed."]
    statuses = {r["rule_id"]: r["status"] for r in core["rule_results"]}
    goal_context = [
        {"objective_id": "obj-robert-1", "context_type": "LINKED_RULE_RESULTS",
         "text": ("Two rules are linked to this objective as context: the single-company limit ({}) and the 2022 loss budget ({}). "
                  "The objective itself is qualitative and has no PASS or FAIL.").format(statuses[cap_rule], statuses["robert-loss-budget-1"]),
         "evidence_ids": ["ev-cap-gap", "ev-budget-gap"]},
        {"objective_id": "obj-robert-1", "context_type": "CONCENTRATION",
         "text": "Largest single-company exposure: 5.8% to 6.0% (Royal Bank of Canada) before the purchase, 26.2% to 26.4% (NVIDIA) after it.",
         "evidence_ids": ["ev-ry-lower-start", "ev-ry-upper-start", "ev-nvda-lower", "ev-nvda-upper"]},
        {"objective_id": "obj-robert-1", "context_type": "SCENARIO_DRAWDOWN",
         "text": "Deepest fall inside the 2022 replay: 9.85% before the purchase, 22.35% after it. Context only; drawdown is not one of the rules.",
         "evidence_ids": ["ev-scn-start-dd", "ev-scn-prop-dd"]},
    ]
    return finish(
        core, persona_id="robert", portfolio_id="pf-robert-fictional-1", policy_id="pol-robert-demo", version=version,
        preview=variant == "preview", request=request,
        rule_types={cap_rule: "max_issuer_exposure", "robert-loss-budget-1": "scenario_loss_budget"},
        rule_text={cap_rule: (["ev-nvda-lower", "ev-nvda-upper", "ev-cap-threshold", "ev-cap-gap", "ev-xiu-unattributed"], cap_reason),
                   "robert-loss-budget-1": budget_text},
        coverage_meta={"SPY": ("2026-11-12", SYNTHETIC_SOURCE_ID), "XIU.TO": ("2026-11-12", SYNTHETIC_SOURCE_ID)},
        exposure=robert_exposure(), goal_context=goal_context, evidence=evidence,
        max_text=(["ev-max-final", "ev-max-added"], max_reason),
        skipped_reason="Superseded by robert-issuer-cap-2 in this policy version; kept for history, not evaluated.",
    )


# --------------------------------------------------------------------------------------------- Mateo

def mateo_result():
    request = {"instrument_id": "SPY", "target_direct_weight": 0.15, "funding": "CASH", "original_words": "Buy SPY so that it is 15% of my portfolio."}
    pf = "pf-mateo-fictional-1"
    unknown = "The part of a fund not covered by its holdings file could be anything; it is never treated as zero."
    evidence = [
        ev("ev-w-spy-start", "FICTIONAL_SCENARIO", "position_weight", 0.0, "INSTRUMENT", "SPY", "STARTING"),
        ev("ev-w-spy-target", "FICTIONAL_SCENARIO", "position_weight", 0.15, "INSTRUMENT", "SPY", "PROPOSED",
           assumptions=["Hypothetical purchase requested by the user; not executed."]),
        ev("ev-w-xiu", "FICTIONAL_SCENARIO", "position_weight", 0.20, "INSTRUMENT", "XIU.TO", "STARTING"),
        ev("ev-w-esgv", "FICTIONAL_SCENARIO", "position_weight", 0.15, "INSTRUMENT", "ESGV", "STARTING"),
        ev("ev-cash-start", "FICTIONAL_SCENARIO", "cash_weight", 0.25, "PORTFOLIO", pf, "STARTING"),
        ev("ev-cash-after", "CALCULATION", "cash_after_purchase", 0.10, "PORTFOLIO", pf, "PROPOSED",
           derived=["ev-cash-start", "ev-w-spy-start", "ev-w-spy-target"], formula="0.25 - (0.15 - 0.00) = 0.10",
           assumptions=["Funded from cash; fees and taxes excluded."]),
        ev("ev-xiu-enb-weight", "FACT", "fund_constituent_weight", 0.04, "ISSUER", "ENBRIDGE", via="XIU.TO", sources=S),
        ev("ev-xiu-cnq-weight", "FACT", "fund_constituent_weight", 0.03, "ISSUER", "CANADIAN_NATURAL_RESOURCES", via="XIU.TO", sources=S),
        ev("ev-spy-xom-weight", "FACT", "fund_constituent_weight", 0.02, "ISSUER", "EXXON_MOBIL", via="SPY", sources=S),
        ev("ev-xiu-enb-sector", "FACT", "sector_label", "Energy", "ISSUER", "ENBRIDGE", via="XIU.TO", sources=S, unit="text"),
        ev("ev-xiu-cnq-sector", "FACT", "sector_label", "Energy", "ISSUER", "CANADIAN_NATURAL_RESOURCES", via="XIU.TO", sources=S, unit="text"),
        ev("ev-spy-xom-sector", "FACT", "sector_label", "Energy", "ISSUER", "EXXON_MOBIL", via="SPY", sources=S, unit="text"),
        ev("ev-xiu-coverage", "CALCULATION", "fund_coverage_fraction", 0.98, "FUND", "XIU.TO", sources=S, formula="sum of the reported constituent weights = 0.98"),
        ev("ev-xiu-unattributed", "CALCULATION", "unattributed_fund_weight", 0.004, "FUND", "XIU.TO", "PROPOSED",
           derived=["ev-w-xiu", "ev-xiu-coverage"], formula="0.20 x (1 - 0.98) = 0.004", assumptions=[unknown]),
        ev("ev-esgv-unattributed", "CALCULATION", "unattributed_fund_weight", 0.15, "FUND", "ESGV", "PROPOSED",
           derived=["ev-w-esgv"], formula="0.15 x (1 - 0) = 0.15",
           assumptions=["No holdings file is held for ESGV: its coverage is 0.", unknown]),
        ev("ev-energy-lower-start", "CALCULATION", "exposure_lower", 0.014, "RULE", "mateo-excl-energy-1", "STARTING",
           derived=["ev-w-xiu", "ev-xiu-enb-weight", "ev-xiu-cnq-weight", "ev-xiu-enb-sector", "ev-xiu-cnq-sector"], formula="0.20 x (0.04 + 0.03) = 0.014"),
        ev("ev-energy-upper-start", "CALCULATION", "exposure_upper", 0.168, "RULE", "mateo-excl-energy-1", "STARTING",
           derived=["ev-energy-lower-start", "ev-xiu-unattributed", "ev-esgv-unattributed"], formula="0.014 + 0.004 + 0.15 = 0.168"),
        ev("ev-energy-lower", "CALCULATION", "exposure_lower", 0.017, "RULE", "mateo-excl-energy-1", "PROPOSED",
           derived=["ev-energy-lower-start", "ev-w-spy-target", "ev-spy-xom-weight", "ev-spy-xom-sector"], formula="0.014 + 0.15 x 0.02 = 0.017"),
        ev("ev-energy-upper", "CALCULATION", "exposure_upper", 0.171, "RULE", "mateo-excl-energy-1", "PROPOSED",
           derived=["ev-energy-lower", "ev-xiu-unattributed", "ev-esgv-unattributed"], formula="0.017 + 0.004 + 0.15 = 0.171"),
        ev("ev-energy-threshold", "FICTIONAL_SCENARIO", "rule_threshold", 0.0, "RULE", "mateo-excl-energy-1"),
        ev("ev-energy-gap", "CALCULATION", "gap_to_limit", 0.017, "RULE", "mateo-excl-energy-1", "PROPOSED",
           derived=["ev-energy-lower", "ev-energy-threshold"], formula="0.017 - 0.00 = 0.017"),
        ev("ev-controversy-threshold", "FICTIONAL_SCENARIO", "rule_threshold", 0.0, "RULE", "mateo-controversy-1"),
        ev("ev-controversy-lower", "CALCULATION", "exposure_lower", 0.0, "RULE", "mateo-controversy-1", "PROPOSED",
           derived=["ev-controversy-threshold"], formula="no held company has a matching registry record: 0",
           assumptions=["The registry holds no record for any held company. Absence from the registry means not assessed."]),
        ev("ev-w-msft", "FICTIONAL_SCENARIO", "position_weight", 0.05, "INSTRUMENT", "MSFT", "STARTING"),
        ev("ev-w-cnr", "FICTIONAL_SCENARIO", "position_weight", 0.05, "INSTRUMENT", "CNR.TO", "STARTING"),
        ev("ev-xiu-cnr-weight", "FACT", "fund_constituent_weight", 0.03, "ISSUER", "CANADIAN_NATIONAL_RAILWAY", via="XIU.TO", sources=S),
        ev("ev-spy-msft-weight", "FACT", "fund_constituent_weight", 0.06, "ISSUER", "MICROSOFT", via="SPY", sources=S),
        ev("ev-cnr-lower-start", "CALCULATION", "exposure_lower", 0.056, "ISSUER", "CANADIAN_NATIONAL_RAILWAY", "STARTING",
           derived=["ev-w-cnr", "ev-w-xiu", "ev-xiu-cnr-weight"], formula="0.05 + 0.20 x 0.03 = 0.056"),
        ev("ev-cnr-upper-start", "CALCULATION", "exposure_upper", 0.21, "ISSUER", "CANADIAN_NATIONAL_RAILWAY", "STARTING",
           derived=["ev-cnr-lower-start", "ev-xiu-unattributed", "ev-esgv-unattributed"], formula="0.056 + 0.004 + 0.15 = 0.210", assumptions=[unknown]),
        ev("ev-msft-lower", "CALCULATION", "exposure_lower", 0.059, "ISSUER", "MICROSOFT", "PROPOSED",
           derived=["ev-w-msft", "ev-w-spy-target", "ev-spy-msft-weight"], formula="0.05 + 0.15 x 0.06 = 0.059"),
        ev("ev-msft-upper", "CALCULATION", "exposure_upper", 0.213, "ISSUER", "MICROSOFT", "PROPOSED",
           derived=["ev-msft-lower", "ev-xiu-unattributed", "ev-esgv-unattributed"], formula="0.059 + 0.004 + 0.15 = 0.213", assumptions=[unknown]),
        ev("ev-controversy-upper", "CALCULATION", "exposure_upper", 0.65, "RULE", "mateo-controversy-1", "PROPOSED",
           derived=["ev-w-xiu", "ev-w-esgv", "ev-w-spy-target"], formula="0.20 + 0.15 + 0.15 + 0.05 + 0.05 + 0.05 = 0.65",
           assumptions=["Every company exposure without a registry record counts as unknown, never as a pass."]),
    ]
    extra = 0.154

    def row(issuer, name, direct, start_paths, proposed_paths):
        return {"issuer_id": issuer, "name": name, "starting": breakdown(direct, start_paths, extra), "proposed": breakdown(direct, proposed_paths, extra)}

    xiu = lambda known: [("XIU.TO", known)]  # noqa: E731
    # Selection (SEMANTICS.md section 10): the three breaching companies are required, then the largest remaining
    # exposures up to 10 in total; the list is sorted by the proposed lower bound, then by issuer_id.
    exposure = {
        "possible_extra": {"starting": extra, "proposed": extra},
        "issuers": [
            row("MICROSOFT", "Microsoft", 0.05, [], [("SPY", 0.009)]),
            row("CANADIAN_NATIONAL_RAILWAY", "Canadian National Railway", 0.05, xiu(0.006), xiu(0.006)),
            row("FORTIS", "Fortis", 0.05, [], []),
            row("SYN_CA_ISSUER_1", "Synthetic Canadian filler company 1", 0.0, xiu(0.04), xiu(0.04)),
            row("SYN_CA_ISSUER_2", "Synthetic Canadian filler company 2", 0.0, xiu(0.04), xiu(0.04)),
            row("SYN_CA_ISSUER_3", "Synthetic Canadian filler company 3", 0.0, xiu(0.04), xiu(0.04)),
            row("SYN_CA_ISSUER_4", "Synthetic Canadian filler company 4", 0.0, xiu(0.04), xiu(0.04)),
            row("ENBRIDGE", "Enbridge", 0.0, xiu(0.008), xiu(0.008)),
            row("CANADIAN_NATURAL_RESOURCES", "Canadian Natural Resources", 0.0, xiu(0.006), xiu(0.006)),
            row("EXXON_MOBIL", "Exxon Mobil", 0.0, [], [("SPY", 0.003)]),
        ],
        "selection_note": EXPOSURE_SELECTION_NOTE,
    }
    energy_reason = ("Holdings labelled Energy are between 1.7% and 17.1% of the portfolio after the purchase: 1.4% through XIU.TO (Enbridge, Canadian Natural "
                     "Resources), 0.3% through SPY (Exxon Mobil), and up to 15.4% that cannot be ruled out because ESGV has no holdings file and XIU.TO is "
                     "98% covered. The confirmed tolerance is 0.0%: the rule fails.")
    return finish(
        ec.mateo_expected(), persona_id="mateo", portfolio_id=pf, policy_id="pol-mateo-demo", version=1, preview=False, request=request,
        rule_types={"mateo-excl-energy-1": "exclusion", "mateo-controversy-1": "controversy_exclusion"},
        rule_text={
            "mateo-excl-energy-1": (["ev-energy-lower", "ev-energy-upper", "ev-energy-threshold", "ev-energy-gap", "ev-esgv-unattributed", "ev-xiu-unattributed"], energy_reason),
            "mateo-controversy-1": (["ev-controversy-lower", "ev-controversy-upper", "ev-controversy-threshold"],
                                    "No held company has a matching record in the controversy registry, and the registry covers none of the held companies. "
                                    "Absence from the registry means not assessed, so this rule is UNKNOWN, not passed."),
        },
        coverage_meta={"XIU.TO": ("2026-11-12", SYNTHETIC_SOURCE_ID), "SPY": ("2026-11-12", SYNTHETIC_SOURCE_ID), "ESGV": (None, None)},
        exposure=exposure,
        goal_context=[
            {"objective_id": "obj-mateo-1", "context_type": "LINKED_RULE_RESULTS",
             "text": "Two rules are linked to this objective as context: the Energy-label exclusion (FAIL) and the controversy exclusion (UNKNOWN). "
                     "The objective itself is qualitative and has no PASS or FAIL.",
             "evidence_ids": ["ev-energy-gap", "ev-controversy-upper"]},
            {"objective_id": "obj-mateo-1", "context_type": "CONCENTRATION",
             "text": "Largest single-company exposure: 5.6% to 21.0% (Canadian National Railway) before the purchase, 5.9% to 21.3% (Microsoft) after it.",
             "evidence_ids": ["ev-cnr-lower-start", "ev-cnr-upper-start", "ev-msft-lower", "ev-msft-upper"]},
        ],
        evidence=evidence,
        max_text=(["ev-energy-lower-start", "ev-energy-threshold"],
                  "No purchase of SPY can make every confirmed rule pass with cash funding: the Energy-label exclusion is already breached by the starting "
                  "portfolio (1.4% through XIU.TO), and buying does not reduce it. Bringing it to 0 would require selling, which this funding path does not support."),
        finding_text={"mateo-excl-energy-1": (
            ["ev-energy-lower-start", "ev-energy-upper-start", "ev-energy-threshold"],
            "Before any purchase, holdings labelled Energy are already between 1.4% and 16.8% of the portfolio (through XIU.TO), above the confirmed tolerance of 0.0%. "
            "The purchase itself adds 0.3% (Exxon Mobil through SPY).")},
    )


# --------------------------------------------------------------------------------------------- invalid request

INVALID_REQUEST = {"instrument_id": "RY.TO", "target_direct_weight": 0.02, "funding": "CASH", "original_words": "Cut my Royal Bank position to 2%."}


def invalid_request_result():
    """Robert asks for a final weight below the current one (0.02 < 0.05): the engine refuses, nothing is evaluated."""
    result = {
        "schema_version": "1.0.0", "persona_id": "robert", "portfolio_id": "pf-robert-fictional-1", "policy_id": "pol-robert-demo",
        "policy_version": 1, "preview": False, "calculation_version": CALC, "valuation_date": VALUATION_DATE, "purchase_request": INVALID_REQUEST,
        "execution": {"status": "INVALID_REQUEST", "code": "TARGET_BELOW_CURRENT_WEIGHT",
                      "message": "The requested final direct weight of RY.TO (2.0%) is below its current direct weight (5.0%). "
                                 "Only cash-funded purchases are simulated; selling is not supported."},
        "feasibility": None, "policy_consistency": {"status": "NOT_ASSESSED", "conflicts": []},
        "rule_results": [], "rules_not_evaluated": [], "starting_portfolio_findings": [], "data_coverage": [], "scenario": None,
        "goal_context": [], "max_compliant": None, "exposure": None, "evidence": [],
    }
    result["summary"] = derive_summary(result)
    result["disclosures"] = list(DISCLOSURES)
    errors = check_result_errors(result)
    assert not errors, errors
    return result


if __name__ == "__main__":
    for name in ("v1", "v2", "preview"):
        print(name, robert_result(name)["summary"])
    print("mateo", mateo_result()["summary"])
    print("invalid", invalid_request_result()["summary"])
