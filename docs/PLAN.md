# Project plan and working rules

Owner's corrections of 2026-11-14 (evening) are recorded here. Where this file
and `docs/BUILD_BRIEF.md` or `docs/LEAD_DECISIONS.md` differ on process, this
file wins. Fields the owner has not filled in are marked **UNRESOLVED**.

## P1. Milestone stopping rule

One milestone at a time. At the end of each milestone the lead:

1. Stops edits and pauses the subagents.
2. Reports completed work, changed files, tests actually run (re-run by the
   lead, not only reported by an agent), remaining issues, and any preview URL
   or screenshots.
3. States the next milestone and its estimated effort.
4. Waits for the owner's explicit "continue".

A blocked milestone is reported with its blocker and the work completed. Scope
is never expanded silently and no later milestone is started early.

## P2. Deadline

- Submission deadline: **UNRESOLVED** (date, time and timezone not given).
- Time reserved for final testing and recording: **UNRESOLVED**.
- Because both are blank, this plan does **not** assume there is enough time.
- AWS account expiry, from the organizer's cheat sheet ("Atelier AWS
  PolyFinances, aide-mémoire", section 1): "compte valide jusqu'au lundi 16
  novembre, en fin de journée (heure exacte précisée avec le code), puis
  supprimé avec toutes ses données". The exact hour and timezone are stated
  only with the team's access code, which this session has not seen:
  **UNRESOLVED**.
- Provisional internal target only: have the recording saved and the code
  pushed by Monday 2026-11-16 12:00 Eastern. This is our own planning figure.
  It is not a guaranteed safe deadline: the real submission deadline and the
  real expiry hour may be earlier.
- Before access expires: the demo recording is saved locally, the code is on
  GitHub, and `infra/README.md` + `scripts/deploy.md` let someone redeploy
  the stack in another account.

Remaining time is recalculated at every checkpoint once the deadline is known.
Priority: Robert's complete, tested workflow and the four required
deliverables.

## P3. Cut order if time is tight

1. Optional questionnaire.
2. 2D map and cosmetic enhancements.
3. Extended-history horizon analysis.
4. Additional funds and broad controversy coverage.
5. Expanded Amira demonstration.
6. Additional Mateo features beyond the smallest credible second scenario.

Never cut: calculation correctness, explicit rule confirmation, missing-data
handling, essential validation, real AWS integration. Material cuts are
proposed in a checkpoint report for the owner's review, not made silently.

Items 1–3 were never started (they are disabled extensions in BUILD_BRIEF §1).

## P4. AWS configuration

The owner's template fields are still blank. These are the existing values,
re-verified with read-only calls on 2026-11-15 (UTC):

| Field | Verified value | Check |
| --- | --- | --- |
| Account ID | `010928212265` | `sts:GetCallerIdentity` |
| Region | `us-east-1` (all other regions explicitly denied by `ws-default-policy`) | policy document; stack lives there |
| Authentication method | AWS MCP server tool in the Claude Code session, assumed role `WSParticipantRole` (Workshop Studio). No AWS CLI profile, no access keys in the repo. | caller ARN |
| Bedrock identifier | Inference profile `us.anthropic.claude-sonnet-5-5` (foundation model `anthropic.claude-sonnet-5-5`), stack parameter `BedrockModelId` | real Converse call returned a reply; `DescribeStacks` with `StackName=before-you-buy` |
| Stack | `before-you-buy`, `UPDATE_COMPLETE`; HTTP API, three Lambdas on `python3.14`, one private data bucket; no Amplify app yet | `DescribeStacks`, `amplify:ListApps` |

The development model (Claude Fable 5.2 in Claude Code) is not used by the
application and is not assumed to be the Bedrock runtime model.

**Limits.** No approved spending or resource limit has been given by the
owner or found in the organizer material: **UNRESOLVED**. What exists is
self-imposed engineering protection, which is not a budget: worker reserved
concurrency 5; API throttling (5 rps / burst 10 on `POST /investigations`,
20 rps / burst 40 otherwise); bounded tool rounds, tokens and a 150 s job
deadline; 7-day log retention; lifecycle expiry on job objects.

If the owner's values differ from the verified ones, deployment stops and the
mismatch is reported. Every `DescribeStacks` call passes
`StackName=before-you-buy`.

## P5. `build_dataset.py`

Not located in the current checkout; user reports it exists in
`alphaforge_starter`.

Searched on 2026-11-14 without finding the folder or the script: the home
directory by filename, Spotlight, and the zip archives in Downloads. Organizer
delivery of the script has not been verified by us. When it is placed at
`data/starter/build_dataset.py`, the data agent inspects it and reuses or
adapts it, preserving its behaviour. Until then `data/scripts/` builds the
processed files from the supplied CSVs.

## P6. Locally supplied fund holdings

- Directory for issuer holdings files: `data/raw/etf_holdings/` (gitignored).
  The build reads only from there.
- The demo never depends on live issuer access: the build reads local files
  only, and the deployed app reads a snapshot from the private S3 bucket.
- Files are inventoried and validated before use; issuer, source URL, holdings
  date, retrieval date, weight units, coverage and reuse terms go in
  `data/manifests/raw_files_manifest.json` and `docs/data-sources.md`.
- Missing holdings are never invented and never treated as zero exposure.
- Source files whose terms prohibit redistribution are not committed; the
  documentation says how to obtain them.

Inventory on 2026-11-14:

| File | Issuer | Holdings date | Coverage | Status |
| --- | --- | --- | --- | --- |
| `SPY_2026-11-14.xlsx` | State Street | 2026-11-12 | 0.99871 (503 holdings) | Valid. No per-constituent sector in the file. Fetched by script. |
| `XIU_2026-11-14.csv` | BlackRock Canada | 2026-11-12 | 0.9977 (60 holdings) | Valid. Fetched by script; kept by the owner's decision because provenance and contents validate. How it was fetched and the issuer's terms are disclosed in `docs/data-sources.md`. |
| ESGV, QQQ | — | — | — | Not acquired by design; exposure through them is UNKNOWN. |

Inventory on 2026-11-15 (files in use after that day's refresh and correction):

| File | Issuer | Holdings date | Coverage | Status |
| --- | --- | --- | --- | --- |
| `SPY_2026-11-15.xlsx` | State Street | 2026-11-12 | 0.99871 (503 holdings) | In use. Byte-identical to `SPY_2026-11-14.xlsx` (same SHA-256). Fetched by script. |
| `XIU_2026-11-14.csv` | BlackRock Canada | 2026-11-12 | 0.9977 (60 holdings) | In use. Restored from a teammate's copy, SHA-256 verified against the manifest. |
| `XIU_2026-11-15.csv` | BlackRock Canada | 2026-11-13 | 0.9973 (60 holdings) | Registered, **not used**: dated after the valuation date (look-ahead). The build skips it and quality check Q29 guards it (`docs/data-sources.md` 2.2). |

## P7. Milestones

| # | Milestone | State on 2026-11-15T00:40Z | Estimated remaining effort |
| --- | --- | --- | --- |
| 1 | Requirements, schemas, fixtures | Mostly done; `api.md`, `requirements.md`, README, Mateo fixture fix in progress | about 30 min |
| 2 | Minimal AWS vertical slice | Met; phase-1 evidence refresh pending | about 15 min |
| 3 | Data and deterministic engine | Data done; engine reports 204 tests passing | lead re-check only |
| 4 | Frontend on typed fixtures | In progress (moving to contract types) | about 45 min |
| 5 | Robert end to end through the real API | Not started (backend phase 2, live frontend wiring) | about 2 h |
| 6 | Mateo | Not started | about 45 min |
| 7 | Independent validation | Not started | about 1 h |
| 8 | Deliverables, hosted frontend, push | README draft with the review session; rest not started | about 1.5 h |

Extensions (Amira, horizon, map, questionnaire) are scheduled only after
Milestone 8 and only with the owner's agreement.

## P8. Open items carried out of Milestone 1 (recorded 2026-11-15)

Evidence quality, to fix in Milestone 3 (engine); the arithmetic is verified,
but the result is **not yet fully traceable**:

1. `ev-max-final` must link every input its closed form uses: the starting
   scenario return, the instrument's scenario return, the look-through
   exposure records and the unattributed-weight records, not only the two
   thresholds, starting cash and starting weight.
2. The engine test case list (`backend/tests/engine/engine_helpers.py`) must
   include the new contract fixture M2; until then
   `test_every_fixture_file_is_covered` fails (1 failed, 203 passed).
3. Decide whether the unrounded boundary belongs in the result. The contract
   serializes 9 decimals. For Robert on real data the serialized value happens
   to lie below the exact boundary and is feasible without the 1e-9 tolerance.
   **Open defect (found by the review session, line confirmed by the lead,
   reproduction not re-run by the lead):** `backend/engine/boundary.py` rounds
   the maximum to the *nearest* 9th decimal, not down, so for a threshold with
   more than nine decimals the returned weight can exceed the exact boundary
   by up to 5e-10 and pass only through the tolerance, with a positive gap on
   a PASS result. Fix: round down, add a property test over random thresholds
   asserting measured <= limit exactly at the returned weight, and settle how
   a within-tolerance PASS reports its gap. Fewer digits in display text is a
   presentation choice, not a defect.

Other:

- SPY's file leaves 0.00032528 of the fund unexplained (not rounding, not a
  printed line). It stays unresolved and is covered by the upper bound.
- The frontend's synced contract copies are stale (11 files) and the frontend
  does not typecheck: Milestone 4.
- Proposed integration at push time: a normal merge of
  `origin/review/visual-verification` into `feat/before-you-buy-prototype`
  (no force, no reset), re-checked for conflicts at that time.

## P9. Review-session findings to schedule (received 2026-11-15, not verified by the lead)

For Milestone 4 (frontend):

- Delete every hand-written result object; fixtures mode uses only the synced
  contract fixtures. Add a guard test and `sync-contracts --check` to the test
  script.
- Take cash after purchase, the before/after table, headline, counts and the
  maximum compliant weight from the API response; no financial arithmetic in
  the browser.
- Generate idempotency keys with `crypto.randomUUID`.
- Render model-written text as plain text only.
- Every figure in screenshots and the demo script names its source: contract
  synthetic fixture, or real data.

For Milestone 5 (backend phase 2):

- Wrap third-party text returned by tools (controversy evidence) as untrusted
  data, the same way the request is wrapped.

For Milestone 8 (hosting):

- Amplify custom headers: Content-Security-Policy restricting `connect-src`
  to self and the API origin, `X-Content-Type-Options`, `Referrer-Policy`,
  `frame-ancestors 'none'`; tighten `AllowedOrigin` in the same change.
- Keep the disclosure that one shared access code gives no isolation between
  users; acceptable only because all data is fictional.

Explorer (3D exposure view): **confirmed by the owner in the lead session on
2026-11-15**. It is part of Milestone 4 as a progressive enhancement and must
not block contract integration or the functional verdict experience.

- Built by the review session in its own worktree under
  `frontend/src/components/explorer/`; integrated only after the
  contract-typed frontend build passes and is committed.
- Plain `three` (no `@react-three/fiber`), loaded lazily; the lead's frontend
  agent adds the dependency and regenerates the lockfile.
- The existing 2D chart and table remain the source of truth and the fallback
  (no WebGL, chunk failure, reduced motion, forced colours, narrow screens).
- No financial arithmetic in the browser; unknown or uncovered weight is drawn
  as an explicit range, never as zero; a draft value never becomes a confirmed
  rule.
- This is a 3D chart of issuer exposure. The "3D values map" excluded by
  `docs/BUILD_BRIEF.md` §1 stays excluded.

## P10. Open defects from independent validation (2026-11-15)

Blocker class (false pass), reproduced by the lead:

- **F-01 / F-05, contracts validators.** `validate_portfolio` accepts a NaN
  position weight and a NaN cash weight. The review session's validator
  reports that the engine then drops the position and can return PASS with a
  SUPPORTED maximum for a portfolio that breaches its cap. Not reachable over
  HTTP at d36e41f (the API rejects NaN in request bodies), but it must be
  closed before release: every numeric field in portfolio, purchase request,
  rule, holdings and market-data validators must be finite
  (`math.isfinite`), with negative tests; the engine must also refuse
  non-finite inputs at its boundary and never drop a position silently.

Other, for the milestones named:

- Engine: maximum rounded to nearest instead of down (P8); controversy
  evidence value must be the registry record id; Energy evidence must cite
  the sector fraction and emit a null sector-label record for an unclassified
  fund; cite the binding rule's records when no purchase is feasible.
- Contracts: the Mateo API fixture shows 11 numbers with no backing evidence
  record; reconcile with SEMANTICS §13. `docs/data-sources.md` says FX is
  matched to the price date while SEMANTICS says the valuation date; make the
  wording agree with what the engine does.
- Frontend (Milestone 4, in progress): no browser arithmetic for feasibility;
  headline from `summary.headline` including POLICY_CONFLICT,
  INVALID_REQUEST and EXECUTION_ERROR; treat `unknown_causes` as a set.
- Backend: model text must be validated against evidence before it is
  returned; snapshots must be validated when loaded; API role needs read
  access to the prefixes it serves.
- Hosting: tighten `AllowedOrigin`; a rotated access code keeps working for
  about six minutes (authorizer cache); the account id and API host appear in
  tracked files (not credentials; the account is deleted on 2026-11-16).
