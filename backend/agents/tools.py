"""Tool registry: the allowlist, schema enforcement and event records.

A tool call requested by the model is executed only if

1. its name is exactly one of the registered names, and
2. its arguments validate against that tool's input schema.

Anything else is REJECTED: recorded as an event, reported back to the model as
an error result, and never executed.

Phase 1 registers a single tool, ``compute_exposure``, whose calculation is a
clearly labelled PLACEHOLDER. Phase 2 replaces the handler with a call into
``backend/engine`` and registers the rest of the allowlist from the build
brief (section 6); nothing else in this module needs to change.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable

from backend.agents import schema as schema_validator
from backend.common.clock import to_iso

STEP_SUCCEEDED = "SUCCEEDED"
STEP_FAILED = "FAILED"
STEP_REJECTED = "REJECTED"

ORIGIN_MODEL = "model"
ORIGIN_SERVER = "server"

ERROR_UNKNOWN_TOOL = "UNKNOWN_TOOL"
ERROR_INVALID_ARGUMENTS = "INVALID_ARGUMENTS"
ERROR_TOOL_ERROR = "TOOL_ERROR"

MAX_SUMMARY = 240

PLACEHOLDER_CALCULATION_VERSION = "phase1-placeholder-1"


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[[dict[str, Any]], dict[str, Any]]
    summarize_input: Callable[[dict[str, Any]], str]
    summarize_result: Callable[[dict[str, Any]], str]


@dataclass
class ToolEvent:
    """One attempted tool call. ``to_step`` is what the job document stores."""

    tool: str
    origin: str
    tool_use_id: str | None
    started_at: str
    finished_at: str
    duration_ms: int
    status: str
    input_summary: str
    result_summary: str
    error: dict[str, str] | None = None
    # Kept for the trace and the result, not copied into the job's steps.
    arguments: dict[str, Any] | None = field(default=None, repr=False)
    output: dict[str, Any] | None = field(default=None, repr=False)

    def to_step(self, seq: int) -> dict[str, Any]:
        return {
            "seq": seq,
            "tool": self.tool,
            "origin": self.origin,
            "tool_use_id": self.tool_use_id,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_ms": self.duration_ms,
            "status": self.status,
            "input_summary": self.input_summary,
            "result_summary": self.result_summary,
            "error": self.error,
        }

    def to_trace(self) -> dict[str, Any]:
        record = self.to_step(0)
        del record["seq"]
        record["arguments"] = self.arguments
        record["output"] = self.output
        return record


def _clip(text: str, limit: int = MAX_SUMMARY) -> str:
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _safe_name(name: Any) -> str:
    text = name if isinstance(name, str) else f"<{type(name).__name__}>"
    cleaned = "".join(ch if (ch.isascii() and (ch.isalnum() or ch in "_-.")) else "?" for ch in text[:64])
    return cleaned or "<empty>"


def _describe_untrusted(arguments: Any) -> str:
    """Shape of rejected arguments: key names and value types, never values."""
    if not isinstance(arguments, dict):
        return f"arguments were not an object ({type(arguments).__name__})"
    if not arguments:
        return "no arguments"
    parts = [f"{_safe_name(key)}:{type(value).__name__}" for key, value in list(arguments.items())[:8]]
    more = len(arguments) - 8
    return _clip("argument types: " + ", ".join(parts) + (f", +{more} more" if more > 0 else ""))


class ToolRegistry:
    def __init__(self, specs: list[ToolSpec]) -> None:
        self._specs: dict[str, ToolSpec] = {}
        for spec in specs:
            if spec.name in self._specs:
                raise ValueError(f"duplicate tool name {spec.name}")
            schema_validator.assert_supported(spec.input_schema, f"{spec.name}.input_schema")
            if spec.input_schema.get("type") != "object":
                raise ValueError(f"{spec.name}: the input schema must describe an object")
            self._specs[spec.name] = spec

    @property
    def names(self) -> list[str]:
        return sorted(self._specs)

    def tool_config(self) -> dict[str, Any]:
        """The ``toolConfig`` argument of Bedrock Converse."""
        return {
            "tools": [
                {
                    "toolSpec": {
                        "name": spec.name,
                        "description": spec.description,
                        "inputSchema": {"json": spec.input_schema},
                    }
                }
                for spec in self._specs.values()
            ]
        }

    def execute(self, name: Any, arguments: Any, *, origin: str, clock: Any, tool_use_id: str | None = None) -> ToolEvent:
        started = clock.time()

        def finish(status: str, tool: str, input_summary: str, result_summary: str, **extra: Any) -> ToolEvent:
            finished = clock.time()
            return ToolEvent(
                tool=tool,
                origin=origin,
                tool_use_id=tool_use_id,
                started_at=to_iso(started),
                finished_at=to_iso(finished),
                duration_ms=max(0, int(round((finished - started) * 1000))),
                status=status,
                input_summary=input_summary,
                result_summary=result_summary,
                **extra,
            )

        spec = self._specs.get(name) if isinstance(name, str) else None
        if spec is None:
            message = f"unknown tool; allowed tools: {', '.join(self.names)}"
            return finish(
                STEP_REJECTED,
                _safe_name(name),
                _describe_untrusted(arguments),
                "rejected, not executed: the tool name is not on the allowlist",
                error={"code": ERROR_UNKNOWN_TOOL, "message": message},
            )

        problems = schema_validator.validate(arguments, spec.input_schema)
        if problems:
            return finish(
                STEP_REJECTED,
                spec.name,
                _describe_untrusted(arguments),
                "rejected, not executed: the arguments do not match the tool schema",
                error={"code": ERROR_INVALID_ARGUMENTS, "message": _clip("; ".join(problems), 600)},
            )

        try:
            output = spec.handler(arguments)
            # A tool result must be a JSON object that survives serialization.
            json.dumps(output, allow_nan=False)
            if not isinstance(output, dict):
                raise TypeError("tool handlers must return an object")
        except Exception as error:  # noqa: BLE001 - a tool bug must not kill the loop
            return finish(
                STEP_FAILED,
                spec.name,
                _clip(spec.summarize_input(arguments)),
                "the tool raised an error; no result was produced",
                error={"code": ERROR_TOOL_ERROR, "message": type(error).__name__},
                arguments=arguments,
            )
        return finish(
            STEP_SUCCEEDED,
            spec.name,
            _clip(spec.summarize_input(arguments)),
            _clip(spec.summarize_result(output)),
            arguments=arguments,
            output=output,
        )


# --------------------------------------------------------------------------
# Phase 1 placeholder tool
# --------------------------------------------------------------------------

INSTRUMENT_ID_PATTERN = r"^[A-Z0-9][A-Z0-9.\-]{0,14}$"

COMPUTE_EXPOSURE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "instrument_id": {
            "type": "string",
            "description": "Instrument identifier exactly as given in the request, for example NVDA or XIU.TO.",
            "pattern": INSTRUMENT_ID_PATTERN,
        },
        "target_direct_weight": {
            "type": "number",
            "description": "Final direct position weight as a portfolio fraction between 0 and 1 (10% is 0.10).",
            "minimum": 0,
            "maximum": 1,
        },
    },
    "required": ["instrument_id", "target_direct_weight"],
    "additionalProperties": False,
}

COMPUTE_EXPOSURE_DESCRIPTION = (
    "Calculates the exposure of the portfolio to one instrument after a proposed purchase. "
    "Call it with the instrument_id and target_direct_weight taken unchanged from the request. "
    "It returns portfolio fractions. A field that is null was not computed and is unknown, not zero. "
    "In this build the calculation is a placeholder and the result says so."
)


def compute_exposure_placeholder(arguments: dict[str, Any]) -> dict[str, Any]:
    """PLACEHOLDER calculation (phase 1 only).

    It reads no portfolio, no holdings and no rules. It reports the requested
    final direct weight and marks everything it did not compute as unknown.
    The real calculation is ``backend/engine`` in phase 2.
    """
    direct = float(arguments["target_direct_weight"])
    return {
        "placeholder": True,
        "calculation_version": PLACEHOLDER_CALCULATION_VERSION,
        "instrument_id": arguments["instrument_id"],
        "unit": "portfolio_fraction",
        "direct_weight": direct,
        "direct_weight_percent": round(direct * 100, 6),
        "indirect_weight": None,
        "total_exposure_lower_bound": direct,
        "total_exposure_upper_bound": None,
        "coverage": "NOT_COMPUTED",
        "notes": [
            "PLACEHOLDER: this result repeats the requested final direct weight and nothing else.",
            "Indirect exposure through funds was not computed. It is unknown, not zero.",
            "No portfolio, holdings or rule data was read. This is not a verdict.",
        ],
    }


def _summarize_exposure_input(arguments: dict[str, Any]) -> str:
    return f"instrument_id={arguments['instrument_id']}, target_direct_weight={arguments['target_direct_weight']}"


def _summarize_exposure_result(output: dict[str, Any]) -> str:
    return (
        f"PLACEHOLDER result: direct_weight={output['direct_weight']} "
        f"({output['direct_weight_percent']}% of the portfolio); indirect exposure not computed (unknown, not zero)"
    )


def build_phase1_registry() -> ToolRegistry:
    return ToolRegistry(
        [
            ToolSpec(
                name="compute_exposure",
                description=COMPUTE_EXPOSURE_DESCRIPTION,
                input_schema=COMPUTE_EXPOSURE_SCHEMA,
                handler=compute_exposure_placeholder,
                summarize_input=_summarize_exposure_input,
                summarize_result=_summarize_exposure_result,
            )
        ]
    )
