"""Follow-up of the code review of "Customize this profile" (findings F4, F5, F6, F9), through the two Lambda handlers.

F4  evidence of a customized portfolio says that the user entered the starting weights; default flows say nothing new.
F5  a clarification never offers, as supported, a demo request the engine would refuse on the job's portfolio.
F6  a follow-up investigation (``parent_investigation_id``) is about the same portfolio as its parent.
F9  a stored request the engine refuses when the worker runs ends the job FAILED, never SUCCEEDED with INVALID_REQUEST.

Expected results are ``backend.engine`` run directly on portfolio documents written out in the test.
"""

import copy
import json

import pytest
from byb_contracts import FAILURE_CODES, investigation_job_errors, validate_api_body

from backend import engine
from backend.engine.check import CUSTOMIZED_WEIGHT_ASSUMPTION
from service_fakes import NVDA_REQUEST, Service, create_body, engine_data, engine_direct, scenario
from test_service_custom_portfolio import CUSTOM_A, CUSTOM_B, check_body, expected_id, expected_portfolio, investigate, investigation_body, stored

UNIVERSE = "robert_synthetic_universe"
SCENARIO_ID = "pf-robert-fictional-1"
FREE_TEXT = {"instrument_id": None, "target_direct_weight": None, "funding": "CASH", "original_words": "Put more into technology."}
# Robert already holds NVDA at 30%: the scenario's demo request "NVDA to 25%" would be a sale on this portfolio.
CUSTOM_NVDA_30 = {"cash_weight": 0.2, "positions": [{"instrument_id": "XBB.TO", "weight": 0.5}, {"instrument_id": "NVDA", "weight": 0.3}]}


@pytest.fixture
def svc():
    service = Service(UNIVERSE)
    service.policy = service.confirm()
    return service


def engine_on(portfolio, policy, request, *, customized):
    data = engine_data(UNIVERSE)
    return engine.check_rules(portfolio, policy, request, data["instruments"], data["holdings"], data["market_data"], data["controversies"],
                              data_sources=data["data_sources"], portfolio_customized=customized)


def starting_weight_records(result):
    return [record for record in result["evidence"] if record["evidence_id"] == "ev-cash-start"
            or (record["evidence_id"].startswith("ev-w-") and record["evidence_id"].endswith("-start"))]


def noted(result):
    return sorted(record["evidence_id"] for record in result["evidence"] if CUSTOMIZED_WEIGHT_ASSUMPTION in record["assumptions"])


# --------------------------------------------------------------------------- F4


def test_cf01_a_customized_check_and_investigation_say_the_user_entered_the_starting_weights(svc):
    portfolio = expected_portfolio("robert", CUSTOM_A)
    status, check = svc.call("POST /check", check_body(svc.policy, CUSTOM_A))
    assert status == 200, check
    validate_api_body("check_result.schema.json", check)
    # The cash and the three held positions, and no other record.
    assert noted(check) == ["ev-cash-start", "ev-w-NVDA-start", "ev-w-SPY-start", "ev-w-XBB.TO-start"]
    assert noted(check) == sorted(record["evidence_id"] for record in starting_weight_records(check))
    assert check == engine_on(portfolio, svc.policy, NVDA_REQUEST, customized=True)
    # Without the note the document is the engine's plain answer for these weights: no figure or status changed.
    plain = copy.deepcopy(check)
    for record in plain["evidence"]:
        if CUSTOMIZED_WEIGHT_ASSUMPTION in record["assumptions"]:
            record["assumptions"].remove(CUSTOMIZED_WEIGHT_ASSUMPTION)
    assert plain == engine_on(portfolio, svc.policy, NVDA_REQUEST, customized=False)

    job = investigate(svc, svc.policy, CUSTOM_A, key="cf01-custom-investigation")
    assert job["status"] == "SUCCEEDED" and investigation_job_errors(job) == []
    assert job["result"] == check, "the investigation and the check agree, the note included"
    assert noted(job["result"]) == noted(check)

    # A preview of draft rules on the customized portfolio carries it too.
    drafts = [dict(rule, rule_id="robert-draft-" + str(index)) for index, rule in enumerate(scenario("robert")["scenario_rules"][:1])]
    status, preview = svc.call("POST /check", check_body(None, CUSTOM_A, drafts))
    assert status == 200 and preview["preview"] is True and noted(preview) == noted(check)


@pytest.mark.parametrize("custom", ["absent", None, "same-weights"])
def test_cf02_the_scenario_portfolio_carries_no_customization_note_on_either_route(svc, custom):
    if custom == "same-weights":  # rule 5 of api.md 2a: the scenario's own weights are the scenario portfolio
        base = scenario("robert")["portfolio"]
        custom = {"cash_weight": base["cash_weight"], "positions": list(reversed(base["positions"]))}
    expected = engine_direct(UNIVERSE, "robert", svc.policy, NVDA_REQUEST)  # the engine's default: not customized
    status, check = svc.call("POST /check", check_body(svc.policy, custom))
    assert status == 200 and check == expected and noted(check) == [] and check["portfolio_id"] == SCENARIO_ID
    job = investigate(svc, svc.policy, custom, key="cf02-default-investigation")
    assert job["status"] == "SUCCEEDED" and job["result"] == expected and noted(job["result"]) == []
    assert CUSTOMIZED_WEIGHT_ASSUMPTION not in json.dumps(job)


def test_cf03_a_legacy_job_and_a_job_storing_the_scenario_portfolio_carry_no_note(svc):
    status, accepted = svc.call("POST /investigations", investigation_body(svc.policy), key="cf03-legacy-job")
    assert status == 202
    key = f"jobs/{accepted['id']}.json"
    legacy = svc.s3.json(key)
    assert legacy["portfolio"]["portfolio_id"] == SCENARIO_ID
    del legacy["portfolio"]  # the stored shape of a job created before jobs carried their portfolio
    svc.s3.objects[key] = json.dumps(legacy).encode()
    svc.run_worker(accepted["id"])
    job = svc.get(accepted["id"])
    assert job["status"] == "SUCCEEDED" and job["result"] == engine_direct(UNIVERSE, "robert", svc.policy, NVDA_REQUEST)
    assert noted(job["result"]) == []


def test_cf04_a_change_rule_child_of_a_customized_job_keeps_the_note(svc):
    parent = investigate(svc, svc.policy, CUSTOM_A, key="cf04-parent")
    rule_id = svc.policy["rules"][0]["rule_id"]
    change = {"type": "CHANGE_RULE", "payload": {"rule_id": rule_id, "new_threshold": 0.3, "user_note": "Raise it."}}
    status, answer = svc.call("POST /investigations/{id}/challenge", change, path={"id": parent["id"]}, key="cf04-change-rule")
    assert status == 202, answer
    svc.run_worker(answer["investigation"]["id"])
    child = svc.get(answer["investigation"]["id"])
    assert child["status"] == "SUCCEEDED"
    assert child["result"] == engine_on(parent["portfolio"], answer["policy"], NVDA_REQUEST, customized=True)
    assert noted(child["result"]) == noted(parent["result"]) != []


# --------------------------------------------------------------------------- F5


def test_cf05_a_demo_request_the_customized_portfolio_would_refuse_is_not_offered_as_supported(svc):
    portfolio = expected_portfolio("robert", CUSTOM_NVDA_30)
    (demo,) = scenario("robert")["demo_requests"]
    assert demo["purchase_request"]["instrument_id"] == "NVDA" and demo["purchase_request"]["target_direct_weight"] == 0.25
    data = engine_data(UNIVERSE)
    refused = engine.simulate_change(portfolio, demo["purchase_request"], data["instruments"], svc.policy)["execution"]
    assert (refused["status"], refused["code"]) == ("INVALID_REQUEST", "TARGET_BELOW_CURRENT_WEIGHT")

    job = investigate(svc, svc.policy, CUSTOM_NVDA_30, key="cf05-free-text", request=FREE_TEXT)
    assert investigation_job_errors(job) == []
    assert job["status"] == "SUCCEEDED" and job["result"] is None and job["portfolio"] == portfolio
    options = {option["option_id"]: option for option in job["clarification"]["options"]}
    option = options[demo["request_id"]]
    # Shown disabled, with the engine's reason, and carrying nothing that could be submitted.
    assert option["supported"] is False and option["purchase_request"] is None and option["proposed_rule"] is None
    assert "TARGET_BELOW_CURRENT_WEIGHT" in option["description"] and refused["message"] in option["description"]
    assert option["label"] == demo["label"]
    assert options["enter-instrument-and-weight"]["supported"] is True and options["sell-or-rebalance"]["supported"] is False

    # Every option that is offered as supported with a request is accepted by POST /investigations for this portfolio.
    for index, offered in enumerate(o for o in job["clarification"]["options"] if o["supported"] and o["purchase_request"]):
        body = dict(investigation_body(svc.policy, CUSTOM_NVDA_30, offered["purchase_request"]), parent_investigation_id=job["id"])
        status, answer = svc.call("POST /investigations", body, key=f"cf05-option-{index}")
        assert status == 202, answer
    # The refused one really is refused there, which is why it must not be offered.
    body = dict(investigation_body(svc.policy, CUSTOM_NVDA_30, {**demo["purchase_request"], "original_words": FREE_TEXT["original_words"]}),
                parent_investigation_id=job["id"])
    status, answer = svc.call("POST /investigations", body, key="cf05-refused-option")
    assert status == 422 and answer["error"]["details"][0]["issue"].startswith("TARGET_BELOW_CURRENT_WEIGHT")


@pytest.mark.parametrize("custom", ["absent", CUSTOM_B], ids=["scenario", "custom-without-nvda"])
def test_cf06_a_demo_request_the_portfolio_accepts_is_offered_exactly_as_before(svc, custom):
    job = investigate(svc, svc.policy, custom, key="cf06-free-text", request=FREE_TEXT)
    assert investigation_job_errors(job) == [] and job["status"] == "SUCCEEDED"
    (demo,) = scenario("robert")["demo_requests"]
    assert job["clarification"]["options"] == [
        {"option_id": demo["request_id"], "label": demo["label"],
         "description": "A request from the fictional scenario: a final direct weight, funded from cash.",
         "supported": True, "proposed_rule": None, "purchase_request": {**demo["purchase_request"], "original_words": FREE_TEXT["original_words"]}},
        {"option_id": "enter-instrument-and-weight", "label": "Choose the instrument and enter the final direct weight yourself",
         "description": "Use the purchase form: pick an instrument and type the final weight as a share of the portfolio.",
         "supported": True, "proposed_rule": None, "purchase_request": None},
        {"option_id": "sell-or-rebalance", "label": "Sell or rebalance existing positions",
         "description": "Not supported: only purchases funded from existing cash are simulated.",
         "supported": False, "proposed_rule": None, "purchase_request": None},
    ]
    assert svc.bedrock.calls == []


# --------------------------------------------------------------------------- F6


def follow_up(svc, parent_id, custom="absent", *, key, policy=None, request=None):
    policy = policy or svc.policy
    body = dict(investigation_body(policy, custom, request), parent_investigation_id=parent_id)
    return svc.call("POST /investigations", body, key=key)


def assert_portfolio_mismatch(status, body, parent_portfolio_id, request_portfolio_id):
    assert status == 400 and body["error"]["code"] == "VALIDATION_ERROR", body
    validate_api_body("api.schema.json#/$defs/error_response", body)
    first = body["error"]["details"][0]
    assert first["path"] == "custom_portfolio"
    assert "must carry the portfolio of the investigation it follows" in first["issue"]
    assert parent_portfolio_id in first["issue"] and request_portfolio_id in first["issue"] and parent_portfolio_id != request_portfolio_id


def test_cf07_a_follow_up_on_the_same_portfolio_as_its_parent_is_accepted(svc):
    # scenario / scenario: absent, null and the scenario's own weights all resolve to the scenario portfolio
    parent = investigate(svc, svc.policy, key="cf07-scenario-parent")
    base = scenario("robert")["portfolio"]
    same = {"cash_weight": base["cash_weight"], "positions": base["positions"]}
    for index, custom in enumerate(["absent", None, same]):
        status, accepted = follow_up(svc, parent["id"], custom, key=f"cf07-scenario-child-{index}")
        assert status == 202, accepted
        svc.run_worker(accepted["id"])
        child = svc.get(accepted["id"])
        assert child["status"] == "SUCCEEDED" and child["parent_investigation_id"] == parent["id"]
        assert child["portfolio"] == parent["portfolio"] == base and child["result"] == parent["result"]

    # custom / custom: the same weights, whatever their order
    parent = investigate(svc, svc.policy, CUSTOM_A, key="cf07-custom-parent")
    reordered = {"cash_weight": CUSTOM_A["cash_weight"], "positions": list(reversed(CUSTOM_A["positions"]))}
    for index, custom in enumerate([CUSTOM_A, reordered]):
        status, accepted = follow_up(svc, parent["id"], custom, key=f"cf07-custom-child-{index}")
        assert status == 202, accepted
        svc.run_worker(accepted["id"])
        child = svc.get(accepted["id"])
        assert child["status"] == "SUCCEEDED" and child["parent_investigation_id"] == parent["id"]
        assert child["portfolio"]["portfolio_id"] == parent["portfolio"]["portfolio_id"] == expected_id("robert", CUSTOM_A)
        assert child["result"]["feasibility"] == parent["result"]["feasibility"] and child["result"]["rule_results"] == parent["result"]["rule_results"]


def test_cf08_a_follow_up_on_another_portfolio_than_its_parent_is_400_and_nothing_is_stored(svc, monkeypatch):
    custom_parent = investigate(svc, svc.policy, CUSTOM_A, key="cf08-custom-parent")
    scenario_parent = investigate(svc, svc.policy, key="cf08-scenario-parent")
    before, invocations = stored(svc), len(svc.lambda_client.invocations)
    calls = []
    monkeypatch.setattr(engine, "check_rules", lambda *a, **k: calls.append("check_rules"))
    monkeypatch.setattr(engine, "simulate_change", lambda *a, **k: calls.append("simulate_change"))
    custom_a, custom_b = expected_id("robert", CUSTOM_A), expected_id("robert", CUSTOM_B)
    # custom parent, scenario request (absent and null); scenario parent, custom request; custom parent, another custom
    assert_portfolio_mismatch(*follow_up(svc, custom_parent["id"], "absent", key="cf08-mismatch-1"), custom_a, SCENARIO_ID)
    assert_portfolio_mismatch(*follow_up(svc, custom_parent["id"], None, key="cf08-mismatch-2"), custom_a, SCENARIO_ID)
    assert_portfolio_mismatch(*follow_up(svc, scenario_parent["id"], CUSTOM_A, key="cf08-mismatch-3"), SCENARIO_ID, custom_a)
    assert_portfolio_mismatch(*follow_up(svc, custom_parent["id"], CUSTOM_B, key="cf08-mismatch-4"), custom_a, custom_b)
    assert calls == [] and stored(svc) == before and len(svc.lambda_client.invocations) == invocations


def test_cf09_a_legacy_parent_counts_as_the_scenario_portfolio(svc):
    parent = investigate(svc, svc.policy, key="cf09-legacy-parent")
    key = f"jobs/{parent['id']}.json"
    legacy = svc.s3.json(key)
    del legacy["portfolio"]  # stored before jobs carried their portfolio: it was checked against the scenario's
    svc.s3.objects[key] = json.dumps(legacy).encode()
    assert "portfolio" not in svc.get(parent["id"])
    assert_portfolio_mismatch(*follow_up(svc, parent["id"], CUSTOM_A, key="cf09-custom-child"), SCENARIO_ID, expected_id("robert", CUSTOM_A))
    status, accepted = follow_up(svc, parent["id"], key="cf09-scenario-child")
    assert status == 202, accepted
    assert svc.s3.json(f"jobs/{accepted['id']}.json")["portfolio"] == scenario("robert")["portfolio"]


def test_cf10_a_parent_of_another_persona_is_not_found(svc):
    mateo = Service("mateo_synthetic_universe")
    mateo_policy = mateo.confirm("mateo")
    request = scenario("mateo")["demo_requests"][0]["purchase_request"]
    status, accepted = mateo.call("POST /investigations", create_body("mateo", mateo_policy["policy_id"], mateo_policy["version"], request),
                                  key="cf10-mateo-parent")
    assert status == 202, accepted
    # The same job object in Robert's store: a real job, of another persona.
    svc.s3.objects[f"jobs/{accepted['id']}.json"] = mateo.s3.objects[f"jobs/{accepted['id']}.json"]
    assert svc.s3.json(f"jobs/{accepted['id']}.json")["persona_id"] == "mateo"
    before = stored(svc)
    unknown = follow_up(svc, "inv-" + "0" * 32, key="cf10-unknown-parent")
    other = follow_up(svc, accepted["id"], key="cf10-other-persona")
    for status, body in (unknown, other):
        assert status == 404 and body["error"]["code"] == "NOT_FOUND" and body["error"]["details"][0]["path"] == "parent_investigation_id", body
    assert other[1]["error"]["message"] == unknown[1]["error"]["message"] and other[1]["error"]["details"] == unknown[1]["error"]["details"]
    assert stored(svc) == before


# --------------------------------------------------------------------------- F9


def queue_then_break(svc, damage, key):
    """Store a valid job, then change what the worker will read so the engine refuses the stored request."""
    status, accepted = svc.call("POST /investigations", investigation_body(svc.policy, CUSTOM_A), key=key)
    assert status == 202, accepted
    job_key = f"jobs/{accepted['id']}.json"
    job = svc.s3.json(job_key)
    damage(job)
    svc.s3.objects[job_key] = json.dumps(job).encode()
    return accepted["id"], job


def test_cf11_a_stored_request_the_engine_refuses_at_run_time_fails_the_job_with_no_result(svc):
    # The stored portfolio (still a valid contract document) now holds NVDA at 30%: the stored target of 25% is below it.
    job_id, job = queue_then_break(svc, lambda job: job["portfolio"].update(
        cash_weight=0.1, positions=[{"instrument_id": "XBB.TO", "weight": 0.3}, {"instrument_id": "SPY", "weight": 0.3},
                                    {"instrument_id": "NVDA", "weight": 0.3}]), "cf11-below-current")
    refused = engine_on(job["portfolio"], svc.policy, NVDA_REQUEST, customized=True)
    assert (refused["execution"]["status"], refused["execution"]["code"]) == ("INVALID_REQUEST", "TARGET_BELOW_CURRENT_WEIGHT")
    assert refused["summary"]["headline"] == "INVALID_REQUEST"

    outcome = svc.run_worker(job_id)
    assert outcome["outcome"] == "completed" and outcome["status"] == "FAILED", outcome
    view = svc.get(job_id)
    assert investigation_job_errors(view) == []
    assert view["status"] == "FAILED" and view["result"] is None and view["clarification"] is None and view["explanation"] == []
    assert view["failure"]["code"] in FAILURE_CODES and view["failure"]["code"] == outcome["failure_code"] == "DATA_UNAVAILABLE"
    assert view["failure"]["retryable"] is False
    assert "TARGET_BELOW_CURRENT_WEIGHT" in view["failure"]["message"] and "no result" in view["failure"]["message"].lower()
    assert svc.s3.keys("results/") == [] and svc.bedrock.calls == []  # no result object, and the model was never asked


def test_cf12_an_instrument_missing_from_the_workers_registry_fails_the_job_with_no_result(svc):
    """The request names an instrument the data the worker reads no longer has (a later snapshot dropped it)."""
    status, accepted = svc.call("POST /investigations", investigation_body(svc.policy), key="cf12-dropped-instrument")
    assert status == 202, accepted
    snapshot = svc.worker._snapshots.load()
    registry = snapshot.instruments
    entries = registry["instruments"] if isinstance(registry, dict) and "instruments" in registry else registry
    if isinstance(entries, dict):
        entries.pop("NVDA")
    else:
        entries[:] = [entry for entry in entries if entry["instrument_id"] != "NVDA"]
    data = engine_data(UNIVERSE)
    assert engine.simulate_change(scenario("robert")["portfolio"], NVDA_REQUEST, snapshot.instruments, svc.policy)["execution"]["code"] == "UNSUPPORTED_INSTRUMENT"
    assert engine.simulate_change(scenario("robert")["portfolio"], NVDA_REQUEST, data["instruments"], svc.policy)["execution"]["status"] == "OK"

    outcome = svc.run_worker(accepted["id"])
    assert outcome == {"outcome": "completed", "status": "FAILED", "failure_code": "DATA_UNAVAILABLE"}, outcome
    view = svc.get(accepted["id"])
    assert investigation_job_errors(view) == []
    assert view["status"] == "FAILED" and view["result"] is None and view["explanation"] == []
    assert "UNSUPPORTED_INSTRUMENT" in view["failure"]["message"]
    assert svc.s3.keys("results/") == [] and svc.bedrock.calls == []
