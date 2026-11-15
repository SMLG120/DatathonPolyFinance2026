"""API lifecycle: idempotent creation, dispatch, polling, deadline."""

import json

import pytest

from backend.api.handler import job_id_for, parse_create_request, read_idempotency_key
from backend.common.clock import to_iso
from backend.common.http import ApiError
from service_fakes import (
    ROBERT_BODY,
    FakeClock,
    FakeLambda,
    FakeS3,
    body_of,
    build_api,
    client_error,
    get_event,
    post_event,
)

JOB_ID = job_id_for(ROBERT_BODY["idempotency_key"])
JOB_KEY = f"jobs/{JOB_ID}.json"


@pytest.fixture
def env():
    s3, lam, clock = FakeS3(), FakeLambda(), FakeClock()
    return s3, lam, clock, build_api(s3, lam, clock)


def test_svc01_post_stores_queued_job_then_dispatches_then_answers_202(env):
    s3, lam, clock, api = env
    seen_at_invoke = {}
    lam.on_invoke = lambda record: seen_at_invoke.update(s3.json(JOB_KEY))

    response = api.handle(post_event(), None)

    assert response["statusCode"] == 202
    body = body_of(response)
    assert body["investigation_id"] == JOB_ID
    assert body["status"] == "QUEUED"
    assert body["replayed"] is False
    assert body["poll"]["href"] == f"/investigations/{JOB_ID}"
    assert response["headers"]["location"] == f"/investigations/{JOB_ID}"
    # The validated request was already stored, as QUEUED, when the worker was invoked.
    assert seen_at_invoke["status"] == "QUEUED"
    assert seen_at_invoke["request"]["purchase"] == {"instrument_id": "NVDA", "target_direct_weight": 0.25}
    assert lam.invocations == [{"FunctionName": "test-worker", "InvocationType": "Event", "Payload": {"job_id": JOB_ID}}]
    # Deadline is stored with the job.
    assert s3.json(JOB_KEY)["deadline_at"] == to_iso(clock.now + 150)
    assert s3.unconditional_puts() == []


def test_svc02_duplicate_post_returns_same_job_and_creates_nothing_new(env):
    s3, lam, clock, api = env
    first = body_of(api.handle(post_event(), None))
    clock.advance(1)
    second_response = api.handle(post_event(), None)
    second = body_of(second_response)

    assert second_response["statusCode"] == 202
    assert second["investigation_id"] == first["investigation_id"] == JOB_ID
    assert second["created_at"] == first["created_at"]  # the stored job, not a new one
    assert second["replayed"] is True
    assert s3.keys("jobs/") == [JOB_KEY]


def test_svc03_idempotency_key_may_come_from_the_header(env):
    s3, lam, clock, api = env
    body = {k: v for k, v in ROBERT_BODY.items() if k != "idempotency_key"}
    response = api.handle(post_event(body, headers={"idempotency-key": ROBERT_BODY["idempotency_key"]}), None)
    assert response["statusCode"] == 202
    assert body_of(response)["investigation_id"] == JOB_ID


def test_svc04_same_key_with_a_different_request_is_a_conflict(env):
    s3, lam, clock, api = env
    api.handle(post_event(), None)
    changed = dict(ROBERT_BODY, purchase={"instrument_id": "NVDA", "target_direct_weight": 0.30})
    response = api.handle(post_event(changed), None)

    assert response["statusCode"] == 409
    assert body_of(response)["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"
    assert s3.json(JOB_KEY)["request"]["purchase"]["target_direct_weight"] == 0.25  # first request untouched
    assert len(lam.invocations) == 1


def test_svc05_duplicate_post_after_the_job_started_does_not_dispatch_again(env):
    s3, lam, clock, api = env
    api.handle(post_event(), None)
    job = s3.json(JOB_KEY)
    job["status"] = "RUNNING"
    s3.objects[JOB_KEY] = json.dumps(job).encode()

    response = api.handle(post_event(), None)
    assert response["statusCode"] == 202
    assert body_of(response)["status"] == "RUNNING"
    assert len(lam.invocations) == 1


def test_svc06_duplicate_post_while_still_queued_dispatches_again(env):
    """Covers an API process that died between storing the job and invoking the worker."""
    s3, lam, clock, api = env
    api.handle(post_event(), None)
    response = api.handle(post_event(), None)
    assert response["statusCode"] == 202
    assert len(lam.invocations) == 2  # safe: only one worker can claim the job
    assert s3.keys("jobs/") == [JOB_KEY]


def test_svc07_invoke_exception_marks_job_failed_and_returns_503(env):
    s3, lam, clock, api = env
    lam.error = client_error("ServiceException", "Invoke", 500)

    response = api.handle(post_event(), None)

    assert response["statusCode"] == 503
    error = body_of(response)["error"]
    assert error["code"] == "DISPATCH_FAILED"
    assert error["investigation_id"] == JOB_ID
    stored = s3.json(JOB_KEY)
    assert stored["status"] == "FAILED"
    assert stored["error"]["code"] == "DISPATCH_FAILED"
    assert stored["finished_at"] is not None


def test_svc08_invoke_not_accepted_is_not_a_202(env):
    s3, lam, clock, api = env
    lam.status_code = 200  # anything but 202 means the event was not queued
    response = api.handle(post_event(), None)
    assert response["statusCode"] == 503
    assert s3.json(JOB_KEY)["status"] == "FAILED"


def test_svc09_replay_of_a_dispatch_failure_reports_the_failure_again(env):
    s3, lam, clock, api = env
    lam.error = client_error("TooManyRequestsException", "Invoke", 429)
    api.handle(post_event(), None)
    lam.error = None

    response = api.handle(post_event(), None)
    assert response["statusCode"] == 503
    assert body_of(response)["error"]["code"] == "DISPATCH_FAILED"
    assert len(lam.invocations) == 1  # a terminal job is never dispatched again
    assert s3.json(JOB_KEY)["status"] == "FAILED"


def test_svc10_storage_failure_returns_structured_500_without_dispatch(env, captured_log):
    s3, lam, clock, api = env
    s3.fail_puts_with = [client_error("InternalError", "PutObject", 500)]
    response = api.handle(post_event(), None)
    assert response["statusCode"] == 500
    assert body_of(response)["error"]["code"] == "INTERNAL_ERROR"
    assert lam.invocations == []
    assert "api_unexpected_error" in captured_log.getvalue()


@pytest.mark.parametrize(
    "mutation, expected_code",
    [
        (lambda b: b.pop("idempotency_key"), "IDEMPOTENCY_KEY_REQUIRED"),
        (lambda b: b.update(idempotency_key="short"), "INVALID_IDEMPOTENCY_KEY"),
        (lambda b: b.update(idempotency_key="has space in it"), "INVALID_IDEMPOTENCY_KEY"),
        (lambda b: b.update(persona_id="warren"), "INVALID_REQUEST"),
        (lambda b: b.update(purchase={"instrument_id": "nvda", "target_direct_weight": 0.25}), "INVALID_REQUEST"),
        (lambda b: b.update(purchase={"instrument_id": "NVDA\n", "target_direct_weight": 0.25}), "INVALID_REQUEST"),
        (lambda b: b.update(purchase={"instrument_id": "NVDA", "target_direct_weight": 25}), "INVALID_REQUEST"),
        (lambda b: b.update(purchase={"instrument_id": "NVDA", "target_direct_weight": -0.1}), "INVALID_REQUEST"),
        (lambda b: b.update(purchase={"instrument_id": "NVDA", "target_direct_weight": "0.25"}), "INVALID_REQUEST"),
        (lambda b: b.update(purchase={"instrument_id": "NVDA", "target_direct_weight": True}), "INVALID_REQUEST"),
        (lambda b: b.update(purchase={"instrument_id": "NVDA", "target_direct_weight": 0.25, "funding": "MARGIN"}), "INVALID_REQUEST"),
        (lambda b: b.update(policy_version=0), "INVALID_REQUEST"),
        (lambda b: b.update(question="x" * 501), "INVALID_REQUEST"),
        (lambda b: b.update(verdict="PASS"), "INVALID_REQUEST"),
    ],
)
def test_svc11_invalid_requests_are_rejected_before_anything_is_stored(env, mutation, expected_code):
    s3, lam, clock, api = env
    body = json.loads(json.dumps(ROBERT_BODY))
    mutation(body)
    response = api.handle(post_event(body), None)
    assert response["statusCode"] == 400
    assert body_of(response)["error"]["code"] == expected_code
    assert s3.objects == {} and lam.invocations == []


@pytest.mark.parametrize("raw", ["", "not json", "[1,2]", '{"persona_id": NaN}', "{" * 5000])
def test_svc12_malformed_bodies_are_rejected(env, raw):
    s3, lam, clock, api = env
    response = api.handle(post_event(raw=raw), None)
    assert response["statusCode"] == 400
    assert s3.objects == {}


def test_svc13_oversized_body_is_rejected(env):
    s3, lam, clock, api = env
    response = api.handle(post_event(raw=json.dumps(dict(ROBERT_BODY, question="x" * 9000))), None)
    assert response["statusCode"] == 413
    assert s3.objects == {}


def test_svc14_header_and_field_keys_must_agree():
    with pytest.raises(ApiError) as caught:
        read_idempotency_key({"headers": {"idempotency-key": "key-number-one"}}, {"idempotency_key": "key-number-two"})
    assert caught.value.code == "IDEMPOTENCY_KEY_MISMATCH"


def test_svc15_request_is_normalized_and_units_are_fractions():
    request = parse_create_request(dict(ROBERT_BODY, question="  why?  ", purchase={"instrument_id": "XIU.TO", "target_direct_weight": 1}))
    assert request == {
        "persona_id": "robert",
        "purchase": {"instrument_id": "XIU.TO", "target_direct_weight": 1.0},
        "policy_version": None,
        "question": "why?",
    }


def test_svc16_get_unknown_or_malformed_id_is_404(env):
    s3, lam, clock, api = env
    for job_id in ["inv_" + "0" * 32, "../../snapshots/x", "inv_XYZ", ""]:
        response = api.handle(get_event(job_id), None)
        assert response["statusCode"] == 404
        assert body_of(response)["error"]["code"] == "INVESTIGATION_NOT_FOUND"


def test_svc17_get_treats_access_denied_on_a_missing_key_as_404_only_after_listing():
    """Without s3:ListBucket S3 answers 403 for a missing key; the API role lists the jobs/ prefix to tell."""
    s3, lam, clock = FakeS3(missing_is_access_denied=True), FakeLambda(), FakeClock()
    api = build_api(s3, lam, clock)
    assert api.handle(get_event("inv_" + "a" * 32), None)["statusCode"] == 404


def test_svc18_get_returns_public_view_without_internal_fields(env):
    s3, lam, clock, api = env
    api.handle(post_event(), None)
    response = api.handle(get_event(JOB_ID), None)
    assert response["statusCode"] == 200
    assert response["headers"]["cache-control"] == "no-store"
    body = body_of(response)
    assert body["investigation_id"] == JOB_ID and body["status"] == "QUEUED"
    assert body["steps"] == [] and body["result"] is None and body["error"] is None
    assert "request_hash" not in body and "attempt" not in body


@pytest.mark.parametrize("status", ["QUEUED", "RUNNING"])
def test_svc19_job_past_its_deadline_is_reported_failed_and_the_failure_is_persisted(env, status):
    """The worker died silently: nothing ever moved the job out of QUEUED/RUNNING."""
    s3, lam, clock, api = env
    api.handle(post_event(), None)
    job = s3.json(JOB_KEY)
    job["status"] = status
    s3.objects[JOB_KEY] = json.dumps(job).encode()

    clock.advance(149)
    assert body_of(api.handle(get_event(JOB_ID), None))["status"] == status  # not yet

    clock.advance(1)  # exactly at the deadline
    body = body_of(api.handle(get_event(JOB_ID), None))
    assert body["status"] == "FAILED"
    assert body["error"]["code"] == "DEADLINE_EXCEEDED"
    stored = s3.json(JOB_KEY)
    assert stored["status"] == "FAILED" and stored["error"]["code"] == "DEADLINE_EXCEEDED"
    # Later polls keep returning the same terminal state.
    clock.advance(600)
    assert body_of(api.handle(get_event(JOB_ID), None))["error"]["code"] == "DEADLINE_EXCEEDED"


def test_svc20_deadline_does_not_touch_a_job_that_already_succeeded(env):
    s3, lam, clock, api = env
    api.handle(post_event(), None)
    job = s3.json(JOB_KEY)
    job.update(status="SUCCEEDED", result_key=f"results/{JOB_ID}.json")
    s3.objects[JOB_KEY] = json.dumps(job).encode()
    s3.objects[f"results/{JOB_ID}.json"] = json.dumps({"placeholder": True}).encode()

    clock.advance(10_000)
    body = body_of(api.handle(get_event(JOB_ID), None))
    assert body["status"] == "SUCCEEDED" and body["result"] == {"placeholder": True}
    assert s3.json(JOB_KEY)["status"] == "SUCCEEDED"


def test_svc21_unknown_route_is_404(env):
    s3, lam, clock, api = env
    response = api.handle({"routeKey": "DELETE /investigations/{id}", "requestContext": {}}, None)
    assert response["statusCode"] == 404 and body_of(response)["error"]["code"] == "ROUTE_NOT_FOUND"
