# Backend infrastructure (phase 1 deployed; milestone 5 in this branch, not deployed)

Stack `before-you-buy`, account `010928212265`, region `us-east-1`. One SAM
template, `infra/template.yaml`, deployed through CloudFormation change sets.
Everything is a fictional simulation; the account is deleted after 2026-11-16.

> **Status when work was paused (2026-11-14, about 23:55 UTC).** The text below and
> `infra/evidence/milestone2.md` describe the deployment as proven by smoke run 3. After that,
> live probes showed that API Gateway throttling does not bound a burst, so reserved concurrency
> (5) was added to the worker and deployed. `infra/template.yaml` is that deployed template
> (SHA-256 prefix `9b1c94d4e07d8bc3`). Not yet folded into the text: the probe results (raw
> outputs in `infra/evidence/raw/`), the 429 answers seen right after a flood (smoke runs 4
> and 5), the final smoke run on the current template, and a pending decision on the throttle
> limits. See `work/PAUSE_CHECKPOINT.md`.

## Milestone 5 (branch `agent/a2-backend`): what the code and the template are now. Not deployed.

Everything from "What phase 1 proves" down describes the deployment that is still running in the account
(phase-1 zip, template `9b1c94d4e07d8bc3`) and stays as its record. This section says what differs in this branch.
None of it has been deployed, and no AWS call was made to produce it: it is verified by the local tests only
(`backend/tests/service`, in particular `test_service_template.py`, `test_service_package.py`,
`test_service_workflow.py`).

**Code.** The seven routes of `contracts/api.md` are implemented in the API function; the worker runs the real
engine (`backend/engine`, `check_rules`) on the stored request before and independently of any model call; the
"Gap to the contracts" table below is closed except where "Limitations of milestone 5" says otherwise. The
placeholder `compute_exposure` is gone. A model failure no longer fails the job: the server runs the same checks,
every statement is a template and `agent.mode` is `DETERMINISTIC_FALLBACK`.

**Data.** Holdings, prices, registries and the three scenarios are a snapshot in the data bucket under
`snapshots/<snapshot_id>/` (`manifest.json` plus eight files), read by both functions with `s3:GetObject`, verified
(manifest id, SHA-256 of every file, strict JSON, contract validators, coverage and issuer consistency) and cached
in memory per container. Nothing can write there except the deploying identity. The id is the stack parameter
`DataSnapshotId` (no default) and the environment variable `DATA_SNAPSHOT_ID`. See `scripts/deploy.md`, 3b.

**Template changes since the deployed one** (each is asserted by `test_service_template.py`):

| What | Before (deployed) | Now (this branch) |
| --- | --- | --- |
| Parameters | - | `DataSnapshotId` (required, pattern `snap-YYYY-MM-DD-<12 hex>`); output `DataSnapshotId` |
| Routes | `POST /investigations`, `GET /investigations/{id}` | plus `POST /investigations/{id}/challenge` (throttle 5 rps, burst 10, like create), `GET /portfolios/{persona_id}`, `POST /rules/interpret`, `POST /rules/confirm`, `POST /check` (default throttle 20 rps, burst 40). Same authorizer, payload 2.0, 20 s integration timeout. No `$default` route |
| API function environment | `DATA_BUCKET`, `WORKER_FUNCTION_NAME`, `JOB_DEADLINE_SECONDS`, `LOG_LEVEL` | plus `DATA_SNAPSHOT_ID`, `BYB_SCHEMA_DIR=/var/task/byb_contracts/schemas`, `BEDROCK_MODEL_ID` (display only: the role has no Bedrock permission) |
| Worker environment | as deployed | plus `DATA_SNAPSHOT_ID`, `BYB_SCHEMA_DIR` |
| API role, `s3:GetObject` | `jobs/*`, `results/*` | plus `policies/*`, `snapshots/*` (statement `ReadJobsResultsPoliciesAndSnapshots`) |
| API role, `s3:PutObject` | `jobs/*` with `If-None-Match` or `If-Match` | plus `policies/*` only with `If-None-Match` (new statement `CreatePolicyVersionOnlyIfAbsent`, condition `Null: s3:if-none-match = false`): a policy version is written once and never overwritten |
| API role, `s3:ListBucket` | prefix `jobs/*` | prefixes `jobs/*` and `policies/*` (statement `ListJobsAndPoliciesPrefixesOnly`, condition `StringLike s3:prefix`): latest-version lookup, and a missing object is a 404 instead of a 403 |
| Worker role, `s3:GetObject` | `jobs/*`, `snapshots/*` | plus `policies/*` (statement `ReadJobsPoliciesAndSnapshots`) |
| Authorizer | `ReauthorizeEvery: 300`, function cache 60 s | `ReauthorizeEvery: 0`, function cache 30 s: a rotated code stops working within 30 s instead of about 6 minutes |
| CORS | `AllowedOrigin` default `*` | unchanged in the template; `scripts/mcp/02_deploy.py` refuses to execute a change set whose effective origin is `*` unless `ALLOW_WILDCARD_ORIGIN` is set on purpose |

No statement uses a wildcard action or `Resource: "*"`; no role can write under `snapshots/`; the worker cannot
write `policies/` or create a job; the authorizer role is unchanged. Worker timeout 160 s = contract deadline
150 s + 10 s; reserved concurrency and retries 0 are unchanged.

**Failure codes of a job** are now the contract's: `DEADLINE_EXCEEDED`, `WORKER_INVOCATION_FAILED`,
`WORKER_ERROR`, `ENGINE_ERROR`, `DATA_UNAVAILABLE`. The `MODEL_*` codes below no longer exist: a model problem
is a fallback, not a failure.

**Limitations of milestone 5.**

- `POST /rules/interpret` and the `CLARIFY_PREFERENCE` challenge answer 502 `INTERPRETER_FAILED` (a code the
  contract documents): no interpreter is implemented. A free-text purchase request is answered by a template
  clarification built from the scenario's demo requests, without a model.
- Model-written statements are filtered by wording rules (`backend/agents/explain.py`), which is not a proof of
  meaning. Decisive sentences are always the engine's templates.
- The 5 s budget of `POST /check` is logged (`check_completed.elapsed_ms`), not enforced. Locally a check on the
  real data takes about 60 ms plus about 35 ms of input guards; a cold start also loads and validates the 1.4 MB
  snapshot (about 0.3 s locally, not measured in Lambda).
- `ReauthorizeEvery: 0`, the five new routes and the new IAM statements have never been through CloudFormation.
- The snapshot id is not a member of the frozen result or job schema: it is in the job's internal part, the
  stored result's `inputs`, the trace and the logs, not in what `GET` returns.

What phase 1 proves: one real request goes through API Gateway, is stored,
reaches Amazon Bedrock, executes an allowlisted tool and writes a result and a
trace to S3. The infrastructure, the roles and the asynchronous lifecycle are
real. **The tool's calculation is a placeholder** (`compute_exposure` repeats
the requested direct weight and reports indirect exposure as unknown), and the
request and response shapes predate `contracts/` (see "Gap to the contracts").

Live proof with real output: `infra/evidence/milestone2.md`.
Exact deploy sequence: `scripts/deploy.md`.

## Architecture

    browser
      |  Authorization: Bearer <access code>
      v
    API Gateway HTTP API  -- CORS preflight answered here, no token needed
      |  Lambda authorizer (REQUEST, payload 2.0, simple responses)
      |     compares the token with an SSM SecureString, constant time
      v
    API function (15 s)                         before-you-buy-api
      |  POST /investigations
      |     1. validate            2. S3 PutObject jobs/<id>.json  If-None-Match: *
      |     3. Lambda Invoke (Event) on the worker; must answer 202
      |     4. only then HTTP 202 {investigation_id, status, poll}
      |  GET /investigations/{id}   reads jobs/<id>.json (+ results/<id>.json)
      v
    worker function (160 s, async, 0 retries)   before-you-buy-worker
      |  claim QUEUED -> RUNNING by compare-and-swap (If-Match)
      |  Bedrock Converse loop, model us.anthropic.claude-sonnet-5-5
      |     one allowlisted tool, schema enforced; each tool event is appended
      |     to the job as it completes
      |  results/<id>.json and traces/<id>.json, write-once (If-None-Match: *)
      v
    S3 data bucket (private)   snapshots/ policies/ jobs/ results/ traces/

No database, queue or state machine: S3 conditional writes are the only job
store. The API function never waits for the model.

### Resources (18)

| Logical id | Type | Notes |
| --- | --- | --- |
| `DataBucket`, `DataBucketPolicy` | S3 | Block Public Access x4, SSE-S3, `BucketOwnerEnforced`, deny non-TLS, `jobs/` and `traces/` expire after 3 days, retained on stack deletion |
| `HttpApi`, `HttpApiApiGatewayDefaultStage` | API Gateway HTTP API | `$default` stage, CORS, throttle 10 rps / burst 20 (POST /investigations: 1 rps / burst 4), JSON access log without headers or caller address |
| `ApiFunction`, `WorkerFunction`, `AuthorizerFunction` | Lambda, `python3.14`, arm64, 512 MB | timeouts 15 s / 160 s / 5 s; one shared zip, three handlers |
| `ApiFunctionRole`, `WorkerFunctionRole`, `AuthorizerFunctionRole` | IAM | one role per function, inline policy, no managed policy |
| `WorkerFunctionEventInvokeConfig` | Lambda | `MaximumRetryAttempts: 0`, `MaximumEventAgeInSeconds: 60` |
| `ApiLogGroup`, `WorkerLogGroup`, `AuthorizerLogGroup`, `HttpApiAccessLogGroup` | CloudWatch Logs | explicit, 7-day retention, deleted with the stack |
| three `AWS::Lambda::Permission` | Lambda | generated by SAM: API Gateway may invoke the API function (two routes) and the authorizer |

Outside the stack (created by `scripts/mcp/01_bootstrap.py`): the artifacts
bucket `byb-artifacts-010928212265-us-east-1` and the SSM SecureString
`/before-you-buy/access-code`.

### Parameters

| Parameter | Default | Purpose |
| --- | --- | --- |
| `CodeS3Bucket`, `CodeS3Key` | none | Location of the zip built by `scripts/package.py` (content-addressed key) |
| `BedrockModelId` | `us.anthropic.claude-sonnet-5-5` | Inference profile the worker calls |
| `BedrockFoundationModelId` | `anthropic.claude-sonnet-5-5` | Foundation model that profile routes to; used only to build IAM resource ARNs. Change both together |
| `AllowedOrigin` | `*` | CORS origin. **Tighten to the Amplify origin once it exists** |
| `AccessCodeParameterName` | `/before-you-buy/access-code` | Name (never the value) of the SSM SecureString |
| `PythonRuntime` | `python3.14` | `python3.13`, `python3.14` or `python3.15` |
| `LogRetentionDays` | `7` | Retention of the four log groups |
| `WorkerReservedConcurrency` | `5` | Hard cap on concurrent investigations (0 to 10; 0 stops the worker) |

### Outputs (2026-11-14, `UPDATE_COMPLETE`)

| Output | Value |
| --- | --- |
| `ApiBaseUrl` | `https://3t4hod912l.execute-api.us-east-1.amazonaws.com` |
| `HttpApiId` | `3t4hod912l` |
| `DataBucketName` | `before-you-buy-databucket-brqny1fkd68i` |
| `ApiFunctionName` / `WorkerFunctionName` / `AuthorizerFunctionName` | `before-you-buy-api` / `before-you-buy-worker` / `before-you-buy-authorizer` |
| `AccessCodeParameterName` | `/before-you-buy/access-code` |
| `BedrockModelId` / `PythonRuntime` | `us.anthropic.claude-sonnet-5-5` / `python3.14` |
| `CodeArtifact` | `lambda/byb-backend-5cf91f80c5c1a2ce.zip` |
| `WorkerLogGroupName` / `ApiLogGroupName` / `AuthorizerLogGroupName` | `/aws/lambda/before-you-buy-worker` / `-api` / `-authorizer` |
| `AccessLogGroupName` | `/aws/vendedlogs/apigateway/before-you-buy-http-api` |

## Lifecycle rules, and where each is enforced

| Rule | Enforced by |
| --- | --- |
| Store the validated request before invoking the worker | `InvestigationApi._create`: conditional `PutObject` first, `Invoke` second |
| 202 only after the invocation was accepted | `_dispatch` requires `StatusCode == 202` from `Invoke`; otherwise the job is marked `FAILED / DISPATCH_FAILED` and the answer is 503 with a structured error |
| Same idempotency key gives the same job | job id = `inv_` + the first 32 hexadecimal characters of SHA-256 over a fixed namespace and the key; creation uses `If-None-Match: *`; a different body under the same key is 409 `IDEMPOTENCY_KEY_REUSED` |
| QUEUED -> RUNNING -> SUCCEEDED or FAILED only | `JobStore.update`: read, refuse terminal states, validate the transition, write with `If-Match` |
| Terminal results are immutable | code: `TerminalStateError`; IAM: results and traces can only be written with `If-None-Match` (create-once), job documents only with `If-Match` or `If-None-Match` |
| Duplicate delivery produces no second result | the worker claims the job by compare-and-swap and records its Lambda request id; a second delivery finds the job not QUEUED, logs `worker_duplicate_delivery` and returns |
| Deadline with a visible failure state | `deadline_at` = creation + 150 s. The worker stops 5 s before it and never writes SUCCEEDED after it. `GET` turns an overdue non-terminal job into `FAILED / DEADLINE_EXCEEDED` and persists that, so the failure is visible even if the worker died |
| Tool calls are allowlisted and schema-checked | `ToolRegistry.execute`: unknown names and invalid arguments are recorded as `REJECTED` steps and never executed |
| The model cannot skip the calculation | after the loop the worker checks that `compute_exposure` ran with the stored request's arguments; if not it runs it itself (`origin: "server"`) and the result uses that step |
| Bounded rounds, calls, tokens, retries, time | 6 tool rounds, 16 tool calls, `maxTokens` 4096 per call, 4 attempts per model call with jittered backoff that never sleeps past the deadline; SDK retries are off for Bedrock so attempts are counted once |

Each tool event (`seq, tool, origin, started_at, finished_at, status,
input_summary, result_summary`) is appended to `steps` when it completes, before
the next model call. Steps hold tool actions and results only, never model
reasoning. The full tool input and output, the model calls (latency, tokens,
request ids) and the visible transcript go to `traces/<id>.json`.

Failure codes written to a job in phase 1: `DISPATCH_FAILED`,
`DEADLINE_EXCEEDED`, `MODEL_THROTTLED`, `MODEL_ERROR`, `MODEL_OUTPUT_TRUNCATED`,
`MODEL_STOPPED`, `MODEL_EMPTY_RESPONSE`, `TOOL_ROUNDS_EXCEEDED`,
`TOOL_CALLS_EXCEEDED`, `INTERNAL_ERROR`.

## Decisions

- **Worker retries: 0, with an idempotent worker anyway.** Lambda's default
  for asynchronous invocation is two retries, the first after one minute. A
  retry would start at least 60 s into a 150 s deadline and pay for the Bedrock
  calls a second time, for a job the user can simply resubmit. The worker is
  still idempotent because asynchronous delivery is at-least-once whatever the
  retry setting: the claim is a compare-and-swap, and both result and trace are
  write-once. `MaximumEventAgeInSeconds` is 60 so that an event throttled for a
  long time is dropped rather than run after the user has given up; the
  deadline rule then reports the job as failed.
- **No dead-letter queue or destination.** A lost event is already visible:
  the job stays QUEUED and becomes `FAILED / DEADLINE_EXCEEDED` at the next GET.
- **A duplicate POST re-dispatches while the job is still QUEUED.** If the
  first invocation was lost, the client's retry repairs it. If it was not, the
  second worker run is a logged no-op. That happened in all three live runs:
  about 90 ms in the last two, 1.8 s in the first (a cold start, before the
  clients were built at init).
- **A failed dispatch uses up the idempotency key.** The job is terminal
  (`DISPATCH_FAILED`), so the same key keeps answering 503. Retry with a new key.
- **Reserved concurrency of 5 on the worker** (parameter `WorkerReservedConcurrency`).
  It is the only hard bound on concurrent Bedrock conversations. API Gateway
  throttling is best effort
  (https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-throttling.html):
  with the route limit at 1 request per second and burst 4, 79 of 80 parallel
  requests passed, and 10 real investigations started at once. With the cap,
  the same burst ran five at a time (the other five waited about 3.7 s) and
  all ten succeeded. Events beyond the cap wait in Lambda's queue for at most
  60 s (`MaximumEventAgeInSeconds`); a job whose event is dropped is reported
  `FAILED / DEADLINE_EXCEEDED`. This account can reserve 10 at most: Lambda
  keeps 100 units unreserved and the pool was 110
  (https://docs.aws.amazon.com/lambda/latest/dg/configuration-concurrency.html);
  it is now 105. Setting the parameter to 0 stops the worker.
- **Versioning off on the data bucket.** A job document is rewritten several
  times per job; versions would only accumulate. Results and traces are
  write-once already.
- **Only `bedrock:InvokeModel`.** The worker uses `Converse`, not
  `ConverseStream`, so `InvokeModelWithResponseStream` is not granted.
- **Runtime `python3.14`.** The newest generally available runtime. `python3.15`
  is accepted too but is a public preview.
- **SDK clients are built during the init phase**, outside the handler. In the
  two cold worker runs measured, before and after that change, the handler
  duration went from 4,085 ms to 2,847 ms and the init duration from 82 ms to
  602 ms, with the same Bedrock latency (2.39 s) in both.
- **A model failure fails the job in phase 1.** The contracts written since
  then describe a deterministic fallback instead (`agent.mode`); that is
  phase 2 work.

## IAM

Three roles, one inline policy each, no managed policy, no permissions
boundary. Rendered policies, the wildcard scan and 36 policy simulations are in
the evidence file.

| Role | Allowed |
| --- | --- |
| API function | `logs:CreateLogStream`, `logs:PutLogEvents` on its own log group. `s3:GetObject` on `jobs/*` and `results/*`. `s3:PutObject` on `jobs/*` only when the request carries `If-None-Match` or `If-Match`. `s3:ListBucket` only for prefix `jobs/*`. `lambda:InvokeFunction` on the worker function only |
| Worker function | Logs as above. `s3:GetObject` on `jobs/*` and `snapshots/*`. `s3:PutObject` on `jobs/*` only with `If-Match`; on `results/*` and `traces/*` only with `If-None-Match`. `bedrock:InvokeModel` on the one inference profile, and on the foundation model in `us-east-1`, `us-east-2`, `us-west-2` only when called through that profile |
| Authorizer function | Logs as above. `ssm:GetParameter` on the one parameter |

Not granted to anyone: `s3:DeleteObject`, `s3:*`, `bedrock:*`, any write to
`snapshots/` or `policies/`, any read of `traces/` by the API, `kms:*`
(the parameter uses the AWS managed key `alias/aws/ssm`, which needs no extra
grant: proven by the live "match" decision of the authorizer).

Each trust policy lets `lambda.amazonaws.com` assume the role only for this
account (`aws:SourceAccount`) and this function (`aws:SourceArn`). A live probe
with throwaway resources confirmed that Lambda can still create and invoke a
function under such a trust policy.

### Every wildcard, stated

Identity policies contain **no `*` action and no `Resource: "*"`**. No
statement needed the exception "where AWS requires it". What remains:

| Where | Wildcard | Why |
| --- | --- | --- |
| Log statements | `log-group:/aws/lambda/<function>:*` | Log streams of the function's own group; `CreateLogStream` and `PutLogEvents` act on stream ARNs |
| S3 statements | `<bucket>/jobs/*`, `/results/*`, `/traces/*`, `/snapshots/*` | Every object under one prefix; object keys are not known in advance |
| `s3:ListBucket` condition | `s3:prefix` like `jobs/*` | Restricts listing to the jobs prefix |
| Trust policies | `aws:SourceArn` also matches `function:<name>:*` | Versions and aliases of the same function |
| Data bucket policy | `Effect: Deny`, `Principal: "*"`, `Action: "s3:*"` when `aws:SecureTransport` is false | A deny for everyone on everything is the purpose; it grants nothing |
| Lambda permissions (generated by SAM) | `execute-api` source ARNs `<api>/*/GET/investigations/*`, `<api>/*/POST/investigations`, `<api>/authorizers/*` | Any stage, the `{id}` path parameter, the API's authorizers. Principal is `apigateway.amazonaws.com` |

The foundation-model ARNs have an empty account field
(`arn:aws:bedrock:us-east-1::foundation-model/...`). That is how AWS names
them, not a wildcard. The three Regions are listed one by one.

## Facts checked, and how

| Question | Answer | Source | Checked live |
| --- | --- | --- | --- |
| Newest Python runtime accepted in `us-east-1` | `python3.14` is the newest generally available; `python3.15` is listed as a public preview | https://docs.aws.amazon.com/lambda/latest/dg/lambda-runtimes.html | Yes: `CreateFunction` + `Invoke` succeeded for both. `python3.14` reported Python 3.14.10 with boto3 1.42.97; `python3.15` reported Python 3.15.2 with boto3 1.43.119. The stack runs `python3.14` |
| HTTP API maximum integration timeout | 30 seconds | https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-quotas.html | The SAM property accepts 50 to 29,000 ms (default 5,000): https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/sam-property-function-httpapi.html. Configured 20,000 ms; `GetIntegrations` shows 20000. Measured integration latency of the 202: 147 to 152 ms |
| Lambda timeout, default and configured | Default 3 s, maximum 900 s | https://docs.aws.amazon.com/lambda/latest/dg/configuration-timeout.html | Configured and read back: API 15 s, worker 160 s, authorizer 5 s |
| Asynchronous invocation retries | Two retries by default (after 1 and 2 minutes); an event can be delivered more than once | https://docs.aws.amazon.com/lambda/latest/dg/invocation-async-error-handling.html | `GetFunctionEventInvokeConfig`: retries 0, maximum event age 60 s. Duplicate delivery was observed and was a no-op |
| S3 conditional writes | `If-None-Match: *` creates only if absent; `If-Match: <etag>` is a compare-and-swap; failures are 412 (or 409 for a concurrent conflict, to be retried). `s3:if-none-match` and `s3:if-match` are policy condition keys | https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-writes.html and https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-writes-enforce.html | Yes: the whole job lifecycle runs on them in the deployed stack, under roles that cannot write unconditionally (simulated: unconditional `PutObject` is denied for both roles) |
| IAM for a cross-Region inference profile | Allow `bedrock:InvokeModel` on the profile ARN and on the foundation model in each destination Region, the latter conditioned on `bedrock:InferenceProfileArn` | https://docs.aws.amazon.com/bedrock/latest/userguide/inference-profiles-prereq.html | Yes: the worker's two Converse calls per job succeed under exactly that policy |
| Converse request and response shape | `toolConfig`, `toolUse` / `toolResult` blocks, `stopReason`, `usage`, `metrics.latencyMs` | https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_Converse.html | Yes: see the trace in the evidence file |
| HTTP API Lambda authorizer | Simple responses (`isAuthorized`), identity sources; a request without the identity source gets 401 without invoking the function; results are cached per identity source value | https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-lambda-authorizer.html | Yes: 401 in under 0.11 s with no authorizer log line; 403 for a wrong token; cached answers observed |
| CORS preflight on an HTTP API | When CORS is configured, API Gateway answers preflight `OPTIONS` requests itself, even without an `OPTIONS` route (which is why the template has no `$default` route behind the authorizer) | https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-cors.html | Yes: 204 with the CORS headers and no token |

Also used: HTTP API access logging
(https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-logging.html),
`AWS::Serverless::HttpApi`
(https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/sam-resource-httpapi.html),
its Lambda authorizer
(https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/sam-property-httpapi-lambdaauthorizer.html),
Lambda execution roles
(https://docs.aws.amazon.com/lambda/latest/dg/lambda-intro-execution-role.html).

Two things learned from the live system rather than from the documentation:

- For an unknown id, S3 appears to answer "no such key" directly to the API
  function, whose `s3:ListBucket` grant is limited to the `jobs/` prefix. This
  is an inference: the code also handles the other possible answer (403, then
  a one-key listing to confirm) and logs `s3_missing_key_confirmed_by_listing`
  when it does, and that line never appeared in the two live runs made with
  the build that writes it. The 403 path is unit-tested only.
- API Gateway caches the authorizer's **denials** as well as its approvals for
  300 s per `Authorization` value. In the second live run, made within that
  window, the authorizer function was not invoked at all.

## Deploying

### Path A: CloudFormation change sets through the AWS MCP tool (used)

No SAM CLI, no AWS CLI, no local credentials. Step by step in
`scripts/deploy.md`; in short:

1. `python3 scripts/package.py` builds `dist/byb-backend-<sha16>.zip`.
2. `scripts/mcp/01_bootstrap.py` (once): artifacts bucket and access code.
3. Upload the zip and `infra/template.yaml` through presigned URLs.
4. `scripts/mcp/02_deploy.py`: `CreateChangeSet` with `TemplateURL`,
   `CAPABILITY_IAM` and `CAPABILITY_AUTO_EXPAND`; read the changes and the
   validation events; then `ExecuteChangeSet`.
5. `scripts/mcp/03_status.py`: status and outputs.
6. `scripts/e2e_smoke.sh`: end-to-end check.

### Path B: `sam deploy` (not executed: the SAM CLI is not installed here)

The template takes the code location as parameters instead of a local
`CodeUri`, so `sam build` and `sam package` are not needed. With credentials
for account `010928212265`:

    python3 scripts/package.py
    aws s3 cp dist/byb-backend-<sha16>.zip s3://byb-artifacts-010928212265-us-east-1/lambda/
    sam deploy \
      --template-file infra/template.yaml \
      --stack-name before-you-buy \
      --region us-east-1 \
      --capabilities CAPABILITY_IAM CAPABILITY_AUTO_EXPAND \
      --s3-bucket byb-artifacts-010928212265-us-east-1 \
      --parameter-overrides \
          CodeS3Bucket=byb-artifacts-010928212265-us-east-1 \
          CodeS3Key=lambda/byb-backend-<sha16>.zip \
      --no-fail-on-empty-changeset

`sam deploy` creates and executes a change set, which is what path A does by
hand. The artifacts bucket and the SSM parameter must exist first (path A,
step 2, or the console). This path is written from the documentation and has
not been run.

## Validation performed

| Layer | Tool | Result |
| --- | --- | --- |
| Template syntax and schema | cfn-lint 1.60.1 | No error, warning or informational finding. A deliberately broken copy was caught (E3034, E3002) |
| Security rules | cfn-guard (`guardpycfn`), AWS Guard Rules Registry 1.0.2, Well-Architected Security Pillar, on the **processed** template | 45 rules: 6 pass, 32 skipped (not applicable), 7 fail. See below |
| Service-side validation | CloudFormation change sets | Both change sets `CREATE_COMPLETE` / `AVAILABLE`; no validation event |
| IAM actions | iam-policy-autopilot baseline from the source code | The template grants only a subset of the generated baseline, plus the two log actions |
| IAM behaviour | `iam:SimulatePrincipalPolicy`, 36 cases | 36 of 36 as expected (13 allowed, 23 denied) |
| Code | 146 unit tests, `backend/tests/service` | All pass on Python 3.14.2 and 3.15.2. 14 deliberately injected defects were each caught by at least one test |
| The deployed system | `scripts/e2e_smoke.sh`, five runs | Runs 1 to 3: all checks pass. Runs 4 and 5, started seconds after a 50-request flood sent by `scripts/e2e_probe.sh`, got 429 from API Gateway on POST and stopped there. Not re-run since |
| Enforcement and concurrency | `scripts/e2e_probe.sh`, three runs | Injected instructions in the question did not change the calculation (6 of 6). A burst of 10 real investigations: all succeeded, before and after the concurrency cap |

The seven cfn-guard failures:

| Rule | Verdict |
| --- | --- |
| `S3_BUCKET_SSL_REQUESTS_ONLY` | False positive. The rule wants one exact literal statement; ours denies non-TLS requests on the named bucket ARNs. `GetBucketPolicy` output is in the evidence file |
| `CW_LOGGROUP_RETENTION_PERIOD_CHECK` | False positive. The rule wants a literal number; the template uses the `LogRetentionDays` parameter. Deployed value read back: 7 days on all four groups |
| `IAM_NO_INLINE_POLICY_CHECK` | Accepted. Inline policies keep each role's permissions next to the function, and nothing else may reuse them |
| `LAMBDA_INSIDE_VPC` | Accepted. The functions call only AWS service endpoints (S3, Lambda, Bedrock, SSM); a VPC would add NAT or interface endpoints and no isolation that matters here |
| `S3_BUCKET_VERSIONING_ENABLED` | Accepted. See "Decisions" |
| `S3_BUCKET_LOGGING_ENABLED` | Accepted for a three-day prototype. No server access log bucket |
| `CLOUDWATCH_LOG_GROUP_ENCRYPTED` | Accepted. Default encryption, no customer managed key; the logs hold no token, no prompt and no personal data |

## Gap to the contracts

`contracts/` was empty while this slice was built; schemas appeared afterwards
(read on 2026-11-14 around 23:30 UTC, `schema_version` 1.0.0; the
`contracts/api.md` they refer to did not exist yet). The phase-1 wire shapes
are deliberately isolated in a few functions (`read_idempotency_key`,
`parse_create_request`, `new_job`, `public_view`, `_accepted` in
`backend/api/handler.py`; `ToolEvent.to_step` in `backend/agents/tools.py`;
`error_response` in `backend/common/http.py`), so that aligning them does not
touch the lifecycle code. Known differences:

| Item | Phase 1 | `contracts/schemas` |
| --- | --- | --- |
| Create request | `persona_id`, `purchase {instrument_id, target_direct_weight}`, optional `policy_version`, `question`, `idempotency_key` | `persona_id`, `policy_id`, `policy_version`, `request` (a purchase request with `funding` and `original_words`, or an unresolved free-text request), `parent_investigation_id`; no other property |
| Idempotency key | Header `Idempotency-Key` or body field; 8 to 128 characters from `[A-Za-z0-9._:-]` | Stored on the job; 8 to 64 characters from `[A-Za-z0-9_-]`; the body schema has no such field, so it has to be the header |
| 202 body | `investigation_id, status, created_at, updated_at, deadline_at, replayed, poll {href, interval_ms}` | `schema_version, id, status, created_at, deadline_at, expires_at, poll {path, interval_ms}` |
| Job id | `inv_<32 hex>` | Pattern `^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$`: **an underscore is not allowed** |
| Job document | `investigation_id, status, created_at, updated_at, deadline_at, started_at, finished_at, request, steps, result, error` | 22 required members, among them `expires_at`, `policy_id`, `resolved_request`, `agent {mode, model_id, tool_rounds, note}`, `clarification`, `explanation[]`, `failure {code, message, retryable}`, `proposed_corrections` |
| Step | `seq, tool, origin (model/server), tool_use_id, started_at, finished_at, duration_ms, status (SUCCEEDED/FAILED/REJECTED), input_summary, result_summary, error` | `seq, tool, initiated_by (MODEL/SERVER), started_at, finished_at, status (RUNNING/OK/ERROR), input_summary, result_summary, evidence_ids` |
| Result | Placeholder object | `check_result.schema.json`, produced by the engine |
| Failure codes | See "Lifecycle rules" | `DEADLINE_EXCEEDED, WORKER_INVOCATION_FAILED, WORKER_ERROR, ENGINE_ERROR, DATA_UNAVAILABLE` |
| Error body | `{error: {code, message, request_id, ...}}` | `{error: {code, message, details: [{path, issue}], request_id}}` with a fixed list of codes |
| Range errors in a purchase | 400 from the API | Not a schema error: the engine reports `execution.status INVALID_REQUEST` |
| Model unavailable | Job fails with a `MODEL_*` code | `agent.mode: DETERMINISTIC_FALLBACK`, the server runs the checks and every statement is a template |

## Operating notes

- **Logs.** One JSON object per line. Worker events: `worker_claimed`,
  `bedrock_call`, `tool_event`, `worker_finished`, `worker_duplicate_delivery`.
  API events: `investigation_accepted`, `api_error`. Authorizer:
  `authorizer_decision` (decision and reason, never the token). Example filter:
  `{ $.event = "tool_event" }` on `/aws/lambda/before-you-buy-worker`. Keys
  that look like secrets are redacted and long strings are truncated before
  anything is written.
- **Errors from API Gateway have another shape.** 401 (no token), 403 (wrong
  token) and 429 (throttled) are answered by API Gateway as
  `{"message": "..."}`, not by the service's `{"error": {...}}` envelope. The
  frontend must handle both.
- **Access code.** See `scripts/deploy.md` for reading it once and for rotation.
  This is demo-grade access control, not user identity.
- **CORS.** `AllowedOrigin` is `*` until the Amplify origin is known. CORS is
  not authentication; the bearer code is.

## Limitations

- The tool's result is a placeholder, and the explanation is model-written
  text that phase 1 does not check against evidence records (the result says
  so: `verified_against_evidence: false`). No verdict is produced.
- Only the success path and the request-level rejections (401, 403, 400, 404,
  409, 429) were exercised live, plus duplicate delivery and a burst against
  the concurrency cap. Dispatch failure, deadline expiry, Bedrock throttling,
  unknown tools and round limits are covered by unit tests with fakes, not
  provoked in AWS. The server-run calculation (`origin: "server"`) never
  occurred live: the model called the tool correctly every time, even when the
  question told it not to.
- One model, `us.anthropic.claude-sonnet-5-5`, was run. Another model needs
  both Bedrock parameters changed and its own test.
- A Bedrock call already in flight at the deadline is not interrupted. The
  worker checks the remaining time before each call (it needs at least 3 s),
  the SDK read timeout is 60 s and the Lambda timeout of 160 s is the hard
  stop. GET reports the failure at the deadline whatever the worker is doing.
- If the deadline passes between writing the result and the final state
  change, the job ends FAILED and an orphan `results/<id>.json` remains. It is
  never served.
- `results/` objects do not expire while `jobs/` documents expire after three
  days, after which GET answers 404. The contracts' `expires_at` and 410 are
  not implemented. Irrelevant in practice: the account is deleted first.
- No alarm, no dashboard, no tracing, no dead-letter queue.
- Cold starts add 0.48 to 0.60 s of init per function (six cold starts measured).
- The `sam deploy` path was not run.

## Teardown

`scripts/deploy.md`, section 8. The data bucket is retained when the stack is
deleted; the artifacts bucket and the SSM parameter are outside the stack.
