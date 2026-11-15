"""Canonical derivations that every component must share. Standard library only.

These are the definitions referred to by contracts/SEMANTICS.md. The engine,
the API and the validators call these functions instead of re-deriving the
values, so a summary can never disagree with the per-rule results.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable, Optional

from .constants import EPS, MAX_TYPE_RULES, MIN_TYPE_RULES


def canonical_json(value: Any) -> bytes:
    """Canonical JSON used for hashing: sorted keys, no spaces, UTF-8."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def compute_content_hash(policy: dict) -> str:
    """'sha256:' + SHA-256 of the canonical JSON of the policy without its ``content_hash``."""
    body = {key: value for key, value in policy.items() if key != "content_hash"}
    return "sha256:" + hashlib.sha256(canonical_json(body)).hexdigest()


def rule_is_evaluated(rule: dict, preview: bool = False) -> bool:
    """Only CONFIRMED rules with a number are evaluated (LEAD_DECISIONS D3).

    In a preview (POST /check with draft_rules) every draft with a number that
    is not SUPERSEDED is evaluated, and the result is labelled a preview.
    """
    if rule.get("threshold") is None:
        return False
    if preview:
        return rule.get("status") in ("PROPOSED", "CONFIRMED")
    return rule.get("status") == "CONFIRMED"


def status_from_bounds(rule_type: str, lower: Optional[float], upper: Optional[float], limit: float) -> str:
    """PASS / FAIL / UNKNOWN from interval bounds (LEAD_DECISIONS D4, tolerance D2).

    Max-type rules (and the loss budget): PASS if upper <= limit, FAIL if
    lower > limit, else UNKNOWN. Min-type rules: PASS if lower >= limit, FAIL
    if upper < limit, else UNKNOWN. Missing bounds are UNKNOWN.
    """
    if lower is None or upper is None:
        return "UNKNOWN"
    if rule_type in MAX_TYPE_RULES:
        if upper <= limit + EPS:
            return "PASS"
        if lower > limit + EPS:
            return "FAIL"
        return "UNKNOWN"
    if rule_type in MIN_TYPE_RULES:
        if lower >= limit - EPS:
            return "PASS"
        if upper < limit - EPS:
            return "FAIL"
        return "UNKNOWN"
    raise ValueError(f"unknown rule_type {rule_type!r}")


def gap_from_bounds(rule_type: str, status: str, lower: Optional[float], upper: Optional[float], limit: float) -> Optional[float]:
    """Positive = amount of breach, zero or negative = headroom, None when UNKNOWN."""
    if status == "UNKNOWN" or lower is None or upper is None:
        return None
    if rule_type in MAX_TYPE_RULES:
        return (lower - limit) if status == "FAIL" else (upper - limit)
    return (limit - upper) if status == "FAIL" else (limit - lower)


def feasibility_status(cash_after: float) -> str:
    return "INSUFFICIENT_CASH" if cash_after < -EPS else "FEASIBLE"


def coverage_status(has_holdings_file: bool, coverage_fraction: float) -> str:
    if not has_holdings_file:
        return "MISSING"
    return "COVERED" if coverage_fraction >= 1 - EPS else "PARTIAL"


def derive_headline(execution_status: str, consistency_status: str, rule_statuses: Iterable[str]) -> str:
    """First match wins. See contracts/SEMANTICS.md section 9."""
    statuses = list(rule_statuses)
    if execution_status == "ERROR":
        return "EXECUTION_ERROR"
    if execution_status == "INVALID_REQUEST":
        return "INVALID_REQUEST"
    if consistency_status == "PROVEN_CONFLICT":
        return "POLICY_CONFLICT"
    if not statuses:
        return "NO_RULES_EVALUATED"
    if "FAIL" in statuses:
        return "HAS_FAIL"
    if "UNKNOWN" in statuses:
        return "NO_FAIL_BUT_UNKNOWN"
    return "ALL_PASS"


def derive_summary(result: dict) -> dict:
    """Build ``check_result.summary`` from the rest of the result. Never author it by hand."""
    statuses = [entry["status"] for entry in result.get("rule_results", [])]
    feasibility = result.get("feasibility")
    return {
        "headline": derive_headline(result["execution"]["status"], result["policy_consistency"]["status"], statuses),
        "counts": {
            "pass": statuses.count("PASS"),
            "fail": statuses.count("FAIL"),
            "unknown": statuses.count("UNKNOWN"),
        },
        "rules_evaluated": len(statuses),
        "rules_not_evaluated": len(result.get("rules_not_evaluated", [])),
        "starting_portfolio_breaches": len(result.get("starting_portfolio_findings", [])),
        "feasibility_status": feasibility["status"] if feasibility else None,
    }
