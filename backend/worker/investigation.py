"""Investigation worker: claim the job, run the bounded tool loop, persist.

Delivery is at least once (Lambda's asynchronous queue can hand over the same
event twice), so the worker is idempotent by construction:

* it starts work only if it wins the compare-and-swap ``QUEUED -> RUNNING``;
  a delivery that finds the job RUNNING or terminal is a logged no-op;
* every later write requires the job to be RUNNING *and* owned by this
  invocation (the Lambda request id stored at claim time);
* results and traces are write-once objects.

So a job has at most one result, and a terminal job is never touched again.

The model does not own the calculation. Whatever it did or did not call, the
server makes sure the required tool ran with the arguments of the stored
request, and the result is built from that execution only.
"""

from __future__ import annotations

import platform
from typing import Any

from backend.agents import prompts
from backend.agents.bedrock_client import FAILURE_DEADLINE_EXCEEDED, BedrockConverse
from backend.agents.loop import LoopFailure, LoopLimits, LoopRecorder, run_tool_loop
from backend.agents.tools import ORIGIN_SERVER, STEP_SUCCEEDED, ToolEvent, ToolRegistry
from backend.common import log
from backend.common.clock import from_iso, to_iso
from backend.common.config import WorkerConfig
from backend.common.jobs import (
    FAILED,
    QUEUED,
    RUNNING,
    SUCCEEDED,
    JobNotFoundError,
    JobStore,
    StateConflict,
    TerminalStateError,
    is_valid_job_id,
    result_key,
    trace_key,
)

FAILURE_INTERNAL_ERROR = "INTERNAL_ERROR"
REQUIRED_TOOL = "compute_exposure"

# Stop this far before the job deadline so the final writes fit inside it.
JOB_DEADLINE_MARGIN_SECONDS = 5.0
# Stop this far before the Lambda timeout so the job can still be marked FAILED.
LAMBDA_TIMEOUT_MARGIN_SECONDS = 10.0

RESULT_SCHEMA_VERSION = 1
TRACE_SCHEMA_VERSION = 1


class JobAbandoned(Exception):
    """The job stopped being ours (for example it was expired). Write nothing more."""


def _boto3_version() -> str:
    try:
        import boto3

        return boto3.__version__
    except Exception:  # noqa: BLE001 - version reporting must never break a job
        return "unknown"


class InvestigationWorker:
    def __init__(self, *, store: JobStore, model: BedrockConverse, registry: ToolRegistry, config: WorkerConfig, clock: Any) -> None:
        self._store = store
        self._model = model
        self._registry = registry
        self._config = config
        self._clock = clock

    # ------------------------------------------------------------------ entry

    def handle(self, event: Any, context: Any) -> dict[str, Any]:
        job_id = event.get("job_id") if isinstance(event, dict) else None
        lambda_request_id = getattr(context, "aws_request_id", None) or "unknown"
        log.bind(component="worker", job_id=job_id if is_valid_job_id(job_id) else None, lambda_request_id=lambda_request_id)
        if not is_valid_job_id(job_id):
            log.error("worker_invalid_event")
            return {"outcome": "ignored", "reason": "invalid_event"}

        try:
            job = self._store.update(job_id, lambda draft: self._claim(draft, lambda_request_id))
        except TerminalStateError as error:
            log.info("worker_duplicate_delivery", status=error.job.get("status"))
            return {"outcome": "duplicate", "status": error.job.get("status")}
        except StateConflict as error:
            status = (error.job or {}).get("status")
            log.info("worker_duplicate_delivery", status=status)
            return {"outcome": "duplicate", "status": status}
        except JobNotFoundError:
            log.error("worker_job_not_found")
            return {"outcome": "ignored", "reason": "job_not_found"}

        if job["status"] == FAILED:
            log.warning("worker_job_expired_before_start", deadline_at=job.get("deadline_at"))
            return {"outcome": "expired", "status": FAILED}

        log.info("worker_claimed", deadline_at=job["deadline_at"], model_id=self._model.model_id)
        return self._run(job, context, lambda_request_id)

    def _claim(self, draft: dict[str, Any], lambda_request_id: str) -> None:
        if draft.get("status") != QUEUED:
            raise StateConflict("the job is not queued", draft)
        now = self._clock.time()
        if now >= from_iso(draft["deadline_at"]):
            draft["status"] = FAILED
            draft["finished_at"] = to_iso(now)
            draft["error"] = {
                "code": FAILURE_DEADLINE_EXCEEDED,
                "message": "The investigation was not started before its deadline.",
            }
            return
        draft["status"] = RUNNING
        draft["started_at"] = to_iso(now)
        draft["attempt"] = {"lambda_request_id": lambda_request_id, "claimed_at": to_iso(now)}

    # -------------------------------------------------------------------- run

    def _run(self, job: dict[str, Any], context: Any, owner: str) -> dict[str, Any]:
        job_id = job["id"]
        started = self._clock.time()
        recorder = LoopRecorder()
        deadline = from_iso(job["deadline_at"]) - JOB_DEADLINE_MARGIN_SECONDS
        remaining = getattr(context, "get_remaining_time_in_millis", None)
        if callable(remaining):
            deadline = min(deadline, started + remaining() / 1000.0 - LAMBDA_TIMEOUT_MARGIN_SECONDS)

        def owned(draft: dict[str, Any]) -> None:
            if draft.get("status") != RUNNING or (draft.get("attempt") or {}).get("lambda_request_id") != owner:
                raise StateConflict("the job is no longer running under this invocation", draft)

        def record_step(event: ToolEvent) -> int:
            def mutate(draft: dict[str, Any]) -> None:
                owned(draft)
                draft["steps"].append(event.to_step(len(draft["steps"]) + 1))

            try:
                updated = self._store.update(job_id, mutate)
            except (TerminalStateError, StateConflict) as error:
                raise JobAbandoned(str(error)) from error
            seq = len(updated["steps"])
            recorder.tool_events.append((seq, event))
            log.info(
                "tool_event",
                seq=seq,
                tool=event.tool,
                origin=event.origin,
                status=event.status,
                duration_ms=event.duration_ms,
                input_summary=event.input_summary,
                result_summary=event.result_summary,
                error_code=(event.error or {}).get("code"),
            )
            return seq

        request = job["request"]
        try:
            text = run_tool_loop(
                model=self._model,
                registry=self._registry,
                system_prompt=prompts.INVESTIGATOR_SYSTEM_PROMPT,
                user_text=prompts.build_user_message(_model_view(request)),
                limits=LoopLimits(
                    max_tool_rounds=self._config.max_tool_rounds,
                    max_tool_calls=self._config.max_tool_calls,
                    max_tokens=self._config.max_tokens,
                ),
                deadline=deadline,
                clock=self._clock,
                on_tool_event=record_step,
                recorder=recorder,
            )
            seq, exposure = self._required_calculation(request, recorder, record_step)
            if self._clock.time() >= from_iso(job["deadline_at"]):
                raise LoopFailure(FAILURE_DEADLINE_EXCEEDED, "The investigation finished after its deadline.")

            result = self._result_document(job, text, seq, exposure, recorder)
            if not self._store.put_result(job_id, result):
                raise LoopFailure(FAILURE_INTERNAL_ERROR, "A result already exists for this investigation.")
            self._store.put_trace(job_id, self._trace_document(job, recorder, context, started, SUCCEEDED, None))

            def finalize(draft: dict[str, Any]) -> None:
                owned(draft)
                now = self._clock.time()
                draft["finished_at"] = to_iso(now)
                draft["trace_key"] = trace_key(job_id)
                if now >= from_iso(draft["deadline_at"]):
                    draft["status"] = FAILED
                    draft["error"] = {
                        "code": FAILURE_DEADLINE_EXCEEDED,
                        "message": "The investigation finished after its deadline.",
                    }
                else:
                    draft["status"] = SUCCEEDED
                    draft["result_key"] = result_key(job_id)

            final = self._store.update(job_id, finalize)
        except LoopFailure as failure:
            log.warning("worker_failed", failure_code=failure.code)
            return self._fail(job, recorder, context, started, owner, failure.code, failure.message)
        except (JobAbandoned, TerminalStateError, StateConflict) as error:
            log.warning("worker_job_abandoned", reason=str(error))
            return {"outcome": "abandoned"}
        except Exception as error:
            log.error("worker_unexpected_error", error_type=type(error).__name__, error_message=str(error))
            try:
                self._fail(job, recorder, context, started, owner, FAILURE_INTERNAL_ERROR, "The worker stopped on an unexpected error.")
            except Exception as secondary:  # noqa: BLE001 - keep the original error; the deadline rule still fails the job
                log.error("worker_could_not_record_failure", error_type=type(secondary).__name__)
            raise

        totals = recorder.usage_totals()
        log.info(
            "worker_finished",
            status=final["status"],
            steps=len(final["steps"]),
            elapsed_ms=int(round((self._clock.time() - started) * 1000)),
            **totals,
        )
        return {"outcome": "completed", "status": final["status"]}

    def _required_calculation(self, request: dict[str, Any], recorder: LoopRecorder, record_step: Any) -> tuple[int, dict[str, Any]]:
        """Server-side enforcement: the result never depends on the model's choices."""
        canonical = {
            "instrument_id": request["purchase"]["instrument_id"],
            "target_direct_weight": request["purchase"]["target_direct_weight"],
        }
        for seq, event in recorder.tool_events:
            if event.tool == REQUIRED_TOOL and event.status == STEP_SUCCEEDED and event.arguments == canonical:
                return seq, event.output  # type: ignore[return-value]
        event = self._registry.execute(REQUIRED_TOOL, canonical, origin=ORIGIN_SERVER, clock=self._clock)
        seq = record_step(event)
        if event.status != STEP_SUCCEEDED or event.output is None:
            raise LoopFailure(FAILURE_INTERNAL_ERROR, "The required calculation could not be run.")
        log.info("server_enforced_calculation", seq=seq, tool=REQUIRED_TOOL)
        return seq, event.output

    def _fail(self, job: dict[str, Any], recorder: LoopRecorder, context: Any, started: float, owner: str, code: str, message: str) -> dict[str, Any]:
        job_id = job["id"]
        failure = {"code": code, "message": message}
        trace_written = False
        try:
            self._store.put_trace(job_id, self._trace_document(job, recorder, context, started, FAILED, failure))
            trace_written = True
        except Exception as error:  # noqa: BLE001 - the trace is best effort; the job state is not
            log.error("trace_write_failed", error_type=type(error).__name__)

        def mutate(draft: dict[str, Any]) -> None:
            if draft.get("status") != RUNNING or (draft.get("attempt") or {}).get("lambda_request_id") != owner:
                raise StateConflict("the job is no longer running under this invocation", draft)
            draft["status"] = FAILED
            draft["finished_at"] = to_iso(self._clock.time())
            draft["error"] = failure
            if trace_written:
                draft["trace_key"] = trace_key(job_id)

        try:
            self._store.update(job_id, mutate)
        except (TerminalStateError, StateConflict) as error:
            log.warning("worker_job_abandoned", reason=str(error))
            return {"outcome": "abandoned"}
        return {"outcome": "completed", "status": FAILED, "failure_code": code}

    # -------------------------------------------------------------- documents

    def _result_document(self, job: dict[str, Any], text: str, seq: int, exposure: dict[str, Any], recorder: LoopRecorder) -> dict[str, Any]:
        origin = next(event.origin for step, event in recorder.tool_events if step == seq)
        return {
            "schema_version": RESULT_SCHEMA_VERSION,
            "kind": "investigation_result",
            "investigation_id": job["id"],
            "generated_at": to_iso(self._clock.time()),
            "placeholder": bool(exposure.get("placeholder")),
            "request": job["request"],
            # From a deterministic tool run by the server with the stored
            # request's arguments. Never taken from model text.
            "exposure": exposure,
            "exposure_source": {"step_seq": seq, "tool": REQUIRED_TOOL, "origin": origin},
            "explanation": {
                "text": text,
                "author": "model",
                "model_id": self._model.model_id,
                "prompt_version": prompts.PROMPT_VERSION,
                "verified_against_evidence": False,
                "note": "Model-written text. Phase 1 does not check its statements against evidence records.",
            },
            "usage": recorder.usage_totals(),
            "trace_key": trace_key(job["id"]),
        }

    def _trace_document(self, job: dict[str, Any], recorder: LoopRecorder, context: Any, started: float, outcome: str, failure: dict[str, str] | None) -> dict[str, Any]:
        now = self._clock.time()
        return {
            "schema_version": TRACE_SCHEMA_VERSION,
            "kind": "investigation_trace",
            "investigation_id": job["id"],
            "outcome": outcome,
            "failure": failure,
            "written_at": to_iso(now),
            "timing": {
                "job_created_at": job.get("created_at"),
                "job_deadline_at": job.get("deadline_at"),
                "worker_started_at": to_iso(started),
                "worker_elapsed_ms": int(round((now - started) * 1000)),
            },
            "model": {
                "model_id": self._model.model_id,
                "prompt_version": prompts.PROMPT_VERSION,
                "system_prompt_sha256": prompts.system_prompt_sha256(),
                "limits": {
                    "max_tool_rounds": self._config.max_tool_rounds,
                    "max_tool_calls": self._config.max_tool_calls,
                    "max_tokens": self._config.max_tokens,
                },
                "tool_rounds_used": recorder.rounds,
            },
            "usage_totals": recorder.usage_totals(),
            "model_calls": recorder.model_calls,
            "tool_events": [dict(event.to_trace(), seq=seq) for seq, event in recorder.tool_events],
            "transcript": recorder.transcript(),
            "runtime": {
                "lambda_request_id": getattr(context, "aws_request_id", None),
                "function_name": getattr(context, "function_name", None),
                "function_version": getattr(context, "function_version", None),
                "memory_limit_mb": _as_int(getattr(context, "memory_limit_in_mb", None)),
                "python_version": platform.python_version(),
                "boto3_version": _boto3_version(),
                "code_artifact": self._config.code_artifact,
            },
        }


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _model_view(request: dict[str, Any]) -> dict[str, Any]:
    """The part of the stored request the model is shown."""
    view = {
        "persona_id": request["persona_id"],
        "instrument_id": request["purchase"]["instrument_id"],
        "target_direct_weight": request["purchase"]["target_direct_weight"],
    }
    if request.get("question"):
        view["question"] = request["question"]
    return view
