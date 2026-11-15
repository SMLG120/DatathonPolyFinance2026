"""API example bodies: one envelope per file in contracts/fixtures/api (see fixture.schema.json#/$defs/api_fixture).

Every numeric result here comes from the hand-entered engine expectations in
engine_cases.py (HAND_CALCS.md R1, R2, M1, M2), completed by api_results.py.
"""

from __future__ import annotations

import api_jobs as aj
import api_results as ar
import engine_cases as ec
import scenario_defs as sd
from fixture_lib import instrument, max_issuer

SYNTHETIC = (
    "SYNTHETIC: the fund constituent weights, fund coverage, 2022 prices and FX rates behind the numbers in this body are "
    "invented (contracts/fixtures/engine/robert_synthetic_universe.json and mateo_synthetic_universe.json) so that every "
    "figure can be checked by hand in contracts/fixtures/engine/HAND_CALCS.md. They are NOT the real holdings or prices of "
    "SPY, XIU.TO, NVDA or any other instrument. Controversy records cited here are synthetic fixture records, not sources. "
    "Portfolio weights and thresholds are fictional-scenario values."
)
NO_MARKET_NUMBERS = (
    "No market or fund numbers in this body. Portfolio weights and thresholds, where present, are fictional-scenario values "
    "invented by the team; persona facts quote the official case."
)
JSON_HEADERS = {**aj.AUTH, "Content-Type": "application/json"}
STARTER = "starter_assets_universe"


def fx(fixture_id, route, status, schema, body, description, *, request=None, headers=None, synthetic=True):
    return {
        "fixture": True, "fixture_id": fixture_id, "synthetic": synthetic,
        "synthetic_note": SYNTHETIC if synthetic else NO_MARKET_NUMBERS, "description": description,
        "route": route, "http_status": status,
        "request_headers": dict(headers if headers is not None else (JSON_HEADERS if request is not None else aj.AUTH)),
        "request_body": request, "response_schema": schema, "response_body": body,
    }


def accepted(job):
    return {"schema_version": "1.0.0", "id": job["id"], "status": "QUEUED", "created_at": job["created_at"],
            "deadline_at": job["deadline_at"], "expires_at": job["expires_at"],
            "poll": {"path": f"/investigations/{job['id']}", "interval_ms": 1500}}


def error(code, message, details=(), request_id="req-fixture-0001"):
    return {"error": {"code": code, "message": message, "details": [{"path": p, "issue": i} for p, i in details], "request_id": request_id}}


def portfolio_response():
    entries = [
        instrument("XBB.TO", "XBB.TO", "iShares Core Canadian Universe Bond Index ETF", "etf_bond", "CAD", "Bonds (Canada aggregate)", STARTER),
        instrument("SPY", "SPY", "SPDR S&P 500 ETF Trust", "etf_equity", "USD", "Broad market (U.S.)", STARTER),
        instrument("XIU.TO", "XIU.TO", "iShares S&P/TSX 60 Index ETF", "etf_equity", "CAD", "Broad market (Canada)", STARTER),
        instrument("RY.TO", "ROYAL_BANK_OF_CANADA", "Royal Bank of Canada", "equity", "CAD", "Financials", STARTER),
        instrument("JNJ", "JOHNSON_AND_JOHNSON", "Johnson & Johnson", "equity", "USD", "Health Care", STARTER),
        instrument("NVDA", "NVIDIA", "NVIDIA", "equity", "USD", "Information Technology", STARTER),
    ]
    return {"schema_version": "1.0.0", "scenario": sd.robert(), "instruments": {e["instrument_id"]: e for e in entries},
            "purchasable_instrument_ids": ["JNJ", "NVDA", "RY.TO", "SPY", "XBB.TO", "XIU.TO"]}


def amira_portfolio_response():
    """GET /portfolios/amira, abbreviated like Robert's to her positions. Labels are the committed starter-kit registry labels."""
    entries = [
        instrument("SPY", "SPY", "SPDR S&P 500 ETF Trust", "etf_equity", "USD", "Broad market (U.S.)", STARTER),
        instrument("XIU.TO", "XIU.TO", "iShares S&P/TSX 60 Index ETF", "etf_equity", "CAD", "Broad market (Canada)", STARTER),
        instrument("NVDA", "NVIDIA", "NVIDIA", "equity", "USD", "Information Technology", STARTER),
        instrument("MSFT", "MICROSOFT", "Microsoft", "equity", "USD", "Information Technology", STARTER),
        instrument("SHOP.TO", "SHOPIFY", "Shopify", "equity", "CAD", "Information Technology", STARTER),
        instrument("JPM", "JPMORGAN_CHASE", "JPMorgan Chase", "equity", "USD", "Financials", STARTER),
        instrument("BTC-USD", "BTC-USD", "Bitcoin", "crypto", "USD", "Crypto asset", STARTER),
        instrument("ETH-USD", "ETH-USD", "Ether", "crypto", "USD", "Crypto asset", STARTER),
    ]
    return {"schema_version": "1.0.0", "scenario": sd.amira(), "instruments": {e["instrument_id"]: e for e in entries},
            "purchasable_instrument_ids": sorted(e["instrument_id"] for e in entries)}


def all_fixtures():
    robert_scn = sd.robert()
    create_robert = {"persona_id": "robert", "policy_id": "pol-robert-demo", "policy_version": 1, "request": aj.ROBERT_REQUEST, "parent_investigation_id": None}
    queued = aj.robert_job("QUEUED")
    child = aj.robert_job_after_challenge()
    change = aj.change_rule_challenge()
    fact = aj.correct_fact_challenge()
    clarify = {"challenge_id": "ch-mateo-0001", "investigation_id": "inv-mateo-0001", "type": "CLARIFY_PREFERENCE",
               "payload": sd.mateo()["demo_challenge"]["payload"], "created_at": "2026-11-14T15:16:00Z"}
    draft_cap = max_issuer("robert-issuer-cap-1", 0.20, status="PROPOSED", origin="USER_STATED", threshold_source="USER_ENTERED",
                           words="What if my single-company limit were 20%?", objective_id="obj-robert-1")
    mateo_draft_cap = max_issuer(ec.MATEO_CAP_RULE_ID, 0.20, status="PROPOSED", origin="USER_STATED", threshold_source="USER_ENTERED",
                                 words=ec.MATEO_CAP_WORDS)
    key = lambda job: {**JSON_HEADERS, "Idempotency-Key": job["idempotency_key"]}  # noqa: E731
    get = "GET /investigations/{id}"
    challenge_route = "POST /investigations/{id}/challenge"
    return [
        fx("portfolio_robert", "GET /portfolios/{persona_id}", 200, "api.schema.json#/$defs/portfolio_response", portfolio_response(),
           "GET /portfolios/robert. The fictional scenario plus registry entries. `instruments` is abbreviated here to Robert's positions and NVDA; "
           "the deployed response lists every purchasable instrument. Sector labels are the starter-kit registry labels.", synthetic=False),
        fx("portfolio_amira", "GET /portfolios/{persona_id}", 200, "api.schema.json#/$defs/portfolio_response", amira_portfolio_response(),
           "GET /portfolios/amira. The fictional scenario plus registry entries, abbreviated like portfolio_robert to her positions; "
           "the deployed response lists every purchasable instrument. Sector labels are the starter-kit registry labels. "
           "Crypto assets carry equity_scope false, so company-exposure rules do not assess them.", synthetic=False),
        fx("interpret_mateo_clarification", "POST /rules/interpret", 200, "interpretation.schema.json", aj.mateo_interpretation(),
           "Mateo's sentence. 'oil' is ambiguous, so the interpreter asks a question whose options carry the drafts they lead to. "
           "The drafts are SYSTEM_PROPOSED structures with a null threshold: no number is invented.",
           request={"persona_id": "mateo", "text": ec.MATEO_OBJECTIVE["original_words"], "policy_id": None, "policy_version": None}, synthetic=False),
        fx("interpret_amira_ambiguous", "POST /rules/interpret", 200, "interpretation.schema.json", aj.amira_interpretation(),
           "Ambiguous language ('maximum growth and strict diversification') yields a clarification question, never a contradiction verdict.",
           request={"persona_id": "amira", "text": "I want maximum growth and strict diversification.", "policy_id": None, "policy_version": None}, synthetic=False),
        fx("confirm_robert_v1", "POST /rules/confirm", 201, "api.schema.json#/$defs/confirm_response",
           {"schema_version": "1.0.0", "policy": ec.robert_policy_v1()},
           "Robert accepts both fictional-scenario rules with their scenario numbers unchanged: policy version 1 is created. "
           "The rules keep origin FICTIONAL_SCENARIO because the numbers were accepted as offered.",
           request={"persona_id": "robert", "policy_id": None, "base_version": None, "objectives": robert_scn["objectives"],
                    "confirmations": [{"rule": r, "threshold": r["threshold"]} for r in robert_scn["scenario_rules"]],
                    "withdraw_rule_ids": [], "change_note": "Fictional-scenario rules confirmed by the user."}, synthetic=False),
        fx("check_robert_preview", "POST /check", 200, "check_result.schema.json", ar.robert_result("preview"),
           "Slider preview: the single-company limit is a DRAFT at 0.20, the loss budget is the confirmed rule. preview is true, policy_id and "
           "policy_version are null in the result and the stored policy is not modified. HAND_CALCS.md R1 with the cap limit changed to 0.20.",
           request={"persona_id": "robert", "policy_id": "pol-robert-demo", "policy_version": 1, "purchase_request": aj.ROBERT_REQUEST,
                    "draft_rules": [draft_cap, ec.robert_rules_v1()[1]]}),
        fx("check_mateo_preview_unknown", "POST /check", 200, "check_result.schema.json", ar.mateo_cap_preview_result(),
           "A rule whose status is UNKNOWN. Preview of one draft rule on Mateo's portfolio (no single company above 0.20): the known exposure "
           "is below the limit, but ESGV has no holdings file, so the upper bound is above it. Neither PASS nor FAIL; headline "
           "NO_FAIL_BUT_UNKNOWN; the maximum compliant weight is WITHHELD. No policy context is sent, so goal_context is empty. HAND_CALCS.md M2.",
           request={"persona_id": "mateo", "policy_id": None, "policy_version": None, "purchase_request": aj.MATEO_REQUEST,
                    "draft_rules": [mateo_draft_cap]}),
        fx("check_invalid_request", "POST /check", 200, "check_result.schema.json", ar.invalid_request_result(),
           "A well-formed request the engine cannot execute (the target is below the current direct weight, which would mean selling). "
           "HTTP 200 with execution.status INVALID_REQUEST: no rule is evaluated and nothing is defaulted.",
           request={"persona_id": "robert", "policy_id": "pol-robert-demo", "policy_version": 1,
                    "purchase_request": ar.INVALID_REQUEST, "draft_rules": None}, synthetic=False),
        fx("investigation_accepted", "POST /investigations", 202, "api.schema.json#/$defs/investigation_accepted", accepted(queued),
           "Robert's investigation is accepted. The response is returned before any model call; the client polls poll.path.",
           request=create_robert, headers=key(queued), synthetic=False),
        fx("investigation_robert_queued", get, 200, "investigation_job.schema.json", queued,
           "GET /investigations/inv-robert-0001 immediately after creation.", synthetic=False),
        fx("investigation_robert_running", get, 200, "investigation_job.schema.json", aj.robert_job("RUNNING"),
           "Partial timeline: four finished tool steps and one RUNNING. No result, no explanation and no evidence ids until the job is terminal."),
        fx("investigation_robert_succeeded", get, 200, "investigation_job.schema.json", aj.robert_job("SUCCEEDED"),
           "Robert, policy version 1: both rules FAIL, with the maximum compliant final weight. HAND_CALCS.md R1."),
        fx("challenge_change_rule", challenge_route, 202, "api.schema.json#/$defs/challenge_response",
           {"schema_version": "1.0.0", "challenge": change, "proposed_correction": None, "interpretation": None,
            "policy": ec.robert_policy_v2(), "investigation": accepted(child)},
           "POST /investigations/inv-robert-0001/challenge. Robert raises the single-company limit to 0.30: policy version 2 is created (the old "
           "rule stays in it as SUPERSEDED) and a child investigation is queued. Version 1 and its report are unchanged.",
           request={"type": "CHANGE_RULE", "payload": change["payload"]}, headers=key(child), synthetic=False),
        fx("investigation_robert_after_challenge_succeeded", get, 200, "investigation_job.schema.json", child,
           "The child investigation on policy version 2: the single-company rule passes, the 2022 loss budget still fails with measured loss, "
           "budget and gap. HAND_CALCS.md R2."),
        fx("challenge_correct_fact", challenge_route, 201, "api.schema.json#/$defs/challenge_response",
           {"schema_version": "1.0.0", "challenge": fact, "proposed_correction": aj.proposed_correction(), "interpretation": None,
            "policy": None, "investigation": None},
           "POST /investigations/inv-robert-0001/challenge. A disputed fact becomes an UNVERIFIED proposed correction with provenance. "
           "It is not applied to any calculation and the disputed evidence record is untouched.",
           request={"type": "CORRECT_FACT", "payload": fact["payload"]}),
        fx("investigation_robert_with_correction", get, 200, "investigation_job.schema.json", aj.robert_job_with_correction(),
           "The same finished investigation after the CORRECT_FACT challenge: result and evidence are identical; the correction is appended "
           "to proposed_corrections."),
        fx("challenge_clarify_preference", challenge_route, 200, "api.schema.json#/$defs/challenge_response",
           {"schema_version": "1.0.0", "challenge": clarify, "proposed_correction": None, "interpretation": aj.mateo_clarified_interpretation(),
            "policy": None, "investigation": None},
           "POST /investigations/inv-mateo-0001/challenge. Mateo clarifies 'oil'. The reply is a fresh draft interpretation; 'companies that "
           "produce oil' is reported as an unsupported definition and no stored rule changes.",
           request={"type": "CLARIFY_PREFERENCE", "payload": clarify["payload"]}, synthetic=False),
        fx("investigation_mateo_succeeded", get, 200, "investigation_job.schema.json", aj.mateo_job(),
           "Mateo: both rules are already breached by the STARTING portfolio through XIU.TO (two starting-portfolio findings). The purchase is "
           "proven to add Exxon Mobil to the controversy rule; what it adds to the Energy-label rule is unresolved (0 proven, up to 0.15 "
           "possible) because the SPY rows carry no sector label. ESGV has no holdings file (coverage MISSING). HAND_CALCS.md M1."),
        fx("investigation_amira_clarification", get, 200, "investigation_job.schema.json", aj.amira_clarification_job(),
           "A free-text request ('Add 5% Nvidia.') that is ambiguous: the job SUCCEEDS with a clarification and no result. The client answers "
           "by posting a new investigation with the chosen option's purchase_request and parent_investigation_id.", synthetic=False),
        fx("investigation_failed", get, 200, "investigation_job.schema.json", aj.failed_job(),
           "A FAILED job: a tool step errored, so there is no result and nothing was assumed in its place.", synthetic=False),
        fx("error_validation", "POST /check", 400, "api.schema.json#/$defs/error_response",
           error("VALIDATION_ERROR", "The request body does not match the contract.",
                 [("purchase_request.target_direct_weight", "expected a number (a fraction such as 0.25), got the string '25%'"),
                  ("draft_rules", "required property is missing (send null to evaluate the stored policy)")]),
           "A malformed body is rejected before the engine runs.",
           request={"persona_id": "robert", "policy_id": "pol-robert-demo", "policy_version": 1,
                    "purchase_request": {"instrument_id": "NVDA", "target_direct_weight": "25%", "funding": "CASH", "original_words": None}},
           synthetic=False),
        fx("error_unauthorized", "GET /portfolios/{persona_id}", 401, "api.schema.json#/$defs/error_response",
           error("UNAUTHORIZED", "Missing or wrong access code."), "Any route without a valid Authorization header.",
           headers={}, synthetic=False),
        fx("error_not_found", get, 404, "api.schema.json#/$defs/error_response",
           error("NOT_FOUND", "No investigation with this id."), "GET /investigations/inv-does-not-exist.", synthetic=False),
        fx("error_policy_version_conflict", "POST /rules/confirm", 409, "api.schema.json#/$defs/error_response",
           error("POLICY_VERSION_CONFLICT", "The policy has a newer version than the one this confirmation was based on. Reload it and confirm again.",
                 [("base_version", "is 1; the latest version of pol-robert-demo is 2")]),
           "base_version is not the latest version of the policy; nothing is stored.",
           request={"persona_id": "robert", "policy_id": "pol-robert-demo", "base_version": 1, "objectives": robert_scn["objectives"],
                    "confirmations": [], "withdraw_rule_ids": ["robert-loss-budget-1"], "change_note": "Drop the loss budget."}, synthetic=False),
        fx("error_interpreter_timeout", "POST /rules/interpret", 504, "api.schema.json#/$defs/error_response",
           error("INTERPRETER_TIMEOUT", "The interpreter did not answer in time. Nothing was changed. Try again, or enter the rule with the form."),
           "The model call exceeded the server-side timeout. The structured error lets the UI fall back to the manual rule form.",
           request={"persona_id": "robert", "text": ec.ROBERT_OBJECTIVE["original_words"], "policy_id": None, "policy_version": None}, synthetic=False),
    ]
