# Release 2026-11-15 (evening): Evidence Investigator

Backend and frontend, deployed from `release/datathon-final-integration` at `8a3656f` (PR #25). Times are UTC
(2026-11-16).

## What was running before

The backend-only interpreter release of `main` `bffec35`, executed at 01:27: code key
`lambda/byb-backend-3a2220a805a80ce1.zip`, template `templates/template-8f99698805dfb0b8.yaml` (the template on
`main`). This release is that source plus the Evidence Investigator, so nothing of it is undone.

## Backend

| | |
|---|---|
| Code key | `lambda/byb-backend-3366f6357259c7ec.zip` (675 437 bytes) |
| Template key | `templates/template-8621e53b69811867.yaml` |
| Change set | `byb-8621e53b69811867-3366f6357259c7ec` (id ending `9e0751c0-27a3-4643-a406-da3e175f08f7`) |
| Executed | 01:41:30, `UPDATE_COMPLETE` 01:42:10 |
| `DataSnapshotId` | `snap-2026-11-12-2662b7a89c03` (unchanged, no data uploaded) |
| `AllowedOrigin` | `https://main.dwtdk87nismj6.amplifyapp.com` (unchanged) |

Artifacts were uploaded through presigned URLs and the change set was created, reviewed, then executed with the
guards of `scripts/cloudshell_release.py execute` (no removal, no replacement, planned code key, snapshot and origin).

Resources changed, from the stack events: the three functions (new code), `HttpApi` (body gains
`POST /evidence/investigate`), and one added `AWS::Lambda::Permission`
(`ApiFunctionInvestigateEvidencePermission`: API Gateway may invoke the existing API function for the new route).
No IAM role or policy was changed. The summary view of the change set listed `ApiFunctionRole` and the authorizer
permission as possibly affected; the property-level view listed neither, and neither appears in the stack events.

Template difference from `main`: the 10 lines of the `InvestigateEvidence` event.

## Frontend

Amplify app `dwtdk87nismj6`, branch `main`, job 5, `SUCCEED` at 01:44:44. `frontend.zip` sha256
`0ea1e769e82329a41e791847160ef0dddc8d2024d5a16d70201ecdd381ca6397`, 42 files, built with
`NEXT_PUBLIC_API_BASE_URL=https://3t4hod912l.execute-api.us-east-1.amazonaws.com`. The zip was built from the working
tree just before commit `8a3656f` was made, from the same sources. Published only after the backend checks below passed.

## Checks on the deployed release

Backend, on code key `3366f635…` and the snapshot above:

- `scripts/cloudshell_smoke.py`: PASS, 23 checks, investigation in MODEL mode.
- `scripts/cloudshell_customize_check.py`: PASS.
- `scripts/cloudshell_interpreter_check.py` (from `release/records-2026-11-15-interpreter`): PASS, 4 cases, real model,
  one attempt each.

Hosted site:

- `validation/release_final/hosted_check.py`: PASS, 21 of 21.
- `validation/customize/hosted_check.py`: PASS, 22 checks.

What `release_final/hosted_check.py` observed (deployed data, not fixtures):

- "Keep any single company below 10%." gives one `max_issuer_exposure` 0.10 rule, status PROPOSED, quote "10%".
- "At most 5% in any company. At least 10% in Exxon Mobil." gives no drafted rule and one question.
- `POST /evidence/investigate` answers 401 without the access code and 400 for client-supplied figures.
- The header link "Evidence Investigator" is visible at desktop width and at 390 px and opens `/evidence/`; the page
  calls `https://3t4hod912l.execute-api.us-east-1.amazonaws.com`.
- SPY: verified 99.871325%, unresolved 0.128675%; sector classification missing for 503 of 503 holdings.
- ESGV: no holdings file in the deployed snapshot; verified share reported as unknown, evidence unavailable.
- Company limit (Robert, suggested 10% rule, PROPOSED and labelled as not confirmed): verified 5.958%, conditional
  maximum 6.006735%, within the limit under every scenario.
- No answer carried model-written text.

## Rollback

Backend: `python3 cloudshell_release.py rollback --code-key lambda/byb-backend-3a2220a805a80ce1.zip` puts the code
back with the template the stack has (the route stays declared in API Gateway, but that older code does not serve
it; not tried); to remove the route as well, create a change set from `templates/template-8f99698805dfb0b8.yaml` with that code key. Frontend:
republish the previous `frontend.zip` (job 4, built from `main` `fc4841a`).
