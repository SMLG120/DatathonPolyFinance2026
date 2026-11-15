"""contracts/api.md cannot drift from the fixtures, the schemas or the constants.

Every JSON block in api.md follows a marker
    <!-- fixture: <fixture_id> <request_body|response_body> <complete|excerpt> -->
and must equal (complete) or be a subset of (excerpt) that part of the fixture.
The fixtures themselves are validated against the schemas by test_fixtures_validate.py.
"""

from __future__ import annotations

import json
import re

import pytest

import byb_contracts as byb
import byb_contracts.constants as c
from paths import API, API_FIXTURES, CONTRACTS, load

DOC = (CONTRACTS / "api.md").read_text(encoding="utf-8")
BLOCKS = re.findall(r"<!-- fixture: (\w+) (request_body|response_body) (complete|excerpt) -->\n```json\n(.*?)\n```", DOC, re.S)
ROUTES = ["GET /portfolios/{persona_id}", "POST /rules/interpret", "POST /rules/confirm", "POST /check", "POST /investigations",
          "GET /investigations/{id}", "POST /investigations/{id}/challenge"]


def test_every_json_block_is_tied_to_a_fixture():
    assert len(BLOCKS) >= 20
    assert len(BLOCKS) == DOC.count("```json"), "a JSON block in api.md has no fixture marker, so nothing checks it"


@pytest.mark.parametrize("fixture_id,part,mode,text", BLOCKS, ids=[f"{b[0]}:{b[1]}" for b in BLOCKS])
def test_json_block_matches_its_fixture(fixture_id, part, mode, text):
    block, actual = json.loads(text), load(API / f"{fixture_id}.json")[part]
    assert byb.subset_mismatches(block, actual, path=part) == []
    if mode == "complete":
        assert byb.subset_mismatches(actual, block, path=part) == [], "the block is marked complete but leaves members out"


def test_each_route_has_a_section_with_a_request_and_a_response_example():
    for number, route in enumerate(ROUTES, start=2):
        assert f"\n## {number}. {route}\n" in DOC, f"api.md has no section for {route}"
    shown = {(load(API / f"{fixture_id}.json")["route"], part) for fixture_id, part, _, _ in BLOCKS}
    for route in ROUTES:
        assert (route, "response_body") in shown, f"no response example for {route}"
        if route.startswith("POST"):
            assert (route, "request_body") in shown, f"no request example for {route}"


def test_the_example_index_lists_every_fixture_and_nothing_else():
    index = DOC.split("## 9. Example index")[1]
    listed = set(re.findall(r"`([a-z0-9_]+)`", index)) - {"byb_contracts"}
    assert listed == {path.stem for path in API_FIXTURES}
    for name in re.findall(r"fixtures/api/(\w+)\.json", DOC):
        assert (API / f"{name}.json").is_file(), f"api.md points to a missing fixture: {name}"


def test_the_error_table_lists_every_error_code_once_with_the_status_the_fixtures_use():
    table = DOC.split("| HTTP | `code` | When |")[1].split("\n\n")[0]
    rows = re.findall(r"^\| ([0-9, ]+) \| `([A-Z_]+)` \|", table, re.M)
    assert sorted(code for _, code in rows) == sorted(c.ERROR_CODES), "every error code exactly once (the table is ordered by HTTP status)"
    statuses = {code: {int(s) for s in status.split(",")} for status, code in rows}
    for path in API_FIXTURES:
        fixture = load(path)
        if fixture["http_status"] >= 400:
            assert fixture["http_status"] in statuses[fixture["response_body"]["error"]["code"]], path.name


def test_the_timing_values_are_the_constants():
    assert f"| Polling interval | {c.POLL_INTERVAL_MS} ms |" in DOC
    assert f"`created_at` + {c.INVESTIGATION_DEADLINE_SECONDS} s | `INVESTIGATION_DEADLINE_SECONDS`" in DOC
    assert f"| {c.POLL_DEADLINE_SECONDS} s after the 202 | `POLL_DEADLINE_SECONDS`" in DOC
    assert f"`created_at` + {c.INVESTIGATION_EXPIRY_SECONDS // 3600} h | `INVESTIGATION_EXPIRY_SECONDS`" in DOC
    assert f"| {c.INTERPRET_TIMEOUT_SECONDS} s | `INTERPRET_TIMEOUT_SECONDS`" in DOC
    assert f"| {c.CHECK_TIMEOUT_SECONDS} s | `CHECK_TIMEOUT_SECONDS`" in DOC
    assert (c.POLL_INTERVAL_MS, c.INVESTIGATION_DEADLINE_SECONDS, c.POLL_DEADLINE_SECONDS) == (1500, 150, 180), "values fixed by the lead"
    accepted = load(API / "investigation_accepted.json")["response_body"]
    assert accepted["poll"]["interval_ms"] == c.POLL_INTERVAL_MS
    assert byb.schema_errors(load(API / "investigation_accepted.json")["request_headers"]["Idempotency-Key"],
                             "investigation_job.schema.json#/properties/idempotency_key") == []
    pattern = byb.load_schema("investigation_job.schema.json")["properties"]["idempotency_key"]["pattern"]
    assert f"`{pattern}`" in DOC


def test_the_decisions_the_lead_asked_for_are_stated():
    for sentence in ("Clients treat 401\nand 403 alike", "Decision: synchronous, with a hard server deadline of 20 s",
                     "A preview never reads the stored rules and never changes the stored policy",
                     "`preview: true`, `policy_id: null`, `policy_version: null`", "Terminal results are immutable",
                     "180 s after the 202"):
        assert sentence in DOC, f"api.md no longer states: {sentence!r}"
