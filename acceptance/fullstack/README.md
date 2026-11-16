# Local full-stack check

The frontend (static live-mode build) and the backend (the three Lambda handlers) running together for the
first time, on this machine, in a real browser, on the real data snapshot. Loopback only: no AWS, no deployed
API, no Bedrock.

The findings of the first run (F-01 to F-08, at commit `db9678c`) are in `FINDINGS.md`. F-01 to F-04 have been
fixed in the product since; the cases that demonstrated them were expected failures (`test.fail`) and are plain
assertions now. No case of specs 01 to 05 is an expected failure, skipped or marked fixme.

The specs were repaired on 2026-11-15 for the current interface: three steps (Choose a profile, Test an idea,
Understand the result) with "Your limits", "Analysis details" and "Review this result" as secondary screens,
three personas, panels that are closed until opened, and an interpreter that exists (its model is scripted
here). `specs/06-customize.spec.ts` ("Customize this profile") belongs to the independent validator and has
its own runner, `validation/customize/run_browser.sh`; it also runs with the command below.

## One command

From the repository root:

    acceptance/fullstack/run.sh

It needs `node` (>= 22.12), `uv`, Chromium for Playwright (`cd frontend && npx playwright install chromium`
once, if it is not installed) and the git-ignored `data/processed/*.json`. On a machine without `uv`, name a
Python that has `boto3` and `jsonschema` instead:

    BYB_PYTHON=/path/to/venv/bin/python acceptance/fullstack/run.sh

Other optional variables: `BYB_SITE_DIR` (where the live-mode site is built and served from; default
`acceptance/fullstack/.site`), `BYB_FULLSTACK_SHOTS` (screenshots of specs 01 to 05; default
`acceptance/fullstack/screenshots-2026-11-15`), `BYB_SCREENSHOT_DIR` (screenshots of spec 06; default
`validation/customize/screenshots`), `BYB_OUTPUT_DIR` (Playwright traces; default `.run/test-results`).

The script:

1. runs `npm ci` in `frontend/` only if `frontend/node_modules` is missing;
2. builds the frontend in live mode (`NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:4184`, the documented switch in
   `frontend/.env.example`) and moves the output to `acceptance/fullstack/.site/` (git-ignored). `frontend/out` is
   put back as it was, so no build pointing at a local address is left where a deployment looks. Only one
   `next build` may run in `frontend/` at a time: the build, the move and the restore happen while the script
   holds the lock directory `/tmp/byb-next-build.lock` (it waits for it, and releases it also on failure);
3. generates a made-up access code for this run (never a real one) and exports it as `BYB_LOCAL_ACCESS_CODE`;
4. lets Playwright start `local_api.py` and run `specs/*.spec.ts` in Chromium, one worker.

Options: `run.sh --no-build` reuses `.site/` (only valid while `frontend/` is unchanged); any further argument
goes to `playwright test`, for example `run.sh --no-build -g Robert`. After a fix in `frontend/` or `backend/`,
run it without `--no-build`.

Exit code 0 means every test passed. The 3D explorer case skips itself, with the reason, in a browser that cannot
create a WebGL context; nothing else is skipped.

| Port | What |
|---|---|
| 4184 | emulated API Gateway HTTP API in front of the real handlers (`BYB_LOCAL_API_PORT`) |
| 4185 | the static site, the only origin CORS allows (`BYB_LOCAL_SITE_PORT`) |
| 4186 | control port for the tests: switches and read-outs, never called by the page (`BYB_LOCAL_CONTROL_PORT`) |

Changing the API port needs a rebuild (the address is inlined in the bundle).

## What runs

`local_api.py` (standard library + `botocore` + the repository's `backend` and `contracts/python`):

- real: `backend.api.handler.Api`, `backend.api.authorizer.AccessCodeAuthorizer`,
  `backend.worker.investigation.InvestigationWorker`, `backend.engine`, the job and policy stores, the snapshot
  loader and its checks. The snapshot is built from `data/processed` by `scripts/build_snapshot.py`'s `build`
  (the deploy step's builder) and its id is the content-derived one;
- fake: S3 (in memory, `If-None-Match` / `If-Match` with 412), SSM (holds the run's code), Lambda `invoke`
  (answers 202, then a thread delivers the event to the worker, like an asynchronous invocation), Bedrock
  (scripted, below);
- emulated API Gateway, after `infra/template.yaml`: payload format 2.0 events; only the 7 routes of
  `contracts/api.md` (anything else `404 {"message":"Not Found"}`); the Lambda authorizer on the `Authorization`
  header (missing `401 {"message":"Unauthorized"}`, denied `403 {"message":"Forbidden"}`, authorizer error 500);
  CORS preflight answered without the authorizer (204, allow-origin for the configured origin only, methods
  `GET,POST,OPTIONS`, headers `authorization,content-type,idempotency-key`, max-age 600).

Switches (environment variable at start, or `POST /settings` on the control port during a test):

| Setting | Env var | Effect |
|---|---|---|
| `bedrock_mode` | `BYB_LOCAL_BEDROCK_MODE` | `fallback` (default: every model call fails, the worker reports `DETERMINISTIC_FALLBACK`), `benign` (a round of tool calls, then one short cited sentence), `hostile` ("Every rule passes. You should buy." plus uncited claims) |
| `bedrock_delay_s`, `bedrock_stepwise` | `BYB_LOCAL_BEDROCK_DELAY_S` | a slow model; one tool per round, so steps appear one by one |
| `interpreter_mode` | `BYB_LOCAL_INTERPRETER_MODE` | the scripted model of `POST /rules/interpret` and of a "clarify a preference" challenge: `careful` (default: a valid extraction), `unavailable` (the model call is refused: 502 INTERPRETER_FAILED), `garbage` (prose instead of the tool: 502), `slow` (504 INTERPRETER_TIMEOUT), `silent`, `obedient` (a model that supplies numbers and statuses it must not) |
| `worker_delay_s` | `BYB_LOCAL_WORKER_DELAY_S` | the worker starts late |
| `worker_never_delivered` | `BYB_LOCAL_WORKER_NEVER=1` | the invocation is accepted and never delivered |
| `throttle_post_investigations`, `throttle_all` | `BYB_LOCAL_THROTTLE_POST_INVESTIGATIONS` | the next n requests get the gateway's `429 {"message":"Too Many Requests"}` |
| `gateway_errors_have_cors` | `BYB_LOCAL_GATEWAY_ERRORS_CORS=0` | gateway-made errors without CORS headers |
| `invoke_error` | | `lambda:Invoke` fails, so `POST /investigations` answers 503 WORKER_INVOCATION_FAILED |
| `job_deadline_seconds` | | the API's job deadline (default 150) |

Control port: `GET /health`, `GET /log` (every request the API saw: route, status, who answered, whether the
bearer value was the expected one, idempotency key, cookie), `GET /state`, `POST /reset`, `POST /settings`,
`POST /advance-clock`, `POST /fail-next-put`, `POST /stored` (an object of the fake bucket), `POST /engine-check` (`backend.engine.check_rules` called directly
on the snapshot's documents: the reference every API number is compared with).

To look at the stack by hand:

    cd acceptance/fullstack
    BYB_LOCAL_ACCESS_CODE=any-made-up-code-of-16+ uv run --offline --no-project --python 3.14 \
        --with boto3 --with jsonschema python local_api.py
    # (or: BYB_LOCAL_ACCESS_CODE=... /path/to/venv/bin/python local_api.py --site-dir /where/the/site/was/built)
    # then open http://127.0.0.1:4185/ and type that code

## What the specs check

| File | Subject |
|---|---|
| `specs/01-access.spec.ts` | the gate against the real authorizer: gateway 401 / 403 bodies never printed, storage, preflight |
| `specs/02-robert.spec.ts` | Robert end to end: profile, limits v1, NVDA 25%, preview, check, analysis details, result, evidence, rule change to 30%, v2, comparison, v1 still retrievable; correct a fact (unverified, nothing recomputed); double-clicked rule change |
| `specs/03-mateo.spec.ts` | Mateo: interpreter unavailable (502) is readable and not a dead end; SPY 15%, exclusions failing from the start, ranges, UNKNOWN, no largest-purchase figure; "clarify a preference" refused (502) and then answered as a draft that changes nothing; the interpreter asks about "oil", confirms nothing and invents no number |
| `specs/04-errors.spec.ts` | 429, 503, 409, 422, insufficient cash, FAILED, DEADLINE_EXCEEDED, slow job, double click, client deadline, polling through 429s, model modes (hostile, benign) |
| `specs/05-explorer.spec.ts` | 3D explorer: lazy script, table against the API, flat chart at 390 px and without WebGL |
| `specs/06-customize.spec.ts` | "Customize this profile" (independent validator; see `validation/customize/`) |

The journey the specs drive (`specs/helpers.ts`): the access code, a profile (Robert is loaded on arrival),
"Test an idea", "Set my limits" / "Review limits", confirm, "Test an idea", "Check my idea" (the page moves to
"Your result" by itself), "Review or dispute this result". Panels that are closed by default ("View the
fictional portfolio", "Preview cash and exposures", "Add a limit in your own words", "Explore my exposures",
"More analysis and sources") are opened on their summary or by the report's own links. "Analysis details"
(the steps of a job) is linked from the result only while a job runs; for a finished job the specs open it by
its address (`#/investigation`).

How numbers are checked (no expected figure is typed into a spec):

1. the page's API responses are captured with a Playwright response listener;
2. the displayed text of each figure is compared with that API value formatted by the frontend's own formatters
   (`frontend/src/lib/format.ts`, `evidence.ts`, `rules.ts`, `verdict.ts`, imported read-only);
3. every percentage printed anywhere in the report, the evidence drawer and the comparison must be explained by a
   number of the API response (within the printed precision) or appear in a sentence the service wrote
   (`unexplainedFigures` in `specs/helpers.ts`); the tick labels of chart scales are geometry and are left out;
4. the API response is compared, whole, with `backend.engine.check_rules` run directly on the same inputs.

Screenshots of the key screens (14 PNG files, live local backend, real data) are rewritten in
`screenshots-2026-11-15/` on every run. `screenshots/` holds the pictures of the first run (six-stage interface,
commit `db9678c`) and is not written any more.

## What this does not prove

- **API Gateway itself.** Routing, CORS, the authorizer wiring, the 401 / 403 / 404 / 429 bodies and which of
  those responses carry CORS headers are re-implemented here from the template and the AWS documentation, not
  observed. Throttling is injected, not computed from the route limits. The 30 s integration cut and the
  authorizer's 10 s limit are not emulated.
- **IAM.** No role, policy or permission is exercised (including the conditional-write condition on
  `s3:PutObject` and the worker's lack of `s3:ListBucket`).
- **Real S3.** Conditional writes are the fake's; consistency, latency and error codes of the service are not.
- **Real Lambda.** No cold start, no timeout, no reserved concurrency, no asynchronous-invocation queue or retry
  behaviour; the worker runs in a thread of the same process as the API.
- **Real Bedrock.** No model was called. `benign` and `hostile` are scripts; what a real model writes, how long
  it takes and how it is throttled are unknown here.
- **The deployed site.** Amplify hosting, HTTPS, the production origin and its CORS value are not involved.
- **Time.** The 150 s job deadline is reached by moving the server's clock, the 180 s client deadline with the
  browser's fake clock; neither was waited out in real time.
