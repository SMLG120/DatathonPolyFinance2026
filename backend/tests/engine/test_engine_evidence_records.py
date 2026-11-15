"""Text and calculation-path evidence records (SEMANTICS section 13), on the Mateo fixtures."""

import byb_contracts

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
