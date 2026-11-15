# HTTP API contract (schema_version 1.0.0)

Seven routes (BUILD_BRIEF section 7). Bodies are defined by `schemas/*.schema.json`; the meaning of
the numbers by `SEMANTICS.md`. Complete example exchanges are in `fixtures/api/*.json`; every JSON
block below is checked against the fixture named above it by `python/tests/test_api_doc.py`
(`complete` = the whole body, `excerpt` = some of its members).

| Route | Purpose | Success | Model call |
|---|---|---|---|
| `GET /portfolios/{persona_id}` | Fictional scenario, registry entries, purchasable instruments | 200 | no |
| `POST /rules/interpret` | Turn the user's words into a draft | 200 | yes, synchronous |
| `POST /rules/confirm` | Create a policy version from explicitly confirmed rules | 201 | no |
| `POST /check` | Deterministic check of one purchase; also slider previews | 200 | no |
| `POST /investigations` | Start an asynchronous investigation | 202 | in the worker |
| `GET /investigations/{id}` | Poll an investigation | 200 | no |
| `POST /investigations/{id}/challenge` | Dispute a fact, clarify a preference, change a rule | 201, 200, 202 | only to clarify |

BUILD_BRIEF writes the first route as `/portfolios/{persona}`; the path parameter is the `persona_id`
(`robert`, `mateo`, `amira`).

## 1. Conventions

- JSON in, JSON out, UTF-8. Requests with a body send `Content-Type: application/json`.
- Every property of every body is required; an absent value is an explicit `null`. Unknown
  properties are rejected (400). Every success body carries `schema_version`.
- Every weight, limit, exposure, return and gap is a **fraction** (10% = 0.10). A percentage string
  such as `"25%"` is a 400.
- Every number is a finite IEEE-754 double. `NaN`, `Infinity` and `-Infinity` (which are not JSON) are
  rejected with 400 `VALIDATION_ERROR` before any calculation, never read as missing data or as zero.
- Timestamps are UTC (`2026-11-14T15:02:00Z`). Dates are `YYYY-MM-DD`.
- Every response is sent with `Cache-Control: no-store`.

### Authentication (LEAD_DECISIONS D8)

Every route requires

```http
Authorization: Bearer <access code>
```

The code is typed by the user at run time and kept in `sessionStorage`; it is never in the bundle
or the repository. It is demo-grade access control, not a user identity.

A missing or wrong code is answered with **401 or 403**. API Gateway may reject the request itself,
with its own body (`{"message": "Unauthorized"}` or `{"message": "Forbidden"}`). **Clients treat 401
and 403 alike**: forget the stored code, show the access-code prompt, do not read the body. When
the service itself answers, the body is the error shape below with code `UNAUTHORIZED`
(`fixtures/api/error_unauthorized.json`).

CORS is not authentication. The browser sends the headers `Authorization`, `Content-Type` and
`Idempotency-Key`, so all three must be allowed; the preflight `OPTIONS` request carries no access
code and must be answered without one.

### Errors

Every 4xx and 5xx answer produced by the service has this body (`api.schema.json#/$defs/error_response`):

<!-- fixture: error_validation response_body complete -->
```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "The request body does not match the contract.",
    "details": [
      { "path": "purchase_request.target_direct_weight", "issue": "expected a number (a fraction such as 0.25), got the string '25%'" },
      { "path": "draft_rules", "issue": "required property is missing (send null to evaluate the stored policy)" }
    ],
    "request_id": "req-fixture-0001"
  }
}
```

- `message` is safe to display. It never contains secrets, stack traces or model output.
- `details[].path` is a dotted path into the request body, `""` for the body as a whole and
  `headers.<Name>` for a header.
- An error answer whose body is not this shape comes from API Gateway itself (unknown route,
  throttling, authorization). Clients then act on the status code alone.

| HTTP | `code` | When |
|---|---|---|
| 400 | `VALIDATION_ERROR` | Body is not JSON, does not match the request schema, or a required header is missing or malformed |
| 401, 403 | `UNAUTHORIZED` | Missing or wrong access code |
| 404 | `NOT_FOUND` | Unknown persona, policy, policy version or investigation |
| 409 | `POLICY_VERSION_CONFLICT` | `POST /rules/confirm`: `base_version` is not the latest version |
| 409 | `IDEMPOTENCY_KEY_REUSED` | The same `Idempotency-Key` was used with a different body |
| 409 | `INVESTIGATION_NOT_FINISHED` | A challenge was sent to an investigation that is `QUEUED` or `RUNNING` |
| 410 | `INVESTIGATION_EXPIRED` | The investigation is past `expires_at` |
| 422 | `INVALID_PURCHASE_REQUEST` | `POST /investigations`: the engine would refuse the structured request |
| 422 | `INVALID_CONFIRMATION` | `POST /rules/confirm`: the confirmation cannot be applied (section 4) |
| 422 | `UNSUPPORTED_CHALLENGE` | The challenge cannot be applied to this investigation (section 8) |
| 429 | `RATE_LIMITED` | Throttled. Retry later |
| 500 | `INTERNAL_ERROR` | Unexpected failure |
| 502 | `INTERPRETER_FAILED` | The model call failed or its output was rejected by validation |
| 503 | `WORKER_INVOCATION_FAILED` | The investigation worker could not be started |
| 504 | `INTERPRETER_TIMEOUT` | The interpreter did not finish within the server deadline |

### Timing

| What | Value | Constant (`byb_contracts.constants`) |
|---|---|---|
| Polling interval | 1500 ms | `POLL_INTERVAL_MS` |
| Job deadline, enforced by the server | `created_at` + 150 s | `INVESTIGATION_DEADLINE_SECONDS` |
| Polling deadline, enforced by the client | 180 s after the 202 | `POLL_DEADLINE_SECONDS` |
| Job expiry | `created_at` + 24 h | `INVESTIGATION_EXPIRY_SECONDS` |
| Interpreter deadline, enforced by the server | 20 s | `INTERPRET_TIMEOUT_SECONDS` |
| `POST /check` budget | 5 s | `CHECK_TIMEOUT_SECONDS` |

API Gateway HTTP APIs cut every integration at 30 s and this quota cannot be raised (AWS
documentation, "Quotas for configuring and running an HTTP API"). No synchronous route may rely on
more than 20 s.

## 2. GET /portfolios/{persona_id}

Returns the fictional scenario of one persona, the registry entries the client needs and the
instruments a purchase may name. The content is fixed per deployment; the client may keep it for
the session.

| Status | Body |
|---|---|
| 200 | `api.schema.json#/$defs/portfolio_response` |
| 404 | `NOT_FOUND`: no such persona |

<!-- fixture: portfolio_robert response_body excerpt -->
```json
{
  "schema_version": "1.0.0",
  "scenario": {
    "fictional": true,
    "persona": { "persona_id": "robert", "display_name": "Robert", "case_reference": "Case p.7" },
    "portfolio": {
      "schema_version": "1.0.0",
      "portfolio_id": "pf-robert-fictional-1",
      "persona_id": "robert",
      "fictional": true,
      "valuation_date": "2026-11-12",
      "base_currency": "CAD",
      "cash_weight": 0.3,
      "positions": [
        { "instrument_id": "XBB.TO", "weight": 0.3 },
        { "instrument_id": "SPY", "weight": 0.2 },
        { "instrument_id": "XIU.TO", "weight": 0.1 },
        { "instrument_id": "RY.TO", "weight": 0.05 },
        { "instrument_id": "JNJ", "weight": 0.05 }
      ]
    }
  },
  "purchasable_instrument_ids": ["JNJ", "NVDA", "RY.TO", "SPY", "XBB.TO", "XIU.TO"]
}
```

- `scenario.scenario_rules` are **offered** rules: status `PROPOSED`, origin `FICTIONAL_SCENARIO`.
  They are inactive until the user confirms them with `POST /rules/confirm`.
- `instruments` holds the registry entry of every position and every purchasable instrument.
- `purchasable_instrument_ids`: instruments that are in the registry **and** have a price series.
- No route reads a stored policy. The client keeps the `policy` returned by `POST /rules/confirm`
  and by a `CHANGE_RULE` challenge for the session.

## 3. POST /rules/interpret

Turns the user's words into a **draft** (`interpretation.schema.json`). It never stores anything
and never changes a policy.

**Decision: synchronous, with a hard server deadline of 20 s** for the whole handler (model calls
and validation), well under the 30 s API Gateway limit. When the deadline passes the route answers
with a structured error instead of a late result. A job would add polling to a call that normally
takes a few seconds and whose result nothing else depends on.

Request: `api.schema.json#/$defs/interpret_request`. `text` is 1 to 2000 characters and is data,
not instruction. `policy_id` and `policy_version` are optional context (both `null`, or both set).

<!-- fixture: interpret_mateo_clarification request_body complete -->
```json
{
  "persona_id": "mateo",
  "text": "Balanced growth over 8 to 12 years; ESG matters to me; I want to avoid oil and companies involved in significant controversies.",
  "policy_id": null,
  "policy_version": null
}
```

| Status | Body |
|---|---|
| 200 | `interpretation.schema.json` |
| 400 | `VALIDATION_ERROR` |
| 404 | `NOT_FOUND`: persona, or the policy version given as context |
| 429 | `RATE_LIMITED` |
| 502 | `INTERPRETER_FAILED`: model error, or output that failed validation after the bounded retry |
| 504 | `INTERPRETER_TIMEOUT` (`fixtures/api/error_interpreter_timeout.json`) |

<!-- fixture: interpret_mateo_clarification response_body excerpt -->
```json
{
  "schema_version": "1.0.0",
  "interpretation_id": "int-mateo-0001",
  "persona_id": "mateo",
  "model_id": "us.anthropic.claude-sonnet-5-5",
  "objectives": [
    { "objective_id": "obj-1", "original_words": "Balanced growth over 8 to 12 years", "kind": "goal", "source": "USER_STATED", "case_reference": null },
    { "objective_id": "obj-2", "original_words": "ESG matters to me", "kind": "preference", "source": "USER_STATED", "case_reference": null },
    { "objective_id": "obj-3", "original_words": "I want to avoid oil and companies involved in significant controversies", "kind": "constraint", "source": "USER_STATED", "case_reference": null }
  ],
  "proposed_rules": [
    { "rule_id": "draft-controversy-1", "rule_type": "controversy_exclusion", "threshold": null, "threshold_source": null, "status": "PROPOSED", "origin": "SYSTEM_PROPOSED" }
  ],
  "unsupported": []
}
```

- Every proposed rule is `PROPOSED`. It carries a number only when the user's own words contain
  it (`threshold_source: "USER_WORDS"` with the quoted span). Otherwise it is `SYSTEM_PROPOSED`
  with `threshold: null`: the interpreter never invents a number.
- Ambiguous wording ("oil") produces a `clarifications[]` entry with at least two options. A
  supported option carries the draft it leads to (`proposed_rule` or `purchase_request`), so
  choosing it needs no second call. An option with `supported: false` is shown disabled.
- The server validates the model output (`byb_contracts.validate_interpretation`) and answers 502
  rather than passing on an invalid draft.
- On 502 or 504 the client keeps the user's text and offers a retry. The scenario rules can still
  be confirmed without the interpreter.

## 4. POST /rules/confirm

Creates a new, immutable policy version from rules the user explicitly confirmed. This is the only
way a rule becomes `CONFIRMED`, apart from a `CHANGE_RULE` challenge.

Request: `api.schema.json#/$defs/confirm_request`. The rule objects are shortened in this excerpt;
send each one complete, as displayed (`fixtures/api/confirm_robert_v1.json`).

<!-- fixture: confirm_robert_v1 request_body excerpt -->
```json
{
  "persona_id": "robert",
  "policy_id": null,
  "base_version": null,
  "confirmations": [
    { "rule": { "rule_id": "robert-issuer-cap-1", "rule_type": "max_issuer_exposure", "status": "PROPOSED", "origin": "FICTIONAL_SCENARIO", "threshold": 0.1 }, "threshold": 0.1 },
    { "rule": { "rule_id": "robert-loss-budget-1", "rule_type": "scenario_loss_budget", "status": "PROPOSED", "origin": "FICTIONAL_SCENARIO", "threshold": 0.1 }, "threshold": 0.1 }
  ],
  "withdraw_rule_ids": [],
  "change_note": "Fictional-scenario rules confirmed by the user."
}
```

| Status | Body |
|---|---|
| 201 | `api.schema.json#/$defs/confirm_response`: the new policy version |
| 400 | `VALIDATION_ERROR` |
| 404 | `NOT_FOUND`: persona or policy |
| 409 | `POLICY_VERSION_CONFLICT` (`fixtures/api/error_policy_version_conflict.json`) |
| 422 | `INVALID_CONFIRMATION` |

<!-- fixture: confirm_robert_v1 response_body excerpt -->
```json
{
  "schema_version": "1.0.0",
  "policy": {
    "policy_id": "pol-robert-demo",
    "persona_id": "robert",
    "version": 1,
    "parent_version": null,
    "rules": [
      { "rule_id": "robert-issuer-cap-1", "status": "CONFIRMED", "threshold": 0.1, "threshold_source": "FICTIONAL_SCENARIO", "confirmed_at": "2026-11-14T15:00:00Z", "confirmed_by": "demo_user" },
      { "rule_id": "robert-loss-budget-1", "status": "CONFIRMED", "threshold": 0.1, "threshold_source": "FICTIONAL_SCENARIO", "confirmed_at": "2026-11-14T15:00:00Z", "confirmed_by": "demo_user" }
    ],
    "change_note": "Fictional-scenario rules confirmed by the user."
  }
}
```

Server rules:

1. `policy_id: null` creates a policy at version 1 (`base_version` must be `null`). Otherwise
   `base_version` must be the latest stored version (else 409) and the new version is
   `base_version + 1` with `parent_version = base_version`.
2. `confirmations[].threshold` is the number the user entered, selected or accepted. It is always
   required: a rule cannot be confirmed without a number.
3. The server writes the stored rule; the client does not. `status: "CONFIRMED"`, `confirmed_at`
   (server time), `confirmed_by: "demo_user"`, and the provenance:
   - the submitted rule is `FICTIONAL_SCENARIO` and `threshold` equals its number: it stays
     `FICTIONAL_SCENARIO`;
   - the submitted rule is `USER_WORDS` and `threshold` equals its number: `USER_STATED` /
     `USER_WORDS`, quote kept;
   - anything else: `USER_STATED` / `USER_ENTERED`, `threshold_quote: null`.
4. Replacing a rule: the submitted rule has a **new** `rule_id` and names the rule it replaces in
   `supersedes_rule_id`. Withdrawing a rule: list it in `withdraw_rule_ids`. In the new version the
   old rule stays, as `SUPERSEDED` (`superseded_by_rule_id` is the replacement, or `null` when
   withdrawn).
5. Rule order of the new version (it is "policy order" everywhere else): the rules of the base
   version in their order, a replacement placed directly after the rule it supersedes, then the
   other new rules in the order of `confirmations`.
6. `objectives` is the complete objective list of the new version. `change_note: null` makes the
   server write a template note. `content_hash` is computed by the server
   (`byb_contracts.compute_content_hash`).
7. 422 `INVALID_CONFIRMATION` when: there is neither a confirmation nor a withdrawal; a submitted
   rule is not `PROPOSED`; a `rule_id` is already used in the policy or twice in the request;
   `supersedes_rule_id` or a withdrawn id is not a `CONFIRMED` rule of `base_version`; a rule is
   both replaced and withdrawn; a replacement has another `rule_type` than the rule it replaces;
   a rule's `objective_id` is not in `objectives`.
8. Earlier versions stay stored and unchanged. On 409 the client drops its policy state and starts
   the rule stage again: there is no route that reads a stored policy.

## 5. POST /check

Deterministic and bounded: no model, no storage, 5 s budget. It runs the engine once and returns
the full `check_result.schema.json`.

Request: `api.schema.json#/$defs/check_request`. `draft_rules` selects the mode:

| `draft_rules` | What is evaluated | Result |
|---|---|---|
| `null` | The stored policy version `policy_id` / `policy_version` (both required) | `preview: false`, `policy_id` and `policy_version` echoed |
| an array of rules | **Exactly these rules, instead of any stored policy** | `preview: true`, `policy_id: null`, `policy_version: null` |

**A preview never reads the stored rules and never changes the stored policy.** It exists for
sliders and "what if" drafts, and the UI must label it as a preview. In a preview:

- rules that carry a number and are `PROPOSED` or `CONFIRMED` are evaluated; the others are listed
  in `rules_not_evaluated`;
- every evidence record has `policy_version: null`, and a draft threshold is labelled `ASSUMPTION`;
- `policy_id` and `policy_version` may be sent as context only: `goal_context` then uses the
  objectives of that version. With both `null`, `goal_context` is `[]`;
- a preview cannot be investigated. To make a draft number count, confirm it first
  (`POST /rules/confirm`), then use the new policy version.

Preview request (rule objects shortened; `fixtures/api/check_robert_preview.json` has them complete):

<!-- fixture: check_robert_preview request_body excerpt -->
```json
{
  "persona_id": "robert",
  "policy_id": "pol-robert-demo",
  "policy_version": 1,
  "purchase_request": {
    "instrument_id": "NVDA",
    "target_direct_weight": 0.25,
    "funding": "CASH",
    "original_words": "Everyone is talking about Nvidia. I want it to be 25% of my portfolio."
  },
  "draft_rules": [
    { "rule_id": "robert-issuer-cap-1", "status": "PROPOSED", "origin": "USER_STATED", "threshold_source": "USER_ENTERED", "threshold": 0.2 },
    { "rule_id": "robert-loss-budget-1", "status": "CONFIRMED", "origin": "FICTIONAL_SCENARIO", "threshold_source": "FICTIONAL_SCENARIO", "threshold": 0.1 }
  ]
}
```

<!-- fixture: check_robert_preview response_body excerpt -->
```json
{
  "schema_version": "1.0.0",
  "persona_id": "robert",
  "portfolio_id": "pf-robert-fictional-1",
  "policy_id": null,
  "policy_version": null,
  "preview": true,
  "valuation_date": "2026-11-12",
  "execution": { "status": "OK", "code": null, "message": null },
  "feasibility": {
    "funding": "CASH",
    "starting_direct_weight": 0.0,
    "target_direct_weight": 0.25,
    "additional_purchase": 0.25,
    "cash_before": 0.3,
    "cash_after": 0.05,
    "status": "FEASIBLE"
  },
  "policy_consistency": { "status": "CONSISTENT", "conflicts": [] },
  "rule_results": [
    { "rule_id": "robert-issuer-cap-1", "status": "FAIL", "measured": { "lower": 0.262, "upper": 0.264 }, "limit": 0.2, "gap": 0.062 },
    { "rule_id": "robert-loss-budget-1", "status": "FAIL", "measured": { "lower": 0.1525, "upper": 0.1525 }, "limit": 0.1, "gap": 0.0525 }
  ],
  "max_compliant": {
    "status": "SUPPORTED",
    "final_direct_weight": 0.1,
    "additional_purchase": 0.1,
    "binding_constraint": { "type": "RULE", "rule_id": "robert-loss-budget-1" },
    "verified_by_rerun": true
  },
  "summary": {
    "headline": "HAS_FAIL",
    "counts": { "pass": 0, "fail": 2, "unknown": 0 },
    "rules_evaluated": 2,
    "rules_not_evaluated": 0,
    "starting_portfolio_breaches": 0,
    "feasibility_status": "FEASIBLE"
  }
}
```

A rule that can be neither proven to pass nor proven to fail has status `UNKNOWN`: both bounds, a
`null` gap and at least one `unknown_causes` entry. Show it as unknown, never as a pass. Example: a
draft limit of 0.20 on any single company, on a portfolio that holds a fund without a holdings file
(`fixtures/api/check_mateo_preview_unknown.json`, sent without a policy, so `goal_context` is empty):

<!-- fixture: check_mateo_preview_unknown response_body excerpt -->
```json
{
  "preview": true,
  "policy_id": null,
  "policy_version": null,
  "rule_results": [
    {
      "rule_id": "mateo-issuer-cap-draft",
      "rule_type": "max_issuer_exposure",
      "status": "UNKNOWN",
      "measured": { "lower": 0.059, "upper": 0.213 },
      "limit": 0.2,
      "gap": null,
      "breaching_subjects": [],
      "unknown_causes": ["MISSING_HOLDINGS", "PARTIAL_HOLDINGS"],
      "starting": { "status": "UNKNOWN", "measured": { "lower": 0.056, "upper": 0.21 } }
    }
  ],
  "starting_portfolio_findings": [],
  "goal_context": [],
  "max_compliant": {
    "status": "WITHHELD",
    "final_direct_weight": null,
    "additional_purchase": null,
    "binding_constraint": null,
    "verified_by_rerun": false
  },
  "summary": {
    "headline": "NO_FAIL_BUT_UNKNOWN",
    "counts": { "pass": 0, "fail": 0, "unknown": 1 },
    "rules_evaluated": 1,
    "rules_not_evaluated": 0,
    "starting_portfolio_breaches": 0,
    "feasibility_status": "FEASIBLE"
  }
}
```

| Status | Body |
|---|---|
| 200 | `check_result.schema.json`, **including** a request the engine refuses (`execution.status: "INVALID_REQUEST"`) and a controlled engine failure (`execution.status: "ERROR"`) |
| 400 | `VALIDATION_ERROR`: the body does not match the schema, or `draft_rules` is `null` without `policy_id` and `policy_version` (`fixtures/api/error_validation.json`) |
| 404 | `NOT_FOUND`: persona, policy or policy version |
| 500 | `INTERNAL_ERROR`: no result document could be produced |

A request the engine refuses is a normal answer, not an HTTP error. Nothing is evaluated:

<!-- fixture: check_invalid_request request_body complete -->
```json
{
  "persona_id": "robert",
  "policy_id": "pol-robert-demo",
  "policy_version": 1,
  "purchase_request": { "instrument_id": "RY.TO", "target_direct_weight": 0.02, "funding": "CASH", "original_words": "Cut my Royal Bank position to 2%." },
  "draft_rules": null
}
```

<!-- fixture: check_invalid_request response_body excerpt -->
```json
{
  "preview": false,
  "policy_id": "pol-robert-demo",
  "policy_version": 1,
  "execution": {
    "status": "INVALID_REQUEST",
    "code": "TARGET_BELOW_CURRENT_WEIGHT",
    "message": "The requested final direct weight of RY.TO (2.0%) is below its current direct weight (5.0%). Only cash-funded purchases are simulated; selling is not supported."
  },
  "feasibility": null,
  "policy_consistency": { "status": "NOT_ASSESSED", "conflicts": [] },
  "rule_results": [],
  "scenario": null,
  "max_compliant": null,
  "exposure": null,
  "summary": {
    "headline": "INVALID_REQUEST",
    "counts": { "pass": 0, "fail": 0, "unknown": 0 },
    "rules_evaluated": 0,
    "rules_not_evaluated": 0,
    "starting_portfolio_breaches": 0,
    "feasibility_status": null
  }
}
```

Client rules for sliders: debounce the calls (250 ms suggested), number them, and ignore any
response older than the latest request sent. The route is stateless, so ordering is the client's
job. Retrying is always safe.

## 6. POST /investigations

Starts an asynchronous investigation of one purchase against one **stored** policy version.

```http
Authorization: Bearer <access code>
Content-Type: application/json
Idempotency-Key: 0b6f0c9e-5a7e-4c0e-9a55-1f2d3c4b5a61
```

`Idempotency-Key` is required and matches `^[A-Za-z0-9_-]{8,64}$` (a UUID fits). The client
creates one key per user action and reuses it when it retries that action.

Request: `api.schema.json#/$defs/investigation_create_request`.

<!-- fixture: investigation_accepted request_body complete -->
```json
{
  "persona_id": "robert",
  "policy_id": "pol-robert-demo",
  "policy_version": 1,
  "request": {
    "instrument_id": "NVDA",
    "target_direct_weight": 0.25,
    "funding": "CASH",
    "original_words": "Everyone is talking about Nvidia. I want it to be 25% of my portfolio."
  },
  "parent_investigation_id": null
}
```

| Status | Body |
|---|---|
| 202 | `api.schema.json#/$defs/investigation_accepted` |
| 400 | `VALIDATION_ERROR`: body, or `Idempotency-Key` missing or malformed (`path: "headers.Idempotency-Key"`) |
| 404 | `NOT_FOUND`: persona, policy, policy version or parent investigation |
| 409 | `IDEMPOTENCY_KEY_REUSED` |
| 422 | `INVALID_PURCHASE_REQUEST` |
| 503 | `WORKER_INVOCATION_FAILED` |

<!-- fixture: investigation_accepted response_body complete -->
```json
{
  "schema_version": "1.0.0",
  "id": "inv-robert-0001",
  "status": "QUEUED",
  "created_at": "2026-11-14T15:02:00Z",
  "deadline_at": "2026-11-14T15:04:30Z",
  "expires_at": "2026-11-15T15:02:00Z",
  "poll": { "path": "/investigations/inv-robert-0001", "interval_ms": 1500 }
}
```

Server rules:

1. Order: validate the request, store the job as `QUEUED`, invoke the worker asynchronously, and
   answer 202 **only after the invocation was accepted**. The 202 is sent before any model call.
2. Idempotency. The same key with the same body (equal after canonical JSON serialization) returns
   202 with the **same** `id`; `status` is the job's current status; no second job is created and
   no second result is ever produced. If the replayed job is still `QUEUED`, the service may invoke
   the worker again to recover a first invocation that was lost; a delivery for a job that is
   already claimed or terminal does nothing (no model call, no state change). The same key with a
   different body is 409. Keys are remembered until the job expires.
3. A structured request is checked against the persona's portfolio before the job is stored. If the
   engine would answer `INVALID_REQUEST`, the route answers 422 and `details[0].issue` starts with
   the execution code (for example `TARGET_BELOW_CURRENT_WEIGHT: ...`).
4. A free-text request (`instrument_id` and `target_direct_weight` are `null`, `original_words` is
   set) is accepted. The investigator resolves it into `resolved_request`, or asks: the job then
   ends `SUCCEEDED` with `clarification` set and `result: null`
   (`fixtures/api/investigation_amira_clarification.json`). The client answers by sending a **new**
   `POST /investigations` (new key) whose `request` is the chosen option's `purchase_request` and
   whose `parent_investigation_id` is the id of the job that asked.
5. If the worker cannot be started, the stored job is marked `FAILED`
   (`failure.code: "WORKER_INVOCATION_FAILED"`, `retryable: true`) and the route answers 503. The
   client retries with a **new** key.

## 7. GET /investigations/{id}

Returns the job (`investigation_job.schema.json`). Lifecycle `QUEUED -> RUNNING -> SUCCEEDED | FAILED`.

| Status | Body |
|---|---|
| 200 | The job, in **any** state. A `FAILED` job is a 200 |
| 404 | `NOT_FOUND` (`fixtures/api/error_not_found.json`) |
| 410 | `INVESTIGATION_EXPIRED` |

A running job shows the tool events completed so far and the one in progress:

<!-- fixture: investigation_robert_running response_body excerpt -->
```json
{
  "id": "inv-robert-0001",
  "status": "RUNNING",
  "agent": { "mode": "MODEL", "model_id": "us.anthropic.claude-sonnet-5-5", "tool_rounds": 3, "note": null },
  "steps": [
    { "seq": 1, "tool": "get_portfolio", "initiated_by": "MODEL", "status": "OK", "finished_at": "2026-11-14T15:02:05Z" },
    { "seq": 2, "tool": "get_policy", "initiated_by": "MODEL", "status": "OK", "finished_at": "2026-11-14T15:02:08Z" },
    { "seq": 3, "tool": "simulate_change", "initiated_by": "MODEL", "status": "OK", "finished_at": "2026-11-14T15:02:11Z" },
    { "seq": 4, "tool": "get_holdings", "initiated_by": "MODEL", "status": "OK", "finished_at": "2026-11-14T15:02:14Z" },
    { "seq": 5, "tool": "compute_exposure", "initiated_by": "MODEL", "status": "RUNNING", "finished_at": null, "result_summary": null }
  ],
  "clarification": null,
  "result": null,
  "explanation": [],
  "failure": null
}
```

A finished job carries the engine result, the explanation and no failure:

<!-- fixture: investigation_robert_succeeded response_body excerpt -->
```json
{
  "id": "inv-robert-0001",
  "status": "SUCCEEDED",
  "created_at": "2026-11-14T15:02:00Z",
  "updated_at": "2026-11-14T15:02:27Z",
  "deadline_at": "2026-11-14T15:04:30Z",
  "expires_at": "2026-11-15T15:02:00Z",
  "idempotency_key": "0b6f0c9e-5a7e-4c0e-9a55-1f2d3c4b5a61",
  "policy_id": "pol-robert-demo",
  "policy_version": 1,
  "parent_investigation_id": null,
  "challenge": null,
  "clarification": null,
  "result": {
    "preview": false,
    "policy_version": 1,
    "max_compliant": {
      "status": "SUPPORTED",
      "final_direct_weight": 0.086,
      "additional_purchase": 0.086,
      "binding_constraint": { "type": "RULE", "rule_id": "robert-issuer-cap-1" },
      "verified_by_rerun": true
    },
    "summary": {
      "headline": "HAS_FAIL",
      "counts": { "pass": 0, "fail": 2, "unknown": 0 },
      "rules_evaluated": 2,
      "rules_not_evaluated": 0,
      "starting_portfolio_breaches": 0,
      "feasibility_status": "FEASIBLE"
    }
  },
  "failure": null,
  "proposed_corrections": []
}
```

A failed job has a `failure`, no `result` and no explanation. It never shows a partial verdict:

<!-- fixture: investigation_failed response_body excerpt -->
```json
{
  "id": "inv-failed-0001",
  "status": "FAILED",
  "clarification": null,
  "result": null,
  "explanation": [],
  "failure": {
    "code": "DATA_UNAVAILABLE",
    "message": "The holdings snapshot could not be read, so no check was run and no result was produced. Nothing was assumed in its place.",
    "retryable": true
  }
}
```

State rules (enforced by the schema and `byb_contracts.validate_investigation_job`):

- `QUEUED`: no steps, result, clarification, failure or explanation.
- `RUNNING`: steps grow; the last one may be `RUNNING` (`finished_at: null`). No outcome yet.
- `SUCCEEDED`: `result` and/or `clarification` is set; `failure` is `null`; no step is `RUNNING`.
- `FAILED`: `failure` is set; `result` and `clarification` are `null`; `explanation` is empty.
- `steps` are real tool events with template-rendered summaries, never model reasoning.
  `initiated_by: "SERVER"` marks a check the service ran whatever the model did.
- `result` is the engine's output. The model cannot alter it. Every evidence id cited by a step or
  an explanation statement exists in `result.evidence`.
- **Terminal results are immutable.** Once a response shows `SUCCEEDED` or `FAILED`, the members
  `status`, `steps`, `result`, `explanation`, `clarification` and `failure` never change. Only
  `proposed_corrections` can grow.

Polling:

1. Poll `poll.path` every `poll.interval_ms` (1500 ms) until the status is `SUCCEEDED` or `FAILED`.
2. The server enforces the job deadline: after `deadline_at` (`created_at` + 150 s) the route never
   answers `QUEUED` or `RUNNING` again; a job that did not finish is `FAILED` with
   `failure.code: "DEADLINE_EXCEEDED"`. The worker must not write to a job that is already terminal.
3. The client enforces its own deadline as well: **180 s after the 202** it stops polling and shows
   a visible failure state ("the investigation did not finish in time"), keeping the id. 180 s is
   longer than the job deadline on purpose, so that the client normally sees the server's terminal
   state first. Measure it with a client timer, not by comparing clocks.
4. During polling, a network error, a 429 or a 5xx is retried at the same interval until the client
   deadline. 401 or 403: stop and ask for the access code. 404 or 410: stop.
5. After `expires_at` the route answers 410 while the record exists, and 404 once it was deleted.

## 8. POST /investigations/{id}/challenge

The user disputes a finished investigation. Request: `api.schema.json#/$defs/challenge_request`;
response: `api.schema.json#/$defs/challenge_response`, in which exactly the members that belong to
the challenge type are non-null.

| `type` | Status | Non-null members | Effect |
|---|---|---|---|
| `CORRECT_FACT` | 201 | `proposed_correction` | Stores an **unverified** correction next to the disputed evidence. Nothing is recomputed |
| `CLARIFY_PREFERENCE` | 200 | `interpretation` | Returns a new **draft**. Nothing stored changes |
| `CHANGE_RULE` | 202 | `policy`, `investigation` | Creates a new policy version and a child investigation |

Errors for every type: 400 `VALIDATION_ERROR`; 404 `NOT_FOUND`; 409 `INVESTIGATION_NOT_FINISHED`
(the job is `QUEUED` or `RUNNING`); 410 `INVESTIGATION_EXPIRED`; 422 `UNSUPPORTED_CHALLENGE` (the
job is `FAILED`, or the conditions listed per type below are not met).

### CORRECT_FACT

<!-- fixture: challenge_correct_fact request_body complete -->
```json
{
  "type": "CORRECT_FACT",
  "payload": {
    "evidence_id": "ev-spy-nvda-weight",
    "asserted_value": 0.08,
    "asserted_unit": "fraction",
    "user_note": "The fund fact sheet I have shows a higher NVIDIA weight in SPY.",
    "user_source": "SPY fact sheet, user's own copy (not retrieved by the system)"
  }
}
```

<!-- fixture: challenge_correct_fact response_body excerpt -->
```json
{
  "schema_version": "1.0.0",
  "challenge": { "challenge_id": "ch-robert-0002", "investigation_id": "inv-robert-0001", "type": "CORRECT_FACT" },
  "proposed_correction": {
    "correction_id": "corr-robert-0001",
    "challenge_id": "ch-robert-0002",
    "investigation_id": "inv-robert-0001",
    "evidence_id": "ev-spy-nvda-weight",
    "original_value": 0.06,
    "original_unit": "fraction",
    "asserted_value": 0.08,
    "asserted_unit": "fraction",
    "provenance": {
      "asserted_by": "USER",
      "asserted_at": "2026-11-14T15:09:00Z",
      "user_note": "The fund fact sheet I have shows a higher NVIDIA weight in SPY.",
      "user_source": "SPY fact sheet, user's own copy (not retrieved by the system)"
    },
    "status": "UNVERIFIED",
    "applied_to_calculation": false
  },
  "interpretation": null,
  "policy": null,
  "investigation": null
}
```

- Conditions (else 422): the job has a `result`; `evidence_id` is in `result.evidence`;
  `asserted_unit` equals the unit of that record; the value is a number for numeric units and a
  string for `date` and `text`.
- The correction is appended to the job's `proposed_corrections`
  (`fixtures/api/investigation_robert_with_correction.json`). The disputed evidence record, the
  result and the policy are untouched. Schema version 1 never applies a correction to a
  calculation, and the UI must show it as an unverified user assertion, never as a fact.
- `user_note` and `user_source` are stored and displayed verbatim. They are never obeyed and the
  source is not fetched.
- No idempotency key: a repeated request stores a second correction. Disable the button while the
  request is pending.

### CLARIFY_PREFERENCE

<!-- fixture: challenge_clarify_preference request_body complete -->
```json
{
  "type": "CLARIFY_PREFERENCE",
  "payload": {
    "text": "By oil I meant companies that produce oil, not pipelines or utilities.",
    "objective_id": "obj-mateo-1"
  }
}
```

<!-- fixture: challenge_clarify_preference response_body excerpt -->
```json
{
  "schema_version": "1.0.0",
  "challenge": { "challenge_id": "ch-mateo-0001", "investigation_id": "inv-mateo-0001", "type": "CLARIFY_PREFERENCE" },
  "proposed_correction": null,
  "interpretation": {
    "interpretation_id": "int-mateo-0002",
    "persona_id": "mateo",
    "original_words": "By oil I meant companies that produce oil, not pipelines or utilities.",
    "proposed_rules": [],
    "unsupported": [
      {
        "words": "companies that produce oil",
        "code": "UNSUPPORTED_DEFINITION",
        "reason": "We hold no sourced classification of oil producers. The confirmed Energy-label rule stays as it is until you confirm a change."
      }
    ]
  },
  "policy": null,
  "investigation": null
}
```

- The interpretation is a draft, exactly as in section 3, including the 20 s deadline and the 502
  and 504 answers. To act on it the user confirms a rule with `POST /rules/confirm`.
- Condition (else 422): `objective_id`, when set, is an objective of the job's policy version.

### CHANGE_RULE

An explicit confirmation of a new number by the user. It needs an `Idempotency-Key` header, as in
section 6.

<!-- fixture: challenge_change_rule request_body complete -->
```json
{
  "type": "CHANGE_RULE",
  "payload": {
    "rule_id": "robert-issuer-cap-1",
    "new_threshold": 0.3,
    "user_note": "Raise my single-company limit to 30%."
  }
}
```

<!-- fixture: challenge_change_rule response_body excerpt -->
```json
{
  "schema_version": "1.0.0",
  "challenge": {
    "challenge_id": "ch-robert-0001",
    "investigation_id": "inv-robert-0001",
    "type": "CHANGE_RULE",
    "payload": { "rule_id": "robert-issuer-cap-1", "new_threshold": 0.3, "user_note": "Raise my single-company limit to 30%." },
    "created_at": "2026-11-14T15:06:00Z"
  },
  "proposed_correction": null,
  "interpretation": null,
  "policy": {
    "policy_id": "pol-robert-demo",
    "version": 2,
    "parent_version": 1,
    "rules": [
      { "rule_id": "robert-issuer-cap-1", "status": "SUPERSEDED", "threshold": 0.1, "supersedes_rule_id": null, "superseded_by_rule_id": "robert-issuer-cap-2" },
      { "rule_id": "robert-issuer-cap-2", "status": "CONFIRMED", "threshold": 0.3, "origin": "USER_STATED", "threshold_source": "USER_ENTERED", "supersedes_rule_id": "robert-issuer-cap-1", "superseded_by_rule_id": null },
      { "rule_id": "robert-loss-budget-1", "status": "CONFIRMED", "threshold": 0.1, "supersedes_rule_id": null, "superseded_by_rule_id": null }
    ]
  },
  "investigation": {
    "schema_version": "1.0.0",
    "id": "inv-robert-0002",
    "status": "QUEUED",
    "created_at": "2026-11-14T15:06:00Z",
    "deadline_at": "2026-11-14T15:08:30Z",
    "expires_at": "2026-11-15T15:06:00Z",
    "poll": { "path": "/investigations/inv-robert-0002", "interval_ms": 1500 }
  }
}
```

- Conditions (else 422): the job has a `result`; `rule_id` is a `CONFIRMED` rule of the job's
  policy version; `new_threshold` differs from that rule's number.
- New policy version: number = latest stored version + 1, `parent_version` = the job's policy
  version. Its rules are those of the job's version with the challenged rule kept as `SUPERSEDED`
  and its replacement placed directly after it: a server-generated new `rule_id`, the same type,
  parameters and wording, `threshold = new_threshold`, `origin: "USER_STATED"`,
  `threshold_source: "USER_ENTERED"`, `status: "CONFIRMED"`, `supersedes_rule_id` = the old rule.
- Child investigation: `parent_investigation_id` = the challenged job, `challenge` = this
  challenge, the same resolved purchase request, the new policy version. Poll it as in section 7
  (`fixtures/api/investigation_robert_after_challenge_succeeded.json`).
- **The earlier policy version and the earlier report are preserved and unchanged**; both stay
  retrievable, which is what the old/new comparison uses.
- Idempotency: the same key with the same body returns the same response (same policy version, same
  child `id`); with a different body, 409 `IDEMPOTENCY_KEY_REUSED`.
  The service first reserves the child job with a fixed challenge timestamp and version candidate.
  It then writes the policy and marks the reservation ready before dispatching the worker.
  Concurrent retries resume this reservation; an interrupted policy write is recovered by comparing
  the stored policy with the reserved operation. A version occupied by another operation advances
  the reservation using a conditional write. The response always reads the child's stored policy.
  Jobs from earlier deployments remain readable without a readiness marker.
- If the worker cannot be started the route answers 503 `WORKER_INVOCATION_FAILED`. The client
  retries the challenge with a **new** key; a policy version left unused by the failed attempt is
  harmless, because a `CHANGE_RULE` always derives from the challenged job's version.

The worker requires its data snapshot to match the snapshot recorded when a job was accepted.
A deployment mismatch ends the job as `FAILED / DATA_UNAVAILABLE`, with no calculated result;
it never silently replaces the accepted snapshot identifier. Retry as a new investigation once
the API and worker are configured consistently.

## 9. Example index (`fixtures/api/`)

| Route | Fixtures |
|---|---|
| `GET /portfolios/{persona_id}` | `portfolio_robert`, `portfolio_amira`, `error_unauthorized` (401) |
| `POST /rules/interpret` | `interpret_mateo_clarification`, `interpret_amira_ambiguous`, `error_interpreter_timeout` (504) |
| `POST /rules/confirm` | `confirm_robert_v1` (201), `error_policy_version_conflict` (409) |
| `POST /check` | `check_robert_preview`, `check_mateo_preview_unknown`, `check_invalid_request`, `error_validation` (400) |
| `POST /investigations` | `investigation_accepted` (202) |
| `GET /investigations/{id}` | `investigation_robert_queued`, `investigation_robert_running`, `investigation_robert_succeeded`, `investigation_robert_after_challenge_succeeded`, `investigation_robert_with_correction`, `investigation_mateo_succeeded`, `investigation_amira_clarification`, `investigation_failed`, `error_not_found` (404) |
| `POST /investigations/{id}/challenge` | `challenge_correct_fact` (201), `challenge_clarify_preference` (200), `challenge_change_rule` (202) |

Every number in these fixtures is synthetic or fictional and is labelled so in the file. Validate a
body with `byb_contracts.validate_api_body(schema_ref, body)`.
