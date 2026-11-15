"""Regenerates the numbers in robert_max_compliant.md from data/processed.

Run from anywhere, without writing bytecode:

    python3 -B backend/engine/evidence/robert_max_compliant.py

Read-only: it loads the processed data and the Robert scenario, calls the
engine, and prints Markdown to standard output. It is evidence tooling, not
part of the engine (the engine itself does no I/O).
"""

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
for extra in (REPO / "contracts" / "python", REPO):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from byb_contracts import EPS, check_result_errors, compute_content_hash, validate_policy  # noqa: E402

from backend import engine  # noqa: E402
from backend.engine.boundary import solve_max_compliant  # noqa: E402
from backend.engine.check import analyse  # noqa: E402

STEP = 1e-6
PROCESSED = REPO / "data" / "processed"
SOURCES = {"prices": "starter_prices_daily", "fx_usdcad": "starter_fx_usdcad"}


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def policy_of(scenario, rules, version, parent):
    policy = {
        "schema_version": "1.0.0", "policy_id": "pol-robert-real", "persona_id": "robert", "version": version,
        "parent_version": parent, "created_at": "2026-11-14T15:00:00Z", "objectives": scenario["objectives"], "rules": rules,
        "change_note": "Evidence run: fictional-scenario rules confirmed." if version == 1 else "Evidence run: issuer cap raised to 0.30.",
        "content_hash": "sha256:" + "0" * 64,
    }
    policy["content_hash"] = compute_content_hash(policy)
    validate_policy(policy)
    return policy


def latest(rows, day):
    """Independent backward match: the last [date, value] row on or before ``day``."""
    found = None
    for row_date, value in rows:
        if row_date <= day:
            found = (row_date, value)
        else:
            break
    return found


def rule_lines(result):
    lines = ["| rule_id | status | measured lower | measured upper | limit | gap | unknown_causes | breaching_subjects |", "|---|---|---|---|---|---|---|---|"]
    for entry in result["rule_results"]:
        subjects = "; ".join(f"{s['subject_id']} [{s['lower']!r}, {s['upper']!r}]" for s in entry["breaching_subjects"]) or "none"
        lines.append(
            f"| {entry['rule_id']} | {entry['status']} | {entry['measured']['lower']!r} | {entry['measured']['upper']!r} | {entry['limit']!r} | "
            f"{entry['gap']!r} | {', '.join(entry['unknown_causes']) or 'none'} | {subjects} |"
        )
    feasibility = result["feasibility"]
    lines.append("")
    lines.append(f"Feasibility: {feasibility['status']}, cash_after {feasibility['cash_after']!r}. Headline: {result['summary']['headline']}. "
                 f"Contract validation errors: {check_result_errors(result) or 'none'}.")
    return lines


def main():
    data = {name: read(PROCESSED / f"{name}.json") for name in ("instruments", "holdings", "market_data", "controversies")}
    scenario = read(REPO / "contracts" / "scenarios" / "robert.json")
    held = scenario["portfolio"]
    purchase = scenario["demo_requests"][0]["purchase_request"]
    confirmed = [dict(r, status="CONFIRMED", confirmed_at="2026-11-14T15:00:00Z", confirmed_by="demo_user") for r in scenario["scenario_rules"]]
    cap, budget = confirmed
    old_cap = dict(cap, status="SUPERSEDED", superseded_by_rule_id="robert-issuer-cap-2")
    new_cap = dict(cap, rule_id="robert-issuer-cap-2", threshold=0.30, origin="USER_STATED", threshold_source="USER_ENTERED",
                   supersedes_rule_id="robert-issuer-cap-1", original_words=scenario["demo_challenge"]["payload"]["user_note"])
    policies = {
        "v1 (issuer cap 0.10, 2022 loss budget 0.10)": (policy_of(scenario, [cap, budget], 1, None), "robert-issuer-cap-1"),
        "v2 (issuer cap 0.30, 2022 loss budget 0.10)": (policy_of(scenario, [old_cap, new_cap, budget], 2, 1), "robert-issuer-cap-2"),
    }
    args = (data["instruments"], data["holdings"], data["market_data"], data["controversies"])

    def check(policy, target):
        return engine.check_rules(held, policy, dict(purchase, target_direct_weight=target), *args, data_sources=SOURCES)

    out = []
    first = check(policies["v1 (issuer cap 0.10, 2022 loss budget 0.10)"][0], purchase["target_direct_weight"])
    scn = first["scenario"]
    out += [
        "## A. Inputs", "",
        f"- CALCULATION_VERSION: `{engine.CALCULATION_VERSION}`",
        f"- Portfolio `{held['portfolio_id']}` (fictional), valuation date {first['valuation_date']}: cash {held['cash_weight']!r}; "
        + ", ".join(f"{p['instrument_id']} {p['weight']!r}" for p in held["positions"]),
        f"- Request: {purchase['instrument_id']} to a final direct weight of {purchase['target_direct_weight']!r}, funding {purchase['funding']}; "
        f"starting direct weight {first['feasibility']['starting_direct_weight']!r}",
        f"- Scenario `{scn['scenario_id']}`: base date {scn['base_date']}, end date {scn['end_date']}, status {scn['status']}",
        "- Holdings snapshot: " + "; ".join(
            f"{f['fund_id']} holdings_date {f['holdings_date']}, source `{f['source_id']}`, coverage {f['coverage_fraction']!r} ({f['status']})"
            for f in first["data_coverage"]),
        f"- market_data valuation_date {data['market_data']['valuation_date']}; price source id `{SOURCES['prices']}`, FX source id `{SOURCES['fx_usdcad']}`",
        "",
    ]

    # ---- replay inputs, recomputed independently of the engine's replay code
    prices, fx = data["market_data"]["prices"], data["market_data"]["fx_usdcad"]
    engine_rows = {row["instrument_id"]: row for row in scn["instrument_returns"]}
    out += ["## B. 2022 replay inputs (adjusted close, backward-matched FX to CAD)", "",
            "| instrument | currency | base price (date) | base USDCAD (date, age d) | end price (date) | end USDCAD (date, age d) | CAD return, recomputed here | CAD return, engine | starting weight | weight x return |",
            "|---|---|---|---|---|---|---|---|---|---|"]
    weights = {p["instrument_id"]: p["weight"] for p in held["positions"]}
    returns = {}
    start_return = 0.0
    for instrument_id in list(weights) + [purchase["instrument_id"]]:
        series = prices[instrument_id]
        base, end = latest(series["series"], scn["base_date"]), latest(series["series"], scn["end_date"])
        row = engine_rows[instrument_id]
        if series["currency"] == "USD":
            base_fx, end_fx = latest(fx, scn["base_date"]), latest(fx, scn["end_date"])
            value = (end[1] * end_fx[1]) / (base[1] * base_fx[1]) - 1.0
            fx_cells = (f"{base_fx[1]!r} ({base_fx[0]}, {row['base_fx_age_days']})", f"{end_fx[1]!r} ({end_fx[0]}, {row['end_fx_age_days']})")
        else:
            value = end[1] / base[1] - 1.0
            fx_cells = ("n/a", "n/a")
        returns[instrument_id] = value
        weight = weights.get(instrument_id, 0.0)
        start_return += weight * value
        out.append(f"| {instrument_id} | {series['currency']} | {base[1]!r} ({base[0]}) | {fx_cells[0]} | {end[1]!r} ({end[0]}) | {fx_cells[1]} | "
                   f"{value!r} | {row['return_cad']!r} | {weight!r} | {weight * value!r} |")
    nvda_return = returns[purchase["instrument_id"]]
    out += ["",
            f"- Starting replay terminal return R(w0), recomputed here as the sum of weight x return (cash x 0): `{start_return!r}`",
            f"- Starting replay terminal return reported by the engine: `{scn['starting']['scenario_terminal_return']!r}` (starting loss {-scn['starting']['scenario_terminal_return']!r})",
            f"- NVDA CAD replay return r: recomputed `{nvda_return!r}`, engine `{scn['target_instrument_return']!r}`",
            f"- Replay at the requested 0.25: terminal return `{scn['proposed']['scenario_terminal_return']!r}`; "
            f"linear form R(w0) + 0.25 x r = `{scn['starting']['scenario_terminal_return'] + 0.25 * scn['target_instrument_return']!r}`",
            ""]

    # ---- exposure inputs
    sim = engine.simulate_change(held, purchase, data["instruments"])
    start = engine.compute_exposure(sim["starting_portfolio"], data["instruments"], data["holdings"])
    nvidia = data["instruments"]["instruments"][purchase["instrument_id"]]["issuer_id"]
    via = start["lower"].get(nvidia, 0.0)
    extra = start["possible_extra"]
    top_other = max((v, k) for k, v in start["lower"].items() if k != nvidia)
    out += ["## C. Exposure inputs (starting portfolio; none of them changes when NVDA is bought directly)", "",
            f"- NVIDIA known exposure through funds: `{via!r}` = " + " + ".join(f"{k!r} via {f}" for f, k in start["via_fund"].get(nvidia, {}).items()),
            "- Unattributed fund weight U: `" + repr(extra) + "` = " + " + ".join(f"{v!r} ({f})" for f, v in start["uncovered_by_fund"].items()),
            f"- Largest other issuer: {top_other[1]} lower `{top_other[0]!r}`, upper `{top_other[0] + extra!r}`",
            "- Out of equity scope (in neither bound): " + ", ".join(f"{e['instrument_id']} {e['weight']!r}" for e in start["out_of_scope"]),
            f"- Cash before the purchase: `{held['cash_weight']!r}`",
            ""]

    for title, (policy, cap_id) in policies.items():
        result = check(policy, purchase["target_direct_weight"])
        maximum = result["max_compliant"]
        analysis = analyse(held, policy, purchase, *args)
        _, detail = solve_max_compliant(analysis, held, policy, purchase, *args, None, SOURCES)
        limits = {r["rule_id"]: r["limit"] for r in result["rule_results"]}
        cap_limit, budget_limit = limits[cap_id], limits["robert-loss-budget-1"]
        loss_start = -start_return
        budget_alone = (budget_limit - loss_start) / (-nvda_return)
        cap_upper_alone = cap_limit - via - extra
        cap_lower_alone = cap_limit - via
        cash_alone = result["feasibility"]["starting_direct_weight"] + result["feasibility"]["cash_before"]
        unrounded = min(budget_alone, cap_upper_alone, cash_alone)
        out += [f"## D. Policy {title}", "",
                f"Policy `{policy['policy_id']}` version {policy['version']}, content hash `{policy['content_hash']}`.", "",
                "### Closed form, each constraint on its own (final direct weight w of NVDA, w0 = 0)", "",
                "| constraint | condition | boundary w | computed as |", "|---|---|---|---|",
                f"| 2022 loss budget | L(w) = -R(w0) - w x r <= {budget_limit!r} | `{budget_alone!r}` | ({budget_limit!r} - {loss_start!r}) / {-nvda_return!r} |",
                f"| issuer cap, upper-bound version (rule is PASS up to here) | w + via + U <= {cap_limit!r} | `{cap_upper_alone!r}` | {cap_limit!r} - {via!r} - {extra!r} |",
                f"| issuer cap, lower-bound version (rule is a proven FAIL above here) | w + via > {cap_limit!r} | `{cap_lower_alone!r}` | {cap_limit!r} - {via!r} |",
                f"| cash | w - w0 <= cash_before | `{cash_alone!r}` | 0.0 + {held['cash_weight']!r} |",
                "",
                f"- Unrounded boundary, recomputed here = min(budget, cap upper-bound version, cash): `{unrounded!r}`",
                "- Engine's internal PASS intervals in d = w - w0 (lower end, upper end), before rounding: "
                + "; ".join(f"{rule_id} `{info['pass_interval']!r}`" for rule_id, info in detail["rules"].items()),
                f"- Engine `max_compliant`: status {maximum['status']}, final_direct_weight `{maximum['final_direct_weight']!r}` (rounded to 9 decimals), "
                f"additional_purchase `{maximum['additional_purchase']!r}`, binding_constraint `{json.dumps(maximum['binding_constraint'])}`, "
                f"verified_by_rerun {maximum['verified_by_rerun']}",
                f"- Rounding moved the weight by `{maximum['final_direct_weight'] - unrounded!r}` (comparison tolerance EPS = {EPS!r})",
                f"- Engine reason text: {maximum['reason']}",
                ""]
        by_id = {record["evidence_id"]: record for record in result["evidence"]}
        out += ["### Evidence ids (in the check_result for the requested 0.25)", "", f"- max_compliant.evidence_ids: {maximum['evidence_ids']}"]
        for evidence_id in maximum["evidence_ids"]:
            record = by_id[evidence_id]
            out.append(f"  - `{evidence_id}`: {record['metric_id']} = {record['value']!r}; derived_from {record['derived_from']}; formula: {record['formula']}")
        def describe(evidence_id):
            record = by_id.get(evidence_id)
            if record is None:
                return f"  - `{evidence_id}`: NOT PRESENT in this result"
            return (f"  - `{evidence_id}`: {record['label']} {record['metric_id']} = {record['value']!r}, state {record['subject']['portfolio_state']}, "
                    f"period {json.dumps(record['period'])}, sources {record['source_ids']}")

        out.append("- Records cited by `ev-max-final.derived_from` (the inputs of the closed form):")
        out += [describe(evidence_id) for evidence_id in by_id[maximum["evidence_ids"][0]]["derived_from"]]
        behind = [f"ev-px-{purchase['instrument_id']}-base", f"ev-px-{purchase['instrument_id']}-end", f"ev-fx-{scn['base_date']}",
                  f"ev-fx-{scn['end_date']}", f"ev-cw-SPY-{nvidia}", "ev-cov-SPY", "ev-cov-XIU.TO", "ev-hdate-SPY", "ev-hdate-XIU.TO"]
        out.append("- Source records one step behind them (prices, FX rates, constituent weight, coverage, holdings dates):")
        out += [describe(evidence_id) for evidence_id in behind]
        out.append("")

        final = maximum["final_direct_weight"]
        at, above = check(policy, final), check(policy, final + STEP)
        out += [f"### check_rules exactly at the boundary (target_direct_weight = {final!r})", ""] + rule_lines(at) + [""]
        nvidia_row = next(i for i in at["exposure"]["issuers"] if i["issuer_id"] == nvidia)
        out += [f"NVIDIA at the boundary: direct {nvidia_row['proposed']['direct']!r}, known via funds "
                f"{[(p['fund_id'], p['known']) for p in nvidia_row['proposed']['indirect_by_fund']]!r}, lower {nvidia_row['proposed']['lower']!r}, "
                f"upper {nvidia_row['proposed']['upper']!r} (possible_extra {at['exposure']['possible_extra']['proposed']!r}); "
                f"headroom of the upper bound to the cap: {cap_limit - nvidia_row['proposed']['upper']!r}.",
                f"Replay at the boundary: terminal return {at['scenario']['proposed']['scenario_terminal_return']!r}; "
                f"loss minus budget: {-at['scenario']['proposed']['scenario_terminal_return'] - budget_limit!r}.",
                f"max_compliant reported by the run at the boundary: {at['max_compliant']['status']}, final {at['max_compliant']['final_direct_weight']!r}.",
                "",
                f"### check_rules immediately above the boundary (step +{STEP!r}: target_direct_weight = {final + STEP!r})", ""] + rule_lines(above) + [""]
        any_unknown = [e["rule_id"] for e in at["rule_results"] if e["status"] != "PASS"]
        out += [f"Rules that are not PASS at the boundary: {any_unknown or 'none'}.", ""]

    print("\n".join(out))


if __name__ == "__main__":
    main()
