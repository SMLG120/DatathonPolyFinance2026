"""Job store: conditional writes only, compare-and-swap, terminal immutability."""

import json

import pytest

from backend.common.jobs import (
    ConcurrentUpdateError,
    InvalidTransitionError,
    JobNotFoundError,
    JobStore,
    StateConflict,
    TerminalStateError,
    is_valid_job_id,
)
from service_fakes import BUCKET, FakeClock, FakeS3, client_error

JOB_ID = "inv-" + "1" * 32
KEY = f"jobs/{JOB_ID}.json"


def make_job(status="QUEUED"):
    return {"id": JOB_ID, "status": status, "steps": [], "updated_at": "x"}


@pytest.fixture
def store_env():
    s3, clock = FakeS3(), FakeClock()
    return s3, clock, JobStore(s3, BUCKET, clock)


def test_js01_create_is_once_only(store_env):
    s3, clock, store = store_env
    job, etag, created = store.create(make_job())
    assert created and etag
    other = dict(make_job(), marker="second")
    job2, etag2, created2 = store.create(other)
    assert not created2 and "marker" not in job2 and etag2 == etag
    assert s3.puts[0]["IfNoneMatch"] == "*"


def test_js02_create_retries_on_conditional_request_conflict(store_env):
    s3, clock, store = store_env
    s3.fail_puts_with = [client_error("ConditionalRequestConflict", "PutObject", 409)]
    _, _, created = store.create(make_job())
    assert created and len(s3.puts) == 2


def test_js03_update_uses_if_match_and_retries_when_it_loses_the_race(store_env):
    s3, clock, store = store_env
    store.create(make_job())

    def concurrent_writer(key):
        job = s3.json(KEY)
        job["steps"].append("written by someone else")
        s3.objects[KEY] = json.dumps(job).encode()

    s3.before_put.append(concurrent_writer)
    calls = []

    def mutate(draft):
        calls.append(list(draft["steps"]))
        draft["steps"].append("mine")

    updated = store.update(JOB_ID, mutate)
    assert updated["steps"] == ["written by someone else", "mine"]  # nothing lost
    assert calls == [[], ["written by someone else"]]  # mutate re-ran on the fresh copy
    assert all(put["IfMatch"] or put["IfNoneMatch"] for put in s3.puts)


def test_js04_update_gives_up_after_bounded_attempts(store_env):
    s3, clock, store = store_env
    store.create(make_job())
    s3.fail_puts_with = [client_error("PreconditionFailed", "PutObject", 412)] * 3
    with pytest.raises(ConcurrentUpdateError):
        store.update(JOB_ID, lambda draft: None, max_attempts=3)


@pytest.mark.parametrize("terminal", ["SUCCEEDED", "FAILED"])
def test_js05_terminal_jobs_are_immutable(store_env, terminal):
    s3, clock, store = store_env
    store.create(make_job(terminal))
    before = s3.objects[KEY]
    called = []
    with pytest.raises(TerminalStateError) as caught:
        store.update(JOB_ID, lambda draft: called.append(1) or draft.update(status="RUNNING"))
    assert caught.value.job["status"] == terminal
    assert called == []  # the mutation is not even attempted
    assert s3.objects[KEY] == before


@pytest.mark.parametrize("start, end", [("QUEUED", "SUCCEEDED"), ("RUNNING", "QUEUED"), ("QUEUED", "PAUSED")])
def test_js06_only_lifecycle_transitions_are_allowed(store_env, start, end):
    s3, clock, store = store_env
    store.create(make_job(start))
    with pytest.raises(InvalidTransitionError):
        store.update(JOB_ID, lambda draft: draft.update(status=end))
    assert s3.json(KEY)["status"] == start


def test_js07_state_conflict_from_the_mutation_abandons_the_write(store_env):
    s3, clock, store = store_env
    store.create(make_job("RUNNING"))
    writes = len(s3.puts)

    def mutate(draft):
        raise StateConflict("not mine", draft)

    with pytest.raises(StateConflict):
        store.update(JOB_ID, mutate)
    assert len(s3.puts) == writes


def test_js08_results_and_traces_are_write_once(store_env):
    s3, clock, store = store_env
    assert store.put_result(JOB_ID, {"n": 1}) is True
    assert store.put_result(JOB_ID, {"n": 2}) is False
    assert store.get_result(JOB_ID) == {"n": 1}
    assert store.put_trace(JOB_ID, {"t": 1}) is True
    assert store.put_trace(JOB_ID, {"t": 2}) is False


def test_js09_missing_job(store_env):
    s3, clock, store = store_env
    assert store.get(JOB_ID) is None
    with pytest.raises(JobNotFoundError):
        store.update(JOB_ID, lambda draft: None)


def test_js10_access_denied_is_not_mistaken_for_missing_when_the_object_exists():
    """403 on a key that exists is a real permission problem and must surface."""
    s3, clock = FakeS3(), FakeClock()
    store = JobStore(s3, BUCKET, clock, can_list=True)
    store.create(make_job())
    s3.get_object = lambda **kwargs: (_ for _ in ()).throw(client_error("AccessDenied", "GetObject", 403))
    with pytest.raises(Exception) as caught:
        store.get(JOB_ID)
    assert "AccessDenied" in str(caught.value)


def test_js11_store_without_list_permission_surfaces_access_denied():
    s3, clock = FakeS3(missing_is_access_denied=True), FakeClock()
    store = JobStore(s3, BUCKET, clock, can_list=False)
    with pytest.raises(Exception) as caught:
        store.get(JOB_ID)
    assert "AccessDenied" in str(caught.value)


def test_js12_streaming_bodies_are_closed(store_env):
    s3, clock, store = store_env
    store.create(make_job())
    store.get(JOB_ID)
    assert s3.bodies and all(body.closed for body in s3.bodies)


def test_js13_job_id_format():
    """The contract id pattern allows no underscore, so the phase 1 form ``inv_<hex>`` is no longer an id."""
    import re

    from byb_contracts import load_schema

    assert is_valid_job_id("inv-" + "a" * 32)
    assert re.fullmatch(load_schema("common.schema.json")["$defs"]["id"]["pattern"], "inv-" + "a" * 32)
    for bad in ["inv_" + "a" * 32, "inv-" + "a" * 31, "inv-" + "A" * 32, "inv-" + "a" * 32 + "\n", "jobs/../x", None, 5]:
        assert not is_valid_job_id(bad)
