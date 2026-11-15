# Before You Buy

**PolyFinances AlphaForge AI Datathon 2026.** Before an investor changes a
portfolio, Before You Buy investigates whether the decision respects the rules
that investor has explicitly confirmed, and shows evidence the investor can
inspect and challenge.

> **Fictional simulation only.** Portfolios, thresholds and transactions are
> invented. The project gives no advice, makes no recommendation or forecast,
> and places no trades. "PASS" means consistent with the investor's own
> confirmed rules. It does not mean "a good investment".

> **Status: work in progress, not ready for demonstration.** This README
> describes commit `d36e41f` (2026-11-15 UTC).
>
> | | At `d36e41f` |
> | --- | --- |
> | Real and tested | Contracts (schemas, semantics, API contract, fixtures, TypeScript types); data pipeline; deterministic engine `byb-engine-1.0.1` |
> | Real and deployed, **placeholder calculation** | Backend phase 1: an API with two investigation routes, an authorizer and a worker that runs a Bedrock Converse tool loop. The worker does not call the engine yet and its request and response shapes predate the contracts |
> | Built on **provisional types and test fixtures** | The interface. It is not connected to the API |
> | Does not exist | A hosted frontend (no Amplify app), a real verdict through the API, independent validation |
> | In progress elsewhere, **not in this commit** | Frontend on contract types with a 3D exposure explorer; real engine in the worker and the remaining API routes; an engine rounding fix; Mateo acceptance tests; independent validation (section 4) |
>
> Statements about work after `d36e41f` are marked "in progress" and were
> reported by the lead on 2026-11-14; they are not verified here.

## Contents

1. [What the product does](#1-what-the-product-does)
2. [Architecture and tech stack](#2-architecture-and-tech-stack)
3. [Repository map and documentation index](#3-repository-map-and-documentation-index)
4. [Milestones and status](#4-milestones-and-status)
5. [Problems and the solutions in the code](#5-problems-and-the-solutions-in-the-code)
6. [Run, test and build](#6-run-test-and-build)
7. [Deployment](#7-deployment)
8. [Data, sources and licences](#8-data-sources-and-licences)
9. [Screenshots](#9-screenshots)
10. [Limitations and next steps](#10-limitations-and-next-steps)
11. [How this was built](#11-how-this-was-built)

## 1. What the product does

One workflow in six stages (`frontend/src/state/stage.ts`):

| Stage | What the user does |
| --- | --- |
| 1. Persona & portfolio | Picks a fictional investor (Robert, Mateo) and sees the portfolio |
| 2. Goals & rules | Turns a goal into *proposed* rules, sets the threshold, confirms them as policy version 1 |
| 3. Proposed purchase | Enters a final direct weight for one instrument, funded from cash |
| 4. Investigation steps | Watches the steps the job actually reported |
| 5. Verdict & evidence | Reads PASS / FAIL / UNKNOWN per rule, the exposure chart, the scenario test and the evidence drawer |
| 6. Challenge | Corrects a fact, clarifies a preference or changes a rule; a rule change creates a new policy version and a second report beside the first |

Principles every part follows (`docs/BUILD_BRIEF.md`):

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

The two demonstration scenarios, step by step with their expected outcomes,
are in [`docs/WORKFLOWS.md`](docs/WORKFLOWS.md). Persona facts come from the
official case; the portfolios and thresholds are invented by the team
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

Detail, trust boundaries and the status of each element:
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

| Layer | Technology | State at `d36e41f` |
| --- | --- | --- |
| Interface | Next.js 16 static export, React 19, TypeScript, Tailwind 4, Radix dialog and tabs (`frontend/package.json`) | Built on provisional types; runs on fixtures |
| Frontend hosting | AWS Amplify Hosting (planned; `amplify.yml`, `docs/DEPLOYMENT.md`) | **Not created** |
| API | API Gateway HTTP API, Lambda authorizer | Deployed: `POST /investigations`, `GET /investigations/{id}` only |
| Compute | Three Lambda functions, Python 3.14, arm64, standard library plus `boto3` | Deployed |
| Model | Amazon Bedrock Converse, `us.anthropic.claude-sonnet-5-5` (stack parameter) | Deployed, real calls |
| Storage | One private S3 bucket; conditional writes are the job store (no database, no queue) | Deployed |
| Logs | CloudWatch Logs, 7-day retention | Deployed |
| Infrastructure as code | AWS SAM template deployed through CloudFormation change sets (`infra/template.yaml`) | Deployed; its hash matches deployment D4 in `infra/evidence/milestone2.md` |
| Financial engine | Pure Python package `backend/engine/`, version in `backend/engine/version.py` | In the repository and tested; **not yet called by the worker** |

"Deployed" means recorded in `infra/evidence/milestone2.md` (collected
2026-11-14 23:14 UTC to 2026-11-15 00:29 UTC). It was not re-checked for this
README. Region `us-east-1` only. The AWS account is a workshop account that is
deleted at the end of 2026-11-16, so the deployment, and any hosted URL, stops
working then.

## 3. Repository map and documentation index

Documents:

| Document | Content |
| --- | --- |
| [`docs/ONE_PAGER.md`](docs/ONE_PAGER.md) | One page for judges |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Technical document: components, request paths, trust boundaries, evidence model, security |
| [`docs/WORKFLOWS.md`](docs/WORKFLOWS.md) | Robert and Mateo step by step, mapped to routes and engine concepts |
| [`docs/DEMO_SCRIPT.md`](docs/DEMO_SCRIPT.md) | Timed recording script, checklist, fallback, claims not to make |
| [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) | Hosting steps, security headers, verification, rollback, missing prerequisites |
| [`docs/requirements.md`](docs/requirements.md) | Official requirements, our choices, assumptions and open questions |
| [`docs/BUILD_BRIEF.md`](docs/BUILD_BRIEF.md) | Binding product and engineering rules |
| [`docs/LEAD_DECISIONS.md`](docs/LEAD_DECISIONS.md) | Frozen decisions D1 to D9 |
| [`docs/PLAN.md`](docs/PLAN.md) | Milestones, deadline, cut order, open items |
| [`docs/data-sources.md`](docs/data-sources.md) | Every data source, hash, processing step, limitation and licence note |
| [`contracts/README.md`](contracts/README.md) | What the contracts are and how to check them |
| [`contracts/api.md`](contracts/api.md) | The seven routes: requests, responses, errors, idempotency, polling |
| [`contracts/SEMANTICS.md`](contracts/SEMANTICS.md) | Normative meaning of rules, bounds, replay, summaries and evidence |
| [`contracts/fixtures/engine/HAND_CALCS.md`](contracts/fixtures/engine/HAND_CALCS.md) | Hand arithmetic for the 26 engine cases |
| [`backend/engine/README.md`](backend/engine/README.md) | Engine functions and version notes |
| [`backend/engine/evidence/robert_max_compliant.md`](backend/engine/evidence/robert_max_compliant.md) | Robert's maximum compliant weight on the real data |
| [`infra/README.md`](infra/README.md) | Resources, IAM, lifecycle rules, decisions, gap to the contracts |
| [`infra/evidence/milestone2.md`](infra/evidence/milestone2.md) | Recorded live proof of the deployed backend slice |
| [`scripts/deploy.md`](scripts/deploy.md) | Backend deployment sequence |

Code and data:

| Path | Content |
| --- | --- |
| `contracts/schemas/` | 19 JSON Schemas shared by backend and frontend |
| `contracts/scenarios/`, `contracts/fixtures/` | The three personas; 26 engine cases; 24 API example exchanges. All numbers synthetic |
| `contracts/python/`, `contracts/typescript/contracts.ts` | Validators, fixture generators, contract tests; TypeScript mirror of the schemas |
| `backend/engine/`, `backend/tests/engine/` | Deterministic engine and its tests |
| `backend/api/`, `backend/worker/`, `backend/agents/`, `backend/common/` | API handler and authorizer, investigation worker, Bedrock loop and tools, job store and logging |
| `backend/tests/service/` | Service tests (no network, no AWS) |
| `data/scripts/` | Acquisition, build, audit and quality-check scripts |
| `data/starter/`, `data/processed/`, `data/curated/`, `data/manifests/` | Organizer files, normalized outputs, controversy records, raw-file hashes |
| `frontend/` | The interface, unit tests and Playwright tests |
| `infra/template.yaml`, `scripts/package.py`, `scripts/mcp/` | SAM template, packaging, deployment snippets |
| `amplify.yml` | Amplify Hosting build specification (never executed) |
| `.claude/agents/` | Definitions of the six development agents |

Not in this commit: `docs/review/` (screenshots; section 9) and `validation/`
(independent validator; section 4).

## 4. Milestones and status

Milestones are defined in `docs/PLAN.md` P7. State is at `d36e41f`.

| # | Milestone | State | Evidence |
| --- | --- | --- | --- |
| 1 | Requirements, schemas, fixtures | Done | `docs/requirements.md`, `contracts/`; contract tests pass (section 6) |
| 2 | Minimal AWS vertical slice | Done, with a **placeholder** calculation | `infra/evidence/milestone2.md`: smoke runs 6 to 8 passed on the live deployment |
| 3 | Data and deterministic engine | Done. In progress, not in this commit: a rounding fix for the maximum compliant weight (round down instead of to nearest; effect at most 5e-10, as reported by the lead) | `docs/data-sources.md`, `backend/engine/`; engine tests pass (section 6); the three real-data tests are skipped on a fresh clone |
| 4 | Frontend on typed fixtures | **In progress, not in this commit.** At `d36e41f` the interface uses provisional types, and `docs/PLAN.md` P8 records that it does not typecheck against the synced contract copies. In progress: migration to contract types and a lazy-loaded 3D exposure explorer (plain three.js, issuer rules only, with the 2D chart and table as the accessible fallback) | `frontend/src/lib/provisional-types.ts`; `docs/PLAN.md` P8, P9 |
| 5 | Robert end to end through the real API | **In progress, not in this commit.** Real engine in the worker and the contract routes | `infra/README.md` "Gap to the contracts" |
| 6 | Mateo | **In progress, not in this commit.** The engine passes the Mateo fixtures M1 and M2; acceptance tests and a live check script are being written | `contracts/fixtures/engine/M1.json`, `M2.json` |
| 7 | Independent validation | **In progress, not in this commit.** No `validation/` directory exists | none yet |
| 8 | Deliverables, hosted frontend, push | Documents written (this README and the five new files in `docs/`). **No frontend is hosted and no Amplify app exists.** Nothing after the first review merge is on GitHub `main` | `git log origin/main` ends at merge `061682c` |

Extensions (Amira, horizon analysis, 2D map, questionnaire) are not started
and are scheduled only after milestone 8 (`docs/PLAN.md` P7).

The submission deadline and the exact hour at which the AWS account expires
are unresolved (`docs/PLAN.md` P2, `docs/requirements.md` Q1, Q2).

## 5. Problems and the solutions in the code

| Problem | Solution | Source |
| --- | --- | --- |
| A model could skip an unfavourable calculation or pass wrong arguments | After the loop the worker checks the required tool ran with the stored request's arguments, and runs it itself otherwise; the result is built from that run only | `backend/worker/investigation.py` |
| Lambda asynchronous delivery is at least once, so a job could run twice | The worker claims a job by compare-and-swap (`If-Match`), every later write checks ownership, results and traces are write-once | `backend/common/jobs.py`, `infra/README.md` |
| API Gateway throttling did not bound a burst: 79 of 80 parallel requests passed and 10 investigations started at once | Reserved concurrency of 5 on the worker; the same burst then ran five at a time and all ten succeeded | `infra/README.md` "Decisions" |
| A job could hang forever if the worker died | Every job has a 150 s deadline; a `GET` turns an overdue job into `FAILED / DEADLINE_EXCEEDED` and stores that | `backend/api/handler.py` |
| A retried request could create a second job | Job id derived from the idempotency key; creation uses `If-None-Match: *`; a different body under the same key is a 409 | `infra/README.md` "Lifecycle rules" |
| Unbounded model cost or runtime | 6 tool rounds, 16 tool calls, 4,096 output tokens per call, 4 attempts per call, all inside the job deadline | `backend/agents/loop.py`, `backend/common/config.py` |
| Missing or partial fund holdings could look like zero exposure | Interval semantics: known exposure is a lower bound, the uncovered part of a fund is added as a possible extra, and a rule is UNKNOWN when the limit falls inside the range | `docs/LEAD_DECISIONS.md` D4, `contracts/SEMANTICS.md` 5 |
| A maximum found by search could be wrong when a historical constraint is involved | Closed form from the proof that the replay return is linear in the target weight, then the same evaluator is re-run at the boundary; withheld when data is unknown | `contracts/SEMANTICS.md` 11, `backend/engine/boundary.py` |
| "Avoid oil" has no single meaning | The interpreter must ask which supported definition is meant; unsupported definitions are refused, not guessed | `docs/LEAD_DECISIONS.md` D3, D7 |
| The interpreter could invent a threshold | System-proposed rules carry a null threshold and stay inactive until the user sets and confirms one | `docs/LEAD_DECISIONS.md` D3 |
| An older API answer could overwrite a newer one | Sequence-number guard plus request abort in `useLatestRequest`; previews are debounced | `frontend/src/hooks/` |
| Fixture output could be mistaken for live output | A persistent "Test data — fixtures" label and a footer note in fixtures mode | `frontend/src/components/shell/AppShell.tsx` |
| Credentials in the browser bundle | The access code is typed at runtime and kept in `sessionStorage`; no secret is a build variable | `docs/LEAD_DECISIONS.md` D8, `frontend/src/lib/access-code.ts` |
| Third-party data that may not be redistributed | Yahoo-derived prices, raw issuer files, issuer-derived processed files and case material are git-ignored; hashes are kept in a manifest | `.gitignore`, `data/.gitignore`, `docs/data-sources.md` 6 |

## 6. Run, test and build

Requirements: Node.js 22.12 or later (`frontend/package.json` engines),
Python 3.14, [`uv`](https://docs.astral.sh/uv/).

Backend, engine and contracts, from the repository root:

    uv run --no-project --python 3.14 --with pytest --with boto3 --with jsonschema \
      pytest backend/tests contracts/python/tests -q

Run for this README on a clean checkout of `d36e41f`: **1083 passed, 3
skipped**. The three skipped tests are the engine's real-data tests
(`backend/tests/engine/test_engine_real_data.py`); they need
`data/processed/holdings.json`, `instruments.json` and `market_data.json`,
which are git-ignored (section 8). The lead reports 1086 passed in a worktree
that holds those files.

Frontend (fixtures mode needs no backend). These scripts exist in
`frontend/package.json`; they were **not run for this README**:

    cd frontend
    npm ci
    npm run dev            # development server
    npm run build          # static export to frontend/out
    npm start              # serve frontend/out on http://127.0.0.1:4173
    npm test               # unit tests (vitest)
    npm run typecheck && npm run lint
    npm run test:e2e:install && npm run test:e2e   # Playwright; builds first

`docs/PLAN.md` P8 records that at this commit the frontend does not typecheck
against the synced contract copies; that is milestone 4 work.

To point a build at a deployed API, set `NEXT_PUBLIC_API_BASE_URL` (see
`frontend/.env.example`). With no base URL, or with `?fixtures=1` in the
address, the app uses recorded fixtures and says so
(`frontend/src/lib/config.ts`). Never put the access code in a build variable.

Data pipeline (standard library). A fresh clone lacks the files listed in
section 8 and must restore them first; `docs/data-sources.md` section 1 has
the full sequence:

    python3 -I data/scripts/build_processed.py
    python3 -I data/scripts/quality_checks.py

## 7. Deployment

Full procedure, security headers, verification, rollback and the list of
missing prerequisites: [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md).

- **Backend:** stack `before-you-buy` in `us-east-1`, deployed from
  `infra/template.yaml` through CloudFormation change sets after
  `python3 scripts/package.py` builds a content-addressed zip. The exact
  sequence is in `scripts/deploy.md`.
- **Proof:** `infra/evidence/milestone2.md` records a real request from 401 to
  `SUCCEEDED`, the S3 objects, Bedrock usage, logs, IAM simulations and, in
  its section 16, what was *not* proven.
- **Frontend:** not hosted. No Amplify app exists. `amplify.yml` is a build
  specification written from the AWS documentation and never executed.
- **Traceability:** the deployed code artifact name is a stack output. No
  hosted version is tied to a Git commit.

The deployed worker returns a placeholder calculation. A successful
investigation on the current stack is proof of the pipeline, not a financial
result.

## 8. Data, sources and licences

- **Organizer starter files:** prices, FX, macro series and the asset
  universe. They hold no ETF constituents, no portfolios and no ESG or
  controversy data.
- **ETF holdings:** from the issuers' own files (State Street for SPY,
  BlackRock Canada for XIU), one snapshot dated 2026-11-12. It is used only
  for today's look-through and never as historical composition. ESGV and QQQ
  holdings are not acquired: their exposure is unknown, never zero. SPY's file
  carries no per-constituent sector, so a sector exclusion is unknown through
  SPY.
- **Controversy registry:** three records from official pages. Absence from
  the registry means "not assessed", never "no controversy".
- **Not redistributed:** the raw issuer files, the issuer-derived processed
  files (`holdings.json`, `instruments.json` and two supplementary files) and
  the Yahoo-derived prices and corporate actions, because of the issuers' and
  Yahoo's terms; and the organizer's case material. `data/scripts/`
  regenerates the derived files, so a fresh clone needs the starter prices and
  the issuer files. Whether the issuer-derived files may be published is a
  pending decision (`docs/data-sources.md` section 6).
- **Regulatory context:** a CIRO news release dated 2026-03-12 announces
  guidance that, in its words, "broadens the range of decision-making supports
  that OEO dealers can offer to clients without violating the rule that
  prohibits them from making recommendations". The guidance itself was not
  read, and nothing here implies regulatory approval of this prototype
  (`docs/data-sources.md` section 8).

Full provenance, hashes and terms: `docs/data-sources.md`.

## 9. Screenshots

There are no screenshots in this commit. Playwright captures of the built app
at the earlier commit `db0b90f` are on branch `review/visual-verification`
(also merged into GitHub `main`) under `docs/review/screenshots/`, indexed in
`docs/review/README.md` on that branch. **All of them show fixture data**, not
live output, and they predate the contract types. No screenshot of a live
result exists.

## 10. Limitations and next steps

At this commit:

- The worker does not call the engine: no verdict returned by the deployed API
  is a real calculation.
- The API has two of the seven contract routes, with shapes that predate the
  contracts (`infra/README.md` "Gap to the contracts").
- The frontend runs on provisional types and fixtures, is not connected to the
  API and is not hosted.
- The client polling deadline is 120 s (`frontend/src/lib/config.ts`), shorter
  than the 150 s job deadline; the contract asks for 180 s
  (`contracts/api.md` section 1).
- The CORS origin is `*`.
- Model-written explanations are not checked against evidence records in the
  deployed phase.
- Access control is one shared code. It gives no isolation between users and
  is acceptable only because all data is fictional.
- Holdings are one dated snapshot of two funds; controversy coverage is three
  issuers; sector labels exist for XIU only.
- Failure paths (dispatch failure, deadline expiry, Bedrock throttling) are
  covered by unit tests with fakes and were not provoked in AWS
  (`infra/evidence/milestone2.md` section 16).

Next steps, in order: finish milestones 4 and 5 (contract-typed frontend; real
engine and contract routes in the backend; redeploy; a full smoke pass);
Mateo; independent validation; hosting with a hosted run of the Robert
workflow; recording.

## 11. How this was built

Built with Claude Code (Claude Fable 5.2) using role-scoped development agents
with non-overlapping file ownership (`docs/LEAD_DECISIONS.md` D9,
`.claude/agents/`). The application's runtime model is separate:
`us.anthropic.claude-sonnet-5-5` on Amazon Bedrock. The development model
never appears in application code.
