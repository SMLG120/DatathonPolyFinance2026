"""Concurrency, retry and snapshot regressions from the repository audit; no AWS calls."""

import json

import pytest

from backend.common.data import build_manifest
from backend.common.jobs import JobStore
from backend.common.policies import PolicyStore
from service_fakes import BUCKET, FakeClock, FakeS3, Service, api_fixture, build_worker, client_error, snapshot_contents


def challenge(svc, job, key="audit-challenge-key"):
    return svc.call("POST /investigations/{id}/challenge", api_fixture("challenge_change_rule")["request_body"],
                    path={"id": job["id"]}, key=key)


@pytest.mark.parametrize("same_key", [True, False])
def test_challenges_interleaved_at_policy_write_return_their_stored_policy(same_key):
    svc = Service()
    parent = svc.investigate(svc.confirm())
    nested = []

    def interleave(key):
        if key.startswith("policies/"):
            response = challenge(svc, parent, "audit-challenge-key" if same_key else "audit-other-key")
            nested.append(response)
            assert response[0] == 202
            # The other invocation can even finish the job before this request resumes.
            svc.run_worker(response[1]["investigation"]["id"])
        else:
            svc.s3.before_put.append(interleave)

    svc.s3.before_put.append(interleave)
    outer = challenge(svc, parent)
    assert outer[0] == 202
    for _, response in [outer, *nested]:
        child = svc.get(response["investigation"]["id"])
        assert response["policy"]["version"] == child["policy_version"]
        assert response["policy"] == svc.api._policies.get(child["policy_id"], child["policy_version"])
    assert len(svc.s3.keys("policies/")) == (2 if same_key else 3)
    assert (outer[1]["investigation"]["id"] == nested[0][1]["investigation"]["id"]) == same_key
    if same_key:
        assert outer[1]["policy"] == nested[0][1]["policy"]
        assert len(svc.lambda_client.invocations) == 2  # parent and child, no duplicate work


@pytest.mark.parametrize("failure_point", ["before_policy", "after_policy", "before_ready"])
def test_challenge_retry_resumes_reserved_version_after_interrupted_write(failure_point):
    svc = Service()
    parent = svc.investigate(svc.confirm())
    original_create = svc.api._policies.create
    original_update = svc.api._store.update

    def broken_create(policy):
        svc.api._policies.create = original_create
        if failure_point == "after_policy":
            original_create(policy)
        raise client_error("ServiceUnavailable", "PutObject", 503)

    def broken_update(*args, **kwargs):
        svc.api._store.update = original_update
        raise client_error("ServiceUnavailable", "PutObject", 503)

    if failure_point == "before_ready":
        svc.api._store.update = broken_update
    else:
        svc.api._policies.create = broken_create
    assert challenge(svc, parent)[0] == 500
    assert len(svc.lambda_client.invocations) == 1
    svc.clock.advance(1)  # a retry must use the persisted timestamp, not the new request's time
    status, response = challenge(svc, parent)
    assert status == 202
    assert response["policy"]["version"] == 2
    assert len(svc.s3.keys("policies/")) == 2
    child_id = response["investigation"]["id"]
    assert svc.run_worker(child_id)["status"] == "SUCCEEDED"
    assert svc.get(child_id)["policy_version"] == 2


def test_worker_cannot_claim_challenge_before_its_policy_is_ready():
    svc = Service()
    parent = svc.investigate(svc.confirm())
    original_create = svc.api._policies.create
    attempted = []

    def create(policy):
        child = next(svc.s3.json(k) for k in svc.s3.keys("jobs/") if svc.s3.json(k)["id"] != parent["id"])
        attempted.append(svc.run_worker(child["id"]))
        assert svc.get(child["id"])["status"] == "QUEUED"
        original_create(policy)

    svc.api._policies.create = create
    assert challenge(svc, parent)[0] == 202
    assert attempted == [{"outcome": "duplicate", "status": "QUEUED"}]


def test_worker_rejects_a_new_snapshot_instead_of_overwriting_accepted_provenance():
    svc = Service()
    job = svc.investigate(svc.confirm(), run=False)
    contents = snapshot_contents()
    market = json.loads(contents["market_data.json"])
    series = market["prices"]["NVDA"]["series"]
    endpoint = max(i for i, row in enumerate(series) if row[0] <= "2022-12-30")
    series[endpoint][1] *= 2
    contents["market_data.json"] = json.dumps(market).encode()
    contents.pop("manifest.json")
    manifest = build_manifest(market["valuation_date"], contents, {})
    contents["manifest.json"] = json.dumps(manifest).encode()
    replacement = manifest["snapshot_id"]
    assert replacement != svc.snapshot_id
    for name, data in contents.items():
        svc.s3.objects[f"snapshots/{replacement}/{name}"] = data
    svc.worker = build_worker(svc.s3, svc.bedrock, svc.clock, snapshot_id=replacement)
    svc.run_worker(job["id"])
    result = svc.get(job["id"])
    assert result["status"] == "FAILED" and result["failure"]["code"] == "DATA_UNAVAILABLE"
    assert result["result"] is None and svc.bedrock.calls == []
    assert svc.s3.json(f"jobs/{job['id']}.json")["internal"]["data_snapshot_id"] == svc.snapshot_id


def test_latest_policy_version_reads_all_s3_pages_in_lexicographic_order():
    s3 = FakeS3()
    for version in range(1, 2001):
        s3.objects[f"policies/pol-audit/v{version}.json"] = b"{}"
    assert PolicyStore(s3, BUCKET).latest_version("pol-audit") == 2000


def test_all_corrections_are_returned_across_s3_pages():
    s3 = FakeS3()
    store = JobStore(s3, BUCKET, FakeClock())
    job_id = "inv-" + "a" * 32
    for number in range(205):
        assert store.put_correction(job_id, {"correction_id": f"corr-{number:04}", "provenance": {"asserted_at": "2026-11-15"}})
    corrections = store.list_corrections(job_id)
    assert len(corrections) == 205
    assert corrections[-1]["correction_id"] == "corr-0204"
