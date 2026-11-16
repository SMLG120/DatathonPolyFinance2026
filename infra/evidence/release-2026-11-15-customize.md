# Release "Customize this profile" + corrected data snapshot, 2026-11-15 (evening)

Status: **deployed and verified live** (backend 19:35 EST, frontend 19:44 EST). Hosting: https://main.dwtdk87nismj6.amplifyapp.com/ .
This is a second release on 2026-11-15; `release-2026-11-15.md` describes the earlier one (code `bd73f44e`, snapshot
`snap-2026-11-12-c2289f2b406d`). The API still requires the existing access code, which was not displayed, changed or stored.

Built from an **uncommitted working tree** on top of `origin/main` 1f582bf, so the release is identified by hashes:

| Artifact | Value |
| --- | --- |
| Bundle `cloudshell-release-customize.zip` | sha256 `b2b0a76701b9613a89fc5ebf632a7724037cc39a081f93d7416285384747b1d4` |
| Code key | `lambda/byb-backend-7c459ee17d81cff1.zip` (sha256 `7c459ee17d81cff1822b8a25f7b16750b4e729c4c11a3fd97959e7557475525c`) |
| Data snapshot | `snap-2026-11-12-2662b7a89c03` (XIU.TO as of 2026-11-12; replaces the look-ahead snapshot) |
| Frontend `frontend.zip` | sha256 `393138fe726707d29d4dd677b5e668bbcac19f3d4b0ba09fc462d3cd74c1184c` |

## Source of the published artifacts (audited 2026-11-15 19:41 to 19:50 EST, by file comparison)

This audit did not query AWS: which artifacts run there is taken from the steps recorded below. What was compared is the
content of the local copies of those artifacts with Git and with the working tree.

- **Backend zip**, 63 files, each compared byte for byte:
  - 63 of 63 identical to the working tree at the time of the audit;
  - 52 identical to `origin/main` (1f582bf, and 4e32a12 after the fetch of 19:41);
  - 11 are in no commit and on no branch of the remote: `backend/api/handler.py`, `backend/worker/investigation.py`,
    `backend/engine/check.py`, `backend/common/jobview.py`, `backend/common/portfolios.py` (new file),
    `backend/agents/prompts.py`, `backend/agents/tools.py`, `contracts/python/byb_contracts/result_validators.py`,
    `contracts/schemas/api.schema.json`, `contracts/schemas/check_result.schema.json`,
    `contracts/schemas/investigation_job.schema.json`.
- **Data snapshot**, 9 files: `controversies.json` and the three scenarios are identical to `origin/main`; `sources.json` is
  identical to the uncommitted `data/processed/sources.json` and differs from `origin/main`; `holdings.json`,
  `instruments.json` and `market_data.json` are git-ignored by design and identical to the local processed files.
- **Template**: `template.yaml` of the bundle is identical to `infra/template.yaml` on `origin/main`.
- **Frontend `frontend.zip`**: built at 18:24 EST from the working tree. No file under `frontend/src`, `frontend/public` or the
  frontend configuration is newer than the archive. It calls `https://3t4hod912l.execute-api.us-east-1.amazonaws.com`.
- **Not in the published frontend**: PR #20 ("added color", merged into `origin/main` as 4e32a12 at 19:36 EST, after the site
  was built). The published style sheet still has the earlier palette (`--color-banner: #18181b`). PR #20 changes three
  frontend files and nothing in the backend, the contracts or the data.
- The earlier release of the same day (`release-2026-11-15.md`, code `bd73f44e`) was different: all 61 files of that zip are
  identical to commit 0774e12, which is on `origin/main`.

Until the working tree is committed and pushed, the only copies of the source of this release are the working tree and
the backup `byb-backup-2026-11-15-deployed-source/` kept beside the repository on the owner's machine.

## What was run (procedure of `scripts/deploy.md`, "Customize this profile")

Access: boto3 with the workshop profile on the owner's machine (role `WSParticipantRole`), authorized by the owner. The AWS MCP
tool was not available in that session; the AWS CLI was not used.

1. `cloudshell_release.py prepare`: snapshot and code uploaded, change set created, nothing executed.
2. Change set `arn:aws:cloudformation:us-east-1:010928212265:changeSet/release-d734b96da9e5ec3547c0/1723043b-9192-4c29-9dc0-aff5cd3d0eca` reviewed: parameters equal to the plan; its template
   identical to the deployed template; 6 `Modify`, no `Add`, no `Remove`: the three functions, the HTTP API body, the authorizer
   invocation permission (conditional replacement) and `ApiFunctionRole` (a `Dynamic` evaluation caused by `WorkerFunction.Arn`;
   the policy text comes from an unchanged template, so no permission changed).
3. `execute` 19:34; `UPDATE_COMPLETE` 19:35:36. `verify`: `verified: true`, running the code key and snapshot above.
4. `cloudshell_smoke.py` (real Bedrock): **RESULT: PASS (23 checks, 0 warnings, 17 requests)**; the interpreter asked what "oil"
   means and invented no threshold; the investigation ended `SUCCEEDED` in agent mode `MODEL`.
5. `cloudshell_customize_check.py`: **17 of 17 PASS**: Amira served; no fund holdings dated after the valuation date; Robert's
   NVIDIA upper bound 0.262763304 (the corrected snapshot); a customized portfolio checked and investigated as sent
   (`inv-d7d200e2bf88a9907400ee41a1b305d8`, agent mode `MODEL`); weights totalling 90% refused with 400.
6. `host`: Amplify app `dwtdk87nismj6`, branch `main`, job `3`: `SUCCEED` at 19:44:31.
7. Hosted site in headless Chromium (`validation/customize/hosted_check.py`): **16 of 16 PASS**: live build; Amira's portfolio
   loads; Robert customized (JNJ removed, SPY 15%, cash 40%), rules confirmed, NVDA to 25% investigated
   (`inv-ad0569d63ce7aa6c90e324b49fee3169`, agent mode `MODEL`); the request bodies carry exactly the displayed weights; the job
   stores that portfolio; the report says "Customized fictional portfolio" with the edited weights; no console error.
   Screenshots: `validation/customize/screenshots-hosted/` (regenerated on every run; kept on the owner's machine, not
   committed).

## Not covered by this evidence

- Mateo and the challenge flows were not driven on the hosted site (they were on the local full stack: `acceptance/fullstack`,
  39 of 39).
- Known UI gaps left for a follow-up, none introduced by this release: the banner's valuation date is visually hidden
  (`sr-only`, since commit 0774e12; BUILD_BRIEF section 8 asks for a persistent one); a finished job's steps have no link from
  the result; some wording still names the six-stage screens.
- Rollback was not exercised on AWS. Targets and steps: `scripts/deploy.md`, "Rollback".
