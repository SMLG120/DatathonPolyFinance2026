"""Building a new immutable policy version (contracts/api.md sections 4 and 8).

Pure functions: no storage, no clock. The caller supplies the time and stores the result.
The server writes the stored rule; nothing the client sends can mark a rule CONFIRMED by itself.
"""

from __future__ import annotations

import copy
import hashlib
from typing import Any

from byb_contracts import SCHEMA_VERSION, compute_content_hash, policy_errors
from byb_contracts.templates import scope_description

CONFIRMED_BY = "demo_user"


class InvalidConfirmation(Exception):
    """422 INVALID_CONFIRMATION / UNSUPPORTED_CHALLENGE. ``path`` points into the request body."""

    def __init__(self, path: str, issue: str) -> None:
        super().__init__(issue)
        self.path, self.issue = path, issue


def _confirmed_rule(submitted: dict, threshold: float, now_iso: str) -> dict:
    """Server rule 3: status, confirmation stamp and provenance are written here."""
    rule = copy.deepcopy(submitted)
    same_number = submitted.get("threshold") is not None and submitted["threshold"] == threshold
    if submitted["origin"] == "FICTIONAL_SCENARIO" and same_number:
        rule.update(origin="FICTIONAL_SCENARIO", threshold_source="FICTIONAL_SCENARIO", threshold_quote=None)
    elif submitted.get("threshold_source") == "USER_WORDS" and same_number:
        rule.update(origin="USER_STATED", threshold_source="USER_WORDS")
    else:
        rule.update(origin="USER_STATED", threshold_source="USER_ENTERED", threshold_quote=None)
    rule.update(
        threshold=threshold, status="CONFIRMED", confirmed_at=now_iso, confirmed_by=CONFIRMED_BY, superseded_by_rule_id=None,
        # The rule card text is a template of the rule's type and parameters, never client or model text.
        scope_description=scope_description(rule["rule_type"], rule["parameters"]),
    )
    return rule


def _finish(policy: dict) -> dict:
    policy["content_hash"] = compute_content_hash(policy)
    errors = policy_errors(policy)
    if errors:
        raise InvalidConfirmation("", "the resulting policy would not be valid: " + "; ".join(errors[:3]))
    return policy


def build_confirmed_version(*, request: dict, base: dict | None, policy_id: str, new_version: int, now_iso: str) -> dict:
    """The policy version that ``POST /rules/confirm`` stores. ``base`` is the latest stored version or None."""
    confirmations, withdrawn = request["confirmations"], list(request["withdraw_rule_ids"])
    if not confirmations and not withdrawn:
        raise InvalidConfirmation("confirmations", "there is neither a confirmation nor a withdrawal")
    base_rules = copy.deepcopy(base["rules"]) if base else []
    by_id = {rule["rule_id"]: rule for rule in base_rules}
    objective_ids = {objective["objective_id"] for objective in request["objectives"]}

    if len(set(withdrawn)) != len(withdrawn):
        raise InvalidConfirmation("withdraw_rule_ids", "a rule is listed twice")
    for index, rule_id in enumerate(withdrawn):
        if rule_id not in by_id or by_id[rule_id]["status"] != "CONFIRMED":
            raise InvalidConfirmation(f"withdraw_rule_ids[{index}]", f"{rule_id} is not a CONFIRMED rule of the base version")

    seen: set[str] = set()
    replacements: dict[str, dict] = {}
    appended: list[dict] = []
    for index, confirmation in enumerate(confirmations):
        where = f"confirmations[{index}].rule"
        submitted, threshold = confirmation["rule"], confirmation["threshold"]
        rule_id = submitted["rule_id"]
        if submitted["status"] != "PROPOSED":
            raise InvalidConfirmation(f"{where}.status", f"is {submitted['status']}; only a PROPOSED rule can be confirmed")
        if rule_id in seen:
            raise InvalidConfirmation(f"{where}.rule_id", f"{rule_id} appears twice in the request")
        if rule_id in by_id:
            raise InvalidConfirmation(f"{where}.rule_id", f"{rule_id} is already used in the policy; a replacement needs a new rule_id")
        seen.add(rule_id)
        if submitted["objective_id"] is not None and submitted["objective_id"] not in objective_ids:
            raise InvalidConfirmation(f"{where}.objective_id", f"{submitted['objective_id']} is not in objectives")
        stored = _confirmed_rule(submitted, threshold, now_iso)
        old_id = submitted["supersedes_rule_id"]
        if old_id is None:
            appended.append(stored)
            continue
        old = by_id.get(old_id)
        if old is None or old["status"] != "CONFIRMED":
            raise InvalidConfirmation(f"{where}.supersedes_rule_id", f"{old_id} is not a CONFIRMED rule of the base version")
        if old_id in withdrawn:
            raise InvalidConfirmation(f"{where}.supersedes_rule_id", f"{old_id} is both replaced and withdrawn")
        if old_id in replacements:
            raise InvalidConfirmation(f"{where}.supersedes_rule_id", f"{old_id} is replaced twice")
        if old["rule_type"] != submitted["rule_type"]:
            raise InvalidConfirmation(f"{where}.rule_type", f"a replacement must keep the rule type {old['rule_type']}")
        replacements[old_id] = stored

    rules: list[dict] = []
    for rule in base_rules:  # server rule 5: base order, a replacement directly after the rule it supersedes
        if rule["rule_id"] in replacements:
            rule.update(status="SUPERSEDED", superseded_by_rule_id=replacements[rule["rule_id"]]["rule_id"])
            rules += [rule, replacements[rule["rule_id"]]]
        elif rule["rule_id"] in withdrawn:
            rule.update(status="SUPERSEDED", superseded_by_rule_id=None)
            rules.append(rule)
        else:
            rules.append(rule)
    rules += appended

    note = request["change_note"]
    if note is None:
        parts = []
        if confirmations:
            parts.append(f"{len(confirmations)} rule(s) confirmed by the user")
        if withdrawn:
            parts.append(f"{len(withdrawn)} rule(s) withdrawn by the user")
        note = "; ".join(parts).capitalize() + "."
    return _finish({
        "schema_version": SCHEMA_VERSION, "policy_id": policy_id, "persona_id": request["persona_id"], "version": new_version,
        "parent_version": base["version"] if base else None, "created_at": now_iso, "objectives": copy.deepcopy(request["objectives"]),
        "rules": rules, "change_note": note, "content_hash": "",
    })


def replacement_rule_id(old_rule_id: str, new_version: int, existing: set[str]) -> str:
    """Server-generated id of a replacement: the old id with its trailing number replaced by the new version."""
    stem = old_rule_id.rsplit("-", 1)[0] if old_rule_id.rsplit("-", 1)[-1].isdigit() else old_rule_id
    candidate = f"{stem}-{new_version}"[:128]
    if candidate in existing:
        candidate = f"{stem[:100]}-{new_version}-{hashlib.sha256(old_rule_id.encode('utf-8')).hexdigest()[:8]}"
    return candidate


def build_changed_rule_version(*, job_policy: dict, rule_id: str, new_threshold: float, user_note: str | None,
                               new_version: int, now_iso: str) -> dict:
    """The policy version a CHANGE_RULE challenge creates. It always derives from the challenged job's version."""
    rules = copy.deepcopy(job_policy["rules"])
    old = next((rule for rule in rules if rule["rule_id"] == rule_id), None)
    if old is None or old["status"] != "CONFIRMED":
        raise InvalidConfirmation("payload.rule_id", f"{rule_id} is not a CONFIRMED rule of policy version {job_policy['version']}")
    if old["threshold"] == new_threshold:
        raise InvalidConfirmation("payload.new_threshold", "is the rule's current number; nothing would change")
    new_id = replacement_rule_id(rule_id, new_version, {rule["rule_id"] for rule in rules})
    replacement = copy.deepcopy(old)
    replacement.update(
        rule_id=new_id, threshold=new_threshold, origin="USER_STATED", threshold_source="USER_ENTERED", threshold_quote=None,
        status="CONFIRMED", confirmed_at=now_iso, confirmed_by=CONFIRMED_BY, supersedes_rule_id=rule_id, superseded_by_rule_id=None,
        scope_description=scope_description(old["rule_type"], old["parameters"]),
    )
    old.update(status="SUPERSEDED", superseded_by_rule_id=new_id)
    index = rules.index(old)
    rules.insert(index + 1, replacement)
    # The note is a template. The user's own note stays on the challenge, verbatim and unobeyed.
    note = f"Challenge: the user changed the number of rule {rule_id} from {old['threshold']} to {new_threshold} (new rule {new_id})."
    return _finish({
        "schema_version": SCHEMA_VERSION, "policy_id": job_policy["policy_id"], "persona_id": job_policy["persona_id"],
        "version": new_version, "parent_version": job_policy["version"], "created_at": now_iso,
        "objectives": copy.deepcopy(job_policy["objectives"]), "rules": rules, "change_note": note, "content_hash": "",
    })


def body_hash(value: Any) -> str:
    from byb_contracts import canonical_json
    return hashlib.sha256(canonical_json(value)).hexdigest()
