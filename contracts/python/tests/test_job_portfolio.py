"""The optional members added for a customized fictional portfolio (api.md section 2a). Standard library only.

A job may carry the exact portfolio it was checked against; when it does, the validator ties it to the job
and to the result. Bounds in a result are not capped at 1 (SEMANTICS section 5).
"""

from __future__ import annotations

import copy
import json

import byb_contracts as byb
from paths import CONTRACTS

API = CONTRACTS / "fixtures" / "api"


def _load(name):
    return json.loads((API / f"{name}.json").read_text(encoding="utf-8"))


def _job_with_portfolio():
    job = copy.deepcopy(_load("investigation_robert_succeeded")["response_body"])
    portfolio = copy.deepcopy(_load("portfolio_robert")["response_body"]["scenario"]["portfolio"])
    assert job["result"]["portfolio_id"] == portfolio["portfolio_id"]
    job["portfolio"] = portfolio
    return job


def test_a_job_without_a_portfolio_and_a_job_with_its_own_portfolio_are_both_valid():
    assert byb.investigation_job_errors(_load("investigation_robert_succeeded")["response_body"]) == []
    assert byb.investigation_job_errors(_job_with_portfolio()) == []


def test_a_null_portfolio_is_refused_the_member_is_left_out_instead():
    job = _job_with_portfolio()
    job["portfolio"] = None
    assert byb.investigation_job_errors(job) != []


def test_a_job_portfolio_that_is_not_the_one_the_result_names_is_refused():
    job = _job_with_portfolio()
    job["portfolio"]["portfolio_id"] = "pf-robert-custom-0123456789ab"
    assert any("result.portfolio_id differs" in error for error in byb.investigation_job_errors(job))


def test_a_job_portfolio_of_another_persona_is_refused():
    job = _job_with_portfolio()
    job["portfolio"]["persona_id"] = "mateo"
    assert any("portfolio.persona_id differs" in error for error in byb.investigation_job_errors(job))


def test_a_job_portfolio_whose_weights_do_not_total_one_is_refused():
    job = _job_with_portfolio()
    job["portfolio"]["cash_weight"] += 0.05
    assert any(error.startswith("portfolio: ") and "must equal 1" in error for error in byb.investigation_job_errors(job))


def test_custom_portfolio_request_member_is_optional_and_refuses_shorting_and_extra_members():
    ref = "api.schema.json#/$defs/check_request"
    body = copy.deepcopy(_load("check_robert_preview")["request_body"])
    assert byb.schema_errors(body, ref) == []
    for custom in (None, {"cash_weight": 0.5, "positions": [{"instrument_id": "SPY", "weight": 0.5}]}, {"cash_weight": 1, "positions": []}):
        assert byb.schema_errors(dict(body, custom_portfolio=custom), ref) == [], custom
    for custom in ({"cash_weight": 0.5, "positions": [{"instrument_id": "SPY", "weight": -0.5}]},
                   {"cash_weight": 0.5, "positions": [{"instrument_id": "SPY", "weight": 0}]},
                   {"cash_weight": 1.5, "positions": []},
                   {"cash_weight": 0.5, "positions": [{"instrument_id": "SPY", "weight": 0.5}], "portfolio_id": "pf-x"},
                   {"cash_weight": 0.5}):
        assert byb.schema_errors(dict(body, custom_portfolio=custom), ref) != [], custom


def test_bounds_of_a_breaching_subject_and_of_the_exposure_table_are_not_capped_at_one():
    assert byb.schema_errors({"subject_kind": "ISSUER", "subject_id": "NVIDIA", "lower": 0.15, "upper": 1.05},
                             "check_result.schema.json#/$defs/breaching_subject") == []
    assert byb.schema_errors({"direct": 0.15, "indirect_by_fund": [], "lower": 0.15, "upper": 1.05},
                             "check_result.schema.json#/$defs/exposure_breakdown") == []
    assert byb.schema_errors({"direct": 0.15, "indirect_by_fund": [], "lower": -0.1, "upper": 1.05},
                             "check_result.schema.json#/$defs/exposure_breakdown") != []
