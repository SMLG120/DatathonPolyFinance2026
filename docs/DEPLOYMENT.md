# Deployment

How to host Before You Buy, written for commit `d36e41f` (2026-11-15 UTC).

**Nothing in this document has been executed.** No Amplify app exists, no
frontend is hosted, and this document was written without AWS access. The
backend half refers to a procedure that was executed and recorded
(`scripts/deploy.md`, `infra/evidence/milestone2.md`); the frontend half is a
plan. Section 13 lists what is missing before hosting can work, and section 14
what could not be verified.

## 1. State today

| Part | State | Source |
| --- | --- | --- |
| Backend stack `before-you-buy`, `us-east-1` | Deployed four times on 2026-11-14 and 2026-11-15 UTC; last status `UPDATE_COMPLETE`; smoke runs 6 to 8 passed. Phase 1: two routes, **placeholder calculation**, pre-contract shapes | `infra/evidence/milestone2.md` sections 1 and 15 |
| Template in the repository | `infra/template.yaml`, SHA-256 prefix `e076af541c8b13f5`, equal to deployment D4 in the evidence file | computed for this document |
| Backend phase 2 (real engine, contract routes) | In progress, not in this commit | reported by the lead on 2026-11-14 |
| Data snapshot in S3 | Not uploaded; no upload step in this commit | section 5 |
| Frontend | Not hosted. No Amplify app | `docs/PLAN.md` P4 |
| CORS allowed origin | `*` | `infra/evidence/milestone2.md` section 1 |

The AWS account is a workshop account. It is deleted at the end of 2026-11-16
with all its data; the exact hour is unresolved (`docs/PLAN.md` P2). Every URL
below stops working then.

## 2. Order of operations

1. Deploy backend phase 2 (section 4) and upload the data snapshot (section 5).
2. Run the backend smoke check.
3. Build the frontend with the API base URL (sections 3 and 6).
4. Host it and note the origin (section 6).
5. Set the security headers (section 7) and tighten CORS (section 8).
6. Verify (section 10) and record what is deployed (section 9).

The API base URL does not change when the stack is updated, so step 3 does not
depend on step 5.

## 3. Environment variables

| Variable | Where | Secret | Notes |
| --- | --- | --- | --- |
| `NEXT_PUBLIC_API_BASE_URL` | Frontend build (shell, or Amplify environment variable) | **No. Public.** | Inlined into the JavaScript bundle by `next build` and readable by every visitor (`frontend/.env.example`). The value is the stack output `ApiBaseUrl`, without a trailing slash. Empty or invalid means the site runs in fixtures mode and shows "Test data — fixtures" (`frontend/src/lib/config.ts`) |
| `AMPLIFY_MONOREPO_APP_ROOT` | Amplify app, Git-connected option only | No | Must be `frontend`, equal to `appRoot` in `amplify.yml` |

**No secret may ever be a build variable.** Anything prefixed `NEXT_PUBLIC_`
is published. The access code is not configuration: the user types it at
runtime and it is kept in `sessionStorage` only
(`frontend/src/lib/access-code.ts`, `docs/LEAD_DECISIONS.md` D8). The project
uses no `.env` file (`scripts/deploy.md`), and none should be created for
deployment. The access code is 48 hexadecimal characters
(`scripts/deploy.md` section 2), which is what the bundle check in section 6
looks for.

Backend configuration is stack parameters and Lambda environment variables set
by the template; the one secret is the SSM SecureString
`/before-you-buy/access-code`, created by the bootstrap step and never printed
(`scripts/deploy.md` section 2).

## 4. Backend

Follow `scripts/deploy.md`: build the zip, upload zip and template through
presigned URLs, create the change set, read it, execute it, read the status,
run `scripts/e2e_smoke.sh`.

For phase 2 the packaging command changes: `scripts/deploy.md` section 1 says
to add `--with-engine` and `--include contracts/python=<archive prefix>`, and
`backend/engine/README.md` says a deployment must ship
`contracts/python/byb_contracts` and `contracts/schemas` next to the engine.
**The exact command, the new routes and any IAM change are pending the backend
handoff.** One change is certain to be needed: in the deployed stack no role
may write to `policies/` or `snapshots/` (`infra/README.md` "IAM"), and the
contract stores policy versions.

## 5. Data snapshot upload: pending

The engine needs the instrument registry, the holdings snapshot, market data
and the controversy registry. The worker role can read `snapshots/*` in the
data bucket, and nothing in the stack can write there, so the upload is a
deployer action.

**No upload script or procedure exists in this commit. To be confirmed by the
backend handoff:** the object keys, the file list and the command.

What is known:

- The files are the outputs of `python3 -I data/scripts/build_processed.py`
  in `data/processed/`. Five of the seven are git-ignored and absent from a
  fresh clone: `holdings.json`, `instruments.json`, `market_data.json`,
  `fund_sector_breakdowns.json`, `build_report.json`. They exist only on a
  machine that holds the raw issuer files and the starter prices
  (`docs/data-sources.md` section 1).
- The bucket is private, so uploading there is not publication. Whether the
  issuer-derived files may be published is a separate, pending decision
  (`docs/data-sources.md` section 6).
- Uploads from this environment go through presigned URLs, as for the code zip
  (`scripts/deploy.md` section 3).
- Record the holdings date (2026-11-12) and the source ids of the uploaded
  snapshot next to the deployed commit (section 9).

## 6. Frontend hosting

The site is a Next.js static export: `next build` writes plain files to
`frontend/out` (`frontend/next.config.ts`). It has one page, `/`, so no
rewrite rule is needed. The Amplify platform is `WEB` (static hosting).

Build, for either option:

    cd frontend
    npm ci
    NEXT_PUBLIC_API_BASE_URL=https://<api-id>.execute-api.us-east-1.amazonaws.com npm run build

Node.js 22.12 or later is required (`frontend/package.json`).

### Option A: manual deploy of the `out/` zip (recommended)

1. Build locally as above, from a clean checkout of the commit to be hosted.
2. Check the bundle before uploading:

       grep -rl "execute-api" frontend/out/_next/static | head -1     # the API URL was inlined
       grep -rEow "[0-9a-f]{48}" frontend/out | head                  # expect nothing; explain any hit before uploading

3. Zip the **contents** of `out/`, named with the commit:

       (cd frontend/out && zip -qr "../../dist/byb-frontend-$(git rev-parse --short HEAD).zip" .)

   `dist/` and `*.zip` are git-ignored.
4. In the Amplify console: create an app with "Deploy without Git", give the
   app and the environment a name, upload the zip. Through the AWS MCP tool
   the equivalent is `CreateApp` (platform `WEB`), `CreateBranch`,
   `CreateDeployment`, upload the zip to the returned URL, `StartDeployment`.
5. The origin is `https://<environment-name>.<app-id>.amplifyapp.com`.

### Option B: Git-connected branch

1. Push the commit to GitHub.
2. In the Amplify console: create an app from the GitHub repository, choose
   the branch, tick the monorepo box and enter `frontend` as the app root.
   The console then sets `AMPLIFY_MONOREPO_APP_ROOT`.
3. Set the environment variable `NEXT_PUBLIC_API_BASE_URL`.
4. Amplify reads `amplify.yml` from the repository root. If the console
   proposes Next.js server-side settings (an artifact directory `.next`), the
   file in the repository overrides them; check that the app's platform is
   `WEB`.
5. Each push to the branch builds and deploys.

### Recommendation: option A

- Nothing after the first review merge is on GitHub `main`. Option B cannot
  host the current code until it is pushed, and then hosts whatever the branch
  holds, tested or not.
- The account is deleted within two days. Continuous deployment has no value
  for one or two deployments, and option B adds things that have never been
  run here: the Amplify build image, its Node.js version, `nvm`, and the
  console's framework detection.
- With option A the hosted files are exactly the files that were built and
  checked locally.
- Option B requires authorizing the Amplify GitHub app on the repository
  owner's GitHub account. That authorization is outside AWS and is not removed
  when the AWS account is deleted. The repository is public, so hosting from
  it adds nothing a reader cannot already build.

The cost of option A: the commit is not recorded automatically (section 9),
and custom headers are set in the console (section 7).

## 7. Security headers

Set as Amplify custom headers. This is a proposal: **the policy below was not
tested against a build** and must not be copied blindly.

What a Next.js static export needs:

- **Inline scripts.** The exported HTML contains inline `<script>` elements
  that carry the data React needs to start. A policy of `script-src 'self'`
  alone blocks them and the page stays blank. A static host cannot issue a
  nonce per response, so the choices are `'unsafe-inline'` or one hash per
  inline script, recomputed at every build. The snippet uses
  `'unsafe-inline'`; hashes are the stricter option if time allows.
- **Inline styles.** The exposure chart sets `style` attributes
  (`frontend/src/components/verdict/ExposureChart.tsx`), so `style-src` needs
  `'unsafe-inline'`.
- **No third-party origin.** The stylesheet imports only Tailwind, compiled
  into a local file (`frontend/src/app/globals.css`); no external font, script
  or image host was found in `frontend/src`.
- **The 3D exposure explorer** (in progress, not in this commit) uses WebGL
  through three.js and is loaded lazily from the same origin. It may need
  additions such as `worker-src blob:` or `img-src blob:`. Re-test the policy
  after it is integrated.

With `'unsafe-inline'` for scripts, the policy does not stop an injected
inline script. What it still does: `connect-src` limits where a script can
send data to the site itself and the API; `frame-ancestors` prevents framing;
`object-src` and `base-uri` close two other routes.

`customHttp.yml` for option A (paste into Hosting, Custom headers, then deploy
again), with `<api-origin>` replaced by the stack output `ApiBaseUrl`
(`https://3t4hod912l.execute-api.us-east-1.amazonaws.com` on 2026-11-14,
`infra/README.md`):

```yaml
customHeaders:
  - pattern: '**/*'
    headers:
      - key: 'Content-Security-Policy'
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

For option B the file is saved in the repository root and uses the monorepo
form:

```yaml
applications:
  - appRoot: frontend
    customHeaders:
      - pattern: '**/*'
        headers:
          - key: 'Content-Security-Policy'
            value: "..."   # same headers as above
```

No `customHttp.yml` exists in the repository; creating it is a lead decision.

Procedure: first deploy with the header named
`Content-Security-Policy-Report-Only`, run the whole Robert workflow with the
browser console open, fix every reported violation, then rename the header to
`Content-Security-Policy` and deploy again.

## 8. Tighten the API's allowed origin

The stack parameter `AllowedOrigin` is `*`. Once the hosted origin is known,
set it to exactly that origin, with scheme and without a trailing slash, in
`PARAMETER_OVERRIDES` of `scripts/mcp/02_deploy.py`
(`scripts/deploy.md` section 4):

    PARAMETER_OVERRIDES = {"AllowedOrigin": "https://<environment-name>.<app-id>.amplifyapp.com"}

- `authorization` must be an allowed header, with `content-type` and
  `idempotency-key`: the browser sends all three (`contracts/api.md`
  section 1). The template already lists them (`infra/template.yaml`,
  `AllowHeaders`). Do not remove them, and add any new request header the
  phase-2 frontend sends.
- The template takes one origin. After the change, a frontend served from
  anywhere else (`npm run dev`, `npm start` on `127.0.0.1:4173`) can no longer
  call the API from a browser. Do it after local testing is finished.
- `scripts/e2e_smoke.sh` sends its preflight check with
  `Origin: https://example.org` and expects 204. Its CORS lines may read
  differently after the change; the other checks use `curl` and are not
  affected by CORS.
- CORS is not authentication. The bearer code is.
- Make this change in the same change set as, or directly after, the header
  change in section 7 (`docs/PLAN.md` P9).

## 9. Record what is deployed

Nothing in the interface shows which commit it was built from, and no hosted
version is tied to a Git commit.

**Proposal, not implemented:** a public build variable
`NEXT_PUBLIC_COMMIT_SHA`, set at build time
(`NEXT_PUBLIC_COMMIT_SHA=$(git rev-parse --short HEAD)`; on a Git-connected
Amplify build the commit is available as `AWS_COMMIT_ID`) and shown in the
footer. It needs a frontend change by the frontend owner. It does not exist in
this commit.

Until then, write down by hand, in the release notes or
`infra/evidence/`:

| Item | Where to read it |
| --- | --- |
| Frontend commit | `git rev-parse HEAD` in the checkout that was built; the zip file name |
| Backend commit and code artifact | the checkout that was packaged; stack output `CodeArtifact` |
| Template | SHA-256 prefix of `infra/template.yaml`; the change set name |
| Data snapshot | holdings date, source ids, object keys |
| Engine version | `backend/engine/version.py`; `calculation_version` in a result |
| Runtime model | stack output `BedrockModelId` |
| Hosted origin and Amplify deployment or job id | Amplify console |

## 10. Verification after deploy

| Check | How | Expected |
| --- | --- | --- |
| Headers | `curl -sI https://<hosted-origin>/` | The five headers of section 7 |
| Live mode | Open the site in a private window | The access-code screen appears; the label "Test data — fixtures" is **absent**; no `?fixtures=1` |
| API origin | Browser network panel during a run | Requests go only to the hosted origin and to `ApiBaseUrl`; the preflight is answered; no Content-Security-Policy violation in the console |
| No stale assets | Hard reload; compare the `_next/static/<build id>` path in the page source with the local `out/index.html` | Same build id |
| Hosted Robert run | The whole workflow of `docs/WORKFLOWS.md` on the hosted site | Statuses as described there; figures equal to the real-data column (`backend/engine/evidence/robert_max_compliant.md`); the investigation id noted |
| Result is real | The result's `calculation_version` | `byb-engine-...`, not `phase1-placeholder-1` |
| Other origins refused | A browser call from another origin after section 8 | Blocked by CORS |
| Authentication | A wrong code | The access-code prompt returns; nothing is displayed |
| Backend | `scripts/e2e_smoke.sh` (`scripts/deploy.md` section 6) | Exit status 0 |
| Fixtures mode still labelled | Add `?fixtures=1` | The label is present |

Keep the outputs. A check that was not run is reported as not run.

## 11. Rollback

- **Frontend, option A:** upload the previous zip again. Keep every deployed
  zip, named with its commit, until the recording is saved.
- **Frontend, option B:** in the Amplify console, open the branch and choose
  "Redeploy this version" on the previous build.
- **Backend:** create and execute a change set with the previous `CODE_KEY`
  and `TEMPLATE_KEY` in `scripts/mcp/02_deploy.py`. The phase-1 pair recorded
  as live on 2026-11-15 is `lambda/byb-backend-5cf91f80c5c1a2ce.zip` with
  `templates/template-e076af541c8b13f5.yaml`
  (`infra/evidence/milestone2.md`). Objects in the artifacts bucket expire
  after 7 days, which is later than the account's deletion. A failed update
  rolls back by itself (`scripts/deploy.md` section 5).
- Rolling the backend back to phase 1 returns the placeholder calculation and
  the pre-contract shapes. A contract-typed frontend will not work against it;
  roll both back, or switch the demonstration to fixtures mode and say so.
- **CORS:** set `AllowedOrigin` back to `*` with a parameter-only change set.

## 12. Teardown, and what survives

Backend teardown: `scripts/deploy.md` section 8. Add: delete the Amplify app.
If option B was used, remove the Amplify GitHub app's access to the repository
in GitHub settings.

The whole account is deleted at the end of 2026-11-16, which removes the
stack, both buckets, the SSM parameter, the logs, the Amplify app and every
stored investigation.

What survives the deletion:

- The code on GitHub, once pushed. Today nothing after the first review merge
  is on `main`.
- The demo recording, if it was saved locally.
- `infra/evidence/` in the repository: the recorded proof of the deployment.
- The procedure to redeploy in another account (`infra/README.md`,
  `scripts/deploy.md`, this file). A redeploy needs Bedrock access to the
  runtime model, a new access code, and the data files that are not in git.

What does not survive: the hosted URL, the API URL, the access code, the
uploaded snapshot, stored policies, results and traces.

## 13. Missing deployment prerequisites

Found in the repository at `d36e41f`, most blocking first.

1. **Backend phase 2 is not in this commit and not deployed.** The API has two
   of the seven routes, pre-contract shapes and a placeholder calculation
   (`infra/README.md` "Gap to the contracts"). A hosted live frontend has
   nothing correct to call.
2. **The frontend is on provisional types and is not wired to the contract
   API.** `docs/PLAN.md` P8 records that it does not typecheck against the
   synced contract copies at this commit. Whether `npm run build` succeeds at
   this commit was not checked.
3. **No data snapshot procedure**: no upload script, no agreed object keys,
   and the processed files are absent from a fresh clone (section 5).
4. **IAM**: no role can write `policies/`; phase 2 needs a template change
   (section 4).
5. **No Amplify app, and the code to host is not on GitHub** (`origin/main`
   ends at the first review merge).
6. **The access code must reach the presenter** without entering the
   repository, a build variable or the recording. The documented way is the
   Systems Manager console (`scripts/deploy.md` section 6).
7. **`AllowedOrigin` is `*`** and no security header is configured; no
   `customHttp.yml` exists.
8. **Client polling deadline 120 s**, below the 150 s job deadline; the
   contract says 180 s and a 1.5 s interval (`frontend/src/lib/config.ts`,
   `contracts/api.md` section 1). A slow investigation would be shown as
   failed while it is still running.
9. **No commit identifier in the interface** (section 9).
10. **Deadline and expiry hour unresolved** (`docs/PLAN.md` P2): the time
    available for hosting and recording is unknown.
11. **`infra/README.md` is partly stale**: its status box names template
    `9b1c94d4e07d8bc3` and its resource table gives the earlier throttle
    limits, while `infra/evidence/milestone2.md` records the later deployment
    D4 (`e076af541c8b13f5`, 20 rps / burst 40 and 5 rps / burst 10). It also
    points to `work/PAUSE_CHECKPOINT.md`, which is git-ignored. The evidence
    file is the current one.
12. **No Node.js version file** (`.nvmrc`) for the build image; `amplify.yml`
    installs Node 22 with `nvm` instead.
13. A comment in `frontend/scripts/serve-out.mjs` names "S3 + CloudFront" as
    the deployed host. The decided host is Amplify Hosting.

## 14. Not verified without AWS access

Checked against the AWS documentation on 2026-11-14 (Amplify Hosting user
guide: monorepo build settings, custom headers, manual deploys): the
`amplify.yml` keys `version`, `applications`, `appRoot`, `frontend`, `phases`,
`preBuild`, `build`, `commands`, `artifacts`, `baseDirectory`, `files`,
`cache`, `paths`; that `appRoot` must equal `AMPLIFY_MONOREPO_APP_ROOT`; that
the console sets that variable for a monorepo app; the two `customHttp.yml`
forms; that a manual deploy accepts a zip of build output and does not support
server-side rendering. `amplify.yml` parses as YAML and its two guard commands
were run locally.

Not verified:

- That `amplify.yml` builds this app in Amplify. It has never run.
- That `baseDirectory` and the cache paths are resolved relative to `appRoot`
  when `buildPath` is not set. The documentation's example with `buildPath: /`
  uses a path from the repository root; this file relies on the default.
- The Node.js version of the default build image, and that `nvm install 22`
  works in it and gives 22.12 or later. The file fails the build if not.
- Whether the console detects a Next.js 16 static export as static (`WEB`) or
  proposes server-side settings (`WEB_COMPUTE`).
- The Amplify API operation names in section 6, option A, and
  `AWS_COMMIT_ID`: written from memory, not looked up.
- Whether custom headers saved in the console apply to a manual-deploy app
  without including a `customHttp.yml` in the zip. The documentation describes
  both ways.
- That the Content-Security-Policy in section 7 lets the built site run. No
  build was made for this document.
- How API Gateway answers a preflight from an origin that is no longer
  allowed, and so what `scripts/e2e_smoke.sh` prints after section 8.
- How Amplify serves an unknown path for this export (`404.html`).
- The current state of the stack. It was last read on 2026-11-15 00:23 UTC
  (`infra/evidence/milestone2.md` section 1).
- That the account allows creating an Amplify app. `docs/PLAN.md` P4 records
  a successful `amplify:ListApps` call only.
