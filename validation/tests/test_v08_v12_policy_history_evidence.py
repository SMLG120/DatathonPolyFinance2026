"""V08-V12: ambiguous wording (fixture level), unconfirmed thresholds, policy revision,
historical metrics with FX, evidence traceability.
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path

import pytest

from byb_contracts import check_result_errors, interpretation_errors, policy_errors

from validation.support import reference as ref
from validation.support import universe as U
from validation.support.run import by_rule, check, close

REPO_ROOT = Path(__file__).resolve().parents[2]
API_FIXTURES = REPO_ROOT / "contracts" / "fixtures" / "api"
SCENARIOS = REPO_ROOT / "contracts" / "scenarios"


def _fixture(name: str) -> dict:
    return json.loads((API_FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def _all_rules(interpretation: dict) -> list[dict]:
    rules = list(interpretation["proposed_rules"])
    for clarification in interpretation["clarifications"]:
        rules += [option["proposed_rule"] for option in clarification["options"] if option["proposed_rule"]]
    return rules


# --------------------------------------------------------------------------- V08 (fixtures level)

@pytest.mark.vcase("V08")
def test_v08_amira_ambiguous_wording_gets_a_question_not_a_contradiction():
    """'maximum growth' + 'strict diversification' (LEAD_DECISIONS D7, BUILD_BRIEF section 3)."""
    interpretation = _fixture("interpret_amira_ambiguous")["response_body"]
    assert interpretation_errors(interpretation) == []
    assert interpretation["original_words"] == "I want maximum growth and strict diversification.", "the user's words are preserved"
    assert interpretation["proposed_rules"] == [], "no rule may be drafted from ambiguous wording without asking"
    assert len(interpretation["clarifications"]) >= 1
    for clarification in interpretation["clarifications"]:
        assert len(clarification["options"]) >= 2
        assert clarification["about_words"] in interpretation["original_words"]
    text = json.dumps(interpretation).lower()
    assert "proven_conflict" not in text and "min_exceeds_max" not in text
    for rule in _all_rules(interpretation):
        assert rule["status"] == "PROPOSED" and rule["threshold"] is None and rule["origin"] == "SYSTEM_PROPOSED"
    growth = [u for u in interpretation["unsupported"] if "growth" in u["words"]]
    assert growth and growth[0]["code"] in ("UNSUPPORTED_RULE_TYPE", "UNSUPPORTED_DEFINITION")


@pytest.mark.vcase("V08")
def test_v08_mateo_oil_is_clarified_and_unsupported_definitions_are_labelled():
    interpretation = _fixture("interpret_mateo_clarification")["response_body"]
    assert interpretation_errors(interpretation) == []
    oil = next(c for c in interpretation["clarifications"] if c["about_words"] == "oil")
    assert len(oil["options"]) >= 2
    by_id = {o["option_id"]: o for o in oil["options"]}
    unsupported = [o for o in oil["options"] if not o["supported"]]
    assert unsupported, "definitions without sourced data (oil producers, fossil fuels) must be offered as unsupported (D3)"
    assert all(o["proposed_rule"] is None for o in unsupported)
    energy = by_id["energy-sector-label"]["proposed_rule"]
    assert energy["rule_type"] == "exclusion" and energy["parameters"]["definition"] == {"kind": "fund_reported_sector", "sector": "Energy"}
    assert energy["threshold"] is None, "the interpreter must not invent the tolerance"


@pytest.mark.vcase("V08")
@pytest.mark.parametrize("name", ["interpret_amira_ambiguous", "interpret_mateo_clarification", "challenge_clarify_preference"])
def test_v08_no_interpretation_fixture_carries_an_invented_number(name):
    """A draft number is allowed only when it is quoted from the user's own words (SEMANTICS 14)."""
    body = _fixture(name)["response_body"]
    interpretation = body.get("interpretation") or body
    words = interpretation["original_words"]
    for rule in _all_rules(interpretation):
        assert rule["status"] == "PROPOSED", "an interpretation never activates a rule"
        assert rule["origin"] != "FICTIONAL_SCENARIO", "the interpreter never emits FICTIONAL_SCENARIO rules"
        if rule["threshold"] is not None:
            assert rule["threshold_source"] == "USER_WORDS" and rule["threshold_quote"] in words


@pytest.mark.vcase("V08")
def test_v08_interpretation_validator_rejects_an_invented_threshold():
    """The contract validator (used by the service) must refuse a model draft that carries a number the user never wrote."""
    interpretation = copy.deepcopy(_fixture("interpret_mateo_clarification")["response_body"])
    rule = next(o["proposed_rule"] for c in interpretation["clarifications"] for o in c["options"] if o["proposed_rule"])
    rule.update(threshold=0.10, origin="USER_STATED", threshold_source="USER_WORDS", threshold_quote="10%")
    assert interpretation_errors(interpretation), "a quoted number that is not in the user's words must be rejected"
    system_number = copy.deepcopy(_fixture("interpret_mateo_clarification")["response_body"])
    rule = next(o["proposed_rule"] for c in system_number["clarifications"] for o in c["options"] if o["proposed_rule"])
    rule["threshold"] = 0.10
    assert interpretation_errors(system_number), "a SYSTEM_PROPOSED rule must never carry a number"


@pytest.mark.vcase("V08")
@pytest.mark.parametrize("persona", ["robert", "mateo", "amira"])
def test_v08_scenarios_are_labelled_fictional_and_rules_start_inactive(persona):
    scenario = json.loads((SCENARIOS / f"{persona}.json").read_text(encoding="utf-8"))
    assert scenario["fictional"] is True and scenario["portfolio"]["fictional"] is True
    assert "advice" in scenario["fiction_notice"].lower()
    for rule in scenario["scenario_rules"]:
        assert rule["status"] == "PROPOSED", "scenario rules are offered for confirmation, never pre-confirmed"
        assert rule["confirmed_at"] is None and rule["confirmed_by"] is None


# --------------------------------------------------------------------------- V09

V09_PORTFOLIO = {"AAA": 0.30, "BND": 0.50}


@pytest.mark.vcase("V09")
def test_v09_a_proposed_threshold_is_never_evaluated_in_a_stored_policy():
    """A drafted cap of 0.10 (PROPOSED, with a number) on ALPHA 0.35 would FAIL, a drafted cap of 0.90 would PASS:
    neither may produce a verdict before confirmation."""
    for limit in (0.10, 0.90):
        rules = [U.cap_any("draft-cap", limit, status="PROPOSED"), U.cap_any("blank", None, status="PROPOSED")]
        result = check(U.portfolio(0.20, V09_PORTFOLIO), rules, U.request("AAA", 0.35))
        assert result["rule_results"] == []
        assert [(r["rule_id"], r["status"]) for r in result["rules_not_evaluated"]] == [("draft-cap", "PROPOSED"), ("blank", "PROPOSED")]
        assert result["summary"]["headline"] == "NO_RULES_EVALUATED"
        assert result["summary"]["counts"] == {"pass": 0, "fail": 0, "unknown": 0}
        assert result["max_compliant"]["status"] == "WITHHELD", "nothing confirmed: nothing to be compliant with"
        assert result["scenario"] is None


@pytest.mark.vcase("V09")
def test_v09_unconfirmed_rule_does_not_hide_or_dilute_a_confirmed_failure():
    rules = [U.cap_any("draft-cap", 0.90, status="PROPOSED"), U.cap_any("cap", 0.10)]
    result = check(U.portfolio(0.20, V09_PORTFOLIO), rules, U.request("AAA", 0.35))
    assert [r["rule_id"] for r in result["rule_results"]] == ["cap"] and result["rule_results"][0]["status"] == "FAIL"
    assert result["summary"]["headline"] == "HAS_FAIL" and result["summary"]["rules_not_evaluated"] == 1


@pytest.mark.vcase("V09")
def test_v09_preview_evaluates_drafts_but_is_labelled_and_stores_no_policy_reference():
    drafts = [U.cap_any("draft-cap", 0.10, status="PROPOSED"), U.cap_any("blank", None, status="PROPOSED")]
    result = check(U.portfolio(0.20, V09_PORTFOLIO), drafts, U.request("AAA", 0.35), preview=True)
    assert result["preview"] is True and result["policy_id"] is None and result["policy_version"] is None
    assert by_rule(result)["draft-cap"]["status"] == "FAIL"
    assert [r["rule_id"] for r in result["rules_not_evaluated"]] == ["blank"]
    assert all(record["policy_version"] is None for record in result["evidence"])
    threshold = next(r for r in result["evidence"] if r["metric_id"] == "rule_threshold")
    assert threshold["label"] == "ASSUMPTION", "a draft number in a preview is an assumption, not a confirmed fact"


@pytest.mark.vcase("V09")
def test_v09_confirmed_threshold_evidence_keeps_its_provenance_label():
    rules = [U.cap_any("user-cap", 0.50), U.loss_budget("scenario-budget", 0.50, origin="FICTIONAL_SCENARIO")]
    result = check(U.portfolio(0.20, V09_PORTFOLIO), rules, U.request("AAA", 0.35))
    labels = {r["subject"]["id"]: r["label"] for r in result["evidence"] if r["metric_id"] == "rule_threshold"}
    assert labels == {"user-cap": "FACT", "scenario-budget": "FICTIONAL_SCENARIO"}


# --------------------------------------------------------------------------- V10

V10_PORTFOLIO = {"BND": 0.40, "F2": 0.10, "F1": 0.10, "BBB": 0.05, "CCC": 0.05}


def _v10_policies() -> tuple[dict, dict]:
    objective = U.objective()
    v1 = U.policy([U.cap_any("cap-1", 0.10, objective_id="obj-1"), U.loss_budget("budget-1", 0.05, objective_id="obj-1")], objectives=[objective])
    v2 = U.policy(
        [U.cap_any("cap-1", 0.10, objective_id="obj-1", status="SUPERSEDED", superseded_by="cap-2"),
         U.cap_any("cap-2", 0.40, objective_id="obj-1", supersedes="cap-1"),
         U.loss_budget("budget-1", 0.05, objective_id="obj-1")],
        version=2, parent=1, objectives=[objective],
    )
    return v1, v2


@pytest.mark.vcase("V10")
def test_v10_raising_the_cap_creates_a_new_version_and_the_budget_is_still_reported():
    """cash 0.30 | BND 0.40 | F2 0.10 | F1 0.10 | BBB 0.05 | CCC 0.05 ; buy AAA to 0.25.

    ALPHA before = 0.10 x 0.30 (F1) + 0.10 x 0.50 (F2) = 0.08 ; U = 0.10 x 0.20 = 0.02
    ALPHA after  = 0.33 lower, 0.35 upper
    v1 cap 0.10 -> FAIL, gap 0.23.       v2 cap 0.40 -> PASS, gap 0.35 - 0.40 = -0.05.
    loss before = 0.40x0.05 + 0.10x0.1296 + 0.10x0.10 - 0.05x0.30 + 0.05x0.0208 = 0.029
    loss after  = 0.029 + 0.25 x 0.10 = 0.054 ; budget 0.05 -> FAIL with gap 0.004 in BOTH versions.
    maximum under v2: cap 0.10 + w <= 0.40 -> 0.30 ; budget 0.029 + 0.10 w <= 0.05 -> 0.21 ; cash 0.30 -> 0.21, bound by the budget.
    """
    v1, v2 = _v10_policies()
    assert policy_errors(v1) == [] and policy_errors(v2) == []
    portfolio, request = U.portfolio(0.30, V10_PORTFOLIO), U.request("AAA", 0.25)

    first = check(portfolio, v1, request)
    assert first["policy_version"] == 1
    assert [(r["rule_id"], r["status"]) for r in first["rule_results"]] == [("cap-1", "FAIL"), ("budget-1", "FAIL")]
    assert close(by_rule(first)["cap-1"]["gap"], 0.23)

    second = check(portfolio, v2, request)
    assert second["policy_version"] == 2
    assert [(r["rule_id"], r["status"]) for r in second["rule_results"]] == [("cap-2", "PASS"), ("budget-1", "FAIL")]
    assert [(r["rule_id"], r["status"]) for r in second["rules_not_evaluated"]] == [("cap-1", "SUPERSEDED")]
    cap, budget = by_rule(second)["cap-2"], by_rule(second)["budget-1"]
    assert cap["limit"] == 0.40 and close(cap["gap"], -0.05)
    assert close(budget["measured"]["lower"], 0.054) and budget["limit"] == 0.05 and close(budget["gap"], 0.004)
    assert second["summary"]["headline"] == "HAS_FAIL", "raising one cap must not turn a separately confirmed budget breach into a pass"
    assert second["policy_consistency"]["status"] == "CONSISTENT", "goal tension is not a mathematical contradiction"
    assert {r["policy_version"] for r in second["evidence"]} == {2}
    assert {r["policy_version"] for r in first["evidence"]} == {1}

    maximum = second["max_compliant"]
    assert maximum["status"] == "SUPPORTED" and close(maximum["final_direct_weight"], 0.21, 1e-9)
    assert maximum["binding_constraint"] == {"type": "RULE", "rule_id": "budget-1"}

    # No stale verdict: nothing in the v2 result cites the superseded rule or its number.
    cited = {entry["rule_id"] for entry in second["rule_results"]} | {f["rule_id"] for f in second["starting_portfolio_findings"]}
    assert "cap-1" not in cited
    assert not any(r["metric_id"] == "rule_threshold" and r["subject"]["id"] == "cap-1" for r in second["evidence"])


@pytest.mark.vcase("V10")
def test_v10_old_report_is_reproducible_bit_for_bit_and_objective_is_preserved():
    v1, v2 = _v10_policies()
    portfolio, request = U.portfolio(0.30, V10_PORTFOLIO), U.request("AAA", 0.25)
    first = check(portfolio, v1, request)
    check(portfolio, v2, request)
    again = check(portfolio, v1, request)
    assert again == first, "re-running the earlier policy version must reproduce the earlier report exactly"
    assert v1["objectives"] == v2["objectives"]
    assert v1["content_hash"] != v2["content_hash"]


@pytest.mark.vcase("V10")
def test_v10_a_policy_version_edited_in_place_is_refused():
    """Immutability: changing a stored version's number without a new version breaks its content hash."""
    v1, _ = _v10_policies()
    tampered = copy.deepcopy(v1)
    tampered["rules"][0]["threshold"] = 0.90
    assert policy_errors(tampered), "the validator must notice the edit"
    result = check(U.portfolio(0.30, V10_PORTFOLIO), tampered, U.request("AAA", 0.25))
    assert result["execution"] == {**result["execution"], "status": "INVALID_REQUEST", "code": "INVALID_POLICY"}
    assert result["rule_results"] == [] and result["summary"]["headline"] == "INVALID_REQUEST"


@pytest.mark.vcase("V10")
def test_v10_broken_supersede_links_are_refused():
    objective = U.objective()
    dangling = U.policy([U.cap_any("cap-2", 0.40, objective_id="obj-1", supersedes="cap-1")], version=2, parent=1, objectives=[objective])
    assert policy_errors(dangling)
    two_active = U.policy([U.cap_any("cap-1", 0.10, status="SUPERSEDED", superseded_by="cap-2"), U.cap_any("cap-2", 0.40)], version=2, parent=1)
    assert policy_errors(two_active), "a replacement must point back to the rule it supersedes"
    wrong_parent = U.policy([U.cap_any("cap-1", 0.10)], version=2, parent=None)
    assert policy_errors(wrong_parent)


# --------------------------------------------------------------------------- V11 (synthetic)

V11_PORTFOLIO = {"AAB": 0.30, "CCC": 0.20, "AAA": 0.30}


@pytest.mark.vcase("V11")
def test_v11_terminal_loss_and_drawdown_are_different_metrics_with_backward_matched_fx():
    """cash 0.20 | AAB 0.30 (USD) | CCC 0.20 (USD) | AAA 0.30 (CAD).

    Base 2021-12-31: AAB's last price is 2021-12-30 (1 day old) x fx of 2021-12-31 (1.25, matched to the valuation
    date, SEMANTICS 7) = 62.5. End 2022-12-30: fx is the 2022-12-28 rate 1.36 (2 days old; there is no later row).
        r(AAB) = 55 x 1.36 / 62.5 - 1 = +0.1968 ; r(CCC) = 180 x 1.36 / 250 - 1 = -0.0208 ; r(AAA) = -0.10
    terminal return = 0.30 x 0.1968 - 0.20 x 0.0208 - 0.30 x 0.10 = +0.02488   (a GAIN: loss = -0.02488)
    2022-06-30 (fx 1.30): AAB 52/62.5 = 0.832 ; CCC 195/250 = 0.78 ; AAA 0.80
        V = 0.20 + 0.30 x 0.832 + 0.20 x 0.78 + 0.30 x 0.80 = 0.8456 -> drawdown -0.1544 on 2022-06-30
    A 5% loss budget therefore PASSES although the path fell 15.44%: the rule measures terminal loss only.
    """
    from backend.engine import replay_period

    data = U.universe()
    portfolio = U.portfolio(0.20, V11_PORTFOLIO)
    replay = replay_period(portfolio, data["market_data"])
    assert replay["status"] == "COMPUTED"
    assert close(replay["scenario_terminal_return"], 0.02488, 1e-12)
    assert close(replay["scenario_max_drawdown"], -0.1544, 1e-12)
    assert replay["max_drawdown_date"] == "2022-06-30"
    rows = {row["instrument_id"]: row for row in replay["instrument_returns"]}
    for instrument, expected in (("AAB", 0.1968), ("CCC", -0.0208), ("AAA", -0.10)):
        assert close(rows[instrument]["return_cad"], expected, 1e-12)
        assert close(rows[instrument]["return_cad"], U.HAND_RETURNS[instrument], 1e-12)
    aab = rows["AAB"]
    assert (aab["base_price_date"], aab["base_price_age_days"]) == ("2021-12-30", 1)
    assert (aab["base_fx_date"], aab["base_fx_age_days"]) == ("2021-12-31", 0)
    assert (aab["end_fx_date"], aab["end_fx_age_days"]) == ("2022-12-28", 2), "the rate age must be reported"
    assert rows["AAA"]["base_fx_date"] is None and rows["AAA"]["end_fx_age_days"] is None

    # The validator's own replay agrees (plain scan instead of the engine's bisect).
    own = ref.replay(0.20, V11_PORTFOLIO, data["market_data"]["prices"], data["market_data"]["fx_usdcad"])
    assert close(own["terminal_return"], replay["scenario_terminal_return"], 1e-12)
    assert close(own["max_drawdown"], replay["scenario_max_drawdown"], 1e-12)

    result = check(portfolio, [U.loss_budget("budget", 0.05)], U.request("AAA", 0.30))
    rule = by_rule(result)["budget"]
    assert rule["status"] == "PASS" and close(rule["measured"]["lower"], -0.02488, 1e-12), "the measure is -terminal return and may be negative"
    assert close(rule["gap"], -0.02488 - 0.05, 1e-12)
    scenario = result["scenario"]
    assert close(scenario["proposed"]["scenario_max_drawdown"], -0.1544, 1e-12)
    assert rule["breaching_subjects"] == [] and rule["out_of_scope"] == []


@pytest.mark.vcase("V11")
def test_v11_the_fx_rate_is_never_a_later_rate():
    """A forward match would use no rate at all at the end date (none after 2022-12-28) or the 2021-12-31 rate for a
    2021-12-30 valuation. Check the engine's own observation at 2021-12-30 uses 1.20, not 1.25."""
    from backend.engine.core import _Market  # the subject under test

    market = _Market(U.market_data())
    seen = market.observation("AAB", "2021-12-30")
    assert (seen["fx_date"], seen["fx"]) == ("2021-12-30", 1.20)
    assert market.observation("AAB", "2021-12-29") is None, "no price on or before the date: nothing is invented"


@pytest.mark.vcase("V11")
def test_v11_linearity_of_the_terminal_return_in_the_target_weight():
    """R(w) = R(w0) + (w - w0) x r (LEAD_DECISIONS D6): 0.029 loss at w=0, +0.10 per unit of AAA."""
    portfolio = U.portfolio(0.30, V10_PORTFOLIO)
    for target in (0.0, 0.05, 0.21, 0.30):
        rule = by_rule(check(portfolio, [U.loss_budget("budget", 0.05)], U.request("AAA", target)))["budget"]
        assert close(rule["measured"]["lower"], 0.029 + 0.10 * target, 1e-12)
        assert rule["status"] == ("PASS" if target <= 0.21 else "FAIL")


@pytest.mark.vcase("V11")
def test_v11_scenario_is_labelled_as_a_replay_with_period_and_assumptions_and_never_a_forecast():
    result = check(U.portfolio(0.20, V11_PORTFOLIO), [U.loss_budget("budget", 0.05)], U.request("AAA", 0.30))
    scenario = result["scenario"]
    assert (scenario["base_date"], scenario["end_date"]) == ("2021-12-31", "2022-12-30")
    assert "not a forecast" in scenario["label"].lower()
    joined = " ".join(scenario["assumptions"]).lower()
    for needle in ("buy and hold", "no rebalancing", "cash earns a return of 0", "adjusted-close", "on or before", "fees and taxes"):
        assert needle in joined, f"assumption not disclosed: {needle}"
    text = json.dumps(result).lower()
    for banned in ("maximum future loss", "expected return", "will lose", "will return", "we recommend", "you should buy", "you should sell"):
        assert banned not in text, f"forecast or advice wording in an engine result: {banned!r}"
    assert any("not forecasts" in d.lower() or "not a forecast" in d.lower() for d in result["disclosures"])
    assert any("fees and taxes are excluded" in d.lower() for d in result["disclosures"])
    drawdown_context = [g for g in result["goal_context"] if g["context_type"] == "SCENARIO_DRAWDOWN"]
    assert drawdown_context == [], "no objective in this policy: goal context stays empty"


@pytest.mark.vcase("V11")
def test_v11_drawdown_is_context_only_and_has_no_status():
    result = check(U.portfolio(0.20, V11_PORTFOLIO), U.policy([U.loss_budget("budget", 0.05, objective_id="obj-1")], objectives=[U.objective()]),
                   U.request("AAA", 0.30))
    context = [g for g in result["goal_context"] if g["context_type"] == "SCENARIO_DRAWDOWN"]
    assert len(context) == 1 and "status" not in context[0]
    assert "not a forecast" in context[0]["text"].lower() and "context only" in context[0]["text"].lower()
    assert all(entry["rule_type"] != "scenario_max_drawdown" for entry in result["rule_results"])
    for entry in result["goal_context"]:
        assert "status" not in entry, "an objective is never PASS or FAIL"


# --------------------------------------------------------------------------- V12 (engine evidence)

def _evidence(result: dict) -> dict[str, dict]:
    return {record["evidence_id"]: record for record in result["evidence"]}


def _cited_ids(node, found=None) -> set:
    found = set() if found is None else found
    if isinstance(node, dict):
        for key, value in node.items():
            if key in ("evidence_ids", "derived_from") and isinstance(value, list):
                found.update(value)
            else:
                _cited_ids(value, found)
    elif isinstance(node, list):
        for item in node:
            _cited_ids(item, found)
    return found


V12_CASES = [
    (0.30, V10_PORTFOLIO, [U.cap_any("cap", 0.40), U.loss_budget("budget", 0.05)], ("AAA", 0.25)),
    (0.30, V04_PORTFOLIO := {"F2": 0.20, "F3": 0.25, "AAA": 0.05, "BND": 0.20},
     [U.cap_any("cap", 0.10), U.exclude_sector("energy", "Energy", 0.0), U.exclude_named("no-gamma", ["GAMMA"], 0.0)], ("BBB", 0.05)),
    (0.20, {"AAA": 0.05, "AAB": 0.05, "F1": 0.30, "F2": 0.20, "BND": 0.20}, [U.floor_one("floor", "ALPHA", 0.20), U.cap_one("cap", "ALPHA", 0.50)], ("CCC", 0.05)),
]


@pytest.mark.vcase("V12")
@pytest.mark.parametrize("cash, positions, rules, purchase", V12_CASES)
def test_v12_every_cited_evidence_id_exists_and_ids_are_unique(cash, positions, rules, purchase):
    result = check(U.portfolio(cash, positions), rules, U.request(*purchase))
    records = result["evidence"]
    ids = [r["evidence_id"] for r in records]
    assert len(ids) == len(set(ids))
    missing = _cited_ids(result) - set(ids)
    assert missing == set(), f"ids cited but absent from evidence[]: {sorted(missing)[:5]}"


@pytest.mark.vcase("V12")
@pytest.mark.parametrize("cash, positions, rules, purchase", V12_CASES)
def test_v12_decisive_numbers_trace_to_a_record_of_the_right_metric_subject_unit_and_state(cash, positions, rules, purchase):
    """Not a digit search: each decisive number must be backed by a cited record whose metric, subject, unit,
    portfolio state and period all fit the claim (BUILD_BRIEF section 6)."""
    result = check(U.portfolio(cash, positions), rules, U.request(*purchase))
    evidence = _evidence(result)
    for entry in result["rule_results"]:
        cited = [evidence[i] for i in entry["evidence_ids"]]
        threshold = [r for r in cited if r["metric_id"] == "rule_threshold"]
        assert len(threshold) == 1
        assert threshold[0]["subject"] == {**threshold[0]["subject"], "kind": "RULE", "id": entry["rule_id"]}
        assert threshold[0]["value"] == entry["limit"] and threshold[0]["unit"] == "fraction"

        if entry["gap"] is not None:
            gaps = [r for r in cited if r["metric_id"] == "gap_to_limit"]
            assert len(gaps) == 1 and close(gaps[0]["value"], entry["gap"]) and gaps[0]["subject"]["id"] == entry["rule_id"]
            assert gaps[0]["subject"]["portfolio_state"] == "PROPOSED"
            assert threshold[0]["evidence_id"] in gaps[0]["derived_from"]
        else:
            assert not [r for r in cited if r["metric_id"] == "gap_to_limit"], "an UNKNOWN rule has no gap to cite"

        proposed = [r for r in cited if r["subject"]["portfolio_state"] == "PROPOSED"]
        if entry["rule_type"] == "scenario_loss_budget":
            loss = [r for r in proposed if r["metric_id"] == "scenario_loss"]
            assert len(loss) == 1 and close(loss[0]["value"], entry["measured"]["lower"])
            assert loss[0]["period"] == {"type": "RANGE", "start_date": "2021-12-31", "end_date": "2022-12-30"}
            assert loss[0]["subject"]["kind"] == "PORTFOLIO" and loss[0]["unit"] == "fraction"
        elif entry["rule_type"] in ("max_issuer_exposure", "min_issuer_exposure") and entry["measured"]["lower"] > 0:
            lowers = [r for r in proposed if r["metric_id"] == "exposure_lower" and close(r["value"], entry["measured"]["lower"])]
            uppers = [r for r in proposed if r["metric_id"] == "exposure_upper" and close(r["value"], entry["measured"]["upper"])]
            assert lowers and uppers, f"{entry['rule_id']}: measured bounds are not backed by a cited exposure record"
            assert lowers[0]["subject"]["kind"] == "ISSUER" and lowers[0]["unit"] == "fraction"
            assert lowers[0]["period"]["type"] == "AS_OF" and lowers[0]["period"]["date"] == result["valuation_date"]

    if result["max_compliant"]["status"] == "SUPPORTED":
        final = evidence[result["max_compliant"]["evidence_ids"][0]]
        assert final["metric_id"] == "max_compliant_final_weight" and final["value"] == result["max_compliant"]["final_direct_weight"]
        assert final["subject"]["id"] == purchase[0] and final["formula"]


@pytest.mark.vcase("V12")
@pytest.mark.parametrize("cash, positions, rules, purchase", V12_CASES)
def test_v12_calculation_records_carry_their_path_and_fact_records_their_source(cash, positions, rules, purchase):
    """SEMANTICS 13 and evidence_record.schema.json: a CALCULATION carries a formula and its path (derived_from),
    or, when it is computed straight from a source file (coverage, share classes summed), the source id;
    a FACT cites a source or is a confirmed threshold."""
    result = check(U.portfolio(cash, positions), rules, U.request(*purchase))
    problems = []
    for record in result["evidence"]:
        if record["label"] == "CALCULATION" and not (record["formula"] and (record["derived_from"] or record["source_ids"])):
            problems.append((record["evidence_id"], "CALCULATION without a formula and a path or source"))
        if record["label"] != "CALCULATION" and record["derived_from"]:
            problems.append((record["evidence_id"], "derived_from on a non-CALCULATION record"))
        if record["label"] == "FACT" and record["metric_id"] != "rule_threshold" and not record["source_ids"]:
            problems.append((record["evidence_id"], "FACT without a source"))
        if record["calculation_version"] != result["calculation_version"]:
            problems.append((record["evidence_id"], "calculation_version differs from the result"))
    assert problems == [], problems[:6]


@pytest.mark.vcase("V12")
def test_v12_result_validator_rejects_wrong_references_units_and_tampered_verdicts():
    """The contract validator the service relies on must catch an inconsistent result document."""
    good = check(U.portfolio(0.30, V10_PORTFOLIO), [U.cap_any("cap", 0.40), U.loss_budget("budget", 0.05)], U.request("AAA", 0.25))
    assert check_result_errors(good) == []

    def broken(mutate) -> list:
        document = copy.deepcopy(good)
        mutate(document)
        return check_result_errors(document)

    def cite_missing(d): d["rule_results"][0]["evidence_ids"].append("ev-does-not-exist")
    def derive_missing(d): d["evidence"][-1]["derived_from"].append("ev-does-not-exist")
    def duplicate_id(d): d["evidence"].append(copy.deepcopy(d["evidence"][0]))
    def flip_status(d): d["rule_results"][1]["status"] = "PASS"
    def stale_headline(d): d["summary"]["headline"] = "ALL_PASS"
    def stale_counts(d): d["summary"]["counts"] = {"pass": 2, "fail": 0, "unknown": 0}
    def percent_unit(d): d["rule_results"][0]["limit"] = 40
    def inverted_bounds(d): d["rule_results"][0]["measured"] = {"lower": 0.35, "upper": 0.33}
    def unknown_with_gap(d): d["rule_results"][0].update(status="UNKNOWN", gap=0.01)

    for mutate in (cite_missing, derive_missing, duplicate_id, flip_status, stale_headline, stale_counts, percent_unit, inverted_bounds, unknown_with_gap):
        assert broken(mutate), f"validate_check_result accepted a document broken by {mutate.__name__}"


@pytest.mark.vcase("V12")
def test_v12_reason_text_states_the_engine_numbers_with_the_right_subject():
    """Template text may print percentages, but they must be the engine's own values for that rule."""
    result = check(U.portfolio(0.30, V10_PORTFOLIO), [U.cap_any("cap", 0.10), U.loss_budget("budget", 0.05)], U.request("AAA", 0.25))
    cap, budget = by_rule(result)["cap"], by_rule(result)["budget"]
    assert re.search(r"33\.00%.*35\.00%", cap["reason"]) and "10.00%" in cap["reason"]
    # The company is named by the registry name of its instrument with the smallest id (SEMANTICS 10): AAA for ALPHA.
    assert "AAA (validator synthetic)" in cap["reason"]
    assert "5.40%" in budget["reason"] and "5.00%" in budget["reason"] and "2021-12-31" in budget["reason"] and "2022-12-30" in budget["reason"]
    assert "33.00%" not in budget["reason"] and "5.40%" not in cap["reason"], "numbers must not migrate between rules"
