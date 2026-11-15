"""``live_check.py`` driven against the REAL backend handlers, in process.

API Lambda handler + investigation worker + access-code authorizer (A2's code, unmodified) on A2's in-memory fakes
for S3, Lambda, Bedrock and SSM, behind the transport seam of the live script (``inprocess_backend.py``). No socket,
no AWS, no model: the fake Bedrock answers an empty explanation, and ``POST /rules/interpret`` answers 502 because
no interpreter exists yet.

The second half probes the backend directly against ``contracts/api.md`` for the cases the happy path never sends.
"""

from __future__ import annotations

import json

import pytest

import inprocess_backend as ib
import live_check as lc
import mateo_helpers as mh

CODE = "acceptance-code-0123456789"  # a test value; the real one is only ever read from the environment
BASE = "https://inprocess.invalid"
KEY = "mateo-inprocess-0001"
SYNTHETIC = "mateo_synthetic_universe"

needs_real_data = pytest.mark.skipif(not mh.real_data_present(), reason="data/processed is absent")


def run_main(*extra, universe=None, code=CODE, **transport_options):
    lines, box = [], {}

    def factory(base_url, access_code, timeout, max_requests):
        box["t"] = ib.InProcessTransport(base_url, access_code, timeout, max_requests, universe=universe, **transport_options)
        return box["t"]

    exit_code = lc.main(["--base-url", BASE, *extra], environ={lc.ENV_ACCESS_CODE: code}, transport_factory=factory, out=lines.append,
                        sleep=lambda seconds: box["t"].sleep(seconds), clock=lambda: box["t"].clock())
    return exit_code, lines, box.get("t")


def statuses(transport):
    return [(method, path.split("/inv-")[0], status) for method, path, status in transport.log]


WORKFLOW = [("GET", "/portfolios/mateo", 200), ("POST", "/rules/interpret", 502), ("POST", "/rules/confirm", 201), ("POST", "/check", 200),
            ("POST", "/check", 200), ("POST", "/check", 200), ("POST", "/investigations", 202), ("POST", "/investigations", 202),
            ("GET", "/investigations", 200), ("GET", "/investigations", 200), ("GET", "/investigations", 200)]


# ---------------------------------------------------------------- the workflow, end to end

@needs_real_data
def test_default_run_passes_and_the_missing_interpreter_is_a_warning():
    code, lines, transport = run_main()
    text = "\n".join(lines)
    assert code == lc.EXIT_PASS, text
    assert lines[-1] == "RESULT: PASS (20 checks, 1 warnings, 11 requests sent)", text
    assert "[WARN] POST /rules/interpret: HTTP 502" in text and "[FAIL]" not in text
    assert statuses(transport) == WORKFLOW
    assert CODE not in text


@needs_real_data
def test_skip_interpret_sends_no_interpret_request():
    code, lines, transport = run_main("--skip-interpret")
    assert code == lc.EXIT_PASS, "\n".join(lines)
    assert lines[-1] == "RESULT: PASS (20 checks, 1 warnings, 10 requests sent)"
    assert statuses(transport) == [entry for entry in WORKFLOW if entry[1] != "/rules/interpret"]


@needs_real_data
def test_require_interpreter_fails_on_the_502_and_stops_before_anything_is_stored():
    code, lines, transport = run_main("--require-interpreter")
    text = "\n".join(lines)
    assert code == lc.EXIT_FAIL, text
    assert "HTTP 502 (INTERPRETER_FAILED), expected 200" in text and "Later steps were not run" in text
    assert statuses(transport) == WORKFLOW[:2]
    assert not [key for key in transport.service.s3.keys() if "pol-" in key or "inv-" in key]
    assert transport.service.lambda_client.invocations == []


@needs_real_data
def test_compare_local_the_backend_result_is_the_local_engine_result_on_the_real_data():
    code, lines, transport = run_main("--compare-local")
    text = "\n".join(lines)
    assert code == lc.EXIT_PASS, text
    assert "[PASS] compare-local" in text and "byte-identical canonical JSON" in text
    assert "mateo-excl-energy-1 FAIL->FAIL [0.033320, 0.333780]" in text
    assert "mateo-controversy-1 FAIL->FAIL [0.015678, 0.650000]" in text
    assert "max_compliant NO_FEASIBLE_PURCHASE" in text
    assert lines[-1] == "RESULT: PASS (21 checks, 1 warnings, 11 requests sent)"


def test_a_backend_serving_the_synthetic_snapshot_is_stopped_at_the_first_step():
    """The synthetic contract universe has no price series, so nothing is purchasable (api.md section 2): the
    script must refuse to go on rather than report a shape-valid run on invented data."""
    code, lines, transport = run_main("--compare-local", universe=SYNTHETIC)
    text = "\n".join(lines)
    assert code == lc.EXIT_FAIL, text
    assert "SPY is not purchasable" in text and "Later steps were not run" in text
    assert statuses(transport) == WORKFLOW[:1]


def test_a_wrong_access_code_is_exit_2_after_one_request_and_reaches_no_handler():
    code, lines, transport = run_main(universe=SYNTHETIC, stored_access_code="another-code-9876543210")
    text = "\n".join(lines)
    assert code == lc.EXIT_COULD_NOT_RUN, text
    assert "COULD NOT RUN" in text and "HTTP 403" in text
    assert transport.log == [("GET", "/portfolios/mateo", 403)] and transport.response_headers == []
    assert CODE not in text and "another-code" not in text


@needs_real_data
def test_exactly_one_policy_and_one_job_and_one_worker_run():
    code, lines, transport = run_main()
    assert code == lc.EXIT_PASS, "\n".join(lines)
    service = transport.service
    jobs = {path for _method, path, _status in transport.log if path.startswith("/investigations/")}
    assert len(jobs) == 1
    assert len(service.bedrock.calls) == 1  # one worker ran, whatever the number of deliveries
    assert all(record["InvocationType"] == "Event" and set(record["Payload"]) == {"job_id"} for record in service.lambda_client.invocations)
    assert {record["Payload"]["job_id"] for record in service.lambda_client.invocations} == {next(iter(jobs)).rsplit("/", 1)[1]}


@needs_real_data
def test_the_job_is_queued_until_the_worker_runs_and_polling_follows_the_servers_interval():
    code, lines, transport = run_main(worker_after_polls=4)
    text = "\n".join(lines)
    assert code == lc.EXIT_PASS, text
    assert "SUCCEEDED after 4 polls, 0 retries" in text


@needs_real_data
def test_a_worker_that_never_runs_ends_in_the_servers_deadline_failure_before_the_client_deadline():
    """api.md section 7 polling rule 2: after deadline_at the route never answers QUEUED again."""
    code, lines, transport = run_main(worker_after_polls=None)
    text = "\n".join(lines)
    assert code == lc.EXIT_FAIL, text
    assert "[PASS] polling: reached a terminal state before the client deadline: FAILED" in text
    assert "DEADLINE_EXCEEDED" in text
    polls = [entry for entry in transport.log if entry[1].startswith("/investigations/")]
    assert 100 <= len(polls) <= lc.max_polls(lc.POLL_DEADLINE_SECONDS, lc.POLL_INTERVAL_MS)
    assert "RESULT: FAIL" in lines[-1]


@needs_real_data
def test_every_response_is_sent_with_cache_control_no_store():
    _code, _lines, transport = run_main()
    assert len(transport.response_headers) == 11
    for headers in transport.response_headers:
        lowered = {name.lower(): value for name, value in headers.items()}
        assert lowered.get("cache-control") == "no-store", headers
        assert lowered.get("content-type", "").startswith("application/json"), headers


# ---------------------------------------------------------------- the backend against contracts/api.md, error paths

@pytest.fixture()
def backend():
    transport = ib.InProcessTransport(BASE, CODE, universe=SYNTHETIC)
    scenario = transport.send(lc.portfolio_request()).body["scenario"]
    policy = transport.send(lc.confirm_request(scenario)).body["policy"]
    return transport, scenario, policy, scenario["demo_requests"][0]["purchase_request"]


def error_of(response, status, code):
    assert response.status == status, (response.status, response.body)
    assert lc.shape_problems("api.schema.json#/$defs/error_response", response.body) == [], response.body
    error = response.body["error"]
    assert error["code"] == code, error
    return error


def test_interpret_answers_the_contract_error_envelope(backend):
    transport, scenario, _policy, _purchase = backend
    error = error_of(transport.send(lc.interpret_request(scenario["objectives"][0]["original_words"])), 502, "INTERPRETER_FAILED")
    assert error["message"] and "Traceback" not in json.dumps(error)


def test_unknown_persona_policy_and_investigation_are_404(backend):
    transport, _scenario, policy, purchase = backend
    error_of(transport.send(lc.build_request("GET", "/portfolios/nobody")), 404, "NOT_FOUND")
    error_of(transport.send(lc.poll_request("/investigations/inv-00000000000000000000000000000000")), 404, "NOT_FOUND")
    error_of(transport.send(lc.check_request("pol-mateo-unknown", 1, purchase)), 404, "NOT_FOUND")
    error_of(transport.send(lc.check_request(policy["policy_id"], 7, purchase)), 404, "NOT_FOUND")


def test_malformed_bodies_are_400_before_any_calculation(backend):
    transport, _scenario, policy, purchase = backend
    extra = lc.check_request(policy["policy_id"], policy["version"], purchase)
    extra["body"]["surprise"] = 1
    error_of(transport.send(extra), 400, "VALIDATION_ERROR")
    percent = lc.check_request(policy["policy_id"], policy["version"], dict(purchase, target_direct_weight="15%"))
    error_of(transport.send(percent), 400, "VALIDATION_ERROR")
    missing = lc.check_request(policy["policy_id"], policy["version"], purchase)
    del missing["body"]["purchase_request"]
    error_of(transport.send(missing), 400, "VALIDATION_ERROR")


def test_investigation_needs_a_key_and_refuses_a_reused_key_with_another_body(backend):
    transport, _scenario, policy, purchase = backend
    request = lc.investigation_request(policy["policy_id"], policy["version"], purchase, KEY)
    without = json.loads(json.dumps(request))
    del without["headers"]["Idempotency-Key"]
    error = error_of(transport.send(without), 400, "VALIDATION_ERROR")
    assert error["details"][0]["path"] == "headers.Idempotency-Key"
    assert transport.send(request).status == 202
    other = lc.investigation_request(policy["policy_id"], policy["version"], dict(purchase, target_direct_weight=0.10), KEY)
    error_of(transport.send(other), 409, "IDEMPOTENCY_KEY_REUSED")
    assert len({record["Payload"]["job_id"] for record in transport.service.lambda_client.invocations}) == 1


def test_a_purchase_the_engine_would_refuse_is_422_and_stores_no_job(backend):
    transport, scenario, policy, purchase = backend
    held = next(position for position in scenario["portfolio"]["positions"] if position["weight"] >= 0.2)
    below = dict(purchase, instrument_id=held["instrument_id"], target_direct_weight=held["weight"] / 2)
    error = error_of(transport.send(lc.investigation_request(policy["policy_id"], policy["version"], below, KEY)), 422, "INVALID_PURCHASE_REQUEST")
    assert error["details"][0]["issue"].startswith("TARGET_BELOW_CURRENT_WEIGHT")
    assert transport.service.lambda_client.invocations == []


def test_confirming_on_a_stale_version_is_409(backend):
    transport, scenario, policy, _purchase = backend
    again = lc.confirm_request(scenario)  # policy_id null: a second policy would be a second version 1
    again["body"]["policy_id"], again["body"]["base_version"] = policy["policy_id"], 0
    response = transport.send(again)
    assert response.status in (400, 409), response.body  # base_version 0 may be refused by the schema first
    stale = lc.confirm_request(scenario)
    stale["body"]["policy_id"], stale["body"]["base_version"] = policy["policy_id"], 5
    error_of(transport.send(stale), 409, "POLICY_VERSION_CONFLICT")


@pytest.mark.xfail(strict=True, reason="B1: replaying POST /investigations while the job is QUEUED invokes the worker Lambda a second time "
                                       "(api.md section 6 server rule 2: 'no second job and no second worker are created')")
def test_B1_an_idempotent_replay_of_a_queued_job_invokes_no_second_worker(backend):
    transport, _scenario, policy, purchase = backend
    request = lc.investigation_request(policy["policy_id"], policy["version"], purchase, KEY)
    first, second = transport.send(request), transport.send(request)
    assert (first.status, second.status) == (202, 202) and first.body["id"] == second.body["id"]
    assert second.body["status"] == "QUEUED"
    assert len(transport.service.lambda_client.invocations) == 1


def test_B1_the_second_delivery_is_a_no_op_one_model_call_one_terminal_state(backend):
    """What bounds B1: the worker's claim. Both deliveries run; the job is computed once and never rewritten."""
    transport, _scenario, policy, purchase = backend
    request = lc.investigation_request(policy["policy_id"], policy["version"], purchase, KEY)
    path = transport.send(request).body["poll"]["path"]
    transport.send(request)
    transport.deliver_worker_events()
    assert transport.delivered == 2 and len(transport.service.bedrock.calls) == 1
    job = transport.send(lc.poll_request(path)).body
    assert job["status"] == "SUCCEEDED"
    assert lc.immutable_problems(job, transport.send(lc.poll_request(path)).body) == []
