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
