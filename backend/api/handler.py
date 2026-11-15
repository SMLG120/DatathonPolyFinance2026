"""Lambda entry point for the HTTP API (API Gateway HTTP API, payload 2.0).

Handler string: ``backend.api.handler.handler``.

Phase 1 routes:

* ``POST /investigations``      - store the validated request as a QUEUED job,
  hand it to the worker asynchronously, answer 202 only once Lambda accepted
  the invocation.
* ``GET  /investigations/{id}`` - the job, with its result once SUCCEEDED.

Authentication is done by the Lambda authorizer in front of these routes;
this handler never sees or logs the access code.

The request and response shapes below are phase 1 shapes. They live in
``parse_create_request`` and ``public_view`` so that phase 2 can swap in the
frozen contracts without touching the lifecycle code.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import math
import os
import re
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError

from backend.common import log
from backend.common.clock import from_iso, to_iso
from backend.common.config import ApiConfig
from backend.common.http import ApiError, error_response, json_response
from backend.common.jobs import (
    FAILED,
    QUEUED,
    RUNNING,
    SUCCEEDED,
    ConcurrentUpdateError,
    JobStore,
    StateConflict,
    TerminalStateError,
    is_valid_job_id,
)

JOB_SCHEMA_VERSION = 1
MAX_BODY_BYTES = 8192
MAX_QUESTION_CHARS = 500

FAILURE_DISPATCH_FAILED = "DISPATCH_FAILED"
FAILURE_DEADLINE_EXCEEDED = "DEADLINE_EXCEEDED"

PERSONA_IDS = frozenset({"robert", "mateo", "amira"})
_IDEMPOTENCY_KEY_RE = re.compile(r"[A-Za-z0-9._:\-]{8,128}")
_INSTRUMENT_ID_RE = re.compile(r"[A-Z0-9][A-Z0-9.\-]{0,14}")
_ALLOWED_FIELDS = frozenset({"persona_id", "purchase", "policy_version", "question", "idempotency_key"})
_PURCHASE_FIELDS = frozenset({"instrument_id", "target_direct_weight"})

_DISPATCH_FAILED_MESSAGE = "The investigation could not be started. Nothing was run. Retry with a new idempotency key."


class DispatchError(Exception):
    """Lambda did not accept the asynchronous invocation."""


# --------------------------------------------------------------------------
# Phase 1 wire shapes
# --------------------------------------------------------------------------


def _invalid(message: str) -> ApiError:
    return ApiError(400, "INVALID_REQUEST", message)


def _reject_constant(name: str) -> Any:
    raise ValueError(f"{name} is not valid JSON")


def read_json_body(event: dict[str, Any]) -> dict[str, Any]:
    raw = event.get("body")
    if raw is None or raw == "":
        raise _invalid("A JSON request body is required.")
    if event.get("isBase64Encoded"):
        try:
            raw = base64.b64decode(raw, validate=True).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError, ValueError) as error:
            raise _invalid("The request body is not valid UTF-8.") from error
    if not isinstance(raw, str):
        raise _invalid("A JSON request body is required.")
    if len(raw.encode("utf-8")) > MAX_BODY_BYTES:
        raise ApiError(413, "REQUEST_TOO_LARGE", f"The request body is larger than {MAX_BODY_BYTES} bytes.")
    try:
        body = json.loads(raw, parse_constant=_reject_constant)
    except (ValueError, RecursionError) as error:
        raise _invalid("The request body is not valid JSON.") from error
    if not isinstance(body, dict):
        raise _invalid("The request body must be a JSON object.")
    return body


def read_idempotency_key(event: dict[str, Any], body: dict[str, Any]) -> str:
    """From the ``Idempotency-Key`` header or the ``idempotency_key`` field."""
    header = (event.get("headers") or {}).get("idempotency-key")
    field = body.get("idempotency_key")
    if header is not None and field is not None and header != field:
        raise ApiError(400, "IDEMPOTENCY_KEY_MISMATCH", "The Idempotency-Key header and the idempotency_key field differ.")
    key = header if header is not None else field
    if key is None:
        raise ApiError(400, "IDEMPOTENCY_KEY_REQUIRED", "Send an idempotency key (Idempotency-Key header or idempotency_key field).")
    if not isinstance(key, str) or _IDEMPOTENCY_KEY_RE.fullmatch(key) is None:
        raise ApiError(400, "INVALID_IDEMPOTENCY_KEY", "The idempotency key must be 8 to 128 characters: letters, digits, '.', '_', ':' or '-'.")
    return key


def parse_create_request(body: dict[str, Any]) -> dict[str, Any]:
    """Validate the phase 1 body and return its normalized form.

    Units are portfolio fractions (10% is 0.10). ``question`` is untrusted free
    text: it is stored and shown to the model as data, never interpreted here.
    """
    unknown = sorted(set(body) - _ALLOWED_FIELDS)
    if unknown:
        raise _invalid("Unknown field(s): " + ", ".join(str(name)[:40] for name in unknown[:5]) + ".")

    persona_id = body.get("persona_id")
    if not isinstance(persona_id, str) or persona_id not in PERSONA_IDS:
        raise _invalid("persona_id must be one of: " + ", ".join(sorted(PERSONA_IDS)) + ".")

    purchase = body.get("purchase")
    if not isinstance(purchase, dict):
        raise _invalid("purchase must be an object with instrument_id and target_direct_weight.")
    unknown = sorted(set(purchase) - _PURCHASE_FIELDS)
    if unknown:
        raise _invalid("Unknown field(s) in purchase: " + ", ".join(str(name)[:40] for name in unknown[:5]) + ".")
    instrument_id = purchase.get("instrument_id")
    if not isinstance(instrument_id, str) or _INSTRUMENT_ID_RE.fullmatch(instrument_id) is None:
        raise _invalid("purchase.instrument_id must be an instrument identifier such as NVDA or XIU.TO.")
    weight = purchase.get("target_direct_weight")
    if isinstance(weight, bool) or not isinstance(weight, (int, float)) or not math.isfinite(weight):
        raise _invalid("purchase.target_direct_weight must be a number (a portfolio fraction, 10% is 0.10).")
    if not 0 <= weight <= 1:
        raise _invalid("purchase.target_direct_weight must be between 0 and 1 (a portfolio fraction, 10% is 0.10).")

    policy_version = body.get("policy_version")
    if policy_version is not None and (isinstance(policy_version, bool) or not isinstance(policy_version, int) or policy_version < 1):
        raise _invalid("policy_version must be a positive integer.")

    question = body.get("question")
    if question is not None:
        if not isinstance(question, str):
            raise _invalid("question must be text.")
        question = question.strip()
        if len(question) > MAX_QUESTION_CHARS:
            raise _invalid(f"question must be at most {MAX_QUESTION_CHARS} characters.")
        question = question or None

    return {
        "persona_id": persona_id,
        "purchase": {"instrument_id": instrument_id, "target_direct_weight": float(weight)},
        "policy_version": policy_version,
        "question": question,
    }


def job_id_for(idempotency_key: str) -> str:
    """Deterministic id, so a retried POST addresses the same S3 key."""
    digest = hashlib.sha256(b"byb/investigation/v1\x00" + idempotency_key.encode("utf-8")).hexdigest()
    return "inv_" + digest[:32]


def request_hash(request: dict[str, Any]) -> str:
    canonical = json.dumps(request, separators=(",", ":"), sort_keys=True, allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def new_job(job_id: str, request: dict[str, Any], now: float, deadline_seconds: int, api_request_id: str | None) -> dict[str, Any]:
    return {
        "schema_version": JOB_SCHEMA_VERSION,
        "kind": "investigation",
        "id": job_id,
        "status": QUEUED,
        "created_at": to_iso(now),
        "updated_at": to_iso(now),
        "deadline_at": to_iso(now + deadline_seconds),
        "started_at": None,
        "finished_at": None,
        "request": request,
        "request_hash": request_hash(request),
        "steps": [],
        "result_key": None,
        "trace_key": None,
        "error": None,
        "attempt": None,
        "created_by_request_id": api_request_id,
    }


def public_view(job: dict[str, Any], result: dict[str, Any] | None = None) -> dict[str, Any]:
    """What ``GET /investigations/{id}`` returns. Internal fields stay internal."""
    return {
        "investigation_id": job["id"],
        "status": job["status"],
        "created_at": job["created_at"],
        "updated_at": job["updated_at"],
        "deadline_at": job["deadline_at"],
        "started_at": job.get("started_at"),
        "finished_at": job.get("finished_at"),
        "request": job["request"],
        "steps": job.get("steps", []),
        "result": result,
        "error": job.get("error"),
    }


# --------------------------------------------------------------------------
# Lifecycle
# --------------------------------------------------------------------------


class InvestigationApi:
    def __init__(self, *, store: JobStore, lambda_client: Any, config: ApiConfig, clock: Any) -> None:
        self._store = store
        self._lambda = lambda_client
        self._config = config
        self._clock = clock

    def handle(self, event: dict[str, Any], context: Any) -> dict[str, Any]:
        request_id = (event.get("requestContext") or {}).get("requestId") or getattr(context, "aws_request_id", None)
        route = event.get("routeKey")
        log.bind(component="api", request_id=request_id, route=route)
        try:
            if route == "POST /investigations":
                return self._create(event, request_id)
            if route == "GET /investigations/{id}":
                return self._get(event)
            raise ApiError(404, "ROUTE_NOT_FOUND", "No such route.")
        except ApiError as error:
            log.info("api_error", status=error.status, code=error.code)
            return error_response(error.status, error.code, error.message, request_id, **error.details)
        except Exception as error:  # noqa: BLE001 - last line of defence: a structured 500, details in the log only
            log.error("api_unexpected_error", error_type=type(error).__name__, error_message=str(error))
            return error_response(500, "INTERNAL_ERROR", "The service reported an internal error.", request_id)

    # ------------------------------------------------------------------ POST

    def _create(self, event: dict[str, Any], request_id: str | None) -> dict[str, Any]:
        body = read_json_body(event)
        key = read_idempotency_key(event, body)
        request = parse_create_request(body)
        job_id = job_id_for(key)
        log.add_context(job_id=job_id)

        candidate = new_job(job_id, request, self._clock.time(), self._config.job_deadline_seconds, request_id)
        # 1. Store first. If-None-Match makes the duplicate POST find the first job.
        job, _etag, created = self._store.create(candidate)
        if not created:
            if job.get("request_hash") != candidate["request_hash"]:
                raise ApiError(
                    409,
                    "IDEMPOTENCY_KEY_REUSED",
                    "This idempotency key was already used with a different request.",
                    investigation_id=job_id,
                )
            job = self._expire_if_overdue(job)
            if job["status"] != QUEUED:
                log.info("investigation_replayed", status=job["status"])
                return self._accepted(job, replayed=True)
            # Still QUEUED: the first request may have died before dispatching.
            # Dispatching again is safe because only one worker can claim a job.

        # 2. Dispatch. 3. Answer 202 only if Lambda accepted the invocation.
        try:
            self._dispatch(job_id)
        except DispatchError as error:
            log.error("dispatch_failed", reason=str(error))
            job = self._mark_dispatch_failed(job_id)
            return self._accepted(job, replayed=not created)
        log.info("investigation_accepted", created=created, deadline_at=job["deadline_at"])
        return self._accepted(job, replayed=not created)

    def _dispatch(self, job_id: str) -> None:
        payload = json.dumps({"job_id": job_id}).encode("utf-8")
        try:
            response = self._lambda.invoke(
                FunctionName=self._config.worker_function_name,
                InvocationType="Event",
                Payload=payload,
            )
        except (ClientError, BotoCoreError) as error:
            raise DispatchError(type(error).__name__) from error
        status = response.get("StatusCode")
        if status != 202:
            raise DispatchError(f"unexpected status {status}")

    def _mark_dispatch_failed(self, job_id: str) -> dict[str, Any]:
        def mutate(draft: dict[str, Any]) -> None:
            if draft.get("status") != QUEUED:
                raise StateConflict("the job is no longer queued", draft)
            draft["status"] = FAILED
            draft["finished_at"] = to_iso(self._clock.time())
            draft["error"] = {"code": FAILURE_DISPATCH_FAILED, "message": _DISPATCH_FAILED_MESSAGE}

        try:
            return self._store.update(job_id, mutate)
        except TerminalStateError as error:
            return error.job
        except StateConflict as error:
            # Another request got it dispatched and a worker already claimed it.
            return error.job or {}

    def _accepted(self, job: dict[str, Any], *, replayed: bool) -> dict[str, Any]:
        if job["status"] == FAILED and (job.get("error") or {}).get("code") == FAILURE_DISPATCH_FAILED:
            raise ApiError(503, FAILURE_DISPATCH_FAILED, _DISPATCH_FAILED_MESSAGE, investigation_id=job["id"])
        location = f"/investigations/{job['id']}"
        return json_response(
            202,
            {
                "investigation_id": job["id"],
                "status": job["status"],
                "created_at": job["created_at"],
                "updated_at": job["updated_at"],
                "deadline_at": job["deadline_at"],
                "replayed": replayed,
                "poll": {"href": location, "interval_ms": self._config.poll_interval_ms},
            },
            headers={"location": location},
        )

    # ------------------------------------------------------------------- GET

    def _get(self, event: dict[str, Any]) -> dict[str, Any]:
        job_id = (event.get("pathParameters") or {}).get("id")
        not_found = ApiError(404, "INVESTIGATION_NOT_FOUND", "The service has no record of this investigation.")
        if not is_valid_job_id(job_id):
            raise not_found
        log.add_context(job_id=job_id)
        found = self._store.get(job_id)
        if found is None:
            raise not_found
        job = self._expire_if_overdue(found[0])
        result = None
        if job["status"] == SUCCEEDED:
            result = self._store.get_result(job_id)
            if result is None:
                log.error("result_missing_for_succeeded_job")
                raise ApiError(500, "RESULT_UNAVAILABLE", "The result of this investigation could not be read.")
        return json_response(200, public_view(job, result))

    # -------------------------------------------------------------- deadline

    def _expire_if_overdue(self, job: dict[str, Any]) -> dict[str, Any]:
        """A job past its deadline is FAILED, even if its worker died silently.

        The failure is written to the job (compare-and-swap) so that a worker
        that wakes up late finds a terminal job and cannot overwrite it.
        """
        if job.get("status") not in (QUEUED, RUNNING) or self._clock.time() < from_iso(job["deadline_at"]):
            return job
        failure = {
            "code": FAILURE_DEADLINE_EXCEEDED,
            "message": "The investigation did not finish before its deadline. Nothing more will be run for it.",
        }

        def mutate(draft: dict[str, Any]) -> None:
            draft["status"] = FAILED
            draft["finished_at"] = to_iso(self._clock.time())
            draft["error"] = failure

        try:
            expired = self._store.update(job["id"], mutate)
            log.warning("investigation_expired", previous_status=job.get("status"))
            return expired
        except TerminalStateError as error:
            return error.job  # it reached a terminal state by itself in the meantime
        except ConcurrentUpdateError:
            # Could not persist right now; still report the truth. The worker
            # never writes SUCCEEDED after the deadline, so this cannot flip.
            log.warning("investigation_expired_not_persisted")
            return dict(job, status=FAILED, error=failure)


_app: InvestigationApi | None = None


def _build_app() -> InvestigationApi:
    import boto3
    from botocore.config import Config

    from backend.common.clock import SystemClock

    config = ApiConfig.from_env()
    clock = SystemClock()
    client_config = Config(retries={"total_max_attempts": 2, "mode": "standard"}, connect_timeout=2, read_timeout=5)
    s3 = boto3.client("s3", config=client_config)
    lambda_client = boto3.client("lambda", config=client_config)
    return InvestigationApi(
        store=JobStore(s3, config.data_bucket, clock, can_list=True),
        lambda_client=lambda_client,
        config=config,
        clock=clock,
    )


def _get_app() -> InvestigationApi:
    global _app
    if _app is None:
        log.configure(os.environ.get("LOG_LEVEL", "INFO"))
        _app = _build_app()
    return _app


# Inside Lambda, create the SDK clients during the init phase (outside the
# handler) so the first request does not pay for it. Anywhere else, stay lazy.
if os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
    _get_app()


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    return _get_app().handle(event, context)
