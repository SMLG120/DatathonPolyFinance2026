"""Customized fictional portfolio (contracts/api.md, section 2a) through the two Lambda handlers.

``custom_portfolio`` replaces the persona's scenario portfolio for ``POST /check`` and
``POST /investigations``. The job stores the full portfolio it was created with; the worker, every
tool and a ``CHANGE_RULE`` child read that stored portfolio.

Every expected result is ``backend.engine.check_rules`` run directly on a portfolio document that
is written out here by hand (never produced by the code under test), on the same data.
"""

import copy
import hashlib
import json

import pytest
from byb_contracts import ContractError, investigation_job_errors, validate_api_body, validate_portfolio

from backend import engine
from backend.agents.tools import build_investigation_registry
from backend.common.portfolios import InvalidCustomPortfolio, custom_portfolio_id, resolve_portfolio
from service_fakes import (
    NVDA_REQUEST,
    REAL_DATA_PRESENT,
    REAL_DATA_REASON,
    Service,
    api_fixture,
    client_error,
    confirm_body,
    create_body,
    engine_data,
    engine_direct,
    final_response,
    highlights,
    scenario,
    snapshot_contents,
    tool_use_response,
)

UNIVERSE = "robert_synthetic_universe"
needs_real_data = pytest.mark.skipif(not REAL_DATA_PRESENT, reason=REAL_DATA_REASON)
REAL = pytest.param(None, id="real-data", marks=needs_real_data)
ROBERT_UNIVERSES = [pytest.param(UNIVERSE, id="synthetic"), REAL]
CHANGE_RULE = api_fixture("challenge_change_rule")["request_body"]
ISSUER_CAP_DRAFT = api_fixture("check_mateo_preview_unknown")["request_body"]["draft_rules"]  # no single company above 20%

# Purchasable in the synthetic Robert universe: JNJ, NVDA, RY.TO, SPY, XBB.TO, XIU.TO.
CUSTOM_A = {"cash_weight": 0.2, "positions": [{"instrument_id": "XBB.TO", "weight": 0.3}, {"instrument_id": "SPY", "weight": 0.3},
                                             {"instrument_id": "NVDA", "weight": 0.2}]}
CUSTOM_B = {"cash_weight": 0.5, "positions": [{"instrument_id": "XBB.TO", "weight": 0.5}]}


def expected_id(persona_id, custom):
    """The id rule of api.md 2a, written out independently of the service."""
    content = {"cash_weight": float(custom["cash_weight"]),
               "positions": sorted(({"instrument_id": p["instrument_id"], "weight": float(p["weight"])} for p in custom["positions"]),
                                   key=lambda p: p["instrument_id"])}
    digest = hashlib.sha256(json.dumps(content, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return f"pf-{persona_id}-custom-{digest[:12]}"


def expected_portfolio(persona_id, custom):
    """The document the server must build: the scenario's identity fields, the submitted weights in the submitted order."""
    base = scenario(persona_id)["portfolio"]
    return {"schema_version": base["schema_version"], "portfolio_id": expected_id(persona_id, custom), "persona_id": persona_id, "fictional": True,
            "valuation_date": base["valuation_date"], "base_currency": "CAD", "cash_weight": custom["cash_weight"],
            "positions": copy.deepcopy(custom["positions"])}


def engine_on(universe, portfolio, policy, request, draft_rules=None):
    """The engine run directly on a customized portfolio written out in the test.

    ``portfolio_customized=True``: every portfolio passed here is one the user edited, and the service tells the
    engine so (code review F4), which puts the "entered by the user" note on the starting-weight evidence records.
    """
    data = engine_data(universe)
    return engine.check_rules(portfolio, policy, request, data["instruments"], data["holdings"], data["market_data"], data["controversies"],
                              draft_rules=draft_rules, data_sources=data["data_sources"], portfolio_customized=True)


def check_body(policy=None, custom="absent", drafts=None, persona_id="robert", request=None):
    body = {"persona_id": persona_id, "policy_id": policy["policy_id"] if policy else None, "policy_version": policy["version"] if policy else None,
            "purchase_request": dict(request or NVDA_REQUEST), "draft_rules": drafts}
    if custom != "absent":
        body["custom_portfolio"] = custom
    return body


def investigation_body(policy, custom="absent", request=None):
    body = create_body(policy["persona_id"], policy["policy_id"], policy["version"], request)
    if custom != "absent":
        body["custom_portfolio"] = custom
    return body


def investigate(svc, policy, custom="absent", *, key, request=None, run=True):
    status, accepted = svc.call("POST /investigations", investigation_body(policy, custom, request), key=key)
    assert status == 202, accepted
    if run:
        svc.run_worker(accepted["id"])
    return svc.get(accepted["id"])


def stored(svc, prefixes=("policies/", "jobs/", "results/", "traces/", "corrections/")):
    return {key: value for key, value in svc.s3.objects.items() if key.startswith(prefixes)}


def log_lines(stream, event):
    return [line for line in (json.loads(text) for text in stream.getvalue().splitlines() if text.strip()) if line.get("event") == event]


@pytest.fixture
def svc():
    service = Service(UNIVERSE)
    service.policy = service.confirm()
    return service


# --------------------------------------------------------------------------- the pure resolver


def test_cp01_resolver_builds_the_document_and_a_content_derived_id():
    base = scenario("robert")["portfolio"]
    before = copy.deepcopy(base)
    purchasable = ["JNJ", "NVDA", "RY.TO", "SPY", "XBB.TO", "XIU.TO"]
    assert resolve_portfolio(base, None, purchasable) is base  # absent / null: the scenario portfolio itself
    built = resolve_portfolio(base, CUSTOM_A, purchasable)
    assert built == expected_portfolio("robert", CUSTOM_A) and built["portfolio_id"].startswith("pf-robert-custom-")
    validate_portfolio(built)
    assert [p["instrument_id"] for p in built["positions"]] == ["XBB.TO", "SPY", "NVDA"]  # the submitted order
    # Equal weights give the same id whatever the order and whether a number arrives as 0 or 0.0.
    reordered = {"cash_weight": 0.2, "positions": list(reversed(CUSTOM_A["positions"]))}
    assert resolve_portfolio(base, reordered, purchasable)["portfolio_id"] == built["portfolio_id"]
    all_in = lambda cash, weight: {"cash_weight": cash, "positions": [{"instrument_id": "SPY", "weight": weight}]}  # noqa: E731
    assert resolve_portfolio(base, all_in(0, 1), purchasable)["portfolio_id"] == resolve_portfolio(base, all_in(0.0, 1.0), purchasable)["portfolio_id"]
    assert resolve_portfolio(base, CUSTOM_B, purchasable)["portfolio_id"] != built["portfolio_id"]
    assert base == before  # the scenario portfolio is never modified
    # A persona id may contain "_", which the contract id pattern does not allow.
    assert custom_portfolio_id("some_persona", 0.5, CUSTOM_B["positions"]).startswith("pf-some-persona-custom-")


def test_cp02_resolver_treats_the_scenarios_own_weights_as_the_scenario_portfolio():
    base = scenario("robert")["portfolio"]
    purchasable = [p["instrument_id"] for p in base["positions"]]
    same = {"cash_weight": base["cash_weight"] + 4e-10, "positions": [dict(p, weight=p["weight"] - 1e-10) for p in reversed(base["positions"])]}
    assert resolve_portfolio(base, same, purchasable) is base
    moved = copy.deepcopy(same)
    moved["cash_weight"], moved["positions"][0]["weight"] = base["cash_weight"] - 0.01, moved["positions"][0]["weight"] + 0.01
    assert resolve_portfolio(base, moved, purchasable)["portfolio_id"].startswith("pf-robert-custom-")


@pytest.mark.parametrize("custom, path, words", [
    ({"cash_weight": 0.2, "positions": [{"instrument_id": "SPY", "weight": 0.7}]}, "custom_portfolio", "never rescaled"),
    ({"cash_weight": 0.5, "positions": [{"instrument_id": "SPY", "weight": 0.7}]}, "custom_portfolio", "leverage"),
    ({"cash_weight": 0.2 + 1e-8, "positions": [{"instrument_id": "SPY", "weight": 0.8}]}, "custom_portfolio", "never rescaled"),
    ({"cash_weight": 1.2, "positions": [{"instrument_id": "SPY", "weight": -0.2}]}, "custom_portfolio.cash_weight", "leverage"),
    ({"cash_weight": 0.9, "positions": [{"instrument_id": "SPY", "weight": 0.3}, {"instrument_id": "XBB.TO", "weight": -0.2}]},
     "custom_portfolio.positions[1].weight", "shorting"),
    ({"cash_weight": 1.0, "positions": [{"instrument_id": "SPY", "weight": 0}]}, "custom_portfolio.positions[0].weight", "zero"),
    ({"cash_weight": 0.2, "positions": [{"instrument_id": "SPY", "weight": 0.4}, {"instrument_id": "XBB.TO", "weight": 0.2},
                                        {"instrument_id": "SPY", "weight": 0.2}]}, "custom_portfolio.positions[2].instrument_id", "more than once"),
    ({"cash_weight": 0.2, "positions": [{"instrument_id": "AAPL", "weight": 0.8}]}, "custom_portfolio.positions[0].instrument_id", "purchasable"),
    ({"cash_weight": float("nan"), "positions": []}, "custom_portfolio.cash_weight", "finite"),
    ({"cash_weight": 0.5, "positions": [{"instrument_id": "SPY", "weight": float("inf")}]}, "custom_portfolio.positions[0].weight", "finite"),
    ({"cash_weight": True, "positions": []}, "custom_portfolio.cash_weight", "finite"),
    ({"cash_weight": 1.0, "positions": [], "portfolio_id": "pf-mine"}, "custom_portfolio.portfolio_id", "not a member"),
    ("everything in NVDA", "custom_portfolio", "object"),
])
def test_cp03_resolver_refuses_what_it_cannot_use_and_never_rescales(custom, path, words):
    base = scenario("robert")["portfolio"]
    with pytest.raises(InvalidCustomPortfolio) as caught:
        resolve_portfolio(base, custom, ["JNJ", "NVDA", "RY.TO", "SPY", "XBB.TO", "XIU.TO"])  # AAPL is in the registry but has no price series
    assert (path, True) in [(problem_path, words in issue) for problem_path, issue in caught.value.problems], caught.value.problems


# --------------------------------------------------------------------------- POST /check


def test_cp04_check_evaluates_the_stored_policy_on_the_customized_portfolio(svc, captured_log):
    status, body = svc.call("POST /check", check_body(svc.policy, CUSTOM_A))
    assert status == 200, body
    validate_api_body("check_result.schema.json", body)
    portfolio = expected_portfolio("robert", CUSTOM_A)
    assert body == engine_on(UNIVERSE, portfolio, svc.policy, NVDA_REQUEST)
    assert body["portfolio_id"] == portfolio["portfolio_id"] != "pf-robert-fictional-1" and body["preview"] is False
    # NVDA is already 20% of the customized portfolio and cash is 20%, where the scenario has no NVDA and 30% cash.
    feasibility = body["feasibility"]
    assert feasibility["cash_before"] == 0.2 and feasibility["starting_direct_weight"] == 0.2
    assert feasibility["additional_purchase"] == pytest.approx(0.05) and feasibility["cash_after"] == pytest.approx(0.15)
    default = engine_direct(UNIVERSE, "robert", svc.policy, NVDA_REQUEST)
    assert default["feasibility"]["cash_before"] == 0.3 and body != default
    (line,) = log_lines(captured_log, "check_completed")
    assert line["portfolio_id"] == portfolio["portfolio_id"] and line["custom_portfolio"] is True
    assert svc.s3.keys("jobs/") == [] and svc.lambda_client.invocations == []  # a check stores nothing


def test_cp05_check_previews_draft_rules_on_the_customized_portfolio(svc):
    before = stored(svc)
    drafts = [dict(rule, rule_id="robert-issuer-cap-draft") for rule in ISSUER_CAP_DRAFT]
    for policy in (None, svc.policy):  # without a stored policy, and with one that only supplies the objectives
        status, body = svc.call("POST /check", check_body(policy, CUSTOM_A, drafts))
        assert status == 200, body
        validate_api_body("check_result.schema.json", body)
        assert body == engine_on(UNIVERSE, expected_portfolio("robert", CUSTOM_A), policy, NVDA_REQUEST, draft_rules=drafts)
        assert body["preview"] is True and body["portfolio_id"] == expected_id("robert", CUSTOM_A) and body["feasibility"]["cash_before"] == 0.2
        assert [entry["rule_id"] for entry in body["rule_results"]] == ["robert-issuer-cap-draft"]
    assert stored(svc) == before


def test_cp06_check_with_the_scenarios_own_weights_reports_the_scenario_portfolio(svc, captured_log):
    base = scenario("robert")["portfolio"]
    same = {"cash_weight": base["cash_weight"], "positions": list(reversed(base["positions"]))}
    status, body = svc.call("POST /check", check_body(svc.policy, same))
    assert status == 200 and body["portfolio_id"] == "pf-robert-fictional-1"
    assert body == engine_direct(UNIVERSE, "robert", svc.policy, NVDA_REQUEST)
    assert log_lines(captured_log, "check_completed")[-1]["custom_portfolio"] is False


INVALID = [
    pytest.param({"cash_weight": 0.2, "positions": [{"instrument_id": "SPY", "weight": 0.7}]}, "custom_portfolio", id="total-below-1"),
    pytest.param({"cash_weight": 0.5, "positions": [{"instrument_id": "SPY", "weight": 0.7}]}, "custom_portfolio", id="total-above-1-leverage"),
    pytest.param({"cash_weight": 0.9, "positions": [{"instrument_id": "SPY", "weight": 0.3}, {"instrument_id": "XBB.TO", "weight": -0.2}]},
                 "custom_portfolio.positions[1].weight", id="negative-weight-shorting"),
    pytest.param({"cash_weight": -0.2, "positions": [{"instrument_id": "SPY", "weight": 0.6}, {"instrument_id": "XBB.TO", "weight": 0.6}]},
                 "custom_portfolio.cash_weight", id="negative-cash-leverage"),
    pytest.param({"cash_weight": 1.0, "positions": [{"instrument_id": "SPY", "weight": 0}]}, "custom_portfolio.positions[0].weight", id="zero-weight"),
    pytest.param({"cash_weight": 0.2, "positions": [{"instrument_id": "SPY", "weight": 0.4}, {"instrument_id": "XBB.TO", "weight": 0.2},
                                                    {"instrument_id": "SPY", "weight": 0.2}]},
                 "custom_portfolio.positions[2].instrument_id", id="duplicate-instrument"),
    pytest.param({"cash_weight": 0.2, "positions": [{"instrument_id": "AAPL", "weight": 0.8}]},
                 "custom_portfolio.positions[0].instrument_id", id="in-registry-but-not-purchasable"),
    pytest.param({"cash_weight": 0.2, "positions": [{"instrument_id": "ZZZZ", "weight": 0.8}]},
                 "custom_portfolio.positions[0].instrument_id", id="unknown-instrument"),
    pytest.param({"cash_weight": 0.2, "positions": [{"instrument_id": "SPY", "weight": 0.8}], "portfolio_id": "pf-robert-fictional-1"},
                 "custom_portfolio", id="unknown-property"),
    pytest.param({"cash_weight": 0.2, "positions": [{"instrument_id": "SPY", "weight": 0.8, "shares": 10}]},
                 "custom_portfolio.positions[0]", id="unknown-position-property"),
    pytest.param({"cash_weight": 0.18, "positions": [{"instrument_id": "SPY", "weight": 0.02}] * 41}, "custom_portfolio.positions", id="41-positions"),
    pytest.param({"cash_weight": "20%", "positions": [{"instrument_id": "SPY", "weight": 0.8}]}, "custom_portfolio.cash_weight", id="weight-as-text"),
    pytest.param({"positions": [{"instrument_id": "SPY", "weight": 1.0}]}, "custom_portfolio", id="cash-missing"),
    pytest.param([], "custom_portfolio", id="not-an-object"),
]


def assert_refused(status, body, path_prefix):
    assert status == 400 and body["error"]["code"] == "VALIDATION_ERROR", body
    validate_api_body("api.schema.json#/$defs/error_response", body)
    paths = [entry["path"] for entry in body["error"]["details"]]
    assert paths and all(path.startswith("custom_portfolio") for path in paths), paths
    assert any(path.startswith(path_prefix) for path in paths), paths


@pytest.mark.parametrize("custom, path", INVALID)
def test_cp07_an_invalid_custom_portfolio_is_400_on_both_routes_and_nothing_is_calculated_or_stored(svc, custom, path, monkeypatch):
    before = stored(svc)
    calls = []
    monkeypatch.setattr(engine, "check_rules", lambda *a, **k: calls.append("check_rules"))
    monkeypatch.setattr(engine, "simulate_change", lambda *a, **k: calls.append("simulate_change"))
    assert_refused(*svc.call("POST /check", check_body(svc.policy, custom)), path)
    assert_refused(*svc.call("POST /check", check_body(None, custom, ISSUER_CAP_DRAFT)), path)
    assert_refused(*svc.call("POST /investigations", investigation_body(svc.policy, custom), key="cp07-invalid-portfolio"), path)
    assert calls == [] and stored(svc) == before and svc.lambda_client.invocations == []


@pytest.mark.parametrize("literal", ["NaN", "Infinity", "-Infinity", "1e999"])
def test_cp08_a_non_finite_weight_is_refused_before_anything_runs(svc, literal):
    before = stored(svc)
    for route, body, key in [("POST /check", check_body(svc.policy, CUSTOM_A), None),
                             ("POST /investigations", investigation_body(svc.policy, CUSTOM_A), "cp08-non-finite-weight")]:
        raw = json.dumps(body).replace('"cash_weight": 0.2', f'"cash_weight": {literal}')
        assert literal in raw
        status, answer = svc.call(route, raw=raw, key=key)
        assert status == 400 and answer["error"]["code"] == "VALIDATION_ERROR"
    assert stored(svc) == before and svc.lambda_client.invocations == []


def test_cp09_the_refusal_says_that_weights_are_not_rescaled_and_names_shorting_and_leverage(svc):
    _, body = svc.call("POST /check", check_body(svc.policy, {"cash_weight": 0.5, "positions": [{"instrument_id": "SPY", "weight": 0.7}]}))
    (entry,) = body["error"]["details"]
    assert entry["path"] == "custom_portfolio" and "never rescaled" in entry["issue"] and "leverage" in entry["issue"] and "1.2" in entry["issue"]
    assert "never rescaled" in body["error"]["message"] and "shorting" in body["error"]["message"] and "leverage" in body["error"]["message"]
    _, body = svc.call("POST /check", check_body(svc.policy, {"cash_weight": 0.2, "positions": [{"instrument_id": "AAPL", "weight": 0.8}]}))
    assert body["error"]["details"] == [{"path": "custom_portfolio.positions[0].instrument_id",
                                         "issue": "AAPL is not one of purchasable_instrument_ids; no other asset can be held"}]


# --------------------------------------------------------------------------- default behaviour is unchanged


@pytest.mark.parametrize("universe", ROBERT_UNIVERSES)
@pytest.mark.parametrize("custom", ["absent", None], ids=["absent", "null"])
def test_cp10_robert_without_a_custom_portfolio_is_checked_exactly_as_before(universe, custom):
    svc = Service(universe)
    policy = svc.confirm()
    expected = engine_direct(universe, "robert", policy, NVDA_REQUEST)
    status, body = svc.call("POST /check", check_body(policy, custom))
    assert status == 200 and body == expected and body["portfolio_id"] == "pf-robert-fictional-1"
    job = investigate(svc, policy, custom, key="cp10-robert-default")
    assert investigation_job_errors(job) == []
    assert job["status"] == "SUCCEEDED" and job["result"] == expected and job["portfolio"] == scenario("robert")["portfolio"]


@pytest.mark.parametrize("universe", [pytest.param("mateo_synthetic_universe", id="synthetic"), REAL])
@pytest.mark.parametrize("custom", ["absent", None], ids=["absent", "null"])
def test_cp11_mateo_without_a_custom_portfolio_is_checked_exactly_as_before(universe, custom):
    svc = Service(universe)
    policy = svc.confirm("mateo")
    request = scenario("mateo")["demo_requests"][0]["purchase_request"]
    expected = engine_direct(universe, "mateo", policy, request)
    status, body = svc.call("POST /check", check_body(policy, custom, persona_id="mateo", request=request))
    assert status == 200 and body == expected and body["portfolio_id"] == "pf-mateo-fictional-1"
    fixture = api_fixture("check_mateo_preview_unknown")["request_body"]
    if custom != "absent":
        fixture = dict(fixture, custom_portfolio=custom)
    status, preview = svc.call("POST /check", fixture)
    assert status == 200 and preview == engine_direct(universe, "mateo", None, fixture["purchase_request"], draft_rules=fixture["draft_rules"])
    assert preview["rule_results"][0]["status"] == "UNKNOWN"
    job = investigate(svc, policy, custom, key="cp11-mateo-default", request=request)
    assert job["status"] == "SUCCEEDED" and job["result"] == expected and job["portfolio"] == scenario("mateo")["portfolio"]


def test_cp12_a_job_stored_before_jobs_carried_a_portfolio_still_runs_and_is_served(svc):
    status, accepted = svc.call("POST /investigations", investigation_body(svc.policy), key="cp12-legacy-job")
    assert status == 202
    key = f"jobs/{accepted['id']}.json"
    legacy = svc.s3.json(key)
    del legacy["portfolio"]  # the stored shape of a job created by the previous build
    svc.s3.objects[key] = json.dumps(legacy).encode()
    queued = svc.get(accepted["id"])
    assert "portfolio" not in queued and investigation_job_errors(queued) == []
    svc.run_worker(accepted["id"])
    job = svc.get(accepted["id"])
    assert "portfolio" not in job and investigation_job_errors(job) == []
    assert job["status"] == "SUCCEEDED" and job["result"] == engine_direct(UNIVERSE, "robert", svc.policy, NVDA_REQUEST)
    assert svc.s3.json(f"results/{accepted['id']}.json")["inputs"]["portfolio_id"] == "pf-robert-fictional-1"
    # Its CHANGE_RULE child is checked against the scenario portfolio too, and from now on carries it.
    status, answer = svc.call("POST /investigations/{id}/challenge", CHANGE_RULE, path={"id": job["id"]}, key="cp12-legacy-challenge")
    assert status == 202, answer
    svc.run_worker(answer["investigation"]["id"])
    child = svc.get(answer["investigation"]["id"])
    assert child["portfolio"] == scenario("robert")["portfolio"]
    assert child["result"] == engine_direct(UNIVERSE, "robert", answer["policy"], NVDA_REQUEST)


# --------------------------------------------------------------------------- POST /investigations and the worker


def model_script():
    calls = [tool_use_response(name, {}, tool_use_id=f"tool-{i}") for i, name in enumerate(["get_portfolio", "simulate_change", "compute_exposure"])]
    return calls + [final_response(highlights("ev-cash-after"))]


def recording_factory(seen):
    def factory(context):
        seen.append(context)
        return build_investigation_registry(context)
    return factory


def tool_results(bedrock, name):
    """What the model was sent back for its calls of ``name`` (the JSON text of each toolResult)."""
    wanted, found = set(), []
    for call in bedrock.calls[-1:]:  # the last call carries the whole conversation
        for message in call["messages"]:
            for block in message["content"]:
                if "toolUse" in block and block["toolUse"]["name"] == name:
                    wanted.add(block["toolUse"]["toolUseId"])
                if "toolResult" in block and block["toolResult"]["toolUseId"] in wanted:
                    found.append(json.dumps(block["toolResult"]["content"]))
    return found


FALLBACK = [client_error("ValidationException", "Converse")]


@pytest.mark.parametrize("script, mode", [(model_script, "MODEL"), (lambda: list(FALLBACK), "DETERMINISTIC_FALLBACK")], ids=["model", "fallback"])
def test_cp13_the_job_stores_the_customized_portfolio_and_engine_tools_and_public_job_all_show_it(script, mode):
    seen = []
    svc = Service(UNIVERSE, bedrock_script=script(), registry_factory=recording_factory(seen))
    policy = svc.confirm()
    portfolio = expected_portfolio("robert", CUSTOM_A)
    status, accepted = svc.call("POST /investigations", investigation_body(policy, CUSTOM_A), key="cp13-custom-investigation")
    assert status == 202, accepted
    job_id = accepted["id"]
    assert svc.s3.json(f"jobs/{job_id}.json")["portfolio"] == portfolio  # stored at creation, before any worker ran
    queued = svc.get(job_id)
    assert queued["status"] == "QUEUED" and queued["portfolio"] == portfolio and investigation_job_errors(queued) == []

    assert svc.run_worker(job_id) == {"outcome": "completed", "status": "SUCCEEDED"}
    job = svc.get(job_id)
    assert investigation_job_errors(job) == []
    expected = engine_on(UNIVERSE, portfolio, policy, NVDA_REQUEST)
    assert job["agent"]["mode"] == mode and job["portfolio"] == portfolio
    assert job["result"] == expected and job["result"]["portfolio_id"] == portfolio["portfolio_id"]
    assert job["result"]["feasibility"]["cash_before"] == 0.2 and job["result"] != engine_direct(UNIVERSE, "robert", policy, NVDA_REQUEST)

    # The tools: one context, holding the stored portfolio and the engine result computed on it.
    (context,) = seen
    assert context.portfolio == portfolio and context.result == expected
    output = build_investigation_registry(context).execute("get_portfolio", {}, origin="server", clock=svc.clock)
    step = next(s for s in job["steps"] if s["tool"] == "get_portfolio")
    assert step["initiated_by"] == ("MODEL" if mode == "MODEL" else "SERVER") and step["result_summary"] == output.result_summary
    assert "3 positions" in step["result_summary"] and "20" in step["result_summary"]
    if mode == "MODEL":
        (shown,) = tool_results(svc.bedrock, "get_portfolio")
        assert portfolio["portfolio_id"] in shown and "pf-robert-fictional-1" not in shown
        assert "NVDA" in shown and "XIU.TO" not in shown and "RY.TO" not in shown  # the customized positions, not the scenario's
        request_block = svc.bedrock.calls[0]["messages"][0]["content"][0]["text"]
        assert f'"portfolio_id":"{portfolio["portfolio_id"]}"' in request_block and '"portfolio_customized":true' in request_block
    else:
        assert all(s["initiated_by"] == "SERVER" for s in job["steps"])
        assert all(statement["rendered_by"] == "TEMPLATE" for statement in job["explanation"])

    outcome, trace = svc.s3.json(f"results/{job_id}.json"), svc.s3.json(f"traces/{job_id}.json")
    assert outcome["inputs"]["portfolio_id"] == trace["portfolio_id"] == portfolio["portfolio_id"]
    assert outcome["inputs"]["portfolio_content_sha256"] == hashlib.sha256(
        json.dumps(portfolio, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


def test_cp14_the_model_is_told_when_the_portfolio_is_the_scenarios_own():
    svc = Service(UNIVERSE, bedrock_script=model_script())
    job = investigate(svc, svc.confirm(), key="cp14-default-portfolio")
    assert job["agent"]["mode"] == "MODEL"
    request_block = svc.bedrock.calls[0]["messages"][0]["content"][0]["text"]
    assert '"portfolio_id":"pf-robert-fictional-1"' in request_block and '"portfolio_customized":false' in request_block
    (shown,) = tool_results(svc.bedrock, "get_portfolio")
    assert "pf-robert-fictional-1" in shown


def test_cp15_the_request_is_checked_against_the_customized_portfolio_before_the_job_is_stored(svc):
    # NVDA is 20% of portfolio A: a target of 10% would be a sale. For the scenario portfolio (no NVDA) it is a purchase.
    lower = dict(NVDA_REQUEST, target_direct_weight=0.1)
    status, body = svc.call("POST /investigations", investigation_body(svc.policy, CUSTOM_A, lower), key="cp15-below-current")
    assert status == 422 and body["error"]["code"] == "INVALID_PURCHASE_REQUEST" and body["error"]["details"][0]["issue"].startswith("TARGET_BELOW_CURRENT_WEIGHT")
    assert svc.s3.keys("jobs/") == [] and svc.lambda_client.invocations == []
    # The same 10% target is accepted for the scenario portfolio: the refusal above came from the customized weights.
    status, _ = svc.call("POST /investigations", investigation_body(svc.policy, "absent", lower), key="cp15-default-portfolio")
    assert status == 202


def test_cp16_a_free_text_request_keeps_the_customized_portfolio_and_invents_nothing(svc):
    words = {"instrument_id": None, "target_direct_weight": None, "funding": "CASH", "original_words": "Put more into technology."}
    job = investigate(svc, svc.policy, CUSTOM_A, key="cp16-free-text", request=words)
    assert investigation_job_errors(job) == []
    assert job["status"] == "SUCCEEDED" and job["result"] is None and job["clarification"] is not None
    assert job["portfolio"] == expected_portfolio("robert", CUSTOM_A)
    (step,) = job["steps"]
    assert step["tool"] == "get_portfolio" and "3 positions" in step["result_summary"]
    assert svc.s3.json(f"results/{job['id']}.json")["inputs"]["portfolio_id"] == expected_id("robert", CUSTOM_A)
    assert svc.bedrock.calls == []


def test_cp17_a_stored_portfolio_that_is_not_valid_fails_the_job_and_nothing_is_guessed(svc):
    for index, damage in enumerate([lambda p: p.update(cash_weight=0.5),                                  # no longer adds up to 1
                                    lambda p: p["positions"].append(dict(p["positions"][0])),             # a duplicate instrument
                                    lambda p: p.update(persona_id="mateo"),                               # another persona's portfolio
                                    lambda p: p.pop("valuation_date")]):                                  # not the contract's shape
        status, accepted = svc.call("POST /investigations", investigation_body(svc.policy, CUSTOM_A), key=f"cp17-damaged-{index}")
        assert status == 202
        key = f"jobs/{accepted['id']}.json"
        job = svc.s3.json(key)
        damage(job["portfolio"])
        svc.s3.objects[key] = json.dumps(job).encode()
        assert svc.run_worker(accepted["id"]) == {"outcome": "completed", "status": "FAILED", "failure_code": "DATA_UNAVAILABLE"}
        failed = svc.s3.json(key)
        assert failed["status"] == "FAILED" and failed["failure"]["code"] == "DATA_UNAVAILABLE" and failed["failure"]["retryable"] is False
    assert svc.s3.keys("results/") == [] and svc.bedrock.calls == []


# --------------------------------------------------------------------------- immutability, reproducibility


def test_cp18_an_earlier_customization_and_its_report_stay_byte_for_byte_unchanged(svc):
    job_a = investigate(svc, svc.policy, CUSTOM_A, key="cp18-portfolio-a")
    frozen = {key: value for key, value in stored(svc).items() if job_a["id"] in key}
    assert sorted(key.split("/")[0] for key in frozen) == ["jobs", "results", "traces"]
    view_a = json.dumps(job_a, sort_keys=True)

    job_b = investigate(svc, svc.policy, CUSTOM_B, key="cp18-portfolio-b")
    job_default = investigate(svc, svc.policy, key="cp18-portfolio-default")
    status, check = svc.call("POST /check", check_body(svc.policy, CUSTOM_B))
    assert status == 200 and check == job_b["result"]

    assert {key: svc.s3.objects[key] for key in frozen} == frozen  # job, result and trace of A: the same bytes
    assert json.dumps(svc.get(job_a["id"]), sort_keys=True) == view_a
    assert job_a["portfolio"] == expected_portfolio("robert", CUSTOM_A) and job_b["portfolio"] == expected_portfolio("robert", CUSTOM_B)
    assert job_default["portfolio"] == scenario("robert")["portfolio"]
    assert len({job["portfolio"]["portfolio_id"] for job in (job_a, job_b, job_default)}) == 3
    assert len({job["id"] for job in (job_a, job_b, job_default)}) == 3
    # Each report is the engine's answer for its own portfolio, so A can be reproduced from what A's job stores.
    assert job_a["result"] == engine_on(UNIVERSE, job_a["portfolio"], svc.policy, job_a["resolved_request"])
    assert job_b["result"] == engine_on(UNIVERSE, job_b["portfolio"], svc.policy, job_b["resolved_request"])
    assert job_default["result"] == engine_direct(UNIVERSE, "robert", svc.policy, NVDA_REQUEST)
    assert job_a["result"] != job_b["result"] != job_default["result"] != job_a["result"]


def test_cp19_a_second_delivery_of_a_finished_custom_job_changes_nothing(svc):
    job = investigate(svc, svc.policy, CUSTOM_A, key="cp19-duplicate-delivery")
    before = stored(svc)
    assert svc.run_worker(job["id"]) == {"outcome": "duplicate", "status": "SUCCEEDED"}
    assert stored(svc) == before


# --------------------------------------------------------------------------- CHANGE_RULE


def test_cp20_a_change_rule_child_is_checked_against_the_parents_customized_portfolio(svc):
    parent = investigate(svc, svc.policy, CUSTOM_A, key="cp20-parent")
    frozen = {key: value for key, value in stored(svc).items() if parent["id"] in key}
    status, answer = svc.call("POST /investigations/{id}/challenge", CHANGE_RULE, path={"id": parent["id"]}, key="cp20-change-rule")
    assert status == 202, answer
    validate_api_body("api.schema.json#/$defs/challenge_response", answer)
    child_id = answer["investigation"]["id"]
    assert svc.s3.json(f"jobs/{child_id}.json")["portfolio"] == parent["portfolio"]  # inherited at creation; the challenge carries none
    svc.run_worker(child_id)
    child = svc.get(child_id)
    assert investigation_job_errors(child) == []
    assert child["status"] == "SUCCEEDED" and child["parent_investigation_id"] == parent["id"]
    assert child["portfolio"] == parent["portfolio"] == expected_portfolio("robert", CUSTOM_A)
    assert child["policy_version"] == 2 and child["result"] == engine_on(UNIVERSE, parent["portfolio"], answer["policy"], NVDA_REQUEST)
    assert child["result"]["portfolio_id"] == parent["portfolio"]["portfolio_id"] and child["result"]["feasibility"]["cash_before"] == 0.2
    assert child["result"] != engine_direct(UNIVERSE, "robert", answer["policy"], NVDA_REQUEST)  # not the scenario portfolio
    assert {key: svc.s3.objects[key] for key in frozen} == frozen  # the challenged job and its report are untouched
    # A replay of the challenge is the same child, with the same portfolio.
    status, replay = svc.call("POST /investigations/{id}/challenge", CHANGE_RULE, path={"id": parent["id"]}, key="cp20-change-rule")
    assert status == 202 and replay["investigation"]["id"] == child_id and svc.get(child_id)["portfolio"] == parent["portfolio"]
    # A challenge request cannot carry a portfolio of its own.
    status, refused = svc.call("POST /investigations/{id}/challenge", dict(CHANGE_RULE, custom_portfolio=CUSTOM_B), path={"id": parent["id"]},
                               key="cp20-change-rule-other")
    assert status == 400 and refused["error"]["code"] == "VALIDATION_ERROR"


# --------------------------------------------------------------------------- idempotency


def test_cp21_idempotency_covers_the_portfolio(svc):
    key = "cp21-one-user-action"
    status, first = svc.call("POST /investigations", investigation_body(svc.policy, CUSTOM_A), key=key)
    assert status == 202
    status, again = svc.call("POST /investigations", investigation_body(svc.policy, copy.deepcopy(CUSTOM_A)), key=key)
    assert status == 202 and again == first and len(svc.s3.keys("jobs/")) == 1  # the same key and body: the same job
    job_bytes = svc.s3.objects[f"jobs/{first['id']}.json"]
    for other in (CUSTOM_B, "absent", None):  # another portfolio, or none, under the same key
        status, body = svc.call("POST /investigations", investigation_body(svc.policy, other), key=key)
        assert status == 409 and body["error"]["code"] == "IDEMPOTENCY_KEY_REUSED", body
    assert svc.s3.objects[f"jobs/{first['id']}.json"] == job_bytes and len(svc.s3.keys("jobs/")) == 1
    assert svc.s3.json(f"jobs/{first['id']}.json")["portfolio"] == expected_portfolio("robert", CUSTOM_A)
    # After the job finished, the replay still answers with that job.
    svc.run_worker(first["id"])
    status, replay = svc.call("POST /investigations", investigation_body(svc.policy, CUSTOM_A), key=key)
    assert status == 202 and replay["id"] == first["id"] and replay["status"] == "SUCCEEDED"
    status, body = svc.call("POST /investigations", investigation_body(svc.policy, CUSTOM_B), key=key)
    assert status == 409


# --------------------------------------------------------------------------- missing holdings stay UNKNOWN


def service_without_holdings_for(fund_id):
    """The synthetic Robert universe with one equity fund's holdings file removed (as ESGV and QQQ have none in the real data)."""
    from backend.common.data import build_manifest
    from service_fakes import build_api, build_worker

    contents = {name: data for name, data in snapshot_contents(UNIVERSE).items() if name != "manifest.json"}
    holdings = json.loads(contents["holdings.json"])
    assert fund_id in holdings["funds"]
    del holdings["funds"][fund_id]
    contents["holdings.json"] = json.dumps(holdings, sort_keys=True).encode("utf-8")
    manifest = build_manifest(json.loads(contents["market_data.json"])["valuation_date"], contents, {})
    contents["manifest.json"] = json.dumps(manifest, sort_keys=True).encode("utf-8")

    svc = Service(UNIVERSE)
    for key in svc.s3.keys("snapshots/"):
        del svc.s3.objects[key]
    for name, data in contents.items():
        svc.s3.objects[f"snapshots/{manifest['snapshot_id']}/{name}"] = data
    svc.snapshot_id = manifest["snapshot_id"]
    svc.api = build_api(svc.s3, svc.lambda_client, svc.clock, snapshot_id=svc.snapshot_id, bedrock=svc.bedrock)
    svc.worker = build_worker(svc.s3, svc.bedrock, svc.clock, snapshot_id=svc.snapshot_id)
    data = {name: json.loads(contents[f"{name}.json"]) for name in ("instruments", "holdings", "market_data", "controversies")}
    return svc, data


def assert_unknown_for_missing_holdings(result, fund_id, fund_weight):
    (entry,) = result["rule_results"]
    assert entry["status"] == "UNKNOWN" and entry["status"] != "PASS" and entry["gap"] is None
    assert "MISSING_HOLDINGS" in entry["unknown_causes"]
    assert entry["measured"]["lower"] <= entry["limit"] < entry["measured"]["upper"]  # neither proven to pass nor to fail
    fund = next(fund for fund in result["data_coverage"] if fund["fund_id"] == fund_id)
    assert fund["status"] == "MISSING" and fund["coverage_fraction"] == 0.0
    assert fund["portfolio_weight"] == fund["uncovered_portfolio_weight"] == pytest.approx(fund_weight)
    assert result["summary"]["counts"]["pass"] == 0 and result["max_compliant"]["status"] == "WITHHELD"


def test_cp22_a_fund_without_a_holdings_file_in_a_custom_portfolio_is_unknown_never_pass():
    svc, data = service_without_holdings_for("XIU.TO")
    custom = {"cash_weight": 0.4, "positions": [{"instrument_id": "XBB.TO", "weight": 0.3}, {"instrument_id": "XIU.TO", "weight": 0.3}]}
    request = {"instrument_id": "JNJ", "target_direct_weight": 0.05, "funding": "CASH", "original_words": "A little Johnson & Johnson."}
    drafts = [dict(rule, rule_id="robert-issuer-cap-draft") for rule in ISSUER_CAP_DRAFT]  # no single company above 20%
    status, body = svc.call("POST /check", check_body(None, custom, drafts, request=request))
    assert status == 200, body
    portfolio = expected_portfolio("robert", custom)
    assert body == engine.check_rules(portfolio, None, request, data["instruments"], data["holdings"], data["market_data"], data["controversies"],
                                      draft_rules=drafts, data_sources=None, portfolio_customized=True)
    assert_unknown_for_missing_holdings(body, "XIU.TO", 0.3)

    # The same through an investigation, with a confirmed rule: 30% of the portfolio is a fund nobody can look through.
    rule = dict(scenario("robert")["scenario_rules"][0])
    assert rule["rule_type"] == "max_issuer_exposure"
    policy = svc.confirm(rules=[rule], confirmations=[{"rule": rule, "threshold": 0.2}])
    job = investigate(svc, policy, custom, key="cp22-missing-holdings", request=request)
    assert job["status"] == "SUCCEEDED" and job["portfolio"] == portfolio
    assert job["result"] == engine.check_rules(portfolio, policy, request, data["instruments"], data["holdings"], data["market_data"],
                                               data["controversies"], data_sources=None, portfolio_customized=True)
    assert_unknown_for_missing_holdings(job["result"], "XIU.TO", 0.3)


@needs_real_data
@pytest.mark.parametrize("fund_id", ["ESGV", "QQQ"])
def test_cp23_real_funds_without_holdings_in_a_custom_portfolio_are_unknown_never_pass(fund_id):
    svc = Service(None)
    custom = {"cash_weight": 0.4, "positions": [{"instrument_id": "XBB.TO", "weight": 0.3}, {"instrument_id": fund_id, "weight": 0.3}]}
    request = {"instrument_id": "JNJ", "target_direct_weight": 0.05, "funding": "CASH", "original_words": "A little Johnson & Johnson."}
    drafts = [dict(rule, rule_id="robert-issuer-cap-draft") for rule in ISSUER_CAP_DRAFT]
    status, body = svc.call("POST /check", check_body(None, custom, drafts, request=request))
    assert status == 200, body
    assert body == engine_on(None, expected_portfolio("robert", custom), None, request, draft_rules=drafts)
    assert_unknown_for_missing_holdings(body, fund_id, 0.3)


@needs_real_data
def test_cp24_mateo_customized_on_real_data_through_check_and_an_investigation():
    svc = Service(None)
    policy = svc.confirm("mateo")
    base = scenario("mateo")["portfolio"]
    # Mateo moves 5 points from cash into MSFT and drops nothing: ESGV (no holdings file) is still held.
    custom = {"cash_weight": 0.2, "positions": [dict(p, weight=0.1) if p["instrument_id"] == "MSFT" else dict(p) for p in base["positions"]]}
    request = scenario("mateo")["demo_requests"][0]["purchase_request"]
    portfolio = expected_portfolio("mateo", custom)
    expected = engine_on(None, portfolio, policy, request)
    status, body = svc.call("POST /check", check_body(policy, custom, persona_id="mateo", request=request))
    if expected["execution"]["status"] != "OK":
        pytest.skip("the scenario's demo request is not executable on this customized portfolio")
    assert status == 200 and body == expected and body["portfolio_id"] == portfolio["portfolio_id"]
    assert body != engine_direct(None, "mateo", policy, request)
    job = investigate(svc, policy, custom, key="cp24-mateo-custom", request=request)
    assert job["status"] == "SUCCEEDED" and job["result"] == expected and job["portfolio"] == portfolio
    for entry in job["result"]["rule_results"]:
        assert entry["status"] != "PASS" and "MISSING_HOLDINGS" in entry["unknown_causes"]


def test_cp25_the_custom_portfolio_definition_itself_refuses_bad_shapes():
    """Rule 1 is the schema's: these never reach the resolver through a route."""
    for custom in [{"cash_weight": -0.1, "positions": []}, {"cash_weight": 1.1, "positions": []},
                   {"cash_weight": 1.0, "positions": [{"instrument_id": "SPY", "weight": 0}]},
                   {"cash_weight": 1.0, "positions": [{"instrument_id": "SPY", "weight": -0.5}]},
                   {"cash_weight": 0.0, "positions": [{"instrument_id": "SPY", "weight": 1.5}]},
                   {"cash_weight": 1.0, "positions": [], "leverage": 2},
                   {"cash_weight": 0.18, "positions": [{"instrument_id": "SPY", "weight": 0.02}] * 41},
                   {"cash_weight": 1.0, "positions": [{"instrument_id": "spy", "weight": 0.5}]}]:
        with pytest.raises(ContractError):
            validate_api_body("api.schema.json#/$defs/custom_portfolio", custom)
    validate_api_body("api.schema.json#/$defs/custom_portfolio", CUSTOM_A)
    validate_api_body("api.schema.json#/$defs/check_request", check_body(None, CUSTOM_A, []))
    validate_api_body("api.schema.json#/$defs/check_request", check_body(None, None, []))
    validate_api_body("api.schema.json#/$defs/check_request", check_body(None, "absent", []))
    validate_api_body("api.schema.json#/$defs/investigation_create_request", dict(create_body(), custom_portfolio=CUSTOM_A))


# --------------------------------------------------------------------------- code review F1: a bound above 1

def over_cash_case():
    """90% in an equity fund nobody can look through, 10% cash, and a purchase 5 points larger than the cash.

    contracts/SEMANTICS.md section 4: with INSUFFICIENT_CASH the rules are still evaluated at the requested weights.
    Section 5: upper = lower + U. NVIDIA: lower 0.15 (direct), U = 0.90 (the whole fund), upper = 1.05.
    """
    svc, data = service_without_holdings_for("XIU.TO")
    custom = {"cash_weight": 0.1, "positions": [{"instrument_id": "XIU.TO", "weight": 0.9}]}
    request = {"instrument_id": "NVDA", "target_direct_weight": 0.15, "funding": "CASH", "original_words": "Some NVIDIA."}
    rule = dict(scenario("robert")["scenario_rules"][0])
    assert rule["rule_type"] == "max_issuer_exposure"
    policy = svc.confirm(rules=[rule], confirmations=[{"rule": rule, "threshold": 0.1}])
    return svc, data, custom, request, policy


def assert_over_cash_result(result):
    from byb_contracts import validate_check_result

    validate_check_result(result)  # the document the service publishes is a valid contract document
    assert result["execution"]["status"] == "OK"
    assert result["feasibility"]["status"] == "INSUFFICIENT_CASH" and result["feasibility"]["cash_after"] == pytest.approx(-0.05)
    assert result["summary"]["feasibility_status"] == "INSUFFICIENT_CASH"
    (entry,) = result["rule_results"]
    assert entry["status"] == "FAIL"  # 0.15 proven > 0.10
    assert entry["measured"]["lower"] == pytest.approx(0.15) and entry["measured"]["upper"] == pytest.approx(1.05)
    nvidia = next(subject for subject in entry["breaching_subjects"] if subject["lower"] == pytest.approx(0.15))
    assert nvidia["upper"] == pytest.approx(1.05), "the same quantity is the same number wherever the result shows it: never capped in one place"
    assert max(issuer["proposed"]["upper"] for issuer in result["exposure"]["issuers"]) == pytest.approx(1.05)


def test_cp26_an_over_cash_purchase_next_to_a_fund_without_holdings_is_insufficient_cash_on_both_routes():
    svc, data, custom, request, policy = over_cash_case()
    portfolio = expected_portfolio("robert", custom)
    expected = engine.check_rules(portfolio, policy, request, data["instruments"], data["holdings"], data["market_data"], data["controversies"],
                                  data_sources=None, portfolio_customized=True)

    status, body = svc.call("POST /check", check_body(policy, custom, request=request))
    assert status == 200, body
    assert body == expected
    assert_over_cash_result(body)

    job = investigate(svc, policy, custom, key="cp26-over-cash", request=request)
    assert job["status"] == "SUCCEEDED", job["failure"]
    assert investigation_job_errors(job) == []
    assert job["result"] == body, "the investigation and the check agree"
    assert_over_cash_result(job["result"])


def test_cp27_check_never_returns_a_result_that_is_not_a_valid_contract_document(svc, monkeypatch):
    """The worker refuses to publish an invalid result (FAILED / ENGINE_ERROR); POST /check must not answer 200 with one."""
    real = engine.check_rules

    def broken(*args, **kwargs):
        result = real(*args, **kwargs)
        result["rule_results"][0]["limit"] = 7.0  # a threshold is a fraction: this document is not a check_result
        return result

    monkeypatch.setattr(engine, "check_rules", broken)
    status, body = svc.call("POST /check", check_body(svc.policy))
    assert status == 500 and body["error"]["code"] == "INTERNAL_ERROR", body
    assert "rule_results" not in body
