"""Thin call wrappers around the engine under test (no logic of their own)."""

from __future__ import annotations

import copy
import math
from typing import Any, Optional

from backend.engine import check_rules
from byb_contracts import check_result_errors

from . import universe as U


def check(portfolio: dict, rules_or_policy: Any, request: dict, data: Optional[dict] = None, *, preview: bool = False,
          validate: bool = True, **kwargs: Any) -> dict:
    """Run ``check_rules``. ``rules_or_policy`` is a policy dict or a list of rules (wrapped into a policy,
    or sent as draft rules when ``preview`` is true). The output must always satisfy the result contract."""
    data = data or U.universe()
    if preview:
        policy, extra = None, {"draft_rules": rules_or_policy}
    else:
        policy = rules_or_policy if isinstance(rules_or_policy, dict) else U.policy(rules_or_policy)
        extra = {}
    result = check_rules(portfolio, policy, request, data["instruments"], data["holdings"], data["market_data"],
                         data["controversies"], **extra, **kwargs)
    if validate:
        errors = check_result_errors(result)
        assert errors == [], f"engine output violates check_result contract: {errors[:5]}"
    return result


def by_rule(result: dict) -> dict[str, dict]:
    return {entry["rule_id"]: entry for entry in result["rule_results"]}


def close(a: Optional[float], b: Optional[float], tol: float = 1e-12) -> bool:
    if a is None or b is None:
        return a is b
    return math.isclose(float(a), float(b), rel_tol=0.0, abs_tol=tol)


def frozen(value: Any) -> Any:
    return copy.deepcopy(value)
