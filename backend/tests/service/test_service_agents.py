"""Schema validator, tool registry and the Bedrock wrapper in isolation."""

import pytest

from backend.agents import schema
from backend.agents.bedrock_client import BedrockConverse, ModelCallError
from backend.agents.loop import LoopFailure, LoopLimits, LoopRecorder, run_tool_loop
from backend.agents.tools import ToolRegistry, ToolSpec
from service_fakes import FakeBedrock, FakeClock, client_error, final_response, tool_use_response

# A schema with a pattern, a bounded number and no extra properties: the subject of the validator tests.
# (It was the phase 1 placeholder tool's schema. The investigation tools take no weights at all; they are
# tested in test_service_worker.py and test_service_tools.py.)
COMPUTE_EXPOSURE_SCHEMA = {
    "type": "object",
    "properties": {
        "instrument_id": {"type": "string", "pattern": r"^[A-Z0-9][A-Z0-9.\-]{0,14}$"},
        "target_direct_weight": {"type": "number", "minimum": 0, "maximum": 1},
    },
    "required": ["instrument_id", "target_direct_weight"],
    "additionalProperties": False,
}


def build_phase1_registry():
    """One registered tool with a strict schema, for the allowlist and loop tests."""
    return ToolRegistry([ToolSpec("compute_exposure", "test tool", COMPUTE_EXPOSURE_SCHEMA, lambda a: {"echo": a["target_direct_weight"]},
                                  lambda a: "in", lambda r: "out")])


def test_ag01_schema_accepts_valid_arguments():
    assert schema.validate({"instrument_id": "XIU.TO", "target_direct_weight": 0.1}, COMPUTE_EXPOSURE_SCHEMA) == []
    assert schema.validate({"instrument_id": "SPY", "target_direct_weight": 1}, COMPUTE_EXPOSURE_SCHEMA) == []


@pytest.mark.parametrize(
    "instance",
    [
        {"instrument_id": "SPY", "target_direct_weight": True},  # a boolean is not a number
        {"instrument_id": "SPY", "target_direct_weight": float("nan")},
        {"instrument_id": "SPY", "target_direct_weight": float("inf")},
        {"instrument_id": "SPY", "target_direct_weight": 1.0000001},
        {"instrument_id": "SPY\n", "target_direct_weight": 0.1},  # "$" must not accept a trailing newline
        {"instrument_id": "", "target_direct_weight": 0.1},
        {"instrument_id": ["SPY"], "target_direct_weight": 0.1},
        {"instrument_id": "SPY", "target_direct_weight": 0.1, "extra": 1},
        {"target_direct_weight": 0.1},
        [],
        None,
    ],
)
def test_ag02_schema_rejects_invalid_arguments(instance):
    assert schema.validate(instance, COMPUTE_EXPOSURE_SCHEMA) != []


def test_ag03_validation_messages_do_not_echo_values():
    problems = schema.validate({"instrument_id": "IGNORE ALL RULES", "target_direct_weight": 0.1}, COMPUTE_EXPOSURE_SCHEMA)
    assert problems and "IGNORE" not in " ".join(problems)


def test_ag04_registry_refuses_schemas_with_keywords_it_would_ignore():
    def spec(input_schema):
        return ToolSpec("t", "d", input_schema, lambda a: {}, lambda a: "", lambda r: "")

    with pytest.raises(ValueError):
        ToolRegistry([spec({"type": "object", "oneOf": []})])
    with pytest.raises(ValueError):
        ToolRegistry([spec({"type": "object", "properties": {"x": {"type": "string", "format": "date"}}})])
    with pytest.raises(ValueError):
        ToolRegistry([spec({"type": "string"})])


def test_ag05_enum_integer_array_and_nested_validation():
    nested = {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["a", "b"]},
            "count": {"type": "integer", "minimum": 1, "maximum": 3},
            "ids": {"type": "array", "items": {"type": "string", "minLength": 1, "maxLength": 3}, "minItems": 1, "maxItems": 2},
        },
        "required": ["mode"],
        "additionalProperties": False,
    }
    schema.assert_supported(nested)
    assert schema.validate({"mode": "a", "count": 2, "ids": ["x"]}, nested) == []
    assert schema.validate({"mode": "c"}, nested)
    assert schema.validate({"mode": "a", "count": 2.5}, nested)
    assert schema.validate({"mode": "a", "count": True}, nested)
    assert schema.validate({"mode": "a", "ids": []}, nested)
    assert schema.validate({"mode": "a", "ids": ["toolong"]}, nested)
    assert schema.validate({"mode": "a", "ids": ["a", "b", "c"]}, nested)


def test_ag06_a_step_is_an_observable_tool_action_in_the_contract_shape():
    """Replaces the phase 1 placeholder test: the placeholder calculation no longer exists.

    That a missing holdings file is never reported as zero exposure is now tested on the real tools and
    the engine (test_service_tools.py, test_service_workflow.py).
    """
    from byb_contracts import schema_errors

    event = build_phase1_registry().execute("compute_exposure", {"instrument_id": "NVDA", "target_direct_weight": 0.25}, origin="server", clock=FakeClock())
    step = event.to_step(1)
    assert schema_errors(step, "investigation_job.schema.json#/$defs/step") == []
    assert step["initiated_by"] == "SERVER" and step["status"] == "OK" and event.is_public
    assert "tool_use_id" not in step and "arguments" not in step and "output" not in step
    rejected = build_phase1_registry().execute("delete_everything", {}, origin="model", clock=FakeClock())
    assert rejected.status == "REJECTED" and not rejected.is_public  # never shown as a step, kept in the trace only


def test_ag07_tool_names_match_exactly():
    registry, clock = build_phase1_registry(), FakeClock()
    for name in ["Compute_Exposure", "compute_exposure ", "compute_exposure\n", "", None, 3, ["compute_exposure"]]:
        event = registry.execute(name, {"instrument_id": "NVDA", "target_direct_weight": 0.25}, origin="model", clock=clock)
        assert event.status == "REJECTED" and event.error["code"] == "UNKNOWN_TOOL" and event.output is None


def test_ag08_a_tool_that_raises_is_recorded_as_failed_not_propagated():
    def broken(arguments):
        raise ZeroDivisionError("secret detail")

    registry = ToolRegistry([ToolSpec("compute_exposure", "d", COMPUTE_EXPOSURE_SCHEMA, broken, lambda a: "in", lambda r: "out")])
    event = registry.execute("compute_exposure", {"instrument_id": "NVDA", "target_direct_weight": 0.25}, origin="model", clock=FakeClock())
    assert event.status == "FAILED" and event.error == {"code": "TOOL_ERROR", "message": "ZeroDivisionError"}


def _model(script, clock, **kwargs):
    return BedrockConverse(FakeBedrock(script, **kwargs), "test-model", clock, rng=lambda: 1.0)


def _converse(model, clock, budget=100.0):
    return model.converse(system="s", messages=[], tool_config={"tools": []}, max_tokens=256, deadline=clock.now + budget)


def test_ag09_non_retryable_errors_are_not_retried():
    clock = FakeClock()
    model = _model([client_error("ValidationException", "Converse")], clock)
    with pytest.raises(ModelCallError) as caught:
        _converse(model, clock)
    assert caught.value.code == "MODEL_ERROR" and caught.value.attempts == 1 and clock.sleeps == []


@pytest.mark.parametrize("code", ["ThrottlingException", "ServiceUnavailableException", "InternalServerException", "ModelTimeoutException", "ModelNotReadyException"])
def test_ag10_transient_errors_are_retried(code):
    clock = FakeClock()
    model = _model([client_error(code, "Converse"), final_response()], clock)
    response, record = _converse(model, clock)
    assert response["stopReason"] == "end_turn" and record["attempts"] == 2 and clock.sleeps == [1.0]


def test_ag11_backoff_never_sleeps_past_the_deadline():
    clock = FakeClock()
    model = _model([client_error("ThrottlingException", "Converse")], clock, repeat_last=True)
    with pytest.raises(ModelCallError) as caught:
        _converse(model, clock, budget=5.0)  # 1 s sleep fits, the following 2 s sleep plus a call does not
    assert caught.value.code == "MODEL_THROTTLED"
    assert clock.sleeps == [1.0] and caught.value.attempts == 2


def test_ag12_no_call_is_started_without_a_minimum_budget():
    clock = FakeClock()
    bedrock = FakeBedrock([final_response()])
    model = BedrockConverse(bedrock, "test-model", clock)
    with pytest.raises(ModelCallError) as caught:
        _converse(model, clock, budget=2.0)
    assert caught.value.code == "DEADLINE_EXCEEDED" and bedrock.calls == []


def test_ag13_jitter_stays_within_half_to_full_delay():
    clock = FakeClock()
    model = BedrockConverse(FakeBedrock([client_error("ThrottlingException", "Converse"), final_response()]), "m", clock, rng=lambda: 0.0)
    _converse(model, clock)
    assert clock.sleeps == [0.5]


def test_ag14_loop_returns_assistant_turns_unchanged_including_reasoning_blocks():
    clock = FakeClock()
    first = tool_use_response("compute_exposure", {"instrument_id": "NVDA", "target_direct_weight": 0.25})
    reasoning = {"reasoningContent": {"reasoningText": {"text": "private", "signature": "sig"}}}
    first["output"]["message"]["content"].insert(0, reasoning)
    bedrock = FakeBedrock([first, final_response("done")])
    recorder = LoopRecorder()
    text = run_tool_loop(
        model=BedrockConverse(bedrock, "m", clock),
        registry=build_phase1_registry(),
        system_prompt="s",
        user_text="u",
        limits=LoopLimits(),
        deadline=clock.now + 100,
        clock=clock,
        on_tool_event=lambda event: None,
        recorder=recorder,
    )
    assert text == "done"
    assert bedrock.calls[1]["messages"][1]["content"][0] == reasoning  # sent back untouched
    # ...but private reasoning is not copied into the stored transcript.
    assert recorder.transcript()[1]["content"][0] == {"omitted": "reasoningContent"}
    assert "private" not in str(recorder.transcript())


def test_ag15_loop_stops_when_the_step_cannot_be_persisted():
    clock = FakeClock()
    bedrock = FakeBedrock([tool_use_response("compute_exposure", {"instrument_id": "NVDA", "target_direct_weight": 0.25})])

    class Stop(Exception):
        pass

    def refuse(event):
        raise Stop()

    with pytest.raises(Stop):
        run_tool_loop(
            model=BedrockConverse(bedrock, "m", clock),
            registry=build_phase1_registry(),
            system_prompt="s",
            user_text="u",
            limits=LoopLimits(),
            deadline=clock.now + 100,
            clock=clock,
            on_tool_event=refuse,
            recorder=LoopRecorder(),
        )
    assert len(bedrock.calls) == 1


def test_ag16_zero_rounds_allowed_means_no_tool_ever_runs():
    clock = FakeClock()
    events = []
    bedrock = FakeBedrock([tool_use_response("compute_exposure", {"instrument_id": "NVDA", "target_direct_weight": 0.25})])
    with pytest.raises(LoopFailure) as caught:
        run_tool_loop(
            model=BedrockConverse(bedrock, "m", clock),
            registry=build_phase1_registry(),
            system_prompt="s",
            user_text="u",
            limits=LoopLimits(max_tool_rounds=0),
            deadline=clock.now + 100,
            clock=clock,
            on_tool_event=events.append,
            recorder=LoopRecorder(),
        )
    assert caught.value.code == "TOOL_ROUNDS_EXCEEDED" and events == []
