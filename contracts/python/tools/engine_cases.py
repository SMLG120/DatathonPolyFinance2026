"""Hand-entered engine cases. Every expected number below was typed from HAND_CALCS.md, not computed.

Run ``python3 contracts/python/tools/build_fixtures.py`` to (re)write the JSON files.
"""

from __future__ import annotations

from fixture_lib import (
    SYNTHETIC_NOTE, controversy, exclude_issuers, exclude_sector, loss_budget, max_issuer, min_issuer,
    objective, policy, portfolio, purchase,
)

C = dict(status="CONFIRMED", origin="FICTIONAL_SCENARIO", words="Synthetic test rule.")


def b(lower, upper):
    return {"lower": lower, "upper": upper}


def rr(rule_id, status, measured, limit, gap, start_status, start_measured, breaching=(), causes=(), out_of_scope=None):
    entry = {
        "rule_id": rule_id, "status": status, "measured": measured, "limit": limit, "gap": gap,
        "breaching_subjects": [{"subject_kind": "ISSUER", "subject_id": i, "lower": lo, "upper": up} for (i, lo, up) in breaching],
        "unknown_causes": list(causes),
        "starting": {"status": start_status, "measured": start_measured},
    }
    if out_of_scope is not None:
        entry["out_of_scope"] = [{"instrument_id": i, "weight": w} for (i, w) in out_of_scope]
    return entry


def finding(rule_id, measured, limit, gap, breaching, lower_change, upper_change):
    return {
        "rule_id": rule_id, "status": "FAIL", "measured": measured, "limit": limit, "gap": gap,
        "breaching_subjects": [{"subject_kind": "ISSUER", "subject_id": i, "lower": lo, "upper": up} for (i, lo, up) in breaching],
        "purchase_effect": {"lower_change": lower_change, "upper_change": upper_change},
    }


def feas(start, target, added, cash_before, cash_after, status="FEASIBLE"):
    return {"funding": "CASH", "starting_direct_weight": start, "target_direct_weight": target, "additional_purchase": added,
            "cash_before": cash_before, "cash_after": cash_after, "status": status}


def cov(fund_id, weight, coverage, labelled, uncovered, status):
    return {"fund_id": fund_id, "portfolio_weight": weight, "coverage_fraction": coverage,
            "sector_labelled_fraction": labelled, "uncovered_portfolio_weight": uncovered, "status": status}


def summ(headline, p, f, u, not_evaluated=0, breaches=0, feasibility="FEASIBLE"):
    return {"headline": headline, "counts": {"pass": p, "fail": f, "unknown": u}, "rules_evaluated": p + f + u,
            "rules_not_evaluated": not_evaluated, "starting_portfolio_breaches": breaches, "feasibility_status": feasibility}


def maxc(status, final=None, added=None, binding=None):
    constraint = None
    if binding == "CASH":
        constraint = {"type": "CASH", "rule_id": None}
    elif binding is not None:
        constraint = {"type": "RULE", "rule_id": binding}
    return {"status": status, "final_direct_weight": final, "additional_purchase": added,
            "binding_constraint": constraint, "verified_by_rerun": status == "SUPPORTED"}


OK = {"status": "OK", "code": None}
CONSISTENT = {"status": "CONSISTENT", "conflicts": []}
P_BASE = dict(cash=0.50, positions={"FUND_A": 0.40, "SYN_A": 0.10})


def case(fixture_id, title, tests, hand_calc, pf, rules, request, expected, universe="synthetic_universe.json",
         persona="synthetic_test", objectives=(), version=1, parent=None, note="Synthetic test policy."):
    return {
        "fixture": True,
        "fixture_id": fixture_id,
        "synthetic": True,
        "synthetic_note": SYNTHETIC_NOTE,
        "title": title,
        "tests": tests,
        "universe": universe,
        "hand_calc": hand_calc,
        "inputs": {
            "portfolio": portfolio(f"pf-{fixture_id.lower()}", persona, pf["cash"], pf["positions"]),
            "policy": policy(f"pol-{fixture_id.lower()}", persona, version, rules, objectives=objectives, parent=parent, note=note),
            "purchase_request": request,
        },
        "expected": expected,
    }


def generic_cases():
    cases = []
    cases.append(case(
        "E01", "Direct plus indirect exposure through one fully covered fund", ["direct and indirect exposure"], "E01",
        P_BASE, [max_issuer("e01-cap", 0.25, **C)], purchase("SYN_A", 0.15),
        {
            "execution": OK, "feasibility": feas(0.10, 0.15, 0.05, 0.50, 0.45), "policy_consistency": CONSISTENT,
            "rule_results": [rr("e01-cap", "PASS", b(0.23, 0.23), 0.25, -0.02, "PASS", b(0.18, 0.18), out_of_scope=[])],
            "rules_not_evaluated": [], "starting_portfolio_findings": [],
            "data_coverage": [cov("FUND_A", 0.40, 1.0, 1.0, 0.0, "COVERED")],
            "scenario": None,
            "max_compliant": maxc("SUPPORTED", 0.17, 0.07, "e01-cap"),
            "exposure": {
                "possible_extra": {"starting": 0.0, "proposed": 0.0},
                "issuers": [
                    {"issuer_id": "ISS_A", "starting": {"direct": 0.10, "indirect_by_fund": [{"fund_id": "FUND_A", "known": 0.08}], "lower": 0.18, "upper": 0.18},
                     "proposed": {"direct": 0.15, "indirect_by_fund": [{"fund_id": "FUND_A", "known": 0.08}], "lower": 0.23, "upper": 0.23}},
                    {"issuer_id": "ISS_D", "starting": {"direct": 0.0, "indirect_by_fund": [{"fund_id": "FUND_A", "known": 0.16}], "lower": 0.16, "upper": 0.16},
                     "proposed": {"direct": 0.0, "indirect_by_fund": [{"fund_id": "FUND_A", "known": 0.16}], "lower": 0.16, "upper": 0.16}},
                    {"issuer_id": "ISS_C", "starting": {"direct": 0.0, "indirect_by_fund": [{"fund_id": "FUND_A", "known": 0.10}], "lower": 0.10, "upper": 0.10},
                     "proposed": {"direct": 0.0, "indirect_by_fund": [{"fund_id": "FUND_A", "known": 0.10}], "lower": 0.10, "upper": 0.10}},
                    {"issuer_id": "ISS_B", "starting": {"direct": 0.0, "indirect_by_fund": [{"fund_id": "FUND_A", "known": 0.06}], "lower": 0.06, "upper": 0.06},
                     "proposed": {"direct": 0.0, "indirect_by_fund": [{"fund_id": "FUND_A", "known": 0.06}], "lower": 0.06, "upper": 0.06}},
                ],
            },
            "summary": summ("ALL_PASS", 1, 0, 0),
        }))
    cases.append(case(
        "E02", "Exact threshold equality passes", ["exact threshold equality"], "E02",
        P_BASE, [max_issuer("e02-cap", 0.25, **C)], purchase("SYN_A", 0.17),
        {
            "execution": OK, "feasibility": feas(0.10, 0.17, 0.07, 0.50, 0.43), "policy_consistency": CONSISTENT,
            "rule_results": [rr("e02-cap", "PASS", b(0.25, 0.25), 0.25, 0.0, "PASS", b(0.18, 0.18))],
            "starting_portfolio_findings": [],
            "max_compliant": maxc("SUPPORTED", 0.17, 0.07, "e02-cap"),
            "summary": summ("ALL_PASS", 1, 0, 0),
        }))
    cases.append(case(
        "E03", "Two fund paths to the same issuer", ["multiple fund paths"], "E03",
        dict(cash=0.30, positions={"FUND_A": 0.40, "FUND_D": 0.20, "SYN_A": 0.10}),
        [max_issuer("e03-cap", 0.29, **C)], purchase("SYN_A", 0.12),
        {
            "execution": OK, "feasibility": feas(0.10, 0.12, 0.02, 0.30, 0.28), "policy_consistency": CONSISTENT,
            "rule_results": [rr("e03-cap", "FAIL", b(0.30, 0.30), 0.29, 0.01, "PASS", b(0.28, 0.28), breaching=[("ISS_A", 0.30, 0.30)])],
            "starting_portfolio_findings": [],
            "data_coverage": [cov("FUND_A", 0.40, 1.0, 1.0, 0.0, "COVERED"), cov("FUND_D", 0.20, 1.0, 1.0, 0.0, "COVERED")],
            "max_compliant": maxc("SUPPORTED", 0.11, 0.01, "e03-cap"),
            "summary": summ("HAS_FAIL", 0, 1, 0),
        }))
    cases.append(case(
        "E04", "Share classes of one issuer are aggregated", ["issuer share classes"], "E04",
        dict(cash=0.40, positions={"FUND_A": 0.40, "SYN_B1": 0.10, "SYN_B2": 0.10}),
        [max_issuer("e04-cap-b", 0.30, scope="ISS_B", **C)], purchase("SYN_B2", 0.15),
        {
            "execution": OK, "feasibility": feas(0.10, 0.15, 0.05, 0.40, 0.35), "policy_consistency": CONSISTENT,
            "rule_results": [rr("e04-cap-b", "FAIL", b(0.31, 0.31), 0.30, 0.01, "PASS", b(0.26, 0.26), breaching=[("ISS_B", 0.31, 0.31)])],
            "starting_portfolio_findings": [],
            "max_compliant": maxc("SUPPORTED", 0.14, 0.04, "e04-cap-b"),
            "summary": summ("HAS_FAIL", 0, 1, 0),
        }))
    cases.append(case(
        "E05", "Partial holdings give an interval and an UNKNOWN verdict", ["partial holdings", "interval bounds"], "E05",
        dict(cash=0.50, positions={"FUND_B": 0.40, "SYN_A": 0.10}),
        [max_issuer("e05-cap", 0.30, **C)], purchase("SYN_A", 0.12),
        {
            "execution": OK, "feasibility": feas(0.10, 0.12, 0.02, 0.50, 0.48), "policy_consistency": CONSISTENT,
            "rule_results": [rr("e05-cap", "UNKNOWN", b(0.24, 0.40), 0.30, None, "UNKNOWN", b(0.22, 0.38), causes=["PARTIAL_HOLDINGS"])],
            "starting_portfolio_findings": [],
            "data_coverage": [cov("FUND_B", 0.40, 0.60, 0.40, 0.16, "PARTIAL")],
            "max_compliant": maxc("WITHHELD"),
            "summary": summ("NO_FAIL_BUT_UNKNOWN", 0, 0, 1),
        }))
    cases.append(case(
        "E06", "Missing holdings: a proven failure next to an unknown check", ["missing holdings", "proven failure plus unknown checks"], "E06",
        dict(cash=0.30, positions={"FUND_C": 0.30, "FUND_A": 0.20, "SYN_A": 0.20}),
        [max_issuer("e06-cap", 0.25, **C), exclude_issuers("e06-excl-e", 0.05, ["ISS_E"], **C)], purchase("SYN_A", 0.30),
        {
            "execution": OK, "feasibility": feas(0.20, 0.30, 0.10, 0.30, 0.20), "policy_consistency": CONSISTENT,
            "rule_results": [
                rr("e06-cap", "FAIL", b(0.34, 0.64), 0.25, 0.09, "UNKNOWN", b(0.24, 0.54), breaching=[("ISS_A", 0.34, 0.64)], causes=["MISSING_HOLDINGS"]),
                rr("e06-excl-e", "UNKNOWN", b(0.0, 0.30), 0.05, None, "UNKNOWN", b(0.0, 0.30), causes=["MISSING_HOLDINGS"]),
            ],
            "starting_portfolio_findings": [],
            "data_coverage": [cov("FUND_C", 0.30, 0.0, 0.0, 0.30, "MISSING"), cov("FUND_A", 0.20, 1.0, 1.0, 0.0, "COVERED")],
            "max_compliant": maxc("WITHHELD"),
            "summary": summ("HAS_FAIL", 0, 1, 1),
        }))
    cases.append(case(
        "E07", "Insufficient cash is a feasibility result, not a rule failure", ["insufficient cash"], "E07",
        dict(cash=0.05, positions={"FUND_A": 0.85, "SYN_A": 0.10}),
        [max_issuer("e07-cap", 0.50, **C)], purchase("SYN_A", 0.20),
        {
            "execution": OK, "feasibility": feas(0.10, 0.20, 0.10, 0.05, -0.05, "INSUFFICIENT_CASH"), "policy_consistency": CONSISTENT,
            "rule_results": [rr("e07-cap", "PASS", b(0.37, 0.37), 0.50, -0.13, "PASS", b(0.34, 0.34))],
            "starting_portfolio_findings": [],
            "max_compliant": maxc("SUPPORTED", 0.15, 0.05, "CASH"),
            "summary": summ("ALL_PASS", 1, 0, 0, feasibility="INSUFFICIENT_CASH"),
        }))
    cases.append(case(
        "E08", "Maximum compliant weight: the tighter of two rules binds", ["maximum compliant amount"], "E08",
        P_BASE, [max_issuer("e08-cap-any", 0.25, **C), max_issuer("e08-cap-a", 0.22, scope="ISS_A", **C)], purchase("SYN_A", 0.30),
        {
            "execution": OK, "feasibility": feas(0.10, 0.30, 0.20, 0.50, 0.30), "policy_consistency": CONSISTENT,
            "rule_results": [
                rr("e08-cap-any", "FAIL", b(0.38, 0.38), 0.25, 0.13, "PASS", b(0.18, 0.18), breaching=[("ISS_A", 0.38, 0.38)]),
                rr("e08-cap-a", "FAIL", b(0.38, 0.38), 0.22, 0.16, "PASS", b(0.18, 0.18), breaching=[("ISS_A", 0.38, 0.38)]),
            ],
            "starting_portfolio_findings": [],
            "max_compliant": maxc("SUPPORTED", 0.14, 0.04, "e08-cap-a"),
            "summary": summ("HAS_FAIL", 0, 2, 0),
        }))
    cases.append(case(
        "E09", "No feasible purchase: the starting portfolio already breaches", ["no feasible purchase", "starting portfolio finding"], "E09",
        dict(cash=0.30, positions={"FUND_A": 0.50, "SYN_A": 0.20}),
        [max_issuer("e09-cap", 0.25, **C)], purchase("SYN_A", 0.25),
        {
            "execution": OK, "feasibility": feas(0.20, 0.25, 0.05, 0.30, 0.25), "policy_consistency": CONSISTENT,
            "rule_results": [rr("e09-cap", "FAIL", b(0.35, 0.35), 0.25, 0.10, "FAIL", b(0.30, 0.30), breaching=[("ISS_A", 0.35, 0.35)])],
            "starting_portfolio_findings": [finding("e09-cap", b(0.30, 0.30), 0.25, 0.05, [("ISS_A", 0.30, 0.30)], 0.05, 0.05)],
            "max_compliant": maxc("NO_FEASIBLE_PURCHASE", binding="e09-cap"),
            "summary": summ("HAS_FAIL", 0, 1, 0, breaches=1),
        }))
    cases.append(case(
        "E10", "Proven conflict: minimum above maximum for the same issuer", ["explicit incompatible supported bounds"], "E10",
        P_BASE, [min_issuer("e10-min-a", 0.20, "ISS_A", **C), max_issuer("e10-max-a", 0.10, scope="ISS_A", **C)], purchase("SYN_A", 0.15),
        {
            "execution": OK, "feasibility": feas(0.10, 0.15, 0.05, 0.50, 0.45),
            "policy_consistency": {"status": "PROVEN_CONFLICT", "conflicts": [
                {"conflict_type": "MIN_EXCEEDS_MAX_SAME_ISSUER", "rule_ids": ["e10-min-a", "e10-max-a"], "issuer_id": "ISS_A", "min_fraction": 0.20, "max_fraction": 0.10}]},
            "rule_results": [
                rr("e10-min-a", "PASS", b(0.23, 0.23), 0.20, -0.03, "FAIL", b(0.18, 0.18)),
                rr("e10-max-a", "FAIL", b(0.23, 0.23), 0.10, 0.13, "FAIL", b(0.18, 0.18), breaching=[("ISS_A", 0.23, 0.23)]),
            ],
            "starting_portfolio_findings": [
                finding("e10-min-a", b(0.18, 0.18), 0.20, 0.02, [], 0.05, 0.05),
                finding("e10-max-a", b(0.18, 0.18), 0.10, 0.08, [("ISS_A", 0.18, 0.18)], 0.05, 0.05),
            ],
            "max_compliant": maxc("WITHHELD"),
            "summary": summ("POLICY_CONFLICT", 1, 1, 0, breaches=2),
        }))
    cases.append(case(
        "E11", "Minimum equal to maximum is not a conflict; a no-op purchase", ["exact threshold equality", "no feasible purchase"], "E11",
        P_BASE, [min_issuer("e11-min-a", 0.18, "ISS_A", **C), max_issuer("e11-max-a", 0.18, scope="ISS_A", **C)], purchase("SYN_A", 0.10),
        {
            "execution": OK, "feasibility": feas(0.10, 0.10, 0.0, 0.50, 0.50), "policy_consistency": CONSISTENT,
            "rule_results": [
                rr("e11-min-a", "PASS", b(0.18, 0.18), 0.18, 0.0, "PASS", b(0.18, 0.18)),
                rr("e11-max-a", "PASS", b(0.18, 0.18), 0.18, 0.0, "PASS", b(0.18, 0.18)),
            ],
            "starting_portfolio_findings": [],
            "max_compliant": maxc("NO_FEASIBLE_PURCHASE", binding="e11-max-a"),
            "summary": summ("ALL_PASS", 2, 0, 0),
        }))
    cases.append(case(
        "E12", "2022 replay with FX conversion, backward matching and the linear boundary", ["historical metric definitions", "FX conversion"], "E12",
        dict(cash=0.40, positions={"SYN_A": 0.40, "SYN_C": 0.20}),
        [loss_budget("e12-budget", 0.05, **C)], purchase("SYN_C", 0.30),
        {
            "execution": OK, "feasibility": feas(0.20, 0.30, 0.10, 0.40, 0.30), "policy_consistency": CONSISTENT,
            "rule_results": [rr("e12-budget", "FAIL", b(0.056, 0.056), 0.05, 0.006, "PASS", b(0.044, 0.044), out_of_scope=[])],
            "starting_portfolio_findings": [], "data_coverage": [],
            "scenario": {
                "scenario_id": "replay_2022", "base_date": "2021-12-31", "end_date": "2022-12-30", "status": "COMPUTED",
                "starting": {"scenario_terminal_return": -0.044, "scenario_max_drawdown": -0.12944, "max_drawdown_date": "2022-09-30"},
                "proposed": {"scenario_terminal_return": -0.056, "scenario_max_drawdown": -0.16416, "max_drawdown_date": "2022-09-30"},
                "target_instrument_return": -0.12,
                "instrument_returns": [
                    {"instrument_id": "SYN_A", "currency": "CAD", "base_price_date": "2021-12-30", "end_price_date": "2022-12-30",
                     "base_price_age_days": 1, "end_price_age_days": 0, "base_fx_date": None, "end_fx_date": None,
                     "base_fx_age_days": None, "end_fx_age_days": None, "return_cad": -0.05},
                    {"instrument_id": "SYN_C", "currency": "USD", "base_price_date": "2021-12-31", "end_price_date": "2022-12-30",
                     "base_price_age_days": 0, "end_price_age_days": 0, "base_fx_date": "2021-12-30", "end_fx_date": "2022-12-30",
                     "base_fx_age_days": 1, "end_fx_age_days": 0, "return_cad": -0.12},
                ],
                "missing_instruments": [],
            },
            "max_compliant": maxc("SUPPORTED", 0.25, 0.05, "e12-budget"),
            "summary": summ("HAS_FAIL", 0, 1, 0),
        }))
    invalid = {
        "feasibility": None, "policy_consistency": {"status": "NOT_ASSESSED", "conflicts": []}, "rule_results": [],
        "rules_not_evaluated": [], "starting_portfolio_findings": [], "data_coverage": [], "scenario": None, "goal_context": [],
        "max_compliant": None, "exposure": None, "evidence": [],
        "summary": summ("INVALID_REQUEST", 0, 0, 0, feasibility=None),
    }
    cases.append(case(
        "E13", "Target below the current direct weight is an invalid request", ["invalid request", "execution status"], "E13",
        P_BASE, [max_issuer("e13-cap", 0.25, **C)], purchase("SYN_A", 0.05),
        {"execution": {"status": "INVALID_REQUEST", "code": "TARGET_BELOW_CURRENT_WEIGHT"}, **invalid}))
    cases.append(case(
        "E14", "Unknown instrument is an invalid request", ["invalid request", "execution status"], "E14",
        P_BASE, [max_issuer("e14-cap", 0.25, **C)], purchase("NOPE", 0.10),
        {"execution": {"status": "INVALID_REQUEST", "code": "UNSUPPORTED_INSTRUMENT"}, **invalid}))
    cases.append(case(
        "E15", "Sector exclusion already breached before the purchase, with unknown parts",
        ["starting portfolio finding", "missing and partial holdings", "unclassified sector"], "E15",
        dict(cash=0.20, positions={"BOND_X": 0.10, "FUND_A": 0.30, "FUND_C": 0.20, "SYN_D": 0.20}),
        [exclude_sector("e15-excl-energy", 0.0, "Energy", **C)], purchase("FUND_B", 0.10),
        {
            "execution": OK, "feasibility": feas(0.0, 0.10, 0.10, 0.20, 0.10), "policy_consistency": CONSISTENT,
            "rule_results": [rr("e15-excl-energy", "FAIL", b(0.085, 0.345), 0.0, 0.085, "FAIL", b(0.075, 0.275),
                                breaching=[("ISS_C", 0.085, 0.325)], causes=["MISSING_HOLDINGS", "PARTIAL_HOLDINGS", "UNCLASSIFIED_SECTOR"],
                                out_of_scope=[("BOND_X", 0.10)])],
            "starting_portfolio_findings": [finding("e15-excl-energy", b(0.075, 0.275), 0.0, 0.075, [("ISS_C", 0.075, 0.275)], 0.01, 0.07)],
            "data_coverage": [cov("FUND_A", 0.30, 1.0, 1.0, 0.0, "COVERED"), cov("FUND_C", 0.20, 0.0, 0.0, 0.20, "MISSING"),
                              cov("FUND_B", 0.10, 0.60, 0.40, 0.04, "PARTIAL")],
            "max_compliant": maxc("NO_FEASIBLE_PURCHASE", binding="e15-excl-energy"),
            "summary": summ("HAS_FAIL", 0, 1, 0, breaches=1),
        }))
    natures = ["REGULATORY_FINDING", "COURT_RULING"]
    cases.append(case(
        "E16", "Controversy exclusion: a matching registry record proves a failure", ["controversy exclusion", "starting portfolio finding"], "E16",
        P_BASE, [controversy("e16-controversy", 0.0, natures, **C)], purchase("SYN_A", 0.15),
        {
            "execution": OK, "feasibility": feas(0.10, 0.15, 0.05, 0.50, 0.45), "policy_consistency": CONSISTENT,
            "rule_results": [rr("e16-controversy", "FAIL", b(0.10, 0.55), 0.0, 0.10, "FAIL", b(0.10, 0.50),
                                breaching=[("ISS_C", 0.10, 0.10)], causes=["REGISTRY_ABSENCE"])],
            "starting_portfolio_findings": [finding("e16-controversy", b(0.10, 0.50), 0.0, 0.10, [("ISS_C", 0.10, 0.10)], 0.0, 0.05)],
            "max_compliant": maxc("NO_FEASIBLE_PURCHASE", binding="e16-controversy"),
            "summary": summ("HAS_FAIL", 0, 1, 0, breaches=1),
        }))
    cases.append(case(
        "E17", "Controversy exclusion: no matching record is UNKNOWN, never PASS", ["registry absence is unknown"], "E17",
        P_BASE, [controversy("e17-controversy", 0.0, ["COURT_RULING"], **C)], purchase("SYN_A", 0.15),
        {
            "execution": OK, "feasibility": feas(0.10, 0.15, 0.05, 0.50, 0.45), "policy_consistency": CONSISTENT,
            "rule_results": [rr("e17-controversy", "UNKNOWN", b(0.0, 0.55), 0.0, None, "UNKNOWN", b(0.0, 0.50), causes=["REGISTRY_ABSENCE"])],
            "starting_portfolio_findings": [],
            "max_compliant": maxc("WITHHELD"),
            "summary": summ("NO_FAIL_BUT_UNKNOWN", 0, 0, 1),
        }))
    cases.append(case(
        "E18", "Unconfirmed rules are never evaluated", ["unconfirmed thresholds"], "E18",
        P_BASE,
        [max_issuer("e18-cap-proposed", None, status="PROPOSED", origin="SYSTEM_PROPOSED", words="I do not want too much in one company."),
         loss_budget("e18-budget-proposed", 0.10, status="PROPOSED", origin="FICTIONAL_SCENARIO", words="Synthetic scenario budget, not confirmed.")],
        purchase("SYN_A", 0.15),
        {
            "execution": OK, "feasibility": feas(0.10, 0.15, 0.05, 0.50, 0.45), "policy_consistency": CONSISTENT,
            "rule_results": [],
            "rules_not_evaluated": [{"rule_id": "e18-cap-proposed", "status": "PROPOSED"}, {"rule_id": "e18-budget-proposed", "status": "PROPOSED"}],
            "starting_portfolio_findings": [], "scenario": None,
            "max_compliant": maxc("WITHHELD"),
            "summary": summ("NO_RULES_EVALUATED", 0, 0, 0, not_evaluated=2),
        }))
    row_a = {"instrument_id": "SYN_A", "currency": "CAD", "base_price_date": "2021-12-30", "end_price_date": "2022-12-30",
             "base_price_age_days": 1, "end_price_age_days": 0, "base_fx_date": None, "end_fx_date": None,
             "base_fx_age_days": None, "end_fx_age_days": None, "return_cad": -0.05}
    row_c = {"instrument_id": "SYN_C", "currency": "USD", "base_price_date": "2021-12-31", "end_price_date": "2022-12-30",
             "base_price_age_days": 0, "end_price_age_days": 0, "base_fx_date": "2021-12-30", "end_fx_date": "2022-12-30",
             "base_fx_age_days": 1, "end_fx_age_days": 0, "return_cad": -0.12}

    def no_history(rule_id, missing, rows, target_return):
        return {
            "policy_consistency": CONSISTENT,
            "rule_results": [rr(rule_id, "UNKNOWN", None, 0.05, None, "UNKNOWN", None, causes=["INSUFFICIENT_HISTORY"], out_of_scope=[])],
            "starting_portfolio_findings": [], "data_coverage": [],
            "scenario": {
                "scenario_id": "replay_2022", "base_date": "2021-12-31", "end_date": "2022-12-30", "status": "INSUFFICIENT_HISTORY",
                "starting": None, "proposed": None, "target_instrument_return": target_return,
                "instrument_returns": rows, "missing_instruments": missing,
            },
            "max_compliant": maxc("WITHHELD"),
            "summary": summ("NO_FAIL_BUT_UNKNOWN", 0, 0, 1),
        }

    cases.append(case(
        "E19", "The purchased instrument has no price history: the loss budget is UNKNOWN", ["historical metric definitions", "insufficient history"], "E19",
        dict(cash=0.40, positions={"SYN_A": 0.40, "SYN_C": 0.20}),
        [loss_budget("e19-budget", 0.05, **C)], purchase("SYN_D", 0.10),
        {"execution": OK, "feasibility": feas(0.0, 0.10, 0.10, 0.40, 0.30), **no_history("e19-budget", ["SYN_D"], [row_a, row_c], None)}))
    cases.append(case(
        "E20", "A stale end price is not carried forward: insufficient history", ["historical metric definitions", "insufficient history"], "E20",
        dict(cash=0.40, positions={"SYN_A": 0.40, "SYN_E": 0.20}),
        [loss_budget("e20-budget", 0.05, **C)], purchase("SYN_A", 0.45),
        {"execution": OK, "feasibility": feas(0.40, 0.45, 0.05, 0.40, 0.35), **no_history("e20-budget", ["SYN_E"], [row_a], -0.05)}))
    cases.append(case(
        "E21", "No cash at all: no purchase can be funded", ["insufficient cash", "no feasible purchase"], "E21",
        dict(cash=0.0, positions={"FUND_A": 0.90, "SYN_A": 0.10}),
        [max_issuer("e21-cap", 0.50, **C)], purchase("SYN_A", 0.15),
        {
            "execution": OK, "feasibility": feas(0.10, 0.15, 0.05, 0.0, -0.05, "INSUFFICIENT_CASH"), "policy_consistency": CONSISTENT,
            "rule_results": [rr("e21-cap", "PASS", b(0.36, 0.36), 0.50, -0.14, "PASS", b(0.36, 0.36))],
            "starting_portfolio_findings": [],
            "max_compliant": maxc("NO_FEASIBLE_PURCHASE", binding="CASH"),
            "summary": summ("ALL_PASS", 1, 0, 0, feasibility="INSUFFICIENT_CASH"),
        }))
    cases.append(case(
        "E22", "A minimum rule does not cap the purchase: cash is the only limit", ["maximum compliant amount", "starting portfolio finding"], "E22",
        P_BASE, [min_issuer("e22-min-a", 0.20, "ISS_A", **C)], purchase("SYN_A", 0.11),
        {
            "execution": OK, "feasibility": feas(0.10, 0.11, 0.01, 0.50, 0.49), "policy_consistency": CONSISTENT,
            "rule_results": [rr("e22-min-a", "FAIL", b(0.19, 0.19), 0.20, 0.01, "FAIL", b(0.18, 0.18))],
            "starting_portfolio_findings": [finding("e22-min-a", b(0.18, 0.18), 0.20, 0.02, [], 0.01, 0.01)],
            "max_compliant": maxc("SUPPORTED", 0.60, 0.50, "CASH"),
            "summary": summ("HAS_FAIL", 0, 1, 0, breaches=1),
        }))
    return cases


ROBERT_OBJECTIVE = objective(
    "obj-robert-1", "Preserve my capital while keeping some growth potential over the next 3 to 5 years.", case_reference="Case p.7")
ROBERT_PORTFOLIO = dict(cash=0.30, positions={"XBB.TO": 0.30, "SPY": 0.20, "XIU.TO": 0.10, "RY.TO": 0.05, "JNJ": 0.05})
ROBERT_REQUEST_WORDS = "Everyone is talking about Nvidia. I want it to be 25% of my portfolio."
ROBERT_CAP_WORDS = "Fictional scenario: no more than 10% of the portfolio in any single company, funds included."
ROBERT_BUDGET_WORDS = "Fictional scenario: replayed through 2022, the portfolio should not end the year more than 10% lower."


def robert_rules_v1(confirmed_at="2026-11-14T15:00:00Z"):
    kw = dict(status="CONFIRMED", origin="FICTIONAL_SCENARIO", objective_id="obj-robert-1", confirmed_at=confirmed_at)
    return [
        max_issuer("robert-issuer-cap-1", 0.10, words=ROBERT_CAP_WORDS, **kw),
        loss_budget("robert-loss-budget-1", 0.10, words=ROBERT_BUDGET_WORDS, **kw),
    ]


def robert_rules_v2():
    old_cap, budget = robert_rules_v1()
    old_cap = {**old_cap, "status": "SUPERSEDED", "superseded_by_rule_id": "robert-issuer-cap-2"}
    new_cap = max_issuer(
        "robert-issuer-cap-2", 0.30, status="CONFIRMED", origin="USER_STATED", threshold_source="USER_ENTERED",
        words="Raise my single-company limit to 30%.", objective_id="obj-robert-1",
        confirmed_at="2026-11-14T15:06:00Z", supersedes="robert-issuer-cap-1")
    return [old_cap, new_cap, budget]


def robert_policy_v1():
    return policy("pol-robert-demo", "robert", 1, robert_rules_v1(), objectives=[ROBERT_OBJECTIVE],
                  note="Fictional-scenario rules confirmed by the user.")


def robert_policy_v2():
    return policy("pol-robert-demo", "robert", 2, robert_rules_v2(), objectives=[ROBERT_OBJECTIVE], parent=1,
                  created_at="2026-11-14T15:06:00Z",
                  note="Issuer cap raised from 0.10 to 0.30 by the user (CHANGE_RULE challenge). Objective and loss budget unchanged.")


def robert_scenario(include_returns=True):
    scenario = {
        "scenario_id": "replay_2022", "base_date": "2021-12-31", "end_date": "2022-12-30", "status": "COMPUTED",
        "starting": {"scenario_terminal_return": -0.065, "scenario_max_drawdown": -0.0985, "max_drawdown_date": "2022-06-30"},
        "proposed": {"scenario_terminal_return": -0.1525, "scenario_max_drawdown": -0.2235, "max_drawdown_date": "2022-06-30"},
        "target_instrument_return": -0.35,
        "missing_instruments": [],
    }
    if include_returns:
        def row(instrument_id, currency, value):
            usd = currency == "USD"
            return {"instrument_id": instrument_id, "currency": currency, "base_price_date": "2021-12-31", "end_price_date": "2022-12-30",
                    "base_price_age_days": 0, "end_price_age_days": 0,
                    "base_fx_date": "2021-12-31" if usd else None, "end_fx_date": "2022-12-30" if usd else None,
                    "base_fx_age_days": 0 if usd else None, "end_fx_age_days": 0 if usd else None, "return_cad": value}
        scenario["instrument_returns"] = [
            row("XBB.TO", "CAD", -0.10), row("SPY", "USD", -0.155), row("XIU.TO", "CAD", -0.05),
            row("RY.TO", "CAD", -0.02), row("JNJ", "USD", 0.04), row("NVDA", "USD", -0.35),
        ]
    return scenario


ROBERT_COVERAGE = [cov("SPY", 0.20, 1.0, 0.0, 0.0, "COVERED"), cov("XIU.TO", 0.10, 0.98, 0.0, 0.002, "PARTIAL")]


def robert_expected_v1():
    return {
        "execution": OK, "feasibility": feas(0.0, 0.25, 0.25, 0.30, 0.05), "policy_consistency": CONSISTENT,
        "rule_results": [
            rr("robert-issuer-cap-1", "FAIL", b(0.262, 0.264), 0.10, 0.162, "PASS", b(0.058, 0.060),
               breaching=[("NVIDIA", 0.262, 0.264)], causes=["PARTIAL_HOLDINGS"], out_of_scope=[("XBB.TO", 0.30)]),
            rr("robert-loss-budget-1", "FAIL", b(0.1525, 0.1525), 0.10, 0.0525, "PASS", b(0.065, 0.065), out_of_scope=[]),
        ],
        "rules_not_evaluated": [], "starting_portfolio_findings": [],
        "data_coverage": ROBERT_COVERAGE,
        "scenario": robert_scenario(),
        "max_compliant": maxc("SUPPORTED", 0.086, 0.086, "robert-issuer-cap-1"),
        "summary": summ("HAS_FAIL", 0, 2, 0),
    }


def robert_expected_v2():
    return {
        "execution": OK, "feasibility": feas(0.0, 0.25, 0.25, 0.30, 0.05), "policy_consistency": CONSISTENT,
        "rule_results": [
            rr("robert-issuer-cap-2", "PASS", b(0.262, 0.264), 0.30, -0.036, "PASS", b(0.058, 0.060),
               causes=["PARTIAL_HOLDINGS"], out_of_scope=[("XBB.TO", 0.30)]),
            rr("robert-loss-budget-1", "FAIL", b(0.1525, 0.1525), 0.10, 0.0525, "PASS", b(0.065, 0.065), out_of_scope=[]),
        ],
        "rules_not_evaluated": [{"rule_id": "robert-issuer-cap-1", "status": "SUPERSEDED"}],
        "starting_portfolio_findings": [],
        "data_coverage": ROBERT_COVERAGE,
        "scenario": robert_scenario(),
        "max_compliant": maxc("SUPPORTED", 0.10, 0.10, "robert-loss-budget-1"),
        "summary": summ("HAS_FAIL", 1, 1, 0, not_evaluated=1),
    }


def robert_cases():
    request = purchase("NVDA", 0.25, ROBERT_REQUEST_WORDS)
    common = dict(universe="robert_synthetic_universe.json", persona="robert", objectives=[ROBERT_OBJECTIVE])
    r1 = case("R1", "Robert-shaped: NVDA to 25% under the 10% issuer cap and the 10% 2022 loss budget",
              ["direct and indirect exposure", "partial holdings", "maximum compliant amount", "historical scenario"], "R1",
              ROBERT_PORTFOLIO, robert_rules_v1(), request, robert_expected_v1(),
              note="Fictional-scenario rules confirmed by the user.", **common)
    r2 = case("R2", "Robert-shaped: cap raised to 30%; the loss budget still fails with a gap",
              ["policy revision", "reproducible old reports", "scenario budget gap"], "R2",
              ROBERT_PORTFOLIO, robert_rules_v2(), request, robert_expected_v2(), version=2, parent=1,
              note="Issuer cap raised from 0.10 to 0.30 by the user (CHANGE_RULE challenge). Objective and loss budget unchanged.", **common)
    r1["inputs"]["policy"] = robert_policy_v1()
    r2["inputs"]["policy"] = robert_policy_v2()
    return [r1, r2]


MATEO_OBJECTIVE = objective(
    "obj-mateo-1", "Balanced growth over 8 to 12 years; ESG matters to me; I want to avoid oil and companies involved in significant controversies.",
    case_reference="Case p.6")
MATEO_PORTFOLIO = dict(cash=0.25, positions={"XBB.TO": 0.25, "XIU.TO": 0.20, "ESGV": 0.15, "MSFT": 0.05, "CNR.TO": 0.05, "FTS.TO": 0.05})
MATEO_NATURES = ["REGULATORY_FINDING", "COURT_RULING", "SETTLEMENT"]


def mateo_rules():
    kw = dict(status="CONFIRMED", origin="FICTIONAL_SCENARIO", objective_id="obj-mateo-1")
    return [
        exclude_sector("mateo-excl-energy-1", 0.0, "Energy",
                       words="Fictional scenario: by 'oil' I mean no holdings labelled Energy in what my funds report.", **kw),
        controversy("mateo-controversy-1", 0.0, MATEO_NATURES,
                    words="Fictional scenario: no companies with a regulatory finding, court ruling or settlement in the registry.", **kw),
    ]


def mateo_policy():
    return policy("pol-mateo-demo", "mateo", 1, mateo_rules(), objectives=[MATEO_OBJECTIVE],
                  note="Fictional-scenario rules confirmed by the user after the 'oil' clarification.")


def mateo_expected():
    """HAND_CALCS.md M1. Both rules are proven FAIL before and after the purchase; what the purchase adds differs per rule."""
    out = [("XBB.TO", 0.25)]
    held_flagged = [("ENBRIDGE", 0.008, 0.162), ("CANADIAN_NATURAL_RESOURCES", 0.006, 0.160)]
    return {
        "execution": OK, "feasibility": feas(0.0, 0.15, 0.15, 0.25, 0.10), "policy_consistency": CONSISTENT,
        "rule_results": [
            rr("mateo-excl-energy-1", "FAIL", b(0.014, 0.318), 0.0, 0.014, "FAIL", b(0.014, 0.168),
               breaching=held_flagged, causes=["MISSING_HOLDINGS", "PARTIAL_HOLDINGS", "UNCLASSIFIED_SECTOR"], out_of_scope=out),
            rr("mateo-controversy-1", "FAIL", b(0.017, 0.65), 0.0, 0.017, "FAIL", b(0.014, 0.50),
               breaching=held_flagged + [("EXXON_MOBIL", 0.003, 0.157)],
               causes=["MISSING_HOLDINGS", "PARTIAL_HOLDINGS", "REGISTRY_ABSENCE"], out_of_scope=out),
        ],
        "rules_not_evaluated": [],
        "starting_portfolio_findings": [
            finding("mateo-excl-energy-1", b(0.014, 0.168), 0.0, 0.014, held_flagged, 0.0, 0.15),
            finding("mateo-controversy-1", b(0.014, 0.50), 0.0, 0.014, held_flagged, 0.003, 0.15),
        ],
        "data_coverage": mateo_coverage(),
        "scenario": None,
        "max_compliant": maxc("NO_FEASIBLE_PURCHASE", binding="mateo-excl-energy-1"),
        "summary": summ("HAS_FAIL", 0, 2, 0, breaches=2),
    }


def mateo_coverage():
    """XIU.TO lists 98% of its weight (all labelled), ESGV has no file, SPY lists 100% with no sector label."""
    return [cov("XIU.TO", 0.20, 0.98, 0.98, 0.004, "PARTIAL"), cov("ESGV", 0.15, 0.0, 0.0, 0.15, "MISSING"),
            cov("SPY", 0.15, 1.0, 0.0, 0.0, "COVERED")]


MATEO_CAP_RULE_ID = "mateo-issuer-cap-draft"
MATEO_CAP_WORDS = "No single company above 20% of my portfolio, funds included."


def mateo_cap_expected():
    """HAND_CALCS.md M2. A 0.20 single-company limit can be neither proven nor refuted while ESGV has no holdings file."""
    return {
        "execution": OK, "feasibility": feas(0.0, 0.15, 0.15, 0.25, 0.10), "policy_consistency": CONSISTENT,
        "rule_results": [
            rr(MATEO_CAP_RULE_ID, "UNKNOWN", b(0.059, 0.213), 0.20, None, "UNKNOWN", b(0.056, 0.21),
               causes=["MISSING_HOLDINGS", "PARTIAL_HOLDINGS"], out_of_scope=[("XBB.TO", 0.25)]),
        ],
        "rules_not_evaluated": [],
        "starting_portfolio_findings": [],
        "data_coverage": mateo_coverage(),
        "scenario": None,
        "max_compliant": maxc("WITHHELD"),
        "summary": summ("NO_FAIL_BUT_UNKNOWN", 0, 0, 1),
    }


def mateo_cases():
    spy = purchase("SPY", 0.15, "Buy SPY so that it is 15% of my portfolio.")
    m1 = case("M1", "Mateo-shaped: SPY to 15% with an Energy-label exclusion and a controversy exclusion",
              ["starting portfolio finding", "missing holdings", "unlabelled constituents are unknown, not zero",
               "controversy record match", "purchase effect kept apart from an existing breach"], "M1",
              MATEO_PORTFOLIO, mateo_rules(), spy, mateo_expected(),
              universe="mateo_synthetic_universe.json", persona="mateo", objectives=[MATEO_OBJECTIVE])
    m1["inputs"]["policy"] = mateo_policy()
    cap = [max_issuer(MATEO_CAP_RULE_ID, 0.20, status="CONFIRMED", origin="USER_STATED", words=MATEO_CAP_WORDS)]
    m2 = case("M2", "Mateo-shaped: a 20% single-company limit is UNKNOWN because ESGV has no holdings file",
              ["missing holdings", "unknown is neither pass nor fail", "maximum withheld without a proof"], "M2",
              MATEO_PORTFOLIO, cap, spy, mateo_cap_expected(),
              universe="mateo_synthetic_universe.json", persona="mateo", objectives=[MATEO_OBJECTIVE])
    for fixture in (m1, m2):
        fixture["synthetic_note"] += (
            " In this universe the three controversy records are fixture records that copy only the issuer, the event date "
            "and the nature of the records in the project's registry; they are not sources.")
    return [m1, m2]


def all_cases():
    return generic_cases() + robert_cases() + mateo_cases()
