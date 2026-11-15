"""Bedrock Converse wrapper with bounded, deadline-aware retries.

botocore's own retries are switched off for this client (see
``backend/worker/handler.py``) so that every attempt is visible here, is
counted in the trace and can be stopped by the job deadline.

Request shape notes for the configured model (Claude Sonnet 5.5):

* ``maxTokens`` is always sent. Leaving it out reserves the model maximum
  against the account quota and is a common cause of throttling.
* No ``temperature`` / ``topP`` and no forced ``toolChoice``: this model
  generation rejects non-default sampling parameters and forced tool choice.
  The server does not rely on the model calling a tool anyway.
"""

from __future__ import annotations

import random
from typing import Any, Callable

from botocore.exceptions import (
    ClientError,
    ConnectionClosedError,
    ConnectTimeoutError,
    EndpointConnectionError,
    ReadTimeoutError,
)

from backend.common import log

FAILURE_MODEL_THROTTLED = "MODEL_THROTTLED"
FAILURE_MODEL_ERROR = "MODEL_ERROR"
FAILURE_DEADLINE_EXCEEDED = "DEADLINE_EXCEEDED"

THROTTLING_CODES = frozenset({"ThrottlingException", "TooManyRequestsException"})
RETRYABLE_CODES = THROTTLING_CODES | frozenset(
    {
        "ModelTimeoutException",
        "ModelNotReadyException",
        "ServiceUnavailableException",
        "InternalServerException",
    }
)
_TRANSPORT_ERRORS = (ReadTimeoutError, ConnectTimeoutError, EndpointConnectionError, ConnectionClosedError)


class ModelCallError(Exception):
    """A Converse call failed for good. ``code`` is a job failure code."""

    def __init__(self, code: str, message: str, *, aws_error: str | None = None, attempts: int = 0) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.aws_error = aws_error
        self.attempts = attempts


class BedrockConverse:
    def __init__(
        self,
        client: Any,
        model_id: str,
        clock: Any,
        *,
        max_attempts: int = 4,
        base_delay_seconds: float = 1.0,
        max_delay_seconds: float = 8.0,
        min_call_budget_seconds: float = 3.0,
        rng: Callable[[], float] = random.random,
    ) -> None:
        self._client = client
        self.model_id = model_id
        self._clock = clock
        self._max_attempts = max_attempts
        self._base_delay = base_delay_seconds
        self._max_delay = max_delay_seconds
        self._min_call_budget = min_call_budget_seconds
        self._rng = rng

    def converse(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tool_config: dict[str, Any],
        max_tokens: int,
        deadline: float,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Return ``(response, call_record)``. ``deadline`` is epoch seconds."""
        retries: list[dict[str, Any]] = []
        attempt = 0
        while True:
            started = self._clock.time()
            if deadline - started < self._min_call_budget:
                raise ModelCallError(
                    FAILURE_DEADLINE_EXCEEDED,
                    "The investigation ran out of time before the model could be called.",
                    attempts=attempt,
                )
            attempt += 1
            try:
                response = self._client.converse(
                    modelId=self.model_id,
                    system=[{"text": system}],
                    messages=messages,
                    toolConfig=tool_config,
                    inferenceConfig={"maxTokens": max_tokens},
                )
            except ClientError as error:
                aws_error = str(error.response.get("Error", {}).get("Code", "Unknown"))
                retryable = aws_error in RETRYABLE_CODES
                failure = FAILURE_MODEL_THROTTLED if aws_error in THROTTLING_CODES else FAILURE_MODEL_ERROR
            except _TRANSPORT_ERRORS as error:
                aws_error = type(error).__name__
                retryable = True
                failure = FAILURE_MODEL_ERROR
            else:
                finished = self._clock.time()
                usage = response.get("usage") or {}
                record = {
                    "attempts": attempt,
                    "retries": retries,
                    "stop_reason": response.get("stopReason"),
                    "usage": {
                        "input_tokens": usage.get("inputTokens"),
                        "output_tokens": usage.get("outputTokens"),
                        "total_tokens": usage.get("totalTokens"),
                        "cache_read_input_tokens": usage.get("cacheReadInputTokens"),
                        "cache_write_input_tokens": usage.get("cacheWriteInputTokens"),
                    },
                    "bedrock_latency_ms": (response.get("metrics") or {}).get("latencyMs"),
                    "wall_ms": int(round((finished - started) * 1000)),
                    "request_id": (response.get("ResponseMetadata") or {}).get("RequestId"),
                }
                return response, record

            if not retryable or attempt >= self._max_attempts:
                raise ModelCallError(
                    failure,
                    f"The model call failed ({aws_error}) after {attempt} attempt(s).",
                    aws_error=aws_error,
                    attempts=attempt,
                )
            # Exponential backoff with jitter: 50-100% of 1 s, 2 s, 4 s, ... capped.
            delay = min(self._max_delay, self._base_delay * (2 ** (attempt - 1))) * (0.5 + 0.5 * self._rng())
            if self._clock.time() + delay + self._min_call_budget > deadline:
                raise ModelCallError(
                    failure,
                    f"The model call failed ({aws_error}) and there was no time left to retry.",
                    aws_error=aws_error,
                    attempts=attempt,
                )
            retries.append({"attempt": attempt, "error": aws_error, "delay_ms": int(round(delay * 1000))})
            log.warning("bedrock_retry", attempt=attempt, aws_error=aws_error, delay_ms=int(round(delay * 1000)))
            self._clock.sleep(delay)
