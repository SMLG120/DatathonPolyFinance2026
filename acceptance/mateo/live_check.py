#!/usr/bin/env python3
"""Deterministic live-API check of Mateo's workflow (Milestone 6). Standard library only.

Drives the canonical routes of ``contracts/api.md`` against a deployed Before You Buy API:

    GET  /portfolios/mateo                 fictional scenario (LEAD_DECISIONS D7)
    POST /rules/interpret                  Mateo's sentence -> a draft that must ASK what "oil" means
    POST /rules/confirm                    the two scenario rules, accepted unchanged -> policy version 1
    POST /check        (stored policy)     deterministic result, sent twice (must be identical)
    POST /check        (preview)           one draft rule; nothing stored; UNKNOWN is never a pass
    POST /investigations                   202, random Idempotency-Key; replayed once with the same key
    GET  /investigations/{id}              polled until SUCCEEDED / FAILED or the client deadline
    GET  /investigations/{id}              once more: a terminal job is immutable

and asserts response shapes, the invariants of ``mateo_invariants`` (the same ones the engine acceptance
tests assert), and, with ``--compare-local``, equality between the live ``result`` and
``backend.engine.check_rules`` run locally on ``data/processed`` for the same inputs.

    BYB_ACCESS_CODE=... python3 acceptance/mateo/live_check.py --base-url https://<api-id>.execute-api.us-east-1.amazonaws.com
    python3 acceptance/mateo/live_check.py --dry-run --base-url https://example.invalid

The access code is read from the environment variable ``BYB_ACCESS_CODE`` only. It is never accepted on the
command line, never printed, never logged and never written to disk; every line of output is passed through a
redaction filter as a last defence. The script writes no file.

Each real run creates one policy and one investigation (and makes one interpreter call) in the deployment.

Exit codes: 0 every check passed; 1 at least one assertion failed; 2 the check could not run (no access code,
bad arguments, network failure, 401/403, request budget exhausted).
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Callable, Optional

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
for _extra in (HERE, REPO_ROOT / "contracts" / "python", REPO_ROOT):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

import mateo_invariants as inv  # noqa: E402  (standard library only, lives next to this file)

try:  # shape validation with the contract package when the script runs from a checkout
    import byb_contracts as _contracts  # noqa: E402
except Exception:  # pragma: no cover - only outside a checkout
    _contracts = None

ENV_ACCESS_CODE = "BYB_ACCESS_CODE"
PERSONA = "mateo"
EXIT_PASS, EXIT_FAIL, EXIT_COULD_NOT_RUN = 0, 1, 2

# contracts/api.md, "Timing"
POLL_INTERVAL_MS = 1500
POLL_DEADLINE_SECONDS = 180
MIN_POLL_INTERVAL_MS, MAX_POLL_INTERVAL_MS = 500, 10000
DEFAULT_TIMEOUT_SECONDS = 30  # API Gateway cuts every integration at 30 s
DEFAULT_MAX_REQUESTS = 160    # 9 workflow requests + at most 121 polls + bounded retries
IDEMPOTENCY_KEY_PATTERN = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
TERMINAL = ("SUCCEEDED", "FAILED")
IMMUTABLE_MEMBERS = ("status", "steps", "result", "explanation", "clarification", "failure")
COMPARE_TOLERANCE = 1e-9


class CouldNotRun(Exception):
    """The check could not be carried out (exit code 2). Not a verdict about the API's behaviour."""


class Abort(Exception):
    """A prerequisite step failed its assertions; later steps cannot run (exit code 1)."""


# ---------------------------------------------------------------- pure: secrets and URLs

def redact(text: str, secret: Optional[str]) -> str:
    """Remove the access code from anything about to be printed."""
    text = re.sub(r"(?i)(bearer\s+)[^\s\"',}]+", r"\1<redacted>", text)
    if secret:
        text = text.replace(secret, "<redacted>")
    return text


def read_access_code(environ: dict) -> str:
    code = environ.get(ENV_ACCESS_CODE, "")
    if not code.strip():
        raise CouldNotRun(f"the environment variable {ENV_ACCESS_CODE} is not set (the access code is never taken from the command line)")
    return code.strip()


def normalise_base_url(base_url: str) -> str:
    parsed = urllib.parse.urlsplit(base_url)
    if parsed.scheme not in ("https", "http") or not parsed.netloc:
        raise CouldNotRun(f"--base-url must be an absolute http(s) URL, got {base_url!r}")
    if parsed.scheme == "http" and parsed.hostname not in ("localhost", "127.0.0.1", "::1"):
        raise CouldNotRun("--base-url must use https (plain http is accepted for localhost only): the access code is sent as a header")
    if parsed.query or parsed.fragment or parsed.username or parsed.password:
        raise CouldNotRun("--base-url must not carry a query string, a fragment or credentials")
    return base_url.rstrip("/")


def new_idempotency_key() -> str:
    key = str(uuid.uuid4())
    assert IDEMPOTENCY_KEY_PATTERN.match(key)
    return key


# ---------------------------------------------------------------- pure: request building (contracts/api.md)

def build_request(method: str, path: str, body: Any = None, idempotency_key: Optional[str] = None) -> dict:
    """One request, without the Authorization header (the transport adds it; it is never stored in a plan)."""
    if not path.startswith("/"):
        raise ValueError(f"path must start with '/': {path!r}")
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if idempotency_key is not None:
        if not IDEMPOTENCY_KEY_PATTERN.match(idempotency_key):
            raise ValueError("Idempotency-Key must match ^[A-Za-z0-9_-]{8,64}$")
        headers["Idempotency-Key"] = idempotency_key
    return {"method": method, "path": path, "headers": headers, "body": body}


def portfolio_request() -> dict:
    return build_request("GET", f"/portfolios/{PERSONA}")


def interpret_request(text: str) -> dict:
    return build_request("POST", "/rules/interpret", {"persona_id": PERSONA, "text": text, "policy_id": None, "policy_version": None})


def confirm_request(scenario: dict) -> dict:
    """Section 4: a new policy (``policy_id`` and ``base_version`` null) from the offered scenario rules, each sent
    complete, as displayed, with the number the user accepted (the scenario number, unchanged)."""
    confirmations = [{"rule": rule, "threshold": rule["threshold"]} for rule in scenario["scenario_rules"]]
    return build_request("POST", "/rules/confirm", {
        "persona_id": PERSONA, "policy_id": None, "base_version": None, "objectives": scenario["objectives"],
        "confirmations": confirmations, "withdraw_rule_ids": [], "change_note": "Fictional-scenario rules confirmed by the acceptance check.",
    })


def check_request(policy_id: str, policy_version: int, purchase_request: dict) -> dict:
    return build_request("POST", "/check", {"persona_id": PERSONA, "policy_id": policy_id, "policy_version": policy_version,
                                            "purchase_request": purchase_request, "draft_rules": None})


def preview_draft_rule() -> dict:
    """A what-if limit that is not part of Mateo's policy (contract fixture ``check_mateo_preview_unknown``)."""
    return {
        "rule_id": "mateo-issuer-cap-draft", "rule_type": "max_issuer_exposure", "parameters": {"issuer_scope": "any"},
        "threshold": 0.2, "threshold_kind": "max_fraction", "threshold_source": "USER_ENTERED", "threshold_quote": None,
        "unit": "fraction", "status": "PROPOSED", "origin": "USER_STATED",
        "original_words": "No single company above 20% of my portfolio, funds included.", "objective_id": None,
        "scope_description": "Maximum total equity exposure to any single company: direct holdings plus look-through via equity funds, "
                             "share classes of one company added together. Bond funds, commodity funds and crypto assets are outside "
                             "this rule's scope and are not assessed.",
        "confirmed_at": None, "confirmed_by": None, "supersedes_rule_id": None, "superseded_by_rule_id": None,
    }


def preview_request(purchase_request: dict) -> dict:
    return build_request("POST", "/check", {"persona_id": PERSONA, "policy_id": None, "policy_version": None,
                                            "purchase_request": purchase_request, "draft_rules": [preview_draft_rule()]})


def investigation_request(policy_id: str, policy_version: int, purchase_request: dict, idempotency_key: str) -> dict:
    return build_request("POST", "/investigations", {
        "persona_id": PERSONA, "policy_id": policy_id, "policy_version": policy_version, "request": purchase_request,
        "parent_investigation_id": None}, idempotency_key=idempotency_key)


def poll_request(path: str) -> dict:
    return build_request("GET", path)


def max_polls(deadline_seconds: float, interval_ms: int) -> int:
    return int(math.ceil(deadline_seconds * 1000.0 / interval_ms)) + 1


def clamp_interval(interval_ms: Any) -> int:
    if isinstance(interval_ms, bool) or not isinstance(interval_ms, int):
        return POLL_INTERVAL_MS
    return max(MIN_POLL_INTERVAL_MS, min(MAX_POLL_INTERVAL_MS, interval_ms))


def local_scenario() -> Optional[dict]:
    path = REPO_ROOT / "contracts" / "scenarios" / "mateo.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def planned_requests(scenario: Optional[dict]) -> list[dict]:
    """The requests of one run, in order, for ``--dry-run``. Values only known at run time are placeholders."""
    if scenario is None:
        text = inv.MATEO_OBJECTIVE
        purchase = {"instrument_id": inv.MATEO_REQUEST[0], "target_direct_weight": inv.MATEO_REQUEST[1], "funding": "CASH",
                    "original_words": "<from GET /portfolios/mateo>"}
        confirm = build_request("POST", "/rules/confirm", "<the scenario_rules and objectives returned by GET /portfolios/mateo, each rule with its own threshold>")
    else:
        text = scenario["demo_phrases"][0]["original_words"]
        purchase = scenario["demo_requests"][0]["purchase_request"]
        confirm = confirm_request(scenario)
    key = "<random UUID4, generated per run>"
    investigation = build_request("POST", "/investigations", {"persona_id": PERSONA, "policy_id": "<policy_id from the 201>", "policy_version": 1,
                                                              "request": purchase, "parent_investigation_id": None})
    investigation["headers"]["Idempotency-Key"] = key
    stored = check_request("<policy_id from the 201>", 1, purchase)
    polls = max_polls(POLL_DEADLINE_SECONDS, POLL_INTERVAL_MS)
    return [
        dict(portfolio_request(), expect="200 portfolio_response", note="Mateo's fictional scenario (D7 weights, offered rules, SPY purchasable)"),
        dict(interpret_request(text), expect="200 interpretation (502/504 tolerated unless --require-interpreter)", note="model call; skipped with --skip-interpret"),
        dict(confirm, expect="201 confirm_response", note="creates one policy at version 1"),
        dict(stored, expect="200 check_result", note="stored policy; deterministic"),
        dict(stored, expect="200 check_result identical to the previous one", note="determinism"),
        dict(preview_request(purchase), expect="200 check_result with preview true", note="draft rule only; nothing stored"),
        dict(investigation, expect="202 investigation_accepted", note="creates one investigation"),
        dict(investigation, expect="202 with the same id", note="idempotent replay, same key and body"),
        dict(poll_request("/investigations/<id from the 202>"), expect="200 investigation_job until SUCCEEDED or FAILED",
             note=f"every poll.interval_ms ({POLL_INTERVAL_MS} ms by contract), at most {polls} polls, client deadline {POLL_DEADLINE_SECONDS} s"),
        dict(poll_request("/investigations/<id from the 202>"), expect="200, terminal members unchanged", note="terminal results are immutable"),
    ]


# ---------------------------------------------------------------- pure: checks on responses

def shape_problems(schema_ref: str, body: Any) -> list[str]:
    """Contract shape and semantics (``byb_contracts.api_body_errors``) when run from a checkout; a minimal
    required-member check otherwise."""
    if _contracts is not None:
        try:
            return [f"{schema_ref}: {error}" for error in _contracts.api_body_errors(schema_ref, body)]
        except Exception as error:  # a validator crash is a finding about the body, not a reason to stop
            return [f"{schema_ref}: validator raised {type(error).__name__}: {error}"]
    required = {
        "api.schema.json#/$defs/portfolio_response": ("schema_version", "scenario", "instruments", "purchasable_instrument_ids"),
        "interpretation.schema.json": ("schema_version", "interpretation_id", "original_words", "objectives", "proposed_rules", "unsupported", "clarifications"),
        "api.schema.json#/$defs/confirm_response": ("schema_version", "policy"),
        "check_result.schema.json": ("schema_version", "preview", "execution", "feasibility", "policy_consistency", "rule_results", "rules_not_evaluated",
                                     "starting_portfolio_findings", "data_coverage", "scenario", "goal_context", "max_compliant", "exposure", "evidence", "summary"),
        "api.schema.json#/$defs/investigation_accepted": ("schema_version", "id", "status", "created_at", "deadline_at", "expires_at", "poll"),
        "investigation_job.schema.json": ("schema_version", "id", "status", "steps", "clarification", "result", "explanation", "failure"),
    }[schema_ref]
    if not isinstance(body, dict):
        return [f"{schema_ref}: the body is not a JSON object"]
    return [f"{schema_ref}: required member {name!r} is missing" for name in required if name not in body]


def interpretation_problems(draft: dict, text: str) -> list[str]:
    """What must hold for ANY interpreter output (BUILD_BRIEF sections 2 and 6, SEMANTICS section 14)."""
    problems = []
    if draft.get("original_words") != text:
        problems.append("interpretation: original_words is not the user's text, verbatim")
    rules = [("proposed_rules", rule) for rule in draft.get("proposed_rules", [])]
    for clarification in draft.get("clarifications", []):
        if len(clarification["options"]) < 2:
            problems.append(f"clarification {clarification['clarification_id']}: fewer than two options")
        if clarification["about_words"] not in text:
            problems.append(f"clarification {clarification['clarification_id']}: about_words is not a span of the user's text")
        for option in clarification["options"]:
            if option["proposed_rule"] is not None:
                rules.append((f"option {option['option_id']}", option["proposed_rule"]))
            if not option["supported"] and (option["proposed_rule"] is not None or option["purchase_request"] is not None):
                problems.append(f"option {option['option_id']}: an unsupported definition carries a draft")
    for where, rule in rules:
        name = f"{where}[{rule['rule_id']}]"
        if rule["status"] != "PROPOSED" or rule["confirmed_at"] is not None or rule["confirmed_by"] is not None:
            problems.append(f"{name}: a draft rule must be PROPOSED and unconfirmed (inactive)")
        if rule["origin"] == "FICTIONAL_SCENARIO":
            problems.append(f"{name}: the interpreter never emits FICTIONAL_SCENARIO rules")
        if rule["threshold"] is not None:
            quote = rule.get("threshold_quote")
            if rule["threshold_source"] != "USER_WORDS" or not quote or quote not in text:
                problems.append(f"{name}: invented threshold {rule['threshold']} (a number is allowed only when quoted from the user's words)")
        elif rule["origin"] != "SYSTEM_PROPOSED" or rule["threshold_source"] is not None:
            problems.append(f"{name}: a rule without a number must be SYSTEM_PROPOSED with a null threshold_source")
        if rule["original_words"] not in text:
            problems.append(f"{name}: original_words is not a span of the user's text")
    for item in draft.get("unsupported", []):
        if item["words"] not in text:
            problems.append("unsupported: words is not a span of the user's text")
    return problems


def mateo_oil_clarification_problems(draft: dict) -> list[str]:
    """LEAD_DECISIONS D7/D3: the interpreter must ask what "oil" means, offer the supported definitions and mark
    the others unsupported. Wording and option ids are free; the structure is not."""
    about_oil = [c for c in draft.get("clarifications", []) if "oil" in c["about_words"].lower()]
    if not about_oil:
        return ["no clarification question about 'oil' (the interpreter must ask, not guess)"]
    problems = []
    options = [option for clarification in about_oil for option in clarification["options"]]
    energy = [o for o in options if o["supported"] and o["proposed_rule"] is not None and o["proposed_rule"]["rule_type"] == "exclusion"
              and o["proposed_rule"]["parameters"].get("definition", {}).get("kind") == "fund_reported_sector"]
    if not energy:
        problems.append("the 'oil' question offers no supported fund_reported_sector exclusion")
    for option in energy:
        if option["proposed_rule"]["parameters"]["definition"].get("sector") != "Energy":
            problems.append(f"option {option['option_id']}: the sector label offered is not 'Energy'")
        if option["proposed_rule"]["threshold"] is not None:
            problems.append(f"option {option['option_id']}: the Energy draft carries a number the user never gave")
    if not [o for o in options if not o["supported"]]:
        problems.append("the 'oil' question lists no unsupported definition (oil producers, fossil fuels)")
    outright = [r["rule_id"] for r in draft.get("proposed_rules", []) if r["rule_type"] == "exclusion"]
    if outright:
        problems.append(f"an exclusion rule is proposed outright ({outright}) although 'oil' is ambiguous")
    return problems


def portfolio_response_problems(body: dict) -> list[str]:
    scenario = body["scenario"]
    problems = inv.mateo_portfolio_problems(scenario["portfolio"])
    if scenario["persona"]["persona_id"] != PERSONA or scenario["fictional"] is not True:
        problems.append("the scenario is not Mateo's fictional scenario")
    if [o["original_words"] for o in scenario["objectives"]] != [inv.MATEO_OBJECTIVE]:
        problems.append("the objective is not Mateo's D7 sentence")
    types = [rule["rule_type"] for rule in scenario["scenario_rules"]]
    if types != ["exclusion", "controversy_exclusion"]:
        problems.append(f"offered rules are {types}, expected the Energy exclusion then the controversy exclusion")
    for rule in scenario["scenario_rules"]:
        if rule["status"] != "PROPOSED" or rule["origin"] != "FICTIONAL_SCENARIO" or rule["confirmed_at"] is not None:
            problems.append(f"offered rule {rule['rule_id']} must be PROPOSED / FICTIONAL_SCENARIO (inactive until confirmed)")
        if rule["threshold"] != 0:
            problems.append(f"offered rule {rule['rule_id']} has threshold {rule['threshold']}, expected 0")
    if types and types[0] == "exclusion" and scenario["scenario_rules"][0]["parameters"] != {"definition": {"kind": "fund_reported_sector", "sector": "Energy"}}:
        problems.append("the offered exclusion is not fund_reported_sector = Energy")
    requests = [r["purchase_request"] for r in scenario["demo_requests"]]
    if not requests or (requests[0]["instrument_id"], requests[0]["target_direct_weight"], requests[0]["funding"]) != (*inv.MATEO_REQUEST, "CASH"):
        problems.append("the demo request is not SPY at a final direct weight of 0.15, funded from cash")
    if inv.MATEO_REQUEST[0] not in body["purchasable_instrument_ids"]:
        problems.append("SPY is not purchasable")
    for instrument_id in list(inv.MATEO_WEIGHTS) + [inv.MATEO_REQUEST[0]]:
        if instrument_id not in body["instruments"]:
            problems.append(f"no registry entry for {instrument_id}")
    return problems


def policy_problems(policy: dict, scenario: dict) -> list[str]:
    """Section 4, server rules 1, 3 and 6, for scenario rules accepted unchanged."""
    problems = []
    if policy["persona_id"] != PERSONA or policy["version"] != 1 or policy["parent_version"] is not None:
        problems.append("a new policy must be version 1 without a parent")
    offered = scenario["scenario_rules"]
    if [rule["rule_id"] for rule in policy["rules"]] != [rule["rule_id"] for rule in offered]:
        problems.append("the stored rules are not the confirmed rules, in the order of the confirmations")
        return problems
    server_written = ("status", "confirmed_at", "confirmed_by")
    for stored, rule in zip(policy["rules"], offered):
        if stored["status"] != "CONFIRMED" or not stored["confirmed_at"] or stored["confirmed_by"] != "demo_user":
            problems.append(f"{stored['rule_id']}: not stored as CONFIRMED by demo_user with a confirmation time")
        if stored["origin"] != "FICTIONAL_SCENARIO" or stored["threshold_source"] != "FICTIONAL_SCENARIO":
            problems.append(f"{stored['rule_id']}: a scenario rule accepted unchanged must stay FICTIONAL_SCENARIO")
        if {k: v for k, v in stored.items() if k not in server_written} != {k: v for k, v in rule.items() if k not in server_written}:
            problems.append(f"{stored['rule_id']}: the stored rule differs from the rule that was confirmed (type, parameters, number or wording)")
    if policy["objectives"] != scenario["objectives"]:
        problems.append("the stored objectives are not the submitted objectives")
    return problems


def in_scope_equity_weight(portfolio: dict, instruments: dict, purchase_request: dict) -> Optional[float]:
    """Equity weight of the proposed portfolio, from the portfolio and the registry entries of the 200 itself."""
    weights = {p["instrument_id"]: p["weight"] for p in portfolio["positions"]}
    weights[purchase_request["instrument_id"]] = purchase_request["target_direct_weight"]
    if any(i not in instruments for i in weights):
        return None
    return sum(w for i, w in weights.items() if instruments[i]["equity_scope"] and w > 0)


def stored_result_problems(result: dict, policy: dict, purchase_request: dict, equity_weight: Optional[float]) -> list[str]:
    problems = []
    if result["preview"] is not False or result["policy_id"] != policy["policy_id"] or result["policy_version"] != policy["version"]:
        problems.append("a stored-policy result must have preview false and echo policy_id and policy_version")
    if result["persona_id"] != PERSONA or result["purchase_request"] != purchase_request:
        problems.append("the result does not echo the persona and the purchase request")
    problems += inv.check_result_problems(result)
    if result["execution"]["status"] == "OK":
        if [e["rule_id"] for e in result["rule_results"]] != [r["rule_id"] for r in policy["rules"]] or result["rules_not_evaluated"]:
            problems.append("every confirmed rule must be evaluated, in policy order, and nothing else")
        else:
            problems += inv.mateo_demo_problems(result, equity_weight)
    return problems


def preview_result_problems(result: dict) -> list[str]:
    problems = []
    if result["preview"] is not True:
        problems.append("draft_rules were sent: the result must be labelled preview")
    problems += inv.check_result_problems(result)
    if result["execution"]["status"] != "OK":
        return problems
    if [e["rule_id"] for e in result["rule_results"]] != ["mateo-issuer-cap-draft"]:
        problems.append("a preview evaluates exactly the draft rules sent, instead of any stored policy")
        return problems
    entry = result["rule_results"][0]
    if "MISSING_HOLDINGS" not in entry["unknown_causes"]:
        problems.append("preview: ESGV has no holdings file, MISSING_HOLDINGS must be a cause")
    if entry["status"] == "PASS" and entry["measured"]["upper"] > entry["limit"] + inv.EPS:
        problems.append("preview: UNKNOWN rendered as PASS")
    if entry["status"] == "UNKNOWN" and result["summary"]["headline"] != "NO_FAIL_BUT_UNKNOWN":
        problems.append("preview: an UNKNOWN rule must give the headline NO_FAIL_BUT_UNKNOWN")
    if result["goal_context"] != []:
        problems.append("preview without policy context: goal_context must be empty")
    if any(record["policy_version"] is not None for record in result["evidence"]):
        problems.append("preview: every evidence record must have policy_version null")
    thresholds = [r for r in result["evidence"] if r["metric_id"] == "rule_threshold"]
    if any(r["label"] != "ASSUMPTION" for r in thresholds):
        problems.append("preview: a draft threshold must be labelled ASSUMPTION")
    if result["starting_portfolio_findings"] and entry["starting"]["status"] != "FAIL":
        problems.append("preview: a starting finding without a starting FAIL")
    return problems


def accepted_problems(body: dict, interval_expected: int = POLL_INTERVAL_MS) -> list[str]:
    problems = []
    if body["status"] not in ("QUEUED", "RUNNING") + TERMINAL:
        problems.append(f"accepted: unknown status {body['status']}")
    path = str(body["poll"]["path"])
    if not path.startswith("/") or not path.endswith(f"/investigations/{body['id']}") or "://" in path or "?" in path:
        problems.append(f"accepted: poll.path {path!r} is not the relative path /investigations/{{id}}")
    if body["poll"]["interval_ms"] != interval_expected:
        problems.append(f"accepted: poll.interval_ms is {body['poll']['interval_ms']}, the contract says {interval_expected}")
    return problems


def job_problems(job: dict, accepted: dict, policy: dict, purchase_request: dict, idempotency_key: str) -> list[str]:
    problems = []
    if job["id"] != accepted["id"]:
        problems.append("job: id differs from the accepted id")
    if job["status"] != "SUCCEEDED":
        failure = job.get("failure") or {}
        problems.append(f"job: ended {job['status']} ({failure.get('code')}: {failure.get('message')})")
        if job["status"] == "FAILED" and (job["result"] is not None or job["explanation"]):
            problems.append("job: a FAILED job must not show a partial verdict")
        return problems
    if job["failure"] is not None:
        problems.append("job: SUCCEEDED with a failure")
    if job["result"] is None or job["clarification"] is not None:
        problems.append("job: a structured request must end with a result and no clarification")
        return problems
    if (job["persona_id"], job["policy_id"], job["policy_version"]) != (PERSONA, policy["policy_id"], policy["version"]):
        problems.append("job: persona, policy_id or policy_version differ from the request")
    if job["request"] != purchase_request or job["resolved_request"] != purchase_request:
        problems.append("job: request / resolved_request differ from the structured request that was sent")
    if job["idempotency_key"] != idempotency_key:
        problems.append("job: idempotency_key is not the key that was sent")
    if any(step["status"] == "RUNNING" for step in job["steps"]):
        problems.append("job: a terminal job has a RUNNING step")
    if [step["seq"] for step in job["steps"]] != list(range(1, len(job["steps"]) + 1)):
        problems.append("job: steps are not numbered 1..n")
    if not any(step["tool"] == "check_rules" and step["status"] == "OK" for step in job["steps"]):
        problems.append("job: no completed check_rules step (the server enforces every check whatever the model does)")
    evidence_ids = {record["evidence_id"] for record in job["result"]["evidence"]}
    for where, items in (("step", job["steps"]), ("explanation", job["explanation"])):
        for item in items:
            missing = [i for i in item["evidence_ids"] if i not in evidence_ids]
            if missing:
                problems.append(f"job: a {where} cites evidence that is not in result.evidence: {missing}")
    for statement in job["explanation"]:
        if statement["rendered_by"] == "MODEL_VALIDATED" and not statement["evidence_ids"]:
            problems.append("job: a model-written statement cites no evidence record")
    if job["agent"]["mode"] == "DETERMINISTIC_FALLBACK" and any(s["rendered_by"] != "TEMPLATE" for s in job["explanation"]):
        problems.append("job: DETERMINISTIC_FALLBACK allows TEMPLATE statements only")
    return problems


def immutable_problems(first: dict, second: dict) -> list[str]:
    return [f"terminal job changed between two reads: {name}" for name in IMMUTABLE_MEMBERS if first.get(name) != second.get(name)]


def json_diff(expected: Any, actual: Any, path: str = "result", tolerance: float = COMPARE_TOLERANCE, limit: int = 20) -> list[str]:
    """Paths at which two JSON documents differ (numbers within ``tolerance`` are equal)."""
    diffs: list[str] = []

    def walk(a: Any, b: Any, where: str) -> None:
        if len(diffs) >= limit:
            return
        number = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)  # noqa: E731
        if number(a) and number(b):
            if abs(a - b) > tolerance:
                diffs.append(f"{where}: {a!r} != {b!r}")
        elif isinstance(a, dict) and isinstance(b, dict):
            for key in sorted(set(a) | set(b)):
                if key not in a or key not in b:
                    diffs.append(f"{where}.{key}: present on one side only")
                else:
                    walk(a[key], b[key], f"{where}.{key}")
        elif isinstance(a, list) and isinstance(b, list):
            if len(a) != len(b):
                diffs.append(f"{where}: {len(a)} items != {len(b)} items")
            else:
                for index, (x, y) in enumerate(zip(a, b)):
                    walk(x, y, f"{where}[{index}]")
        elif a != b or type(a) is not type(b):
            diffs.append(f"{where}: {str(a)[:60]!r} != {str(b)[:60]!r}")

    walk(expected, actual, path)
    return diffs


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


# ---------------------------------------------------------------- transport

class Response:
    def __init__(self, status: int, body: Any, text: str = ""):
        self.status, self.body, self.text = status, body, text


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):  # never forward the Authorization header to another location
        return None


class HttpTransport:
    """urllib transport. Holds the access code in memory only; counts and bounds the requests it sends."""

    def __init__(self, base_url: str, access_code: str, timeout: float = DEFAULT_TIMEOUT_SECONDS, max_requests: int = DEFAULT_MAX_REQUESTS):
        self.base_url, self._code, self.timeout, self.max_requests = base_url, access_code, timeout, max_requests
        self.sent = 0
        self._opener = urllib.request.build_opener(_NoRedirect)

    def send(self, request: dict) -> Response:
        if self.sent >= self.max_requests:
            raise CouldNotRun(f"request budget of {self.max_requests} exhausted")
        self.sent += 1
        data = None if request["body"] is None else json.dumps(request["body"]).encode("utf-8")
        headers = dict(request["headers"], Authorization=f"Bearer {self._code}")
        http_request = urllib.request.Request(self.base_url + request["path"], data=data, method=request["method"], headers=headers)
        try:
            with self._opener.open(http_request, timeout=self.timeout) as reply:
                status, raw = reply.status, reply.read()
        except urllib.error.HTTPError as error:
            status, raw = error.code, error.read()
        text = raw.decode("utf-8", errors="replace")
        try:
            body = json.loads(text) if text.strip() else None
        except ValueError:
            body = None
        return Response(status, body, text)


NETWORK_ERRORS = (urllib.error.URLError, TimeoutError, ConnectionError, OSError)


# ---------------------------------------------------------------- polling (contracts/api.md section 7)

def poll_until_terminal(send: Callable[[dict], Response], path: str, interval_ms: int, deadline_seconds: float = POLL_DEADLINE_SECONDS,
                        sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic) -> dict:
    """Poll until SUCCEEDED / FAILED, the client deadline, or a stop status.

    Returns ``{"outcome", "job", "polls", "retries", "detail"}`` with outcome ``TERMINAL``, ``DEADLINE``,
    ``UNAUTHORIZED`` or ``GONE``. A network error, a 429 or a 5xx is retried at the same interval until the
    client deadline; 401/403 and 404/410 stop at once. The number of polls is bounded by the deadline AND by
    ``max_polls``, whatever the clock does. The deadline is measured with a client timer from the call."""
    interval_ms = clamp_interval(interval_ms)
    started, budget = clock(), max_polls(deadline_seconds, interval_ms)
    polls = retries = 0
    last_job, detail = None, ""
    while polls < budget and clock() - started <= deadline_seconds:
        polls += 1
        try:
            response = send(poll_request(path))
        except NETWORK_ERRORS as error:
            retries, detail = retries + 1, f"network error: {type(error).__name__}"
        else:
            if response.status in (401, 403):
                return {"outcome": "UNAUTHORIZED", "job": last_job, "polls": polls, "retries": retries, "detail": f"HTTP {response.status}"}
            if response.status in (404, 410):
                return {"outcome": "GONE", "job": last_job, "polls": polls, "retries": retries, "detail": f"HTTP {response.status}"}
            if response.status == 429 or response.status >= 500:
                retries, detail = retries + 1, f"HTTP {response.status}"
            elif response.status != 200 or not isinstance(response.body, dict) or "status" not in response.body:
                return {"outcome": "GONE", "job": last_job, "polls": polls, "retries": retries, "detail": f"unexpected answer: HTTP {response.status}"}
            else:
                last_job = response.body
                if last_job["status"] in TERMINAL:
                    return {"outcome": "TERMINAL", "job": last_job, "polls": polls, "retries": retries, "detail": last_job["status"]}
                detail = last_job["status"]
        if polls < budget and clock() - started + interval_ms / 1000.0 <= deadline_seconds:
            sleep(interval_ms / 1000.0)
        else:
            break
    return {"outcome": "DEADLINE", "job": last_job, "polls": polls, "retries": retries,
            "detail": f"not terminal after {polls} polls / {deadline_seconds:g} s (last: {detail or 'no answer'})"}


# ---------------------------------------------------------------- the run

class Report:
    def __init__(self, emit: Callable[[str], None]):
        self.emit, self.checks, self.failures, self.warnings = emit, 0, [], []

    def check(self, name: str, problems: list[str], detail: str = "") -> bool:
        self.checks += 1
        if problems:
            self.failures.append(name)
            self.emit(f"[FAIL] {name}")
            for problem in problems[:25]:
                self.emit(f"         - {problem}")
            if len(problems) > 25:
                self.emit(f"         ... and {len(problems) - 25} more")
            return False
        self.emit(f"[PASS] {name}" + (f": {detail}" if detail else ""))
        return True

    def warn(self, name: str, detail: str) -> None:
        self.warnings.append(name)
        self.emit(f"[WARN] {name}: {detail}")


def _send(transport, request: dict, retry_safe: bool = False, sleep: Callable[[float], None] = time.sleep) -> Response:
    """One request; a network failure means the check could not run. A safe request is retried once on 429/5xx."""
    for attempt in (1, 2):
        try:
            response = transport.send(request)
        except CouldNotRun:
            raise
        except NETWORK_ERRORS as error:
            raise CouldNotRun(f"{request['method']} {request['path']}: network error ({type(error).__name__}: {getattr(error, 'reason', error)})")
        if response.status in (401, 403):
            raise CouldNotRun(f"{request['method']} {request['path']}: HTTP {response.status} (access code missing or wrong; the body is not read)")
        if retry_safe and attempt == 1 and (response.status == 429 or response.status >= 500):
            sleep(2.0)
            continue
        return response
    return response


def _expect(report: Report, name: str, response: Response, status: int, schema_ref: str) -> dict:
    problems = []
    if response.status != status:
        code = response.body.get("error", {}).get("code") if isinstance(response.body, dict) and isinstance(response.body.get("error"), dict) else None
        problems.append(f"HTTP {response.status}" + (f" ({code})" if code else "") + f", expected {status}")
    elif not isinstance(response.body, dict):
        problems.append("the body is not a JSON object")
    else:
        problems += shape_problems(schema_ref, response.body)
    if not report.check(f"{name}: HTTP {status} and {schema_ref.rsplit('/', 1)[-1]} shape", problems):
        raise Abort(name)
    return response.body


def local_result(portfolio: dict, policy: dict, purchase_request: dict) -> tuple[dict, dict]:
    """``backend.engine.check_rules`` on ``data/processed`` for the inputs the API itself returned."""
    processed = REPO_ROOT / "data" / "processed"
    try:
        from backend import engine  # noqa: PLC0415
        data = {name: json.loads((processed / f"{name}.json").read_text(encoding="utf-8"))
                for name in ("instruments", "holdings", "market_data", "controversies")}
    except Exception as error:
        raise CouldNotRun(f"--compare-local needs a checkout with backend/engine and data/processed ({type(error).__name__}: {error})")
    result = engine.check_rules(portfolio, policy, purchase_request, data["instruments"], data["holdings"], data["market_data"], data["controversies"])
    snapshot = {fund_id: fund["holdings_date"] for fund_id, fund in data["holdings"]["funds"].items()}
    return result, snapshot


def run_live(transport, report: Report, *, skip_interpret: bool = False, require_interpreter: bool = False, compare_local: bool = False,
             deadline_seconds: float = POLL_DEADLINE_SECONDS, sleep: Callable[[float], None] = time.sleep,
             clock: Callable[[], float] = time.monotonic, idempotency_key: Optional[str] = None) -> None:
    send = lambda request, retry_safe=False: _send(transport, request, retry_safe, sleep)  # noqa: E731

    # 1. portfolio
    body = _expect(report, "GET /portfolios/mateo", send(portfolio_request(), True), 200, "api.schema.json#/$defs/portfolio_response")
    if not report.check("portfolio: Mateo's D7 scenario (weights sum to 1, offered rules inactive, SPY to 0.15)", portfolio_response_problems(body)):
        raise Abort("portfolio")
    scenario, instruments = body["scenario"], body["instruments"]
    purchase = scenario["demo_requests"][0]["purchase_request"]
    text = scenario["objectives"][0]["original_words"]

    # 2. interpret (a model call: the only non-deterministic step; its safety invariants are still hard)
    if skip_interpret:
        report.warn("POST /rules/interpret", "skipped (--skip-interpret)")
    else:
        response = send(interpret_request(text))
        if response.status in (502, 504) and not require_interpreter:
            report.warn("POST /rules/interpret", f"HTTP {response.status}: the interpreter did not answer; the contract lets the scenario rules be confirmed without it")
        else:
            draft = _expect(report, "POST /rules/interpret", response, 200, "interpretation.schema.json")
            report.check("interpret: words preserved, drafts PROPOSED, no invented threshold", interpretation_problems(draft, text))
            report.check("interpret: asks what 'oil' means, supported definitions offered, unsupported ones refused", mateo_oil_clarification_problems(draft))

    # 3. confirm
    body = _expect(report, "POST /rules/confirm", send(confirm_request(scenario)), 201, "api.schema.json#/$defs/confirm_response")
    policy = body["policy"]
    if not report.check("confirm: version 1, both rules CONFIRMED with their scenario provenance and number", policy_problems(policy, scenario),
                        f"policy {policy.get('policy_id')} v{policy.get('version')}"):
        raise Abort("confirm")

    # 4. check (stored policy), twice
    equity = in_scope_equity_weight(scenario["portfolio"], instruments, purchase)
    stored_request = check_request(policy["policy_id"], policy["version"], purchase)
    first = _expect(report, "POST /check (stored policy)", send(stored_request, True), 200, "check_result.schema.json")
    report.check("check: invariants and Mateo's outcome (starting findings, bounds, causes, no feasible purchase)",
                 stored_result_problems(first, policy, purchase, equity), _summary_line(first))
    second = _expect(report, "POST /check (stored policy, repeated)", send(stored_request, True), 200, "check_result.schema.json")
    report.check("check: same inputs give an identical document", json_diff(first, second, tolerance=0.0))

    # 5. check (preview)
    preview = _expect(report, "POST /check (preview)", send(preview_request(purchase), True), 200, "check_result.schema.json")
    report.check("preview: labelled, draft only, UNKNOWN never shown as a pass", preview_result_problems(preview), _summary_line(preview))

    # 6. investigation
    key = idempotency_key or new_idempotency_key()
    create = investigation_request(policy["policy_id"], policy["version"], purchase, key)
    accepted = _expect(report, "POST /investigations", send(create, True), 202, "api.schema.json#/$defs/investigation_accepted")
    started = clock()  # the client deadline runs from the 202
    if not report.check("investigation: accepted with a poll path and the contract interval", accepted_problems(accepted), f"id {accepted['id']}"):
        raise Abort("investigation accepted")
    replay = _expect(report, "POST /investigations (same key, same body)", send(create, True), 202, "api.schema.json#/$defs/investigation_accepted")
    report.check("investigation: an idempotent replay returns the same id (no second job)",
                 [] if replay["id"] == accepted["id"] else [f"second id {replay['id']} differs from {accepted['id']}"])

    remaining = max(0.0, deadline_seconds - (clock() - started))
    outcome = poll_until_terminal(lambda request: transport.send(request), accepted["poll"]["path"], accepted["poll"]["interval_ms"], remaining, sleep, clock)
    if outcome["outcome"] == "UNAUTHORIZED":
        raise CouldNotRun(f"polling stopped: {outcome['detail']}")
    if not report.check("polling: reached a terminal state before the client deadline",
                        [] if outcome["outcome"] == "TERMINAL" else [f"{outcome['outcome']}: {outcome['detail']}"],
                        f"{outcome['detail']} after {outcome['polls']} polls, {outcome['retries']} retries"):
        raise Abort("polling")
    job = outcome["job"]
    if not report.check("job: investigation_job shape", shape_problems("investigation_job.schema.json", job)):
        raise Abort("job shape")
    if not report.check("job: SUCCEEDED with a result, real steps, a server-run check, citations that resolve",
                        job_problems(job, accepted, policy, purchase, key), f"agent mode {job.get('agent', {}).get('mode')}"):
        raise Abort("job")
    result = job["result"]
    report.check("result: invariants and Mateo's outcome", stored_result_problems(result, policy, purchase, equity), _summary_line(result))
    report.check("result: the investigation's result is the deterministic /check result for the same inputs", json_diff(first, result, tolerance=0.0))
    again = _send(transport, poll_request(accepted["poll"]["path"]), True, sleep)
    report.check("job: terminal members are immutable on a second read",
                 immutable_problems(job, again.body) if again.status == 200 and isinstance(again.body, dict) else [f"HTTP {again.status}"])

    # 7. local engine
    if compare_local:
        expected, snapshot = local_result(scenario["portfolio"], policy, purchase)
        versions = [] if expected["calculation_version"] == result["calculation_version"] else [
            f"calculation_version: local {expected['calculation_version']} != live {result['calculation_version']}"]
        diffs = versions + json_diff(expected, result)
        exact = canonical(expected) == canonical(result)
        report.check("compare-local: the live result equals backend.engine.check_rules on data/processed", diffs,
                     f"{'byte-identical canonical JSON' if exact else 'equal within 1e-9'}; local holdings dates {snapshot}")


def _summary_line(result: dict) -> str:
    if result.get("execution", {}).get("status") != "OK":
        return f"execution {result.get('execution', {}).get('status')}"
    rules = "; ".join(f"{e['rule_id']} {e['starting']['status']}->{e['status']} [{e['measured']['lower']:.6f}, {e['measured']['upper']:.6f}]"
                      for e in result["rule_results"] if e["measured"])
    return f"{result['summary']['headline']}; {rules}; max_compliant {result['max_compliant']['status']}"


# ---------------------------------------------------------------- command line

def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="live_check.py", description="Deterministic live-API check of Mateo's workflow (contracts/api.md).",
        epilog=f"The access code is read from the environment variable {ENV_ACCESS_CODE} only. Exit codes: 0 pass, 1 assertion failure, 2 could not run.")
    parser.add_argument("--base-url", required=True, help="API base URL, e.g. https://<api-id>.execute-api.us-east-1.amazonaws.com (https only)")
    parser.add_argument("--dry-run", action="store_true", help="print the planned requests and send nothing")
    parser.add_argument("--compare-local", action="store_true", help="also compare the live result with backend.engine.check_rules on data/processed")
    parser.add_argument("--skip-interpret", action="store_true", help="do not call POST /rules/interpret (no model call)")
    parser.add_argument("--require-interpreter", action="store_true", help="treat a 502/504 from POST /rules/interpret as a failure")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS, help="per-request timeout in seconds (default 30)")
    parser.add_argument("--poll-deadline", type=float, default=POLL_DEADLINE_SECONDS, help="client polling deadline in seconds (contract: 180)")
    parser.add_argument("--max-requests", type=int, default=DEFAULT_MAX_REQUESTS, help=f"hard cap on requests sent (default {DEFAULT_MAX_REQUESTS})")
    return parser.parse_args(argv)


def dry_run(base_url: str, emit: Callable[[str], None]) -> None:
    plan = planned_requests(local_scenario())
    emit(f"DRY RUN: nothing is sent. {len(plan)} planned requests against {base_url}")
    emit(f"Authorization header: the access code from ${ENV_ACCESS_CODE}, added to every request at run time; never printed.")
    for number, request in enumerate(plan, 1):
        emit(f"{number:2d}. {request['method']} {base_url}{request['path']}")
        emit(f"      headers: {json.dumps(request['headers'], sort_keys=True)}")
        if request["body"] is not None:
            emit(f"      body:    {json.dumps(request['body'], sort_keys=True)}")
        emit(f"      expect:  {request['expect']}")
        emit(f"      note:    {request['note']}")
    emit(f"Request budget: at most {DEFAULT_MAX_REQUESTS} requests; polling stops on SUCCEEDED/FAILED, 401/403, 404/410 or after {POLL_DEADLINE_SECONDS} s.")
    emit("A real run creates one policy and one investigation, and makes one interpreter call unless --skip-interpret.")


def main(argv: Optional[list[str]] = None, environ: Optional[dict] = None, transport_factory: Optional[Callable[..., Any]] = None,
         out: Optional[Callable[[str], None]] = None, sleep: Callable[[float], None] = time.sleep,
         clock: Callable[[], float] = time.monotonic) -> int:
    environ = os.environ if environ is None else environ
    secret = (environ.get(ENV_ACCESS_CODE) or "").strip() or None
    write = out or (lambda line: print(line, flush=True))
    emit = lambda line: write(redact(str(line), secret))  # noqa: E731
    try:
        args = parse_args(sys.argv[1:] if argv is None else argv)
    except SystemExit as stop:
        return EXIT_PASS if stop.code == 0 else EXIT_COULD_NOT_RUN
    report = Report(emit)
    try:
        base_url = normalise_base_url(args.base_url)
        if args.dry_run:
            dry_run(base_url, emit)
            return EXIT_PASS
        if args.max_requests < 12 or args.timeout <= 0 or args.poll_deadline <= 0:
            raise CouldNotRun("--max-requests must be at least 12; --timeout and --poll-deadline must be positive")
        code = read_access_code(environ)
        transport = (transport_factory or HttpTransport)(base_url, code, args.timeout, args.max_requests)
        emit(f"Live check of Mateo's workflow against {base_url}")
        try:
            run_live(transport, report, skip_interpret=args.skip_interpret, require_interpreter=args.require_interpreter,
                     compare_local=args.compare_local, deadline_seconds=args.poll_deadline, sleep=sleep, clock=clock)
        except Abort as stop:
            emit(f"Stopped after a failed prerequisite: {stop}. Later steps were not run.")
        except (KeyError, TypeError, IndexError, AttributeError, ValueError) as error:
            # only reachable when a body passed the shape check available here and still lacks a member
            report.check("response structure", [f"a response could not be read as the contract describes: {type(error).__name__}: {error}"])
        sent = getattr(transport, "sent", "?")
    except CouldNotRun as error:
        emit(f"COULD NOT RUN: {error}")
        return EXIT_COULD_NOT_RUN
    if report.failures:
        emit(f"RESULT: FAIL ({len(report.failures)} of {report.checks} checks failed, {len(report.warnings)} warnings, {sent} requests sent)")
        return EXIT_FAIL
    emit(f"RESULT: PASS ({report.checks} checks, {len(report.warnings)} warnings, {sent} requests sent)")
    return EXIT_PASS


if __name__ == "__main__":
    sys.exit(main())
