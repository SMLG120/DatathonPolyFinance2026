"""The three fictional persona scenarios (contracts/scenarios/*.json).

Persona facts quote the official case with a page reference. Portfolios,
objective wording, thresholds and scripted requests are invented by the team
(LEAD_DECISIONS D7) and flagged FICTIONAL_SCENARIO.
"""

from __future__ import annotations

from engine_cases import (
    MATEO_NATURES, MATEO_OBJECTIVE, MATEO_PORTFOLIO, ROBERT_BUDGET_WORDS, ROBERT_CAP_WORDS, ROBERT_OBJECTIVE,
    ROBERT_PORTFOLIO, ROBERT_REQUEST_WORDS,
)
from fixture_lib import controversy, exclude_sector, loss_budget, max_issuer, min_issuer, objective, portfolio, purchase

NOTICE = (
    "Fictional simulation. The persona facts come from the official case (page references given). The portfolio, the "
    "objective wording, every threshold and every scripted request were invented by the team for the demonstration; "
    "the case gives the personas no numbers. Nothing here is advice, a recommendation or a real account."
)
P = dict(status="PROPOSED", origin="FICTIONAL_SCENARIO")


def fact(fact_id, label, text, page):
    return {"fact_id": fact_id, "label": label, "text": text, "case_reference": page}


def step(seq, stage, description):
    return {"seq": seq, "stage": stage, "description": description}


def scenario(persona, pf, objectives, rules, alternatives, phrases, requests, challenge, steps):
    return {
        "schema_version": "1.0.0", "fictional": True, "fiction_notice": NOTICE, "persona": persona,
        "portfolio": pf, "objectives": objectives, "scenario_rules": rules, "alternative_rule_sets": alternatives,
        "demo_phrases": phrases, "demo_requests": requests, "demo_challenge": challenge, "demo_steps": steps,
    }


def robert():
    persona = {
        "persona_id": "robert", "display_name": "Robert", "case_reference": "Case p.7",
        "facts": [
            fact("age_occupation", "Age and occupation", "59 years old, healthcare professional", "Case p.7"),
            fact("profile", "Profile", "Married, adult children, considering retirement in the next few years; advanced investment experience.", "Case p.7"),
            fact("objective", "Investment objective", "He wants to preserve capital while maintaining some growth potential.", "Case p.7"),
            fact("preference_established", "Preference", "Prefers established companies and investments whose business models he understands.", "Case p.7"),
            fact("preference_stability", "Preference", "Values stability and company quality and has little interest in crypto assets.", "Case p.7"),
            fact("temptation", "Constraint", "May be tempted by a highly publicized company even when it is riskier than he would normally prefer.", "Case p.7"),
            fact("horizon", "Investment horizon", "3-5 years", "Case p.7"),
            fact("risk_profile", "Risk profile", "Low to moderate", "Case p.7"),
        ],
        "what_this_persona_tests": {
            "text": "Can the system challenge a request that conflicts with the investor's profile? It should identify the tension between Robert's immediate interest and his objectives, explain the risks, and avoid simply agreeing.",
            "case_reference": "Case p.7",
        },
    }
    rules = [
        max_issuer("robert-issuer-cap-1", 0.10, words=ROBERT_CAP_WORDS, objective_id="obj-robert-1", **P),
        loss_budget("robert-loss-budget-1", 0.10, words=ROBERT_BUDGET_WORDS, objective_id="obj-robert-1", **P),
    ]
    return scenario(
        persona, portfolio("pf-robert-fictional-1", "robert", ROBERT_PORTFOLIO["cash"], ROBERT_PORTFOLIO["positions"]),
        [ROBERT_OBJECTIVE], rules, [],
        [{"phrase_id": "robert-objective", "original_words": ROBERT_OBJECTIVE["original_words"], "expected_outcome": "PROPOSED_RULES",
          "note": "A goal with no number. A correct interpreter stores the objective and may draft rule structures with a null threshold; it must not invent 10% or any other number."}],
        [{"request_id": "robert-nvda-25", "label": "Make NVDA 25% of the portfolio (final direct weight), funded from cash",
          "purchase_request": purchase("NVDA", 0.25, ROBERT_REQUEST_WORDS)}],
        {"label": "Robert raises the single-company limit to 30%", "type": "CHANGE_RULE",
         "payload": {"rule_id": "robert-issuer-cap-1", "new_threshold": 0.30, "user_note": "Raise my single-company limit to 30%."}},
        [
            step(1, "PERSONA_PORTFOLIO", "Load Robert and his fictional portfolio (30% cash, 30% XBB.TO, 20% SPY, 10% XIU.TO, 5% RY.TO, 5% JNJ)."),
            step(2, "GOALS_RULES", "Show the objective in his words and the two fictional-scenario rules as proposals; the user confirms them (policy version 1)."),
            step(3, "PROPOSED_PURCHASE", "Request NVDA at a final direct weight of 0.25, funded from cash."),
            step(4, "INVESTIGATION", "Run the investigation; the timeline shows the real tool calls."),
            step(5, "VERDICT_EVIDENCE", "Issuer cap FAIL with direct and look-through exposure; 2022 loss budget result; maximum compliant final weight."),
            step(6, "CHALLENGE", "Raise the issuer cap to 0.30: policy version 2, issuer rule re-evaluated, the loss budget still evaluated with measured loss, budget and gap. Version 1 and its report stay available."),
        ],
    )


def mateo():
    persona = {
        "persona_id": "mateo", "display_name": "Mateo", "case_reference": "Case p.6",
        "facts": [
            fact("age_occupation", "Age and occupation", "41 years old, operations manager", "Case p.6"),
            fact("profile", "Profile", "Has a partner and two children; intermediate investment experience.", "Case p.6"),
            fact("objective", "Investment objective", "He wants balanced capital growth over the medium and long term.", "Case p.6"),
            fact("preference_esg", "Preference", "Places high importance on environmental, social, and governance (ESG) factors.", "Case p.6"),
            fact("preference_controversies", "Constraint", "Wants to avoid companies involved in significant environmental or social controversies.", "Case p.6"),
            fact("preference_balance", "Preference", "Seeks a balance between growth potential and stability.", "Case p.6"),
            fact("horizon", "Investment horizon", "8-12 years", "Case p.6"),
            fact("risk_profile", "Risk profile", "Moderate", "Case p.6"),
        ],
        "what_this_persona_tests": {
            "text": "Can the system incorporate more than return and risk? It should consider financial factors and personal preferences, rather than selecting solely for potential return.",
            "case_reference": "Case p.6",
        },
    }
    rules = [
        exclude_sector("mateo-excl-energy-1", 0.0, "Energy", objective_id="obj-mateo-1",
                       words="Fictional scenario: by 'oil' I mean no holdings labelled Energy in what my funds report.", **P),
        controversy("mateo-controversy-1", 0.0, MATEO_NATURES, objective_id="obj-mateo-1",
                    words="Fictional scenario: no companies with a regulatory finding, court ruling or settlement in the registry.", **P),
    ]
    return scenario(
        persona, portfolio("pf-mateo-fictional-1", "mateo", MATEO_PORTFOLIO["cash"], MATEO_PORTFOLIO["positions"]),
        [MATEO_OBJECTIVE], rules, [],
        [{"phrase_id": "mateo-objective", "original_words": MATEO_OBJECTIVE["original_words"], "expected_outcome": "CLARIFICATION",
          "note": "'oil' is ambiguous: named companies, oil producers, fossil fuels or the Energy sector label. The interpreter must ask, offer the supported definitions and mark the others unsupported. The avoidance of oil is our scenario wording; the case itself only mentions controversies (Case p.6)."}],
        [{"request_id": "mateo-spy-15", "label": "Make SPY 15% of the portfolio (final direct weight), funded from cash",
          "purchase_request": purchase("SPY", 0.15, "Buy SPY so that it is 15% of my portfolio.")}],
        {"label": "Mateo clarifies what he meant by oil", "type": "CLARIFY_PREFERENCE",
         "payload": {"text": "By oil I meant companies that produce oil, not pipelines or utilities.", "objective_id": "obj-mateo-1"}},
        [
            step(1, "PERSONA_PORTFOLIO", "Load Mateo and his fictional portfolio (25% cash, 25% XBB.TO, 20% XIU.TO, 15% ESGV, 5% MSFT, 5% CNR.TO, 5% FTS.TO)."),
            step(2, "GOALS_RULES", "Interpret his sentence: the interpreter asks what 'oil' means. Mateo picks the Energy sector label as reported by funds and sets the tolerated exposure to 0; the controversy exclusion is confirmed separately."),
            step(3, "PROPOSED_PURCHASE", "Request SPY at a final direct weight of 0.15, funded from cash."),
            step(4, "INVESTIGATION", "The investigation looks up holdings, sector labels and the controversy registry; no 2022 replay because no scenario rule exists."),
            step(5, "VERDICT_EVIDENCE", "The Energy exclusion is already breached by the starting portfolio through XIU.TO (a finding about the starting portfolio, kept apart from the effect of the purchase). ESGV is unknown because its holdings were not acquired. The controversy rule reports only what dated registry records support; every company without a record stays 'not assessed', never 'clean'."),
            step(6, "CHALLENGE", "Mateo clarifies his preference; the reply is a new draft interpretation, with 'oil producers' reported as an unsupported definition."),
        ],
    )


def amira():
    persona = {
        "persona_id": "amira", "display_name": "Amira", "case_reference": "Case p.5",
        "facts": [
            fact("age_occupation", "Age and occupation", "26 years old, software engineer", "Case p.5"),
            fact("profile", "Profile", "Single, no children; intermediate investment experience.", "Case p.5"),
            fact("objective", "Investment objective", "Her objective is to grow her capital over the long term.", "Case p.5"),
            fact("preference_tech", "Preference", "Very interested in artificial intelligence and emerging technologies.", "Case p.5"),
            fact("preference_risk", "Preference", "Open to high-growth companies and significant volatility; interested in crypto assets.", "Case p.5"),
            fact("preference_diversification", "Constraint", "Still wants some diversification and does not want to invest exclusively in technology.", "Case p.5"),
            fact("horizon", "Investment horizon", "15 years or more", "Case p.5"),
            fact("risk_profile", "Risk profile", "High", "Case p.5"),
        ],
        "what_this_persona_tests": {
            "text": "How much risk will the system accept? It should account for an aggressive profile without interpreting \"high risk\" as \"anything goes,\" while respecting Amira's desire for diversification.",
            "case_reference": "Case p.5",
        },
    }
    goal = objective(
        "obj-amira-1", "Grow my capital over 15 years or more. I accept high risk and I like AI and crypto, but I still want some diversification and not only technology.",
        case_reference="Case p.5")
    rules = [max_issuer("amira-issuer-cap-1", 0.20, objective_id="obj-amira-1",
                        words="Fictional scenario: no more than 20% of the portfolio in any single company, funds included.", **P)]
    pair = [
        min_issuer("amira-min-nvidia-1", 0.20, "NVIDIA", objective_id="obj-amira-1",
                   words="Fictional scenario: keep at least 20% of the portfolio in NVIDIA.", **P),
        max_issuer("amira-max-nvidia-1", 0.10, scope="NVIDIA", objective_id="obj-amira-1",
                   words="Fictional scenario: never more than 10% of the portfolio in NVIDIA.", **P),
    ]
    positions = {"SPY": 0.30, "XIU.TO": 0.10, "NVDA": 0.10, "MSFT": 0.10, "SHOP.TO": 0.05, "JPM": 0.05, "BTC-USD": 0.12, "ETH-USD": 0.08}
    return scenario(
        persona, portfolio("pf-amira-fictional-1", "amira", 0.10, positions), [goal], rules,
        [{"set_id": "proven-conflict-pair", "label": "Minimum 20% and maximum 10% in the same company",
          "purpose": "Demonstrates a PROVEN conflict: a supported calculation shows that no exposure to NVIDIA can be at least 0.20 and at most 0.10.",
          "rules": pair}],
        [{"phrase_id": "amira-ambiguous", "original_words": "I want maximum growth and strict diversification.", "expected_outcome": "CLARIFICATION",
          "note": "Ambiguous language, not a proven contradiction. The correct outcome is a targeted clarification question; a 'contradictory rules' verdict here is a defect."}],
        [
            {"request_id": "amira-nvda-15", "label": "Make NVDA 15% of the portfolio (final direct weight), funded from cash",
             "purchase_request": purchase("NVDA", 0.15, "Take my Nvidia position to 15% of my portfolio.")},
            {"request_id": "amira-btc-15", "label": "Make BTC-USD 15% of the portfolio (final direct weight), funded from cash",
             "purchase_request": purchase("BTC-USD", 0.15, "Take my Bitcoin position to 15% of my portfolio.")},
        ],
        None,
        [
            step(1, "PERSONA_PORTFOLIO", "Load Amira and her fictional portfolio (10% cash, 30% SPY, 10% XIU.TO, 10% NVDA, 10% MSFT, 5% SHOP.TO, 5% JPM, 12% BTC-USD, 8% ETH-USD)."),
            step(2, "GOALS_RULES", "Type 'I want maximum growth and strict diversification.': the interpreter asks a clarification question and proposes nothing with a number."),
            step(3, "GOALS_RULES", "Confirm the explicit pair (minimum 0.20 and maximum 0.10 in NVIDIA): policy consistency reports a proven conflict with the calculation."),
            step(4, "PROPOSED_PURCHASE", "Request NVDA at a final direct weight of 0.15; crypto positions are shown as outside the scope of the company-exposure rules."),
        ],
    )


def all_scenarios():
    return {"robert": robert(), "mateo": mateo(), "amira": amira()}
