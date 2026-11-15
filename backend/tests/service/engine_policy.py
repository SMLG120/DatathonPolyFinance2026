"""A stored policy built the way the service builds it, for tests that call the engine directly."""

from __future__ import annotations

from typing import Any

from backend.common.policy_ops import build_confirmed_version
from service_fakes import confirm_body


def confirmed_policy(persona_id: str, **rule_changes: Any) -> dict[str, Any]:
    body = confirm_body(persona_id)
    for confirmation in body["confirmations"]:
        confirmation["rule"].update(rule_changes)
    return build_confirmed_version(request=body, base=None, policy_id=f"pol-{persona_id}-test", new_version=1, now_iso="2026-11-14T15:00:00.000Z")
