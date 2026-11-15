"""Investigation worker: claim the job, run the engine, let the model look, persist.

Delivery is at least once (Lambda's asynchronous queue can hand over the same
event twice), so the worker is idempotent by construction:

* it starts work only if it wins the compare-and-swap ``QUEUED -> RUNNING``;
  a delivery that finds the job RUNNING or terminal is a logged no-op;
* every later write requires the job to be RUNNING *and* owned by this
  invocation (the Lambda request id stored at claim time);
* results and traces are write-once objects.

So a job has at most one result, and a terminal job is never touched again.

The model does not own the calculation. Order of work:

1. Load the persona's portfolio, the stored policy version named by the job and
   the data snapshot. Failure: ``FAILED / DATA_UNAVAILABLE``, nothing assumed.
2. Run ``backend.engine.check_rules`` on the stored request. This happens before
   any model call and does not depend on one.
3. Let the model call read-only tools over that result (bounded rounds, calls,
   tokens and time) and propose context sentences.
4. Record ``check_rules`` and ``max_compliant_amount`` as SERVER steps, whatever
   the model called.
5. Explanation: the engine's template sentences, plus model sentences that
   pass ``backend.agents.explain``.

If the model fails, is throttled, runs out of rounds or time, or answers
nonsense, the deterministic result is still published: ``agent.mode`` becomes
``DETERMINISTIC_FALLBACK``, every step is a SERVER step and every sentence a
template (contracts/api.md, investigation_job.schema.json).
"""

from __future__ import annotations

import platform
from typing import Any

from byb_contracts import investigation_job_errors

from backend import engine
from backend.agents import explain, prompts
from backend.agents.bedrock_client import FAILURE_DEADLINE_EXCEEDED, BedrockConverse
from backend.agents.loop import LoopFailure, LoopLimits, LoopRecorder, run_tool_loop
from backend.agents.tools import ORIGIN_SERVER, STEP_SUCCEEDED, InvestigationContext, ToolEvent, ToolRegistry, build_investigation_registry
from backend.common import log
from backend.common.clock import from_iso, to_iso
from backend.common.config import WorkerConfig
from backend.common.data import DataUnavailable, SnapshotLoader
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
from backend.common.jobview import OUTCOME_SCHEMA_VERSION, mark_failed, public_view
from backend.common.policies import PolicyStore

# Failure codes of the contract (byb_contracts.FAILURE_CODES).
FAILURE_WORKER_ERROR = "WORKER_ERROR"
FAILURE_ENGINE_ERROR = "ENGINE_ERROR"
FAILURE_DATA_UNAVAILABLE = "DATA_UNAVAILABLE"

# Steps the server records itself in every investigation, after the model loop.
SERVER_ENFORCED_TOOLS = ("check_rules", "max_compliant_amount")
# The fixed sequence of a deterministic fallback (every step SERVER-initiated).
FALLBACK_TOOLS = ("get_portfolio", "get_policy", "simulate_change", "get_holdings", "compute_exposure", "replay_period") + SERVER_ENFORCED_TOOLS

# Stop this far before the job deadline so the final writes fit inside it.
JOB_DEADLINE_MARGIN_SECONDS = 5.0
# Stop this far before the Lambda timeout so the job can still be marked FAILED.
LAMBDA_TIMEOUT_MARGIN_SECONDS = 10.0

TRACE_SCHEMA_VERSION = 2

_DATA_MESSAGE = "The data needed for this check could not be read, so no check was run and no result was produced. Nothing was assumed in its place."
_FALLBACK_NOTE = "The language model did not complete its part ({code}). The checks were run by the service and every sentence is a template."
_FREE_TEXT_NOTE = "A free-text request is not resolved by a model in this build: the service asks instead of guessing an instrument or a number."


class JobAbandoned(Exception):
    """The job stopped being ours (for example it was expired). Write nothing more."""


class JobFailure(Exception):
    """Ends the job as FAILED with one of the contract's failure codes."""

    def __init__(self, code: str, message: str, retryable: bool) -> None:
        super().__init__(message)
        self.code, self.message, self.retryable = code, message, retryable


def _boto3_version() -> str:
    try:
        import boto3

        return boto3.__version__
    except Exception:  # noqa: BLE001 - version reporting must never break a job
        return "unknown"


class InvestigationWorker:
    def __init__(self, *, store: JobStore, model: BedrockConverse, snapshots: SnapshotLoader, policies: PolicyStore,
                 config: WorkerConfig, clock: Any, registry_factory: Any = build_investigation_registry) -> None:
        self._store = store
        self._model = model
        self._snapshots = snapshots
        self._policies = policies
        self._config = config
        self._clock = clock
        self._registry_factory = registry_factory

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
            draft["failure"] = {
                "code": FAILURE_DEADLINE_EXCEEDED,
                "message": "The investigation was not started before its deadline. Nothing was run.",
                "retryable": True,
            }
            return
        draft["status"] = RUNNING
        draft["internal"]["attempt"] = {"lambda_request_id": lambda_request_id, "claimed_at": to_iso(now)}

    # -------------------------------------------------------------------- run

    def _run(self, job: dict[str, Any], context: Any, owner: str) -> dict[str, Any]:
        job_id = job["id"]
        started = self._clock.time()
        recorder = LoopRecorder()
        extras: dict[str, Any] = {"explanation_rejections": [], "fallback": None, "data_snapshot_id": None}
        deadline = from_iso(job["deadline_at"]) - JOB_DEADLINE_MARGIN_SECONDS
        remaining = getattr(context, "get_remaining_time_in_millis", None)
        if callable(remaining):
            deadline = min(deadline, started + remaining() / 1000.0 - LAMBDA_TIMEOUT_MARGIN_SECONDS)

        def owned(draft: dict[str, Any]) -> None:
            if draft.get("status") != RUNNING or ((draft.get("internal") or {}).get("attempt") or {}).get("lambda_request_id") != owner:
                raise StateConflict("the job is no longer running under this invocation", draft)

        def record_step(event: ToolEvent, *, restart: bool = False) -> int:
            """Persist one completed tool action. A call to a name off the allowlist stays in the trace only."""
            seq = 0
            if event.is_public or restart:
                def mutate(draft: dict[str, Any]) -> None:
                    owned(draft)
                    if restart:
                        draft["steps"] = []
                    if event.is_public:
                        draft["steps"].append(event.to_step(len(draft["steps"]) + 1))
                    draft["agent"]["tool_rounds"] = recorder.rounds

                try:
                    updated = self._store.update(job_id, mutate)
                except (TerminalStateError, StateConflict) as error:
                    raise JobAbandoned(str(error)) from error
                seq = len(updated["steps"]) if event.is_public else 0
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

        try:
            snapshot, portfolio, policy = self._load(job)
            extras["data_snapshot_id"] = snapshot.snapshot_id
            if job["request"]["instrument_id"] is None:
                outcome, updates = self._clarify(job, snapshot, portfolio, record_step)
            else:
                outcome, updates = self._investigate(job, snapshot, portfolio, policy, deadline, recorder, record_step, extras)
            if self._clock.time() >= from_iso(job["deadline_at"]):
                raise JobFailure(FAILURE_DEADLINE_EXCEEDED, "The investigation finished after its deadline. No result is shown.", True)

            if not self._store.put_result(job_id, outcome):
                raise JobFailure(FAILURE_WORKER_ERROR, "A result already exists for this investigation.", False)
            self._store.put_trace(job_id, self._trace_document(job, recorder, context, started, SUCCEEDED, None, extras))

            def finalize(draft: dict[str, Any]) -> None:
                owned(draft)
                now = self._clock.time()
                draft["internal"]["trace_key"] = trace_key(job_id)
                if now >= from_iso(draft["deadline_at"]):
                    mark_failed(draft, {
                        "code": FAILURE_DEADLINE_EXCEEDED,
                        "message": "The investigation finished after its deadline. No result is shown.",
                        "retryable": True,
                    })
                else:
                    draft["status"] = SUCCEEDED
                    draft.update(updates)
                    draft["internal"]["result_key"] = result_key(job_id)
                    draft["internal"]["data_snapshot_id"] = snapshot.snapshot_id
                    draft["internal"]["calculation_version"] = engine.CALCULATION_VERSION

            final = self._store.update(job_id, finalize)
        except JobFailure as failure:
            log.warning("worker_failed", failure_code=failure.code)
            return self._fail(job, recorder, context, started, owner, failure, extras)
        except (JobAbandoned, TerminalStateError, StateConflict) as error:
            log.warning("worker_job_abandoned", reason=str(error))
            return {"outcome": "abandoned"}
        except Exception as error:
            log.error("worker_unexpected_error", error_type=type(error).__name__, error_message=str(error))
            try:
                self._fail(job, recorder, context, started, owner,
                           JobFailure(FAILURE_WORKER_ERROR, "The worker stopped on an unexpected error. No result was produced.", True), extras)
            except Exception as secondary:  # noqa: BLE001 - keep the original error; the deadline rule still fails the job
                log.error("worker_could_not_record_failure", error_type=type(secondary).__name__)
            raise

        totals = recorder.usage_totals()
        log.info(
            "worker_finished",
            status=final["status"],
            agent_mode=final["agent"]["mode"],
            steps=len(final["steps"]),
            data_snapshot_id=snapshot.snapshot_id,
            elapsed_ms=int(round((self._clock.time() - started) * 1000)),
            **totals,
        )
        return {"outcome": "completed", "status": final["status"]}

    # ------------------------------------------------------------------ parts

    def _load(self, job: dict[str, Any]) -> tuple[Any, dict[str, Any], dict[str, Any]]:
        try:
            snapshot = self._snapshots.load()
            policy = self._policies.get(job["policy_id"], job["policy_version"])
        except DataUnavailable as error:
            log.error("data_unavailable", reason=str(error))
            raise JobFailure(FAILURE_DATA_UNAVAILABLE, _DATA_MESSAGE, True) from error
        except Exception as error:  # noqa: BLE001 - storage errors while reading inputs
            log.error("data_unavailable", reason=type(error).__name__)
            raise JobFailure(FAILURE_DATA_UNAVAILABLE, _DATA_MESSAGE, True) from error
        scenario = snapshot.scenario(job["persona_id"])
        if scenario is None or policy is None or policy.get("persona_id") != job["persona_id"]:
            log.error("data_unavailable", reason="persona scenario or policy version not found")
            raise JobFailure(FAILURE_DATA_UNAVAILABLE, _DATA_MESSAGE, False)
        return snapshot, scenario["portfolio"], policy

    def _clarify(self, job: dict[str, Any], snapshot: Any, portfolio: dict[str, Any], record_step: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        """A free-text request: ask, never guess. The options are the scenario's own labelled demo requests."""
        words = job["request"]["original_words"]
        scenario = snapshot.scenario(job["persona_id"])
        now = to_iso(self._clock.time())
        event = ToolEvent(
            tool="get_portfolio", origin=ORIGIN_SERVER, tool_use_id=None, started_at=now, finished_at=now, duration_ms=0, status=STEP_SUCCEEDED,
            input_summary=f"Persona {job['persona_id']}.",
            result_summary=f"Fictional portfolio loaded: {len(portfolio['positions'])} positions, valuation date {portfolio['valuation_date']}.",
        )
        record_step(event)
        options = [
            {
                "option_id": demo["request_id"], "label": demo["label"],
                "description": "A request from the fictional scenario: a final direct weight, funded from cash.",
                "supported": True, "proposed_rule": None,
                "purchase_request": {**demo["purchase_request"], "original_words": words},
            }
            for demo in scenario.get("demo_requests", [])[:4]
        ]
        options.append({
            "option_id": "enter-instrument-and-weight", "label": "Choose the instrument and enter the final direct weight yourself",
            "description": "Use the purchase form: pick an instrument and type the final weight as a share of the portfolio.",
            "supported": True, "proposed_rule": None, "purchase_request": None,
        })
        options.append({
            "option_id": "sell-or-rebalance", "label": "Sell or rebalance existing positions",
            "description": "Not supported: only purchases funded from existing cash are simulated.",
            "supported": False, "proposed_rule": None, "purchase_request": None,
        })
        clarification = {
            "clarification_id": "clar-" + job["id"][4:16], "about_words": words,
            "question": "Which instrument, and which final direct weight (as a share of the portfolio), should be checked? The service does not guess a number.",
            "options": options,
        }
        agent = {"mode": "DETERMINISTIC_FALLBACK", "model_id": None, "tool_rounds": 0, "note": _FREE_TEXT_NOTE}
        outcome = self._outcome(job, snapshot, None, [], agent)
        self._validated(job, {"agent": agent, "clarification": clarification, "steps": [event.to_step(1)]}, outcome)
        return outcome, {"agent": agent, "clarification": clarification}

    def _investigate(self, job: dict[str, Any], snapshot: Any, portfolio: dict[str, Any], policy: dict[str, Any], deadline: float,
                     recorder: LoopRecorder, record_step: Any, extras: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        request = job["resolved_request"]
        # 2. The engine, server-side, before and independently of any model call.
        result = engine.check_rules(portfolio, policy, request, snapshot.instruments, snapshot.holdings, snapshot.market_data,
                                    snapshot.controversies, data_sources=snapshot.data_sources or None)
        if result["execution"]["status"] == "ERROR":
            log.error("engine_error", message=result["execution"]["message"])
            raise JobFailure(FAILURE_ENGINE_ERROR, "The calculation could not be completed, so no result was produced.", False)
        registry: ToolRegistry = self._registry_factory(InvestigationContext(
            portfolio=portfolio, policy=policy, request=request, result=result, holdings=snapshot.holdings, controversies=snapshot.controversies))

        # 3. The model looks at the result through read-only tools.
        candidates: list[Any] = []
        fallback: str | None = None
        try:
            text = run_tool_loop(
                model=self._model,
                registry=registry,
                system_prompt=prompts.INVESTIGATOR_SYSTEM_PROMPT,
                user_text=prompts.build_user_message(_model_view(job, request)),
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
            candidates = explain.parse_model_answer(text)
        except LoopFailure as failure:
            fallback = failure.code
            log.warning("model_fallback", failure_code=failure.code)

        # 4. Server-enforced steps. In a fallback the whole sequence is the server's.
        public: list[dict[str, Any]] = []
        if fallback is None:
            public = [event.to_step(seq) for seq, event in recorder.tool_events if seq]
        restart = fallback is not None
        for name in (FALLBACK_TOOLS if fallback is not None else SERVER_ENFORCED_TOOLS):
            event = registry.execute(name, {}, origin=ORIGIN_SERVER, clock=self._clock)
            if event.status != STEP_SUCCEEDED:
                raise JobFailure(FAILURE_WORKER_ERROR, "A required check could not be recorded, so no result is shown.", False)
            seq = record_step(event, restart=restart)
            restart = False
            public.append(event.to_step(seq))

        # 5. Explanation.
        templates = explain.template_statements(result)
        accepted: list[dict[str, Any]] = []
        if fallback is None:
            accepted, rejected = explain.render_highlights(candidates, result, len(templates))
            extras["explanation_rejections"] = rejected
        extras["fallback"] = fallback
        agent = {
            "mode": "MODEL" if fallback is None else "DETERMINISTIC_FALLBACK",
            "model_id": self._model.model_id if fallback is None else None,
            "tool_rounds": recorder.rounds if fallback is None else 0,
            "note": None if fallback is None else _FALLBACK_NOTE.format(code=fallback),
        }
        statements = _numbered(templates[:-1] + accepted + templates[-1:])
        outcome = self._outcome(job, snapshot, result, statements, agent, policy)
        try:
            self._validated(job, {"agent": agent, "steps": public}, outcome)
        except JobFailure:
            if not accepted:
                raise
            # A model sentence broke the document: drop every model sentence and keep the templates.
            extras["explanation_rejections"].append({"index": -1, "reason": "the job document was invalid with the selected evidence sentences"})
            outcome = self._outcome(job, snapshot, result, _numbered(templates), agent, policy)
            self._validated(job, {"agent": agent, "steps": public}, outcome)
        return outcome, {"agent": agent}

    def _outcome(self, job: dict[str, Any], snapshot: Any, result: dict[str, Any] | None, explanation: list[dict[str, Any]],
                 agent: dict[str, Any], policy: dict[str, Any] | None = None) -> dict[str, Any]:
        """The write-once object behind ``result`` and ``explanation``, with the identity of its inputs."""
        return {
            "schema_version": OUTCOME_SCHEMA_VERSION,
            "kind": "investigation_outcome",
            "investigation_id": job["id"],
            "generated_at": to_iso(self._clock.time()),
            "result": result,
            "explanation": explanation,
            "agent": agent,
            "inputs": {
                "data_snapshot_id": snapshot.snapshot_id,
                "calculation_version": engine.CALCULATION_VERSION,
                "persona_id": job["persona_id"],
                "policy_id": job["policy_id"],
                "policy_version": job["policy_version"],
                "policy_content_hash": policy["content_hash"] if policy else None,
                "prompt_version": prompts.PROMPT_VERSION,
            },
        }

    def _validated(self, job: dict[str, Any], updates: dict[str, Any], outcome: dict[str, Any]) -> None:
        """Nothing is published unless the finished job is a valid contract document."""
        candidate = dict(job, status=SUCCEEDED, updated_at=to_iso(self._clock.time()), **updates)
        errors = investigation_job_errors(public_view(candidate, outcome))
        if errors:
            log.error("job_document_invalid", errors=errors[:5])
            raise JobFailure(FAILURE_ENGINE_ERROR, "The result did not pass its own consistency checks, so it is not shown.", False)

    def _fail(self, job: dict[str, Any], recorder: LoopRecorder, context: Any, started: float, owner: str, failure_error: JobFailure,
              extras: dict[str, Any]) -> dict[str, Any]:
        job_id = job["id"]
        failure = {"code": failure_error.code, "message": failure_error.message, "retryable": failure_error.retryable}
        trace_written = False
        try:
            self._store.put_trace(job_id, self._trace_document(job, recorder, context, started, FAILED, failure, extras))
            trace_written = True
        except Exception as error:  # noqa: BLE001 - the trace is best effort; the job state is not
            log.error("trace_write_failed", error_type=type(error).__name__)

        def mutate(draft: dict[str, Any]) -> None:
            if draft.get("status") != RUNNING or ((draft.get("internal") or {}).get("attempt") or {}).get("lambda_request_id") != owner:
                raise StateConflict("the job is no longer running under this invocation", draft)
            mark_failed(draft, failure)
            if trace_written:
                draft["internal"]["trace_key"] = trace_key(job_id)

        try:
            self._store.update(job_id, mutate)
        except (TerminalStateError, StateConflict) as error:
            log.warning("worker_job_abandoned", reason=str(error))
            return {"outcome": "abandoned"}
        return {"outcome": "completed", "status": FAILED, "failure_code": failure_error.code}

    # -------------------------------------------------------------- documents

    def _trace_document(self, job: dict[str, Any], recorder: LoopRecorder, context: Any, started: float, outcome: str, failure: dict[str, Any] | None,
                        extras: dict[str, Any]) -> dict[str, Any]:
        now = self._clock.time()
        return {
            "schema_version": TRACE_SCHEMA_VERSION,
            "kind": "investigation_trace",
            "investigation_id": job["id"],
            "outcome": outcome,
            "failure": failure,
            "data_snapshot_id": extras.get("data_snapshot_id"),
            "calculation_version": engine.CALCULATION_VERSION,
            "policy": {"policy_id": job.get("policy_id"), "policy_version": job.get("policy_version")},
            "model_fallback": extras.get("fallback"),
            "explanation_rejections": extras.get("explanation_rejections", []),
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


def _numbered(statements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [dict(statement, statement_id=f"st-{index + 1}") for index, statement in enumerate(statements)]


def _model_view(job: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
    """The part of the stored request the model is shown. ``original_words`` is untrusted user text."""
    return {
        "persona_id": job["persona_id"],
        "policy_id": job["policy_id"],
        "policy_version": job["policy_version"],
        "instrument_id": request["instrument_id"],
        "target_direct_weight": request["target_direct_weight"],
        "funding": request["funding"],
        "original_words_untrusted_text": request.get("original_words"),
    }
