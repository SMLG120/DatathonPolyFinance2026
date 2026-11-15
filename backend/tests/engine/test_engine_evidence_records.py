"""Text and calculation-path evidence records (SEMANTICS section 13), on the Mateo fixtures."""

import byb_contracts
import pytest

from engine_helpers import case, run_case, universe


def records(result, metric):
    return [record for record in result["evidence"] if record["metric_id"] == metric]


def test_controversy_record_value_is_the_registry_record_id(case_id="M1"):
    """The value identifies the record; the event date is the period; the registry's wording is description only."""
    result = run_case(case_id)
    byb_contracts.validate_check_result(result)
    registry = {record["record_id"]: record for record in universe(case(case_id)["universe"])["controversies"]["records"]}
    found = records(result, "controversy_record")
    # The same three records, on the same issuers, as contracts/fixtures/api/investigation_mateo_succeeded.json.
    assert sorted((record["value"], record["subject"]["id"]) for record in found) == [
        ("SYN-MIRROR-1", "EXXON_MOBIL"), ("SYN-MIRROR-2", "ENBRIDGE"), ("SYN-MIRROR-3", "CANADIAN_NATURAL_RESOURCES")]
    for record in found:
        source = registry[record["value"]]  # KeyError here = the value is not a record_id
        assert record["unit"] == "text" and record["label"] == "FACT"
        assert record["subject"] == {"kind": "ISSUER", "id": source["issuer_id"], "via_fund_id": None, "portfolio_state": "NOT_APPLICABLE"}
        assert record["period"] == {"type": "AS_OF", "date": source["event_date"]}
        assert record["source_ids"] == source["source_ids"]
        # nothing but the id in the value: no nature, date or summary text
        assert source["summary"] not in record["value"] and source["nature"] not in record["value"] and source["event_date"] not in record["value"]
        described = " ".join(record["assumptions"])
        assert source["summary"] in described and source["nature"] in described and source["coverage_note"] in described
        assert "not a judgement of the company" in described
    cited = {i for entry in result["rule_results"] if entry["rule_type"] == "controversy_exclusion" for i in entry["evidence_ids"]}
    assert {record["evidence_id"] for record in found} <= cited


def reachable(result, start):
    """Every record reachable from ``start`` through derived_from, including itself."""
    by_id = {record["evidence_id"]: record for record in result["evidence"]}
    seen, todo = {}, [start]
    while todo:
        current = todo.pop()
        if current not in seen:
            seen[current] = by_id[current]  # KeyError here = a dangling derived_from
            todo.extend(by_id[current]["derived_from"])
    return list(seen.values())


def energy_rule(result):
    return next(entry for entry in result["rule_results"] if entry["rule_id"] == "mateo-excl-energy-1")


def test_sector_lower_bound_reaches_the_sector_fraction_it_multiplies():
    """M1: Energy lower bound 0.014 = 0.2 (XIU.TO weight) x 0.07 (XIU.TO rows labelled Energy): both are records."""
    result = run_case("M1")
    byb_contracts.validate_check_result(result)
    rule = energy_rule(result)
    by_id = {record["evidence_id"]: record for record in result["evidence"]}
    for state in ("STARTING", "PROPOSED"):
        lower = next(by_id[i] for i in rule["evidence_ids"]
                     if by_id[i]["metric_id"] == "exposure_lower" and by_id[i]["subject"] == {"kind": "RULE", "id": rule["rule_id"], "via_fund_id": None, "portfolio_state": state})
        assert lower["value"] == pytest.approx(0.014, abs=1e-12)
        path = reachable(result, lower["evidence_id"])
        weight = next(r for r in path if r["metric_id"] == "position_weight" and r["subject"]["id"] == "XIU.TO")
        fraction = next(r for r in path if r["metric_id"] == "fund_constituent_weight" and r["subject"]["kind"] == "FUND" and r["subject"]["id"] == "XIU.TO")
        assert fraction["value"] == pytest.approx(0.07, abs=1e-12) and fraction["source_ids"] and fraction["label"] == "CALCULATION"
        assert weight["value"] * fraction["value"] == pytest.approx(lower["value"], abs=1e-12)  # the bound is recomputable from its path
        assert "Energy" in fraction["formula"] and fraction["period"]["type"] == "AS_OF"


def test_unclassified_fund_has_a_null_sector_label_record_when_it_is_a_cause():
    """M1 buys SPY, whose synthetic holdings file has no sector label: the cause UNCLASSIFIED_SECTOR is backed by a record."""
    result = run_case("M1")
    rule = energy_rule(result)
    assert "UNCLASSIFIED_SECTOR" in rule["unknown_causes"]
    null_labels = [r for r in records(result, "sector_label") if r["value"] is None]
    assert [(r["subject"]["kind"], r["subject"]["id"], r["unit"]) for r in null_labels] == [("FUND", "SPY", "text")]
    record = null_labels[0]
    assert record["evidence_id"] in rule["evidence_ids"] and record["source_ids"] and record["label"] == "FACT"
    assert "never read as outside the sector" in record["assumptions"][0]
    upper = next(r for r in result["evidence"] if r["metric_id"] == "exposure_upper" and r["subject"]["id"] == rule["rule_id"] and r["subject"]["portfolio_state"] == "PROPOSED")
    assert record["evidence_id"] in upper["derived_from"]
    # XIU.TO reports labels and ESGV has no file at all: neither gets a "no label" record.
    assert all(r["value"] is not None for r in records(result, "sector_label") if r["subject"]["id"] != "SPY")
    # Before the purchase SPY is not held, nothing is unclassified, and no such record is on the starting path.
    start_upper = next(r for r in result["evidence"] if r["metric_id"] == "exposure_upper" and r["subject"]["id"] == rule["rule_id"] and r["subject"]["portfolio_state"] == "STARTING")
    assert record["evidence_id"] not in {r["evidence_id"] for r in reachable(result, start_upper["evidence_id"])}


def test_no_null_label_record_without_the_cause():
    result = run_case("M2")  # no sector rule
    assert [r for r in records(result, "sector_label") if r["value"] is None] == []


NO_PURCHASE_CASES = ["E09", "E11", "E15", "E16", "E21", "M1"]


@pytest.mark.parametrize("case_id", NO_PURCHASE_CASES)
def test_no_feasible_purchase_cites_what_proves_it(case_id):
    """As contracts/fixtures/api/investigation_mateo_succeeded.json does: the binding rule's starting bound and its threshold."""
    result = run_case(case_id)
    byb_contracts.validate_check_result(result)
    maximum = result["max_compliant"]
    assert maximum["status"] == "NO_FEASIBLE_PURCHASE" and maximum["final_direct_weight"] is None
    by_id = {record["evidence_id"]: record for record in result["evidence"]}
    cited = [by_id[i] for i in maximum["evidence_ids"]]  # KeyError here = a citation of a record that does not exist
    binding = maximum["binding_constraint"]
    if binding["type"] == "CASH":
        assert [(r["metric_id"], r["subject"]["portfolio_state"]) for r in cited] == [("cash_weight", "STARTING")]
        assert cited[0]["value"] <= byb_contracts.EPS
        return
    rule = next(entry for entry in result["rule_results"] if entry["rule_id"] == binding["rule_id"])
    proof, threshold = cited
    assert threshold["metric_id"] == "rule_threshold" and threshold["subject"]["id"] == rule["rule_id"] and threshold["value"] == rule["limit"]
    assert proof["subject"]["portfolio_state"] == "STARTING"
    if rule["rule_type"] == "min_issuer_exposure":
        assert proof["metric_id"] == "exposure_upper" and proof["value"] == rule["starting"]["measured"]["upper"]
    else:
        assert proof["metric_id"] in ("exposure_lower", "scenario_loss") and proof["value"] == rule["starting"]["measured"]["lower"]
        # No purchase can help: before buying anything the proven bound is already at or beyond the limit.
        assert proof["value"] >= threshold["value"] - byb_contracts.EPS


def test_mateo_no_feasible_purchase_cites_the_energy_rule_like_the_api_fixture():
    maximum = run_case("M1")["max_compliant"]
    assert maximum["binding_constraint"] == {"type": "RULE", "rule_id": "mateo-excl-energy-1"}
    assert maximum["evidence_ids"] == ["ev-rule-mateo-excl-energy-1-lo-start", "ev-thr-mateo-excl-energy-1"]


def test_share_classes_inside_a_fund_cite_each_reported_row():
    """E04: FUND_A reports ISS_B on two rows (0.10 and 0.05). The aggregated 0.15 is a calculation over two cited rows."""
    result = run_case("E04")
    byb_contracts.validate_check_result(result)
    by_id = {record["evidence_id"]: record for record in result["evidence"]}
    aggregated = [r for r in result["evidence"] if r["metric_id"] == "fund_constituent_weight" and r["label"] == "CALCULATION"
                  and r["subject"]["kind"] == "ISSUER" and r["subject"]["id"] == "ISS_B"]
    assert aggregated, "E04 holds FUND_A, which reports ISS_B on two rows"
    for record in aggregated:
        rows = [by_id[i] for i in record["derived_from"]]
        assert len(rows) >= 2 and all(r["label"] == "FACT" and r["metric_id"] == "fund_constituent_weight" and r["source_ids"] for r in rows)
        assert all(r["subject"] == record["subject"] and r["period"] == record["period"] for r in rows)
        assert sum(r["value"] for r in rows) == pytest.approx(record["value"], abs=1e-12)
        assert sorted(r["value"] for r in rows) == [0.05, 0.1]
        assert {r["assumptions"][0] for r in rows} == {"One reported row of the fund's holdings file: SYN_B1.", "One reported row of the fund's holdings file: SYN_B2."}
        assert "0.1 + 0.05" in record["formula"]
    # A company on a single row is still one FACT record with no calculation.
    single = [r for r in result["evidence"] if r["metric_id"] == "fund_constituent_weight" and r["label"] == "FACT" and not r["evidence_id"].startswith("ev-cwrow-")]
    assert all(r["derived_from"] == [] and r["formula"] is None for r in single)
