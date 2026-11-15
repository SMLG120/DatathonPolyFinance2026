"""Task 2: engine acceptance for Mateo on the canonical contract.

``backend.engine.check_rules`` is called read-only on (a) the synthetic Mateo universe of the contract fixtures
and (b) the real processed data. Expected numbers are never typed in: they are derived in the test from the
input documents by ``mateo_helpers.hand_*`` (an independent look-through), or asserted as logical properties.
Every result produced through ``run`` is validated with ``byb_contracts.check_result_errors`` and with the
invariants of ``mateo_invariants`` (the same ones ``live_check.py`` applies to the deployed API).
"""

import copy
import json

import pytest
from byb_contracts import (
    check_result_errors,
    derive_summary,
    gap_from_bounds as contract_gap_from_bounds,
    status_from_bounds as contract_status_from_bounds,
    subset_mismatches,
    validate_check_result,
)

from backend import engine
from mateo_helpers import (
    DATA_SOURCES,
    by_rule,
    confirm,
    demo_policy,
    demo_request,
    engine_case,
    hand_flagged,
    hand_lookthrough,
    hand_max_compliant_status,
    hand_rule,
    make_policy,
    make_rule,
    portfolio_of,
    proposed_positions,
    real_data_present,
    real_universe,
    records_of,
    run,
    scenario,
    synthetic_universe,
)
from mateo_invariants import (
    check_result_problems,
    derivation_closure,
    mateo_demo_problems,
    status_from_bounds,
)

TOL = 1e-9
approx = lambda value: pytest.approx(value, abs=TOL)  # noqa: E731
ENERGY, CONTROVERSY = "mateo-excl-energy-1", "mateo-controversy-1"
UNIVERSES = ["synthetic", pytest.param("real", marks=pytest.mark.skipif(
    not real_data_present(), reason="data/processed/{holdings,instruments,market_data}.json are not present (git-ignored)"))]


@pytest.fixture(scope="module", params=UNIVERSES)
def uni(request):
    return {"name": request.param, "data": synthetic_universe() if request.param == "synthetic" else real_universe()}


@pytest.fixture(scope="module")
def demo(uni):
    """Mateo's demonstration: both scenario rules confirmed, SPY to a final direct weight of 0.15."""
    s = scenario()
    policy, request = demo_policy(), demo_request()
    result = run(uni["data"], policy, request)
    hand = {rule["rule_id"]: hand_rule(rule, s["portfolio"], request, uni["data"]) for rule in policy["rules"]}
    return {"result": result, "policy": policy, "request": request, "portfolio": s["portfolio"], "hand": hand, "data": uni["data"]}


def fund(data, fund_id):
    return data["holdings"]["funds"].get(fund_id)


# ---------------------------------------------------------------- sector exclusion

def test_sector_exclusion_bounds_are_the_hand_computed_ones(demo):
    entry, hand = by_rule(demo["result"])[ENERGY], demo["hand"][ENERGY]
    for state, snapshot in (("starting", entry["starting"]), ("proposed", entry)):
        assert snapshot["measured"]["lower"] == approx(hand[state]["lower"])
        assert snapshot["measured"]["upper"] == approx(hand[state]["upper"])
        assert snapshot["status"] == hand[state]["status"]
    assert entry["limit"] == 0.0 and entry["rule_type"] == "exclusion"


def test_sector_lower_bound_is_exactly_the_energy_labelled_xiu_rows(demo):
    """Sum the Energy-labelled XIU.TO rows x the fund weight here, straight from the holdings file."""
    data, entry = demo["data"], by_rule(demo["result"])[ENERGY]
    rows = [row for row in fund(data, "XIU.TO")["holdings"] if row["sector"] == "Energy"]
    assert rows, "the XIU.TO file must report Energy-labelled constituents (LEAD_DECISIONS D7)"
    proven = 0.20 * sum(row["weight_fraction"] for row in rows)
    assert proven > 0
    assert entry["measured"]["lower"] == approx(proven) and entry["starting"]["measured"]["lower"] == approx(proven)
    registry = data["instruments"]["instruments"]
    assert all(registry[i]["sector"] != "Energy" for i in ("MSFT", "CNR.TO", "FTS.TO"))  # nothing held directly is labelled Energy
    # A fund's own registry label ("Broad market ...") is never applied to its constituents.
    assert all("Energy" not in (registry[i]["sector"] or "") for i in ("XIU.TO", "SPY", "ESGV"))
    by_issuer = {}
    for row in rows:
        by_issuer[row["issuer_id"]] = by_issuer.get(row["issuer_id"], 0.0) + 0.20 * row["weight_fraction"]
    subjects = {s["subject_id"]: s for s in entry["breaching_subjects"]}
    assert set(subjects) == set(sorted(by_issuer, key=lambda i: (-by_issuer[i], i))[:10])
    for issuer, subject in subjects.items():
        assert subject["lower"] == approx(by_issuer[issuer])


def test_sector_upper_bound_includes_uncovered_and_unclassified_weight(demo):
    data, entry = demo["data"], by_rule(demo["result"])[ENERGY]
    xiu, spy = fund(data, "XIU.TO"), fund(data, "SPY")
    assert fund(data, "ESGV") is None, "ESGV holdings are deliberately not acquired (D7)"
    assert all(row["sector"] is None for row in spy["holdings"]), "the SPY issuer file reports no constituent sector"
    c_xiu = sum(row["weight_fraction"] for row in xiu["holdings"])
    c_spy = sum(row["weight_fraction"] for row in spy["holdings"])
    lower = entry["measured"]["lower"]
    uncovered_start = 0.20 * max(0.0, 1 - c_xiu) + 0.15                      # XIU.TO residual + the whole of ESGV
    uncovered_after = uncovered_start + 0.15 * max(0.0, 1 - c_spy)          # + the SPY residual
    unclassified_after = 0.15 * c_spy                                        # every listed SPY row: no label
    assert entry["starting"]["measured"]["upper"] == approx(lower + uncovered_start)
    assert entry["measured"]["upper"] == approx(lower + uncovered_after + unclassified_after)
    # missing and unlabelled weight is never treated as zero: the whole ESGV and SPY positions stay possible
    assert entry["measured"]["upper"] >= lower + 0.15 + 0.15 - TOL
    assert entry["starting"]["measured"]["upper"] >= lower + 0.15 - TOL


def test_sector_status_follows_bounds_and_names_the_right_causes(demo):
    data, entry = demo["data"], by_rule(demo["result"])[ENERGY]
    for snapshot in (entry, entry["starting"]):
        lower, upper = snapshot["measured"]["lower"], snapshot["measured"]["upper"]
        assert snapshot["status"] == status_from_bounds("exclusion", lower, upper, 0.0) == contract_status_from_bounds("exclusion", lower, upper, 0.0) == "FAIL"
    wanted = {"MISSING_HOLDINGS", "UNCLASSIFIED_SECTOR"}                     # ESGV; the unlabelled SPY rows
    for fund_id in ("XIU.TO", "SPY"):
        if sum(row["weight_fraction"] for row in fund(data, fund_id)["holdings"]) < 1.0:
            wanted.add("PARTIAL_HOLDINGS")
    assert set(entry["unknown_causes"]) == wanted and len(entry["unknown_causes"]) == len(wanted)
    assert "PARTIAL_HOLDINGS" in wanted  # XIU.TO reports less than 100% in both universes
    assert entry["gap"] == approx(entry["measured"]["lower"]) == approx(contract_gap_from_bounds("exclusion", "FAIL", entry["measured"]["lower"], entry["measured"]["upper"], 0.0))
    assert [o["instrument_id"] for o in entry["out_of_scope"]] == ["XBB.TO"] and entry["out_of_scope"][0]["weight"] == 0.25


def test_unknown_sector_result_is_unknown_not_pass(uni):
    """An Energy-free starting portfolio buying the unlabelled SPY: nothing proven, 0 < upper -> UNKNOWN, never PASS."""
    held = portfolio_of(0.80, {"XBB.TO": 0.10, "MSFT": 0.05, "FTS.TO": 0.05})
    policy = make_policy([confirm(scenario()["scenario_rules"][0])])
    result = run(uni["data"], policy, demo_request(), held)
    entry = result["rule_results"][0]
    assert entry["starting"]["status"] == "PASS" and entry["starting"]["measured"] == {"lower": 0.0, "upper": 0.0}
    assert entry["status"] == "UNKNOWN" and entry["gap"] is None and entry["breaching_subjects"] == []
    assert entry["measured"]["lower"] == 0.0 and entry["measured"]["upper"] == approx(0.15)
    assert "UNCLASSIFIED_SECTOR" in entry["unknown_causes"] and "MISSING_HOLDINGS" not in entry["unknown_causes"]
    assert result["summary"]["headline"] == "NO_FAIL_BUT_UNKNOWN" and result["summary"]["counts"] == {"pass": 0, "fail": 0, "unknown": 1}
    assert result["starting_portfolio_findings"] == []
    assert result["max_compliant"]["status"] == "WITHHELD" and result["max_compliant"]["final_direct_weight"] is None


def test_sector_label_is_matched_exactly_and_never_borrowed(uni):
    """'energy' (lower case) matches no row; an unlabelled row is not filled in from the registry label."""
    rule = confirm(scenario()["scenario_rules"][0])
    rule["parameters"] = {"definition": {"kind": "fund_reported_sector", "sector": "energy"}}
    entry = run(uni["data"], make_policy([rule])).get("rule_results")[0]
    assert entry["measured"]["lower"] == 0.0 and entry["status"] == "UNKNOWN" and entry["breaching_subjects"] == []
    # XOM carries 'Energy' in the instrument registry of both universes, but its SPY row has no label:
    registry = uni["data"]["instruments"]["instruments"]
    assert registry["XOM"]["sector"] == "Energy"
    demo_entry = by_rule(run(uni["data"], demo_policy()))[ENERGY]
    assert "EXXON_MOBIL" not in [s["subject_id"] for s in demo_entry["breaching_subjects"]]


# ---------------------------------------------------------------- controversy exclusion

def test_controversy_bounds_are_the_hand_computed_ones(demo):
    entry, hand = by_rule(demo["result"])[CONTROVERSY], demo["hand"][CONTROVERSY]
    for state, snapshot in (("starting", entry["starting"]), ("proposed", entry)):
        assert snapshot["measured"]["lower"] == approx(hand[state]["lower"])
        assert snapshot["measured"]["upper"] == approx(hand[state]["upper"])
        assert snapshot["status"] == hand[state]["status"] == "FAIL"


def test_controversy_lower_bound_is_the_flagged_issuers_from_the_registry(demo):
    data, entry = demo["data"], by_rule(demo["result"])[CONTROVERSY]
    criteria = demo["policy"]["rules"][1]["parameters"]["criteria"]
    flagged = {record["issuer_id"] for record in data["controversies"]["records"] if record["nature"] in criteria["natures"]}
    assert flagged == {"ENBRIDGE", "CANADIAN_NATURAL_RESOURCES", "EXXON_MOBIL"}
    via = lambda fund_id, weight: {i: weight * sum(r["weight_fraction"] for r in fund(data, fund_id)["holdings"] if r["issuer_id"] == i) for i in flagged}  # noqa: E731
    xiu, spy = via("XIU.TO", 0.20), via("SPY", 0.15)
    assert xiu["ENBRIDGE"] > 0 and xiu["CANADIAN_NATURAL_RESOURCES"] > 0 and spy["EXXON_MOBIL"] > 0 and xiu["EXXON_MOBIL"] == 0
    assert entry["starting"]["measured"]["lower"] == approx(sum(xiu.values()))
    assert entry["measured"]["lower"] == approx(sum(xiu.values()) + sum(spy.values()))
    subjects = {s["subject_id"]: s["lower"] for s in entry["breaching_subjects"]}
    assert subjects == {i: approx(xiu[i] + spy[i]) for i in flagged}
    finding = next(f for f in demo["result"]["starting_portfolio_findings"] if f["rule_id"] == CONTROVERSY)
    assert [s["subject_id"] for s in finding["breaching_subjects"]] == sorted((i for i in flagged if xiu[i] > 0), key=lambda i: (-xiu[i], i))
    assert finding["purchase_effect"]["lower_change"] == approx(spy["EXXON_MOBIL"])  # what the purchase is proven to add


def test_controversy_upper_bound_is_all_in_scope_equity_weight_never_zero(demo):
    data, entry = demo["data"], by_rule(demo["result"])[CONTROVERSY]
    registry = data["instruments"]["instruments"]
    in_scope_start = sum(p["weight"] for p in demo["portfolio"]["positions"] if registry[p["instrument_id"]]["equity_scope"])
    assert in_scope_start == approx(0.50)
    assert entry["starting"]["measured"]["upper"] == approx(in_scope_start)
    assert entry["measured"]["upper"] == approx(in_scope_start + 0.15)
    assert "REGISTRY_ABSENCE" in entry["unknown_causes"] and "MISSING_HOLDINGS" in entry["unknown_causes"]
    assert "UNCLASSIFIED_SECTOR" not in entry["unknown_causes"]  # the two concepts stay separate


@pytest.mark.parametrize("variant", ["empty registry", "no nature matches", "date filter excludes all"])
def test_issuers_absent_from_the_registry_are_not_assessed_never_pass(uni, variant):
    data = copy.deepcopy(uni["data"])
    rule = confirm(scenario()["scenario_rules"][1])
    if variant == "empty registry":
        data["controversies"]["records"] = []
    elif variant == "no nature matches":
        rule["parameters"] = {"criteria": {"natures": ["COURT_RULING"], "event_date_from": None}}
    else:
        rule["parameters"] = {"criteria": {"natures": ["REGULATORY_FINDING", "COURT_RULING", "SETTLEMENT"], "event_date_from": "2026-01-01"}}
    assert hand_flagged(rule["parameters"]["criteria"], data["controversies"]) == {}
    result = run(data, make_policy([rule]))
    entry = result["rule_results"][0]
    assert entry["status"] == "UNKNOWN" and entry["starting"]["status"] == "UNKNOWN"  # not PASS: nobody was assessed
    assert entry["measured"]["lower"] == 0.0 and entry["measured"]["upper"] == approx(0.65)
    assert entry["gap"] is None and entry["breaching_subjects"] == [] and "REGISTRY_ABSENCE" in entry["unknown_causes"]
    assert result["summary"]["counts"]["pass"] == 0 and result["summary"]["headline"] == "NO_FAIL_BUT_UNKNOWN"
    assert result["starting_portfolio_findings"] == [] and result["max_compliant"]["status"] == "WITHHELD"


def test_controversy_date_filter_keeps_only_records_on_or_after_the_date(uni):
    rule = confirm(scenario()["scenario_rules"][1])
    rule["parameters"] = {"criteria": {"natures": ["REGULATORY_FINDING", "COURT_RULING", "SETTLEMENT"], "event_date_from": "2020-01-01"}}
    flagged = hand_flagged(rule["parameters"]["criteria"], uni["data"]["controversies"])
    assert set(flagged) == {"CANADIAN_NATURAL_RESOURCES"}
    entry = run(uni["data"], make_policy([rule]))["rule_results"][0]
    assert [s["subject_id"] for s in entry["breaching_subjects"]] == ["CANADIAN_NATURAL_RESOURCES"]
    weight = 0.20 * sum(r["weight_fraction"] for r in fund(uni["data"], "XIU.TO")["holdings"] if r["issuer_id"] == "CANADIAN_NATURAL_RESOURCES")
    assert entry["measured"]["lower"] == approx(weight) and entry["status"] == "FAIL"


def test_controversy_rule_passes_only_when_no_equity_is_in_scope(uni):
    held = portfolio_of(0.75, {"XBB.TO": 0.25})
    request = {"instrument_id": "XBB.TO", "target_direct_weight": 0.30, "funding": "CASH", "original_words": None}
    result = run(uni["data"], make_policy([confirm(scenario()["scenario_rules"][1])]), request, held)
    entry = result["rule_results"][0]
    assert entry["status"] == "PASS" and entry["measured"] == {"lower": 0.0, "upper": 0.0} and entry["unknown_causes"] == []
    assert result["data_coverage"] == []


def test_a_sector_label_is_not_a_controversy(uni):
    """With an empty registry the Energy rule still fails and the controversy rule is still UNKNOWN: neither feeds the other."""
    data = copy.deepcopy(uni["data"])
    data["controversies"]["records"] = []
    rules = by_rule(run(data, demo_policy()))
    assert rules[ENERGY]["status"] == "FAIL" and rules[CONTROVERSY]["status"] == "UNKNOWN"
    assert rules[CONTROVERSY]["measured"]["lower"] == 0.0


# ---------------------------------------------------------------- starting-portfolio findings

def test_starting_breaches_are_findings_distinct_from_the_purchase_effect(demo):
    result, rules = demo["result"], by_rule(demo["result"])
    findings = {f["rule_id"]: f for f in result["starting_portfolio_findings"]}
    assert list(findings) == [ENERGY, CONTROVERSY]  # policy order; both breached before any purchase
    for rule_id, finding in findings.items():
        entry, hand = rules[rule_id], demo["hand"][rule_id]
        assert finding["status"] == "FAIL" and finding["measured"] == entry["starting"]["measured"]
        assert finding["purchase_effect"]["lower_change"] == approx(hand["proposed"]["lower"] - hand["starting"]["lower"])
        assert finding["purchase_effect"]["upper_change"] == approx(hand["proposed"]["upper"] - hand["starting"]["upper"])
        assert finding["gap"] == approx(hand["starting"]["lower"] - 0.0)
        assert [(s["subject_id"], approx(s["lower"]), approx(s["upper"])) for s in finding["breaching_subjects"]] == [
            (s["subject_id"], s["lower"], s["upper"]) for s in hand["starting"]["subjects"]]
        assert finding["reason"].startswith("Already breached before any purchase")
    # Energy: the purchase proves nothing and could add up to the whole SPY position; reported as that range.
    energy = findings[ENERGY]["purchase_effect"]
    assert energy["lower_change"] == approx(0.0) and energy["upper_change"] == approx(0.15)
    assert findings[CONTROVERSY]["purchase_effect"]["lower_change"] > 0
    assert result["summary"]["starting_portfolio_breaches"] == 2


def test_no_finding_when_the_starting_portfolio_does_not_fail(uni):
    """A rule the purchase itself breaks (issuer cap below Microsoft after the purchase is impossible here), and an
    UNKNOWN starting status, produce no starting-portfolio finding."""
    cap = make_rule("cap-any-20", "max_issuer_exposure", {"issuer_scope": "any"}, 0.20)
    result = run(uni["data"], make_policy([cap]))
    assert result["rule_results"][0]["starting"]["status"] == "UNKNOWN" and result["starting_portfolio_findings"] == []
    same_weight = run(uni["data"], demo_policy(), demo_request(0.0))  # a no-op request: nothing added
    for finding in same_weight["starting_portfolio_findings"]:
        assert finding["purchase_effect"] == {"lower_change": approx(0.0), "upper_change": approx(0.0)}
    assert [f["rule_id"] for f in same_weight["starting_portfolio_findings"]] == [ENERGY, CONTROVERSY]


# ---------------------------------------------------------------- evidence

def test_every_cited_id_and_derivation_resolves(demo):
    result = demo["result"]
    records = records_of(result)
    assert len(records) == len(result["evidence"])
    for entry in result["rule_results"] + result["starting_portfolio_findings"]:
        assert entry["evidence_ids"] and all(i in records for i in entry["evidence_ids"])
        for evidence_id in entry["evidence_ids"]:
            closure = derivation_closure(records, evidence_id)
            assert all(parent in records for i in closure for parent in records[i]["derived_from"])
    for record in result["evidence"]:
        assert record["policy_version"] == demo["policy"]["version"] and record["calculation_version"] == engine.CALCULATION_VERSION


def test_rule_bounds_limit_and_gap_have_records_with_the_right_subject_unit_period_and_state(demo):
    result, records = demo["result"], records_of(demo["result"])
    valuation = {"type": "AS_OF", "date": "2026-11-12"}
    for entry in result["rule_results"]:
        cited = [records[i] for i in entry["evidence_ids"]]

        def one(metric, state):
            found = [r for r in cited if r["metric_id"] == metric and r["subject"] == {"kind": "RULE", "id": entry["rule_id"], "via_fund_id": None, "portfolio_state": state}]
            assert len(found) == 1, (entry["rule_id"], metric, state)
            assert found[0]["unit"] == "fraction" and found[0]["period"] == valuation
            return found[0]

        assert one("exposure_lower", "PROPOSED")["value"] == entry["measured"]["lower"]
        assert one("exposure_upper", "PROPOSED")["value"] == entry["measured"]["upper"]
        assert one("exposure_lower", "STARTING")["value"] == entry["starting"]["measured"]["lower"]
        assert one("exposure_upper", "STARTING")["value"] == entry["starting"]["measured"]["upper"]
        threshold = one("rule_threshold", "NOT_APPLICABLE")
        assert threshold["value"] == entry["limit"] == 0.0 and threshold["label"] == "FICTIONAL_SCENARIO"  # an invented scenario number, labelled so
        gap = one("gap_to_limit", "PROPOSED")
        assert gap["value"] == entry["gap"] and gap["label"] == "CALCULATION"
        assert threshold["evidence_id"] in gap["derived_from"] and one("exposure_lower", "PROPOSED")["evidence_id"] in gap["derived_from"]
        for bound in ("exposure_lower", "exposure_upper"):
            for state in ("PROPOSED", "STARTING"):
                assert one(bound, state)["label"] == "CALCULATION" and one(bound, state)["formula"]


def test_breaching_subjects_trace_back_to_sourced_fund_weights(demo):
    """issuer bound -> exposure via fund -> (portfolio weight, constituent weight as the issuer file reports it)."""
    data, result, records = demo["data"], demo["result"], records_of(demo["result"])
    weights = dict(proposed_positions(demo["portfolio"], demo["request"])[0])
    for entry in result["rule_results"]:
        for subject in entry["breaching_subjects"]:
            issuer = subject["subject_id"]
            lower = next(records[i] for i in entry["evidence_ids"] if records[i]["metric_id"] == "exposure_lower"
                         and records[i]["subject"]["id"] == issuer and records[i]["subject"]["portfolio_state"] == "PROPOSED")
            assert lower["subject"]["kind"] == "ISSUER" and lower["value"] == approx(subject["lower"])
            paths = [records[i] for i in lower["derived_from"]]
            assert paths and all(p["metric_id"] in ("issuer_exposure_via_fund", "issuer_direct_exposure") for p in paths)
            assert sum(p["value"] for p in paths) == approx(subject["lower"])
            for path in paths:
                assert path["subject"]["id"] == issuer and path["subject"]["portfolio_state"] == "PROPOSED" and path["unit"] == "fraction"
                fund_id = path["subject"]["via_fund_id"]
                parents = [records[i] for i in path["derived_from"]]
                weight = next(p for p in parents if p["metric_id"] == "position_weight")
                constituent = next(p for p in parents if p["metric_id"] == "fund_constituent_weight")
                snapshot = fund(data, fund_id)
                from_file = sum(r["weight_fraction"] for r in snapshot["holdings"] if r["issuer_id"] == issuer)
                assert weight["subject"]["id"] == fund_id and weight["value"] == weights[fund_id] and weight["label"] == "FICTIONAL_SCENARIO"
                assert constituent["value"] == approx(from_file) and constituent["subject"] == {
                    "kind": "ISSUER", "id": issuer, "via_fund_id": fund_id, "portfolio_state": "NOT_APPLICABLE"}
                assert constituent["source_ids"] == [snapshot["source_id"]]
                assert constituent["period"] == {"type": "AS_OF", "date": snapshot["holdings_date"]}
                assert path["value"] == approx(weights[fund_id] * from_file)
            upper = next(records[i] for i in entry["evidence_ids"] if records[i]["metric_id"] == "exposure_upper"
                         and records[i]["subject"]["id"] == issuer and records[i]["subject"]["portfolio_state"] == "PROPOSED")
            assert upper["value"] == approx(subject["upper"]) and lower["evidence_id"] in upper["derived_from"]
            extra = [records[i] for i in upper["derived_from"] if records[i]["metric_id"] == "unattributed_fund_weight"]
            assert sum(r["value"] for r in extra) == approx(subject["upper"] - subject["lower"])
            assert {r["subject"]["id"] for r in extra} == {"XIU.TO", "ESGV", "SPY"} and all(r["subject"]["portfolio_state"] == "PROPOSED" for r in extra)


def test_sector_label_evidence_quotes_the_fund_file(demo):
    data, result, records = demo["data"], demo["result"], records_of(demo["result"])
    entry = by_rule(result)[ENERGY]
    xiu = fund(data, "XIU.TO")
    cited_labels = [records[i] for i in entry["evidence_ids"] if records[i]["metric_id"] == "sector_label"]
    labels = [r for r in cited_labels if r["value"] is not None]
    assert {r["subject"]["id"] for r in labels} == {s["subject_id"] for s in entry["breaching_subjects"]}
    assert all(r["subject"]["kind"] == "ISSUER" for r in labels)
    for record in labels:
        row = next(r for r in xiu["holdings"] if r["issuer_id"] == record["subject"]["id"])
        assert record["value"] == row["sector"] == "Energy" and record["unit"] == "text" and record["label"] == "FACT"
        assert record["subject"]["via_fund_id"] == "XIU.TO" and record["source_ids"] == [row["sector_source"]]
        assert record["period"] == {"type": "AS_OF", "date": xiu["holdings_date"]}
    # a null label is only ever about the fund whose file reports none (SEMANTICS section 13); never a positive claim about SPY
    assert all(r["subject"] == {"kind": "FUND", "id": "SPY", "via_fund_id": None, "portfolio_state": "NOT_APPLICABLE"} for r in cited_labels if r["value"] is None)
    assert not [r for r in result["evidence"] if r["metric_id"] == "sector_label" and r["value"] is not None
                and "SPY" in (r["subject"]["id"], r["subject"].get("via_fund_id"))]


def test_controversy_evidence_is_dated_sourced_and_about_the_issuer(demo):
    data, result, records = demo["data"], demo["result"], records_of(demo["result"])
    registry = data["controversies"]["records"]
    entry = by_rule(result)[CONTROVERSY]
    cited = [records[i] for i in entry["evidence_ids"] if records[i]["metric_id"] == "controversy_record"]
    assert len(cited) == len(registry) == 3
    for record in cited:
        source = next(r for r in registry if r["issuer_id"] == record["subject"]["id"])
        assert record["subject"] == {"kind": "ISSUER", "id": source["issuer_id"], "via_fund_id": None, "portfolio_state": "NOT_APPLICABLE"}
        assert record["period"] == {"type": "AS_OF", "date": source["event_date"]}  # the event date, not the valuation date
        assert record["source_ids"] == source["source_ids"] and record["label"] == "FACT" and record["unit"] == "text"
        assert source["record_id"] in record["evidence_id"] or record["value"] == source["record_id"]
        assert source["coverage_note"] in record["assumptions"]  # coverage limits travel with the record


def test_E1_controversy_record_value_is_the_registry_record_id(demo):
    """FINDINGS.md E1 (closed in engine 1.0.8). SEMANTICS section 13: the value is the registry ``record_id``, the
    subject the issuer, the period the event date, the sources the record's sources. The description moved to
    ``assumptions``; it must still say what the registry says (nature and summary), unchanged."""
    registry = {r["issuer_id"]: r for r in demo["data"]["controversies"]["records"]}
    cited = [r for r in demo["result"]["evidence"] if r["metric_id"] == "controversy_record"]
    assert len(cited) == 3
    for record in cited:
        source = registry[record["subject"]["id"]]
        assert record["value"] == source["record_id"]
        assert record["subject"] == {"kind": "ISSUER", "id": source["issuer_id"], "via_fund_id": None, "portfolio_state": "NOT_APPLICABLE"}
        assert record["period"] == {"type": "AS_OF", "date": source["event_date"]} and record["source_ids"] == source["source_ids"]
        assert record["label"] == "FACT" and record["unit"] == "text" and record["derived_from"] == []
        described = " ".join(record["assumptions"])
        assert source["summary"] in described and source["nature"] in described and source["coverage_note"] in described
    # same form as the contract fixture
    fixture = __import__("mateo_helpers").api_fixture("investigation_mateo_succeeded")["response_body"]["result"]["evidence"]
    if demo["data"]["controversies"]["records"][0]["record_id"].startswith("SYN-"):
        assert sorted(r["value"] for r in cited) == sorted(r["value"] for r in fixture if r["metric_id"] == "controversy_record")


def test_E2_sector_rule_bounds_cite_the_labels_and_weights_they_are_computed_from(demo):
    """FINDINGS.md E2 (closed in engine 1.0.8). The rule-level lower bound is derived from the fund's weight and a
    sourced record of the fund's Energy-labelled fraction; the upper bound is derived from a ``sector_label``
    record with a null value for SPY (SEMANTICS section 13; fixture ``ev-spy-sector-labels``). The cited numbers
    are compared with the holdings files and are enough to recompute both bounds."""
    data, result, records = demo["data"], demo["result"], records_of(demo["result"])
    xiu, spy = fund(data, "XIU.TO"), fund(data, "SPY")
    about_rule = lambda state: {"kind": "RULE", "id": ENERGY, "via_fund_id": None, "portfolio_state": state}  # noqa: E731
    for state in ("STARTING", "PROPOSED"):
        lower = next(r for r in result["evidence"] if r["metric_id"] == "exposure_lower" and r["subject"] == about_rule(state))
        parents = [records[i] for i in lower["derived_from"]]
        weight = [r for r in parents if r["metric_id"] == "position_weight"]
        fraction = [r for r in parents if r["metric_id"] == "fund_constituent_weight"]
        assert len(weight) == 1 and len(fraction) == 1 and len(parents) == 2
        from_file = sum(row["weight_fraction"] for row in xiu["holdings"] if row["sector"] == "Energy")
        assert fraction[0]["value"] == approx(from_file) and fraction[0]["source_ids"] == [xiu["source_id"]]
        assert fraction[0]["subject"] == {"kind": "FUND", "id": "XIU.TO", "via_fund_id": None, "portfolio_state": "NOT_APPLICABLE"}
        assert fraction[0]["period"] == {"type": "AS_OF", "date": xiu["holdings_date"]} and fraction[0]["formula"]
        assert weight[0]["subject"]["id"] == "XIU.TO" and weight[0]["value"] == 0.20
        assert weight[0]["value"] * fraction[0]["value"] == approx(lower["value"])  # recomputed from the cited records alone
    upper = next(r for r in result["evidence"] if r["metric_id"] == "exposure_upper" and r["subject"] == about_rule("PROPOSED"))
    parents = [records[i] for i in upper["derived_from"]]
    unlabelled = [r for r in parents if r["metric_id"] == "sector_label"]
    assert len(unlabelled) == 1
    assert unlabelled[0]["value"] is None and unlabelled[0]["unit"] == "text" and unlabelled[0]["label"] == "FACT"
    assert unlabelled[0]["subject"] == {"kind": "FUND", "id": "SPY", "via_fund_id": None, "portfolio_state": "NOT_APPLICABLE"}
    assert unlabelled[0]["source_ids"] == [spy["source_id"]] and unlabelled[0]["period"] == {"type": "AS_OF", "date": spy["holdings_date"]}
    chain = [records[i] for i in derivation_closure(records, upper["evidence_id"])]
    coverage = next(r for r in chain if r["metric_id"] == "fund_coverage_fraction" and r["subject"]["id"] == "SPY")
    spy_weight = next(r for r in parents if r["metric_id"] == "position_weight" and r["subject"]["id"] == "SPY")
    not_reported = sum(r["value"] for r in parents if r["metric_id"] == "unattributed_fund_weight")
    lower_parent = next(r for r in parents if r["metric_id"] == "exposure_lower")
    assert lower_parent["value"] + not_reported + spy_weight["value"] * coverage["value"] == approx(upper["value"])
    # the starting portfolio holds no unlabelled row, so its upper bound cites no "no label" record
    start_upper = next(r for r in result["evidence"] if r["metric_id"] == "exposure_upper" and r["subject"] == about_rule("STARTING"))
    assert not [i for i in start_upper["derived_from"] if records[i]["metric_id"] == "sector_label"]


def test_a_fund_without_a_holdings_file_claims_no_date_and_no_source(demo):
    result = demo["result"]
    row = next(r for r in result["data_coverage"] if r["fund_id"] == "ESGV")
    assert row == {"fund_id": "ESGV", "portfolio_weight": 0.15, "coverage_fraction": 0.0, "sector_labelled_fraction": 0.0,
                   "uncovered_portfolio_weight": 0.15, "holdings_date": None, "source_id": None, "status": "MISSING"}
    about_esgv = [r for r in result["evidence"] if r["subject"]["id"] == "ESGV" or r["subject"]["via_fund_id"] == "ESGV"]
    assert about_esgv
    assert not [r for r in about_esgv if r["metric_id"] in ("holdings_date", "fund_constituent_weight", "issuer_exposure_via_fund", "sector_label")]
    assert all(r["source_ids"] == [] and r["label"] != "FACT" for r in about_esgv)  # nothing about ESGV is presented as a sourced fact
    unattributed = next(r for r in about_esgv if r["metric_id"] == "unattributed_fund_weight" and r["subject"]["portfolio_state"] == "PROPOSED")
    assert unattributed["value"] == approx(0.15)
    for fund_id in ("XIU.TO", "SPY"):
        snapshot = fund(demo["data"], fund_id)
        dates = [r for r in result["evidence"] if r["metric_id"] == "holdings_date" and r["subject"]["id"] == fund_id]
        assert len(dates) == 1 and dates[0]["value"] == snapshot["holdings_date"] and dates[0]["source_ids"] == [snapshot["source_id"]]


# ---------------------------------------------------------------- data coverage

def test_coverage_rows_are_the_file_sums_never_rescaled(demo):
    data, result = demo["data"], demo["result"]
    assert [row["fund_id"] for row in result["data_coverage"]] == ["XIU.TO", "ESGV", "SPY"]  # portfolio order, bond fund excluded
    hand = hand_lookthrough(proposed_positions(demo["portfolio"], demo["request"])[0], data["instruments"], data["holdings"])
    assert subset_mismatches(hand["coverage"], result["data_coverage"]) == []
    for row in result["data_coverage"]:
        snapshot = fund(data, row["fund_id"])
        if snapshot is None:
            continue
        reported = sum(r["weight_fraction"] for r in snapshot["holdings"])
        assert row["coverage_fraction"] == approx(reported) == approx(snapshot["coverage_fraction"])
        assert row["uncovered_portfolio_weight"] == approx(row["portfolio_weight"] * max(0.0, 1 - reported))
        assert row["sector_labelled_fraction"] == approx(sum(r["weight_fraction"] for r in snapshot["holdings"] if r["sector"] is not None))
        assert row["holdings_date"] == snapshot["holdings_date"] and row["source_id"] == snapshot["source_id"]
        if reported < 1.0:
            assert row["status"] == "PARTIAL" and row["coverage_fraction"] < 1.0 and row["uncovered_portfolio_weight"] > 0
    spy = next(row for row in result["data_coverage"] if row["fund_id"] == "SPY")
    assert spy["sector_labelled_fraction"] == 0.0


def test_known_plus_uncovered_weight_equals_the_equity_weight_no_double_counting(demo):
    """Rescaling a partial fund to 100%, or counting a fund and its constituents twice, would break this identity."""
    data = demo["data"]
    registry = data["instruments"]["instruments"]
    positions = proposed_positions(demo["portfolio"], demo["request"])[0]
    exposure = engine.compute_exposure(dict(demo["portfolio"], positions=[{"instrument_id": i, "weight": w} for i, w in positions],
                                            cash_weight=0.10), data["instruments"], data["holdings"])
    in_scope = sum(w for i, w in positions if registry[i]["equity_scope"])
    assert sum(exposure["lower"].values()) + exposure["possible_extra"] == approx(in_scope) == approx(0.65)
    hand = hand_lookthrough(positions, data["instruments"], data["holdings"])
    assert exposure["possible_extra"] == approx(hand["U"]) == approx(demo["result"]["exposure"]["possible_extra"]["proposed"])
    for issuer, value in hand["lower"].items():
        assert exposure["lower"][issuer] == approx(value)
    for row in demo["result"]["exposure"]["issuers"]:
        assert row["proposed"]["lower"] == approx(hand["lower"][row["issuer_id"]])
        assert row["proposed"]["upper"] == approx(hand["lower"][row["issuer_id"]] + hand["U"])
    # Microsoft is held directly and through SPY: counted once each way, never twice (BUILD_BRIEF section 2).
    spy_msft = sum(r["weight_fraction"] for r in fund(data, "SPY")["holdings"] if r["issuer_id"] == "MICROSOFT")
    assert exposure["lower"]["MICROSOFT"] == approx(0.05 + 0.15 * spy_msft)
    listed = {row["issuer_id"]: row for row in demo["result"]["exposure"]["issuers"]}
    if "MICROSOFT" in listed:  # SEMANTICS section 10: breaching subjects are listed first, then the largest, up to 10
        msft = listed["MICROSOFT"]
        assert msft["proposed"]["direct"] == 0.05 and msft["proposed"]["indirect_by_fund"] == [{"fund_id": "SPY", "known": approx(0.15 * spy_msft)}]
        assert msft["starting"]["indirect_by_fund"] == []
    else:
        subjects = {s["subject_id"] for e in demo["result"]["rule_results"] for s in e["breaching_subjects"]}
        assert len(listed) == 10 and set(listed) == subjects
    concentration = next(c for c in demo["result"]["goal_context"] if c["context_type"] == "CONCENTRATION")
    largest = max(hand["lower"], key=lambda i: (hand["lower"][i], i))
    cited = [records_of(demo["result"])[i] for i in concentration["evidence_ids"]]
    assert any(r["subject"]["id"] == largest and r["subject"]["portfolio_state"] == "PROPOSED" and r["value"] == approx(hand["lower"][largest]) for r in cited)


# ---------------------------------------------------------------- maximum compliant weight (SEMANTICS section 11)

def test_demo_max_compliant_is_no_feasible_purchase_with_a_reason_and_no_number(demo):
    maximum = demo["result"]["max_compliant"]
    assert maximum["status"] == "NO_FEASIBLE_PURCHASE"
    assert maximum["binding_constraint"] == {"type": "RULE", "rule_id": ENERGY}  # first rule in policy order failing just above w0
    assert maximum["final_direct_weight"] is None and maximum["additional_purchase"] is None and maximum["verified_by_rerun"] is False
    assert ENERGY in maximum["reason"] and maximum["reason"].strip()
    cited = [records_of(demo["result"])[i] for i in maximum["evidence_ids"]]  # as in the contract fixture: starting lower bound and limit
    assert sorted((r["metric_id"], r["subject"]["id"], r["subject"]["portfolio_state"], r["value"]) for r in cited) == [
        ("exposure_lower", ENERGY, "STARTING", by_rule(demo["result"])[ENERGY]["starting"]["measured"]["lower"]),
        ("rule_threshold", ENERGY, "NOT_APPLICABLE", 0.0)]
    evaluated = [r for r in demo["policy"]["rules"]]
    assert hand_max_compliant_status(evaluated, demo["portfolio"], demo["request"], demo["data"]) == "NO_FEASIBLE_PURCHASE"
    # every fundable target really is a proven failure of that rule (re-run the evaluator on a few of them)
    for target in (1e-6, 0.05, 0.15, 0.25):
        again = by_rule(run(demo["data"], demo["policy"], demo_request(target)))
        assert again[ENERGY]["status"] == "FAIL"
    # policy order decides the constraint: with the controversy rule first, it binds
    reversed_policy = make_policy(list(reversed(demo["policy"]["rules"])))
    assert run(demo["data"], reversed_policy)["max_compliant"]["binding_constraint"] == {"type": "RULE", "rule_id": CONTROVERSY}


MAX_CASES = {
    "starting FAIL that buying cannot repair": (lambda: [confirm(scenario()["scenario_rules"][1])], None, "NO_FEASIBLE_PURCHASE"),
    "UNKNOWN at every target (ESGV missing)": (lambda: [make_rule("cap-any-20", "max_issuer_exposure", {"issuer_scope": "any"}, 0.20)], None, "WITHHELD"),
    "provable PASS up to the cash limit": (lambda: [make_rule("cap-any-40", "max_issuer_exposure", {"issuer_scope": "any"}, 0.40)], None, "SUPPORTED"),
    "no evaluated rule": (lambda: [scenario()["scenario_rules"][0]], None, "WITHHELD"),
    "proven conflict": (lambda: [make_rule("min-msft", "min_issuer_exposure", {"issuer_id": "MICROSOFT"}, 0.20),
                                 make_rule("max-msft", "max_issuer_exposure", {"issuer_scope": "MICROSOFT"}, 0.10)], None, "WITHHELD"),
    "no cash": (lambda: [make_rule("cap-any-40", "max_issuer_exposure", {"issuer_scope": "any"}, 0.40)],
                lambda: portfolio_of(0.0, {"XBB.TO": 0.50, "XIU.TO": 0.50}), "NO_FEASIBLE_PURCHASE"),
}


@pytest.mark.parametrize("name", list(MAX_CASES))
def test_max_compliant_gives_no_number_unless_supported(uni, name):
    rules, held, wanted = MAX_CASES[name]
    held = scenario()["portfolio"] if held is None else held()
    policy = make_policy(rules())
    result = run(uni["data"], policy, demo_request(), held)
    maximum = result["max_compliant"]
    assert maximum["status"] == wanted and maximum["reason"].strip()
    if wanted == "SUPPORTED":
        assert maximum["verified_by_rerun"] is True and maximum["final_direct_weight"] is not None
        final = maximum["final_direct_weight"]
        assert maximum["additional_purchase"] == approx(final - 0.0) and 0 < final <= 0.25 + TOL
        at_boundary = run(uni["data"], policy, demo_request(final), held)  # the same evaluator at the boundary
        assert all(e["status"] == "PASS" for e in at_boundary["rule_results"]) and at_boundary["feasibility"]["status"] == "FEASIBLE"
        just_above = run(uni["data"], policy, demo_request(final + 1e-6), held)
        assert just_above["feasibility"]["status"] == "INSUFFICIENT_CASH" or any(e["status"] != "PASS" for e in just_above["rule_results"])
        assert maximum["binding_constraint"] == {"type": "CASH", "rule_id": None} and final == approx(0.25)
    else:
        assert maximum["final_direct_weight"] is None and maximum["additional_purchase"] is None and maximum["verified_by_rerun"] is False
        records = records_of(result)
        cited = [records[i] for i in maximum["evidence_ids"]]  # every id resolves
        assert not [r for r in cited if r["metric_id"].startswith("max_compliant")]  # no boundary number without SUPPORTED
    if wanted == "WITHHELD":
        assert maximum["binding_constraint"] is None
    if name == "no cash":
        assert maximum["binding_constraint"] == {"type": "CASH", "rule_id": None}
        assert [(r["metric_id"], r["value"], r["subject"]["portfolio_state"]) for r in cited] == [("cash_weight", 0.0, "STARTING")]
    if wanted == "NO_FEASIBLE_PURCHASE" and name != "no cash":
        # the statement "already fails before any purchase" rests on the binding rule's starting lower bound and its limit
        binding = maximum["binding_constraint"]["rule_id"]
        entry = by_rule(result)[binding]
        about = {(r["metric_id"], r["subject"]["portfolio_state"]): r for r in cited if r["subject"] == dict(r["subject"], kind="RULE", id=binding)}
        assert set(about) == {("exposure_lower", "STARTING"), ("rule_threshold", "NOT_APPLICABLE")} and len(cited) == 2
        assert about[("exposure_lower", "STARTING")]["value"] == entry["starting"]["measured"]["lower"] > entry["limit"]
        assert about[("rule_threshold", "NOT_APPLICABLE")]["value"] == entry["limit"]
    if name in ("starting FAIL that buying cannot repair", "UNKNOWN at every target (ESGV missing)", "provable PASS up to the cash limit"):
        evaluated = [r for r in policy["rules"] if r["status"] == "CONFIRMED"]
        assert hand_max_compliant_status(evaluated, held, demo_request(), uni["data"]) == wanted  # brute force over targets agrees


# ---------------------------------------------------------------- policy consistency

def test_min_above_max_on_the_same_issuer_is_a_proven_conflict(uni):
    rules = [make_rule("min-msft", "min_issuer_exposure", {"issuer_id": "MICROSOFT"}, 0.20),
             make_rule("max-msft", "max_issuer_exposure", {"issuer_scope": "MICROSOFT"}, 0.10)]
    result = run(uni["data"], make_policy(rules))
    section = result["policy_consistency"]
    assert section["status"] == "PROVEN_CONFLICT" and len(section["conflicts"]) == 1
    conflict = section["conflicts"][0]
    assert conflict["conflict_type"] == "MIN_EXCEEDS_MAX_SAME_ISSUER" and conflict["rule_ids"] == ["min-msft", "max-msft"]
    assert (conflict["issuer_id"], conflict["min_fraction"], conflict["max_fraction"]) == ("MICROSOFT", 0.20, 0.10)
    assert result["summary"]["headline"] == "POLICY_CONFLICT"
    assert len(result["rule_results"]) == 2  # still evaluated one by one
    assert result["max_compliant"]["status"] == "WITHHELD"
    # a maximum on *any* issuer conflicts with the minimum too; equal limits do not
    any_scope = run(uni["data"], make_policy([rules[0], make_rule("max-any", "max_issuer_exposure", {"issuer_scope": "any"}, 0.10)]))
    assert any_scope["policy_consistency"]["status"] == "PROVEN_CONFLICT"
    equal = run(uni["data"], make_policy([rules[0], make_rule("max-msft", "max_issuer_exposure", {"issuer_scope": "MICROSOFT"}, 0.20)]))
    assert equal["policy_consistency"] == {"status": "CONSISTENT", "conflicts": []}
    other_issuer = run(uni["data"], make_policy([rules[0], make_rule("max-fts", "max_issuer_exposure", {"issuer_scope": "FORTIS"}, 0.10)]))
    assert other_issuer["policy_consistency"]["status"] == "CONSISTENT"


def test_ambiguous_goals_are_not_a_conflict(uni):
    objectives = [
        {"objective_id": "obj-growth", "original_words": "I want maximum growth.", "kind": "goal", "source": "USER_STATED", "case_reference": None},
        {"objective_id": "obj-diversify", "original_words": "I want strict diversification.", "kind": "preference", "source": "USER_STATED", "case_reference": None},
    ]
    cap = make_rule("cap-any-40", "max_issuer_exposure", {"issuer_scope": "any"}, 0.40, objective_id="obj-diversify")
    result = run(uni["data"], make_policy([cap], objectives=objectives))
    assert result["policy_consistency"] == {"status": "CONSISTENT", "conflicts": []}
    assert result["summary"]["headline"] != "POLICY_CONFLICT"
    contexts = {(c["objective_id"], c["context_type"]) for c in result["goal_context"]}
    assert ("obj-growth", "NOT_QUANTIFIED") in contexts and ("obj-diversify", "LINKED_RULE_RESULTS") in contexts
    assert all("status" not in context for context in result["goal_context"])  # an objective is never PASS or FAIL
    no_rules = run(uni["data"], make_policy([], objectives=objectives))
    assert no_rules["policy_consistency"]["status"] == "CONSISTENT" and no_rules["summary"]["headline"] == "NO_RULES_EVALUATED"


def test_an_infeasible_cash_purchase_is_not_a_policy_contradiction(uni):
    result = run(uni["data"], demo_policy(), demo_request(0.40))  # needs 0.40 of cash, 0.25 available
    assert result["execution"]["status"] == "OK"
    assert result["feasibility"]["status"] == "INSUFFICIENT_CASH" and result["feasibility"]["cash_after"] == approx(-0.15)
    assert result["policy_consistency"] == {"status": "CONSISTENT", "conflicts": []}
    assert result["summary"]["feasibility_status"] == "INSUFFICIENT_CASH" and result["summary"]["headline"] == "HAS_FAIL"
    assert len(result["rule_results"]) == 2  # still evaluated at the requested weights
    energy = by_rule(result)[ENERGY]
    assert energy["measured"]["upper"] > by_rule(run(uni["data"], demo_policy()))[ENERGY]["measured"]["upper"]
    feasible_but_failing = run(uni["data"], demo_policy())
    assert feasible_but_failing["policy_consistency"]["status"] == "CONSISTENT"  # a failed rule is not a conflict either


# ---------------------------------------------------------------- which rules are evaluated

def test_only_confirmed_rules_with_a_number_are_evaluated(uni):
    offered_energy, offered_controversy = scenario()["scenario_rules"]
    null_draft = dict(offered_energy, rule_id="draft-excl-energy-1", origin="SYSTEM_PROPOSED", threshold=None, threshold_source=None)
    superseded = dict(confirm(offered_controversy), rule_id="mateo-controversy-0", status="SUPERSEDED", superseded_by_rule_id=None)
    policy = make_policy([offered_energy, null_draft, superseded, confirm(offered_controversy)])
    result = run(uni["data"], policy)
    assert [e["rule_id"] for e in result["rule_results"]] == [CONTROVERSY]
    skipped = result["rules_not_evaluated"]
    assert [(e["rule_id"], e["status"]) for e in skipped] == [(ENERGY, "PROPOSED"), ("draft-excl-energy-1", "PROPOSED"), ("mateo-controversy-0", "SUPERSEDED")]
    assert all(e["reason"].strip() for e in skipped)
    assert "threshold" in skipped[1]["reason"].lower() or "number" in skipped[1]["reason"].lower()
    assert result["summary"]["rules_evaluated"] == 1 and result["summary"]["rules_not_evaluated"] == 3
    # an unconfirmed Energy rule produces no verdict, no finding and no evidence about that rule
    assert [f["rule_id"] for f in result["starting_portfolio_findings"]] == [CONTROVERSY]
    assert not [r for r in result["evidence"] if r["subject"]["kind"] == "RULE" and r["subject"]["id"] in (ENERGY, "draft-excl-energy-1", "mateo-controversy-0")]
    assert result["max_compliant"]["binding_constraint"] == {"type": "RULE", "rule_id": CONTROVERSY}


def test_nothing_confirmed_means_no_verdict_at_all(uni):
    result = run(uni["data"], make_policy(scenario()["scenario_rules"]))  # both still PROPOSED
    assert result["rule_results"] == [] and result["starting_portfolio_findings"] == []
    assert result["summary"]["headline"] == "NO_RULES_EVALUATED" and result["summary"]["counts"] == {"pass": 0, "fail": 0, "unknown": 0}
    assert [e["rule_id"] for e in result["rules_not_evaluated"]] == [ENERGY, CONTROVERSY]
    assert result["max_compliant"]["status"] == "WITHHELD"


def test_a_preview_evaluates_numbered_drafts_and_is_labelled_a_preview(uni):
    offered_energy, _ = scenario()["scenario_rules"]
    null_draft = dict(offered_energy, rule_id="draft-excl-energy-1", origin="SYSTEM_PROPOSED", threshold=None, threshold_source=None)
    result = run(uni["data"], None, draft_rules=[null_draft, offered_energy])
    assert result["preview"] is True and result["policy_id"] is None and result["policy_version"] is None
    assert [e["rule_id"] for e in result["rule_results"]] == [ENERGY]
    assert [e["rule_id"] for e in result["rules_not_evaluated"]] == ["draft-excl-energy-1"]
    assert all(record["policy_version"] is None for record in result["evidence"])
    assert result["goal_context"] == []
    stored = by_rule(run(uni["data"], demo_policy()))[ENERGY]
    assert result["rule_results"][0]["measured"] == stored["measured"]  # the same numbers, only the label differs


def test_preview_matches_the_contract_fixture_on_the_synthetic_universe():
    fixture = __import__("mateo_helpers").api_fixture("check_mateo_preview_unknown")
    result = run(synthetic_universe(), None, fixture["request_body"]["purchase_request"], draft_rules=fixture["request_body"]["draft_rules"])
    expected = engine_case("M2")["expected"]
    assert subset_mismatches(expected, result) == []
    pinned = ("feasibility", "policy_consistency", "rules_not_evaluated", "starting_portfolio_findings", "data_coverage", "scenario", "summary", "preview", "policy_id", "policy_version", "goal_context")
    assert subset_mismatches({k: fixture["response_body"][k] for k in pinned}, result) == []
    wanted, got = fixture["response_body"]["rule_results"][0], result["rule_results"][0]
    for key in ("status", "measured", "limit", "gap", "breaching_subjects", "starting"):
        assert subset_mismatches(wanted[key], got[key]) == []
    assert sorted(wanted["unknown_causes"]) == sorted(got["unknown_causes"])
    assert got["status"] == "UNKNOWN"


@pytest.mark.parametrize("case_id", ["M1", "M2"])
def test_engine_reproduces_the_frozen_mateo_fixtures(case_id):
    case = engine_case(case_id)
    result = run(synthetic_universe(), case["inputs"]["policy"], case["inputs"]["purchase_request"], case["inputs"]["portfolio"])
    assert subset_mismatches(case["expected"], result) == []


# ---------------------------------------------------------------- determinism, purity, validity

def test_same_inputs_give_byte_identical_json_and_inputs_are_not_mutated(uni):
    data = copy.deepcopy(uni["data"])
    held, policy, request = scenario()["portfolio"], demo_policy(), demo_request()
    before = copy.deepcopy((held, policy, request, data))
    first = engine.check_rules(held, policy, request, data["instruments"], data["holdings"], data["market_data"], data["controversies"])
    second = engine.check_rules(held, policy, request, data["instruments"], data["holdings"], data["market_data"], data["controversies"])
    assert json.dumps(first) == json.dumps(second)  # key order included
    assert json.dumps(first, sort_keys=True, ensure_ascii=False).encode() == json.dumps(second, sort_keys=True, ensure_ascii=False).encode()
    assert (held, policy, request, data) == before
    from_copies = engine.check_rules(*copy.deepcopy((held, policy, request)), *(copy.deepcopy(data[k]) for k in ("instruments", "holdings", "market_data", "controversies")))
    assert json.dumps(from_copies) == json.dumps(first)
    assert json.loads(json.dumps(first)) == first  # a plain JSON document: no NaN, no tuples, no custom types
    draft_before = copy.deepcopy(scenario()["scenario_rules"])
    drafts = copy.deepcopy(draft_before)
    engine.check_rules(held, None, request, data["instruments"], data["holdings"], data["market_data"], data["controversies"], draft_rules=drafts)
    assert drafts == draft_before and (held, policy, request, data) == before


def test_mateo_result_does_not_depend_on_price_source_labels(uni):
    """No scenario rule -> no price or FX evidence. ``live_check.py --compare-local`` relies on this."""
    data = uni["data"]
    plain = run(data, demo_policy())
    labelled = run(data, demo_policy(), data_sources=DATA_SOURCES)
    assert json.dumps(plain) == json.dumps(labelled)
    assert plain["scenario"] is None and not [r for r in plain["evidence"] if r["unit"] in ("price", "fx_rate")]


def test_the_demo_result_validates_and_is_consistent_between_sections(demo):
    result = demo["result"]
    validate_check_result(result)
    assert check_result_errors(result) == [] and check_result_problems(result) == []
    assert result["summary"] == derive_summary(result)
    assert result["summary"]["headline"] == "HAS_FAIL" and result["summary"]["counts"] == {"pass": 0, "fail": 2, "unknown": 0}
    registry = demo["data"]["instruments"]["instruments"]
    in_scope = sum(w for i, w in proposed_positions(demo["portfolio"], demo["request"])[0] if registry[i]["equity_scope"])
    assert mateo_demo_problems(result, in_scope_equity_weight=in_scope) == []
    assert result["feasibility"] == {"funding": "CASH", "starting_direct_weight": 0.0, "target_direct_weight": 0.15,
                                     "additional_purchase": 0.15, "cash_before": 0.25, "cash_after": approx(0.10), "status": "FEASIBLE"}
    assert result["scenario"] is None and result["persona_id"] == "mateo" and result["valuation_date"] == "2026-11-12"
    assert result["disclosures"] and result["preview"] is False
    for entry in result["rule_results"]:
        assert entry["status"] != "PASS" and entry["measured"]["upper"] > entry["measured"]["lower"]
    listed = {row["issuer_id"] for row in result["exposure"]["issuers"]}
    assert {s["subject_id"] for e in result["rule_results"] for s in e["breaching_subjects"]} <= listed


@pytest.mark.parametrize("bad, code", [
    ({"instrument_id": "NOT_A_TICKER", "target_direct_weight": 0.15}, "UNSUPPORTED_INSTRUMENT"),
    ({"instrument_id": "MSFT", "target_direct_weight": 0.02}, "TARGET_BELOW_CURRENT_WEIGHT"),
    ({"instrument_id": "SPY", "target_direct_weight": 1.5}, "TARGET_ABOVE_ONE"),
])
def test_a_refused_request_evaluates_nothing(uni, bad, code):
    request = dict(demo_request(), **bad)
    result = run(uni["data"], demo_policy(), request)
    assert result["execution"]["status"] == "INVALID_REQUEST" and result["execution"]["code"] == code
    assert result["rule_results"] == [] and result["starting_portfolio_findings"] == [] and result["evidence"] == []
    assert result["feasibility"] is None and result["max_compliant"] is None and result["exposure"] is None
    assert result["policy_consistency"]["status"] == "NOT_ASSESSED" and result["summary"]["headline"] == "INVALID_REQUEST"


# ---------------------------------------------------------------- real data only

@pytest.mark.skipif(not real_data_present(), reason="data/processed is not present")
def test_real_data_outcome_is_reported(capsys):
    """Prints Mateo's real-data outcome (snapshot date included). Numbers are reported, not pinned."""
    data = real_universe()
    result = run(data, demo_policy(), data_sources=DATA_SOURCES)
    lines = [f"\n== Mateo, SPY to 0.15, real data (valuation {result['valuation_date']}, engine {result['calculation_version']})"]
    for fund_id, snapshot in data["holdings"]["funds"].items():
        lines.append(f"  holdings {fund_id}: as of {snapshot['holdings_date']}, retrieved {snapshot['retrieval_date']}, source {snapshot['source_id']}")
    lines.append(f"  controversy registry: research date {data['controversies']['registry_scope']['research_date']}, {len(data['controversies']['records'])} records")
    for entry in result["rule_results"]:
        lines.append(f"  {entry['rule_id']}: {entry['starting']['status']} [{entry['starting']['measured']['lower']:.9f}, {entry['starting']['measured']['upper']:.9f}]"
                     f" -> {entry['status']} [{entry['measured']['lower']:.9f}, {entry['measured']['upper']:.9f}] limit {entry['limit']} gap {entry['gap']:.9f}"
                     f" causes {entry['unknown_causes']} subjects {[s['subject_id'] for s in entry['breaching_subjects']]}")
    for finding in result["starting_portfolio_findings"]:
        lines.append(f"  starting finding {finding['rule_id']}: effect {finding['purchase_effect']}")
    for row in result["data_coverage"]:
        lines.append(f"  coverage {row['fund_id']}: {row['status']} {row['coverage_fraction']}, labelled {row['sector_labelled_fraction']:.6f}, uncovered {row['uncovered_portfolio_weight']:.9f}")
    lines.append(f"  max compliant: {result['max_compliant']['status']} {result['max_compliant']['binding_constraint']}; headline {result['summary']['headline']}")
    with capsys.disabled():
        print("\n".join(lines))
    assert data["holdings"]["funds"]["XIU.TO"]["holdings_date"] == data["holdings"]["funds"]["SPY"]["holdings_date"] == result["valuation_date"]


@pytest.mark.skipif(not real_data_present(), reason="data/processed is not present")
def test_real_holdings_files_are_stored_unrescaled():
    data = real_universe()
    for fund_id, snapshot in data["holdings"]["funds"].items():
        reported = sum(row["weight_fraction"] for row in snapshot["holdings"])
        assert snapshot["coverage_fraction"] == approx(reported) and reported < 1.0, fund_id  # a rescaled file would sum to 1
        assert len(snapshot["holdings"]) == snapshot["n_holdings"]
    assert "ESGV" not in data["holdings"]["funds"]
    assert all(row["sector"] is None for row in data["holdings"]["funds"]["SPY"]["holdings"])
