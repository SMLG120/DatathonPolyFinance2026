"""Structured log lines: valid JSON, secrets redacted, long text truncated."""

import json

from backend.common import log


def test_lg01_one_json_object_per_line_with_bound_context(captured_log):
    log.bind(component="api", request_id="r-1")
    log.info("something_happened", count=3, ratio=0.25)
    record = json.loads(captured_log.getvalue())
    assert record["event"] == "something_happened" and record["level"] == "INFO"
    assert record["component"] == "api" and record["request_id"] == "r-1" and record["count"] == 3


def test_lg02_sensitive_keys_are_redacted_at_any_depth(captured_log):
    log.info(
        "request",
        headers={"Authorization": "Bearer abc123secret", "content-type": "application/json"},
        nested=[{"token": "abc123secret"}, {"access_code": "abc123secret"}],
        identitySource=["Bearer abc123secret"],
    )
    output = captured_log.getvalue()
    assert "abc123secret" not in output
    record = json.loads(output)
    assert record["headers"]["Authorization"] == "[REDACTED]" and record["headers"]["content-type"] == "application/json"


def test_lg03_token_counters_are_not_mistaken_for_secrets(captured_log):
    log.info("bedrock_call", input_tokens=757, output_tokens=149, max_tokens=4096)
    record = json.loads(captured_log.getvalue())
    assert record["input_tokens"] == 757 and record["output_tokens"] == 149 and record["max_tokens"] == 4096


def test_lg04_long_strings_are_truncated_and_odd_values_do_not_break_logging(captured_log):
    log.info("big", prompt="p" * 5000, weird=object(), not_a_number=float("nan"))
    record = json.loads(captured_log.getvalue())
    assert len(record["prompt"]) < 500 and "more chars" in record["prompt"]
    assert record["weird"] == "<object>" and record["not_a_number"] == "nan"


def test_lg05_levels_below_the_threshold_are_dropped(captured_log):
    log.debug("noise")
    assert captured_log.getvalue() == ""
