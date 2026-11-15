"""Subset match between an engine fixture's ``expected`` block and a full check_result.

The fixtures in contracts/fixtures/engine assert only what was calculated by
hand, so ``expected`` is a PARTIAL check_result. This is the one definition of
"the engine output matches the fixture" (contracts/SEMANTICS.md section 12):

    from byb_contracts import subset_mismatches
    assert subset_mismatches(case["expected"], engine_output) == []

Rules
- object: every key in ``expected`` must exist in ``actual`` and match; extra
  keys in ``actual`` are ignored.
- number: equal within 1e-9 (a bool is never a number).
- array of objects: same length; items are paired by the first id key they all
  carry (rule_id, issuer_id, fund_id, instrument_id, subject_id, evidence_id,
  objective_id), otherwise by position. Arrays listed in ORDERED_ARRAYS must
  also be in the same order.
- array of scalars: same items, order ignored.
- anything else (strings, booleans, null): equal.
"""

from __future__ import annotations

from typing import Any

from .constants import EPS

ID_KEYS = ("rule_id", "issuer_id", "fund_id", "instrument_id", "subject_id", "evidence_id", "objective_id")
ORDERED_ARRAYS = ("rule_results", "rules_not_evaluated", "starting_portfolio_findings", "conflicts")


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def subset_mismatches(expected: Any, actual: Any, path: str = "expected", tolerance: float = EPS) -> list[str]:
    """Return a list of human-readable mismatches; an empty list means ``actual`` satisfies ``expected``."""
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return [f"{path}: expected an object, got {actual!r}"]
        problems: list[str] = []
        for key, value in expected.items():
            if key not in actual:
                problems.append(f"{path}.{key}: missing from the output")
            else:
                problems.extend(subset_mismatches(value, actual[key], f"{path}.{key}", tolerance))
        return problems
    if isinstance(expected, list):
        if not isinstance(actual, list):
            return [f"{path}: expected an array, got {actual!r}"]
        if len(expected) != len(actual):
            return [f"{path}: expected {len(expected)} item(s), got {len(actual)}"]
        if expected and all(isinstance(item, dict) for item in expected):
            return _match_objects(expected, actual, path, tolerance)
        if any(isinstance(item, (dict, list)) for item in expected):
            problems = []
            for i, (want, got) in enumerate(zip(expected, actual)):
                problems.extend(subset_mismatches(want, got, f"{path}[{i}]", tolerance))
            return problems
        remaining = list(actual)
        problems = []
        for want in expected:
            for i, got in enumerate(remaining):
                if not subset_mismatches(want, got, path, tolerance):
                    del remaining[i]
                    break
            else:
                problems.append(f"{path}: {want!r} is missing from {actual!r}")
        return problems
    if _is_number(expected):
        if not _is_number(actual) or abs(expected - actual) > tolerance:
            return [f"{path}: expected {expected!r}, got {actual!r}"]
        return []
    if expected != actual or type(expected) is not type(actual):
        return [f"{path}: expected {expected!r}, got {actual!r}"]
    return []


def _match_objects(expected: list, actual: list, path: str, tolerance: float) -> list[str]:
    name = path.rsplit(".", 1)[-1]
    key = next((k for k in ID_KEYS if all(k in item for item in expected)), None)
    if key is None or name in ORDERED_ARRAYS:
        problems = []
        for i, (want, got) in enumerate(zip(expected, actual)):
            label = f"{path}[{i}]" if key is None else f"{path}[{key}={want[key]}]"
            problems.extend(subset_mismatches(want, got, label, tolerance))
        return problems
    by_key = {}
    for item in actual:
        if isinstance(item, dict) and key in item:
            by_key[item[key]] = item
    problems = []
    for want in expected:
        label = f"{path}[{key}={want[key]}]"
        if want[key] not in by_key:
            problems.append(f"{label}: missing from the output")
        else:
            problems.extend(subset_mismatches(want, by_key[want[key]], label, tolerance))
    return problems


__all__ = ["ID_KEYS", "ORDERED_ARRAYS", "subset_mismatches"]
