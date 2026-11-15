# Deployment runbook

For the coordinator. It takes the release candidate from a local checkout to a
deployed backend and a hosted frontend in the workshop AWS account, in the
order that the template forces.

**Candidate described:** local branch `integration/rc` at `deec650`, plus fixes in progress.

**Nothing in this runbook has been executed for this candidate.** It was
written without AWS access. The backend steps use the procedure of
`scripts/deploy.md`, whose phase-1 form was executed and recorded on
2026-11-14 and 2026-11-15 UTC (`infra/evidence/milestone2.md`); its
milestone-5 additions (snapshot upload, two parameters, CORS guard) have never
run against AWS. The Amplify steps have never run at all. Marks used below:

- **[local]** run on one machine for this document or by the coordinator;
- **[phase 1]** executed against AWS for the earlier slice only;
- **[docs]** read in the AWS documentation on 2026-11-14, not executed;
- **[unverified]** not executed and not confirmed anywhere.

Section 9 lists every value the coordinator supplies; section 10 collects
everything unverified.

## Why this order

`infra/template.yaml` gives `AllowedOrigin` no default and accepts only an
exact origin or a literal `*`, and `scripts/mcp/02_deploy.py` refuses to
execute a change set whose resulting origin is `*`. So the backend cannot be
deployed before the site's origin is known. The site in turn inlines the API
base URL at build time (`NEXT_PUBLIC_API_BASE_URL`).

Both values can be known before either side is deployed:

- **API base URL.** The stack already exists. The template keeps the logical
  id `HttpApi` and its type (`AWS::Serverless::HttpApi`), so an update should
  modify the API in place and the stack output `ApiBaseUrl` should stay what
  it is today (`infra/README.md` records the phase-1 URL). **[unverified]**
  until the change set of section 3 shows no `Replacement` for `HttpApi`. If
  it shows a replacement, stop: the URL would change.
- **Site origin.** An Amplify app and a branch can be created without
  deploying anything. The default domain is then
  `https://<branch>.<appId>.amplifyapp.com` **[docs]**.

Order: (1) create the Amplify app and branch, note the origin; (2) build and
upload the data snapshot; (3) deploy the backend with `AllowedOrigin` set to
that origin; (4) check the backend; (5) build the site once with the API base
URL and deploy it; (6) check the hosted site. The site is built once.

## 0. Prerequisites and authorizations

| Needed | Check | State |
| --- | --- | --- |
| Authorization from the account owner to mutate the stack `before-you-buy`, write to the two buckets, and create an Amplify app | Ask; record the answer | Not given to this document's author |
| The AWS MCP tool (`run_script`, `get_presigned_url`) pointed at the workshop account, region `us-east-1` | `scripts/mcp/03_status.py`: it stops if the account is not the expected one | **[phase 1]** |
| The stack exists in `UPDATE_COMPLETE` and still holds the phase-1 template with `AllowedOrigin` `*` | `03_status.py`; last recorded read 2026-11-15 00:23 UTC (`infra/evidence/milestone2.md` section 1) | **[unverified]** today |
| Permission to create an Amplify app in this account | `docs/PLAN.md` P4 records one successful `amplify:ListApps` only | **[unverified]** |
| Bedrock access to the runtime model through the inference profile, for the worker and now for the API function (interpreter) | A successful `POST /rules/interpret` in section 4 | **[phase 1]** for the worker; **[unverified]** for the interpreter |
| A clean checkout of the commit to deploy, with the git-ignored processed data present | `git status --porcelain` is empty; `python3 scripts/build_snapshot.py --check` passes | **[local]**: the check passed on the 2026-11-14 data (`scripts/deploy.md` 3b) |
| Test suites pass on that commit | `uv run --no-project --python 3.14 --with pytest --with boto3 --with jsonschema pytest backend/tests contracts/python/tests -q` and the frontend commands of `README.md` section 6 | **[local]** on the candidate: 1685 passed, 9 skipped (run for this document) |
| Validation has no open blocker | `validation/REPORT.md` when the coordinator adds it; finding F-20 closed | Open on the candidate |
| Node.js 22.12 or later, `npm`, `curl`, `jq`, `zip`, `python3` | `node --version` | Local tools |
| The access code can reach the operator without being written anywhere | `scripts/deploy.md` section 6 (transfer file) or the Systems Manager console | **[phase 1]** |
| Time | The account is deleted at the end of 2026-11-16; the hour is unresolved (`docs/PLAN.md` P2) | Open |

Rules for the whole run: never paste the access code or a presigned URL into
a file of the repository, a report or a chat; keep the output of every check;
a check that was not run is reported as not run.

## 1. Create the Amplify app and branch (no deployment yet)

Through `run_script`, service `amplify`, region `us-east-1` **[docs]** for the
operation and parameter names, **[unverified]** in this account:

1. `CreateApp` with `name` (for example `before-you-buy`) and `platform`
   `WEB`. No repository, no access token. Read `app.appId` and
   `app.defaultDomain` in the response.
2. `CreateBranch` with `appId` and `branchName`. Use a short lowercase name
   without `/` (for example `main`), so the subdomain equals the name.
3. The origin is `https://<branchName>.<defaultDomain>`, that is
   `https://<branch>.<appId>.amplifyapp.com`: scheme included, no trailing
   slash, no path. Write it down as `SITE_ORIGIN`. It must match the
   template's pattern `https://[A-Za-z0-9.-]+`.

Nothing is served yet; what the domain answers before the first deployment was
not checked **[unverified]**.

Git-connected hosting is not used: `integration/rc` is not pushed, the account
lives two more days, and it would add a build image, a Node.js version and a
framework detection that have never run here. `amplify.yml` in the repository
root exists for that option only and has never been executed.

## 2. Data snapshot

Procedure: `scripts/deploy.md` section 3b. **[local]** for the build,
**[unverified]** for the upload.

1. `python3 scripts/build_snapshot.py --check`, then
   `python3 scripts/build_snapshot.py`. It writes
   `dist/snapshots/<snapshot_id>/` and prints the id and the upload list. For
   the data of 2026-11-14 the id was `snap-2026-11-12-3390e023b308` (9 files,
   1,427,264 bytes). Use the id the script prints on the day, not this one:
   other data gives another id.
2. Read the data bucket name from the stack output `DataBucketName`
   (`03_status.py`).
3. For each file of the list: one `get_presigned_url` request
   (`operation: upload`, the data bucket, key `snapshots/<snapshot_id>/<name>`),
   then `curl -sS -o /dev/null -w 'http=%{http_code}\n' --upload-file <file> '<url>'`.
   Each must print `http=200`. Upload `manifest.json` last.
4. In the sandbox, `ListObjectsV2` with prefix `snapshots/<snapshot_id>/`:
   nine keys, sizes equal to the printed `bytes`.
5. Write the id down as `SNAPSHOT_ID`. It is the `DataSnapshotId` parameter.

A snapshot is never modified in place. The bucket is retained by the template
and has no lifecycle rule on `snapshots/`.

## 3. Backend: package, change set, review, execute

Procedure: `scripts/deploy.md` sections 1, 3, 4, 5 and "Next deploy:
checklist". **[phase 1]** for the mechanics, **[unverified]** for this
template and zip.

1. Package and name the template:

       python3 scripts/package.py
       shasum -a 256 infra/template.yaml | cut -c1-16

   The first prints `s3_key` (`lambda/byb-backend-<sha16>.zip`); the second
   gives `templates/template-<sha16>.yaml`. On the candidate the template prefix
   is `0bfb606d3605a68a`; recompute it on the commit actually deployed.
2. Upload the zip and the template to the artifacts bucket through presigned
   URLs (`scripts/deploy.md` section 3). Both uploads print `http=200`.
3. Before editing `02_deploy.py`, note the stack's current `CodeArtifact`
   output and parameters (`03_status.py`). They are the rollback target
   (section 7).
4. In `scripts/mcp/02_deploy.py` set:

       CODE_KEY = "lambda/byb-backend-<sha16>.zip"
       TEMPLATE_KEY = "templates/template-<sha16>.yaml"
       PARAMETER_OVERRIDES = {"DataSnapshotId": "<SNAPSHOT_ID>", "AllowedOrigin": "<SITE_ORIGIN>"}
       ALLOW_WILDCARD_ORIGIN = False
       EXECUTE = False

   and run it. Both parameters are required: `DataSnapshotId` has no default
   and no previous value, and the previous `AllowedOrigin` is `*`, which the
   guard refuses.
5. Review the report before executing:

   | Field | Must be |
   | --- | --- |
   | `allowed_origin` | exactly `SITE_ORIGIN` |
   | `cors_refusal` | `null` |
   | `data_snapshot_id` | `SNAPSHOT_ID` |
   | validation results | none failed |
   | changes | the three functions, both function roles, five new routes with integrations and permissions, the authorizer, the API (CORS) |
   | `Replacement` | **not** `True` for `HttpApi`, `DataBucket` or any function |

6. Set `EXECUTE = True`, run again, set it back to `False`. Then
   `03_status.py`: `UPDATE_COMPLETE`; outputs `ApiBaseUrl` (unchanged),
   `CodeArtifact` (the new key), `DataSnapshotId`. Write `ApiBaseUrl` down as
   `API_BASE_URL`.

**Change-set name trap [unverified].** `02_deploy.py` names the change set
from the two key hashes only and re-uses an existing change set of that name.
If a change set was created with a wrong parameter (for example a mistyped
origin) and the keys are unchanged, a second run would find the first one
again. Call `DeleteChangeSet` on that name before re-running. How the snippet
behaves when the name belongs to a change set that was already executed
(relevant to rollback, section 7) was not tested.

The file `scripts/mcp/02_deploy.py` is committed with the phase-1 keys, an
empty `PARAMETER_OVERRIDES` and `EXECUTE = False`. Whether the edited keys are
committed afterwards is a coordinator decision; never commit `EXECUTE = True`
or `ALLOW_WILDCARD_ORIGIN = True`.

## 4. Post-deploy checks of the backend

None of these has run against this candidate. All use `curl` from a terminal,
so CORS does not block them. Set, in the shell only:

    API=<API_BASE_URL>
    ORIGIN=<SITE_ORIGIN>

Get the access code into a mode-600 file outside the repository with the
transfer procedure of `scripts/deploy.md` section 6, and delete the file at
the end.

| # | Check | Command | Expected |
| --- | --- | --- | --- |
| 4.1 | Smoke test, seven routes, one real Robert investigation | `scripts/e2e_smoke.sh "$API" /tmp/byb-e2e/code` | Exit status 0. One line may differ, see 4.4 |
| 4.2 | Robert figures | In the 4.1 output, or on the hosted site in section 6 | Statuses and figures of the real-data table in `docs/WORKFLOWS.md`; `calculation_version` starts with `byb-engine-`; the agent mode is noted (`MODEL` or `DETERMINISTIC_FALLBACK`) |
| 4.3 | Mateo, live against local engine | `read -rs BYB_ACCESS_CODE && export BYB_ACCESS_CODE`, then `python3 acceptance/mateo/live_check.py --base-url "$API" --compare-local`, then `unset BYB_ACCESS_CODE` | Exit status 0. It creates one policy and one investigation. Add `--require-interpreter` to make a 502 or 504 from the interpreter a failure; `--dry-run` sends nothing |
| 4.4 | Preflight returns the exact origin | block A below | `204`; `access-control-allow-origin` equal to `ORIGIN`; allowed headers `authorization`, `content-type`, `idempotency-key`; no `access-control-allow-credentials` |
| 4.5 | Preflight from another origin | block A with `ORIGIN=https://example.org` | No `access-control-allow-origin` header. The status code is **[unverified]** |
| 4.6 | No code: all seven routes refuse | block B | `401` seven times |
| 4.7 | Wrong code: all seven routes refuse | block B with the extra header | `403` seven times |
| 4.8 | Do gateway refusals carry CORS headers? | block C | Record the answer; either is acceptable, see below |
| 4.9 | Rotated code refused | `scripts/deploy.md` section 7 | Old code `403` and new code `200` after the 45 s wait of that procedure (30 s cache plus margin) |
| 4.10 | Logs hold no secret | CloudWatch log groups named in the stack outputs | No access code, no `Authorization` header, no request body (`validation/ACCEPTANCE.md` L6) |

Block A:

    curl -sS -D - -o /dev/null -X OPTIONS "$API/investigations" \
      -H "Origin: $ORIGIN" -H 'Access-Control-Request-Method: POST' \
      -H 'Access-Control-Request-Headers: authorization,content-type,idempotency-key'

Block B (for 4.7 add `-H 'Authorization: Bearer not-the-access-code'` to the
`curl` line):

    ID=inv-00000000000000000000000000000000
    while read -r METHOD ROUTE; do
      if [ "$METHOD" = POST ]; then set -- -H 'content-type: application/json' -d '{}'; else set --; fi
      printf '%s %s ' "$METHOD" "$ROUTE"
      curl -sS -o /dev/null -w '%{http_code}\n' -X "$METHOD" "$API$ROUTE" "$@"
    done <<EOF
    GET /portfolios/robert
    POST /rules/interpret
    POST /rules/confirm
    POST /check
    POST /investigations
    GET /investigations/$ID
    POST /investigations/$ID/challenge
    EOF

Block C:

    curl -sS -D - -o /dev/null "$API/portfolios/robert" -H "Origin: $ORIGIN" | grep -i '^HTTP\|access-control'
    curl -sS -D - -o /dev/null "$API/portfolios/robert" -H "Origin: $ORIGIN" \
      -H 'Authorization: Bearer not-the-access-code' | grep -i '^HTTP\|access-control'

Notes:

- **4.1 and 4.4.** `scripts/e2e_smoke.sh` sends its own preflight with
  `Origin: https://example.org` and expects `204`. With an exact origin
  configured, that line may print no CORS headers, or fail, without anything
  being wrong **[unverified]**. Judge CORS by 4.4 and 4.5.
- **4.8.** If API Gateway omits CORS headers on the authorizer's `401` and
  `403`, a browser cannot read the status, and the access gate shows "The code
  could not be checked" for a wrong code instead of a wrong-code message
  (`acceptance/fullstack/README.md`). That is a wording defect, not an access
  defect: nothing is displayed either way. Record which case holds and tell
  the presenter.
- **4.9** changes the code. Do it only if a rotation is wanted, before the
  code is given to the presenter. The frontend then needs the new code typed
  again.
- **4.3 interpreter.** The first successful `POST /rules/interpret` is also
  the first live call of the interpreter prompt and of the API function's
  Bedrock permission. If it fails, the rest of the service still works; the
  demo uses the interpreter fallback of `docs/DEMO_SCRIPT.md`.
- `scripts/e2e_probe.sh` still sends phase-1 shapes and will fail; do not run
  it (`scripts/deploy.md`).
- Throttling (`validation/ACCEPTANCE.md` L2) and the bucket checks (L3) are
  optional here; L2 leaves the route throttled for about a minute.

## 5. Frontend: build, deploy, headers

### 5.1 Build **[local]**

    cd frontend
    npm ci
    NEXT_PUBLIC_API_BASE_URL=<API_BASE_URL> npm run build

`NEXT_PUBLIC_API_BASE_URL` is the only build variable. It is public (it is
inlined in the JavaScript) and is not a secret. Without it, or with an invalid
value, the site runs in fixtures mode (`frontend/src/lib/config.ts`). The
output is `frontend/out` (`output: "export"`, `trailingSlash: true` in
`frontend/next.config.ts`).

Check the build before uploading:

    grep -rl "execute-api" frontend/out/_next/static | head -1     # the API URL was inlined
    grep -rEow "[0-9a-f]{48}" frontend/out | head                  # expect nothing; explain any hit
    (cd frontend && npm start)                                     # serves out/ on 127.0.0.1:4173

Served locally, the page loads but its API calls are blocked by CORS, because
the API now allows only `SITE_ORIGIN`. That is expected. The local check is
limited to: the access screen appears and the label "Test data — fixtures" is
absent.

Zip the **contents** of `out/`, named with the commit (`dist/` and `*.zip`
are git-ignored). Keep every deployed zip until the recording is saved.

    (cd frontend/out && zip -qr "../../dist/byb-frontend-$(git rev-parse --short HEAD).zip" .)

### 5.2 Manual deployment **[docs]**, never executed

1. `CreateDeployment` with `appId` and `branchName`. The response carries a
   `jobId` and an upload URL for the zip (field name `zipUploadUrl`
   **[unverified]**, from memory). The URL is presigned: do not record it.
2. `curl -sS -o /dev/null -w 'http=%{http_code}\n' --upload-file dist/byb-frontend-<sha>.zip '<upload url>'`
   must print `http=200`. If the upload is refused for a missing content type,
   add `-H 'Content-Type: application/zip'` **[unverified]**.
3. `StartDeployment` with `appId`, `branchName` and that `jobId`, within eight
   hours of step 1.
4. `GetJob` with `appId`, `branchName`, `jobId` until the status is `SUCCEED`.
   Write the job id down.

The Amplify console does the same under "Deploy without Git" (drag the zip).

### 5.3 Custom headers **[docs]** for the mechanism, **[unverified]** for the policy

For a manual deployment Amplify does not need a `customHttp.yml` in the
repository, so none was added. The headers are set on the app: `UpdateApp`
with `appId` and `customHeaders` (the YAML below as one string), or in the
console under Hosting, Custom headers. Then deploy the same zip again (5.2):
the documentation says a redeploy applies them.

Start with the policy in report-only mode. Replace `<api-origin>` with
`API_BASE_URL` (scheme and host only):

```yaml
customHeaders:
  - pattern: '**/*'
    headers:
      - key: 'Content-Security-Policy-Report-Only'
        value: "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self' <api-origin>; frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'"
      - key: 'X-Content-Type-Options'
        value: 'nosniff'
      - key: 'Referrer-Policy'
        value: 'no-referrer'
      - key: 'X-Frame-Options'
        value: 'DENY'
      - key: 'Strict-Transport-Security'
        value: 'max-age=31536000'
```

Why it looks like this:

- A Next.js static export contains inline `<script>` elements, and a static
  host cannot issue a nonce, so `script-src` needs `'unsafe-inline'` (or one
  hash per inline script, recomputed at each build). With it, the policy does
  not stop an injected inline script; `connect-src` still limits where a
  script can send data to the site and the API.
- Components set `style` attributes, so `style-src` needs `'unsafe-inline'`.
- No third-party origin was found in `frontend/src`.
- The 3D exposure explorer (three.js, WebGL) may need `worker-src 'self' blob:`
  or `blob:` in `img-src`. **This policy has not been tested against a
  build.**

Procedure: with the report-only header deployed, run the whole Robert workflow
and the Mateo workflow with the browser console open, including the purchase
and verdict stages where the explorer loads. Add what the console reports as
violated. Only then rename the header to `Content-Security-Policy` and deploy
again. If time is short, stay in report-only mode and say so: it enforces
nothing. `frame-ancestors` is ignored in report-only mode; `X-Frame-Options`
covers framing meanwhile.

## 6. Hosted checks

None has run. Use a private browser window on `SITE_ORIGIN`.

| # | Check | Expected |
| --- | --- | --- |
| 6.1 | Headers: `curl -sI <SITE_ORIGIN>/` | The five headers of 5.3 |
| 6.2 | Live mode | The screen "Enter the access code" appears; the label "Test data — fixtures" and the "Test data" tag are absent; the label "Simulation — fictional portfolio, not advice" is present |
| 6.3 | API origin: network panel during a run | Requests go only to `SITE_ORIGIN` and `API_BASE_URL`; preflights are answered; no blocked request; no policy violation in the console (or only the ones being fixed in report-only mode) |
| 6.4 | Lazy three.js: network panel, cache disabled, on first load | The three.js chunk (558,259 bytes, 136,902 gzip, in the coordinator's local build) is **not** requested on the first screen; it is requested when the purchase stage opens |
| 6.5 | Wrong code | Nothing is displayed; note the message shown (see 4.8) |
| 6.6 | Robert, whole workflow of `docs/DEMO_SCRIPT.md` act 1 | Statuses and real-data figures of `docs/WORKFLOWS.md`; version 2 created by the challenge; report 1 still opens; investigation ids and agent mode noted |
| 6.7 | Mateo, act 2 | Both rules FAIL with the starting breach separated; ESGV shown as missing; the interpreter either asks about "oil" or shows the readable error; which one is noted |
| 6.8 | Narrow window (390 px) | The flat exposure view replaces the 3D one |
| 6.9 | Same build: the `_next/static/<build id>` path in the page source | Equal to the one in the local `out/index.html` |
| 6.10 | Fixtures mode still labelled: add `?fixtures=1` | The label "Test data — fixtures" is present |
| 6.11 | Unknown path, for example `/nope/` | Recorded; how Amplify serves it for this export is **[unverified]** |

Then record what is deployed, by hand (the interface shows no commit):
commit; zip names; stack outputs `CodeArtifact` and `DataSnapshotId`; template
prefix and change set name; Amplify `appId`, branch and job id; `SITE_ORIGIN`;
the output of every check above. `infra/evidence/` is where earlier
deployments were recorded; that directory is not this document's to write.

## 7. Rollback, step by step

| Step | Rollback | Notes |
| --- | --- | --- |
| 1 Amplify app and branch | `DeleteApp` | Nothing depends on it until step 3. Deleting it after step 3 leaves `AllowedOrigin` pointing at an origin nobody serves, which is harmless |
| 2 Snapshot upload | Nothing to undo | Ids are immutable and unused until a stack parameter names one. Rolling data back means passing the previous `DataSnapshotId` in a change set; before this deployment there is no previous id |
| 3 Backend, update fails | None needed | A failed update rolls back by itself (`scripts/deploy.md` section 5) **[phase 1]** |
| 3 Backend, update succeeded but checks fail | A change set with the previous `CODE_KEY` and `TEMPLATE_KEY`, and the previous parameters | See below |
| 5.2 Site deployment | Deploy the previous zip again (5.2 with the kept file) | The console's "Redeploy this version" on the previous job, or `StartJob` with `jobType` `RETRY`, may also work for a manual deployment **[unverified]** |
| 5.3 Headers | `UpdateApp` with the previous `customHeaders` (an empty string for none), then deploy again | A blank page after enforcing the policy means a violation: go back to report-only |

Backend rollback targets:

- **To the previous candidate build** (after a second deployment of this
  template): the previous `CODE_KEY` (stack output `CodeArtifact`, noted in
  section 3 step 3), the same `TEMPLATE_KEY`, and
  `PARAMETER_OVERRIDES = {"DataSnapshotId": "<previous id>"}` if the data
  changed. Unlisted parameters keep their values.
- **To phase 1**: `CODE_KEY = "lambda/byb-backend-5cf91f80c5c1a2ce.zip"` with
  `TEMPLATE_KEY = "templates/template-e076af541c8b13f5.yaml"`, the pair
  recorded as live on 2026-11-15 (`infra/evidence/milestone2.md`) and the pair
  committed in `02_deploy.py`. `AllowedOrigin` keeps the exact origin, so the
  guard passes; set `ALLOW_WILDCARD_ORIGIN = True` only if `*` is wanted on
  purpose. Phase 1 has two routes, pre-contract shapes and a **placeholder
  calculation**: the candidate's frontend does not work against it. Roll the
  site back too, or switch the demonstration to a fallback of
  `docs/DEMO_SCRIPT.md` and say so. **[unverified]**: this downgrade was never
  run; the phase-1 template does not declare `DataSnapshotId`, and the
  change-set name trap of section 3 applies, because this exact pair of keys
  was already used once.
- Objects in the artifacts bucket expire after 7 days (`scripts/deploy.md`
  section 2). The phase-1 objects were uploaded on 2026-11-14 and
  2026-11-15, so they should still exist; `02_deploy.py` checks with
  `HeadObject` and stops if not.
- Policies, results and traces written by the candidate stay in the bucket
  after a rollback. Phase 1 does not read `policies/` or `snapshots/`.

## 8. Teardown

1. `DeleteApp` on the Amplify app.
2. Backend: `scripts/deploy.md` section 8 (`DeleteStack`; empty and delete the
   retained data bucket, which now also holds `snapshots/` and `policies/`;
   empty and delete the artifacts bucket; `DeleteParameter` on the access
   code).
3. Locally: delete `/tmp/byb-e2e`, the header files of a rotation check, and
   `dist/`.

The whole account is deleted at the end of 2026-11-16, which removes all of
it. What survives: the code on GitHub once pushed (today `integration/rc` is
not pushed), the recording if saved locally, the evidence files in the
repository, and this procedure. A redeploy elsewhere needs Bedrock access to
the runtime model, a new access code and the data files that are not in git.

## 9. Values the coordinator supplies

No value here is a secret except the access code, which is never written.

| Value | Where it comes from | Used in |
| --- | --- | --- |
| Commit to deploy | `git rev-parse HEAD` in the clean checkout; the coordinator stamps the final one | Everything; zip names; the record |
| Authorization to mutate AWS | The account owner | Section 0 |
| Amplify app name and branch name | Chosen by the coordinator | Section 1 |
| `appId`, `defaultDomain` | `CreateApp` response | Sections 1, 5, 7, 8 |
| `SITE_ORIGIN` | `https://<branchName>.<defaultDomain>` | `AllowedOrigin`; checks 4.4, 4.8, 6 |
| `DataBucketName` | Stack output (`03_status.py`) | Section 2 |
| `SNAPSHOT_ID` | Printed by `scripts/build_snapshot.py` | `DataSnapshotId` |
| `CODE_KEY` | `s3_key` printed by `scripts/package.py` | `02_deploy.py` |
| `TEMPLATE_KEY` | `shasum -a 256 infra/template.yaml`, first 16 characters | `02_deploy.py` |
| Previous `CodeArtifact` and parameters | Stack outputs and parameters before the change | Section 7 |
| `API_BASE_URL` | Stack output `ApiBaseUrl` | The build variable, `connect-src`, every check |
| Access code | Systems Manager console ("Show decrypted value") for the presenter; the transfer file of `scripts/deploy.md` section 6 for the scripts; `read -rs` into `BYB_ACCESS_CODE` for `live_check.py` | Sections 4 and 6. Never in a file of the repository, a build variable, a report or the recording |
| Presigned URLs | `get_presigned_url`, `CreateDeployment` | Used once, never recorded |
| Amplify job id | `CreateDeployment` response | The record; rollback |
| Decision: report-only or enforced policy | The coordinator, after 5.3 | Section 5.3 |
| Decision: rotate the code or not | The coordinator | 4.9 |

## 10. Not verified

Read in the AWS documentation on 2026-11-14 (Amplify Hosting user guide and
API reference): the operations `CreateApp`, `CreateBranch`,
`CreateDeployment`, `StartDeployment`, `UpdateApp`; the parameters `name`,
`platform`, `customHeaders`, `appId`, `branchName`, `jobId`; that a manual
deployment takes a zip of build output and does not support server-side
rendering; the eight-hour limit between `CreateDeployment` and
`StartDeployment`; the two forms of `customHttp.yml`; that custom headers for
a manual deployment are set in the console or shipped with the artifacts,
followed by a redeploy.

Not verified, in the order they are met:

1. The present state of the stack, and that the account allows creating an
   Amplify app.
2. The exact shape of the `CreateApp` response (`defaultDomain`) and of the
   `CreateDeployment` response (`zipUploadUrl`); `GetJob`, `DeleteApp` and
   `StartJob` were not looked up.
3. That a branch created without a deployment yields the stated domain before
   anything is deployed, and what it serves meanwhile.
4. The snapshot upload: never run. That the functions accept the uploaded
   snapshot was shown locally only.
5. That CloudFormation accepts this template: the change set, the absence of
   a replacement of `HttpApi`, and therefore the stability of `ApiBaseUrl`.
6. The CORS guard and the two required parameters against a real stack; the
   change-set name re-use described in section 3.
7. Everything in section 4: the smoke test and `live_check.py` have run only
   against local handlers. How API Gateway answers a preflight from a
   non-allowed origin; whether authorizer refusals carry CORS headers; the
   30-second bound on a rotated code.
8. The real model with the current prompts (`investigator-4`,
   `interpreter-3`), and the API function's Bedrock permission.
9. The upload to the Amplify URL (content type), the deployment job, and that
   headers set with `UpdateApp` apply to a manual deployment after a redeploy.
10. The Content-Security-Policy against a real build, including the 3D
    explorer.
11. How Amplify serves an unknown path and the trailing-slash paths of this
    export.
12. Every rollback of section 7, in particular the downgrade to phase 1.
13. `amplify.yml`: never executed; not used by this runbook.

Also noted for the owners of other files: the "Limitations" of
`infra/README.md` still say that no interpreter is implemented and that the
5 s budget of `POST /check` is only logged, which the candidate's code
contradicts (`backend/agents/interpreter.py`, `backend/api/handler.py`); the
header of `scripts/deploy.md` still names the branch `agent/a2-backend`.
