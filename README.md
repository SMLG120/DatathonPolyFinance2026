# Before You Buy

**PolyFinances AlphaForge AI Datathon 2026.** Before You Buy checks whether a
proposed portfolio purchase respects the rules an investor has explicitly
confirmed, and shows the evidence behind every figure so the investor can
inspect and challenge it.

> **Fictional simulation only.** Portfolios, thresholds and transactions are
> invented. The project gives no advice, makes no recommendation or forecast,
> and places no trades. "PASS" means consistent with the investor's own
> confirmed rules. It does not mean "a good investment".

> **Status: work in progress, not ready for demonstration.** This README
> describes commit `db0b90f` (checkpoint, 2026-11-14) plus the review commit
> `93e8d44`. At that point the interface runs on recorded test fixtures, the
> AWS backend is deployed with a **placeholder calculation**, the financial
> engine is not in the repository, and no frontend is hosted. Section 4 says
> what is done and what is not. Work after the checkpoint is described only
> as "in progress" until it is committed and verified.

## Contents

1. [What the product does](#1-what-the-product-does)
2. [Architecture and tech stack](#2-architecture-and-tech-stack)
3. [Repository layout and documentation map](#3-repository-layout-and-documentation-map)
4. [Project phases and status](#4-project-phases-and-status)
5. [Problems, fixes and solutions](#5-problems-fixes-and-solutions)
6. [Implementation notes](#6-implementation-notes)
7. [Run, test and build](#7-run-test-and-build)
8. [Deployment](#8-deployment)
9. [Data, sources and licences](#9-data-sources-and-licences)
10. [Screenshots](#10-screenshots)
11. [Known limitations and next steps](#11-known-limitations-and-next-steps)
12. [How this was built](#12-how-this-was-built)

## 1. What the product does

One workflow in six stages:

| Stage | What the user does |
| --- | --- |
| 1. Persona & portfolio | Picks a fictional investor (Robert, Mateo) and sees the portfolio |
| 2. Goals & rules | Turns a goal into *proposed* rules, sets the threshold, confirms them as policy version 1 |
| 3. Proposed purchase | Enters a final direct weight for one instrument, funded from cash |
| 4. Investigation steps | Watches the steps the job actually reported |
| 5. Verdict & evidence | Reads PASS / FAIL / UNKNOWN per rule, the exposure chart, the scenario test and the evidence drawer |
| 6. Challenge | Corrects a fact, clarifies a preference or changes a rule; a rule change creates a new policy version and a second report beside the first |

Principles that every part of the code follows (`docs/BUILD_BRIEF.md`):

- **Python decides.** Verdicts come from a deterministic engine. The language
  model interprets text and explains results; it cannot activate a policy or
  change a number.
- **Four things stay separate:** the qualitative objective, the confirmed
  rule, the confirmed historical risk budget, and the calculated result.
  "Preserve capital" does not imply a 10% issuer limit.
- **Unknown is not a pass.** Missing fund holdings widen a result into a
  range; they are never treated as zero exposure.
- **A rule change does not change the facts.** Raising a concentration limit
  changes the limit and the status, not the measured exposure.
- **History is not a promise.** The 2022 replay is a test the user selects,
  labelled with its period and assumptions, never a forecast of future loss.

Core formulas (units are portfolio fractions, 10% = 0.10):

    total issuer exposure = direct weight
                          + sum(fund portfolio weight x issuer weight in that fund)
    cash after purchase   = starting cash - (target direct weight - starting direct weight)

Demonstration scenario (Robert): cash 30%, XBB.TO 30%, SPY 20%, XIU.TO 10%,
RY.TO 5%, JNJ 5%; rules "any single company at most 10%" and "2022 replay loss
at most 10%"; request NVDA at a final direct weight of 25%; challenge by
raising the cap to 30%. Persona facts come from the official case; the
portfolios and thresholds are invented by the team
(`docs/LEAD_DECISIONS.md` D7).

## 2. Architecture and tech stack

    browser (Next.js static export)
      |  Authorization: Bearer <access code typed by the user>
      v
    API Gateway HTTP API  --  Lambda authorizer (compares with an SSM SecureString)
      v
    API Lambda            validate, store the job in S3, invoke the worker, answer 202
      v
    Worker Lambda (async) Bedrock Converse tool loop + deterministic tools
      v
    Private S3 bucket     snapshots/ policies/ jobs/ results/ traces/

| Layer | Technology | State at `db0b90f` |
| --- | --- | --- |
| Interface | Next.js 16 (static export), React 19, TypeScript, Tailwind 4, Radix dialog and tabs | Built; runs on fixtures |
| Frontend hosting | AWS Amplify Hosting (planned) | **Not created** |
| API | API Gateway HTTP API, Lambda authorizer | Deployed |
| Compute | Three Lambda functions, Python 3.14, arm64, standard library plus `boto3` | Deployed |
| Model | Amazon Bedrock Converse, `us.anthropic.claude-sonnet-5-5` (stack parameter) | Deployed, real calls |
| Storage | One private S3 bucket; conditional writes are the job store (no database, no queue) | Deployed |
| Logs | CloudWatch Logs, 7-day retention | Deployed |
| Infrastructure as code | AWS SAM template deployed through CloudFormation change sets | `infra/template.yaml` |
| Financial engine | Pure Python package (`backend/engine/`) | **Not in this commit** |

Region `us-east-1` only. The AWS account is a workshop account that is deleted
at the end of 2026-11-16, so the deployment, and any hosted URL, stops working
then.

## 3. Repository layout and documentation map

| Path | Content |
| --- | --- |
| `docs/BUILD_BRIEF.md` | Binding product and engineering rules |
| `docs/LEAD_DECISIONS.md` | Frozen decisions D1-D9: environment, rule types, interval semantics, purchase simulation, 2022 replay, scenarios, authentication, file ownership |
| `docs/data-sources.md` | Every data source, hash, processing step, limitation and licence note |
| `docs/review/` | Screenshot index, capture script and review findings |
| `contracts/SEMANTICS.md` | Normative meaning of rules, bounds, replay, summaries and evidence records |
| `contracts/schemas/` | 19 JSON Schemas shared by backend and frontend |
| `contracts/fixtures/`, `contracts/scenarios/` | Engine cases E01-E22 with hand calculations, API fixtures, the three personas |
| `contracts/python/` | Validators, fixture generators and contract tests |
| `backend/api/`, `backend/worker/`, `backend/agents/`, `backend/common/` | API handler and authorizer, investigation worker, Bedrock loop and tools, job store and logging |
| `backend/tests/service/` | Service tests (no network, no AWS) |
| `data/scripts/` | Acquisition, build, audit and quality-check scripts |
| `data/starter/`, `data/processed/`, `data/curated/`, `data/manifests/` | Organizer files, normalized outputs, controversy records, raw-file hashes |
| `frontend/` | The interface, unit tests and Playwright tests |
| `infra/README.md`, `infra/template.yaml` | Infrastructure description, IAM, decisions |
| `infra/evidence/milestone2.md` | Recorded live proof of the deployed backend slice |
| `scripts/deploy.md`, `scripts/package.py`, `scripts/mcp/` | Packaging and the deployment sequence |
| `.claude/agents/` | Definitions of the six development agents |

Still to be written: the technical document, the one-pager and the demo
script.

## 4. Project phases and status

Status is as of checkpoint `db0b90f` unless a row says otherwise. "Verified in
review" means the check was re-run independently on that commit;
"agent-reported" means it was not.

| Phase | Scope | Status |
| --- | --- | --- |
| 0. Decisions | Build brief, lead decisions, ownership map | Done |
| 1. Contracts | Schemas, semantics, fixtures, hand calculations | Partly done. Schemas, semantics and fixtures are committed. In progress after the checkpoint: TypeScript contracts, `contracts/api.md`, the Mateo fixture correction, `docs/requirements.md` |
| 2. Data | SPY and XIU holdings, controversy registry, audit, quality checks | Done. Agent-reported: audit exit 0; 80 quality checks passed, 1 warning; 30 of 30 seeded defects caught |
| 3. Backend vertical slice (Milestone 2) | API, authorizer, worker, Bedrock loop, S3 job store, deployment | Done with a **placeholder** calculation. Live proof in `infra/evidence/milestone2.md`. Smoke runs 4 and 5 later failed with HTTP 429; a throttle and CORS-header redeploy is in progress |
| 4. Frontend shell | Six stages, design system, fixtures client, accessibility | Done on provisional fixture types. Verified in review: type check, lint, build, 10 browser tests |
| 5. Financial engine | Exposure, rules, replay, maximum compliant weight | **Not in this commit.** In progress after the checkpoint, nothing reported yet |
| 6. Backend phase 2 | Contract request and response shapes, real engine in the worker | Not started |
| 7. Frontend phase 2 | Contract types, then the real API and live investigation progress | Contract types in progress; live API wiring not started |
| 8. Independent validation | Separate validator against the brief's test list | Not started |
| 9. Hosting | Amplify app, CORS origin tightened, hosted end-to-end run | Not started |
| 10. Deliverables | Technical document, one-pager, demo script | Not started |

The only milestone passed so far is Milestone 2, the minimal AWS vertical
slice.

Checks re-run in review on `db0b90f`:

| Check | Result |
| --- | --- |
| `pytest backend/tests contracts/python/tests` (Python 3.14) | 665 passed |
| Frontend unit tests, `npm run typecheck`, `npm run lint` | pass / clean |
| `npm run build` | static export of `/` |
| Playwright with axe on every stage | 10 passed |
| Screenshot capture run | 19 screenshots, 0 browser console errors |
| Frontend bundle | `out/` 1.0 MB; JavaScript 818 kB raw, 244 kB gzipped |

Not measured in review: API latency, investigation duration and Lambda usage
(no API calls were made while the stack was being redeployed).

## 5. Problems, fixes and solutions

Each row is a problem met or anticipated during the build and the solution
that is in the code or the deployed stack. The source column says where the
detail and the evidence are.

| Problem | Fix or solution | Source |
| --- | --- | --- |
| A model could skip an unfavourable calculation or pass wrong arguments | After the loop the worker checks the required tool ran with the stored request's arguments, and runs it itself otherwise; the result is built from that run only | `backend/worker/investigation.py` |
| Lambda asynchronous delivery is at least once, so a job could run twice | The worker claims a job by compare-and-swap (`If-Match`), every later write checks ownership, results and traces are write-once | `backend/common/jobs.py`, `infra/README.md` |
| API Gateway throttling did not bound a burst: 79 of 80 parallel requests passed and 10 investigations started at once | Reserved concurrency of 5 on the worker; the same burst then ran five at a time and all ten succeeded | `infra/README.md` "Decisions" |
| Slow cold start of the worker handler | SDK clients built in the init phase: handler 4,085 ms to 2,847 ms in the two cold runs measured (init 82 ms to 602 ms) | `infra/README.md` "Decisions" |
| A job could hang forever if the worker died | Every job has a 150 s deadline; a `GET` turns an overdue job into `FAILED / DEADLINE_EXCEEDED` and stores that | `backend/api/handler.py` |
| A retried request could create a second job | Job id derived from the idempotency key; creation uses `If-None-Match: *`; a different body under the same key is a 409 | `infra/README.md` "Lifecycle rules" |
| Unbounded model cost or runtime | 6 tool rounds, 16 tool calls, 4,096 output tokens per call, 4 attempts per call, all inside the job deadline | `backend/agents/loop.py` |
| Missing or partial fund holdings could look like zero exposure | Interval semantics: known exposure is a lower bound, the uncovered part of a fund is added as a possible extra, and a rule is UNKNOWN when the limit falls inside the range | `docs/LEAD_DECISIONS.md` D4, `contracts/SEMANTICS.md` 5 |
| "Avoid oil" has no single meaning | The interpreter must ask which supported definition is meant; unsupported definitions are refused, not guessed | `docs/LEAD_DECISIONS.md` D3, D7 |
| The interpreter could invent a threshold | System-proposed rules carry a null threshold and stay inactive until the user sets and confirms one | `docs/LEAD_DECISIONS.md` D3 |
| An older API answer could overwrite a newer one | Sequence-number guard plus request abort in `useLatestRequest`; previews are debounced | `frontend/src/hooks/` |
| A progress indicator could spin forever | `usePolling` stops on a terminal state, on its deadline, after three consecutive errors, or on an error a retry cannot fix | `frontend/src/hooks/usePolling.ts` |
| Fixture output could be mistaken for live output | A persistent "Test data — fixtures" label and a footer note in fixtures mode | `frontend/` |
| Status conveyed by colour alone | PASS / FAIL / UNKNOWN always carry an icon and a word; axe runs on every stage in the browser tests | `frontend/e2e/` |
| Credentials in the browser bundle | The access code is typed at runtime and kept in `sessionStorage`; no secret is a build variable | `docs/LEAD_DECISIONS.md` D8 |
| Third-party data that may not be redistributed | Yahoo-derived prices, raw issuer files and case material are git-ignored; hashes are kept in a manifest | `.gitignore`, `docs/data-sources.md` 6 |

Open problems without a fix in this commit are listed in section 11.

## 6. Implementation notes

**Rules (schema v1).** `max_issuer_exposure`, `min_issuer_exposure`,
`exclusion` (named issuers or a fund-reported sector), `controversy_exclusion`
and `scenario_loss_budget`. Lifecycle `PROPOSED` to `CONFIRMED` to
`SUPERSEDED`; only confirmed rules with a numeric threshold are evaluated.
Policy versions are immutable: a change creates a new version and the earlier
report stays openable.

**Purchase simulation.** The request is a final direct weight, funded from
cash, with every other position unchanged. Fees and taxes are excluded and
that is stated on screen. Insufficient cash is a feasibility result, reported
separately from rule results.

**2022 replay.** Buy and hold from the last price of 2021 to the last price of
2022, no rebalancing, cash earning 0%, USD converted to CAD with the latest
Bank of Canada rate on or before each date. The budget is checked against the
loss at the end of the period; the deepest fall during the period is shown as
context only.

**Job lifecycle.** `QUEUED` to `RUNNING` to `SUCCEEDED` or `FAILED`. The API
stores the validated request, invokes the worker asynchronously and answers
202 only after the invocation is accepted. The timeline shows tool actions and
results, never model reasoning.

**Access control.** Demonstration-grade: a shared bearer access code, checked
by a Lambda authorizer against an SSM SecureString. The code is typed at
runtime, kept in `sessionStorage`, and is never in the bundle or the
repository. It is not user identity. CORS is not authentication; the allowed
origin is currently `*` and is to be narrowed to the hosted origin.

**Frontend.** Static export with no server features. With no API base URL, or
with `?fixtures=1`, the app uses recorded fixtures and says so.

## 7. Run, test and build

Requirements: Node.js 22.12 or later, Python 3.14, [`uv`](https://docs.astral.sh/uv/).

Frontend (fixtures mode needs no backend):

    cd frontend
    npm ci
    npm run dev            # development server
    npm run build          # static export to frontend/out
    npm start              # serve frontend/out on http://127.0.0.1:4173
    npm test               # unit tests
    npm run typecheck && npm run lint
    npx playwright install chromium && npm run test:e2e   # after npm run build

To point a build at a deployed API, set `NEXT_PUBLIC_API_BASE_URL` (see
`frontend/.env.example`). Never put the access code in a build variable.

Backend and contracts, from the repository root:

    uv run --no-project --python 3.14 --with pytest --with boto3 --with jsonschema \
      pytest backend/tests contracts/python/tests -q

Data pipeline (standard library). A fresh clone lacks the files listed in
section 9 and must restore them first; `docs/data-sources.md` section 1 has
the full sequence:

    python3 -I data/scripts/build_processed.py
    python3 -I data/scripts/quality_checks.py

## 8. Deployment

- **Backend:** stack `before-you-buy` in `us-east-1`, deployed from
  `infra/template.yaml` through CloudFormation change sets after
  `python3 scripts/package.py` uploads a content-addressed zip. The exact
  sequence is in `scripts/deploy.md`; resources, IAM and outputs are in
  `infra/README.md`.
- **Proof:** `infra/evidence/milestone2.md` records a real request from 401 to
  `SUCCEEDED`, the S3 objects, Bedrock usage, logs, IAM simulations and what
  was *not* proven.
- **Frontend:** not hosted. No Amplify app exists at this commit.
- **Traceability:** the deployed code artifact name is a stack output. No
  hosted version is tied to a Git commit yet.

The deployed worker returns a placeholder calculation. A successful
investigation on the current stack is proof of the pipeline, not a financial
result.

## 9. Data, sources and licences

- **Organizer starter files:** prices, FX, macro series and the asset universe
  (2021-11-12 to 2026-11-12). They hold no ETF constituents, no portfolios and
  no ESG or controversy data.
- **ETF holdings:** from the issuers' own files (State Street for SPY,
  BlackRock Canada for XIU), dated 2026-11-12. They are used only for today's
  look-through and never as historical composition. ESGV and QQQ holdings are
  not acquired: their exposure is unknown, never zero. SPY's file carries no
  per-constituent sector, so a sector exclusion is UNKNOWN through SPY.
- **Controversy registry:** three records from official pages. Absence from
  the registry means "not assessed", never "no controversy".
- **Not redistributed:** the issuer-derived files and the Yahoo-derived prices
  and corporate actions (issuer and Yahoo terms), the raw downloaded files and
  the organizer's case material. `data/scripts/` regenerates the derived
  files, so a fresh clone needs the starter prices and a re-fetch.
- **Regulatory context:** a CIRO news release dated 2026-03-12 announces
  guidance that, in its words, "broadens the range of decision-making supports
  that OEO dealers can offer to clients without violating the rule that
  prohibits them from making recommendations". The guidance itself was not
  read, and nothing here implies regulatory approval of this prototype
  (`docs/data-sources.md` section 8).

Full provenance, hashes and terms: `docs/data-sources.md`.

## 10. Screenshots

Genuine Playwright captures of the built app are in
`docs/review/screenshots/baseline-db0b90f/`, indexed in
`docs/review/README.md`. **All of them are fixture data**, not live output.
Reproduce with:

    cd frontend && npm ci && npm run build && cd ..
    node docs/review/capture.mjs docs/review/screenshots/<label>

## 11. Known limitations and next steps

Limitations at this commit:

- No financial engine in the repository; no verdict shown anywhere is a real
  calculation.
- The backend's request and response shapes predate the contracts.
- The frontend is not connected to the API and is not hosted.
- `POST /investigations` throttling (1 request per second, burst 4) produced
  HTTP 429 in two smoke runs; a looser setting is being deployed.
- The CORS origin is `*`.
- Model-written explanations are not yet checked against evidence records.
- Mateo's fixture shows the controversy rule as UNKNOWN where the real data
  gives FAIL; the correction is in progress.
- The verdict page is long (about eleven screens on a phone) and the evidence
  drawer's calculation path mixes formulas with values.
- The planned polling deadline (120 s) is shorter than the worker's job
  deadline (150 s); it must be longer.

Next steps, in order:

1. Financial engine against the frozen contracts and real data, with the
   regression cases E01-E22.
2. Backend phase 2 (contract shapes, real engine) and a full smoke pass on the
   final deployment.
3. Frontend phase 2 on contract types and the real API.
4. Independent validation, then Amplify hosting, a hosted run of the Robert
   workflow, and live screenshots.
5. Technical document, one-pager and demo script.

## 12. How this was built

Built with Claude Code (Claude Fable 5.2) using role-scoped development
agents with non-overlapping file ownership (`docs/LEAD_DECISIONS.md` D9,
`.claude/agents/`). The application's runtime model is separate:
`us.anthropic.claude-sonnet-5-5` on Amazon Bedrock. The development model
never appears in application code.
