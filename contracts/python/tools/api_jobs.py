"""Investigation job documents used by the API fixtures (synthetic numbers, see api_results.py)."""

from __future__ import annotations

import copy
from datetime import datetime, timedelta

import api_results as ar
import engine_cases as ec
from byb_contracts.constants import INVESTIGATION_DEADLINE_SECONDS, INVESTIGATION_EXPIRY_SECONDS
from fixture_lib import controversy, exclude_sector, max_issuer, purchase

MODEL_ID = "us.anthropic.claude-sonnet-5-5"
AUTH = {"Authorization": "Bearer <access code typed by the user>"}
ROBERT_REQUEST = purchase("NVDA", 0.25, ec.ROBERT_REQUEST_WORDS)
MATEO_REQUEST = purchase("SPY", 0.15, "Buy SPY so that it is 15% of my portfolio.")
DISCLAIMER = "This is a simulation on a fictional portfolio. It is not advice, and no trade is made."


def _plus(timestamp, seconds):
    stamp = "%Y-%m-%dT%H:%M:%SZ"
    return (datetime.strptime(timestamp, stamp) + timedelta(seconds=seconds)).strftime(stamp)


def step(seq, tool, by, start, end, status, input_summary, result_summary, evidence=()):
    return {"seq": seq, "tool": tool, "initiated_by": by, "started_at": start, "finished_at": end, "status": status,
            "input_summary": input_summary, "result_summary": result_summary, "evidence_ids": list(evidence)}


def statement(statement_id, text, evidence, rendered_by="TEMPLATE"):
    return {"statement_id": statement_id, "text": text, "evidence_ids": list(evidence), "rendered_by": rendered_by}


def job(job_id, status, created, updated, key, persona, policy_id, version, request, *, resolved="same", parent=None, challenge=None,
        mode="MODEL", rounds=0, note=None, steps=(), clarification=None, result=None, explanation=(), failure=None, corrections=()):
    deadline = _plus(created, INVESTIGATION_DEADLINE_SECONDS)
    return {
        "schema_version": "1.0.0", "id": job_id, "status": status, "created_at": created, "updated_at": updated,
        "deadline_at": deadline, "expires_at": _plus(created, INVESTIGATION_EXPIRY_SECONDS), "idempotency_key": key,
        "persona_id": persona, "policy_id": policy_id, "policy_version": version, "request": request,
        "resolved_request": request if resolved == "same" else resolved, "parent_investigation_id": parent, "challenge": challenge,
        "agent": {"mode": mode, "model_id": MODEL_ID if mode == "MODEL" else None, "tool_rounds": rounds, "note": note},
        "steps": list(steps), "clarification": clarification, "result": result, "explanation": list(explanation),
        "failure": failure, "proposed_corrections": list(corrections),
    }


def robert_steps(version, minute, upto=8, running=None, cap_text="single-company limit 10.0%", verdict="0 PASS, 2 FAIL, 0 UNKNOWN",
                 max_text="Maximum compliant final direct weight 8.6% (additional purchase 8.6%); the single-company limit binds; verified by re-run."):
    t = lambda s: f"2026-11-14T15:{minute:02d}:{s:02d}Z"  # noqa: E731
    rows = [
        ("get_portfolio", "MODEL", "Persona robert.", "Fictional portfolio loaded: 5 positions, 30.0% cash, valuation date 2026-11-12.",
         ["ev-cash-start", "ev-w-spy", "ev-w-xiu", "ev-w-ry"]),
        ("get_policy", "MODEL", f"Policy pol-robert-demo, version {version}.", f"2 confirmed rules: {cap_text}; 2022 loss budget 10.0%.",
         ["ev-cap-threshold", "ev-budget-threshold"]),
        ("simulate_change", "MODEL", "NVDA to a final direct weight of 25.0%, funded from cash.", "Additional purchase 25.0%; cash after the purchase 5.0%; feasible.",
         ["ev-w-nvda-start", "ev-w-nvda-target", "ev-cash-after"]),
        ("get_holdings", "MODEL", "Funds SPY and XIU.TO.", "SPY: 8 constituents, 100.0% covered, as of 2026-11-12. XIU.TO: 4 constituents, 98.0% covered, as of 2026-11-12.",
         ["ev-spy-coverage", "ev-xiu-coverage", "ev-spy-nvda-weight"]),
        ("compute_exposure", "MODEL", "Company NVIDIA, portfolio after the purchase.", "NVIDIA: 25.0% direct + 1.2% through SPY = 26.2%; up to 26.4% counting the uncovered part of XIU.TO.",
         ["ev-nvda-via-spy", "ev-nvda-lower", "ev-nvda-upper", "ev-xiu-unattributed"]),
        ("replay_period", "MODEL", "Scenario replay_2022, portfolio after the purchase.", "Terminal return -15.25% (-6.50% before the purchase); deepest drawdown -22.35%.",
         ["ev-scn-prop-return", "ev-scn-start-return", "ev-scn-prop-dd", "ev-ret-nvda"]),
        ("check_rules", "SERVER", f"Every confirmed rule of policy version {version}.", f"2 rules evaluated: {verdict}.", ["ev-cap-gap", "ev-budget-gap"]),
        ("max_compliant_amount", "SERVER", "NVDA, cash funding, every confirmed rule.", max_text, ["ev-max-final", "ev-max-added"]),
    ]
    steps = []
    for i, (tool, by, inp, out, evidence) in enumerate(rows[:upto], start=1):
        if running == i:
            steps.append(step(i, tool, by, t(3 * i), None, "RUNNING", inp, None))
        else:
            steps.append(step(i, tool, by, t(3 * i), t(3 * i + 2), "OK", inp, out, evidence))
    return steps


def robert_job(state):
    key = "0b6f0c9e-5a7e-4c0e-9a55-1f2d3c4b5a61"
    base = dict(job_id="inv-robert-0001", created="2026-11-14T15:02:00Z", key=key, persona="robert", policy_id="pol-robert-demo", version=1, request=ROBERT_REQUEST)
    if state == "QUEUED":
        return job(status="QUEUED", updated="2026-11-14T15:02:00Z", **base)
    if state == "RUNNING":
        steps = robert_steps(1, 2, upto=5, running=5)
        return job(status="RUNNING", updated="2026-11-14T15:02:15Z", rounds=3, steps=[{**s, "evidence_ids": []} for s in steps], **base)
    result = ar.robert_result("v1")
    by_id = {r["rule_id"]: r for r in result["rule_results"]}
    explanation = [
        statement("st-1", by_id["robert-issuer-cap-1"]["reason"], by_id["robert-issuer-cap-1"]["evidence_ids"]),
        statement("st-2", by_id["robert-loss-budget-1"]["reason"], by_id["robert-loss-budget-1"]["evidence_ids"]),
        statement("st-3", result["max_compliant"]["reason"], result["max_compliant"]["evidence_ids"]),
        statement("st-4", "You asked for NVIDIA at 25% of the portfolio. Your stated goal, to preserve capital while keeping some growth potential, is qualitative and is "
                  "not scored. What can be measured is concentration: the purchase would make NVIDIA your largest single-company exposure, at 26.2% to 26.4% of the "
                  "portfolio, where the largest one today is 5.8% to 6.0%.",
                  ["ev-w-nvda-target", "ev-nvda-lower", "ev-nvda-upper", "ev-ry-lower-start", "ev-ry-upper-start"], "MODEL_VALIDATED"),
        statement("st-5", DISCLAIMER, []),
    ]
    return job(status="SUCCEEDED", updated="2026-11-14T15:02:27Z", rounds=4, steps=robert_steps(1, 2), result=result, explanation=explanation, **base)


def change_rule_challenge():
    return {"challenge_id": "ch-robert-0001", "investigation_id": "inv-robert-0001", "type": "CHANGE_RULE",
            "payload": {"rule_id": "robert-issuer-cap-1", "new_threshold": 0.30, "user_note": "Raise my single-company limit to 30%."},
            "created_at": "2026-11-14T15:06:00Z"}


def robert_job_after_challenge():
    result = ar.robert_result("v2")
    by_id = {r["rule_id"]: r for r in result["rule_results"]}
    explanation = [
        statement("st-1", by_id["robert-issuer-cap-2"]["reason"], by_id["robert-issuer-cap-2"]["evidence_ids"]),
        statement("st-2", by_id["robert-loss-budget-1"]["reason"], by_id["robert-loss-budget-1"]["evidence_ids"]),
        statement("st-3", result["max_compliant"]["reason"], result["max_compliant"]["evidence_ids"]),
        statement("st-4", "Raising the single-company limit to 30% makes this purchase pass that rule. The 2022 loss budget, which you confirmed separately, still fails: "
                  "the replayed loss is 15.25% against a budget of 10.0%, a gap of 5.25 percentage points. That is one of your rules failing, not a contradiction "
                  "between your rules. Your earlier policy version and its report are unchanged.",
                  ["ev-cap-threshold", "ev-cap-gap", "ev-scn-prop-loss", "ev-budget-threshold", "ev-budget-gap"], "MODEL_VALIDATED"),
        statement("st-5", DISCLAIMER, []),
    ]
    steps = robert_steps(2, 6, cap_text="single-company limit 30.0% (replaces the 10.0% limit)", verdict="1 PASS, 1 FAIL, 0 UNKNOWN",
                         max_text="Maximum compliant final direct weight 10.0% (additional purchase 10.0%); the 2022 loss budget binds; verified by re-run.")
    return job("inv-robert-0002", "SUCCEEDED", "2026-11-14T15:06:00Z", "2026-11-14T15:06:27Z", "7d1e2f3a-4b5c-4d6e-8f70-91a2b3c4d5e6", "robert",
               "pol-robert-demo", 2, ROBERT_REQUEST, parent="inv-robert-0001", challenge=change_rule_challenge(), rounds=4,
               steps=steps, result=result, explanation=explanation)


def correct_fact_challenge():
    return {"challenge_id": "ch-robert-0002", "investigation_id": "inv-robert-0001", "type": "CORRECT_FACT",
            "payload": {"evidence_id": "ev-spy-nvda-weight", "asserted_value": 0.08, "asserted_unit": "fraction",
                        "user_note": "The fund fact sheet I have shows a higher NVIDIA weight in SPY.",
                        "user_source": "SPY fact sheet, user's own copy (not retrieved by the system)"},
            "created_at": "2026-11-14T15:09:00Z"}


def proposed_correction():
    payload = correct_fact_challenge()["payload"]
    return {
        "correction_id": "corr-robert-0001", "challenge_id": "ch-robert-0002", "investigation_id": "inv-robert-0001",
        "evidence_id": payload["evidence_id"], "original_value": 0.06, "original_unit": "fraction",
        "asserted_value": payload["asserted_value"], "asserted_unit": payload["asserted_unit"],
        "provenance": {"asserted_by": "USER", "asserted_at": "2026-11-14T15:09:00Z", "user_note": payload["user_note"], "user_source": payload["user_source"]},
        "status": "UNVERIFIED", "applied_to_calculation": False,
    }


def robert_job_with_correction():
    document = robert_job("SUCCEEDED")
    document["proposed_corrections"] = [proposed_correction()]
    return document


def failed_job():
    t = "2026-11-14T15:20:"
    steps = [
        step(1, "get_portfolio", "MODEL", t + "03Z", t + "05Z", "OK", "Persona robert.", "Fictional portfolio loaded: 5 positions, 30.0% cash, valuation date 2026-11-12."),
        step(2, "get_holdings", "MODEL", t + "06Z", t + "09Z", "ERROR", "Funds SPY and XIU.TO.", "The holdings snapshot could not be read from storage."),
    ]
    return job("inv-failed-0001", "FAILED", t + "00Z", t + "10Z", "c3d4e5f6-0718-4293-a4b5-c6d7e8f90a1b", "robert", "pol-robert-demo", 1, ROBERT_REQUEST,
               rounds=1, steps=steps,
               failure={"code": "DATA_UNAVAILABLE", "message": "The holdings snapshot could not be read, so no check was run and no result was produced. Nothing was assumed in its place.",
                        "retryable": True})


def mateo_job():
    result = ar.mateo_result()
    by_id = {r["rule_id"]: r for r in result["rule_results"]}
    t = lambda s: f"2026-11-14T15:12:{s:02d}Z"  # noqa: E731
    rows = [
        ("get_portfolio", "MODEL", "Persona mateo.", "Fictional portfolio loaded: 6 positions, 25.0% cash, valuation date 2026-11-12.", ["ev-cash-start", "ev-w-xiu", "ev-w-esgv"]),
        ("get_policy", "MODEL", "Policy pol-mateo-demo, version 1.", "2 confirmed rules: Energy-label exclusion with tolerance 0.0%; controversy exclusion with tolerance 0.0%.",
         ["ev-energy-threshold", "ev-controversy-threshold"]),
        ("simulate_change", "MODEL", "SPY to a final direct weight of 15.0%, funded from cash.", "Additional purchase 15.0%; cash after the purchase 10.0%; feasible.",
         ["ev-w-spy-start", "ev-w-spy-target", "ev-cash-after"]),
        ("get_holdings", "MODEL", "Funds XIU.TO, ESGV and SPY.", "XIU.TO: 98.0% covered, as of 2026-11-12. SPY: 100.0% covered, as of 2026-11-12. ESGV: no holdings file held; treated as unknown, not as zero.",
         ["ev-xiu-coverage", "ev-esgv-unattributed", "ev-xiu-unattributed"]),
        ("compute_exposure", "MODEL", "Holdings labelled Energy, portfolio before and after the purchase.", "Energy label: 1.4% to 16.8% before the purchase; 1.7% to 17.1% after it.",
         ["ev-energy-lower-start", "ev-energy-upper-start", "ev-energy-lower", "ev-energy-upper"]),
        ("lookup_controversy_evidence", "MODEL", "Every company held directly or through XIU.TO and SPY.", "No registry record for any held company. The registry researched none of them: not assessed.",
         ["ev-controversy-lower", "ev-controversy-upper"]),
        ("check_rules", "SERVER", "Every confirmed rule of policy version 1.", "2 rules evaluated: 0 PASS, 1 FAIL, 1 UNKNOWN. 1 rule was already breached before the purchase.",
         ["ev-energy-gap", "ev-controversy-upper"]),
        ("max_compliant_amount", "SERVER", "SPY, cash funding, every confirmed rule.", "No feasible purchase: the Energy-label exclusion is already breached by the starting portfolio.",
         ["ev-energy-lower-start", "ev-energy-threshold"]),
    ]
    steps = [step(i, tool, by, t(3 * i), t(3 * i + 2), "OK", inp, out, evidence) for i, (tool, by, inp, out, evidence) in enumerate(rows, start=1)]
    finding = result["starting_portfolio_findings"][0]
    explanation = [
        statement("st-1", finding["reason"], finding["evidence_ids"]),
        statement("st-2", by_id["mateo-excl-energy-1"]["reason"], by_id["mateo-excl-energy-1"]["evidence_ids"]),
        statement("st-3", by_id["mateo-controversy-1"]["reason"], by_id["mateo-controversy-1"]["evidence_ids"]),
        statement("st-4", result["max_compliant"]["reason"], result["max_compliant"]["evidence_ids"]),
        statement("st-5", "The Energy label is the sector reported in each fund's holdings file. It is not a list of oil producers and it says nothing about controversies.", []),
        statement("st-6", DISCLAIMER, []),
    ]
    return job("inv-mateo-0001", "SUCCEEDED", "2026-11-14T15:12:00Z", "2026-11-14T15:12:27Z", "e5f60718-2930-4a4b-8c5d-6e7f8091a2b3", "mateo",
               "pol-mateo-demo", 1, MATEO_REQUEST, rounds=5, steps=steps, result=result, explanation=explanation)


def amira_clarification_job():
    request = {"instrument_id": None, "target_direct_weight": None, "funding": "CASH", "original_words": "Add 5% Nvidia."}
    clarification = {
        "clarification_id": "clar-amira-0001", "about_words": "Add 5%",
        "question": "NVDA is 10.0% of the portfolio today. What should 'add 5%' mean?",
        "options": [
            {"option_id": "add-five-points", "label": "Add 5 percentage points: NVDA becomes 15.0% of the portfolio",
             "description": "Final direct weight 0.15, an additional purchase of 0.05 funded from cash.", "supported": True,
             "proposed_rule": None, "purchase_request": purchase("NVDA", 0.15, "Add 5% Nvidia.")},
            {"option_id": "final-five", "label": "Make NVDA 5.0% of the portfolio",
             "description": "Not supported: this is below the current 10.0% and would require selling. Only cash-funded purchases are simulated.",
             "supported": False, "proposed_rule": None, "purchase_request": None},
        ],
    }
    steps = [step(1, "get_portfolio", "MODEL", "2026-11-14T15:30:03Z", "2026-11-14T15:30:05Z", "OK", "Persona amira.",
                  "Fictional portfolio loaded: 8 positions, 10.0% cash, valuation date 2026-11-12. NVDA direct weight 10.0%.")]
    return job("inv-amira-0001", "SUCCEEDED", "2026-11-14T15:30:00Z", "2026-11-14T15:30:08Z", "f6071829-3a4b-4c5d-9e6f-708192a3b4c5", "amira",
               "pol-amira-demo", 1, request, resolved=None, rounds=1, steps=steps, clarification=clarification)


def mateo_interpretation():
    words = ec.MATEO_OBJECTIVE["original_words"]
    draft = dict(status="PROPOSED", origin="SYSTEM_PROPOSED", objective_id="obj-3")
    return {
        "schema_version": "1.0.0", "interpretation_id": "int-mateo-0001", "persona_id": "mateo", "created_at": "2026-11-14T15:10:00Z",
        "model_id": MODEL_ID, "original_words": words,
        "objectives": [
            {"objective_id": "obj-1", "original_words": "Balanced growth over 8 to 12 years", "kind": "goal", "source": "USER_STATED", "case_reference": None},
            {"objective_id": "obj-2", "original_words": "ESG matters to me", "kind": "preference", "source": "USER_STATED", "case_reference": None},
            {"objective_id": "obj-3", "original_words": "I want to avoid oil and companies involved in significant controversies", "kind": "constraint",
             "source": "USER_STATED", "case_reference": None},
        ],
        "proposed_rules": [controversy("draft-controversy-1", None, ec.MATEO_NATURES, words="companies involved in significant controversies", **draft)],
        "unsupported": [],
        "clarifications": [{
            "clarification_id": "clar-oil-1", "about_words": "oil",
            "question": "What should 'avoid oil' cover? Only definitions we hold sourced data for can be checked.",
            "options": [
                {"option_id": "energy-sector-label", "label": "Holdings labelled Energy in what the funds report",
                 "description": "Uses the sector label in each fund issuer's holdings file (and the registry label for direct holdings). Broader than oil: it also covers pipelines and gas.",
                 "supported": True, "purchase_request": None,
                 "proposed_rule": exclude_sector("draft-excl-energy-1", None, "Energy", words="avoid oil", **draft)},
                {"option_id": "named-companies", "label": "Specific companies that I name",
                 "description": "Supported once you name them: type the companies in a new sentence and a named-company exclusion will be drafted.",
                 "supported": True, "proposed_rule": None, "purchase_request": None},
                {"option_id": "oil-producers", "label": "Companies that produce oil",
                 "description": "Not supported yet: we hold no sourced classification of oil producers, so this cannot be checked honestly.",
                 "supported": False, "proposed_rule": None, "purchase_request": None},
                {"option_id": "fossil-fuels", "label": "All fossil fuels",
                 "description": "Not supported yet: we hold no sourced fossil-fuel classification.",
                 "supported": False, "proposed_rule": None, "purchase_request": None},
            ],
        }],
    }


def amira_interpretation():
    words = "I want maximum growth and strict diversification."
    return {
        "schema_version": "1.0.0", "interpretation_id": "int-amira-0001", "persona_id": "amira", "created_at": "2026-11-14T15:28:00Z",
        "model_id": MODEL_ID, "original_words": words,
        "objectives": [
            {"objective_id": "obj-1", "original_words": "maximum growth", "kind": "goal", "source": "USER_STATED", "case_reference": None},
            {"objective_id": "obj-2", "original_words": "strict diversification", "kind": "preference", "source": "USER_STATED", "case_reference": None},
        ],
        "proposed_rules": [],
        "unsupported": [{"words": "maximum growth", "code": "UNSUPPORTED_RULE_TYPE",
                         "reason": "No rule type measures growth, and the tool does not forecast returns. It is kept as a qualitative objective."}],
        "clarifications": [{
            "clarification_id": "clar-diversification-1", "about_words": "strict diversification",
            "question": "The two wishes can pull in different directions, but that is not a proven contradiction. What should 'strict diversification' mean as a rule you can check?",
            "options": [
                {"option_id": "single-company-cap", "label": "A maximum share of the portfolio in any single company",
                 "description": "Counts direct holdings and holdings through equity funds. You choose the number.", "supported": True, "purchase_request": None,
                 "proposed_rule": max_issuer("draft-issuer-cap-1", None, status="PROPOSED", origin="SYSTEM_PROPOSED", objective_id="obj-2", words="strict diversification")},
                {"option_id": "sector-cap", "label": "A maximum share in any single sector",
                 "description": "Not supported yet: there is no sector-cap rule type in this version.", "supported": False, "proposed_rule": None, "purchase_request": None},
                {"option_id": "keep-qualitative", "label": "Keep it as a qualitative preference only",
                 "description": "Nothing will be checked numerically for it; it stays visible as context.", "supported": True, "proposed_rule": None, "purchase_request": None},
            ],
        }],
    }


def mateo_clarified_interpretation():
    words = "By oil I meant companies that produce oil, not pipelines or utilities."
    first = copy.deepcopy(mateo_interpretation()["clarifications"][0])
    first.update({"clarification_id": "clar-oil-2", "about_words": "companies that produce oil",
                  "question": "We cannot check 'companies that produce oil' yet. Which supported definition should stand in for it, if any?"})
    first["options"] = [o for o in first["options"] if o["option_id"] in ("energy-sector-label", "named-companies")]
    for option in first["options"]:
        if option["proposed_rule"]:
            option["proposed_rule"]["original_words"] = "companies that produce oil"
            option["proposed_rule"]["objective_id"] = None
            option["proposed_rule"]["rule_id"] = "draft-excl-energy-2"
    return {
        "schema_version": "1.0.0", "interpretation_id": "int-mateo-0002", "persona_id": "mateo", "created_at": "2026-11-14T15:16:00Z",
        "model_id": MODEL_ID, "original_words": words, "objectives": [], "proposed_rules": [],
        "unsupported": [{"words": "companies that produce oil", "code": "UNSUPPORTED_DEFINITION",
                         "reason": "We hold no sourced classification of oil producers. The confirmed Energy-label rule stays as it is until you confirm a change."}],
        "clarifications": [first],
    }
