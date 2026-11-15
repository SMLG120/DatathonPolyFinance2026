"""Task 4: unit tests for the pure parts of ``live_check.py`` and an offline end-to-end run against a fake
transport that answers like the contract says the API does (its results come from the local engine).

Nothing here opens a socket: ``HttpTransport`` is never instantiated with a reachable address.
"""

import copy
import json
import urllib.error

import pytest
from byb_contracts import (
    api_body_errors,
    compute_content_hash,
    investigation_job_errors,
    validate_api_body,
)

import live_check as lc
from mateo_helpers import api_fixture, real_data_present, real_universe, run, scenario, synthetic_universe
from mateo_invariants import MATEO_OBJECTIVE

SECRET = "s3cr3t-Access-Code-Zx9"
BASE = "https://api.example.invalid"
KEY = "0b6f0c9e-5a7e-4c0e-9a55-1f2d3c4b5a61"


# ---------------------------------------------------------------- a fake deployment

class FakeApi:
    """Answers the seven routes from the local engine, per contracts/api.md. Knobs break one behaviour at a time."""

    def __init__(self, universe=None, polls_before_done=2, **knobs):
        self.universe = universe or synthetic_universe()
        self.scenario = scenario()
        self.polls_before_done = polls_before_done
        self.knobs = knobs
        self.calls, self.policies, self.jobs, self.keys = [], {}, {}, {}
        self.sent = 0

    # transport interface -------------------------------------------------
    def send(self, request):
        self.sent += 1
        assert "Authorization" not in request["headers"], "a request plan must never carry the access code"
        self.calls.append((request["method"], request["path"], copy.deepcopy(request["body"]), dict(request["headers"])))
        method, path, body = request["method"], request["path"], request["body"]
        if self.knobs.get("unauthorized"):
            return lc.Response(401, {"message": "Unauthorized"})
        if method == "GET" and path == "/portfolios/mateo":
            return self.portfolio()
        if method == "POST" and path == "/rules/interpret":
            return self.interpret(body)
        if method == "POST" and path == "/rules/confirm":
            return self.confirm(body)
        if method == "POST" and path == "/check":
            return self.check(body)
        if method == "POST" and path == "/investigations":
            return self.create(body, request["headers"])
        if method == "GET" and path.startswith("/investigations/"):
            return self.poll(path.rsplit("/", 1)[-1])
        return lc.Response(404, {"error": {"code": "NOT_FOUND", "message": "No such route.", "details": [], "request_id": None}})

    # routes --------------------------------------------------------------
    def portfolio(self):
        registry = self.universe["instruments"]["instruments"]
        ids = [p["instrument_id"] for p in self.scenario["portfolio"]["positions"]] + ["SPY"]
        s = copy.deepcopy(self.scenario)
        if self.knobs.get("wrong_weights"):
            s["portfolio"]["positions"][0]["weight"] = 0.30
        return lc.Response(200, {"schema_version": "1.0.0", "scenario": s, "instruments": {i: registry[i] for i in ids},
                                 "purchasable_instrument_ids": sorted(ids)})

    def interpret(self, body):
        if self.knobs.get("interpreter_down"):
            return lc.Response(504, {"error": {"code": "INTERPRETER_TIMEOUT", "message": "The interpreter did not finish in time.", "details": [], "request_id": None}})
        draft = api_fixture("interpret_mateo_clarification")["response_body"]
        draft["original_words"] = body["text"]
        if self.knobs.get("invented_threshold"):
            draft["proposed_rules"][0]["threshold"] = 0.05
        if self.knobs.get("no_oil_question"):
            option = draft["clarifications"][0]["options"][0]
            draft["proposed_rules"].append(option["proposed_rule"])
            draft["clarifications"] = []
        return lc.Response(200, draft)

    def confirm(self, body):
        validate_api_body("api.schema.json#/$defs/confirm_request", body)
        rules = []
        for item in body["confirmations"]:
            assert item["rule"]["status"] == "PROPOSED" and item["threshold"] == item["rule"]["threshold"]
            rules.append(dict(item["rule"], status="CONFIRMED", confirmed_at="2026-11-14T15:00:00Z", confirmed_by="demo_user"))
        if self.knobs.get("confirm_as_user_entered"):
            rules[0].update(origin="USER_STATED", threshold_source="USER_ENTERED")
        policy = {"schema_version": "1.0.0", "policy_id": f"pol-mateo-{len(self.policies) + 1:04d}", "persona_id": "mateo", "version": 1,
                  "parent_version": None, "created_at": "2026-11-14T15:00:00Z", "objectives": body["objectives"], "rules": rules,
                  "change_note": body["change_note"], "content_hash": "sha256:" + "0" * 64}
        policy["content_hash"] = compute_content_hash(policy)
        self.policies[(policy["policy_id"], 1)] = policy
        return lc.Response(201, {"schema_version": "1.0.0", "policy": policy})

    def engine(self, policy, purchase, **kwargs):
        return run(self.universe, policy, purchase, self.scenario["portfolio"], validate=False, **kwargs)

    def check(self, body):
        validate_api_body("api.schema.json#/$defs/check_request", body)
        if body["draft_rules"] is not None:
            result = self.engine(None, body["purchase_request"], draft_rules=body["draft_rules"])
            if self.knobs.get("preview_unknown_as_pass"):
                entry = result["rule_results"][0]
                entry.update(status="PASS", gap=entry["measured"]["upper"] - entry["limit"])
                result["summary"]["counts"] = {"pass": 1, "fail": 0, "unknown": 0}
                result["summary"]["headline"] = "ALL_PASS"
            return lc.Response(200, result)
        result = self.engine(self.policies[(body["policy_id"], body["policy_version"])], body["purchase_request"])
        if self.knobs.get("missing_as_zero"):  # ESGV treated as zero exposure: the upper bounds lose 0.15
            for entry in result["rule_results"]:
                if entry["rule_type"] == "exclusion":
                    entry["measured"]["upper"] -= 0.15
        if self.knobs.get("nondeterministic") and sum(1 for c in self.calls if c[1] == "/check") % 2 == 0:
            result["rule_results"][0]["reason"] += " "
        if self.knobs.get("gives_a_number"):
            result["max_compliant"].update(status="SUPPORTED", final_direct_weight=0.1, additional_purchase=0.1, verified_by_rerun=True)
        return lc.Response(200, result)

    def create(self, body, headers):
        validate_api_body("api.schema.json#/$defs/investigation_create_request", body)
        key = headers["Idempotency-Key"]
        if key in self.keys and not self.knobs.get("not_idempotent"):
            job_id = self.keys[key]
        else:
            job_id = f"inv-mateo-{len(self.jobs) + 1:04d}"
            self.keys[key] = job_id
            self.jobs[job_id] = {"body": body, "key": key, "polls": 0}
        return lc.Response(202, {"schema_version": "1.0.0", "id": job_id, "status": "QUEUED", "created_at": "2026-11-14T15:02:00Z",
                                 "deadline_at": "2026-11-14T15:04:30Z", "expires_at": "2026-11-15T15:02:00Z",
                                 "poll": {"path": f"/investigations/{job_id}", "interval_ms": 1500}})

    def poll(self, job_id):
        if job_id not in self.jobs:
            return lc.Response(404, {"error": {"code": "NOT_FOUND", "message": "No such investigation.", "details": [], "request_id": None}})
        record = self.jobs[job_id]
        record["polls"] += 1
        flaky = self.knobs.get("flaky_polls", ())
        if record["polls"] in flaky:
            kind = flaky[record["polls"]]
            if kind == "network":
                raise urllib.error.URLError("connection reset")
            return lc.Response(kind, {"message": "Too Many Requests" if kind == 429 else "Service Unavailable"})
        return lc.Response(200, self.job(job_id, record))

    def job(self, job_id, record):
        body = record["body"]
        template = api_fixture("investigation_mateo_succeeded")["response_body"]
        job = {
            "schema_version": "1.0.0", "id": job_id, "status": "QUEUED", "created_at": "2026-11-14T15:02:00Z", "updated_at": "2026-11-14T15:02:00Z",
            "deadline_at": "2026-11-14T15:04:30Z", "expires_at": "2026-11-15T15:02:00Z", "idempotency_key": record["key"], "persona_id": "mateo",
            "policy_id": body["policy_id"], "policy_version": body["policy_version"], "request": body["request"], "resolved_request": None,
            "parent_investigation_id": None, "challenge": None,
            "agent": {"mode": "DETERMINISTIC_FALLBACK", "model_id": None, "tool_rounds": 0, "note": "Fake transport: no model."},
            "steps": [], "clarification": None, "result": None, "explanation": [], "failure": None, "proposed_corrections": [],
        }
        if self.knobs.get("never_finishes") or record["polls"] <= self.polls_before_done:
            if record["polls"] > 1:
                job["status"], job["resolved_request"] = "RUNNING", body["request"]
            return job
        job["resolved_request"], job["updated_at"] = body["request"], "2026-11-14T15:02:27Z"
        if self.knobs.get("job_fails"):
            job.update(status="FAILED", failure={"code": "DATA_UNAVAILABLE", "message": "The holdings snapshot could not be read.", "retryable": True})
            return job
        result = self.engine(self.policies[(body["policy_id"], body["policy_version"])], body["request"])
        if self.knobs.get("worker_result_differs"):
            result["rule_results"][0]["measured"]["upper"] += 0.01
        steps = [dict(copy.deepcopy(step), seq=n, initiated_by="SERVER", evidence_ids=[]) for n, step in enumerate(template["steps"][-2:], 1)]
        if self.knobs.get("no_server_check"):
            steps = [dict(step, tool="get_portfolio") for step in steps]
        job.update(status="SUCCEEDED", steps=steps, result=result, explanation=[
            {"statement_id": "st-1", "text": result["rule_results"][0]["reason"], "evidence_ids": result["rule_results"][0]["evidence_ids"][:3], "rendered_by": "TEMPLATE"}])
        if self.knobs.get("malformed_job"):
            del job["result"]["rule_results"]
        if self.knobs.get("mutates_after_terminal") and record["polls"] > self.polls_before_done + 1:
            job["explanation"] = []
        return job


def drive(api, **options):
    lines = []
    report = lc.Report(lines.append)
    sleeps = []
    clock = {"t": 0.0}

    def sleep(seconds):
        sleeps.append(seconds)
        clock["t"] += seconds

    options.setdefault("idempotency_key", KEY)
    try:
        lc.run_live(api, report, sleep=sleep, clock=lambda: clock["t"], **options)
    except lc.Abort:
        pass
    return report, lines, sleeps


# ---------------------------------------------------------------- request building

def test_requests_follow_the_contract_request_schemas():
    s = scenario()
    purchase = s["demo_requests"][0]["purchase_request"]
    assert lc.portfolio_request() == {"method": "GET", "path": "/portfolios/mateo", "headers": {"Accept": "application/json"}, "body": None}
    interpret = lc.interpret_request(MATEO_OBJECTIVE)
    validate_api_body("api.schema.json#/$defs/interpret_request", interpret["body"])
    assert interpret["body"] == api_fixture("interpret_mateo_clarification")["request_body"]
    confirm = lc.confirm_request(s)
    validate_api_body("api.schema.json#/$defs/confirm_request", confirm["body"])
    assert confirm["body"]["policy_id"] is None and confirm["body"]["base_version"] is None and confirm["body"]["withdraw_rule_ids"] == []
    assert [c["rule"] for c in confirm["body"]["confirmations"]] == s["scenario_rules"]  # complete, as displayed
    assert [c["threshold"] for c in confirm["body"]["confirmations"]] == [0.0, 0.0]  # the scenario number, unchanged
    assert set(confirm["body"]) == set(api_fixture("confirm_robert_v1")["request_body"])
    check = lc.check_request("pol-x", 1, purchase)
    validate_api_body("api.schema.json#/$defs/check_request", check["body"])
    assert check["body"]["draft_rules"] is None and (check["body"]["policy_id"], check["body"]["policy_version"]) == ("pol-x", 1)
    preview = lc.preview_request(purchase)
    validate_api_body("api.schema.json#/$defs/check_request", preview["body"])
    assert preview["body"] == api_fixture("check_mateo_preview_unknown")["request_body"]
    create = lc.investigation_request("pol-x", 1, purchase, KEY)
    validate_api_body("api.schema.json#/$defs/investigation_create_request", create["body"])
    assert create["headers"]["Idempotency-Key"] == KEY and create["body"]["parent_investigation_id"] is None
    assert set(create["body"]) == set(api_fixture("investigation_accepted")["request_body"])
    for request in (interpret, confirm, check, preview, create):
        assert request["method"] == "POST" and request["headers"]["Content-Type"] == "application/json"
        assert "Authorization" not in request["headers"]  # added by the transport only


def test_idempotency_keys_are_random_and_well_formed():
    keys = {lc.new_idempotency_key() for _ in range(50)}
    assert len(keys) == 50 and all(lc.IDEMPOTENCY_KEY_PATTERN.match(key) for key in keys)
    with pytest.raises(ValueError):
        lc.build_request("POST", "/investigations", {}, idempotency_key="short")
    with pytest.raises(ValueError):
        lc.build_request("GET", "investigations/x")


def test_base_url_must_be_https_and_plain():
    assert lc.normalise_base_url("https://abc.execute-api.us-east-1.amazonaws.com/") == "https://abc.execute-api.us-east-1.amazonaws.com"
    assert lc.normalise_base_url("https://host/prod") == "https://host/prod"
    assert lc.normalise_base_url("http://localhost:3000") == "http://localhost:3000"
    for bad in ("http://api.example.invalid", "ftp://x", "api.example.invalid", "https://user:pw@host", "https://host/?code=1"):
        with pytest.raises(lc.CouldNotRun):
            lc.normalise_base_url(bad)


def test_poll_budget_is_bounded():
    assert lc.max_polls(180, 1500) == 121
    assert lc.max_polls(180, 500) == 361 and lc.max_polls(1, 1500) == 2
    assert lc.clamp_interval(1500) == 1500 and lc.clamp_interval(1) == 500 and lc.clamp_interval(10**9) == 10000
    assert lc.clamp_interval(None) == 1500 and lc.clamp_interval("fast") == 1500 and lc.clamp_interval(True) == 1500
    assert 9 + lc.max_polls(lc.POLL_DEADLINE_SECONDS, lc.MIN_POLL_INTERVAL_MS) > lc.DEFAULT_MAX_REQUESTS  # the transport cap is the last bound
    assert 9 + lc.max_polls(lc.POLL_DEADLINE_SECONDS, lc.POLL_INTERVAL_MS) + 10 <= lc.DEFAULT_MAX_REQUESTS


# ---------------------------------------------------------------- the access code

def test_access_code_comes_from_the_environment_only():
    assert lc.read_access_code({lc.ENV_ACCESS_CODE: f"  {SECRET}\n"}) == SECRET
    for environ in ({}, {lc.ENV_ACCESS_CODE: ""}, {lc.ENV_ACCESS_CODE: "   "}):
        with pytest.raises(lc.CouldNotRun):
            lc.read_access_code(environ)
    options = lc.parse_args(["--base-url", BASE])
    assert not [name for name in vars(options) if "code" in name or "token" in name or "secret" in name]
    for flag in ("--access-code", "--code", "--token"):
        assert lc.main(["--base-url", BASE, flag, SECRET], environ={}, out=lambda line: None) == lc.EXIT_COULD_NOT_RUN


def test_redaction_removes_the_code_and_any_bearer_value():
    assert SECRET not in lc.redact(f"error: Authorization: Bearer {SECRET} rejected; echo {SECRET}", SECRET)
    assert lc.redact("Authorization: Bearer abc.def-123", None) == "Authorization: Bearer <redacted>"
    assert lc.redact("nothing secret", SECRET) == "nothing secret"


def test_missing_access_code_is_exit_2_and_sends_nothing():
    made = []
    lines = []
    code = lc.main(["--base-url", BASE], environ={}, transport_factory=lambda *a: made.append(a), out=lines.append)
    assert code == lc.EXIT_COULD_NOT_RUN and made == [] and "BYB_ACCESS_CODE" in lines[-1]


def test_dry_run_prints_the_plan_sends_nothing_and_needs_no_code():
    lines, made = [], []
    code = lc.main(["--dry-run", "--base-url", "https://example.invalid"], environ={lc.ENV_ACCESS_CODE: SECRET},
                   transport_factory=lambda *a: made.append(a), out=lines.append)
    text = "\n".join(lines)
    assert code == lc.EXIT_PASS and made == [] and SECRET not in text
    assert lines[0].startswith("DRY RUN: nothing is sent. 10 planned requests")
    for wanted in ("GET https://example.invalid/portfolios/mateo", "POST https://example.invalid/rules/interpret", "POST https://example.invalid/rules/confirm",
                   "POST https://example.invalid/check", "POST https://example.invalid/investigations", "GET https://example.invalid/investigations/<id from the 202>",
                   "Idempotency-Key", "at most 121 polls", "client deadline 180 s"):
        assert wanted in text
    assert lc.main(["--dry-run", "--base-url", "https://example.invalid"], environ={}, out=lambda line: None) == lc.EXIT_PASS
    plan = lc.planned_requests(None)  # outside a checkout: placeholders instead of the scenario file
    assert len(plan) == 10 and all("Authorization" not in request["headers"] for request in plan)


# ---------------------------------------------------------------- polling against a fake transport

def scripted(answers):
    """A ``send`` that returns the scripted answers in order (an exception instance is raised)."""
    queue, seen = list(answers), []

    def send(request):
        seen.append(request)
        answer = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(answer, Exception):
            raise answer
        return answer

    return send, seen


def job_answer(status):
    return lc.Response(200, {"id": "inv-1", "status": status})


def timer():
    state = {"t": 0.0, "sleeps": []}

    def sleep(seconds):
        state["sleeps"].append(seconds)
        state["t"] += seconds

    return state, sleep, (lambda: state["t"])


@pytest.mark.parametrize("terminal", ["SUCCEEDED", "FAILED"])
def test_polling_stops_on_a_terminal_state(terminal):
    send, seen = scripted([job_answer("QUEUED"), job_answer("RUNNING"), job_answer("RUNNING"), job_answer(terminal), job_answer("QUEUED")])
    state, sleep, clock = timer()
    outcome = lc.poll_until_terminal(send, "/investigations/inv-1", 1500, 180, sleep, clock)
    assert outcome["outcome"] == "TERMINAL" and outcome["job"]["status"] == terminal and outcome["polls"] == 4 == len(seen)
    assert state["sleeps"] == [1.5, 1.5, 1.5]  # the contract interval, between polls only
    assert all(request == {"method": "GET", "path": "/investigations/inv-1", "headers": {"Accept": "application/json"}, "body": None} for request in seen)


def test_polling_stops_at_the_client_deadline_with_a_bounded_number_of_requests():
    send, seen = scripted([job_answer("RUNNING")])
    state, sleep, clock = timer()
    outcome = lc.poll_until_terminal(send, "/investigations/inv-1", 1500, 180, sleep, clock)
    assert outcome["outcome"] == "DEADLINE" and outcome["job"]["status"] == "RUNNING"
    assert len(seen) == outcome["polls"] <= lc.max_polls(180, 1500) == 121
    assert state["t"] <= 180  # never sleeps past the deadline
    # a clock that never advances cannot make it loop forever either
    send, seen = scripted([job_answer("QUEUED")])
    outcome = lc.poll_until_terminal(send, "/investigations/inv-1", 1500, 180, lambda seconds: None, lambda: 0.0)
    assert outcome["outcome"] == "DEADLINE" and len(seen) == 121


def test_polling_retries_network_errors_429_and_5xx_then_succeeds():
    send, seen = scripted([urllib.error.URLError("reset"), lc.Response(429, None), lc.Response(503, None), TimeoutError(), job_answer("RUNNING"), job_answer("SUCCEEDED")])
    state, sleep, clock = timer()
    outcome = lc.poll_until_terminal(send, "/investigations/inv-1", 1500, 180, sleep, clock)
    assert outcome["outcome"] == "TERMINAL" and outcome["polls"] == 6 and outcome["retries"] == 4
    assert state["sleeps"] == [1.5] * 5


@pytest.mark.parametrize("status, wanted", [(401, "UNAUTHORIZED"), (403, "UNAUTHORIZED"), (404, "GONE"), (410, "GONE")])
def test_polling_stops_at_once_on_auth_and_gone(status, wanted):
    send, seen = scripted([job_answer("RUNNING"), lc.Response(status, {"message": "x"}), job_answer("SUCCEEDED")])
    state, sleep, clock = timer()
    outcome = lc.poll_until_terminal(send, "/investigations/inv-1", 1500, 180, sleep, clock)
    assert outcome["outcome"] == wanted and len(seen) == 2 and outcome["job"]["status"] == "RUNNING"


def test_polling_uses_the_servers_interval_within_bounds():
    for given, used in ((2000, 2.0), (1, 0.5), (10**7, 10.0)):
        send, _ = scripted([job_answer("QUEUED"), job_answer("SUCCEEDED")])
        state, sleep, clock = timer()
        lc.poll_until_terminal(send, "/investigations/inv-1", given, 180, sleep, clock)
        assert state["sleeps"] == [used]


# ---------------------------------------------------------------- response checks (pure)

def test_json_diff_reports_paths_and_respects_the_tolerance():
    a = {"x": [1.0, {"y": "a"}], "z": None}
    assert lc.json_diff(a, copy.deepcopy(a)) == []
    assert lc.json_diff(a, {"x": [1.0 + 1e-12, {"y": "a"}], "z": None}) == []
    assert lc.json_diff(a, {"x": [1.0 + 1e-12, {"y": "a"}], "z": None}, tolerance=0.0) == ["result.x[0]: 1.0 != 1.000000000001"]
    assert lc.json_diff(a, {"x": [1.0, {"y": "b"}], "z": None}) == ["result.x[1].y: 'a' != 'b'"]
    assert lc.json_diff(a, {"x": [1.0], "z": None, "w": 1}) == ["result.w: present on one side only", "result.x: 2 items != 1 items"]
    assert lc.json_diff({"v": True}, {"v": 1}) != [] and lc.json_diff({"v": None}, {"v": 0}) != []
    assert len(lc.json_diff({str(i): i for i in range(100)}, {str(i): i + 1 for i in range(100)})) == 20  # bounded output


def test_shape_validation_uses_the_contract_validators():
    job = api_fixture("investigation_mateo_succeeded")["response_body"]
    assert lc.shape_problems("investigation_job.schema.json", job) == []
    assert lc.shape_problems("check_result.schema.json", job["result"]) == []
    broken = copy.deepcopy(job["result"])
    broken["unexpected"] = 1
    assert lc.shape_problems("check_result.schema.json", broken) != []
    assert lc.shape_problems("api.schema.json#/$defs/investigation_accepted", api_fixture("investigation_accepted")["response_body"]) == []
    assert lc.shape_problems("api.schema.json#/$defs/investigation_accepted", {"id": "x"}) != []


def test_contract_fixtures_pass_the_live_response_checks():
    job = api_fixture("investigation_mateo_succeeded")["response_body"]
    accepted = {"id": job["id"], "status": "QUEUED", "poll": {"path": f"/investigations/{job['id']}", "interval_ms": 1500}}
    policy = {"policy_id": job["policy_id"], "version": job["policy_version"]}
    assert lc.accepted_problems(api_fixture("investigation_accepted")["response_body"]) == []
    assert lc.job_problems(job, accepted, policy, job["request"], job["idempotency_key"]) == []
    assert lc.immutable_problems(job, copy.deepcopy(job)) == []
    later = copy.deepcopy(job)
    later["proposed_corrections"].append({"correction_id": "c"})  # only corrections may grow
    assert lc.immutable_problems(job, later) == []
    later["result"]["summary"]["headline"] = "ALL_PASS"
    assert lc.immutable_problems(job, later) == ["terminal job changed between two reads: result"]
    failed = api_fixture("investigation_failed")["response_body"]
    problems = lc.job_problems(failed, {"id": failed["id"]}, policy, job["request"], KEY)
    assert len(problems) == 1 and "FAILED" in problems[0] and "DATA_UNAVAILABLE" in problems[0]
    preview = api_fixture("check_mateo_preview_unknown")["response_body"]
    assert [p for p in lc.preview_result_problems(preview) if "no cited record backs" not in p] == []  # fixture evidence is illustrative (FINDINGS L1)


# ---------------------------------------------------------------- the whole run, offline

def test_the_fake_deployment_answers_within_the_contract():
    api = FakeApi()
    report, lines, _ = drive(api)
    for method, path, body, _headers in api.calls:
        if path == "/rules/confirm":
            assert api_body_errors("api.schema.json#/$defs/confirm_request", body) == []
    job = api.job("inv-mateo-0001", dict(api.jobs["inv-mateo-0001"], polls=99))
    assert investigation_job_errors(job) == []
    assert report.failures == [], lines


def test_full_run_passes_against_a_conforming_api_and_is_bounded():
    api = FakeApi(polls_before_done=3)
    report, lines, sleeps = drive(api)
    assert report.failures == [] and report.warnings == [], "\n".join(lines)
    routes = [(method, path) for method, path, _, _ in api.calls]
    assert routes[:8] == [("GET", "/portfolios/mateo"), ("POST", "/rules/interpret"), ("POST", "/rules/confirm"), ("POST", "/check"), ("POST", "/check"),
                          ("POST", "/check"), ("POST", "/investigations"), ("POST", "/investigations")]
    polls = [r for r in routes if r == ("GET", "/investigations/inv-mateo-0001")]
    assert len(polls) == 4 + 1 and len(routes) == 8 + 5  # QUEUED, RUNNING, RUNNING, SUCCEEDED, then one immutability read
    assert sleeps == [1.5, 1.5, 1.5]
    assert len(api.jobs) == 1 and len(api.policies) == 1  # one policy, one investigation, despite the replay
    create = [headers for method, path, _, headers in api.calls if path == "/investigations"]
    assert create[0]["Idempotency-Key"] == create[1]["Idempotency-Key"] == KEY
    assert report.checks >= 20 and all(line.startswith(("[PASS]", "[WARN]")) for line in lines)


@pytest.mark.skipif(not real_data_present(), reason="data/processed is not present")
def test_full_run_with_compare_local_on_the_real_data():
    report, lines, _ = drive(FakeApi(universe=real_universe()), compare_local=True)
    assert report.failures == [], "\n".join(lines)
    assert any("compare-local" in line and "byte-identical canonical JSON" in line for line in lines)


@pytest.mark.skipif(not real_data_present(), reason="data/processed is not present")
def test_compare_local_detects_a_deployment_running_on_other_data():
    report, lines, _ = drive(FakeApi(universe=synthetic_universe()), compare_local=True)  # deployed data != local data/processed
    assert report.failures == ["compare-local: the live result equals backend.engine.check_rules on data/processed"]
    assert any(line.strip().startswith("- result.") for line in lines)  # the differing paths are printed


# fault -> the check that must fail. The contract validator (run first, as part of the shape check of the same
# response) may catch it before the script's own invariant does; either way the run fails on that response.
FAULTS = {
    "wrong_weights": ("portfolio: Mateo's D7 scenario", "GET /portfolios/mateo"),
    "invented_threshold": ("interpret: words preserved, drafts PROPOSED, no invented threshold", "POST /rules/interpret"),
    "no_oil_question": ("interpret: asks what 'oil' means",),
    "confirm_as_user_entered": ("confirm: version 1",),
    "missing_as_zero": ("check: invariants and Mateo's outcome", "POST /check (stored policy)"),
    "gives_a_number": ("check: invariants and Mateo's outcome", "POST /check (stored policy)"),
    "nondeterministic": ("check: same inputs give an identical document",),
    "preview_unknown_as_pass": ("preview: labelled, draft only, UNKNOWN never shown as a pass", "POST /check (preview)"),
    "not_idempotent": ("investigation: an idempotent replay returns the same id",),
    "never_finishes": ("polling: reached a terminal state before the client deadline",),
    "job_fails": ("job: SUCCEEDED with a result",),
    "no_server_check": ("job: SUCCEEDED with a result",),
    "worker_result_differs": ("result: the investigation's result is the deterministic /check result", "job: investigation_job shape"),
    "malformed_job": ("response structure", "job: investigation_job shape"),
    "mutates_after_terminal": ("job: terminal members are immutable on a second read",),
}


@pytest.mark.parametrize("fault", list(FAULTS))
def test_each_contract_violation_is_caught(fault):
    api = FakeApi(**{fault: True})
    report, lines, _ = drive(api)
    assert any(name.startswith(FAULTS[fault]) for name in report.failures), "\n".join(lines)
    assert api.sent <= lc.DEFAULT_MAX_REQUESTS
    if fault == "never_finishes":
        assert sum(1 for method, path, _, _ in api.calls if method == "GET" and path.startswith("/investigations/")) <= 121


def test_the_scripts_own_invariants_catch_false_passes_without_the_contract_validators():
    """The same tampered documents, checked by the pure functions alone (no ``byb_contracts``)."""
    api = FakeApi()
    s = scenario()
    purchase = s["demo_requests"][0]["purchase_request"]
    policy = api.confirm(lc.confirm_request(s)["body"]).body["policy"]
    equity = lc.in_scope_equity_weight(s["portfolio"], api.portfolio().body["instruments"], purchase)
    assert equity == pytest.approx(0.65)
    good = api.check(lc.check_request(policy["policy_id"], 1, purchase)["body"]).body
    assert lc.stored_result_problems(good, policy, purchase, equity) == []

    def tampered(change):
        result = copy.deepcopy(good)
        change(result)
        return lc.stored_result_problems(result, policy, purchase, equity)

    def missing_as_zero(result):  # ESGV counted as zero exposure
        result["rule_results"][0]["measured"]["upper"] -= 0.15

    def unknown_as_pass(result):
        result["rule_results"][1].update(status="PASS", gap=0.0, breaching_subjects=[])

    def number_without_proof(result):
        result["max_compliant"].update(status="SUPPORTED", final_direct_weight=0.1, additional_purchase=0.1, verified_by_rerun=True)

    def finding_dropped(result):
        result["starting_portfolio_findings"] = result["starting_portfolio_findings"][1:]

    def effect_as_lower_end(result):  # the unresolved effect reported as its lower end only
        result["starting_portfolio_findings"][0]["purchase_effect"]["upper_change"] = 0.0

    def rescaled(result):
        result["data_coverage"][0].update(coverage_fraction=1.0, status="COVERED")

    def cause_dropped(result):
        result["rule_results"][0]["unknown_causes"].remove("MISSING_HOLDINGS")

    def headline(result):
        result["summary"]["headline"] = "ALL_PASS"

    def dangling_evidence(result):
        result["rule_results"][0]["evidence_ids"].append("ev-does-not-exist")

    def wrong_state(result):  # the right digits attached to the wrong portfolio state
        for record in result["evidence"]:
            if record["metric_id"] == "exposure_upper" and record["subject"]["kind"] == "RULE" and record["subject"]["portfolio_state"] == "PROPOSED":
                record["subject"]["portfolio_state"] = "STARTING"

    def esgv_sourced(result):
        result["data_coverage"][1].update(holdings_date="2026-11-12", source_id="made_up")

    for change in (missing_as_zero, unknown_as_pass, number_without_proof, finding_dropped, effect_as_lower_end, rescaled, cause_dropped,
                   headline, dangling_evidence, wrong_state, esgv_sourced):
        assert tampered(change) != [], change.__name__
    preview = api.check(lc.preview_request(purchase)["body"]).body
    assert lc.preview_result_problems(preview) == [] and preview["rule_results"][0]["status"] == "UNKNOWN"
    shown_as_pass = copy.deepcopy(preview)
    shown_as_pass["rule_results"][0].update(status="PASS", gap=0.013)
    shown_as_pass["summary"].update(headline="ALL_PASS", counts={"pass": 1, "fail": 0, "unknown": 0})
    assert any("status PASS but bounds" in problem for problem in lc.preview_result_problems(shown_as_pass))
    not_labelled = copy.deepcopy(preview)
    not_labelled["preview"] = False
    assert lc.preview_result_problems(not_labelled) != []


def test_interpreter_outage_is_a_warning_unless_required():
    report, lines, _ = drive(FakeApi(interpreter_down=True))
    assert report.failures == [] and report.warnings == ["POST /rules/interpret"]
    report, lines, _ = drive(FakeApi(interpreter_down=True), require_interpreter=True)
    assert report.failures and report.failures[0].startswith("POST /rules/interpret")
    api = FakeApi()
    report, _, _ = drive(api, skip_interpret=True)
    assert report.failures == [] and ("POST", "/rules/interpret") not in [(m, p) for m, p, _, _ in api.calls]


def test_polling_survives_transient_errors_in_the_full_run():
    api = FakeApi(polls_before_done=2, flaky_polls={1: "network", 2: 429, 3: 503})
    report, lines, sleeps = drive(api)
    assert report.failures == [], "\n".join(lines)
    assert any("3 retries" in line for line in lines)


# ---------------------------------------------------------------- main(): exit codes, no secret in the output

def run_main(api, *extra, environ=None):
    lines = []
    seen = {}

    def factory(base_url, access_code, timeout, max_requests):
        seen.update(base_url=base_url, access_code=access_code, timeout=timeout, max_requests=max_requests)
        return api

    ticks = {"t": 0.0}

    def sleep(seconds):
        ticks["t"] += seconds

    code = lc.main(["--base-url", BASE, *extra], environ={lc.ENV_ACCESS_CODE: SECRET} if environ is None else environ,
                   transport_factory=factory, out=lines.append, sleep=sleep, clock=lambda: ticks["t"])
    return code, lines, seen


def test_main_exit_codes():
    code, lines, seen = run_main(FakeApi(polls_before_done=1))
    assert code == lc.EXIT_PASS and lines[-1].startswith("RESULT: PASS"), "\n".join(lines)
    assert seen["access_code"] == SECRET and seen["base_url"] == BASE and seen["max_requests"] == lc.DEFAULT_MAX_REQUESTS
    code, lines, _ = run_main(FakeApi(polls_before_done=1, missing_as_zero=True))
    assert code == lc.EXIT_FAIL and lines[-1].startswith("RESULT: FAIL")
    code, lines, _ = run_main(FakeApi(unauthorized=True))
    assert code == lc.EXIT_COULD_NOT_RUN and lines[-1].startswith("COULD NOT RUN") and "401" in lines[-1]
    code, lines, _ = run_main(FakeApi(), "--max-requests", "3")
    assert code == lc.EXIT_COULD_NOT_RUN


def test_network_failure_is_exit_2():
    class Down:
        sent = 0

        def send(self, request):
            raise urllib.error.URLError("name resolution failed")

    code, lines, _ = run_main(Down())
    assert code == lc.EXIT_COULD_NOT_RUN and "network error" in lines[-1]


def test_the_access_code_never_reaches_the_output_even_if_the_server_echoes_it():
    class Echo(FakeApi):
        def portfolio(self):
            return lc.Response(500, {"error": {"code": f"INTERNAL_ERROR {SECRET}", "message": f"token Bearer {SECRET}", "details": [], "request_id": SECRET}})

    for api in (Echo(), FakeApi(polls_before_done=1), FakeApi(job_fails=True), FakeApi(unauthorized=True)):
        code, lines, _ = run_main(api)
        assert SECRET not in "\n".join(lines)
        assert SECRET not in json.dumps([call for call in api.calls])  # nor into any request plan


def test_http_transport_adds_the_bearer_header_and_enforces_the_budget(monkeypatch):
    transport = lc.HttpTransport(BASE, SECRET, timeout=1, max_requests=2)
    captured = []

    class Reply:
        status = 200

        def read(self):
            return b'{"ok": true}'

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def fake_open(request, timeout):
        captured.append((request.full_url, request.get_method(), dict(request.header_items()), request.data, timeout))
        return Reply()

    monkeypatch.setattr(transport._opener, "open", fake_open)  # no socket is opened
    response = transport.send(lc.check_request("pol-x", 1, {"instrument_id": "SPY"}))
    assert response.status == 200 and response.body == {"ok": True}
    url, method, headers, data, timeout = captured[0]
    assert url == BASE + "/check" and method == "POST" and timeout == 1
    assert headers["Authorization"] == f"Bearer {SECRET}" and headers["Content-type"] == "application/json"
    assert json.loads(data)["policy_id"] == "pol-x"
    transport.send(lc.portfolio_request())
    with pytest.raises(lc.CouldNotRun):
        transport.send(lc.portfolio_request())
    assert transport.sent == 2 and len(captured) == 2
    assert SECRET not in repr(vars(lc.Report(print)))


def test_outside_a_checkout_the_minimal_shape_check_still_guards_the_run(monkeypatch):
    """Without ``byb_contracts`` the script falls back to a required-member check; a malformed body is then a
    reported failure (exit 1), never a traceback."""
    monkeypatch.setattr(lc, "_contracts", None)
    report, lines, _ = drive(FakeApi())
    assert report.failures == [], "\n".join(lines)
    code, lines, _ = run_main(FakeApi(polls_before_done=1, malformed_job=True))
    assert code == lc.EXIT_FAIL and any(line.startswith("[FAIL] response structure") for line in lines)
    assert lc.shape_problems("check_result.schema.json", {"schema_version": "1.0.0"}) != []
    assert lc.shape_problems("check_result.schema.json", []) == ["check_result.schema.json: the body is not a JSON object"]
