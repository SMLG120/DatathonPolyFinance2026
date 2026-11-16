"""Conflict predicates and grouping (backend.agents.conflicts). No network."""

from __future__ import annotations

import pytest

from backend.agents.conflicts import EACH, LOSS, Candidate, find_conflicts, rule_subject

SECTOR_OF = {"EXXON_MOBIL": "Energy", "ENBRIDGE": "Energy", "MICROSOFT": "Information Technology"}


def minimum(index, clause, issuer, threshold=None):
    return Candidate(index, clause, "min_issuer_exposure", {"issuer_id": issuer}, threshold)


def cap(index, clause, scope, threshold=None):
    return Candidate(index, clause, "max_issuer_exposure", {"issuer_scope": scope}, threshold)


def named_exclusion(index, clause, *ids):
    return Candidate(index, clause, "exclusion", {"definition": {"kind": "named_issuers", "issuer_ids": sorted(ids)}})


def sector_exclusion(index, clause, sector):
    return Candidate(index, clause, "exclusion", {"definition": {"kind": "fund_reported_sector", "sector": sector}})


def permission(index, clause, subject):
    return Candidate(index, clause, None, {}, permission=subject)


def reasons(candidates, claims=()):
    return [(tuple(m.index for m in g.members), g.reasons) for g in find_conflicts(candidates, SECTOR_OF, claims)]


@pytest.mark.parametrize("candidates, expected", [
    ([minimum(0, "c1", "EXXON_MOBIL", 0.05), named_exclusion(1, "c2", "EXXON_MOBIL", "ENBRIDGE")], "MIN_VS_NAMED_EXCLUSION"),
    ([sector_exclusion(0, "c1", "Energy"), minimum(1, "c2", "ENBRIDGE")], "MIN_VS_SECTOR_EXCLUSION"),
    ([minimum(0, "c1", "MICROSOFT", 0.10), cap(1, "c2", "MICROSOFT", 0.05)], "MIN_ABOVE_MAX"),
    ([minimum(0, "c1", "MICROSOFT", 0.12), cap(1, "c2", "any", 0.10)], "MIN_ABOVE_ANY_CAP"),
    ([permission(0, "c1", EACH), cap(1, "c2", "any", 0.10)], "PERMISSION_VS_RULE"),
    ([permission(0, "c1", frozenset({"ENBRIDGE"})), named_exclusion(1, "c2", "ENBRIDGE")], "PERMISSION_VS_RULE"),
    ([permission(0, "c1", LOSS), Candidate(1, "c2", "scenario_loss_budget", {"scenario_id": "replay_2022"}, 0.1)], "PERMISSION_VS_RULE"),
])
def test_each_predicate(candidates, expected):
    assert reasons(candidates) == [((0, 1), (expected,))]


@pytest.mark.parametrize("candidates", [
    [minimum(0, "c1", "MICROSOFT", 0.05), named_exclusion(1, "c2", "ENBRIDGE")],
    [minimum(0, "c1", "MICROSOFT"), sector_exclusion(1, "c2", "Energy")],
    [minimum(0, "c1", "MICROSOFT", 0.05), cap(1, "c2", "MICROSOFT", 0.05)],  # equal is feasible
    [minimum(0, "c1", "MICROSOFT", 0.05), cap(1, "c2", "MICROSOFT")],  # the cap's number is not known
    [minimum(0, "c1", "MICROSOFT", 0.05), cap(1, "c2", "ENBRIDGE", 0.01)],
    [permission(0, "c1", EACH), minimum(1, "c2", "MICROSOFT", 0.05)],  # allowing more is compatible with a minimum
    [permission(0, "c1", frozenset({"ENBRIDGE"})), cap(1, "c2", "any", 0.1)],
    [Candidate(0, "c1", "controversy_exclusion", {"criteria": {}}), minimum(1, "c2", "EXXON_MOBIL", 0.05)],
])
def test_compatible_rules_are_not_conflicts(candidates):
    assert reasons(candidates) == []


def test_rules_of_one_clause_never_conflict_with_each_other():
    assert reasons([minimum(0, "c1", "MICROSOFT", 0.10), cap(1, "c1", "MICROSOFT", 0.05)]) == []


def test_minimums_over_the_whole_portfolio():
    candidates = [minimum(0, "c1", "MICROSOFT", 0.6), minimum(1, "c2", "ENBRIDGE", 0.3), minimum(2, "c3", "EXXON_MOBIL", 0.2)]
    assert reasons(candidates) == [((0, 1, 2), ("MINIMUMS_OVER_100",))]
    assert reasons(candidates[:2]) == []


def test_model_claims_link_their_clauses_and_tension_is_not_a_conflict():
    candidates = [cap(0, "c1", "any", 0.1), named_exclusion(1, "c2", "ENBRIDGE")]
    assert reasons(candidates, [("c1", "c2", "TENSION")]) == []
    assert reasons(candidates, [("c1", "c2", "DIRECT_CONTRADICTION")]) == [((0, 1), ("MODEL_DIRECT_CONTRADICTION",))]
    assert reasons(candidates, [("c1", "c9", "INFEASIBLE_TOGETHER")]) == [], "a claim needs candidates on both sides"


def test_union_find_groups_transitively_and_keeps_order():
    candidates = [sector_exclusion(0, "c1", "Energy"), minimum(1, "c2", "ENBRIDGE", 0.05), cap(2, "c3", "ENBRIDGE", 0.01),
                  cap(3, "c4", "any", 0.1)]
    assert reasons(candidates) == [((0, 1, 2), ("MIN_VS_SECTOR_EXCLUSION", "MIN_ABOVE_MAX"))]


def test_a_group_of_permissions_alone_is_not_reported():
    assert find_conflicts([permission(0, "c1", EACH), permission(1, "c2", EACH)], SECTOR_OF, [("c1", "c2", "DIRECT_CONTRADICTION")]) == []


def test_rule_subject():
    assert rule_subject("max_issuer_exposure", {"issuer_scope": "any"}) == EACH
    assert rule_subject("max_issuer_exposure", {"issuer_scope": "ENBRIDGE"}) == frozenset({"ENBRIDGE"})
    assert rule_subject("exclusion", {"definition": {"kind": "fund_reported_sector", "sector": "Energy"}}) is None
    assert rule_subject("scenario_loss_budget", {"scenario_id": "replay_2022"}) == LOSS
