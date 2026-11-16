# Deploying the backend through the AWS MCP tool

> **Milestone 5 (branch `agent/a2-backend`): nothing in this state has been deployed.** The stack in the account
> still runs the phase-1 template and zip named below. Sections 1 to 5 keep the record of what was run on
> 2026-11-14 and say what changes for the next deploy: a new zip (engine and contracts included by default), a
> data snapshot uploaded first (section 3b), two parameters to pass (`DataSnapshotId`, `AllowedOrigin`), and a
> CORS guard in `02_deploy.py`. Read "Next deploy: checklist" at the end before starting.
>
> **Update 2026-11-15.** A full release was deployed that day with the CloudShell helper, not with the MCP sequence
> below: see `infra/evidence/release-2026-11-15.md`. The procedure for the next release is the last section of this
> file, "Customize this profile (2026-11-15)". Sections 1 to 8 are kept as the record of the first deployment.

This is the sequence that was actually used on 2026-11-14 to create and then
update stack `before-you-buy` in account `010928212265`, region `us-east-1`.
It needs no AWS CLI, no SAM CLI and no local AWS credentials: every AWS call
goes through the AWS MCP server (`run_script`, which exposes `call_boto3`, and
`get_presigned_url`). The alternative `sam deploy` path is described in
`infra/README.md`; it was not executed.

There is no `.env` file anywhere. Configuration is: stack parameters (defaults
in `infra/template.yaml`), Lambda environment variables set by the template,
and one SSM SecureString created out-of-band. The frontend needs only the API
base URL (stack output `ApiBaseUrl`) and the access code typed at runtime.

## Files

| File | What it is |
| --- | --- |
| `scripts/package.py` | Local, standard library only. Builds the deterministic zip `dist/byb-backend-<sha16>.zip`. |
| `scripts/build_snapshot.py` | Local, standard library only, no AWS. Validates the processed data and the scenarios and writes `dist/snapshots/<snapshot_id>/`. Prints the id and the upload list. |
| `scripts/mcp/01_bootstrap.py` | Sandbox snippet. Artifacts bucket + access-code parameter. Idempotent. |
| `scripts/mcp/02_deploy.py` | Sandbox snippet. Change set: create, show validation and changes, optionally execute. |
| `scripts/mcp/03_status.py` | Sandbox snippet. Wait, then print status, outputs and failed events. |
| `scripts/e2e_smoke.sh` | Local, `curl` + `jq`. End-to-end check of the deployed API. |
| `scripts/e2e_probe.sh` | Local, `curl` + `jq`. Injected-instruction probes, a burst of real investigations, a throttle flood. Starts 12 real investigations per run. Wait a minute before running the smoke test after it: the flood leaves the route throttled. |

A "sandbox snippet" is not a local program: paste the file's content as the
`code` argument of `run_script`. Every snippet starts with
`sts:GetCallerIdentity` and stops if the account is not `010928212265`.

## 1. Build

    python3 scripts/package.py
    shasum -a 256 infra/template.yaml | cut -c1-16

The first command prints `s3_key` (`lambda/byb-backend-<sha16>.zip`). The
second gives the template key `templates/template-<sha16>.yaml`. Both keys are
content-addressed: the same sources always give the same key, and a changed
key is what makes CloudFormation redeploy the functions.

Used on 2026-11-14: `lambda/byb-backend-5cf91f80c5c1a2ce.zip` (96,694 bytes,
19 files) with `templates/template-e532ad55e3d0fd57.yaml` (23,609 bytes), then
with `templates/template-9b1c94d4e07d8bc3.yaml` (24,229 bytes, current).

Milestone 5: `python3 scripts/package.py` with no option builds the complete zip: `backend/` (handlers, engine,
agents, common), `byb_contracts/` (from `contracts/python/byb_contracts`) and `byb_contracts/schemas/` (from
`contracts/schemas`; the functions find it through `BYB_SCHEMA_DIR=/var/task/byb_contracts/schemas`). No data,
fixture, scenario or test file is in it, and the build fails if one would be (tests `pk05` to `pk07`). `--with-engine`
is no longer needed.

## 2. Bootstrap (once)

Run `scripts/mcp/01_bootstrap.py`. It creates, or leaves alone if they exist:

- bucket `byb-artifacts-010928212265-us-east-1`: all four Block Public Access
  flags, SSE-S3, TLS-only bucket policy, 7-day expiry (`transfer/`: 1 day);
- SSM SecureString `/before-you-buy/access-code` (48 random hexadecimal
  characters generated inside the sandbox, `Overwrite=False`). The value is
  never returned, printed or logged. Report the parameter name, never the value.

## 3. Upload the zip and the template

The sandbox cannot read local files and mangles binary bodies, so uploads go
through presigned URLs. Call `get_presigned_url` with two requests
(`operation: upload`, the artifacts bucket, the two keys from step 1), then:

    curl -sS -o /dev/null -w 'http=%{http_code}\n' --upload-file dist/byb-backend-<sha16>.zip '<presigned PUT URL>'
    curl -sS -o /dev/null -w 'http=%{http_code}\n' --upload-file infra/template.yaml '<presigned PUT URL>'

Both must print `http=200`. A presigned URL embeds a short-lived session
token: never write one into a file in this repository or into a report.

## 3b. Data snapshot (milestone 5; not run yet)

The Lambdas read holdings, prices, the instrument registry, the controversy and source registries and the three
fictional scenarios from the data bucket, never from the zip (issuer holdings and Yahoo-derived prices are not
redistributable through Git). Both functions refuse to serve anything from a snapshot that fails its checks.

1. Build and check locally (no AWS call):

       python3 scripts/build_snapshot.py --check     # validate only, print the id
       python3 scripts/build_snapshot.py             # write dist/snapshots/<snapshot_id>/

   The id is `snap-<valuation date>-<12 hex>` and is derived from the SHA-256 of every file: other data, other id.
   For the data of 2026-11-14 the script printed `snap-2026-11-12-3390e023b308` (9 files, 1,427,264 bytes).
2. Upload every file of the printed `uploads` list to the **data** bucket (stack output `DataBucketName`) under
   exactly the printed key, `snapshots/<snapshot_id>/<name>`: one `get_presigned_url` request per file
   (`operation: upload`), then `curl --upload-file` as in section 3. Upload `manifest.json` last. Neither function
   role can write under `snapshots/`: only the deploying identity can.
3. Check in the sandbox that the nine keys exist (`ListObjectsV2`, prefix `snapshots/<snapshot_id>/`) and that the
   sizes equal the printed `bytes`.
4. Pass `{"DataSnapshotId": "<snapshot_id>"}` in `PARAMETER_OVERRIDES` (section 4). The parameter has no default.

A snapshot is never modified in place. New data is a new id, a new prefix and a parameter change; the previous
snapshot stays, and every investigation records the id it used (job `internal`, result `inputs`, trace, logs).

The first deploy of the milestone-5 template is special: the data bucket is created by the stack, and the stack
needs `DataSnapshotId`. The bucket already exists in the deployed stack, so for an update, upload first and deploy
second. For a brand-new stack, deploy with the id printed by the build, upload immediately after: until the upload
is complete every data route answers 500 and every investigation ends `FAILED / DATA_UNAVAILABLE`, nothing else.

## 4. Create the change set, read it, execute it

In `scripts/mcp/02_deploy.py` set `CODE_KEY` and `TEMPLATE_KEY`, keep
`EXECUTE = False` and run it. It:

1. checks that both objects exist (`HeadObject`);
2. picks `CREATE` or `UPDATE`; on an update every parameter that is not
   overridden keeps its previous value (`UsePreviousValue`);
3. calls `CreateChangeSet` with `TemplateURL`, `CAPABILITY_IAM` and
   `CAPABILITY_AUTO_EXPAND` (the `AWS::Serverless` transform runs server-side);
4. waits for the change set and prints the planned changes;
5. prints the pre-deployment validation results (`DescribeEvents` on the
   change set id: they are not visible anywhere else).

Read the output. Then set `EXECUTE = True` and run it again: it re-uses the
same change set, refuses to execute if any validation failed, calls
`ExecuteChangeSet` and waits up to 100 seconds. Set `EXECUTE` back to `False`
afterwards (the file is committed in that state).

Parameters other than the code location go in `PARAMETER_OVERRIDES`, for
example `{"DataSnapshotId": "snap-2026-11-12-3390e023b308", "AllowedOrigin": "https://main.<app-id>.amplifyapp.com"}`.
A parameter with no default and no previous value (`DataSnapshotId`, `AllowedOrigin`) stops the snippet before any
change set is created.

**CORS origin.** `AllowedOrigin` has no default in the template (validator finding F-08): a new stack cannot be
created without stating it, and the template only accepts an exact origin or a literal `*`. The stack deployed from
the older template still has `*`, which an update would keep as the previous value. A deployment that serves a hosted frontend must pass the exact origin, scheme included and
without a trailing slash. `02_deploy.py` computes the value the stack would have after the change set (override,
else the stack's current value) and reports it as `allowed_origin`. If it is `*`, or not
an `https://` origin (`http://localhost...` is accepted), the report carries `cors_refusal` and, with
`EXECUTE = True`, the change set is **not executed** (`"refused"` in the report). The only way through is
`ALLOW_WILDCARD_ORIGIN = True`, set on purpose and set back afterwards. Nothing about the running stack changes
until someone makes that choice: the guard only stops the next execution. CORS is not access control (the bearer
code is); the point is that no arbitrary website can drive the API from a browser in which the code was typed.

What happened on 2026-11-14:

| Step | Change set | Result |
| --- | --- | --- |
| create | `byb-e532ad55e3d0fd57-0f6cd5afdd57c8b3` | 18 resources added, `CREATE_COMPLETE` in about 70 s |
| update (new zip) | `byb-e532ad55e3d0fd57-5cf91f80c5c1a2ce` | 6 modifications (three functions and their dependants), `UPDATE_COMPLETE` |
| update (reserved concurrency) | `byb-9b1c94d4e07d8bc3-5cf91f80c5c1a2ce` | 5 modifications listed, 2 applied (`WorkerFunction`, its event invoke config), `UPDATE_COMPLETE` at 23:49Z |

All three change sets reached `CREATE_COMPLETE` / `AVAILABLE` with two operation
events and no validation event (nothing failed).

## 5. Status and outputs

Run `scripts/mcp/03_status.py`. It prints the stack status, the outputs and,
after a failure, the failing events with root causes first. If the first
creation fails the stack ends in `ROLLBACK_COMPLETE` and must be deleted
(`DeleteStack`) before the next attempt; a failed update rolls back by itself.

## 6. End-to-end check

`scripts/e2e_smoke.sh API_BASE_URL ACCESS_CODE_FILE` needs the access code in a
local file. The procedure used keeps the value out of the conversation, the
repository and the shell history:

1. Sandbox: read the parameter with `WithDecryption=True` and `PutObject` its
   value to `transfer/<random>.txt` in the artifacts bucket. Return only the key.
2. `get_presigned_url` (`operation: download`, `expires_in: 90`).
3. Locally, outside the repository:

       umask 077 && mkdir -p /tmp/byb-e2e && chmod 700 /tmp/byb-e2e
       curl -sS -o /tmp/byb-e2e/code '<presigned GET URL>' && chmod 600 /tmp/byb-e2e/code

4. Sandbox: `DeleteObject` on the transfer key; list `transfer/` to confirm it is empty.
5. Run the check and keep its output:

       scripts/e2e_smoke.sh https://<api-id>.execute-api.us-east-1.amazonaws.com /tmp/byb-e2e/code

   The script reads the code from the file, sends it through a header file
   (`curl -H @file`) and prints neither the code nor any `Authorization`
   header. It exits non-zero if any check fails.
6. Delete `/tmp/byb-e2e/code`.

The checks: 401 without a token (POST and GET), 403 with a wrong token, CORS
preflight answered without a token, 400 on an invalid body, 404 on an unknown
id, 202 on create, the same id on a duplicate POST, 409 when the key is reused
with another body, polling until the job is terminal, the final job document.

A person who has the code (for example the lead, to type it into the
frontend) can read it once in the AWS console: Systems Manager, Parameter
Store, `/before-you-buy/access-code`, "Show decrypted value".

## 7. Rotating the access code

How long a rotated code keeps working, by template:

| Template | API Gateway authorizer cache (`ReauthorizeEvery`) | Function cache (`ACCESS_CODE_CACHE_SECONDS`) | Worst case |
| --- | --- | --- | --- |
| deployed now (phase 1) | 300 seconds | 60 seconds | about 6 minutes (360 seconds) |
| milestone 5 (this branch, not deployed) | 0: nothing cached | 30 seconds | 30 seconds |

With `ReauthorizeEvery` 0 every request invokes the authorizer function (the throttle is 5 requests per second on
the costly routes, so the cost is negligible), and the only delay left is the function's own in-memory copy of the
code, kept 30 seconds per warm container to avoid one SSM call per request. The function refuses a cache setting
above 300 seconds.

Procedure (sandbox for the AWS calls; nothing is redeployed):

1. `PutParameter` with `Overwrite=True` on `/before-you-buy/access-code`, the value generated inside the sandbox
   as the bootstrap does (48 random hexadecimal characters). Never return or print the value.
2. Wait 45 seconds on the milestone-5 template (30 seconds of cache plus a margin). On the phase-1 template still
   deployed, wait 6 minutes and 30 seconds.
3. Verify with the OLD code: `curl -s -o /dev/null -w '%{http_code}\n' -H @old-header-file <ApiBaseUrl>/portfolios/robert`
   must print `403` (a wrong code is 403; `401` is the answer when no `Authorization` header is sent at all). If it
   still prints `200`, the wait was too short or the parameter was not overwritten: do not consider the code rotated.
4. Verify with the NEW code: the same request must print `200`.
5. Delete both header files.

During the wait the old code can still be accepted and the new one refused, per warm container. Rotation does not
end investigations already running; they need no code.

## 8. Teardown

1. `DeleteStack` on `before-you-buy`. The data bucket is retained on purpose.
2. Empty and delete the data bucket (stack output `DataBucketName`).
3. Empty and delete `byb-artifacts-010928212265-us-east-1`.
4. `DeleteParameter` on `/before-you-buy/access-code`.

The whole account is deleted after 2026-11-16, which removes all of it anyway.

## Next deploy: checklist (milestone 5, to be run by the lead; none of it has been run)

1. `uv run --no-project --python 3.14 --with pytest --with boto3 --with jsonschema pytest backend/tests contracts/python/tests -q` passes.
2. `python3 scripts/package.py` -> zip key; `shasum -a 256 infra/template.yaml | cut -c1-16` -> template key.
3. `python3 scripts/build_snapshot.py` -> snapshot id and upload list; upload the snapshot to the data bucket (3b).
4. Upload the zip and the template to the artifacts bucket (3).
5. `02_deploy.py`: `CODE_KEY`, `TEMPLATE_KEY`, `PARAMETER_OVERRIDES = {"DataSnapshotId": ..., "AllowedOrigin": ...}`,
   `EXECUTE = False`. Read the change set. Expected: the three functions, both function roles (new statements on
   `policies/*` and `snapshots/*`), five new routes with their integrations and permissions, the authorizer
   (`ReauthorizeEvery` 0), the API (CORS origin). No replacement of the bucket, the API or a function.
6. `EXECUTE = True`, run, set it back. `03_status.py`.
7. `scripts/e2e_smoke.sh` (section 6). It exercises the seven routes with the milestone-5 shapes.
8. Rotation check if the code is rotated (section 7).

`scripts/e2e_probe.sh` still sends the phase-1 request shapes and will fail against the milestone-5 API; it was
not updated (it starts 12 real investigations per run and cannot be tried without AWS).


## Customize this profile (2026-11-15)

Written for the owner. **Status: this release was carried out on 2026-11-15** (backend `UPDATE_COMPLETE` 19:35 EST,
Amplify job `3` `SUCCEED` 19:44 EST); the evidence, with the exact artifacts and the audit of their source, is in
`infra/evidence/release-2026-11-15-customize.md`. The text below is the procedure as it was written before the
release: where it says "now deployed" or "not uploaded", read it as the state before 19:34 EST. It replaces the
stack's code and its data snapshot and republishes the site. The bundle was built from an uncommitted working tree
on top of `origin/main` 1f582bf, so it is identified by its hashes below, not by a commit.

### What changes

- **Code** (`CodeS3Key`): "Customize this profile" (`custom_portfolio` on `POST /check` and `POST /investigations`,
  the job's stored `portfolio`), the review fixes that followed, and origin's PR #17 (interpreter as a bounded
  agent, prompt `interpreter-3`) and PR #18 (audit fixes). Investigator prompt version `investigator-5`.
- **Data snapshot** (`DataSnapshotId`): `snap-2026-11-12-c2289f2b406d` (deployed today, built from an XIU.TO file
  dated 2026-11-13, one day after the valuation date) is replaced by `snap-2026-11-12-2662b7a89c03`, built from
  the original file as of 2026-11-12. Same instruments. Figures move slightly: Robert's NVIDIA upper bound
  26.2803% becomes 26.2763%.
- **Frontend**: the editor, the Amira persona, the review fixes.
- **Not changed**: `infra/template.yaml` (byte-identical to the deployed one), IAM, routes, CORS, the model id,
  the access code. No resource is added, removed or replaced, apart from the authorizer invocation permission
  that SAM may recreate (already reviewed for the previous release).

Stored objects need no migration: a job stored by the previous build has no `portfolio`; it is served as is and,
if queued, runs against the scenario portfolio as before.

### Artifacts (built locally on 2026-11-15, bundle zipped at 19:28 EST, not uploaded; `dist/` is git-ignored: do not commit the bundle)

| Artifact | SHA-256 |
| --- | --- |
| `dist/byb-backend-7c459ee17d81cff1.zip` (code key `lambda/byb-backend-7c459ee17d81cff1.zip`) | `7c459ee17d81cff1822b8a25f7b16750b4e729c4c11a3fd97959e7557475525c` |
| `frontend.zip` in the bundle (live build against the existing API URL) | `393138fe726707d29d4dd677b5e668bbcac19f3d4b0ba09fc462d3cd74c1184c` |
| `frontend.zip` republished at 20:01 EST from `main` fc4841a (PR #20's palette with contrast fixes; frontend only, backend untouched) | `d8c5daa96305a08c1c2f677e20ca602dc428c02ea4fa6f7d6e67e8077c8b7ea3` |
| `dist/cloudshell-release-customize.zip` | `b2b0a76701b9613a89fc5ebf632a7724037cc39a081f93d7416285384747b1d4` |

The bundle holds exactly: the backend zip, `frontend.zip`, `template.yaml`, `snapshots/snap-2026-11-12-2662b7a89c03/`,
`cloudshell_release.py`, `cloudshell_smoke.py`, `cloudshell_customize_check.py`, `live_check.py`, `mateo_invariants.py`.

Values to recognise during the release:

| | Now deployed | After this release |
| --- | --- | --- |
| `CodeS3Key` | `lambda/byb-backend-bd73f44e273534f8.zip` | `lambda/byb-backend-7c459ee17d81cff1.zip` |
| `DataSnapshotId` | `snap-2026-11-12-c2289f2b406d` | `snap-2026-11-12-2662b7a89c03` |
| Frontend | `frontend.zip` of `dist/cloudshell-release.zip` | `frontend.zip` of this bundle |

### Procedure (CloudShell; backend first, the site last)

Upload `dist/cloudshell-release-customize.zip`, extract it into a **fresh** directory, `cd cloudshell-release`.

1. `python3 cloudshell_release.py prepare`
   Uploads the snapshot and the code zip, creates a change set, executes nothing. It refuses a directory holding
   more than one snapshot or backend zip.
2. `python3 cloudshell_release.py status`
   Review before going on: `change_set_parameters` shows the new `CodeS3Key` and `DataSnapshotId` from the table
   above, `change_set_differs_from_plan` is `{}`, and `changes` lists only the three functions being modified (and
   possibly the authorizer invocation permission with a conditional replacement). No removal, no IAM change.
3. `python3 cloudshell_release.py execute --change-set-id '<the reviewed ARN>'`
   Refuses a change set that removes or replaces a resource, or whose code key, snapshot or origin are not the
   planned ones. Then repeat `status` until `UPDATE_COMPLETE`.
4. `python3 cloudshell_release.py verify`
   Exit 0 only if the stack runs exactly the planned code key and data snapshot.
5. `python3 cloudshell_smoke.py`
   The existing Mateo flow with the real interpreter and a real investigation in `MODEL` mode. Must print `PASS`.
6. `python3 cloudshell_customize_check.py`
   API-level check of this release: Amira is served; no fund holdings are dated after the valuation date and
   Robert's NVIDIA upper bound is 0.262763304 (the corrected snapshot); a customized portfolio is checked and
   investigated as sent; weights totalling 90% are refused. Must print `PASS`. It reads the access code from SSM
   in memory and never prints it.
7. `python3 cloudshell_release.py host`
   Publishes the site. It refuses unless the stack runs the planned backend **and** steps 5 and 6 both recorded a
   pass on exactly that code key and snapshot (`backend-checks.json`). Wait for the Amplify job to succeed.
8. On the hosted site, without `fixtures=1`: select Amira (her portfolio loads); select Robert, customize, apply,
   confirm the rules, run an investigation; the report shows "Customized fictional portfolio" with the edited
   weights. Only then may the site be described as including this feature.
9. Record the release in `infra/evidence/`: the change-set id, the stack parameters printed by `verify`, the
   Amplify job id and the output of steps 5 and 6.

If step 5 or 6 fails, do not run step 7: the previous site keeps working against the new backend (it never sends
`custom_portfolio` and ignores the job's extra `portfolio` member). Decide between fixing forward and rolling the
backend back (below).

### Rollback

Targets: code `lambda/byb-backend-bd73f44e273534f8.zip`; frontend `frontend.zip` of `dist/cloudshell-release.zip`
(SHA-256 of that bundle `1befff72429af6c8afc5ed7eb236075fccc9bd2f7c3df7dd9cc72caac631e5c9`).
Data snapshot: **keep `snap-2026-11-12-2662b7a89c03`**. The previous code was run locally on it (it loads, validates
and gives the Nov 12 figures); going back to `c2289f2b406d` would restore the look-ahead file and is not advised.

- **The site first, if it was already published (step 7 ran).** Before running `rollback`, while the release plan is
  still the current one: replace `frontend.zip` in the directory with the previous one and run
  `python3 cloudshell_release.py host`; wait for the Amplify job. The previous site works with either backend. (In
  the other order the new site would sit in front of the old backend, where `custom_portfolio` is refused with 400.)
- **The backend.**
  1. `python3 cloudshell_release.py rollback --code-key lambda/byb-backend-bd73f44e273534f8.zip`
     Creates a change set with the template the stack already has, the previous code key and the snapshot in use.
     It uploads nothing and executes nothing. Add `--snapshot-id snap-2026-11-12-c2289f2b406d` only on an explicit
     decision to restore the earlier data as well.
  2. `python3 cloudshell_release.py status`, review, then `execute --change-set-id '<ARN>'`, then `status` until
     `UPDATE_COMPLETE`, then `verify`.
  3. `python3 cloudshell_smoke.py` (must pass on the rolled-back backend).
- If the stack itself ended in `UPDATE_ROLLBACK_COMPLETE`, CloudFormation already put the previous code and
  snapshot back: run `status` to confirm the `running` values, and `prepare` again when ready. `host` refuses until
  the stack is `UPDATE_COMPLETE`.
- Do not re-run the old bundle's own helper for a rollback: it refuses the authorizer-permission replacement and
  its change-set name was already executed. The helper in this bundle handles both.

Jobs created while the new backend ran keep their extra `portfolio` member in S3; the previous code ignores it
(and would run such a queued job against the scenario portfolio).

### Local validation behind this bundle

See `/tmp/datathon-coordination/main-status.md` of 2026-11-15 for the full list. In short: Python suites
(contracts, backend, validation, acceptance/mateo), frontend unit tests, typecheck and lint, the browser journeys
of `validation/customize/run_browser.sh` against the real handlers on loopback, the data quality checks
(74 passed, 0 failed) and `cloudshell_customize_check.py` against the same handlers. Not exercised: real AWS,
real Bedrock, the hosted site.
