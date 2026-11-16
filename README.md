# Before You Buy

**PolyFinances AlphaForge AI Datathon 2026.** Before an investor changes a
portfolio, Before You Buy investigates whether the decision respects the rules
that investor has explicitly confirmed, and shows evidence the investor can
inspect and challenge.

> **Fictional simulation only.** Portfolios, thresholds and transactions are
> invented. The project gives no advice, makes no recommendation or forecast,
> and places no trades. "PASS" means consistent with the investor's own
> confirmed rules. It does not mean "a good investment".

**Candidate described:** local branch `integration/rc` at `deec650`, plus fixes in progress.

> **Status: a release candidate that works locally and has not been deployed.**
>
> | | In the candidate |
> | --- | --- |
> | Built and tested locally, on the real data | Contracts; data pipeline and validated data snapshot; deterministic engine; backend with the seven contract routes, the engine in the worker, a deterministic fallback and write-once policy versions; rule interpreter; frontend on the contract types with a 3D exposure explorer; Mateo acceptance suite; a full-stack browser run against the real handlers; an independent validation suite |
> | **Not verified anywhere** | Any deployment of this candidate; the new template in CloudFormation; the real Bedrock model with the current investigator and interpreter prompts; Amplify hosting |
> | Deployed in AWS today | Still the **phase-1** stack: two routes, a **placeholder calculation**, CORS origin `*` (`infra/evidence/milestone2.md`). It is not this candidate |
> | Open | One HIGH validation finding being fixed (section 4); the fourth validation pass; frontend findings F-01 to F-08, none blocking (`acceptance/fullstack/FINDINGS.md`) |
> | Hosted frontend | None. No Amplify app exists |

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
10. [Disclosed limits](#10-disclosed-limits)
11. [How this was built](#11-how-this-was-built)

## 1. What the product does

One workflow in six stages (`frontend/src/state/stage.ts`):

| Stage | What the user does |
| --- | --- |
| 1. Persona & portfolio | Picks a fictional investor (Robert, Mateo) and sees the portfolio |
| 2. Goals & rules | Confirms offered rules, or has a sentence interpreted into *proposed* rules; sets each number; confirming creates policy version 1 |
| 3. Proposed purchase | Enters a final direct weight for one instrument, funded from cash; sees a labelled preview |
| 4. Investigation steps | Watches the steps the job actually ran |
| 5. Verdict & evidence | Reads PASS / FAIL / UNKNOWN per rule, the exposure views, the scenario test and the evidence drawer |
| 6. Challenge | Corrects a fact, clarifies a preference or changes a rule; a rule change creates a new policy version and a second report beside the first |

Principles every part follows (`docs/BUILD_BRIEF.md`):

- **Python decides.** Verdicts come from a deterministic engine. The language
  model selects tools and evidence and marks spans of the user's text; it
  cannot activate a policy or change a number, and no sentence it writes is
  shown.
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

**Customize this profile (added 2026-11-15, verified locally, see section 4 for what is deployed).** Starting
from a persona, a user can edit the fictional portfolio (weights and cash, supported assets only, total exactly
100%, no shorting or leverage) and the wording of the objective, then run a real investigation on that
portfolio. The edited weights travel with each request (`custom_portfolio`, `contracts/api.md` section 2a);
the server validates them, the Python engine checks that portfolio, and every investigation stores and returns
the exact portfolio it was checked against, so an earlier report stays reproducible after another edit. An
edited objective is context only: it never creates, changes or confirms a rule.

The two demonstration scenarios, step by step with their outcomes on the real
data and on the synthetic fixtures, are in
[`docs/WORKFLOWS.md`](docs/WORKFLOWS.md). Persona facts come from the official
case; the portfolios and thresholds are invented by the team
(`docs/LEAD_DECISIONS.md` D7).

## 2. Architecture and tech stack

    browser (Next.js static export)
      |  Authorization: Bearer <access code typed by the user>
      v
    API Gateway HTTP API  --  Lambda authorizer (compares with an SSM SecureString)
      v
    API Lambda            seven routes: validate, run the engine for /check, store
      |                   policy versions and jobs, call the interpreter, dispatch
      v
    Worker Lambda (async) engine on the stored request + Bedrock Converse tool loop
      v
    Private S3 bucket     snapshots/ policies/ jobs/ results/ traces/

Detail, trust boundaries and the status of each element:
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

| Layer | Technology | State |
| --- | --- | --- |
| Interface | Next.js 16 static export, React 19, TypeScript, Tailwind 4, Radix dialog and tabs, three.js loaded lazily (`frontend/package.json`) | In the candidate; tested locally; not hosted |
| Frontend hosting | AWS Amplify Hosting (`docs/DEPLOYMENT.md`) | **Not created** |
| API | API Gateway HTTP API, Lambda authorizer, seven routes (`infra/template.yaml`) | In the candidate; **not deployed**. Deployed today: phase 1, two routes |
| Compute | Three Lambda functions, Python 3.14, arm64, standard library plus `boto3` | The functions exist in AWS with phase-1 code |
| Model | Amazon Bedrock Converse, `us.anthropic.claude-sonnet-5-5` (stack parameter) | Real calls recorded for phase 1 only. The candidate's prompts have never been sent to a real model |
| Storage | One private S3 bucket; conditional writes are the job and policy store (no database, no queue) | Deployed (phase 1); `snapshots/` and `policies/` are unused until the candidate is deployed |
| Data snapshot | `scripts/build_snapshot.py`, content-derived id, stack parameter `DataSnapshotId` | In the candidate; not uploaded |
| Infrastructure as code | AWS SAM template through CloudFormation change sets | The candidate's template has never been through CloudFormation |
| Financial engine | Pure Python package `backend/engine/`; version in `backend/engine/version.py` | In the candidate; called by the API function and the worker |

Region `us-east-1` only. The AWS account is a workshop account that is deleted
at the end of 2026-11-16, so the deployment, and any hosted URL, stops working
then.

## 3. Repository map and documentation index

Documents:

| Document | Content |
| --- | --- |
| [`docs/ONE_PAGER.md`](docs/ONE_PAGER.md) | One page for judges |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Technical document: components, request paths, trust boundaries, evidence model, security |
| [`docs/WORKFLOWS.md`](docs/WORKFLOWS.md) | Robert and Mateo step by step, mapped to routes and engine concepts |
| [`docs/DEMO_SCRIPT.md`](docs/DEMO_SCRIPT.md) | Timed recording script, checklist, fallback, claims not to make |
| [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) | Deployment runbook: order, values to supply, checks, rollback, teardown |
| [`docs/requirements.md`](docs/requirements.md) | Official requirements, our choices, assumptions and open questions |
| [`docs/BUILD_BRIEF.md`](docs/BUILD_BRIEF.md) | Binding product and engineering rules |
| [`docs/LEAD_DECISIONS.md`](docs/LEAD_DECISIONS.md) | Frozen decisions D1 to D9 |
| [`docs/PLAN.md`](docs/PLAN.md) | Milestones, deadline, cut order, open items |
| [`docs/data-sources.md`](docs/data-sources.md) | Every data source, hash, processing step, limitation and licence note |
| [`contracts/README.md`](contracts/README.md) | What the contracts are and how to check them |
| [`contracts/api.md`](contracts/api.md) | The seven routes: requests, responses, errors, idempotency, polling |
| [`contracts/SEMANTICS.md`](contracts/SEMANTICS.md) | Normative meaning of rules, bounds, replay, summaries and evidence |
| [`contracts/fixtures/engine/HAND_CALCS.md`](contracts/fixtures/engine/HAND_CALCS.md) | Hand arithmetic for the engine cases |
| [`backend/engine/README.md`](backend/engine/README.md) | Engine functions and version notes |
| [`backend/engine/evidence/robert_max_compliant.md`](backend/engine/evidence/robert_max_compliant.md) | Robert's maximum compliant weight on the real data |
| [`infra/README.md`](infra/README.md) | Resources, IAM, lifecycle rules, decisions; what differs between the deployed stack and the candidate |
| [`infra/evidence/milestone2.md`](infra/evidence/milestone2.md) | Recorded live proof of the deployed phase-1 slice |
| [`scripts/deploy.md`](scripts/deploy.md) | Backend deployment sequence, rotation, the next-deploy checklist |
| [`acceptance/mateo/README.md`](acceptance/mateo/README.md), [`FINDINGS.md`](acceptance/mateo/FINDINGS.md) | Mateo acceptance suite and the live check script |
| [`acceptance/fullstack/README.md`](acceptance/fullstack/README.md), [`FINDINGS.md`](acceptance/fullstack/FINDINGS.md) | Browser run of the built frontend against the real handlers, locally |
| [`validation/ACCEPTANCE.md`](validation/ACCEPTANCE.md) | Independent go / no-go criteria. The validation report is to be added by the coordinator |

Code and data:

| Path | Content |
| --- | --- |
| `contracts/schemas/`, `contracts/python/`, `contracts/typescript/contracts.ts` | JSON Schemas, validators and contract tests, TypeScript mirror |
| `contracts/scenarios/`, `contracts/fixtures/` | The three personas; engine cases; API example exchanges. All fixture numbers are synthetic |
| `backend/engine/`, `backend/tests/engine/` | Deterministic engine and its tests |
| `backend/api/`, `backend/worker/`, `backend/agents/`, `backend/common/` | API handler and authorizer; worker; Bedrock loop, tools, explanation templates, interpreter; job store, policy store, snapshot loader |
| `backend/tests/service/` | Service tests (no network, no AWS) |
| `data/scripts/`, `data/starter/`, `data/processed/`, `data/curated/`, `data/manifests/` | Pipeline scripts, organizer files, normalized outputs, controversy records, raw-file hashes |
| `frontend/` | The interface, unit tests and Playwright tests |
| `acceptance/`, `validation/` | Acceptance suites and the independent validation suite |
| `infra/template.yaml`, `scripts/package.py`, `scripts/build_snapshot.py`, `scripts/mcp/` | SAM template, packaging, snapshot builder, deployment snippets |
| `amplify.yml` | Amplify build specification for a Git-connected app (never executed; the runbook uses a manual deploy instead) |
| `.claude/agents/` | Definitions of the development agents |

## 4. Milestones and status

Milestones are defined in `docs/PLAN.md` P7. "Coordinator's run" means the
integration coordinator's local run on the candidate with the real data,
2026-11-14/15; "our run" means a command run for this README (section 6).

| # | Milestone | State | Evidence |
| --- | --- | --- | --- |
| 1 | Requirements, schemas, fixtures | Done | `docs/requirements.md`, `contracts/`; contract tests pass (section 6) |
| 2 | Minimal AWS vertical slice | Done in AWS, phase 1, placeholder calculation | `infra/evidence/milestone2.md` |
| 3 | Data and deterministic engine | Done. Validators and engine both refuse NaN and infinities | `backend/engine/`, `contracts/SEMANTICS.md` section 1; tests |
| 4 | Frontend on typed fixtures | Done locally: contract types, 3D exposure explorer with a flat chart and table as the fallback | Coordinator's run: typecheck and lint clean, 471 unit tests, build OK, 25 browser tests on fixtures or a stub; the three.js chunk (558,259 bytes, 136,902 gzipped) is not referenced by `index.html` |
| 5 | Robert end to end through the real API | Done **locally** against the real handlers; **not on AWS** | `acceptance/fullstack/`: coordinator's run 30 of 31 (the one failure is a test expecting a model-written sentence that the backend deliberately no longer returns) |
| 6 | Mateo | Done **locally**; the live check script is prepared and has never been run against a deployment | `acceptance/mateo/` |
| 7 | Independent validation | Third pass on `d223714`: 1268 passed, 6 strict expected failures; verdict "go with disclosed limits", **conditional on fixing F-20** (HIGH: model-chosen strings in public tool steps; fix in progress). Fourth pass (interpreter, new IAM) in progress | Reported by the coordinator; the validation report is not in the repository yet |
| 8 | Deliverables, hosted frontend, push | Documents written. **Nothing deployed or hosted.** `integration/rc` is not pushed; GitHub `main` holds an earlier snapshot that is not a validated release | `docs/DEPLOYMENT.md` |

Amira is selectable as a third persona since PR #16 (2026-11-15); her scripted Amira demonstration beyond
that, horizon analysis, the 2D map and the questionnaire are not started. Status on 2026-11-15, after this
table was written: a first release was deployed and hosted (`infra/evidence/release-2026-11-15.md`), then replaced
the same evening by the release that carries "Customize this profile", the Amira persona and the corrected data
snapshot (`infra/evidence/release-2026-11-15-customize.md`: exact artifacts, checks run, and what was not checked).
The status block at the top of this file and the table in section 4 predate both releases.
The submission deadline and the exact hour at which the AWS account expires
are unresolved (`docs/PLAN.md` P2).

## 5. Problems and the solutions in the code

| Problem | Solution | Source |
| --- | --- | --- |
| A model could skip an unfavourable calculation or pass wrong arguments | The worker runs the engine on the stored request before and independently of any model call; the result is that run | `backend/worker/investigation.py`, `infra/README.md` |
| A model could write a wrong or advisory sentence | No model sentence is returned. Decisive sentences are the engine's templates; the model may only select an evidence record and a template id, and the server writes the sentence | `backend/agents/explain.py` |
| The interpreter could invent a threshold or obey text addressed to it | The model's tool schema has no numeric member; it marks spans and picks codes from closed lists; a number is read by the server from the user's own words under strict conditions, otherwise the user is asked | `backend/agents/interpreter.py` |
| The model is unavailable | The job still succeeds with the same checks and template text, marked `DETERMINISTIC_FALLBACK` | `infra/README.md`, `acceptance/fullstack/README.md` |
| Lambda asynchronous delivery is at least once, so a job could run twice | The worker claims a job by compare-and-swap (`If-Match`); results and traces are write-once | `backend/common/jobs.py` |
| A policy version could be overwritten | A version is written only with `If-None-Match`; IAM allows nothing else on `policies/` | `backend/common/policies.py`, `infra/template.yaml` |
| API Gateway throttling did not bound a burst | Reserved concurrency of 5 on the worker | `infra/README.md` "Decisions" |
| A job could hang forever if the worker died | 150 s deadline; a `GET` turns an overdue job into `FAILED / DEADLINE_EXCEEDED`; the page polls for 180 s | `backend/api/handler.py`, `frontend/src/lib/config.ts` |
| Missing or partial fund holdings could look like zero exposure | Interval semantics: lower and upper bound; UNKNOWN when the limit falls inside the range | `docs/LEAD_DECISIONS.md` D4, `contracts/SEMANTICS.md` 5 |
| NaN or infinity in a document could drop a position silently | Rejected by every contract validator and, independently, by the engine | `contracts/SEMANTICS.md` 1 |
| Bad data could reach a verdict | The snapshot is validated when built and again when loaded (manifest id, SHA-256 of every file, contract validators); a failing snapshot serves nothing | `scripts/build_snapshot.py`, `backend/common/data.py` |
| "Avoid oil" has no single meaning | The interpreter asks which supported definition is meant; unsupported definitions are listed as such | `docs/LEAD_DECISIONS.md` D3, D7 |
| Any website could drive the API from a browser holding the code | `AllowedOrigin` has no default; the deploy snippet refuses to execute with `*` | `infra/template.yaml`, `scripts/mcp/02_deploy.py` |
| A rotated access code kept working for minutes | No API Gateway authorizer cache; 30 s function cache (not yet observed in AWS) | `scripts/deploy.md` section 7 |
| Fixture output could be mistaken for live output | A persistent "Test data — fixtures" label in fixtures mode | `frontend/src/components/shell/AppShell.tsx` |
| Credentials in the browser bundle | The access code is typed at runtime and kept in `sessionStorage`; no secret is a build variable | `frontend/src/lib/access-code.ts` |
| Third-party data that may not be redistributed | Raw issuer files, issuer-derived files and Yahoo-derived prices are git-ignored and are never in the Lambda zip; the functions read them from the private bucket | `.gitignore`, `data/.gitignore`, `scripts/deploy.md` 3b |

## 6. Run, test and build

Requirements: Node.js 22.12 or later, Python 3.14,
[`uv`](https://docs.astral.sh/uv/).

Backend, engine and contracts, from the repository root:

    uv run --no-project --python 3.14 --with pytest --with boto3 --with jsonschema \
      pytest backend/tests contracts/python/tests -q

| Run | Result |
| --- | --- |
| Our run, a checkout of the candidate **without** the git-ignored data files | **1685 passed, 9 skipped.** The skipped tests need `data/processed/holdings.json`, `instruments.json` and `market_data.json` |
| Our run of `pytest acceptance/mateo validation`, same checkout | 874 passed, 586 skipped, 3 expected failures, **3 failed**. The three failures are the validator's static review of the API function's role (`validation/tests/test_v29_v31_static_review.py`): it predates the Bedrock permission that the interpreter added, and belongs to the fourth validation pass in progress |
| Coordinator's run, with the real data | Backend, contracts and Mateo suites: 1883 passed, with 1 known test under re-judgement |

Other suites (commands from their READMEs):

    uv run --no-project --python 3.14 --with pytest --with boto3 --with jsonschema pytest acceptance/mateo -q
    uv run --no-project --python 3.14 --with pytest --with boto3 --with jsonschema pytest validation -q -rsx
    acceptance/fullstack/run.sh        # needs node, Chromium for Playwright and the git-ignored data

Frontend (scripts in `frontend/package.json`; the results in section 4 are
the coordinator's, we did not run them):

    cd frontend
    npm ci
    npm run dev            # development server
    npm run build          # static export to frontend/out
    npm start              # serve frontend/out on http://127.0.0.1:4173
    npm test               # contract sync check, then unit tests
    npm run typecheck && npm run lint
    npm run test:e2e:install && npm run test:e2e

To point a build at an API, set `NEXT_PUBLIC_API_BASE_URL` (see
`frontend/.env.example`). With no base URL, or with `?fixtures=1` in the
address, the app uses recorded fixtures and says so
(`frontend/src/lib/config.ts`). Never put the access code in a build variable.

Data pipeline and snapshot. A fresh clone lacks the files listed in section 8
and must restore them first (`docs/data-sources.md` section 1):

    python3 -I data/scripts/build_processed.py
    python3 -I data/scripts/quality_checks.py
    python3 scripts/build_snapshot.py --check

## 7. Deployment

The runbook is [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md). **None of it has
been executed for this candidate.**

- **Backend:** stack `before-you-buy` in `us-east-1`, through CloudFormation
  change sets (`scripts/deploy.md`). The next deploy needs a data snapshot
  uploaded first and two parameters without defaults: `DataSnapshotId` and
  `AllowedOrigin`.
- **Frontend:** Amplify Hosting, manual deploy of the built `frontend/out`.
  The Amplify app is created first, because the backend needs its origin.
- **What AWS runs today:** the phase-1 stack. A successful investigation there
  is proof of the pipeline, not a financial result.

## 8. Data, sources and licences

- **Organizer starter files:** prices, FX, macro series and the asset
  universe. They hold no ETF constituents, no portfolios and no ESG or
  controversy data.
- **ETF holdings:** from the issuers' own files (State Street for SPY,
  BlackRock Canada for XIU), one snapshot dated 2026-11-12. It is used only
  for today's look-through and never as historical composition.
- **Controversy registry:** three records from official pages.
- **Not redistributed:** the raw issuer files, the issuer-derived processed
  files and the Yahoo-derived prices and corporate actions, because of the
  issuers' and Yahoo's terms; and the organizer's case material. They are
  git-ignored, never packaged in the Lambda zip, and reach the functions only
  through the private bucket. Whether the issuer-derived files may be
  published is a pending decision (`docs/data-sources.md` section 6).
- **Regulatory context:** a CIRO news release dated 2026-03-12 announces
  guidance that, in its words, "broadens the range of decision-making supports
  that OEO dealers can offer to clients without violating the rule that
  prohibits them from making recommendations". The guidance itself was not
  read, and nothing here implies regulatory approval of this prototype
  (`docs/data-sources.md` section 8).

Full provenance, hashes and terms: `docs/data-sources.md`.

## 9. Screenshots

| Where | What | Data shown |
| --- | --- | --- |
| `acceptance/fullstack/screenshots/` | 14 screens of the built frontend against the real handlers on one machine: Robert's policy, preview, steps, verdict, evidence drawer and v1/v2 comparison; the access gate; Mateo's verdicts; error states; the 3D explorer and its flat fallback | **Local backend, real data.** No AWS, no Bedrock, no hosted site. Recorded at `db9678c`, before the interpreter existed (one screen shows its 502 answer) |
| `docs/review/screenshots/explorer-d36e41f/` | 7 screens of the exposure explorer | From the review session at `d36e41f`; illustration only |
| Branch `review/visual-verification` | Baseline of the first interface at `db0b90f` | **Fixture data**; superseded |

No screenshot of a deployed or hosted system exists.

## 10. Disclosed limits

- **Access control** is one shared access code. It is not user identity and
  gives no isolation between users. Acceptable only because all data is
  fictional.
- **Model text is never shown.** Explanations are server templates; the model
  only selects evidence and tools.
- **The interpreter depends on a model that has never been called live** with
  its prompt. If it fails, the user gets a readable error and can confirm the
  scenario's offered rules by hand.
- **The `POST /check` budget of 5 s is measured, not pre-emptive.** The time
  is checked after the calculation and a late result is refused; a running
  calculation is not interrupted (`backend/api/handler.py`).
- **Policies and results do not expire in storage.** Only job documents and
  traces have a lifecycle rule (`infra/template.yaml`).
- **ESGV and QQQ holdings are missing** on purpose; exposure through them is
  unknown, never zero.
- **SPY has no per-constituent sector label**, so a sector rule is unknown
  through SPY.
- **The controversy registry holds three records.** Absence means "not
  assessed", never "no controversy".
- **Nothing in this candidate has run in AWS.** API Gateway behaviour, IAM,
  real S3 conditional writes, Lambda timing and Bedrock were emulated or faked
  in the local runs (`acceptance/fullstack/README.md`, "What this does not
  prove").
- **Open frontend findings** F-01 to F-08, none blocking; for example, polling
  stops after three failed polls (`acceptance/fullstack/FINDINGS.md`).
- **The 2022 replay** tests an assumed allocation against one past year. It is
  not a forecast.
- **The AWS account is deleted at the end of 2026-11-16.** Any hosted URL
  stops working then.

## 11. How this was built

Built with Claude Code (Claude Fable 5.2) using role-scoped development agents
with non-overlapping file ownership (`docs/LEAD_DECISIONS.md` D9,
`.claude/agents/`). The application's runtime model is separate:
`us.anthropic.claude-sonnet-5-5` on Amazon Bedrock. The development model
never appears in application code.
