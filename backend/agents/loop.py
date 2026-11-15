"""Bounded Converse tool loop.

Bounds, all enforced here:

* tool rounds   - a "round" is one model turn that asks for tools. Round
  ``max_tool_rounds + 1`` is refused: none of its tools run and the loop
  fails with ``TOOL_ROUNDS_EXCEEDED``.
* tool calls    - total across rounds (a single turn may ask for several).
* output tokens - ``maxTokens`` on every call.
* total runtime - every model call is given the job deadline.
* retries       - see ``bedrock_client``.

The assistant message is appended to the history exactly as the model
returned it (including any reasoning blocks, which must go back unchanged),
and the history is append-only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from backend.agents.bedrock_client import BedrockConverse, ModelCallError
from backend.agents.tools import STEP_SUCCEEDED, ORIGIN_MODEL, ToolEvent, ToolRegistry
from backend.common import log

FAILURE_TOOL_ROUNDS_EXCEEDED = "TOOL_ROUNDS_EXCEEDED"
FAILURE_TOOL_CALLS_EXCEEDED = "TOOL_CALLS_EXCEEDED"
FAILURE_MODEL_OUTPUT_TRUNCATED = "MODEL_OUTPUT_TRUNCATED"
FAILURE_MODEL_STOPPED = "MODEL_STOPPED"
FAILURE_MODEL_EMPTY_RESPONSE = "MODEL_EMPTY_RESPONSE"

MAX_TRANSCRIPT_TEXT = 4000


@dataclass(frozen=True)
class LoopLimits:
    max_tool_rounds: int = 6
    max_tool_calls: int = 16
    max_tokens: int = 4096


class LoopFailure(Exception):
    """The loop stopped without a usable answer. ``code`` is a job failure code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class LoopRecorder:
    """Filled in as the loop runs, so a failure still leaves a usable trace."""

    model_calls: list[dict[str, Any]] = field(default_factory=list)
    # (seq, event) pairs, appended by the caller once the step is persisted.
    tool_events: list[tuple[int, ToolEvent]] = field(default_factory=list)
    messages: list[dict[str, Any]] = field(default_factory=list)
    rounds: int = 0

    def usage_totals(self) -> dict[str, Any]:
        def total(path: tuple[str, ...]) -> int:
            amount = 0
            for call in self.model_calls:
                value: Any = call
                for part in path:
                    value = (value or {}).get(part)
                amount += value or 0
            return amount

        return {
            "model_calls": len(self.model_calls),
            "model_attempts": total(("attempts",)),
            "input_tokens": total(("usage", "input_tokens")),
            "output_tokens": total(("usage", "output_tokens")),
            "total_tokens": total(("usage", "total_tokens")),
            "bedrock_latency_ms": total(("bedrock_latency_ms",)),
            "model_wall_ms": total(("wall_ms",)),
        }

    def transcript(self) -> list[dict[str, Any]]:
        """History for the trace: observable content only, no private reasoning."""
        cleaned = []
        for message in self.messages:
            blocks = []
            for block in message.get("content", []):
                if "text" in block:
                    text = block["text"]
                    if len(text) > MAX_TRANSCRIPT_TEXT:
                        text = text[:MAX_TRANSCRIPT_TEXT] + "...[truncated]"
                    blocks.append({"text": text})
                elif "toolUse" in block:
                    use = block["toolUse"]
                    blocks.append({"toolUse": {"toolUseId": use.get("toolUseId"), "name": use.get("name"), "input": use.get("input")}})
                elif "toolResult" in block:
                    blocks.append({"toolResult": block["toolResult"]})
                elif "reasoningContent" in block:
                    blocks.append({"omitted": "reasoningContent"})
                else:
                    blocks.append({"omitted": sorted(block)[0] if block else "empty"})
            cleaned.append({"role": message.get("role"), "content": blocks})
        return cleaned


def _tool_result_block(event: ToolEvent) -> dict[str, Any]:
    if event.status == STEP_SUCCEEDED:
        return {"toolResult": {"toolUseId": event.tool_use_id, "status": "success", "content": [{"json": event.output}]}}
    error = event.error or {}
    text = f"Tool call was not completed ({error.get('code', 'ERROR')}): {error.get('message', 'no detail')}"
    return {"toolResult": {"toolUseId": event.tool_use_id, "status": "error", "content": [{"text": text}]}}


def run_tool_loop(
    *,
    model: BedrockConverse,
    registry: ToolRegistry,
    system_prompt: str,
    user_text: str,
    limits: LoopLimits,
    deadline: float,
    clock: Any,
    on_tool_event: Callable[[ToolEvent], Any],
    recorder: LoopRecorder,
) -> str:
    """Run the loop and return the model's final text.

    ``on_tool_event`` is called once per tool call, right after it completes
    and before the next model call, so the caller can persist the step. Any
    exception it raises stops the loop and propagates.
    """
    messages = recorder.messages
    messages.append({"role": "user", "content": [{"text": user_text}]})
    tool_config = registry.tool_config()
    tool_calls = 0

    while True:
        try:
            response, call_record = model.converse(
                system=system_prompt,
                messages=messages,
                tool_config=tool_config,
                max_tokens=limits.max_tokens,
                deadline=deadline,
            )
        except ModelCallError as error:
            raise LoopFailure(error.code, error.message) from error
        call_record["seq"] = len(recorder.model_calls) + 1
        recorder.model_calls.append(call_record)
        log.info(
            "bedrock_call",
            seq=call_record["seq"],
            stop_reason=call_record["stop_reason"],
            attempts=call_record["attempts"],
            input_tokens=call_record["usage"]["input_tokens"],
            output_tokens=call_record["usage"]["output_tokens"],
            bedrock_latency_ms=call_record["bedrock_latency_ms"],
            wall_ms=call_record["wall_ms"],
        )

        message = (response.get("output") or {}).get("message") or {"role": "assistant", "content": []}
        messages.append(message)
        stop_reason = response.get("stopReason")
        content = message.get("content") or []

        if stop_reason == "tool_use":
            requested = [block["toolUse"] for block in content if "toolUse" in block]
            if not requested:
                raise LoopFailure(FAILURE_MODEL_STOPPED, "The model stopped for a tool call without naming a tool.")
            if recorder.rounds >= limits.max_tool_rounds:
                raise LoopFailure(
                    FAILURE_TOOL_ROUNDS_EXCEEDED,
                    f"The model asked for more than {limits.max_tool_rounds} rounds of tool calls.",
                )
            recorder.rounds += 1
            results = []
            for use in requested:
                if tool_calls >= limits.max_tool_calls:
                    raise LoopFailure(
                        FAILURE_TOOL_CALLS_EXCEEDED,
                        f"The model asked for more than {limits.max_tool_calls} tool calls.",
                    )
                tool_calls += 1
                event = registry.execute(
                    use.get("name"),
                    use.get("input"),
                    origin=ORIGIN_MODEL,
                    clock=clock,
                    tool_use_id=use.get("toolUseId"),
                )
                on_tool_event(event)
                results.append(_tool_result_block(event))
            messages.append({"role": "user", "content": results})
            continue

        if stop_reason == "end_turn":
            text = "".join(block["text"] for block in content if "text" in block).strip()
            if not text:
                raise LoopFailure(FAILURE_MODEL_EMPTY_RESPONSE, "The model finished without writing an answer.")
            return text

        if stop_reason == "max_tokens":
            raise LoopFailure(FAILURE_MODEL_OUTPUT_TRUNCATED, "The model's answer was cut off at the output token limit.")
        raise LoopFailure(FAILURE_MODEL_STOPPED, f"The model stopped unexpectedly (stop reason: {str(stop_reason)[:40]}).")
