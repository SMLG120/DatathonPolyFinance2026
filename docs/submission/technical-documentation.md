# ETHOS: technical documentation

ETHOS (repository and stack name: Before You Buy). State described: the code freeze of 2026-11-15, 22:52 EST,
recorded in `infra/evidence/release-2026-11-15-freeze.md`. Where this document and an older one disagree
(`docs/ARCHITECTURE.md` and the status block of `README.md` predate the releases), this document and the release
records are the current ones.

Architecture and diagram: [`aws-architecture.md`](aws-architecture.md).

Where the official case asks for each item (Datathon official case 2026, English version, p. 15, "3. Technical
documentation"):

| Required content (p. 15) | Section |
|---|---|
| Overall logic, roles and interactions of the agents, controls or governance checks | 2, 3, 4 |
| Methods, models or technologies used and why they were chosen | 4, and `aws-architecture.md` |
| Sources, selected assets, data processing, assumptions | 5 |
| Explainability mechanism and an example connecting a conclusion to data or execution traces | 6 |
| Validation of results and explanations, limitations, proposed improvements | 10, 12, 13 |

## 1. Purpose and boundaries

An investor is about to buy something. ETHOS answers one question: **does this purchase respect the limits I
confirmed myself, and what is the evidence?** It looks through the funds already held, so a purchase that seems
small can be shown to push one company past a limit.

Boundaries, enforced in the product and not only stated:

- Simulation on fictional portfolios (three personas from the challenge: Robert, Mateo, Amira; each can be
  customized). No real transaction, no personalized advice, no recommendation, no forecast.
- A rule exists only when the user confirms it with a number the user can see. The system never invents a threshold.
- A result is PASS, FAIL or UNKNOWN. Missing data gives UNKNOWN or a range, never a zero and never a pass.
- Purchases are funded from existing cash only. Selling, shorting, leverage, fees and taxes are out of scope.

## 2. Components

| Component | Responsibility | Where |
|---|---|---|
| Frontend | Four-step journey (profile, limits, idea, result), evidence drawer, challenge screen, exposure views, printable report. Displays the engine's result; computes no verdict. | `frontend/` |
| API function | Validation against the shared schemas, policies, job creation and reads, instant check, rule interpreter, evidence route. | `backend/api/` |
| Worker function | Runs one investigation: engine first, then the investigator agent; stores result and trace. | `backend/worker/` |
| Deterministic engine | Pure Python: purchase simulation, look-through exposure, rule evaluation, historical replay, largest compliant purchase, evidence records. | `backend/engine/` |
| Agents | Rule interpreter and investigator; Bedrock client; tool definitions; validation of model output. | `backend/agents/` |
| Contracts | JSON Schemas, semantics, TypeScript and Python types, fixtures with hand calculations. | `contracts/` |
| Data pipeline | Acquisition, processing, quality checks, snapshot build. | `data/scripts/`, `scripts/build_snapshot.py` |
| Infrastructure | One SAM template. | `infra/template.yaml` |

## 3. One investigation, end to end

1. The user chooses a persona (optionally edits its weights), confirms limits, and enters a purchase as an
   instrument and a final weight.
2. `POST /investigations` (with an idempotency key): the API function validates the request, refuses one the engine
   cannot evaluate, stores the job with the exact portfolio it will be checked against, invokes the worker
   asynchronously and answers `202`.
3. The worker loads the snapshot named in its configuration, the stored policy version and the stored portfolio.
4. **The engine runs first** and produces the complete result: feasibility, each rule's status with measured value,
   limit and gap, exposures, replay, largest compliant purchase, data coverage, and one evidence record per figure.
5. The investigator agent then receives read-only tools over that result and the snapshot. It chooses which evidence
   to look at. Each tool call is recorded as a step the user can see.
6. The explanation shown to the user is built by the server from templates and evidence records. In this release no
   model-written sentence is displayed.
7. The job document is validated against the contract before it is published. An invalid document fails the job
   instead of being shown.
8. The browser polls the job and shows the report. The user can open the evidence of any figure, dispute a fact
   (stored as an unverified assertion; nothing is recomputed), clarify a preference, or change a rule, which creates
   a new policy version and a new report; the earlier report stays unchanged.

If the model is unavailable, too slow, or exceeds its limits, the worker completes the job on a deterministic path.
The verdict and every figure are identical in both modes, and the report says which mode ran.

## 4. Agents and model versus deterministic calculation

| | Rule interpreter | Investigator | Engine |
|---|---|---|---|
| Runs in | API function | Worker function | Both |
| Uses the model | Yes (Bedrock Converse, tool use) | Yes (Bedrock Converse, tool use) | No |
| Role | Turns the user's words into draft rule structures or a clarification question | Chooses which evidence to inspect for a result that already exists | Decides PASS, FAIL, UNKNOWN and computes every number |
| Cannot do | Set or suggest a threshold, confirm a rule, follow instructions in the user's text | Change a figure or a status, write advice, add uncited text | n/a |
| Controls | Closed tool schemas with no numeric member; output validated; bounded calls and time; user must confirm | Tools are read-only views of the engine's result; bounded rounds and calls (6 and 16 by default); deadline; contract validation; deterministic fallback | Tolerance `EPS = 1e-9`; fixtures with hand calculations; boundary verified by re-running the checks |

Model: Claude Sonnet 5.5 on Amazon Bedrock through the inference profile `us.anthropic.claude-sonnet-5-5`. Prompt
versions at the freeze: `investigator-5`, `interpreter-3`. Details: `docs/INTERPRETER.md`,
`backend/agents/prompts.py`.

Why this split: the challenge asks for explanations faithful to data and observable actions. Keeping the verdict in
auditable code and giving the model a bounded, visible role makes every statement traceable and makes a model failure
harmless to correctness.

Governance checks visible to the user: rules are inactive until confirmed; policy versions are immutable; a report
never changes after it is produced; the portfolio a report was checked against is stored with it; UNKNOWN is shown as
UNKNOWN.

## 5. Data

Full detail, with hashes, retrieval dates, terms of use and limitations: `docs/data-sources.md`.

- **Prices and FX**: the organizers' starter dataset (Yahoo Finance via yfinance, Bank of Canada USD/CAD),
  2021-11-12 to 2026-11-12.
- **Fund holdings**: issuer files for SPY (State Street) and XIU.TO (iShares), both as of 2026-11-12. Other equity
  funds have no holdings file in the snapshot; their whole weight is treated as unknown exposure.
- **Controversy registry**: a small curated set of regulator pages (U.S. EPA, Alberta Energy Regulator), each with a
  hashed raw copy and the sentences relied on. Absence from the registry is not evidence of absence.
- **Personas and portfolios**: fictional, from the challenge's three profiles.
- **Valuation date**: 2026-11-12, the last date of the starter data. It is a team decision, not a challenge
  requirement. No data dated after it is used: the build ignores a holdings file dated later, and a quality check
  enforces it (official case, p. 14, time consistency).
- **Processing**: reported fund weights are summed as published and never rescaled to 100%. The unreported part of
  a fund widens every company's exposure into a range from "proven" to "possible".
- **Provenance**: every figure in a result is an evidence record with a label (fact, assumption, fictional scenario,
  calculation), its source ids, its assumptions, its formula and the records it was derived from.
- **Snapshot**: processed data and scenarios are packed into an immutable snapshot whose id contains a content hash
  (`snap-2026-11-12-2662b7a89c03` at the freeze). The functions read only that snapshot.

Not redistributed: raw issuer files and Yahoo-derived prices are git-ignored and live only in the private bucket.

## 6. Explainability, with an example

Mechanism: the report shows, for each rule, the measured value or range, the limit, the gap and the engine's reason.
Any figure opens an evidence drawer with its label, value, period, source ids, assumptions, formula and the records
it was computed from. The investigation screen lists the real tool calls. The report can be printed or saved as PDF
with the same content, including what is unknown.

Example (Robert, original portfolio, purchase of NVDA to a final direct weight of 25%, limit of 10% per company):

- Conclusion shown: "Maximum exposure to a single company: FAIL, 26.2% to 26.3%, 16.2 points over the limit".
- Trace: direct weight after the purchase 0.25 (hypothetical purchase requested by the user) plus the SPY position
  0.20 multiplied by NVIDIA's reported weight in SPY 0.06137977 (holdings file as of 2026-11-12) gives 0.262275954,
  the proven lower bound. The upper bound, 0.262763304 on the live service, adds the part of the funds that their
  holdings files do not report. Both are above 0.10, so the status is FAIL whatever the unreported part holds.
- The same result on the live service was checked against the engine's instant check for the same inputs
  (`scripts/cloudshell_smoke.py`).

Contrast (Mateo, limits of 10% and 5%, SPY to 15%): the limits lie inside the possible ranges because one fund has no
holdings file, so both rules are UNKNOWN, the headline says "not determined", and no largest purchase is shown.

## 7. API contract and job lifecycle

Authoritative: `contracts/api.md`, `contracts/SEMANTICS.md`, `contracts/schemas/`. Units are portfolio fractions
(10% is 0.10). The eight routes are listed in `aws-architecture.md`.

Job lifecycle: `QUEUED` then `RUNNING` then `SUCCEEDED` or `FAILED`. A job is created once per idempotency key.
State changes are conditional writes, so two writers cannot both win. A job has a deadline (150 s); the client stops
polling after 180 s and says so. Once terminal, a job does not change, except that user corrections can be attached.
Job state and traces expire after 3 days.

## 8. Security and configuration

- One shared access code, stored as an SSM SecureString, checked by a Lambda authorizer on every route, never cached
  at the gateway, never in the site, the repository or the logs. It can be rotated without a deployment
  (`scripts/deploy.md`).
- CORS allows only the hosted site's origin. Requests are throttled per route; the worker has reserved concurrency.
- One IAM role per function, scoped to its own S3 prefixes, the one worker function and the one Bedrock inference
  profile. The bucket is private and encrypted.
- Inputs are validated against JSON Schemas; unknown members are refused, so a client cannot send its own figures.
- Text from the user or from data is displayed as text and never interpreted. Model output is validated before use.
- Configuration is by stack parameters and function environment variables (model id, snapshot id, limits). None is
  a secret. Names and defaults: `infra/template.yaml`, `backend/common/config.py`.
- No personal data: personas are fictional and nothing is stored per user.

## 9. Deployment, verification, rollback

Procedure: `scripts/deploy.md` (authoritative for commands) and `docs/DEPLOYMENT.md`. In short: package the backend
(`scripts/package.py`, content-addressed zip), build the snapshot (`scripts/build_snapshot.py`), create a
CloudFormation change set, review it, execute it, run the backend checks, and only then publish the site
(`scripts/cloudshell_release.py`, which refuses to publish in front of an unchecked backend). Rollback: a change set
back to the previous code key, and the previous site zip.

Deployed at the freeze (from `infra/evidence/release-2026-11-15-freeze.md`): site = Amplify job 9 built from `main`
at `22b2d9d`; backend `lambda/byb-backend-3366f6357259c7ec.zip`; snapshot `snap-2026-11-12-2662b7a89c03`. Each
release has a record in `infra/evidence/`.

## 10. Validation actually performed

Results reported at the freeze, on the final source and the deployed system:

| Check | Result |
|---|---|
| Frontend unit tests | 659 passed, 1 skipped |
| Frontend end-to-end (recorded test data, accessibility checks) | 33 passed |
| Full-stack browser suite: real handlers, worker and engine on the real snapshot, on one machine | 42 passed |
| Live API smoke test with the real model | PASS on rerun; about 1 live investigation in 6 fell back to the deterministic path |
| Live customization check | 17 of 17 |
| Hosted site, real browser, two real investigations including an UNKNOWN case | 78 of 78 |
| Python suites (contracts, backend, independent validation, Mateo acceptance) | Last full run 3750 passed, 22 expected failures, before the final two backend releases; not re-run at the freeze |

What validates the numbers: engine fixtures with hand calculations (`contracts/fixtures/engine/HAND_CALCS.md`), an
independent validation suite (`validation/`), data quality checks (`data/scripts/quality_checks.py`), and the live
comparison of investigation results with the instant check.

Not validated: browsers other than Chromium; real printers; load; Amira's full flow on the hosted site; rollback on
AWS was never exercised.

## 11. Reproduce

Requirements: Python 3.14 with `boto3` for the deployed code (the engine and contracts need only the standard
library), Node.js for the frontend. Setup details: `README.md`, `frontend/README.md`.

```sh
# Python suites (a virtual environment with pytest and boto3)
python -m pytest contracts/python/tests backend/tests validation/tests acceptance/mateo -q

# Frontend
cd frontend && npm ci
npm test            # contract copies check + unit tests
npm run typecheck && npm run lint
npm run test:e2e    # browser tests on recorded test data

# Full stack on one machine, real handlers and data, no AWS (needs data/processed)
validation/customize/run_browser.sh

# Data
python3 data/scripts/quality_checks.py
```

The site can be explored without AWS on recorded test data: `cd frontend && npm run dev`, then open `/?fixtures=1`.
The real data files that are not redistributed must be rebuilt first (`docs/data-sources.md`).

## 12. Known limitations

- Sources are shown as identifiers and dates; publisher, title and link are not delivered to the page.
- Only two funds have holdings data; funds without it produce UNKNOWN or wide ranges by design.
- Holdings are one dated snapshot; it is not the funds' historical composition, so the replay uses fund prices.
- The controversy registry is small and curated; it is not an ESG rating.
- About one live investigation in six completed on the deterministic path at the freeze.
- English only: a French catalogue is in the build but the language selector is not exposed.
- One shared access code; no user accounts; nothing persists beyond the browser tab except stored jobs and policies.
- The banner's valuation date is visually hidden; it is in the report and the printed report.
- The printed report is four pages for typical cases and was tested in Chromium only.
- The AWS account is temporary and is deleted at the end of 2026-11-16.

## 13. Proposed improvements (not built)

- Deliver the source registry to the page so every figure shows a readable citation with a link.
- Holdings for more funds, and dated history of holdings.
- Finish French: selector, remaining screens, printed report.
- Per-user sessions and saved reports.
- Let the investigator's findings appear as validated, cited sentences once a review step exists.
- Selling and rebalancing; fees and taxes.
- A broader, dated controversy and ESG evidence base.
