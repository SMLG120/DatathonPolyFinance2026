"""Every contract fixture (E01-E22, R1, R2, M1): the engine output must equal the hand-calculated values."""

import pytest
from byb_contracts import check_result_errors, subset_mismatches, validate_check_result

from backend import engine
from engine_helpers import CASE_IDS, FIXTURES, case, run_case


def test_every_fixture_file_is_covered():
    on_disk = sorted(p.stem for p in FIXTURES.glob("*.json") if "universe" not in p.name)
    assert on_disk == sorted(CASE_IDS)


@pytest.mark.parametrize("case_id", CASE_IDS)
def test_fixture_expected_values(case_id):
    result = run_case(case_id)
    assert subset_mismatches(case(case_id)["expected"], result) == []


@pytest.mark.parametrize("case_id", CASE_IDS)
def test_fixture_result_is_a_valid_check_result(case_id):
    result = run_case(case_id)
    assert check_result_errors(result) == []
    validate_check_result(result)
    assert result["calculation_version"] == engine.CALCULATION_VERSION


@pytest.mark.parametrize("case_id", CASE_IDS)
def test_fixture_evidence_is_complete(case_id):
    """Every id cited anywhere exists, and each rule result cites its threshold and its measurement."""
    result = run_case(case_id)
    known = {record["evidence_id"] for record in result["evidence"]}
    assert len(known) == len(result["evidence"])
    by_id = {record["evidence_id"]: record for record in result["evidence"]}
    for entry in result["rule_results"]:
        assert set(entry["evidence_ids"]) <= known
        metrics = {by_id[i]["metric_id"] for i in entry["evidence_ids"]}
        assert "rule_threshold" in metrics
        if entry["measured"] is not None:
            assert metrics & {"exposure_lower", "scenario_loss"}
        if entry["gap"] is not None:
            assert "gap_to_limit" in metrics
    for record in result["evidence"]:
        if record["label"] == "CALCULATION":
            assert record["formula"]
