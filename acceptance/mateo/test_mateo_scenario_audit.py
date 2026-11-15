"""Task 1: Mateo's scenario, engine fixtures, API fixtures and HAND_CALCS agree with each other and with
LEAD_DECISIONS D7 and SEMANTICS. The fixtures' expected values are recomputed here by hand-style arithmetic
from the synthetic universe's own inputs (``mateo_helpers.hand_*``), never by calling the engine."""

import re

import pytest
from byb_contracts import (
    check_result_errors,
    compute_content_hash,
    derive_summary,
    interpretation_errors,
    investigation_job_errors,
    policy_errors,
    scenario_errors,
    status_from_bounds as contract_status_from_bounds,
    subset_mismatches,
    validate_controversy_registry,
    validate_holdings_snapshot,
    validate_instrument_registry,
    validate_portfolio,
    validate_purchase_request,
)

from mateo_helpers import (
    CONTRACTS,
    ENGINE_FIXTURES,
    PROCESSED,
    api_fixture,
    confirm,
    engine_case,
    hand_bounds,
    hand_lookthrough,
    hand_max_compliant_status,
    hand_rule,
    load,
    proposed_positions,
    scenario,
    synthetic_universe,
)
from mateo_invariants import (
    MATEO_CASH,
    MATEO_OBJECTIVE,
    MATEO_REQUEST,
    MATEO_WEIGHTS,
    check_result_problems,
    gap_from_bounds,
    headline_of,
    mateo_demo_problems,
    mateo_portfolio_problems,
    status_from_bounds,
)

TOL = 1e-9
approx = lambda value: pytest.approx(value, abs=TOL)  # noqa: E731
CONTRACT_FIELDS_SET_BY_CONFIRMATION = ("status", "confirmed_at", "confirmed_by")


# ---------------------------------------------------------------- scenario vs LEAD_DECISIONS D7

def test_scenario_validates_and_matches_d7_portfolio_objective_and_request():
    s = scenario()
    assert scenario_errors(s) == []
    validate_portfolio(s["portfolio"])
    assert mateo_portfolio_problems(s["portfolio"]) == []
    weights = {p["instrument_id"]: p["weight"] for p in s["portfolio"]["positions"]}
    assert weights == MATEO_WEIGHTS and s["portfolio"]["cash_weight"] == MATEO_CASH
    assert s["portfolio"]["cash_weight"] + sum(weights.values()) == approx(1.0)
    assert [p["instrument_id"] for p in s["portfolio"]["positions"]] == ["XBB.TO", "XIU.TO", "ESGV", "MSFT", "CNR.TO", "FTS.TO"]  # D7 table order
    assert s["portfolio"]["valuation_date"] == "2026-11-12" and s["portfolio"]["base_currency"] == "CAD"  # D2
    assert s["fictional"] is True and s["portfolio"]["fictional"] is True
    assert [o["original_words"] for o in s["objectives"]] == [MATEO_OBJECTIVE]
    assert len(s["demo_requests"]) == 1
    request = s["demo_requests"][0]["purchase_request"]
    validate_purchase_request(request)
    assert (request["instrument_id"], request["target_direct_weight"], request["funding"]) == (*MATEO_REQUEST, "CASH")


def test_the_d7_table_in_lead_decisions_is_what_the_scenario_holds():
    """Parse the Mateo table out of LEAD_DECISIONS.md itself instead of trusting a typed copy."""
    text = (CONTRACTS.parent / "docs" / "LEAD_DECISIONS.md").read_text(encoding="utf-8")
    block = text.split("\nMateo:\n", 1)[1].split("\nAmira", 1)[0]
    rows = dict(re.findall(r"^\| ([A-Za-z.() ]+?) \| (0\.\d+) \|$", block, flags=re.M))
    s = scenario()
    assert float(rows.pop("Cash (CAD)")) == s["portfolio"]["cash_weight"]
    assert {k: float(v) for k, v in rows.items()} == {p["instrument_id"]: p["weight"] for p in s["portfolio"]["positions"]}
    quoted = re.search(r'Objective: "(.+?)"', block, flags=re.S).group(1)
    assert " ".join(quoted.split()) == s["objectives"][0]["original_words"]
    assert "SPY at a final direct weight of 0.15" in block
    assert "`exclusion / fund_reported_sector = Energy` with `max_fraction` 0" in " ".join(block.split())


def test_scenario_rules_are_offered_inactive_with_d3_types_and_thresholds():
    energy, controversy = scenario()["scenario_rules"]
    for rule in (energy, controversy):
        assert rule["status"] == "PROPOSED" and rule["confirmed_at"] is None and rule["confirmed_by"] is None  # inactive until confirmed
        assert rule["origin"] == "FICTIONAL_SCENARIO" and rule["threshold_source"] == "FICTIONAL_SCENARIO"
        assert rule["threshold"] == 0.0 and rule["threshold_kind"] == "max_fraction" and rule["unit"] == "fraction"
        assert rule["objective_id"] == "obj-mateo-1"
    assert energy["rule_type"] == "exclusion"
    assert energy["parameters"] == {"definition": {"kind": "fund_reported_sector", "sector": "Energy"}}
    assert controversy["rule_type"] == "controversy_exclusion"
    assert set(controversy["parameters"]["criteria"]["natures"]) == {"REGULATORY_FINDING", "COURT_RULING", "SETTLEMENT"}
    assert controversy["parameters"]["criteria"]["event_date_from"] is None
    # The two concepts stay separate (BUILD_BRIEF section 4): a sector label is not a controversy.
    assert "not a controversy finding" in energy["scope_description"]
    assert "absence from the registry is unknown, never a pass" in controversy["scope_description"]


def test_scenario_script_matches_the_api_fixtures():
    s = scenario()
    interpret = api_fixture("interpret_mateo_clarification")
    phrase = s["demo_phrases"][0]
    assert phrase["expected_outcome"] == "CLARIFICATION"
    assert phrase["original_words"] == interpret["request_body"]["text"] == MATEO_OBJECTIVE
    challenge = api_fixture("challenge_clarify_preference")
    assert s["demo_challenge"]["type"] == challenge["request_body"]["type"] == "CLARIFY_PREFERENCE"
    assert s["demo_challenge"]["payload"] == challenge["request_body"]["payload"]
    job = api_fixture("investigation_mateo_succeeded")["response_body"]
    assert job["request"] == job["resolved_request"] == s["demo_requests"][0]["purchase_request"]
    assert [step["stage"] for step in s["demo_steps"]] == [
        "PERSONA_PORTFOLIO", "GOALS_RULES", "PROPOSED_PURCHASE", "INVESTIGATION", "VERDICT_EVIDENCE", "CHALLENGE"]


# ---------------------------------------------------------------- fixtures vs scenario

@pytest.mark.parametrize("case_id", ["M1", "M2"])
def test_engine_fixture_inputs_are_mateos_portfolio_and_request(case_id):
    case, s = engine_case(case_id), scenario()
    assert case["synthetic"] is True and case["universe"] == "mateo_synthetic_universe.json"
    held, wanted = case["inputs"]["portfolio"], s["portfolio"]
    assert {k: v for k, v in held.items() if k != "portfolio_id"} == {k: v for k, v in wanted.items() if k != "portfolio_id"}
    assert case["inputs"]["purchase_request"] == s["demo_requests"][0]["purchase_request"]
    policy = case["inputs"]["policy"]
    assert policy_errors(policy) == [] and policy["content_hash"] == compute_content_hash(policy)
    assert policy["objectives"] == s["objectives"]


def test_m1_policy_is_the_scenario_rules_confirmed_unchanged():
    case, s = engine_case("M1"), scenario()
    stored = case["inputs"]["policy"]["rules"]
    assert [r["rule_id"] for r in stored] == [r["rule_id"] for r in s["scenario_rules"]] == ["mateo-excl-energy-1", "mateo-controversy-1"]
    for stored_rule, offered in zip(stored, s["scenario_rules"]):
        assert stored_rule["status"] == "CONFIRMED" and stored_rule["confirmed_by"] == "demo_user" and stored_rule["confirmed_at"]
        strip = lambda rule: {k: v for k, v in rule.items() if k not in CONTRACT_FIELDS_SET_BY_CONFIRMATION}  # noqa: E731
        assert strip(stored_rule) == strip(offered)  # same type, parameters, number, provenance and wording
        assert stored_rule == confirm(offered, confirmed_at=stored_rule["confirmed_at"])


def test_synthetic_universe_validates_and_is_never_rescaled():
    u = synthetic_universe()
    assert u["synthetic"] is True
    validate_instrument_registry(u["instruments"])
    validate_holdings_snapshot(u["holdings"])
    validate_controversy_registry(u["controversies"])
    funds = u["holdings"]["funds"]
    assert set(funds) == {"XIU.TO", "SPY"} and "ESGV" not in funds  # D7: ESGV deliberately not acquired
    for fund in funds.values():
        assert fund["coverage_fraction"] == approx(sum(row["weight_fraction"] for row in fund["holdings"]))
        assert fund["n_holdings"] == len(fund["holdings"])
    assert funds["XIU.TO"]["coverage_fraction"] == approx(0.98) and funds["SPY"]["coverage_fraction"] == approx(1.0)
    assert all(row["sector"] is None and row["sector_source"] is None for row in funds["SPY"]["holdings"])
    assert all(row["sector"] is not None for row in funds["XIU.TO"]["holdings"])
    registry = u["instruments"]["instruments"]
    assert {i: registry[i]["sector"] for i in ("MSFT", "CNR.TO", "FTS.TO")} == {
        "MSFT": "Information Technology", "CNR.TO": "Industrials", "FTS.TO": "Utilities"}
    assert registry["XBB.TO"]["equity_scope"] is False and all(registry[i]["equity_scope"] for i in ("XIU.TO", "ESGV", "SPY"))


def test_synthetic_registry_mirrors_issuer_date_and_nature_of_the_project_registry():
    synthetic = synthetic_universe()["controversies"]["records"]
    real = load(PROCESSED / "controversies.json")["records"]  # committed file
    key = lambda record: (record["issuer_id"], record["event_date"], record["nature"])  # noqa: E731
    assert sorted(map(key, synthetic)) == sorted(map(key, real))
    assert all(record["source_ids"] == ["SYNTHETIC_FIXTURE"] and "SYNTHETIC" in record["summary"] for record in synthetic)
    # Each synthetic summary names the real record it mirrors; that record must exist.
    real_ids = {record["record_id"] for record in real}
    for record in synthetic:
        named = re.search(r"record '([^']+)'", record["summary"]).group(1)
        assert named in real_ids


# ---------------------------------------------------------------- expected values, recomputed by hand

def hand_expected(case: dict) -> dict:
    """The ``expected`` block of a Mateo engine fixture, rebuilt from the universe inputs alone."""
    u = synthetic_universe()
    inputs = case["inputs"]
    held, request, policy = inputs["portfolio"], inputs["purchase_request"], inputs["policy"]
    evaluated = [r for r in policy["rules"] if r["status"] == "CONFIRMED" and r["threshold"] is not None]
    w0 = {p["instrument_id"]: p["weight"] for p in held["positions"]}.get(request["instrument_id"], 0.0)
    cash_after = proposed_positions(held, request)[1]
    rule_results, findings = [], []
    for rule in evaluated:
        hand = hand_rule(rule, held, request, u)
        start, after, look = hand["starting"], hand["proposed"], hand["proposed"]["look"]
        causes = set()
        statuses = {row["status"] for row in look["coverage"]}
        causes |= {"MISSING_HOLDINGS"} if "MISSING" in statuses else set()
        causes |= {"PARTIAL_HOLDINGS"} if "PARTIAL" in statuses else set()
        if rule["rule_type"] == "exclusion" and look["unclassified"] > 0:
            causes.add("UNCLASSIFIED_SECTOR")
        if rule["rule_type"] == "controversy_exclusion" and after["upper"] > after["lower"]:
            causes.add("REGISTRY_ABSENCE")
        rule_results.append({
            "rule_id": rule["rule_id"], "status": after["status"], "measured": {"lower": after["lower"], "upper": after["upper"]},
            "limit": rule["threshold"], "gap": gap_from_bounds(rule["rule_type"], after["status"], after["lower"], after["upper"], rule["threshold"]),
            "breaching_subjects": after["subjects"], "unknown_causes": sorted(causes),
            "starting": {"status": start["status"], "measured": {"lower": start["lower"], "upper": start["upper"]}},
            "out_of_scope": [{"instrument_id": i, "weight": w} for i, w in look["out_of_scope"]],
        })
        if start["status"] == "FAIL":
            findings.append({
                "rule_id": rule["rule_id"], "status": "FAIL", "measured": {"lower": start["lower"], "upper": start["upper"]},
                "limit": rule["threshold"], "gap": gap_from_bounds(rule["rule_type"], "FAIL", start["lower"], start["upper"], rule["threshold"]),
                "breaching_subjects": start["subjects"],
                "purchase_effect": {"lower_change": after["lower"] - start["lower"], "upper_change": after["upper"] - start["upper"]},
            })
    look = hand_lookthrough(proposed_positions(held, request)[0], u["instruments"], u["holdings"])
    coverage = [{k: v for k, v in row.items() if k not in ("holdings_date", "source_id")} for row in look["coverage"]]
    return {
        "feasibility": {"funding": "CASH", "starting_direct_weight": w0, "target_direct_weight": request["target_direct_weight"],
                        "additional_purchase": request["target_direct_weight"] - w0, "cash_before": held["cash_weight"],
                        "cash_after": cash_after, "status": "INSUFFICIENT_CASH" if cash_after < -TOL else "FEASIBLE"},
        "rule_results": rule_results, "starting_portfolio_findings": findings, "data_coverage": coverage,
        "max_compliant_status": hand_max_compliant_status(evaluated, held, request, u),
    }


@pytest.mark.parametrize("case_id", ["M1", "M2"])
def test_fixture_expected_values_equal_the_hand_recomputation(case_id):
    case = engine_case(case_id)
    expected, hand = case["expected"], hand_expected(case)
    # hand -> fixture: every number the fixture pins is the number the arithmetic gives
    assert subset_mismatches(expected["feasibility"], hand["feasibility"]) == []
    assert subset_mismatches(expected["rule_results"], hand["rule_results"]) == []
    assert subset_mismatches(expected["starting_portfolio_findings"], hand["starting_portfolio_findings"]) == []
    assert subset_mismatches(expected["data_coverage"], hand["data_coverage"]) == []
    # fixture -> hand: and the fixture pins every part the arithmetic produces (same rules, subjects, causes)
    assert subset_mismatches(hand["rule_results"], expected["rule_results"]) == []
    assert subset_mismatches(hand["starting_portfolio_findings"], expected["starting_portfolio_findings"]) == []
    assert subset_mismatches(hand["data_coverage"], expected["data_coverage"]) == []
    assert expected["max_compliant"]["status"] == hand["max_compliant_status"]


def test_m1_numbers_step_by_step():
    """The M1 arithmetic written out, from the universe's own rows (HAND_CALCS M1)."""
    u = synthetic_universe()
    xiu = {row["issuer_id"]: row for row in u["holdings"]["funds"]["XIU.TO"]["holdings"]}
    spy = {row["issuer_id"]: row for row in u["holdings"]["funds"]["SPY"]["holdings"]}
    w_xiu, w_esgv, w_spy = 0.20, 0.15, 0.15
    energy_rows = [row for row in xiu.values() if row["sector"] == "Energy"]
    assert sorted(row["issuer_id"] for row in energy_rows) == ["CANADIAN_NATURAL_RESOURCES", "ENBRIDGE"]
    energy_lower = sum(w_xiu * row["weight_fraction"] for row in energy_rows)
    uncovered = w_xiu * (1 - sum(r["weight_fraction"] for r in xiu.values())) + w_esgv + w_spy * (1 - sum(r["weight_fraction"] for r in spy.values()))
    unlabelled_spy = w_spy * sum(r["weight_fraction"] for r in spy.values() if r["sector"] is None)
    in_scope_start = w_xiu + w_esgv + 0.05 + 0.05 + 0.05
    flagged_start = w_xiu * (xiu["ENBRIDGE"]["weight_fraction"] + xiu["CANADIAN_NATURAL_RESOURCES"]["weight_fraction"])
    flagged_after = flagged_start + w_spy * spy["EXXON_MOBIL"]["weight_fraction"]

    energy, controversy = engine_case("M1")["expected"]["rule_results"]
    assert energy["starting"]["measured"] == {"lower": approx(energy_lower), "upper": approx(energy_lower + uncovered)}
    assert energy["measured"] == {"lower": approx(energy_lower), "upper": approx(energy_lower + uncovered + unlabelled_spy)}
    assert (energy_lower, uncovered, unlabelled_spy) == (approx(0.014), approx(0.154), approx(0.15))
    assert controversy["starting"]["measured"] == {"lower": approx(flagged_start), "upper": approx(in_scope_start)}
    assert controversy["measured"] == {"lower": approx(flagged_after), "upper": approx(in_scope_start + w_spy)}
    assert energy["gap"] == approx(energy_lower - 0.0) and controversy["gap"] == approx(flagged_after - 0.0)
    energy_finding, controversy_finding = engine_case("M1")["expected"]["starting_portfolio_findings"]
    assert energy_finding["purchase_effect"] == {"lower_change": approx(0.0), "upper_change": approx(unlabelled_spy)}  # 0 proven, up to 0.15 possible
    assert controversy_finding["purchase_effect"] == {"lower_change": approx(flagged_after - flagged_start), "upper_change": approx(w_spy)}
    # Exxon Mobil is flagged by the registry but carries no sector label: it breaches the controversy rule only.
    assert "EXXON_MOBIL" not in [s["subject_id"] for s in energy["breaching_subjects"]]
    assert [s["subject_id"] for s in controversy["breaching_subjects"]] == ["ENBRIDGE", "CANADIAN_NATURAL_RESOURCES", "EXXON_MOBIL"]
    assert [s["subject_id"] for s in controversy_finding["breaching_subjects"]] == ["ENBRIDGE", "CANADIAN_NATURAL_RESOURCES"]


@pytest.mark.parametrize("case_id", ["M1", "M2"])
def test_fixture_expected_block_is_internally_consistent(case_id):
    expected = engine_case(case_id)["expected"]
    types = {r["rule_id"]: r["rule_type"] for r in engine_case(case_id)["inputs"]["policy"]["rules"]}
    for entry in expected["rule_results"]:
        rule_type, limit = types[entry["rule_id"]], entry["limit"]
        for snapshot in (entry, entry["starting"]):
            lower, upper = snapshot["measured"]["lower"], snapshot["measured"]["upper"]
            assert lower <= upper
            assert snapshot["status"] == status_from_bounds(rule_type, lower, upper, limit) == contract_status_from_bounds(rule_type, lower, upper, limit)
        assert entry["gap"] == (None if entry["status"] == "UNKNOWN" else approx(gap_from_bounds(rule_type, entry["status"], entry["measured"]["lower"], entry["measured"]["upper"], limit)))
        assert entry["unknown_causes"] or entry["status"] != "UNKNOWN"
        assert entry["status"] == "FAIL" or entry["breaching_subjects"] == []
    by_id = {entry["rule_id"]: entry for entry in expected["rule_results"]}
    assert [f["rule_id"] for f in expected["starting_portfolio_findings"]] == [e["rule_id"] for e in expected["rule_results"] if e["starting"]["status"] == "FAIL"]
    for finding in expected["starting_portfolio_findings"]:
        entry = by_id[finding["rule_id"]]
        assert finding["measured"] == entry["starting"]["measured"]
        assert finding["purchase_effect"]["lower_change"] == approx(entry["measured"]["lower"] - entry["starting"]["measured"]["lower"])
        assert finding["purchase_effect"]["upper_change"] == approx(entry["measured"]["upper"] - entry["starting"]["measured"]["upper"])
    summary = expected["summary"]
    counts = {k: sum(1 for e in expected["rule_results"] if e["status"] == k.upper()) for k in ("pass", "fail", "unknown")}
    assert summary["counts"] == counts and summary["rules_evaluated"] == len(expected["rule_results"])
    assert summary["starting_portfolio_breaches"] == len(expected["starting_portfolio_findings"])
    assert summary["feasibility_status"] == expected["feasibility"]["status"]
    assert summary["headline"] == headline_of(dict(expected, execution=expected["execution"]))
    maximum = expected["max_compliant"]
    assert maximum["final_direct_weight"] is None and maximum["additional_purchase"] is None and maximum["verified_by_rerun"] is False
    assert expected["scenario"] is None  # no scenario rule


def test_expected_max_compliant_statuses_follow_semantics_section_11():
    m1, m2 = engine_case("M1")["expected"], engine_case("M2")["expected"]
    # M1: the Energy lower bound is above the limit at every fundable target -> NO_FEASIBLE_PURCHASE, first failing rule in policy order.
    assert m1["max_compliant"]["status"] == "NO_FEASIBLE_PURCHASE"
    assert m1["max_compliant"]["binding_constraint"] == {"type": "RULE", "rule_id": "mateo-excl-energy-1"}
    # M2: nothing proven either way -> WITHHELD, no constraint, no number.
    assert m2["max_compliant"]["status"] == "WITHHELD" and m2["max_compliant"]["binding_constraint"] is None
    assert m2["rule_results"][0]["status"] == "UNKNOWN" and m2["summary"]["headline"] == "NO_FAIL_BUT_UNKNOWN"


# ---------------------------------------------------------------- HAND_CALCS.md vs fixtures

def hand_calc_section(case_id: str) -> str:
    text = (ENGINE_FIXTURES / "HAND_CALCS.md").read_text(encoding="utf-8")
    shared = text.split("## Mateo-shaped universe", 1)[1].split("\n## ", 1)[0]
    own = text.split(f"\n## {case_id} ", 1)[1].split("\n## ", 1)[0]
    return shared + own


def numbers_in(node) -> set:
    found = set()
    if isinstance(node, dict):
        for value in node.values():
            found |= numbers_in(value)
    elif isinstance(node, list):
        for value in node:
            found |= numbers_in(value)
    elif isinstance(node, float):
        found.add(node)
    return found


@pytest.mark.parametrize("case_id", ["M1", "M2"])
def test_hand_calcs_document_derives_every_expected_number_and_status(case_id):
    section = hand_calc_section(case_id)
    printed = {float(token) for token in re.findall(r"(?<![\w.])\d+\.\d+(?![\w])", section)}
    expected = engine_case(case_id)["expected"]
    missing = sorted(n for n in numbers_in(expected) if not any(abs(n - p) <= TOL for p in printed))
    assert missing == [], f"numbers in {case_id}.json that HAND_CALCS.md never derives: {missing}"
    for entry in expected["rule_results"]:
        assert f"`{entry['rule_id']}`" in section
        for cause in entry["unknown_causes"]:
            assert cause in section
    assert expected["max_compliant"]["status"] in section and expected["summary"]["headline"] in section
    for row in expected["data_coverage"]:
        assert row["status"] in section


# ---------------------------------------------------------------- API fixtures vs engine fixtures

def test_investigation_fixture_result_is_m1():
    fixture = api_fixture("investigation_mateo_succeeded")
    job = fixture["response_body"]
    assert fixture["synthetic"] is True and investigation_job_errors(job) == []
    result, m1 = job["result"], engine_case("M1")
    assert check_result_errors(result) == []
    assert subset_mismatches(m1["expected"], result) == []
    assert result["summary"] == derive_summary(result)
    assert job["status"] == "SUCCEEDED" and job["failure"] is None and job["clarification"] is None
    assert (job["policy_id"], job["policy_version"]) == (m1["inputs"]["policy"]["policy_id"], m1["inputs"]["policy"]["version"])
    assert result["preview"] is False and result["policy_version"] == 1
    assert check_result_problems(result, strict_evidence=False) == []
    assert mateo_demo_problems(result, in_scope_equity_weight=0.20 + 0.15 + 0.05 + 0.05 + 0.05 + 0.15) == []
    # the server ran the checks itself, whatever the model did (BUILD_BRIEF section 6)
    server_tools = [step["tool"] for step in job["steps"] if step["initiated_by"] == "SERVER"]
    assert "check_rules" in server_tools and "max_compliant_amount" in server_tools
    assert all(statement["evidence_ids"] for statement in job["explanation"] if re.search(r"\d%", statement["text"]))  # numbers cite records


def test_preview_fixture_result_is_m2_and_unknown_is_not_a_pass():
    fixture = api_fixture("check_mateo_preview_unknown")
    request, result, m2 = fixture["request_body"], fixture["response_body"], engine_case("M2")
    assert check_result_errors(result) == [] and check_result_problems(result, strict_evidence=False) == []
    assert request["policy_id"] is None and request["policy_version"] is None and len(request["draft_rules"]) == 1
    draft, stored = request["draft_rules"][0], m2["inputs"]["policy"]["rules"][0]
    assert draft["status"] == "PROPOSED" and draft["confirmed_at"] is None
    same = ("rule_id", "rule_type", "parameters", "threshold", "threshold_kind")
    assert {k: draft[k] for k in same} == {k: stored[k] for k in same}
    expected = dict(m2["expected"])
    assert subset_mismatches(expected, result) == []
    assert result["preview"] is True and result["policy_id"] is None and result["policy_version"] is None
    assert all(record["policy_version"] is None for record in result["evidence"])
    assert result["goal_context"] == []
    entry = result["rule_results"][0]
    assert entry["status"] == "UNKNOWN" and entry["gap"] is None and entry["unknown_causes"]
    assert result["summary"]["headline"] == "NO_FAIL_BUT_UNKNOWN" and result["summary"]["counts"]["pass"] == 0
    threshold = next(r for r in result["evidence"] if r["metric_id"] == "rule_threshold")
    assert threshold["label"] == "ASSUMPTION"  # a draft number is not a confirmed fact


def test_fixture_evidence_follows_semantics_section_13_for_text_records():
    result = api_fixture("investigation_mateo_succeeded")["response_body"]["result"]
    registry = {record["record_id"]: record for record in synthetic_universe()["controversies"]["records"]}
    records = [r for r in result["evidence"] if r["metric_id"] == "controversy_record"]
    assert len(records) == 3
    for record in records:
        source = registry[record["value"]]  # the value is the registry record_id
        assert record["subject"] == {"kind": "ISSUER", "id": source["issuer_id"], "via_fund_id": None, "portfolio_state": "NOT_APPLICABLE"}
        assert record["period"] == {"type": "AS_OF", "date": source["event_date"]} and record["source_ids"] == source["source_ids"]
    fund_label = next(r for r in result["evidence"] if r["metric_id"] == "sector_label" and r["subject"]["kind"] == "FUND")
    assert fund_label["value"] is None and fund_label["subject"]["id"] == "SPY"  # no label reported for the whole fund


@pytest.mark.xfail(strict=True, reason="FINDINGS.md L1: the fixture shows numbers that no record of its evidence[] backs")
def test_L1_every_number_shown_in_the_investigation_fixture_is_backed_by_a_record():
    """SEMANTICS section 13: 'Every number shown to the user is backed by a record in evidence[]'."""
    result = api_fixture("investigation_mateo_succeeded")["response_body"]["result"]
    backed = [(r["metric_id"], r["subject"]["id"], r["subject"]["portfolio_state"], r["value"]) for r in result["evidence"] if r["unit"] == "fraction"]

    def is_backed(metric, subject, state, value):
        return any(m == metric and s == subject and st == state and abs(v - value) <= TOL for m, s, st, v in backed)

    unbacked = []
    for section, state in ((result["rule_results"], "PROPOSED"), (result["starting_portfolio_findings"], "STARTING")):
        for entry in section:
            for subject in entry["breaching_subjects"]:
                if not is_backed("exposure_upper", subject["subject_id"], state, subject["upper"]):
                    unbacked.append((entry["rule_id"], state, subject["subject_id"], "upper", subject["upper"]))
    for finding in result["starting_portfolio_findings"]:
        if not is_backed("gap_to_limit", finding["rule_id"], "STARTING", finding["gap"]):
            unbacked.append((finding["rule_id"], "STARTING", "gap", finding["gap"]))
    assert unbacked == []
