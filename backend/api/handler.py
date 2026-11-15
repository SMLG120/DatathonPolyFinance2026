"""Lambda entry point for the HTTP API (API Gateway HTTP API, payload 2.0).

Handler string: ``backend.api.handler.handler``. Routes and bodies are the ones
of ``contracts/api.md`` (schema_version 1.0.0):

    GET  /portfolios/{persona_id}          fictional scenario, registry entries, purchasable instruments
    POST /rules/interpret                  model-backed extraction -> PROPOSED drafts and questions; nothing stored
    POST /rules/confirm                    explicit confirmation -> new immutable policy version
    POST /check                            deterministic engine run; draft_rules -> labelled preview; 5 s budget measured
    POST /investigations                   store QUEUED, invoke the worker, 202 once accepted
    GET  /investigations/{id}              the job in any state
    POST /investigations/{id}/challenge    CORRECT_FACT / CLARIFY_PREFERENCE / CHANGE_RULE

Authentication is done by the Lambda authorizer in front of these routes; this
handler never sees or logs the access code. Verdicts come from
``backend.engine`` and a preview never reads or changes a stored policy. The
only model call made here is the interpreter's (``backend.agents.interpreter``),
on ``POST /rules/interpret`` and the ``CLARIFY_PREFERENCE`` challenge: it
drafts and asks; it never evaluates, stores or confirms anything.

Every request body is validated against the contract schema before anything
is read or stored; every error has the contract's error shape.
"""

from __future__ import annotations

import base64
import binascii
import json
import os
import re
import uuid
from typing import Any, Callable

from botocore.exceptions import BotoCoreError, ClientError
from byb_contracts import SCHEMA_VERSION, ContractError, schema_errors
from byb_contracts.constants import CHECK_TIMEOUT_SECONDS

from backend import engine
from backend.agents.interpreter import Interpreter, InterpreterFailed, InterpreterTimeout
from backend.common import log
from backend.common.clock import from_iso, to_iso
from backend.common.config import ApiConfig
from backend.common.data import DataUnavailable, Snapshot, SnapshotLoader
from backend.common.http import ApiError, detail, error_response, json_response
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
from backend.common.jobview import accepted_view, job_id_for, mark_failed, new_job, public_view
from backend.common.policies import PolicyStore, PolicyVersionExists
from backend.common.policy_ops import InvalidConfirmation, body_hash, build_changed_rule_version, build_confirmed_version

# Largest body accepted. A confirmation carrying every rule and objective in full is a few kilobytes.
MAX_BODY_BYTES = 65536
# Longest text handed to the interpreter: the limit of interpret_request.text, applied to a clarification too.
MAX_INTERPRET_CHARS = 2000

FAILURE_WORKER_INVOCATION_FAILED = "WORKER_INVOCATION_FAILED"
FAILURE_DEADLINE_EXCEEDED = "DEADLINE_EXCEEDED"

_IDEMPOTENCY_KEY_RE = re.compile(r"[A-Za-z0-9_-]{8,64}")
_PERSONA_RE = re.compile(r"[a-z][a-z0-9_]{0,31}")
_NUMERIC_UNITS = frozenset({"fraction", "price", "fx_rate", "days", "count"})

_VALIDATION_MESSAGE = "The request body does not match the contract."
_DISPATCH_FAILED_MESSAGE = "The investigation could not be started. Nothing was run. Retry with a new idempotency key."
_DEADLINE_MESSAGE = "The investigation did not finish before its deadline. Nothing more will be run for it."
_CONFLICT_MESSAGE = "The policy has a newer version than the one this confirmation was based on. Reload it and confirm again."
_CHECK_BUDGET_MESSAGE = (f"The check did not finish within its {CHECK_TIMEOUT_SECONDS} second budget, so no result is returned. "
                         "Nothing was stored. Send the request again.")
_INTERPRETER_UNAVAILABLE = "The interpreter is not available in this build. Your text was kept; the scenario rules can still be confirmed without it."
_INTERPRETER_FAILED = "The interpreter could not produce a valid draft. Nothing was changed. Try again, or enter the rule with the form."
_INTERPRETER_TIMEOUT = "The interpreter did not answer in time. Nothing was changed. Try again, or enter the rule with the form."

SCHEMA = "api.schema.json#/$defs/"


class DispatchError(Exception):
    """Lambda did not accept the asynchronous invocation."""


# --------------------------------------------------------------------------
# Request parsing and validation
# --------------------------------------------------------------------------


def _validation(details: list[dict[str, str]], message: str = _VALIDATION_MESSAGE) -> ApiError:
    return ApiError(400, "VALIDATION_ERROR", message, details)


def _not_found(what: str, path: str = "") -> ApiError:
    return ApiError(404, "NOT_FOUND", f"The service has no record of this {what}.", [detail(path, f"unknown {what}")])


def _reject_constant(name: str) -> Any:
    raise ValueError(f"{name} is not valid JSON")


def _finite_float(text: str) -> float:
    value = float(text)
    if value != value or value in (float("inf"), float("-inf")):  # "1e999" is JSON text that parses to infinity
        raise ValueError("a number is too large to be represented")
    return value


def read_json_body(event: dict[str, Any]) -> dict[str, Any]:
    """The body as a JSON object. NaN, Infinity, numbers that overflow, non-UTF-8, non-objects and oversized bodies are 400."""
    raw = event.get("body")
    if raw is None or raw == "":
        raise _validation([detail("", "a JSON request body is required")])
    if event.get("isBase64Encoded"):
        try:
            raw = base64.b64decode(raw, validate=True).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError, ValueError) as error:
            raise _validation([detail("", "the request body is not valid UTF-8")]) from error
    if not isinstance(raw, str):
        raise _validation([detail("", "a JSON request body is required")])
    if len(raw.encode("utf-8")) > MAX_BODY_BYTES:
        raise _validation([detail("", f"the request body is larger than {MAX_BODY_BYTES} bytes")])
    try:
        body = json.loads(raw, parse_constant=_reject_constant, parse_float=_finite_float)
    except (ValueError, RecursionError) as error:
        raise _validation([detail("", "the request body is not valid JSON (NaN, Infinity and numbers too large to represent are refused)")]) from error
    if not isinstance(body, dict):
        raise _validation([detail("", "the request body must be a JSON object")])
    return body


def contract_details(errors: list[str], limit: int = 20) -> list[dict[str, str]]:
    """``byb_contracts`` messages ("path: issue", root "$") as contract error details."""
    details = []
    for error in errors[:limit]:
        path, separator, issue = error.partition(": ")
        if not separator:
            path, issue = "", error
        details.append(detail("" if path == "$" else path, issue))
    return details


def run_engine(function: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Call an engine function; a request the engine refuses as invalid (ContractError) is the client's error: 400."""
    try:
        return function(*args, **kwargs)
    except ContractError as error:
        raise _validation(contract_details(list(error.errors)) or [detail("", "the request is not valid")]) from error


def validate_body(body: dict[str, Any], definition: str) -> None:
    errors = schema_errors(body, SCHEMA + definition)
    if errors:
        raise _validation(contract_details(errors))


def read_idempotency_key(event: dict[str, Any]) -> str:
    """The ``Idempotency-Key`` header (API Gateway lower-cases header names)."""
    headers = event.get("headers") or {}
    key = next((value for name, value in headers.items() if isinstance(name, str) and name.lower() == "idempotency-key"), None)
    if key is None:
        raise _validation([detail("headers.Idempotency-Key", "the header is required")], "A required header is missing or malformed.")
    if not isinstance(key, str) or _IDEMPOTENCY_KEY_RE.fullmatch(key) is None:
        raise _validation([detail("headers.Idempotency-Key", "must be 8 to 64 characters: letters, digits, '_' or '-'")],
                          "A required header is missing or malformed.")
    return key


# --------------------------------------------------------------------------
# The API
# --------------------------------------------------------------------------


class Api:
    def __init__(self, *, store: JobStore, policies: PolicyStore, snapshots: SnapshotLoader, lambda_client: Any, config: ApiConfig,
                 clock: Any, new_id: Callable[[], str] | None = None, interpreter: Interpreter | None = None) -> None:
        self._store = store
        self._policies = policies
        self._snapshots = snapshots
        self._lambda = lambda_client
        self._config = config
        self._clock = clock
        self._new_id = new_id or (lambda: uuid.uuid4().hex)
        self._interpreter = interpreter  # None: not configured; both interpreter entry points answer 502
        self._routes: dict[str, Callable[[dict[str, Any], str | None], dict[str, Any]]] = {
            "GET /portfolios/{persona_id}": self._portfolio,
            "POST /rules/interpret": self._interpret,
            "POST /rules/confirm": self._confirm,
            "POST /check": self._check,
            "POST /investigations": self._create,
            "GET /investigations/{id}": self._get,
            "POST /investigations/{id}/challenge": self._challenge,
        }

    def handle(self, event: dict[str, Any], context: Any) -> dict[str, Any]:
        request_id = (event.get("requestContext") or {}).get("requestId") or getattr(context, "aws_request_id", None)
        route = event.get("routeKey")
        log.bind(component="api", request_id=request_id, route=route)
        try:
            handler = self._routes.get(route) if isinstance(route, str) else None
            if handler is None:
                raise ApiError(404, "NOT_FOUND", "No such route.", [detail("", "unknown route")])
            return handler(event, request_id)
        except ApiError as error:
            log.info("api_error", status=error.status, code=error.code)
            return error_response(error.status, error.code, error.message, request_id, error.details)
        except Exception as error:  # noqa: BLE001 - last line of defence: a structured 500, details in the log only
            log.error("api_unexpected_error", error_type=type(error).__name__, error_message=str(error))
            return error_response(500, "INTERNAL_ERROR", "The service reported an internal error.", request_id)

    # ---------------------------------------------------------------- lookups

    def _snapshot(self) -> Snapshot:
        try:
            return self._snapshots.load()
        except DataUnavailable as error:
            log.error("data_unavailable", reason=str(error))
            raise ApiError(500, "INTERNAL_ERROR", "The data snapshot could not be read, so nothing was calculated.") from error

    def _scenario(self, snapshot: Snapshot, persona_id: Any, path: str = "persona_id") -> dict[str, Any]:
        scenario = snapshot.scenario(persona_id) if isinstance(persona_id, str) and _PERSONA_RE.fullmatch(persona_id) else None
        if scenario is None:
            raise _not_found("persona", path)
        return scenario

    def _policy(self, persona_id: str, policy_id: Any, version: Any) -> dict[str, Any]:
        policy = self._policies.get(policy_id, version)
        if policy is None or policy.get("persona_id") != persona_id:
            raise _not_found("policy version", "policy_version")
        return policy

    # ------------------------------------------------- GET /portfolios/{persona_id}

    def _portfolio(self, event: dict[str, Any], request_id: str | None) -> dict[str, Any]:
        snapshot = self._snapshot()
        scenario = self._scenario(snapshot, (event.get("pathParameters") or {}).get("persona_id"), "")
        purchasable = snapshot.purchasable_instrument_ids()
        wanted = [position["instrument_id"] for position in scenario["portfolio"]["positions"]] + purchasable
        registry = snapshot.registry
        return json_response(200, {
            "schema_version": SCHEMA_VERSION,
            "scenario": scenario,
            "instruments": {instrument_id: registry[instrument_id] for instrument_id in sorted(set(wanted)) if instrument_id in registry},
            "purchasable_instrument_ids": purchasable,
        })

    # ----------------------------------------------------- POST /rules/interpret

    def _interpret(self, event: dict[str, Any], request_id: str | None) -> dict[str, Any]:
        started = self._clock.time()
        body = read_json_body(event)
        validate_body(body, "interpret_request")
        if (body["policy_id"] is None) != (body["policy_version"] is None):
            raise _validation([detail("policy_version", "policy_id and policy_version are both null or both set")])
        snapshot = self._snapshot()
        self._scenario(snapshot, body["persona_id"])
        if body["policy_id"] is not None:
            # Context only: the policy version must exist. It is neither sent to the model nor changed.
            self._policy(body["persona_id"], body["policy_id"], body["policy_version"])
        return json_response(200, self._interpretation(body["text"], body["persona_id"], snapshot, started))

    def _interpretation(self, text: str, persona_id: str, snapshot: Snapshot, started: float, clarification_mode: bool = False) -> dict[str, Any]:
        """A contract-valid draft, or the contract's 502 / 504. Nothing is stored; no policy is read or written; no verdict exists here."""
        if self._interpreter is None:
            raise ApiError(502, "INTERPRETER_FAILED", _INTERPRETER_UNAVAILABLE)
        try:
            return self._interpreter.interpret(text=text, persona_id=persona_id, snapshot=snapshot, started=started,
                                               clarification_mode=clarification_mode)
        except InterpreterTimeout as error:
            raise ApiError(504, "INTERPRETER_TIMEOUT", _INTERPRETER_TIMEOUT) from error
        except InterpreterFailed as error:
            raise ApiError(502, "INTERPRETER_FAILED", _INTERPRETER_FAILED) from error

    # ------------------------------------------------------- POST /rules/confirm

    def _confirm(self, event: dict[str, Any], request_id: str | None) -> dict[str, Any]:
        body = read_json_body(event)
        validate_body(body, "confirm_request")
        persona_id = body["persona_id"]
        self._scenario(self._snapshot(), persona_id)
        policy_id, base_version = body["policy_id"], body["base_version"]
        base = None
        if policy_id is None:
            if base_version is not None:
                raise _validation([detail("base_version", "must be null when policy_id is null (a new policy starts at version 1)")])
            policy_id, new_version = f"pol-{persona_id.replace('_', '-')}-{self._new_id()[:12]}", 1
        else:
            latest = self._policies.latest_version(policy_id)
            base = self._policies.get(policy_id, latest) if latest else None
            if base is None or base.get("persona_id") != persona_id:
                raise _not_found("policy", "policy_id")
            if base_version is None:
                raise _validation([detail("base_version", "is required when policy_id is set")])
            if base_version != latest:
                raise ApiError(409, "POLICY_VERSION_CONFLICT", _CONFLICT_MESSAGE,
                               [detail("base_version", f"is {base_version}; the latest version of {policy_id} is {latest}")])
            new_version = latest + 1
        try:
            policy = build_confirmed_version(request=body, base=base, policy_id=policy_id, new_version=new_version, now_iso=to_iso(self._clock.time()))
        except InvalidConfirmation as error:
            raise ApiError(422, "INVALID_CONFIRMATION", "The confirmation cannot be applied.", [detail(error.path, error.issue)]) from error
        try:
            self._policies.create(policy)
        except PolicyVersionExists as error:
            # Another confirmation created this version between the read and the write.
            raise ApiError(409, "POLICY_VERSION_CONFLICT", _CONFLICT_MESSAGE,
                           [detail("base_version", f"is {base_version}; {policy_id} gained a newer version while this request ran")]) from error
        log.info("policy_version_created", policy_id=policy_id, version=new_version, content_hash=policy["content_hash"])
        return json_response(201, {"schema_version": SCHEMA_VERSION, "policy": policy})

    # --------------------------------------------------------------- POST /check

    def _check(self, event: dict[str, Any], request_id: str | None) -> dict[str, Any]:
        started = self._clock.time()
        body = read_json_body(event)
        validate_body(body, "check_request")
        policy_id, version, drafts = body["policy_id"], body["policy_version"], body["draft_rules"]
        if (policy_id is None) != (version is None):
            raise _validation([detail("policy_version", "policy_id and policy_version are both null or both set")])
        if drafts is None and policy_id is None:
            raise _validation([detail("draft_rules", "is null, so policy_id and policy_version are required (the stored policy is evaluated)")])
        snapshot = self._snapshot()
        scenario = self._scenario(snapshot, body["persona_id"])
        # In a preview the stored version only supplies the objectives for goal_context; its rules are not read.
        policy = self._policy(body["persona_id"], policy_id, version) if policy_id is not None else None
        self._within_check_budget(started, "before the calculation")  # reading the data used the budget: do not start
        result = run_engine(
            engine.check_rules, scenario["portfolio"], policy, body["purchase_request"], snapshot.instruments, snapshot.holdings, snapshot.market_data,
            snapshot.controversies, draft_rules=drafts, data_sources=snapshot.data_sources or None,
        )
        elapsed_ms = self._within_check_budget(started, "after the calculation")  # a late result is not returned
        log.info("check_completed", preview=result["preview"], headline=result["summary"]["headline"], data_snapshot_id=snapshot.snapshot_id,
                 calculation_version=result["calculation_version"], elapsed_ms=elapsed_ms)
        return json_response(200, result)

    def _within_check_budget(self, started: float, stage: str) -> int:
        """The 5 s budget of ``POST /check`` (api.md, Timing), measured on the service clock.

        The engine is a pure synchronous function and is not interrupted: the budget is checked before it starts
        and when it returns, and an answer that is over budget is replaced by an error. The contract has no error
        code of its own for this, so it is a 500 ``INTERNAL_ERROR`` whose details say what happened.
        """
        elapsed_ms = int(round((self._clock.time() - started) * 1000))
        if elapsed_ms > CHECK_TIMEOUT_SECONDS * 1000:
            log.error("check_over_budget", stage=stage, elapsed_ms=elapsed_ms, budget_ms=CHECK_TIMEOUT_SECONDS * 1000)
            raise ApiError(500, "INTERNAL_ERROR", _CHECK_BUDGET_MESSAGE,
                           [detail("", f"over the {CHECK_TIMEOUT_SECONDS} s budget {stage} ({elapsed_ms} ms)")])
        return elapsed_ms

    # ------------------------------------------------------- POST /investigations

    def _create(self, event: dict[str, Any], request_id: str | None) -> dict[str, Any]:
        body = read_json_body(event)
        validate_body(body, "investigation_create_request")
        key = read_idempotency_key(event)
        snapshot = self._snapshot()
        scenario = self._scenario(snapshot, body["persona_id"])
        policy = self._policy(body["persona_id"], body["policy_id"], body["policy_version"])
        parent_id = body["parent_investigation_id"]
        if parent_id is not None and (not is_valid_job_id(parent_id) or self._store.get(parent_id) is None):
            raise _not_found("investigation", "parent_investigation_id")
        request = body["request"]
        if request["instrument_id"] is not None:
            # A request the engine would refuse is never stored (contracts/api.md section 6, rule 3).
            execution = run_engine(engine.simulate_change, scenario["portfolio"], request, snapshot.instruments, policy)["execution"]
            if execution["status"] != "OK":
                raise ApiError(422, "INVALID_PURCHASE_REQUEST", "The purchase request cannot be evaluated.",
                               [detail("request", f"{execution['code']}: {execution['message']}")])
        job_id = job_id_for("investigation", key)
        log.add_context(job_id=job_id)
        candidate = new_job(
            job_id=job_id, now=self._clock.time(), deadline_seconds=self._config.job_deadline_seconds, expiry_seconds=self._config.job_expiry_seconds,
            idempotency_key=key, persona_id=body["persona_id"], policy_id=body["policy_id"], policy_version=body["policy_version"], request=request,
            parent_investigation_id=parent_id, challenge=None, model_id=self._config.model_id, request_hash=body_hash(body),
            snapshot_id=snapshot.snapshot_id, api_request_id=request_id,
        )
        return json_response(202, self._store_and_dispatch(candidate), headers={"location": f"/investigations/{job_id}"})

    def _store_and_dispatch(self, candidate: dict[str, Any]) -> dict[str, Any]:
        """Store first, dispatch second, and report 202 only once Lambda accepted the invocation."""
        job_id = candidate["id"]
        # 1. Store first. If-None-Match makes the duplicate request find the first job.
        job, _etag, created = self._store.create(candidate)
        if not created:
            if (job.get("internal") or {}).get("request_hash") != candidate["internal"]["request_hash"]:
                raise ApiError(409, "IDEMPOTENCY_KEY_REUSED", "This idempotency key was already used with a different request.",
                               [detail("headers.Idempotency-Key", "already used with a different body")])
            job = self._expire_if_overdue(job)
            if job["status"] != QUEUED:
                log.info("investigation_replayed", status=job["status"])
                return self._accepted(job)
            # Still QUEUED: the first request may have died before dispatching.
            # Dispatching again is safe because only one worker can claim a job.
        # 2. Dispatch. 3. Answer 202 only if Lambda accepted the invocation.
        try:
            self._dispatch(job_id)
        except DispatchError as error:
            log.error("dispatch_failed", reason=str(error))
            job = self._mark_dispatch_failed(job_id)
            return self._accepted(job)
        log.info("investigation_accepted", created=created, deadline_at=job["deadline_at"])
        return self._accepted(job)

    def _dispatch(self, job_id: str) -> None:
        payload = json.dumps({"job_id": job_id}).encode("utf-8")
        try:
            response = self._lambda.invoke(FunctionName=self._config.worker_function_name, InvocationType="Event", Payload=payload)
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
            draft["failure"] = {"code": FAILURE_WORKER_INVOCATION_FAILED, "message": _DISPATCH_FAILED_MESSAGE, "retryable": True}

        try:
            return self._store.update(job_id, mutate)
        except TerminalStateError as error:
            return error.job
        except StateConflict as error:
            # Another request got it dispatched and a worker already claimed it.
            return error.job or {}

    def _accepted(self, job: dict[str, Any]) -> dict[str, Any]:
        if job["status"] == FAILED and (job.get("failure") or {}).get("code") == FAILURE_WORKER_INVOCATION_FAILED:
            raise ApiError(503, "WORKER_INVOCATION_FAILED", _DISPATCH_FAILED_MESSAGE, [detail("headers.Idempotency-Key", "retry with a new key")])
        return accepted_view(job, self._config.poll_interval_ms)

    # ------------------------------------------------- GET /investigations/{id}

    def _load_job(self, event: dict[str, Any]) -> dict[str, Any]:
        """The stored job with the deadline and expiry rules applied. 404 / 410 otherwise."""
        job_id = (event.get("pathParameters") or {}).get("id")
        if not is_valid_job_id(job_id):
            raise _not_found("investigation")
        log.add_context(job_id=job_id)
        found = self._store.get(job_id)
        if found is None:
            raise _not_found("investigation")
        job = found[0]
        if self._clock.time() >= from_iso(job["expires_at"]):
            raise ApiError(410, "INVESTIGATION_EXPIRED", "This investigation has expired and is no longer available.",
                           [detail("", f"expired at {job['expires_at']}")])
        return self._expire_if_overdue(job)

    def _outcome(self, job: dict[str, Any]) -> dict[str, Any] | None:
        if job["status"] != SUCCEEDED:
            return None
        outcome = self._store.get_result(job["id"])
        if outcome is None:
            log.error("result_missing_for_succeeded_job")
            raise ApiError(500, "INTERNAL_ERROR", "The result of this investigation could not be read.")
        return outcome

    def _get(self, event: dict[str, Any], request_id: str | None) -> dict[str, Any]:
        job = self._load_job(event)
        corrections = self._store.list_corrections(job["id"]) if job["status"] == SUCCEEDED else []
        return json_response(200, public_view(job, self._outcome(job), corrections))

    def _expire_if_overdue(self, job: dict[str, Any]) -> dict[str, Any]:
        """A job past its deadline is FAILED, even if its worker died silently.

        The failure is written to the job (compare-and-swap) so that a worker
        that wakes up late finds a terminal job and cannot overwrite it.
        """
        if job.get("status") not in (QUEUED, RUNNING) or self._clock.time() < from_iso(job["deadline_at"]):
            return job
        failure = {"code": FAILURE_DEADLINE_EXCEEDED, "message": _DEADLINE_MESSAGE, "retryable": True}

        def mutate(draft: dict[str, Any]) -> None:
            mark_failed(draft, failure)

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
            reported = dict(job)
            mark_failed(reported, failure)
            return reported

    # --------------------------------------- POST /investigations/{id}/challenge

    def _challenge(self, event: dict[str, Any], request_id: str | None) -> dict[str, Any]:
        started = self._clock.time()
        body = read_json_body(event)
        validate_body(body, "challenge_request")
        job = self._load_job(event)
        if job["status"] in (QUEUED, RUNNING):
            raise ApiError(409, "INVESTIGATION_NOT_FINISHED", "The investigation is still running. Wait for it to finish before challenging it.",
                           [detail("", f"status is {job['status']}")])
        if job["status"] == FAILED:
            raise ApiError(422, "UNSUPPORTED_CHALLENGE", "A failed investigation has no result to challenge.", [detail("", "status is FAILED")])
        outcome = self._outcome(job)
        kind = body["type"]
        if kind == "CORRECT_FACT":
            return self._correct_fact(job, outcome, body)
        if kind == "CLARIFY_PREFERENCE":
            return self._clarify_preference(job, body, started)
        return self._change_rule(event, job, outcome, body, request_id)

    @staticmethod
    def _unsupported(path: str, issue: str) -> ApiError:
        return ApiError(422, "UNSUPPORTED_CHALLENGE", "The challenge cannot be applied to this investigation.", [detail(path, issue)])

    def _correct_fact(self, job: dict[str, Any], outcome: dict[str, Any] | None, body: dict[str, Any]) -> dict[str, Any]:
        payload = body["payload"]
        result = (outcome or {}).get("result")
        if result is None:
            raise self._unsupported("", "the investigation has no result")
        record = next((r for r in result["evidence"] if r["evidence_id"] == payload["evidence_id"]), None)
        if record is None:
            raise self._unsupported("payload.evidence_id", "is not an evidence record of this investigation's result")
        if payload["asserted_unit"] != record["unit"]:
            raise self._unsupported("payload.asserted_unit", f"must be the unit of that record ({record['unit']})")
        value = payload["asserted_value"]
        numeric = isinstance(value, (int, float)) and not isinstance(value, bool)
        if (record["unit"] in _NUMERIC_UNITS) != numeric:
            raise self._unsupported("payload.asserted_value", "must be a number for a numeric unit and a string for a date or text")
        now = to_iso(self._clock.time())
        suffix = self._new_id()[:12]
        challenge = {"challenge_id": f"ch-{suffix}", "investigation_id": job["id"], "type": "CORRECT_FACT", "payload": payload, "created_at": now}
        # Stored next to the evidence it disputes, as an unverified user assertion. Nothing is recomputed,
        # the note and the source are kept verbatim and are never obeyed or fetched.
        correction = {
            "correction_id": f"corr-{suffix}", "challenge_id": challenge["challenge_id"], "investigation_id": job["id"],
            "evidence_id": record["evidence_id"], "original_value": record["value"], "original_unit": record["unit"],
            "asserted_value": value, "asserted_unit": payload["asserted_unit"],
            "provenance": {"asserted_by": "USER", "asserted_at": now, "user_note": payload["user_note"], "user_source": payload["user_source"]},
            "status": "UNVERIFIED", "applied_to_calculation": False,
        }
        if not self._store.put_correction(job["id"], correction):
            raise ApiError(500, "INTERNAL_ERROR", "The correction could not be stored.")
        log.info("correction_stored", correction_id=correction["correction_id"], evidence_id=record["evidence_id"])
        return json_response(201, {"schema_version": SCHEMA_VERSION, "challenge": challenge, "proposed_correction": correction,
                                   "interpretation": None, "policy": None, "investigation": None})

    def _clarify_preference(self, job: dict[str, Any], body: dict[str, Any], started: float) -> dict[str, Any]:
        payload = body["payload"]
        objective_id = payload["objective_id"]
        if objective_id is not None:
            policy = self._policies.get(job["policy_id"], job["policy_version"])
            if policy is None or objective_id not in {o["objective_id"] for o in policy["objectives"]}:
                raise self._unsupported("payload.objective_id", "is not an objective of the investigation's policy version")
        if len(payload["text"]) > MAX_INTERPRET_CHARS:
            raise _validation([detail("payload.text", f"is longer than {MAX_INTERPRET_CHARS} characters")])
        # The same interpreter as POST /rules/interpret: a draft and questions only. The job, its report, its policy
        # version and every stored object stay as they are; to act on the draft the user confirms a rule.
        interpretation = self._interpretation(payload["text"], job["persona_id"], self._snapshot(), started, clarification_mode=True)
        challenge = {"challenge_id": f"ch-{self._new_id()[:12]}", "investigation_id": job["id"], "type": "CLARIFY_PREFERENCE",
                     "payload": payload, "created_at": to_iso(self._clock.time())}
        log.info("preference_clarified", challenge_id=challenge["challenge_id"], interpretation_id=interpretation["interpretation_id"])
        return json_response(200, {"schema_version": SCHEMA_VERSION, "challenge": challenge, "proposed_correction": None,
                                   "interpretation": interpretation, "policy": None, "investigation": None})

    def _change_rule(self, event: dict[str, Any], job: dict[str, Any], outcome: dict[str, Any] | None, body: dict[str, Any],
                     request_id: str | None) -> dict[str, Any]:
        key = read_idempotency_key(event)
        payload = body["payload"]
        if (outcome or {}).get("result") is None or job["resolved_request"] is None:
            raise self._unsupported("", "the investigation has no result")
        child_id = job_id_for("challenge", job["id"], key)
        request_hash = body_hash({"investigation_id": job["id"], "body": body})

        existing = self._store.get(child_id)
        if existing is not None:
            # Replay: the same key and body give the same policy version and the same child investigation.
            child = existing[0]
            if (child.get("internal") or {}).get("request_hash") != request_hash:
                raise ApiError(409, "IDEMPOTENCY_KEY_REUSED", "This idempotency key was already used with a different request.",
                               [detail("headers.Idempotency-Key", "already used with a different body")])
            policy = self._policies.get(child["policy_id"], child["policy_version"])
            if policy is None:
                raise ApiError(500, "INTERNAL_ERROR", "The policy version of this challenge could not be read.")
        else:
            job_policy = self._policies.get(job["policy_id"], job["policy_version"])
            if job_policy is None:
                raise ApiError(500, "INTERNAL_ERROR", "The policy version of this investigation could not be read.")
            now = self._clock.time()
            policy = None
            for _ in range(3):  # a concurrent confirmation may take the next number first
                new_version = (self._policies.latest_version(job["policy_id"]) or job["policy_version"]) + 1
                try:
                    policy = build_changed_rule_version(job_policy=job_policy, rule_id=payload["rule_id"], new_threshold=payload["new_threshold"],
                                                        user_note=payload["user_note"], new_version=new_version, now_iso=to_iso(now))
                except InvalidConfirmation as error:
                    raise self._unsupported(error.path, error.issue) from error
                try:
                    self._policies.create(policy)
                    break
                except PolicyVersionExists:
                    policy = None
            if policy is None:
                raise ApiError(500, "INTERNAL_ERROR", "The new policy version could not be stored.")
            log.info("policy_version_created", policy_id=policy["policy_id"], version=policy["version"], content_hash=policy["content_hash"],
                     challenged_investigation=job["id"])
            challenge = {"challenge_id": "ch-" + child_id[4:16], "investigation_id": job["id"], "type": "CHANGE_RULE", "payload": payload,
                         "created_at": to_iso(now)}
            # A fresh investigation under the new version. The earlier job, its result and the earlier
            # policy version are separate immutable objects and are not touched.
            child = new_job(
                job_id=child_id, now=now, deadline_seconds=self._config.job_deadline_seconds, expiry_seconds=self._config.job_expiry_seconds,
                idempotency_key=key, persona_id=job["persona_id"], policy_id=policy["policy_id"], policy_version=policy["version"],
                request=dict(job["resolved_request"]), parent_investigation_id=job["id"], challenge=challenge, model_id=self._config.model_id,
                request_hash=request_hash, snapshot_id=self._snapshot().snapshot_id, api_request_id=request_id,
            )
        log.add_context(child_job_id=child_id)
        accepted = self._store_and_dispatch(child)
        stored = self._store.get(child_id)
        return json_response(202, {"schema_version": SCHEMA_VERSION, "challenge": (stored[0] if stored else child)["challenge"],
                                   "proposed_correction": None, "interpretation": None, "policy": policy, "investigation": accepted})


InvestigationApi = Api  # the phase 1 name, kept for callers that import it

_app: Api | None = None


def _build_app() -> Api:
    import boto3
    from botocore.config import Config

    from backend.common.clock import SystemClock
    from backend.common.data import S3SnapshotSource

    config = ApiConfig.from_env()
    clock = SystemClock()
    client_config = Config(retries={"total_max_attempts": 2, "mode": "standard"}, connect_timeout=2, read_timeout=5)
    s3 = boto3.client("s3", config=client_config)
    lambda_client = boto3.client("lambda", config=client_config)
    return Api(
        interpreter=_build_interpreter(boto3, Config, config, clock),
        store=JobStore(s3, config.data_bucket, clock, can_list=True),
        policies=PolicyStore(s3, config.data_bucket, can_list=True),
        snapshots=SnapshotLoader(S3SnapshotSource(s3, config.data_bucket, config.snapshot_id), config.snapshot_id),
        lambda_client=lambda_client,
        config=config,
        clock=clock,
    )


# One Converse call takes at most connect + read = 13 s, and a call is started only while 13 s of the 20 s budget
# (contracts/api.md, INTERPRET_TIMEOUT_SECONDS) are left. So a second call happens only after a fast failure, and
# the route always answers within about 20 s: before the function timeout and the 30 s API Gateway limit.
INTERPRETER_CONNECT_TIMEOUT_SECONDS = 1
INTERPRETER_READ_TIMEOUT_SECONDS = 12
INTERPRETER_CALL_BUDGET_SECONDS = float(INTERPRETER_CONNECT_TIMEOUT_SECONDS + INTERPRETER_READ_TIMEOUT_SECONDS)


def _build_interpreter(boto3: Any, config_class: Any, config: ApiConfig, clock: Any) -> Interpreter | None:
    if not config.interpreter_enabled or config.model_id is None:
        return None
    from backend.agents.bedrock_client import BedrockConverse

    # botocore's own retries are off: every attempt is made, counted and bounded by BedrockConverse.
    bedrock = boto3.client("bedrock-runtime", config=config_class(
        retries={"total_max_attempts": 1, "mode": "standard"},
        connect_timeout=INTERPRETER_CONNECT_TIMEOUT_SECONDS, read_timeout=INTERPRETER_READ_TIMEOUT_SECONDS))
    model = BedrockConverse(bedrock, config.model_id, clock, max_attempts=2, base_delay_seconds=0.5, max_delay_seconds=1.0,
                            min_call_budget_seconds=INTERPRETER_CALL_BUDGET_SECONDS)
    return Interpreter(model, clock, max_tokens=config.interpreter_max_tokens, call_budget_seconds=INTERPRETER_CALL_BUDGET_SECONDS)


def _get_app() -> Api:
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
