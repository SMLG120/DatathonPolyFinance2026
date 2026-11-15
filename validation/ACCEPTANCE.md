# Before You Buy: acceptance criteria (go / no-go)

Owner: independent validator (A4). Written against commit `d36e41f` from `docs/BUILD_BRIEF.md` (BB),
`docs/LEAD_DECISIONS.md` (D1..D9), `contracts/SEMANTICS.md` (SEM), `contracts/api.md` (API),
`docs/data-sources.md` (DS) and `docs/requirements.md`. The criteria describe the product the documents
require, not the product that happens to exist. Results are in `validation/REPORT.md`.

## 1. Severity classes

| Class | Definition | Effect on release |
|---|---|---|
| **BLOCKER** | Any defect, reachable through a supported input path of the release candidate (a route, a stored document the service reads, a model output, a data file the service loads), that produces one of: (a) **false pass**: a rule, summary, headline, maximum or explanation states or implies PASS / "respected" / "within the limit" when the documented arithmetic gives FAIL or UNKNOWN; (b) **policy bypass**: a rule is evaluated, activated, changed or skipped without the user's explicit confirmation, or a confirmed applicable rule is not evaluated, or a model/user text changes what is calculated; (c) a recommendation, a forecast or an order is produced; (d) a fabricated number, source or evidence record is presented as measured or verified; (e) a secret or licence-restricted data reaches the repository, the bundle, a log or a response; (f) an unauthenticated caller reaches any route. | No-go. **One blocker is a no-go whatever the aggregate pass rate is** (BB 9: "Critical policy-bypass or false-pass defects are blockers even if an aggregate score exceeds 80%"). No averaging, no waiver by score. |
| **HIGH** | A wrong or misleading result that is not a false pass or bypass (false FAIL, wrong number shown, wrong evidence linked), a blocker-class defect that is *not reachable* through a supported input path today but becomes one if an input path is added, a terminal result that can change, a failure that is not visible to the user, a missing contract route. | No-go unless fixed, or the lead records an explicit, dated acceptance with the reason. |
| **MEDIUM** | Contract deviation without a wrong verdict, weak hardening, sub-tolerance numerical deviation, misleading wording, duplicated logic that can drift. | Must be listed in the release notes; fix or accept. |
| **LOW** | Documentation inconsistency, hygiene, disclosure without a credential. | Listed; does not block. |

A criterion is **PASS** only when its check ran and passed on the build under judgement. A criterion whose check
could not run is **NOT TESTABLE YET** (with the reason); it is never counted as a pass. A skipped test is not a pass.

How to run every automated check:

    uv run --no-project --python 3.14 --with pytest --with boto3 --with jsonschema pytest validation -q -rsx

Test ids below are the `Vnn` labels (`pytest.mark.vcase`); `pytest validation -k v13` selects one. Known defects are
kept as `xfail(strict=True)`: when a defect is fixed the test turns into an unexpected pass, the run fails, and the
marker must be removed deliberately.

## 2. Criteria

### A. Financial correctness

| Id | Criterion | Source | Check | Class if violated |
|---|---|---|---|---|
| AC-F1 | Issuer exposure = direct weight + sum over funds of fund weight x constituent weight; share classes of one issuer are added; all values are fractions. | BB 2; D3; SEM 3 | V01, V03, V15, V20 | BLOCKER |
| AC-F2 | Missing or partial holdings give an interval; the uncovered part is added to the upper bound only; lower <= upper; nothing is rescaled. | BB 2, 4; D4; SEM 4 | V04, V16, V20, V21 | BLOCKER |
| AC-F3 | PASS, FAIL, UNKNOWN follow the interval rule with tolerance 1e-9; a value exactly on the threshold passes a maximum rule; the gap has the documented sign and is null when UNKNOWN. | BB 3; SEM 6 | V02, V17 | BLOCKER |
| AC-F4 | Purchase simulation: cash-funded only; additional = target - current; target below current weight, target above cash, unknown instrument are refused with a code and no rule result. | BB 2; D5; SEM 5 | V06, V19, V28 | BLOCKER |
| AC-F5 | The maximum compliant weight is returned only when every bound involved is known and supported, never exceeds any confirmed limit, is verified by re-running the check, and is withheld otherwise. | BB 2, 8; SEM 8 | V13, V14 | BLOCKER (overshoot beyond tolerance) / MEDIUM (within tolerance) |
| AC-F6 | The engine equals an independent exact (rational) implementation on random portfolios and on the real data for Robert and Mateo. | BB 9 | V15, V20, V21 | BLOCKER |
| AC-F7 | Non-finite or contradictory numeric input (NaN, infinity, weights not summing to 1, negative weights, duplicate positions) never yields a verdict. | BB 4; SEM 2 | V19, V23, V28 | BLOCKER when reachable, else HIGH |

### B. Verdict integrity

| Id | Criterion | Source | Check | Class |
|---|---|---|---|---|
| AC-V1 | A proven FAIL stays visible next to UNKNOWN checks; an UNKNOWN is never counted or worded as a pass; the headline follows the documented order. | BB 3; SEM 9 | V05, V17 | BLOCKER |
| AC-V2 | Starting-portfolio breaches are reported separately from the effect of the purchase. | BB 3; SEM 6 | V05, V21 | HIGH |
| AC-V3 | Incompatible confirmed bounds are reported as a policy conflict, not resolved silently. | BB 3, 9; SEM 10 | V07 | BLOCKER |
| AC-V4 | Same inputs give the same result; the engine does not mutate its inputs and has no clock, network, randomness or model dependency. | BB 1, 6 | V17, V30 | HIGH |
| AC-V5 | The result of an investigation is the engine's result for the stored request and stored policy version, whatever the model does or says. | BB 6 | V26, V28 | BLOCKER |

### C. Policy lifecycle

| Id | Criterion | Source | Check | Class |
|---|---|---|---|---|
| AC-P1 | A rule without a confirmed number is never evaluated as active: PROPOSED rules and rules with a null threshold are listed as not evaluated. | BB 3, 9; SEM 1 | V09, V28 | BLOCKER |
| AC-P2 | Only an explicit confirmation carrying the number creates a CONFIRMED rule; the client cannot send CONFIRMED; the interpreter and the investigator cannot confirm or alter a policy. | BB 3, 6; API 4 | V28 | BLOCKER |
| AC-P3 | Policy versions are immutable; a change creates version n+1 with its parent; an old report is reproducible bit for bit from version n; content_hash is reproducible independently. | BB 3, 9; SEM 1; API 4 | V10, V28 | BLOCKER (old version altered) / HIGH |
| AC-P4 | A preview with draft thresholds is labelled, carries no policy version, and never changes or reads the stored policy. | BB 7; API 5 | V09, V28 | BLOCKER |
| AC-P5 | Ambiguous wording produces a clarification (or an unsupported marker), never an invented threshold. | BB 6, 9 | V08, V28 | BLOCKER (invented number becomes active) / HIGH |

### D. Historical metrics

| Id | Criterion | Source | Check | Class |
|---|---|---|---|---|
| AC-H1 | `replay_2022`: buy and hold from 2021-12-31 to 2022-12-30, cash at 0, adjusted close, CAD; terminal return and maximum drawdown equal an independent recomputation from the starter CSV files. | BB 5; D6; SEM 7 | V11, V20 | BLOCKER |
| AC-H2 | USD prices are converted with the USDCAD rate documented in SEM 7; a price older than 7 days or a missing series makes the metric UNKNOWN, never a proxy, zero or carried value. | BB 4, 5; SEM 7 | V11, V18 | BLOCKER |
| AC-H3 | The replay is described as a replay of an assumed allocation, never as a forecast or a maximum future loss. | BB 1, 5 | V12, V30; manual M3 | BLOCKER |

### E. Evidence

| Id | Criterion | Source | Check | Class |
|---|---|---|---|---|
| AC-E1 | Every number in a result is backed by an evidence record with metric, value, unit, subject, period, source ids or derivation, assumptions, calculation version and policy version. | BB 6; SEM 11 | V12, V20 | HIGH |
| AC-E2 | No evidence record, step or statement references an id that does not exist; the contract validators reject a result that does. | BB 6 | V12, V28 | BLOCKER (fabricated reference shown as verified) |
| AC-E3 | An explanation with the wrong asset, unit or period, an invented verdict, advice or a forecast is not shown as validated: it is rejected and replaced by a template. | BB 6, 9 | V26, V28 | BLOCKER |
| AC-E4 | A user's correction of a fact is stored as a proposed correction with provenance; it never overwrites evidence and never changes the verdict. | BB 8; API 8 | V28 | BLOCKER |

### F. Agent boundaries

| Id | Criterion | Source | Check | Class |
|---|---|---|---|---|
| AC-A1 | Only the allowlisted tools exist; an unknown tool or wrong arguments are rejected, recorded and not executed. | BB 6 | V26, V28, V30 | BLOCKER |
| AC-A2 | The server runs every applicable check itself with the stored request; the model cannot skip a rule by not calling a tool, nor substitute its own arguments. | BB 6 | V26, V28 | BLOCKER |
| AC-A3 | Instructions inside the user's text or a source are treated as data: they cannot change the calculation, the tools offered or the system prompt. | BB 6, 9 | V26, V28 | BLOCKER |
| AC-A4 | Tool rounds, tool calls, retries, tokens and runtime are bounded; throttling, timeout, truncation and empty output end in FAILED or in a labelled deterministic fallback. | BB 6, 7 | V25, V26, V28 | HIGH |
| AC-A5 | Steps shown are real tool events only; private reasoning is neither stored nor returned. | BB 6, 8 | V26 | HIGH |

### G. API and job lifecycle

| Id | Criterion | Source | Check | Class |
|---|---|---|---|---|
| AC-I1 | The seven routes of API section 1 exist with the contract request, response and error shapes. | BB 7; API | V28 | HIGH |
| AC-I2 | The validated request is stored before the worker is invoked; 202 is returned only after the invocation is accepted; otherwise 503 and a FAILED job. | BB 7; API 6 | V24, V25, V28 | HIGH |
| AC-I3 | Same idempotency key and body: one job, one worker, one result. Same key, different body: 409 and nothing changes. Duplicate delivery to the worker: no second result, no second model call. | BB 7, 9; API 6 | V24, V28 | BLOCKER (two different results for one job) / HIGH |
| AC-I4 | SUCCEEDED and FAILED are terminal and immutable; results and traces are write-once; every S3 write is conditional. | BB 7 | V24 | HIGH |
| AC-I5 | A job that is not finished at its deadline becomes a visible FAILED with a code, without a partial verdict. | BB 7; API 7 | V25, V28 | HIGH |
| AC-I6 | Malformed input (size, unknown fields, wrong types, percentage strings, NaN/Infinity, traversal-like ids) is refused with 4xx, stores nothing, starts nothing and leaks no internal detail. | API 1 | V23, V28 | HIGH |

### H. Security

| Id | Criterion | Source | Check | Class |
|---|---|---|---|---|
| AC-S1 | Every route is behind the authorizer; a missing, malformed or wrong code is never authorized; the authorizer fails closed when the stored code cannot be read. | D8; API 1 | V22, V29; live L1 | BLOCKER |
| AC-S2 | The access code, tokens and credentials never appear in a log line, a stored document, a response, the template, the repository or the bundle. | BB 7; D8 | V22, V27, V29, V30, V31 | BLOCKER |
| AC-S3 | IAM: separate roles per function, no wildcard action, no `Resource: "*"`, only reviewed prefix wildcards; S3 writes conditional; no delete. | BB 7 | V29 | HIGH |
| AC-S4 | Bucket private (four public-access-block flags), encrypted, TLS-only, job data expires. | BB 7 | V29; live L3 | BLOCKER (public) / HIGH |
| AC-S5 | CORS allows only the hosted frontend origin, the three needed headers and no credentials; throttling, reserved concurrency, timeouts and log retention are bounded. | BB 7; template `must` | V29; live L2 | MEDIUM |
| AC-S6 | Frontend: access code in sessionStorage only, no HTML injection sink, no secret in bundle inputs. | D8; BB 7 | V31; manual M1 | HIGH |

### I. Data provenance and licence

| Id | Criterion | Source | Check | Class |
|---|---|---|---|---|
| AC-D1 | Processed data equals its documented source (starter CSV adjusted close and FX; holdings figures of DS) and is not rescaled or filled. | BB 4; DS | V20 | HIGH |
| AC-D2 | Every data snapshot is validated against its contract before the engine uses it; an inconsistent snapshot (rows not matching coverage, constituent without issuer, unsorted dates) ends in a visible data error, never a verdict. | BB 4 | V19 | HIGH (BLOCKER if a shipped snapshot is inconsistent) |
| AC-D3 | Restricted or licence-pending data and real secrets are not tracked by git and stay git-ignored. | DS; D9 | V30 | BLOCKER |
| AC-D4 | The portfolio, the thresholds and the personas' numbers are labelled fictional everywhere; fixture data shown in the UI is labelled as test data. | BB 8; D7 | V28, V31; manual M2 | HIGH |

### J. No order execution, no recommendation, no forecast

| Id | Criterion | Source | Check | Class |
|---|---|---|---|---|
| AC-N1 | No tool, route, function or UI control places an order, chooses a security, optimises a portfolio or forecasts a return. | BB 1, 6 | V26, V29, V30; manual M3 | BLOCKER |
| AC-N2 | No text returned by the service advises to buy or sell or predicts a price or a return; the maximum compliant weight is presented as a boundary of the user's own rules, not as a suggestion. | BB 1, 2 | V26, V28; manual M3 | BLOCKER |

## 3. Manual and live checks (cannot be automated in this suite)

| Id | Step | Expected |
|---|---|---|
| M1 | Open the hosted frontend, enter the code, inspect Application storage and the network tab. | Code only in `sessionStorage["byb.accessCode"]`; sent only as `Authorization` header to the API origin; not in any URL. |
| M2 | Walk the six stages for Robert and Mateo. | Persistent simulation label and valuation date; rule origin and confirmation status; UNKNOWN shown with text and icon; fixture mode labelled. |
| M3 | Read every sentence of both demonstrations. | No advice, no forecast, replay worded as a replay; every decisive number opens an evidence record. |
| L1 | `curl` each of the seven routes without a code, with a wrong code, and `OPTIONS` without a code. | 401/403, 401/403, 204 with the hosted origin only. |
| L2 | Send 60 `POST /investigations` in one second. | 429 beyond the throttle; no more than the reserved concurrency of workers. |
| L3 | `aws s3api get-public-access-block`, `get-bucket-policy`, anonymous `GET` of an object URL. | Four flags true; TLS-only deny; 403. |
| L4 | Robert, real model: NVDA to 25% under the confirmed 10% cap and 10% loss budget. | FAIL on both rules with the numbers of V20; steps are real tool events; explanation statements cite existing evidence. |
| L5 | Mateo, real model: Energy exclusion, controversy rule, ESGV without holdings. | Starting breach separated; UNKNOWN for what ESGV hides; no pass wording. |
| L6 | CloudWatch log groups after L1, L4, L5. | No access code, no Authorization header, no request body. |

## 4. Decision rule

Go only when: no open BLOCKER; every HIGH fixed or explicitly accepted by the lead in writing; no criterion in
sections A to J is NOT TESTABLE YET on the release candidate; `pytest validation` reports no failure and no
skip other than a documented absence of git-ignored real data; the manual and live checks of section 3 were
carried out on the deployed release candidate and recorded.
