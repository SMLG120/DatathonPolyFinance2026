"""Broken documents must be rejected. Standard library only.

Two families (see negative_examples.py): documents with a broken shape, which
the schema interpreter must reject, and documents with a valid shape that
break a rule a schema cannot express, which the validate_* functions must
reject with a clear message.
"""

from __future__ import annotations

import copy

import pytest

import byb_contracts as byb
from negative_examples import SCHEMA_NEGATIVES, SEMANTIC_NEGATIVES, valid_documents

VALID = valid_documents()


@pytest.mark.parametrize("label", sorted(VALID))
def test_valid_document_is_accepted(label):
    ref, document = VALID[label]
    assert byb.schema_errors(document, ref) == []


@pytest.mark.parametrize("label,base,mutate", SCHEMA_NEGATIVES, ids=[n[0] for n in SCHEMA_NEGATIVES])
def test_broken_shape_is_rejected(label, base, mutate):
    ref, document = VALID[base]
    broken = copy.deepcopy(document)
    mutate(broken)
    assert broken != document, "the mutation changed nothing"
    assert byb.schema_errors(broken, ref) != []


@pytest.mark.parametrize("label,base,mutate,errors_of,fragment", SEMANTIC_NEGATIVES, ids=[n[0] for n in SEMANTIC_NEGATIVES])
def test_broken_rule_is_rejected_with_a_clear_message(label, base, mutate, errors_of, fragment):
    ref, document = VALID[base]
    assert errors_of(copy.deepcopy(document)) == [], "the unbroken document must be accepted"
    broken = copy.deepcopy(document)
    mutate(broken)
    assert byb.schema_errors(broken, ref) == [], "the shape must stay valid: this case is about a semantic rule"
    errors = errors_of(broken)
    assert any(fragment in error for error in errors), f"expected a message containing {fragment!r}, got {errors}"


def test_validate_functions_raise_contract_error_listing_every_issue():
    ref, portfolio = VALID["portfolio"]
    broken = copy.deepcopy(portfolio)
    broken["cash_weight"] = 30
    broken["positions"][0]["weight"] = "a lot"
    with pytest.raises(byb.ContractError) as caught:
        byb.validate_portfolio(broken)
    assert len(caught.value.errors) == 2
    message = str(caught.value)
    assert "portfolio is invalid (2 issue(s))" in message and "cash_weight" in message and "positions[0].weight" in message


def test_a_confirmed_rule_needs_a_number_and_a_system_proposal_has_none():
    confirmed = copy.deepcopy(VALID["rule_confirmed"][1])
    byb.validate_rule(confirmed)
    confirmed.update(threshold=None, threshold_source=None)
    with pytest.raises(byb.ContractError):
        byb.validate_rule(confirmed)
    proposal = copy.deepcopy(VALID["rule_system_proposed"][1])
    byb.validate_rule(proposal)
    assert proposal["threshold"] is None and proposal["origin"] == "SYSTEM_PROPOSED"
    proposal["threshold"] = 0.10
    with pytest.raises(byb.ContractError):
        byb.validate_rule(proposal)


def test_only_confirmed_rules_with_a_number_are_evaluated():
    confirmed, superseded = VALID["rule_confirmed"][1], VALID["rule_superseded"][1]
    proposal, draft = VALID["rule_system_proposed"][1], VALID["rule_user_words"][1]
    assert byb.rule_is_evaluated(confirmed) and not byb.rule_is_evaluated(superseded)
    assert not byb.rule_is_evaluated(proposal) and not byb.rule_is_evaluated(draft)
    assert byb.rule_is_evaluated(draft, preview=True), "a draft with a number is evaluated in a preview only"
    assert not byb.rule_is_evaluated(proposal, preview=True) and not byb.rule_is_evaluated(superseded, preview=True)


def test_status_and_gap_follow_the_interval_rules():
    # LEAD_DECISIONS D4, tolerance 1e-9 (D2).
    assert byb.status_from_bounds("max_issuer_exposure", 0.25, 0.25, 0.25) == "PASS"
    assert byb.status_from_bounds("max_issuer_exposure", 0.25 + 5e-10, 0.25 + 5e-10, 0.25) == "PASS"
    assert byb.status_from_bounds("max_issuer_exposure", 0.2500001, 0.2500001, 0.25) == "FAIL"
    assert byb.status_from_bounds("max_issuer_exposure", 0.22, 0.38, 0.30) == "UNKNOWN"
    assert byb.status_from_bounds("max_issuer_exposure", 0.34, 0.64, 0.25) == "FAIL"
    assert byb.status_from_bounds("min_issuer_exposure", 0.18, 0.18, 0.18) == "PASS"
    assert byb.status_from_bounds("min_issuer_exposure", 0.18, 0.18, 0.20) == "FAIL"
    assert byb.status_from_bounds("min_issuer_exposure", 0.18, 0.30, 0.20) == "UNKNOWN"
    assert byb.status_from_bounds("scenario_loss_budget", None, None, 0.10) == "UNKNOWN"
    assert byb.gap_from_bounds("max_issuer_exposure", "FAIL", 0.34, 0.64, 0.25) == pytest.approx(0.09, abs=1e-12)
    assert byb.gap_from_bounds("max_issuer_exposure", "PASS", 0.262, 0.264, 0.30) == pytest.approx(-0.036, abs=1e-12)
    assert byb.gap_from_bounds("min_issuer_exposure", "FAIL", 0.18, 0.18, 0.20) == pytest.approx(0.02, abs=1e-12)
    assert byb.gap_from_bounds("min_issuer_exposure", "PASS", 0.23, 0.23, 0.20) == pytest.approx(-0.03, abs=1e-12)
    assert byb.gap_from_bounds("max_issuer_exposure", "UNKNOWN", 0.22, 0.38, 0.30) is None


def test_headline_order_of_precedence():
    assert byb.derive_headline("ERROR", "NOT_ASSESSED", []) == "EXECUTION_ERROR"
    assert byb.derive_headline("INVALID_REQUEST", "NOT_ASSESSED", []) == "INVALID_REQUEST"
    assert byb.derive_headline("OK", "PROVEN_CONFLICT", ["PASS", "FAIL"]) == "POLICY_CONFLICT"
    assert byb.derive_headline("OK", "CONSISTENT", []) == "NO_RULES_EVALUATED"
    assert byb.derive_headline("OK", "CONSISTENT", ["PASS", "UNKNOWN", "FAIL"]) == "HAS_FAIL"
    assert byb.derive_headline("OK", "CONSISTENT", ["PASS", "UNKNOWN"]) == "NO_FAIL_BUT_UNKNOWN"
    assert byb.derive_headline("OK", "CONSISTENT", ["PASS", "PASS"]) == "ALL_PASS"


def test_coverage_and_feasibility_status():
    assert byb.coverage_status(False, 0.0) == "MISSING"
    assert byb.coverage_status(True, 1.0) == "COVERED"
    assert byb.coverage_status(True, 0.99871325) == "PARTIAL"
    assert byb.feasibility_status(0.0) == "FEASIBLE" and byb.feasibility_status(-5e-10) == "FEASIBLE"
    assert byb.feasibility_status(-0.05) == "INSUFFICIENT_CASH"


def test_content_hash_is_reproducible_and_sensitive():
    policy = copy.deepcopy(VALID["policy"][1])
    assert policy["content_hash"] == byb.compute_content_hash(policy)
    reordered = {key: policy[key] for key in reversed(list(policy))}
    assert byb.compute_content_hash(reordered) == policy["content_hash"], "key order must not matter"
    policy["rules"][1]["threshold"] = 0.31
    assert byb.compute_content_hash(policy) != policy["content_hash"]
