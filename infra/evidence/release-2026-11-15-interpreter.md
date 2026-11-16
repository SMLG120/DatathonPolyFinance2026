# Backend-only release: interpreter update (PR #22), 2026-11-15 20:28 EST

Status: **deployed and verified live**. Backend code only. The frontend (built from `fc4841a`, Amplify job 4), the data snapshot,
the template, IAM, routes and CORS are unchanged; no frontend deployment was made (latest Amplify job is still 4).

| Item | Value |
| --- | --- |
| Source commit | `bffec359278bc8cbb637cc1d5ce77d67e045d156` (`main` after the merge of PR #22; no newer commit on `origin/main` at packaging time) |
| Code key | `lambda/byb-backend-3a2220a805a80ce1.zip`, built by `scripts/package.py` on a clean export of that commit |
| Zip sha256 | `3a2220a805a80ce18f8059692ca28be1d0d6f571b323076129db881504524da4` |
| Previous code key | `lambda/byb-backend-7c459ee17d81cff1.zip` (rollback target; the only file that differs is `backend/agents/interpreter.py`) |
| Data snapshot | `snap-2026-11-12-2662b7a89c03` (unchanged) |
| Bundle | `cloudshell-release-interpreter.zip` sha256 `cce6af942c4d450244a31aca64af568cdc0d07b4f23fa5ffddb07fd4dd081e39` |

Access: boto3 with the workshop profile on the owner's machine (role `WSParticipantRole`), authorized by the owner. The AWS MCP tool
was not available in that session; the AWS CLI was not used.

## What was run

1. `cloudshell_release.py prepare`: change set created, nothing executed.
2. Change set `arn:aws:cloudformation:us-east-1:010928212265:changeSet/release-a325bf5f0803c55529d3/ac1619e0-8a4f-44c4-a3c9-01daa40b535d` reviewed before execution:
   - the only parameter that changes is `CodeS3Key`; `DataSnapshotId` and `AllowedOrigin` keep their values; none added or removed;
   - its template is identical to the deployed template;
   - 6 `Modify`, no `Add`, no `Remove`: the three functions (static change: the code key), and three `Dynamic` re-evaluations
     caused by function ARNs (`ApiFunctionRole` policies via `WorkerFunction.Arn`, the HTTP API body, the authorizer invocation
     permission with a conditional replacement). No permission, route or CORS text changed.
3. `execute` 20:27; `UPDATE_COMPLETE` 20:28:01. `verify`: `verified: true`. The `CodeSha256` of the API, worker and authorizer
   functions equals the sha256 of the packaged zip; all three `Active`, last update `Successful`.
4. `cloudshell_smoke.py` (real Bedrock): **RESULT: PASS (23 checks, 0 warnings, 16 requests)**, investigation in agent mode `MODEL`.
5. `cloudshell_customize_check.py`: **17 of 17 PASS** (customized investigation `inv-f0989099a19f127ad28dde121ae46556`, `MODEL`).
6. `cloudshell_interpreter_check.py`, the focused check of PR #22's behaviour with the real model. The same four sentences were
   sent to the previous backend first, as a baseline:

   | Case | Sentence | Previous backend (`7c459ee1`) | This release (`3a2220a8`) |
   | --- | --- | --- | --- |
   | A | "Keep any single company below 10%." | no draft; asked which number applies | proposed maximum, any company, 0.10, quote "10%" |
   | B | "I want more than 20% of my portfolio in NVIDIA." | no draft; asked which number applies | proposed minimum, NVIDIA, 0.20, quote "20%"; no maximum |
   | C | "I don't want more than 10% in any single company." | proposed maximum 0.10 | proposed maximum 0.10 (unchanged, as intended) |
   | D | "At most 5% in any single company. At least 10% in NVIDIA." | two drafts that no portfolio can satisfy together | no draft; one question ("cannot both hold") with keep-first-limit, keep-second-limit, keep-qualitative |

   **4 of 4 PASS**, each on the first attempt. In every case every rule is `PROPOSED` and every number is the one in the sentence.
7. Hosted site, unchanged frontend against the new backend (`validation/customize/hosted_check.py`): **22 of 22 PASS**
   (customized investigation `inv-647982a01b52029273428ace5a32f5cf`, `MODEL`).

No rollback was needed. Rollback, if ever required: `cloudshell_release.py rollback --code-key lambda/byb-backend-7c459ee17d81cff1.zip`,
then `status`, `execute`, `verify` and the smoke check (`scripts/deploy.md`, "Rollback").

## Not covered

- Only four interpreter sentences were tried on the live model; the unit suite (`backend/tests/service/test_service_interpreter_clauses.py`)
  covers the other wordings with a scripted model.
- The full Python and browser suites were not re-run for this one-file change; the targeted run on `bffec35` was 879 passed, 21 expected failures.
