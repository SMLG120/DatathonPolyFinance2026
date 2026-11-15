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
- Time reserved for testing, documentation and video: **UNRESOLVED**.
- Known hard constraint: the team AWS account is deleted at the end of the day
  on Monday 2026-11-16 (AWS workshop cheat sheet; exact hour not stated). The
  hosted demo and the video recording must be finished before then.

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

| Field | Owner's value | Verified by read-only checks (2026-11-15T00:3xZ) |
| --- | --- | --- |
| Account ID | **UNRESOLVED** | `010928212265` (`sts:GetCallerIdentity`) |
| Region | **UNRESOLVED** | `us-east-1`; all other regions are explicitly denied by the account's policy |
| Authentication method | **UNRESOLVED** | AWS MCP server tool, role `WSParticipantRole`; the AWS CLI profile is not used |
| Permitted Bedrock model IDs | **UNRESOLVED** | In use: `us.anthropic.claude-sonnet-5-5` (real Converse call succeeded). The development model is not used by the application. |
| Resource or spending limits | **UNRESOLVED** | Self-imposed: worker reserved concurrency 5, API throttling, 7-day log retention, lifecycle expiry on job objects |

Until the owner fills these in, work continues on the verified values, which
are the only account and region this session can reach. If the owner's values
differ, deployment stops and the mismatch is reported.

Every `DescribeStacks` call passes `StackName=before-you-buy`.

## P5. `build_dataset.py`

The owner states the script is supplied in the `alphaforge_starter` folder.
As of 2026-11-14 that folder and the script are **not present on this
machine**: a filename search of the home directory, Spotlight and the zip
archives in Downloads found neither. The supplied folder
`/Users/smlgmac/Datathon PolyFinance 2026` holds the five CSVs, the README,
`sources_metadata.csv` and `data_quality_warnings.txt`, but no script.

Therefore: earlier statements that the script "was not supplied" are corrected
to "supplied by the organizers, not yet available on this machine". When it is
placed at `data/starter/build_dataset.py`, the data agent inspects it and
reuses or adapts it, keeping its behaviour. Until then our own scripts in
`data/scripts/` build the processed files from the supplied CSVs.

## P6. Locally supplied fund holdings

- Directory for owner-supplied issuer files: **UNRESOLVED**. Proposed default:
  `data/raw/etf_holdings/` (gitignored), which the build already reads.
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
| `XIU_2026-11-14.csv` | BlackRock Canada | 2026-11-12 | 0.9977 (60 holdings) | Valid. Fetched by script before BlackRock's terms (which prohibit automated copying) were read; a browser-downloaded replacement is wanted. |
| ESGV, QQQ | — | — | — | Not acquired by design; exposure through them is UNKNOWN. |

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
