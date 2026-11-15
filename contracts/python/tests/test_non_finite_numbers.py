"""Non-finite numbers (NaN, +Infinity, -Infinity) are invalid input everywhere (SEMANTICS section 1).

Regression tests for the false PASS reported as F-01 / F-05 / F-06: a NaN position weight used to pass
``validate_portfolio`` because every comparison with NaN is False, so the range checks and the
"weights add up to 1" check all let it through. The engine then dropped the position.

Every validator entry point must reject a non-finite float anywhere in the document with a
``ContractError`` whose message names the JSON path.
"""

from __future__ import annotations

import copy
import json
import math

import pytest

import byb_contracts as byb
from fixture_lib import max_issuer, policy, portfolio, purchase
from paths import API, ENGINE, SCENARIO_DIR, load

NAN, INF, NEG_INF = float("nan"), float("inf"), float("-inf")
NON_FINITE = [pytest.param(NAN, id="nan"), pytest.param(INF, id="+inf"), pytest.param(NEG_INF, id="-inf")]


def _universe():
    return load(ENGINE / "synthetic_universe.json")


def _e01():
    return load(ENGINE / "E01.json")["inputs"]


def _check_request():
    return load(API / "check_robert_preview.json")["request_body"]


def _result():
    return load(API / "investigation_robert_succeeded.json")["response_body"]["result"]


def _policy_unhashed(document):
    """validate_policy without the hash comparison: the number itself must be what is rejected."""
    byb.validate_policy(document, check_hash=False)


def _set(document, path, value):
    node = document
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value


# label -> (how to get a valid document, validator, path to poison as keys, the same path as it must appear in the message)
TARGETS = {
    "position weight": (lambda: _e01()["portfolio"], byb.validate_portfolio, ["positions", 0, "weight"], "positions[0].weight"),
    "cash weight": (lambda: _e01()["portfolio"], byb.validate_portfolio, ["cash_weight"], "cash_weight"),
    "purchase target weight": (lambda: _e01()["purchase_request"], byb.validate_purchase_request, ["target_direct_weight"], "target_direct_weight"),
    "rule threshold": (lambda: _e01()["policy"]["rules"][0], byb.validate_rule, ["threshold"], "threshold"),
    "policy rule threshold": (lambda: _e01()["policy"], byb.validate_policy, ["rules", 0, "threshold"], "rules[0].threshold"),
    "policy rule threshold (no hash check)": (lambda: _e01()["policy"], _policy_unhashed, ["rules", 0, "threshold"], "rules[0].threshold"),
    "draft-rule threshold": (
        _check_request, lambda body: byb.validate_against("api.schema.json#/$defs/check_request", body),
        ["draft_rules", 0, "threshold"], "draft_rules[0].threshold"),
    "check request target weight": (
        _check_request, lambda body: byb.validate_api_body("api.schema.json#/$defs/check_request", body),
        ["purchase_request", "target_direct_weight"], "purchase_request.target_direct_weight"),
    "holdings row weight": (
        lambda: _universe()["holdings"], byb.validate_holdings_snapshot,
        ["funds", "FUND_A", "holdings", 0, "weight_fraction"], "funds.FUND_A.holdings[0].weight_fraction"),
    "coverage fraction": (
        lambda: _universe()["holdings"], byb.validate_holdings_snapshot,
        ["funds", "FUND_A", "coverage_fraction"], "funds.FUND_A.coverage_fraction"),
    "non-constituent weight": (
        lambda: _universe()["holdings"], byb.validate_holdings_snapshot,
        ["funds", "FUND_A", "non_constituent_weight"], "funds.FUND_A.non_constituent_weight"),
    "price": (lambda: _universe()["market_data"], byb.validate_market_data, ["prices", "SYN_A", "series", 0, 1], "prices.SYN_A.series[0][1]"),
    "FX rate": (lambda: _universe()["market_data"], byb.validate_market_data, ["fx_usdcad", 0, 1], "fx_usdcad[0][1]"),
    "scenario portfolio weight": (
        lambda: load(SCENARIO_DIR / "robert.json"), byb.validate_scenario,
        ["portfolio", "positions", 0, "weight"], "portfolio.positions[0].weight"),
    "result rule limit": (_result, byb.validate_check_result, ["rule_results", 0, "limit"], "rule_results[0].limit"),
    "result measured bound": (_result, byb.validate_check_result, ["rule_results", 0, "measured", "upper"], "rule_results[0].measured.upper"),
    "result cash after": (_result, byb.validate_check_result, ["feasibility", "cash_after"], "feasibility.cash_after"),
    "result evidence value": (_result, byb.validate_check_result, ["evidence", 0, "value"], "evidence[0].value"),
    "job result limit": (
        lambda: load(API / "investigation_robert_succeeded.json")["response_body"], byb.validate_investigation_job,
        ["result", "rule_results", 0, "limit"], "result.rule_results[0].limit"),
    # Documents without a numeric field: a non-finite float is still rejected wherever it turns up.
    "instrument name": (lambda: _universe()["instruments"], byb.validate_instrument_registry, ["instruments", "SYN_A", "name"], "instruments.SYN_A.name"),
    "controversy summary": (lambda: _universe()["controversies"], byb.validate_controversy_registry, ["records", 0, "summary"], "records[0].summary"),
    "source registry entry": (lambda: _universe()["sources"], byb.validate_source_registry, ["sources", "SYNTHETIC_FIXTURE", "title"], "sources.SYNTHETIC_FIXTURE"),
}


@pytest.mark.parametrize("label", sorted(TARGETS))
def test_the_unpoisoned_document_is_valid(label):
    build, validate, _, _ = TARGETS[label]
    validate(build())


@pytest.mark.parametrize("bad", NON_FINITE)
@pytest.mark.parametrize("label", sorted(TARGETS))
def test_a_non_finite_number_is_rejected_with_its_path(label, bad):
    build, validate, keys, shown = TARGETS[label]
    document = build()
    _set(document, keys, bad)
    with pytest.raises(byb.ContractError) as caught:
        validate(document)
    message = str(caught.value)
    assert shown in message, message
    assert "finite" in message, message


@pytest.mark.parametrize("bad", NON_FINITE)
def test_schema_errors_reports_every_non_finite_number_wherever_it_is_nested(bad):
    document = {"a": [1.0, {"b": bad}], "c": bad, "d": [[bad]]}
    errors = byb.schema_errors(document, "common.schema.json#/$defs/non_empty_string")
    assert [e.split(":")[0] for e in errors] == ["a[1].b", "c", "d[0][0]"]
    assert all("finite" in e for e in errors)
    assert byb.schema_errors(bad, "common.schema.json#/$defs/fraction")[0].startswith("$:")


@pytest.mark.parametrize("bad", NON_FINITE)
def test_a_bare_number_type_never_accepts_a_non_finite_float(bad):
    """The root cause: ``type: number`` matched any Python float."""
    from byb_contracts.schema import _type_ok
    assert _type_ok(bad, "number") is False
    assert _type_ok(bad, "integer") is False
    assert _type_ok(1.5, "number") and _type_ok(0, "number") and _type_ok(2.0, "integer")


# ------------------------------------------------------------------------------------ the reported false PASS

def false_pass_inputs():
    """F-01: ISS_B was meant to be 20% of the portfolio (cap 10%) but the weight arrives as NaN.

    Before the fix ``validate_portfolio`` accepted this document, the engine skipped the position
    (``NaN > 0`` is False) and answered PASS / ALL_PASS with a SUPPORTED maximum.
    """
    return {
        "portfolio": portfolio("pf-f01", "synthetic_test", 0.75, {"SYN_B1": NAN, "SYN_A": 0.05}),
        "policy": policy("pol-f01", "synthetic_test", 1, [
            max_issuer("f01-max", 0.10, status="CONFIRMED", origin="FICTIONAL_SCENARIO", words="Synthetic test rule.")]),
        "purchase_request": purchase("SYN_A", 0.08),
    }


def test_the_false_pass_portfolio_is_rejected_by_the_validator():
    inputs = false_pass_inputs()
    byb.validate_policy(inputs["policy"])
    byb.validate_purchase_request(inputs["purchase_request"])
    assert all(p["instrument_id"] in _universe()["instruments"]["instruments"] for p in inputs["portfolio"]["positions"])
    with pytest.raises(byb.ContractError) as caught:
        byb.validate_portfolio(inputs["portfolio"])
    assert "positions[0].weight" in str(caught.value) and "finite" in str(caught.value)
    # the same document with the intended weight is a valid portfolio, so NaN is the only defect
    inputs["portfolio"]["positions"][0]["weight"] = 0.20
    byb.validate_portfolio(inputs["portfolio"])


# ------------------------------------------------------------------------------------ weights: range and sum

def _portfolio(cash, **positions):
    return portfolio("pf-w", "synthetic_test", cash, positions)


@pytest.mark.parametrize("document, fragment", [
    pytest.param(_portfolio(1.1, SYN_A=-0.1), "positions[0].weight", id="negative position weight"),
    pytest.param(_portfolio(1.0, SYN_A=0.0), "positions[0].weight", id="zero position weight (a held position is positive)"),
    pytest.param(_portfolio(1.0, SYN_A=-0.0), "positions[0].weight", id="-0.0 position weight equals zero"),
    pytest.param(_portfolio(0.0, SYN_A=1.5), "positions[0].weight", id="position weight above 1"),
    pytest.param(_portfolio(-0.2, SYN_A=0.6, SYN_C=0.6), "cash_weight", id="negative cash weight"),
    pytest.param(_portfolio(1.5, SYN_A=0.5), "cash_weight", id="cash weight above 1"),
    pytest.param(_portfolio(0.5, SYN_A=0.4), "must equal 1", id="weights sum to 0.9"),
    pytest.param(_portfolio(0.5, SYN_A=0.5, SYN_C=0.1), "must equal 1", id="weights sum to 1.1"),
    pytest.param(_portfolio(0.5, SYN_A=0.5 + 1e-6), "must equal 1", id="sum off by more than EPS"),
    pytest.param(_portfolio(True, SYN_A=1e-12), "cash_weight", id="bool cash weight is not the number 1"),
    pytest.param(_portfolio(0.0, SYN_A=True), "positions[0].weight", id="bool position weight is not the number 1"),
    pytest.param(_portfolio("0.5", SYN_A=0.5), "cash_weight", id="numeric string cash weight"),
    pytest.param(_portfolio(0.5, SYN_A="0.5"), "positions[0].weight", id="numeric string position weight"),
    pytest.param(_portfolio(None, SYN_A=1.0), "cash_weight", id="null cash weight"),
])
def test_bad_weights_are_rejected(document, fragment):
    with pytest.raises(byb.ContractError) as caught:
        byb.validate_portfolio(document)
    assert fragment in str(caught.value)


@pytest.mark.parametrize("document", [
    pytest.param(_portfolio(-0.0, SYN_A=1.0), id="-0.0 cash weight is zero (IEEE-754: -0.0 == 0.0), inside [0, 1]"),
    pytest.param(_portfolio(1.0, SYN_A=5e-324), id="smallest denormal position weight: finite, positive, sum within EPS"),
    pytest.param(_portfolio(5e-324, SYN_A=1.0), id="smallest denormal cash weight"),
    pytest.param(_portfolio(0.5, SYN_A=0.5 + 5e-10), id="sum within EPS = 1e-9"),
    pytest.param(_portfolio(1, ), id="integer 1 is a number"),
])
def test_finite_edge_weights_are_accepted(document):
    """SEMANTICS section 1: every number is a finite double and equality is within EPS, nothing stricter."""
    byb.validate_portfolio(document)


def test_the_sum_check_cannot_be_passed_by_nan():
    """Even if a NaN reached the arithmetic, 'abs(total - 1) > EPS' being False must not mean valid."""
    from byb_contracts.validators import _weights_add_up
    assert _weights_add_up(1.0) and _weights_add_up(1.0 + 5e-10)
    assert not _weights_add_up(NAN) and not _weights_add_up(INF) and not _weights_add_up(0.9)


@pytest.mark.parametrize("bad, fragment", [(True, "boolean"), ("0.1", "str"), ("10%", "str")])
@pytest.mark.parametrize("label", ["purchase target weight", "rule threshold", "holdings row weight", "price", "FX rate"])
def test_a_bool_or_a_numeric_string_is_not_a_number(label, bad, fragment):
    build, validate, keys, shown = TARGETS[label]
    document = build()
    _set(document, keys, bad)
    with pytest.raises(byb.ContractError) as caught:
        validate(document)
    assert shown in str(caught.value)


@pytest.mark.parametrize("threshold", [-0.01, 1.01])
def test_a_threshold_outside_0_1_is_rejected(threshold):
    rule = _e01()["policy"]["rules"][0]
    rule["threshold"] = threshold
    with pytest.raises(byb.ContractError, match="threshold"):
        byb.validate_rule(rule)


@pytest.mark.parametrize("target", [-0.1, 1.5])
def test_a_finite_target_outside_0_1_stays_the_engine_s_invalid_request(target):
    """SEMANTICS section 4 (D5): TARGET_NEGATIVE / TARGET_ABOVE_ONE are execution codes, not contract errors.

    Only a non-finite target is a contract error: there is no result document that could carry it.
    """
    byb.validate_purchase_request(purchase("SYN_A", target))


# ------------------------------------------------------------------------------------ JSON boundary

@pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity"])
def test_a_document_parsed_from_a_non_standard_json_token_is_rejected(token):
    """Python's json.loads accepts these tokens by default; the validator is the second line of defence."""
    text = json.dumps(_e01()["portfolio"]).replace('"cash_weight": 0.5', f'"cash_weight": {token}')
    document = json.loads(text)
    assert not math.isfinite(document["cash_weight"])
    with pytest.raises(byb.ContractError, match="cash_weight"):
        byb.validate_portfolio(document)


@pytest.mark.parametrize("bad", NON_FINITE)
def test_canonical_json_and_the_content_hash_refuse_non_finite_numbers(bad):
    with pytest.raises(ValueError):
        byb.canonical_json({"threshold": bad})
    broken = copy.deepcopy(_e01()["policy"])
    broken["rules"][0]["threshold"] = bad
    with pytest.raises(ValueError):
        byb.compute_content_hash(broken)


@pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity"])
def test_the_schema_loader_refuses_non_standard_json_tokens(token, tmp_path, monkeypatch):
    from byb_contracts import schema
    (tmp_path / "bad.schema.json").write_text('{"type": "number", "minimum": %s}' % token, encoding="utf-8")
    monkeypatch.setenv("BYB_SCHEMA_DIR", str(tmp_path))
    schema.load_schema.cache_clear()
    try:
        with pytest.raises(ValueError, match=token.lstrip("-")):
            schema.load_schema("bad.schema.json")
    finally:
        monkeypatch.undo()
        schema.load_schema.cache_clear()
