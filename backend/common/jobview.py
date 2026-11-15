"""The investigation job document: what is stored, and what ``GET /investigations/{id}`` shows.

Stored at ``jobs/<id>.json``: the contract's members (``investigation_job.schema.json``) plus one
``internal`` object that never leaves the service. The engine result and the explanation are a
separate write-once object (``results/<id>.json``); proposed corrections are write-once objects
too. So nothing of a terminal job can be rewritten.
"""

from __future__ import annotations

import hashlib
from typing import Any

from byb_contracts import SCHEMA_VERSION

from backend.common.clock import to_iso
from backend.common.jobs import QUEUED, SUCCEEDED

OUTCOME_SCHEMA_VERSION = 2
PUBLIC_MEMBERS = (
    "schema_version", "id", "status", "created_at", "updated_at", "deadline_at", "expires_at", "idempotency_key", "persona_id",
    "policy_id", "policy_version", "request", "resolved_request", "parent_investigation_id", "challenge", "agent", "steps",
    "clarification", "result", "explanation", "failure", "proposed_corrections",
)


def job_id_for(namespace: str, *parts: str) -> str:
    """Deterministic id, so a retried request addresses the same S3 key. Matches the contract id pattern."""
    digest = hashlib.sha256(("byb/" + namespace + "/v2").encode("utf-8") + b"".join(b"\x00" + part.encode("utf-8") for part in parts)).hexdigest()
    return "inv-" + digest[:32]


def new_job(*, job_id: str, now: float, deadline_seconds: int, expiry_seconds: int, idempotency_key: str, persona_id: str,
            policy_id: str, policy_version: int, request: dict, parent_investigation_id: str | None, challenge: dict | None,
            model_id: str | None, request_hash: str, snapshot_id: str, api_request_id: str | None) -> dict[str, Any]:
    structured = request.get("instrument_id") is not None
    return {
        "schema_version": SCHEMA_VERSION,
        "id": job_id,
        "status": QUEUED,
        "created_at": to_iso(now),
        "updated_at": to_iso(now),
        "deadline_at": to_iso(now + deadline_seconds),
        "expires_at": to_iso(now + expiry_seconds),
        "idempotency_key": idempotency_key,
        "persona_id": persona_id,
        "policy_id": policy_id,
        "policy_version": policy_version,
        "request": request,
        # A structured request is authoritative: it is what gets checked, unchanged.
        "resolved_request": dict(request) if structured else None,
        "parent_investigation_id": parent_investigation_id,
        "challenge": challenge,
        "agent": {"mode": "MODEL", "model_id": model_id, "tool_rounds": 0, "note": None},
        "steps": [],
        "clarification": None,
        "result": None,
        "explanation": [],
        "failure": None,
        "proposed_corrections": [],
        "internal": {
            "kind": "investigation",
            "request_hash": request_hash,
            # Identity of everything that can change the verdict, with policy_id/policy_version above.
            "data_snapshot_id": snapshot_id,
            "calculation_version": None,
            "attempt": None,
            "result_key": None,
            "trace_key": None,
            "created_by_request_id": api_request_id,
        },
    }


def accepted_view(job: dict[str, Any], poll_interval_ms: int) -> dict[str, Any]:
    """``api.schema.json#/$defs/investigation_accepted``."""
    return {
        "schema_version": SCHEMA_VERSION,
        "id": job["id"],
        "status": job["status"],
        "created_at": job["created_at"],
        "deadline_at": job["deadline_at"],
        "expires_at": job["expires_at"],
        "poll": {"path": f"/investigations/{job['id']}", "interval_ms": poll_interval_ms},
    }


def public_view(job: dict[str, Any], outcome: dict[str, Any] | None = None, corrections: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """The job as the contract shows it. ``outcome`` is the write-once result object of a SUCCEEDED job."""
    view = {name: job.get(name) for name in PUBLIC_MEMBERS}
    if job["status"] == SUCCEEDED and outcome is not None:
        view["result"] = outcome["result"]
        view["explanation"] = outcome["explanation"]
    else:
        view["result"], view["explanation"] = None, []
    view["proposed_corrections"] = list(corrections or [])
    return view


def mark_failed(draft: dict[str, Any], failure: dict[str, Any]) -> None:
    """Turn a job document into its FAILED form. A failed job shows no partial verdict:

    no clarification, and no step may cite evidence, because the evidence lives in a result that
    is not shown (``validate_investigation_job``: a cited id must exist in ``result.evidence``).
    """
    draft["status"] = "FAILED"
    draft["failure"] = failure
    draft["clarification"] = None
    draft["steps"] = [dict(step, evidence_ids=[]) for step in draft.get("steps", [])]
