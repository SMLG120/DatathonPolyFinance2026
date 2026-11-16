"""Which candidate rules cannot all hold together (standard library only).

The compiler hands over every rule it would draft directly, after corrections, exceptions and ellipses are settled,
plus one node per PERMISSION clause ("No limit per company"). Deterministic predicates over those candidates and the
snapshot's sector labels, united with the model's own conflict claims, give groups. The compiler then drafts none of
a group's rules and asks one question instead: two rules that cannot both be satisfied are never both PROPOSED.

Only what the rule parameters prove is a predicate here. A wish that merely pulls against another ("growth" and
"safety", the model's TENSION) is not a conflict and is never reported as one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

EACH = "EACH"  # the subject of an any-company cap, and of a permission about every company
LOSS = "LOSS"  # the subject of a loss budget, and of a permission about losses
# Model conflict kinds that are conflicts. TENSION is logged by the caller only; an honoured CORRECTION never gets here.
MODEL_KINDS = ("DIRECT_CONTRADICTION", "INFEASIBLE_TOGETHER", "CORRECTION")
_EPSILON = 1e-12


@dataclass(frozen=True)
class Candidate:
    """One node: a rule the compiler would draft (``rule_type`` set) or a PERMISSION clause (``rule_type`` None and
    ``permission`` = its subject: ``EACH``, ``LOSS`` or a frozenset of issuer ids)."""

    index: int
    clause_id: str
    rule_type: str | None
    parameters: dict[str, Any]
    threshold: float | None = None
    permission: str | frozenset[str] | None = None


@dataclass(frozen=True)
class ConflictGroup:
    members: tuple[Candidate, ...]  # in candidate order
    reasons: tuple[str, ...]  # predicate codes, for the log


def rule_subject(rule_type: str, parameters: dict[str, Any]) -> str | frozenset[str] | None:
    """What a rule is about, in the terms a permission is compared with."""
    if rule_type == "max_issuer_exposure":
        scope = parameters.get("issuer_scope")
        return EACH if scope == "any" else frozenset({scope})
    if rule_type == "min_issuer_exposure":
        return frozenset({parameters.get("issuer_id")})
    if rule_type == "scenario_loss_budget":
        return LOSS
    if rule_type == "exclusion" and parameters.get("definition", {}).get("kind") == "named_issuers":
        return frozenset(parameters["definition"]["issuer_ids"])
    return None


def _excluded_ids(candidate: Candidate) -> frozenset[str]:
    definition = candidate.parameters.get("definition", {})
    return frozenset(definition.get("issuer_ids", ())) if definition.get("kind") == "named_issuers" else frozenset()


def _excluded_sector(candidate: Candidate) -> str | None:
    definition = candidate.parameters.get("definition", {})
    return definition.get("sector") if definition.get("kind") == "fund_reported_sector" else None


def _pair_reason(minimum: Candidate, other: Candidate, sector_of: dict[str, str]) -> str | None:
    """Why a minimum on one company cannot hold together with ``other``, or None."""
    issuer = minimum.parameters.get("issuer_id")
    if other.rule_type == "exclusion":
        if issuer in _excluded_ids(other):
            return "MIN_VS_NAMED_EXCLUSION"
        sector = _excluded_sector(other)
        if sector is not None and sector_of.get(issuer) == sector:
            return "MIN_VS_SECTOR_EXCLUSION"
    if other.rule_type == "max_issuer_exposure" and minimum.threshold is not None and other.threshold is not None:
        scope = other.parameters.get("issuer_scope")
        if scope in (issuer, "any") and minimum.threshold > other.threshold + _EPSILON:
            return "MIN_ABOVE_MAX" if scope == issuer else "MIN_ABOVE_ANY_CAP"
    return None


def _permission_reason(permission: Candidate, rule: Candidate) -> str | None:
    """A permission ("No limit per company", "I don't mind Exxon") against a limit or exclusion on the same subject."""
    if rule.rule_type in (None, "min_issuer_exposure"):
        return None  # allowing more is compatible with a minimum
    subject = rule_subject(rule.rule_type, rule.parameters)
    return "PERMISSION_VS_RULE" if subject is not None and subject == permission.permission else None


class _UnionFind:
    def __init__(self, size: int) -> None:
        self.parent = list(range(size))

    def find(self, node: int) -> int:
        while self.parent[node] != node:
            self.parent[node] = self.parent[self.parent[node]]
            node = self.parent[node]
        return node

    def union(self, a: int, b: int) -> None:
        self.parent[self.find(a)] = self.find(b)


def find_conflicts(candidates: list[Candidate], sector_of: dict[str, str],
                   model_conflicts: Iterable[tuple[str, str, str]] = ()) -> list[ConflictGroup]:
    """Groups of candidates that cannot all hold, each with at least one rule. ``sector_of`` is
    ``_Reference.sector_of``; ``model_conflicts`` are ``(clause a, clause b, kind)`` claims from the reading."""
    links: list[tuple[int, int, str]] = []
    for i, a in enumerate(candidates):
        for j in range(i + 1, len(candidates)):
            b = candidates[j]
            if a.clause_id == b.clause_id:
                continue  # one clause's own rules (the exclusions of an 'only' wish) never conflict with each other
            reason = None
            for first, second in ((a, b), (b, a)):
                if reason is None and first.rule_type == "min_issuer_exposure":
                    reason = _pair_reason(first, second, sector_of)
                if reason is None and first.rule_type is None:
                    reason = _permission_reason(first, second)
            if reason is not None:
                links.append((i, j, reason))
    minimums = [i for i, c in enumerate(candidates) if c.rule_type == "min_issuer_exposure" and c.threshold is not None]
    if sum(candidates[i].threshold for i in minimums) > 1.0 + _EPSILON:  # type: ignore[misc]
        links.extend((minimums[0], i, "MINIMUMS_OVER_100") for i in minimums[1:])
    for a_id, b_id, kind in model_conflicts:
        if kind not in MODEL_KINDS:
            continue
        side_a = [i for i, c in enumerate(candidates) if c.clause_id == a_id]
        side_b = [i for i, c in enumerate(candidates) if c.clause_id == b_id]
        links.extend((i, j, f"MODEL_{kind}") for i in side_a for j in side_b)

    groups = _UnionFind(len(candidates))
    for i, j, _ in links:
        groups.union(i, j)
    found: dict[int, list[int]] = {}
    reasons: dict[int, list[str]] = {}
    for i, j, reason in links:
        root = groups.find(i)
        reasons.setdefault(root, [])
        if reason not in reasons[root]:
            reasons[root].append(reason)
    for i in range(len(candidates)):
        root = groups.find(i)
        if root in reasons:
            found.setdefault(root, []).append(i)
    return [ConflictGroup(tuple(candidates[i] for i in members), tuple(reasons[root]))
            for root, members in sorted(found.items(), key=lambda item: item[1][0])
            if any(candidates[i].rule_type is not None for i in members)]
