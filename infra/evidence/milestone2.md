# Milestone 2 evidence: the minimal AWS vertical slice

> **Status when work was paused (2026-11-14, about 23:55 UTC).** Sections 1 to 14 are the
> evidence collected up to smoke run 3 and are unchanged. Later events are not folded in yet:
> the stack was updated once more at 23:49:25Z (reserved concurrency 5 on the worker, template
> SHA-256 prefix `9b1c94d4e07d8bc3`, same code zip), so the status, parameters, template hash
> and concurrency lines of sections 1 and 2 are those of 23:35Z; two smoke runs (4 and 5) were
> answered 429 right after a flood; the probe script ran three times. Raw outputs:
> `infra/evidence/raw/`. Summary and next steps: `work/PAUSE_CHECKPOINT.md`.

Pass criterion: one real request reaches Bedrock, executes a tool and writes a
result to S3 in the authorized team account, through API Gateway.

- Account `010928212265`, region `us-east-1`, stack `before-you-buy`.
- Collected on 2026-11-14 between 23:14 and 23:35 UTC. AWS-side facts were read
  with the AWS MCP tool (`call_boto3`); HTTP requests were made with `curl` by
  `scripts/e2e_smoke.sh`.
- Everything below is real output. Long lines are wrapped or trimmed where
  marked; nothing was edited to look better.
- Redaction: the access code, every `Authorization` header and every presigned
  URL are absent by construction (the smoke script never prints them). Section
  10 shows the checks that confirm it. Request ids, Lambda request ids and
  Bedrock request ids are not secrets and are kept.
- The tool's calculation is a **placeholder** in phase 1. The outputs say so.

Three end-to-end runs were made. Run 3 is the reference: it is the only one in
which all three functions of the final build were invoked fresh (see section 12
for runs 1 and 2).

| Run | Build | Investigation | Result |
| --- | --- | --- | --- |
| 1 | `byb-backend-0f6cd5afdd57c8b3` | `inv_fec9ad9165c0306d18a4f39470777374` | SUCCEEDED, 1 step |
| 2 | `byb-backend-5cf91f80c5c1a2ce` (final) | `inv_2e82a727867efaff5483a582721a6bdb` | SUCCEEDED, 1 step |
| 3 | `byb-backend-5cf91f80c5c1a2ce` (final) | `inv_54efc9f9ca2a5117105fe9b980c8dbef` | SUCCEEDED, 1 step |

## 1. Stack status and outputs

`cloudformation:DescribeStacks`, after run 3:

    StackName        before-you-buy
    StackStatus      UPDATE_COMPLETE
    CreationTime     2026-11-14T23:14:32.897Z
    LastUpdatedTime  2026-11-14T23:21:20.164Z
    Capabilities     CAPABILITY_IAM, CAPABILITY_AUTO_EXPAND

    Parameters
      CodeS3Bucket              byb-artifacts-010928212265-us-east-1
      CodeS3Key                 lambda/byb-backend-5cf91f80c5c1a2ce.zip
      BedrockModelId            us.anthropic.claude-sonnet-5-5
      BedrockFoundationModelId  anthropic.claude-sonnet-5-5
      AllowedOrigin             *
      AccessCodeParameterName   /before-you-buy/access-code
      PythonRuntime             python3.14
      LogRetentionDays          7

    Outputs
      ApiBaseUrl              https://3t4hod912l.execute-api.us-east-1.amazonaws.com
      HttpApiId               3t4hod912l
      DataBucketName          before-you-buy-databucket-brqny1fkd68i
      ApiFunctionName         before-you-buy-api
      WorkerFunctionName      before-you-buy-worker
      AuthorizerFunctionName  before-you-buy-authorizer
      AccessCodeParameterName /before-you-buy/access-code
      BedrockModelId          us.anthropic.claude-sonnet-5-5
      PythonRuntime           python3.14
      CodeArtifact            lambda/byb-backend-5cf91f80c5c1a2ce.zip
      WorkerLogGroupName      /aws/lambda/before-you-buy-worker
      ApiLogGroupName         /aws/lambda/before-you-buy-api
      AuthorizerLogGroupName  /aws/lambda/before-you-buy-authorizer
      AccessLogGroupName      /aws/vendedlogs/apigateway/before-you-buy-http-api

`cloudformation:ListStackResources` (18 resources):

    AWS::ApiGatewayV2::Api          HttpApi                                            CREATE_COMPLETE
    AWS::ApiGatewayV2::Stage        HttpApiApiGatewayDefaultStage                      CREATE_COMPLETE
    AWS::IAM::Role                  ApiFunctionRole                                    CREATE_COMPLETE
    AWS::IAM::Role                  AuthorizerFunctionRole                             CREATE_COMPLETE
    AWS::IAM::Role                  WorkerFunctionRole                                 CREATE_COMPLETE
    AWS::Lambda::EventInvokeConfig  WorkerFunctionEventInvokeConfig                    CREATE_COMPLETE
    AWS::Lambda::Function           ApiFunction                                        UPDATE_COMPLETE
    AWS::Lambda::Function           AuthorizerFunction                                 UPDATE_COMPLETE
    AWS::Lambda::Function           WorkerFunction                                     UPDATE_COMPLETE
    AWS::Lambda::Permission         ApiFunctionCreateInvestigationPermission           CREATE_COMPLETE
    AWS::Lambda::Permission         ApiFunctionGetInvestigationPermission              CREATE_COMPLETE
    AWS::Lambda::Permission         HttpApiAccessCodeAuthorizerAuthorizerPermission    CREATE_COMPLETE
    AWS::Logs::LogGroup             ApiLogGroup                                        CREATE_COMPLETE
    AWS::Logs::LogGroup             AuthorizerLogGroup                                 CREATE_COMPLETE
    AWS::Logs::LogGroup             HttpApiAccessLogGroup                              CREATE_COMPLETE
    AWS::Logs::LogGroup             WorkerLogGroup                                     CREATE_COMPLETE
    AWS::S3::Bucket                 DataBucket                                         CREATE_COMPLETE
    AWS::S3::BucketPolicy           DataBucketPolicy                                   CREATE_COMPLETE

Other stacks and functions in the Region were not touched: `DescribeStacks`
lists `before-you-buy UPDATE_COMPLETE` and `kiro-ide-browser CREATE_COMPLETE`;
`ListFunctions` lists the three functions above, the six `kiro-ide-browser-*`
functions and `WSConcurrencyCurtailer-DO-NOT-USE`. `iam:ListRoles` shows no
project role other than the three of this stack (the throwaway probe role was
deleted).

## 2. What is deployed is what is in the repository

    $ python3 scripts/package.py
      "s3_key": "lambda/byb-backend-5cf91f80c5c1a2ce.zip",
      "sha256": "5cf91f80c5c1a2ce018ecc9653e3c96c2ce83c11ca2045ec60c6c49cd450b990",
      "bytes": 96694,
      "file_count": 19
    $ openssl dgst -sha256 -binary dist/byb-backend-5cf91f80c5c1a2ce.zip | base64
    XPkfgMXBos4BjsyWU+PJbCzoPBHKIEXsYMbEnNRQuZA=
    $ shasum -a 256 infra/template.yaml
    e532ad55e3d0fd574f6cbf5e93488efc263772cfaf90f57cc945dcacde6cc885   (deployed from templates/template-e532ad55e3d0fd57.yaml)

`lambda:GetFunctionConfiguration`, after run 3:

| Function | Runtime | Arch | Handler | Timeout | Memory | State | CodeSha256 | Log format |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `before-you-buy-api` | python3.14 | arm64 | `backend.api.handler.handler` | 15 s | 512 MB | Active / Successful | `XPkfgMXBos4BjsyWU+PJbCzoPBHKIEXsYMbEnNRQuZA=` | Text |
| `before-you-buy-worker` | python3.14 | arm64 | `backend.worker.handler.handler` | 160 s | 512 MB | Active / Successful | `XPkfgMXBos4BjsyWU+PJbCzoPBHKIEXsYMbEnNRQuZA=` | Text |
| `before-you-buy-authorizer` | python3.14 | arm64 | `backend.api.authorizer.handler` | 5 s | 512 MB | Active / Successful | `XPkfgMXBos4BjsyWU+PJbCzoPBHKIEXsYMbEnNRQuZA=` | Text |

The three hashes equal the hash of the zip rebuilt from the working tree.

Environment variables (none is a secret; the access code is not among them):

    api         DATA_BUCKET, WORKER_FUNCTION_NAME=before-you-buy-worker, JOB_DEADLINE_SECONDS=150, LOG_LEVEL=INFO
    worker      DATA_BUCKET, BEDROCK_MODEL_ID=us.anthropic.claude-sonnet-5-5, MAX_TOOL_ROUNDS=6, MAX_TOOL_CALLS=16,
                BEDROCK_MAX_TOKENS=4096, CODE_ARTIFACT=lambda/byb-backend-5cf91f80c5c1a2ce.zip, LOG_LEVEL=INFO
    authorizer  ACCESS_CODE_PARAMETER_NAME=/before-you-buy/access-code, ACCESS_CODE_CACHE_SECONDS=60, LOG_LEVEL=INFO

    lambda:GetFunctionEventInvokeConfig (worker)  MaximumRetryAttempts=0  MaximumEventAgeInSeconds=60  no destination
    lambda:GetFunctionConcurrency (worker)        no reserved concurrency

API Gateway (`apigatewayv2:GetApi`, `GetRoutes`, `GetAuthorizers`,
`GetIntegrations`, `GetStages`):

    api           before-you-buy-http-api, HTTP, https://3t4hod912l.execute-api.us-east-1.amazonaws.com
    routes        GET /investigations/{id}   AuthorizationType=CUSTOM
                  POST /investigations       AuthorizationType=CUSTOM
    authorizer    AccessCodeAuthorizer, REQUEST, payload 2.0, EnableSimpleResponses=true,
                  IdentitySource=$request.header.Authorization, AuthorizerResultTtlInSeconds=300
    integrations  AWS_PROXY, payload 2.0, TimeoutInMillis=20000 (both routes)
    stage         $default, AutoDeploy=true, default throttle rate 10 / burst 20,
                  POST /investigations throttle rate 1 / burst 4
    cors          AllowOrigins=["*"], AllowMethods=["GET","POST","OPTIONS"],
                  AllowHeaders=["authorization","content-type","idempotency-key"], MaxAge=600
    access log    {"requestId","requestTime","routeKey","status","responseLatencyMs","integrationLatencyMs",
                  "integrationStatus","authorizerError","errorMessage"}   (no header, no caller address)

`logs:DescribeLogGroups`: `retentionInDays` is 7 on `/aws/lambda/before-you-buy-api`,
`-worker`, `-authorizer` and `/aws/vendedlogs/apigateway/before-you-buy-http-api`.

## 3. Run 3: the request, from 401 to SUCCEEDED

Command (the second argument is a mode-600 file outside the repository):

    scripts/e2e_smoke.sh https://3t4hod912l.execute-api.us-east-1.amazonaws.com /tmp/byb-e2e/code

Exit status 0. Complete output:

```text
== API https://3t4hod912l.execute-api.us-east-1.amazonaws.com   idempotency key e2e-20261114T232959Z-15628
== 1. authentication
PASS  POST without a token -> HTTP 401 in 0.105742s
      {"message":"Unauthorized"}
PASS  GET without a token -> HTTP 401 in 0.094190s
      {"message":"Unauthorized"}
PASS  POST with a wrong token -> HTTP 403 in 0.907820s
      {"message":"Forbidden"}
== 2. CORS preflight (no token)
PASS  OPTIONS /investigations -> HTTP 204 in 0.105041s
      access-control-allow-origin: *
      access-control-allow-methods: GET,OPTIONS,POST
      access-control-allow-headers: authorization,content-type,idempotency-key
      access-control-max-age: 600
      CORS headers on the 401: 1 access-control-allow-origin header(s)
== 3. validation
PASS  POST with an invalid body -> HTTP 400 in 0.876577s
      {"error":{"code":"INVALID_REQUEST","message":"purchase.target_direct_weight must be between 0 and 1 (a portfolio fraction, 10% is 0.10).","request_id":"G2pEDhvWoAMEcqA="}}
PASS  GET an unknown investigation -> HTTP 404 in 0.206161s
      {"error":{"code":"INVESTIGATION_NOT_FOUND","message":"The service has no record of this investigation.","request_id":"G2pEMidRoAMEJJA="}}
== 4. create (202 only after the worker invocation was accepted)
PASS  POST /investigations -> HTTP 202 in 0.252343s
      {"investigation_id":"inv_54efc9f9ca2a5117105fe9b980c8dbef","status":"QUEUED","created_at":"2026-11-14T23:29:43.442Z","updated_at":"2026-11-14T23:29:43.442Z","deadline_at":"2026-11-14T23:32:13.442Z","replayed":false,"poll":{"href":"/investigations/inv_54efc9f9ca2a5117105fe9b980c8dbef","interval_ms":1500}}
      location: /investigations/inv_54efc9f9ca2a5117105fe9b980c8dbef
== 5. idempotency
PASS  duplicate POST (same key, same body) -> HTTP 202 in 0.306998s
      {"investigation_id":"inv_54efc9f9ca2a5117105fe9b980c8dbef","status":"QUEUED","created_at":"2026-11-14T23:29:43.442Z","updated_at":"2026-11-14T23:29:43.442Z","deadline_at":"2026-11-14T23:32:13.442Z","replayed":true,"poll":{"href":"/investigations/inv_54efc9f9ca2a5117105fe9b980c8dbef","interval_ms":1500}}
PASS  same investigation id returned (inv_54efc9f9ca2a5117105fe9b980c8dbef)
PASS  same key, different body -> HTTP 409 in 0.238454s
      {"error":{"code":"IDEMPOTENCY_KEY_REUSED","message":"This idempotency key was already used with a different request.","request_id":"G2pEUiO0IAMEcVg=","investigation_id":"inv_54efc9f9ca2a5117105fe9b980c8dbef"}}
== 6. poll until terminal
      t+1s status=RUNNING steps=0
      t+3s status=SUCCEEDED steps=1
PASS  investigation SUCCEEDED
== 7. final job document
{
  "investigation_id": "inv_54efc9f9ca2a5117105fe9b980c8dbef",
  "status": "SUCCEEDED",
  "created_at": "2026-11-14T23:29:43.442Z",
  "started_at": "2026-11-14T23:29:43.756Z",
  "finished_at": "2026-11-14T23:29:46.549Z",
  "deadline_at": "2026-11-14T23:32:13.442Z",
  "request": {
    "persona_id": "robert",
    "policy_version": null,
    "purchase": {
      "instrument_id": "NVDA",
      "target_direct_weight": 0.25
    },
    "question": "What is my exposure to NVDA after this purchase?"
  },
  "steps": [
    {
      "duration_ms": 0,
      "error": null,
      "finished_at": "2026-11-14T23:29:44.648Z",
      "input_summary": "instrument_id=NVDA, target_direct_weight=0.25",
      "origin": "model",
      "result_summary": "PLACEHOLDER result: direct_weight=0.25 (25.0% of the portfolio); indirect exposure not computed (unknown, not zero)",
      "seq": 1,
      "started_at": "2026-11-14T23:29:44.648Z",
      "status": "SUCCEEDED",
      "tool": "compute_exposure",
      "tool_use_id": "tooluse_Hxes694RwXWak72MBA56ux"
    }
  ],
  "error": null,
  "result": {
    "placeholder": true,
    "exposure": {
      "calculation_version": "phase1-placeholder-1",
      "coverage": "NOT_COMPUTED",
      "direct_weight": 0.25,
      "direct_weight_percent": 25.0,
      "indirect_weight": null,
      "instrument_id": "NVDA",
      "notes": [
        "PLACEHOLDER: this result repeats the requested final direct weight and nothing else.",
        "Indirect exposure through funds was not computed. It is unknown, not zero.",
        "No portfolio, holdings or rule data was read. This is not a verdict."
      ],
      "placeholder": true,
      "total_exposure_lower_bound": 0.25,
      "total_exposure_upper_bound": null,
      "unit": "portfolio_fraction"
    },
    "exposure_source": {
      "origin": "model",
      "step_seq": 1,
      "tool": "compute_exposure"
    },
    "explanation": {
      "author": "model",
      "model_id": "us.anthropic.claude-sonnet-5-5",
      "note": "Model-written text. Phase 1 does not check its statements against evidence records.",
      "prompt_version": "investigator-phase1-1",
      "text": "This result is a placeholder (version phase1-placeholder-1). It only repeats the direct weight you asked for. It didn't read any portfolio, holdings or rule data.\n\nThe direct NVDA weight is 0.25 (25.0%). Indirect exposure through funds was not computed, so it is unknown, not zero. The total exposure lower bound is 0.25. The upper bound is null, so it is unknown. Coverage is reported as NOT_COMPUTED.\n\nSo the tool can't tell you your full NVDA exposure after this purchase. It only shows that the total is at least 0.25. This is not a verdict.",
      "verified_against_evidence": false
    },
    "usage": {
      "bedrock_latency_ms": 2455,
      "input_tokens": 2380,
      "model_attempts": 2,
      "model_calls": 2,
      "model_wall_ms": 2506,
      "output_tokens": 288,
      "total_tokens": 2668
    },
    "trace_key": "traces/inv_54efc9f9ca2a5117105fe9b980c8dbef.json"
  }
}
PASS  GET the finished investigation -> HTTP 200 in 0.183423s
== 0 check(s) failed
```

The local clock was about 16 s ahead of AWS (the idempotency key carries the
local time 23:29:59Z; the job was created at 23:29:43Z by the Lambda clock).
All timestamps below are AWS timestamps.

What this shows:

- **401 without a token**, on both routes, in about 0.1 s, answered by API
  Gateway without invoking the authorizer.
- **403 with a wrong token**, decided by the authorizer function.
- CORS preflight answered **without a token** (204), and CORS headers present
  on a 401.
- **400** for an invalid body and **404** for an unknown id, in the service's
  error envelope.
- **202** in 0.25 s with `status: QUEUED` and a `location` header.
- The same id for a duplicate POST (`replayed: true`), **409** for the same key
  with another body.
- The job polled to **SUCCEEDED** with one real step: tool `compute_exposure`,
  `origin: model` (the model chose the call), `tool_use_id` issued by Bedrock.
- A **model-produced message** (`result.explanation.text`). It states that the
  result is a placeholder, repeats the tool's numbers and does not present
  unknown indirect exposure as zero.

## 4. S3 objects written

`s3:ListObjectsV2` on `before-you-buy-databucket-brqny1fkd68i` (whole bucket):

    jobs/inv_2e82a727867efaff5483a582721a6bdb.json      1309 bytes  2026-11-14T23:22:14+00:00
    jobs/inv_54efc9f9ca2a5117105fe9b980c8dbef.json      1309 bytes  2026-11-14T23:29:47+00:00
    jobs/inv_fec9ad9165c0306d18a4f39470777374.json      1309 bytes  2026-11-14T23:18:24+00:00
    results/inv_2e82a727867efaff5483a582721a6bdb.json   1968 bytes  2026-11-14T23:22:13+00:00
    results/inv_54efc9f9ca2a5117105fe9b980c8dbef.json   1986 bytes  2026-11-14T23:29:47+00:00
    results/inv_fec9ad9165c0306d18a4f39470777374.json   1962 bytes  2026-11-14T23:18:24+00:00
    traces/inv_2e82a727867efaff5483a582721a6bdb.json    4329 bytes  2026-11-14T23:22:13+00:00
    traces/inv_54efc9f9ca2a5117105fe9b980c8dbef.json    4347 bytes  2026-11-14T23:29:47+00:00
    traces/inv_fec9ad9165c0306d18a4f39470777374.json    4325 bytes  2026-11-14T23:18:24+00:00

Three investigations, one job document, one result and one trace each. Each
duplicate POST and each duplicate worker delivery left no extra object.

The stored job document of run 2, raw (`s3:GetObject`), showing the internal
fields the public view leaves out:

```json
{"attempt":{"claimed_at":"2026-11-14T23:22:10.339Z","lambda_request_id":"06dacfee-629b-41a1-93c0-9becde140ba1"},"created_at":"2026-11-14T23:22:09.275Z","created_by_request_id":"G2n9Rg3IIAMEcQw=","deadline_at":"2026-11-14T23:24:39.275Z","error":null,"finished_at":"2026-11-14T23:22:13.045Z","id":"inv_2e82a727867efaff5483a582721a6bdb","kind":"investigation","request":{"persona_id":"robert","policy_version":null,"purchase":{"instrument_id":"NVDA","target_direct_weight":0.25},"question":"What is my exposure to NVDA after this purchase?"},"request_hash":"7f18902beaeb40bec6f165dae8386c2445ee86768d17cff0bde4d8db1d55a76c","result_key":"results/inv_2e82a727867efaff5483a582721a6bdb.json","schema_version":1,"started_at":"2026-11-14T23:22:10.339Z","status":"SUCCEEDED","steps":[{"duration_ms":0,"error":null,"finished_at":"2026-11-14T23:22:11.216Z","input_summary":"instrument_id=NVDA, target_direct_weight=0.25","origin":"model","result_summary":"PLACEHOLDER result: direct_weight=0.25 (25.0% of the portfolio); indirect exposure not computed (unknown, not zero)","seq":1,"started_at":"2026-11-14T23:22:11.216Z","status":"SUCCEEDED","tool":"compute_exposure","tool_use_id":"tooluse_XRAGOouCPVmJFCPyItLKCQ"}],"trace_key":"traces/inv_2e82a727867efaff5483a582721a6bdb.json","updated_at":"2026-11-14T23:22:13.046Z"}
```

## 5. Bedrock usage and latency, from the trace

`s3:GetObject traces/inv_54efc9f9ca2a5117105fe9b980c8dbef.json` (run 3),
transcript omitted:

```json
{
  "outcome": "SUCCEEDED",
  "model": {
    "model_id": "us.anthropic.claude-sonnet-5-5",
    "prompt_version": "investigator-phase1-1",
    "system_prompt_sha256": "1c1750a981c94e03b0ebe4140621eb88d996d3cabc00160474ec34902953759d",
    "limits": {"max_tokens": 4096, "max_tool_calls": 16, "max_tool_rounds": 6},
    "tool_rounds_used": 1
  },
  "model_calls": [
    {"seq": 1, "stop_reason": "tool_use", "attempts": 1, "retries": [], "bedrock_latency_ms": 771, "wall_ms": 812,
     "request_id": "1c05e130-3d6c-4878-8217-76f28f7ed814",
     "usage": {"input_tokens": 1033, "output_tokens": 86, "total_tokens": 1119, "cache_read_input_tokens": 0, "cache_write_input_tokens": 0}},
    {"seq": 2, "stop_reason": "end_turn", "attempts": 1, "retries": [], "bedrock_latency_ms": 1684, "wall_ms": 1694,
     "request_id": "3309c5d8-7745-48c7-a5f2-0ef354c6e64a",
     "usage": {"input_tokens": 1347, "output_tokens": 202, "total_tokens": 1549, "cache_read_input_tokens": 0, "cache_write_input_tokens": 0}}
  ],
  "usage_totals": {"model_calls": 2, "model_attempts": 2, "input_tokens": 2380, "output_tokens": 288, "total_tokens": 2668,
                   "bedrock_latency_ms": 2455, "model_wall_ms": 2506},
  "timing": {"job_created_at": "2026-11-14T23:29:43.442Z", "worker_started_at": "2026-11-14T23:29:43.835Z",
             "worker_elapsed_ms": 2623, "job_deadline_at": "2026-11-14T23:32:13.442Z"},
  "runtime": {"function_name": "before-you-buy-worker", "function_version": "$LATEST", "python_version": "3.14.10",
              "boto3_version": "1.42.97", "memory_limit_mb": 512,
              "code_artifact": "lambda/byb-backend-5cf91f80c5c1a2ce.zip",
              "lambda_request_id": "7c27650e-e7da-4b90-a9f2-45f768da6bb2"}
}
```

Transcript shape in the same trace: `user: text`, `assistant: toolUse`,
`user: toolResult`, `assistant: text`. Two Converse calls, no retry, no
throttling. The three runs used 2,657, 2,664 and 2,668 tokens.

## 6. CloudWatch Logs

### The worker's tool event

`logs:FilterLogEvents`, log group `/aws/lambda/before-you-buy-worker`,
`filterPattern = { $.event = "tool_event" }`, start time 23:29:30Z. One event:

```json
{"ts":"2026-11-14T23:29:44Z","level":"INFO","event":"tool_event","component":"worker","job_id":"inv_54efc9f9ca2a5117105fe9b980c8dbef","lambda_request_id":"7c27650e-e7da-4b90-a9f2-45f768da6bb2","seq":1,"tool":"compute_exposure","origin":"model","status":"SUCCEEDED","duration_ms":0,"input_summary":"instrument_id=NVDA, target_direct_weight=0.25","result_summary":"PLACEHOLDER result: direct_weight=0.25 (25.0% of the portfolio); indirect exposure not computed (unknown, not zero)","error_code":null}
```

### The worker run, in order

Same log group, no filter, start time 23:29:30Z (13 events; the `tool_event`
line is shown above and shortened here):

```text
23:29:43.633Z START RequestId: 7c27650e-e7da-4b90-a9f2-45f768da6bb2 Version: $LATEST
23:29:43.835Z {"ts":"2026-11-14T23:29:43Z","level":"INFO","event":"worker_claimed","component":"worker","job_id":"inv_54efc9f9ca2a5117105fe9b980c8dbef","lambda_request_id":"7c27650e-e7da-4b90-a9f2-45f768da6bb2","deadline_at":"2026-11-14T23:32:13.442Z","model_id":"us.anthropic.claude-sonnet-5-5"}
23:29:44.160Z INIT_START Runtime Version: python:3.14.mainline.v118  (second execution environment, for the duplicate below)
23:29:44.647Z {"ts":"2026-11-14T23:29:44Z","level":"INFO","event":"bedrock_call","component":"worker","job_id":"inv_54efc9f9ca2a5117105fe9b980c8dbef","lambda_request_id":"7c27650e-e7da-4b90-a9f2-45f768da6bb2","seq":1,"stop_reason":"tool_use","attempts":1,"input_tokens":1033,"output_tokens":86,"bedrock_latency_ms":771,"wall_ms":812}
23:29:44.723Z START RequestId: 3387e5e2-9fa5-4a58-8e7c-c227e36fe90f Version: $LATEST
23:29:44.726Z {"event":"tool_event", ... "seq":1,"tool":"compute_exposure","origin":"model","status":"SUCCEEDED", ...}
23:29:44.812Z {"ts":"2026-11-14T23:29:44Z","level":"INFO","event":"worker_duplicate_delivery","component":"worker","job_id":"inv_54efc9f9ca2a5117105fe9b980c8dbef","lambda_request_id":"3387e5e2-9fa5-4a58-8e7c-c227e36fe90f","status":"RUNNING"}
23:29:44.815Z END RequestId: 3387e5e2-9fa5-4a58-8e7c-c227e36fe90f
23:29:44.815Z REPORT RequestId: 3387e5e2-9fa5-4a58-8e7c-c227e36fe90f  Duration: 91.45 ms  Billed Duration: 651 ms  Memory Size: 512 MB  Max Memory Used: 99 MB  Init Duration: 559.17 ms
23:29:46.420Z {"ts":"2026-11-14T23:29:46Z","level":"INFO","event":"bedrock_call","component":"worker","job_id":"inv_54efc9f9ca2a5117105fe9b980c8dbef","lambda_request_id":"7c27650e-e7da-4b90-a9f2-45f768da6bb2","seq":2,"stop_reason":"end_turn","attempts":1,"input_tokens":1347,"output_tokens":202,"bedrock_latency_ms":1684,"wall_ms":1694}
23:29:46.591Z {"ts":"2026-11-14T23:29:46Z","level":"INFO","event":"worker_finished","component":"worker","job_id":"inv_54efc9f9ca2a5117105fe9b980c8dbef","lambda_request_id":"7c27650e-e7da-4b90-a9f2-45f768da6bb2","status":"SUCCEEDED","steps":1,"elapsed_ms":2756,"model_calls":2,"model_attempts":2,"input_tokens":2380,"output_tokens":288,"total_tokens":2668,"bedrock_latency_ms":2455,"model_wall_ms":2506}
23:29:46.593Z END RequestId: 7c27650e-e7da-4b90-a9f2-45f768da6bb2
23:29:46.593Z REPORT RequestId: 7c27650e-e7da-4b90-a9f2-45f768da6bb2  Duration: 2959.01 ms  Billed Duration: 2960 ms  Memory Size: 512 MB  Max Memory Used: 102 MB
```

**Duplicate delivery, live.** The smoke test's duplicate POST arrived while the
job was still QUEUED, so the API dispatched the worker a second time (by
design). The second invocation (`3387e5e2…`) found the job RUNNING, logged
`worker_duplicate_delivery` and returned in 91 ms. No second Bedrock call, no
second step, no second result (section 4).

### The authorizer's decisions

Log group `/aws/lambda/before-you-buy-authorizer`, start time 23:29:30Z (all 9
events; neither line contains the token):

```text
23:29:41.262Z INIT_START Runtime Version: python:3.14.mainline.v118
23:29:41.820Z START RequestId: 20c6809a-d746-4f05-915e-9ec913b54772 Version: $LATEST
23:29:41.913Z {"ts":"2026-11-14T23:29:41Z","level":"INFO","event":"authorizer_decision","component":"authorizer","request_id":"G2pD3gesIAMEJuA=","authorized":false,"reason":"mismatch","route":"POST /investigations"}
23:29:41.915Z END RequestId: 20c6809a-d746-4f05-915e-9ec913b54772
23:29:41.915Z REPORT RequestId: 20c6809a-d746-4f05-915e-9ec913b54772  Duration: 94.14 ms  Billed Duration: 649 ms  Memory Size: 512 MB  Max Memory Used: 96 MB  Init Duration: 554.32 ms
23:29:42.340Z START RequestId: acac4233-5dad-4723-a981-c5da268940e3 Version: $LATEST
23:29:42.341Z {"ts":"2026-11-14T23:29:42Z","level":"INFO","event":"authorizer_decision","component":"authorizer","request_id":"G2pEDhvWoAMEcqA=","authorized":true,"reason":"match","route":"POST /investigations"}
23:29:42.343Z END RequestId: acac4233-5dad-4723-a981-c5da268940e3
23:29:42.343Z REPORT RequestId: acac4233-5dad-4723-a981-c5da268940e3  Duration: 2.08 ms  Billed Duration: 3 ms  Memory Size: 512 MB  Max Memory Used: 96 MB
```

Two invocations for fourteen requests: the three requests without a token
never reached the function, and after the first "match" API Gateway reused the
cached answer for the same header value.

### The API access log

Log group `/aws/vendedlogs/apigateway/before-you-buy-http-api`, start time
23:29:30Z (all 14 events, fields reordered into columns):

```text
time          route                     status  responseLatencyMs  integrationLatencyMs  authorizerError  errorMessage
23:29:40.870Z POST /investigations      401     0                  -                     -                Unauthorized
23:29:40.984Z GET /investigations/{id}  401     0                  -                     -                Unauthorized
23:29:41.095Z POST /investigations      403     810                -                     Forbidden        Forbidden
23:29:42.032Z - (OPTIONS preflight)     204     5                  0                     -                -
23:29:42.154Z GET /investigations/{id}  401     0                  -                     -                Unauthorized
23:29:42.288Z POST /investigations      400     764                716                   -                -
23:29:43.176Z GET /investigations/{id}  404     108                103                   -                -
23:29:43.412Z POST /investigations      202     153                147                   -                -
23:29:43.680Z POST /investigations      202     206                200                   -                -
23:29:43.994Z POST /investigations      409     144                139                   -                -
23:29:44.260Z GET /investigations/{id}  200     47                 41                    -                -
23:29:45.447Z GET /investigations/{id}  200     48                 43                    -                -
23:29:46.635Z GET /investigations/{id}  200     97                 92                    -                -
23:29:46.858Z GET /investigations/{id}  200     87                 81                    -                -
```

The raw line of the 202:

```json
{"requestId":"G2pEPiBjIAMEcRQ=","requestTime":"14/Nov/2026:23:29:43 +0000","routeKey":"POST /investigations","status":"202","responseLatencyMs":"153","integrationLatencyMs":"147","integrationStatus":"200","authorizerError":"-","errorMessage":"-"}
```

The API function's own lines for the same request:

```text
23:29:43.572Z {"ts":"2026-11-14T23:29:43Z","level":"INFO","event":"investigation_accepted","component":"api","request_id":"G2pEPiBjIAMEcRQ=","route":"POST /investigations","job_id":"inv_54efc9f9ca2a5117105fe9b980c8dbef","created":true,"deadline_at":"2026-11-14T23:32:13.442Z"}
23:29:43.574Z REPORT RequestId: 067c3f21-9a4c-4ccc-9447-5c3a2782217e  Duration: 132.79 ms  Billed Duration: 133 ms  Memory Size: 512 MB  Max Memory Used: 100 MB
```

## 7. Durations against the limits

| Measure | Value | Limit |
| --- | --- | --- |
| POST /investigations, client side (curl) | 0.252 s (run 3), 0.287 s (run 2), 0.536 s (run 1) | - |
| POST /investigations, API Gateway `integrationLatencyMs` for the 202 | 147 ms (run 3), 152 ms (run 2), 151 ms (run 1) | integration timeout 20,000 ms configured; 30 s is the HTTP API maximum |
| Slowest integration seen on any request | 1,819 ms (run 1, first request, cold start of the first build); 716 ms with the final build (cold start) | same |
| API function duration for the 202 | 132.79 ms | function timeout 15 s |
| Worker duration (Lambda `REPORT`) | 2,959.01 ms warm (run 3); 2,847.06 ms + 602.25 ms init (run 2, cold); 4,084.85 ms + 81.54 ms init (run 1, cold, first build) | function timeout 160 s; job deadline 150 s |
| Worker memory | 99 to 102 MB used | 512 MB |
| Bedrock latency per job (two calls) | 2,455 ms, 2,394 ms, 2,388 ms | - |
| Job created to job finished | 3.1 s (run 3: 23:29:43.442 to 23:29:46.549) | deadline 150 s |
| Authorizer | 94.14 ms + 554.32 ms init when cold, 2.08 ms warm | function timeout 5 s |

The API call does not wait for the model: it returns in about 150 ms while the
worker takes about 3 s. It is two orders of magnitude inside the integration
limit.

## 8. The bucket is private

`s3:GetPublicAccessBlock` on `before-you-buy-databucket-brqny1fkd68i`:

```json
{"BlockPublicAcls": true, "IgnorePublicAcls": true, "BlockPublicPolicy": true, "RestrictPublicBuckets": true}
```

    s3:GetBucketPolicyStatus       {"IsPublic": false}
    s3:GetBucketEncryption         SSEAlgorithm AES256, BucketKeyEnabled false, BlockedEncryptionTypes ["SSE-C"]
    s3:GetBucketOwnershipControls  BucketOwnerEnforced
    s3:GetBucketVersioning         not enabled (never configured)
    s3:GetBucketLifecycleConfiguration
        ExpireJobs               Enabled  prefix jobs/    expire after 3 days
        ExpireTraces             Enabled  prefix traces/  expire after 3 days
        AbortIncompleteUploads   Enabled  whole bucket    abort after 1 day

`s3:GetBucketPolicy`:

```json
[{"Sid": "DenyInsecureTransport", "Effect": "Deny", "Principal": "*", "Action": "s3:*",
  "Resource": ["arn:aws:s3:::before-you-buy-databucket-brqny1fkd68i", "arn:aws:s3:::before-you-buy-databucket-brqny1fkd68i/*"],
  "Condition": {"Bool": {"aws:SecureTransport": "false"}}}]
```

The artifacts bucket `byb-artifacts-010928212265-us-east-1` has the same four
flags set to true.

## 9. IAM as deployed

`iam:GetRolePolicy` for the single inline policy of each role
(`iam:ListAttachedRolePolicies` returns nothing for all three). ARNs are shown
without the `arn:aws:` prefix. `<bucket>` stands for
`before-you-buy-databucket-brqny1fkd68i`.

API function role `before-you-buy-ApiFunctionRole-0QYxnENSyH6F`:

```text
WriteOwnLogs                   logs:CreateLogStream, logs:PutLogEvents
                               ON logs:us-east-1:010928212265:log-group:/aws/lambda/before-you-buy-api:*
ReadJobsAndResults             s3:GetObject ON s3:::<bucket>/jobs/* | s3:::<bucket>/results/*
CreateJobOnlyIfAbsent          s3:PutObject ON s3:::<bucket>/jobs/*   IF {"Null":{"s3:if-none-match":"false"}}
UpdateJobOnlyByCompareAndSwap  s3:PutObject ON s3:::<bucket>/jobs/*   IF {"Null":{"s3:if-match":"false"}}
ListJobsPrefixOnly             s3:ListBucket ON s3:::<bucket>         IF {"StringLike":{"s3:prefix":"jobs/*"}}
DispatchToWorkerOnly           lambda:InvokeFunction ON lambda:us-east-1:010928212265:function:before-you-buy-worker
```

Worker function role `before-you-buy-WorkerFunctionRole-1d6beAx4kZ6i`:

```text
WriteOwnLogs                   logs:CreateLogStream, logs:PutLogEvents
                               ON logs:us-east-1:010928212265:log-group:/aws/lambda/before-you-buy-worker:*
ReadJobsAndSnapshots           s3:GetObject ON s3:::<bucket>/jobs/* | s3:::<bucket>/snapshots/*
UpdateJobOnlyByCompareAndSwap  s3:PutObject ON s3:::<bucket>/jobs/*   IF {"Null":{"s3:if-match":"false"}}
WriteResultAndTraceOnce        s3:PutObject ON s3:::<bucket>/results/* | s3:::<bucket>/traces/*
                               IF {"Null":{"s3:if-none-match":"false"}}
ConverseThroughInferenceProfile
                               bedrock:InvokeModel ON bedrock:us-east-1:010928212265:inference-profile/us.anthropic.claude-sonnet-5-5
RoutedFoundationModelsOnlyViaThatProfile
                               bedrock:InvokeModel ON bedrock:us-east-1::foundation-model/anthropic.claude-sonnet-5-5
                                                    | bedrock:us-east-2::foundation-model/anthropic.claude-sonnet-5-5
                                                    | bedrock:us-west-2::foundation-model/anthropic.claude-sonnet-5-5
                               IF {"StringEquals":{"bedrock:InferenceProfileArn":
                                   "arn:aws:bedrock:us-east-1:010928212265:inference-profile/us.anthropic.claude-sonnet-5-5"}}
```

Authorizer function role `before-you-buy-AuthorizerFunctionRole-RmqbX7uNOCe4`:

```text
WriteOwnLogs        logs:CreateLogStream, logs:PutLogEvents
                    ON logs:us-east-1:010928212265:log-group:/aws/lambda/before-you-buy-authorizer:*
ReadAccessCodeOnly  ssm:GetParameter ON ssm:us-east-1:010928212265:parameter/before-you-buy/access-code
```

Trust policy of each role (shown for the API function; the other two differ
only by the function name):

```text
Principal {"Service": "lambda.amazonaws.com"}  Action sts:AssumeRole
IF {"StringEquals":{"aws:SourceAccount":"010928212265"},
    "ArnLike":{"aws:SourceArn":["arn:aws:lambda:us-east-1:010928212265:function:before-you-buy-api",
                                "arn:aws:lambda:us-east-1:010928212265:function:before-you-buy-api:*"]}}
```

Lambda resource-based policies (`lambda:GetPolicy`), generated by SAM:

```text
before-you-buy-api         apigateway.amazonaws.com lambda:InvokeFunction
                           IF ArnLike AWS:SourceArn arn:aws:execute-api:us-east-1:010928212265:3t4hod912l/*/GET/investigations/*
                           apigateway.amazonaws.com lambda:InvokeFunction
                           IF ArnLike AWS:SourceArn arn:aws:execute-api:us-east-1:010928212265:3t4hod912l/*/POST/investigations
before-you-buy-authorizer  apigateway.amazonaws.com lambda:InvokeFunction
                           IF ArnLike AWS:SourceArn arn:aws:execute-api:us-east-1:010928212265:3t4hod912l/authorizers/*
before-you-buy-worker      no resource-based policy (invoked only by the API function's role)
```

Automated scan of the three identity policies for an action containing `*` or
a resource equal to `*`: **no match**. The remaining wildcards (ARN suffixes,
the deny-only bucket policy, the SAM permissions) are listed one by one in
`infra/README.md`.

### Do the conditions really bite? `iam:SimulatePrincipalPolicy`

36 cases, 36 as expected (13 allowed, 23 denied). One call was throttled in the
first batch and repeated; its result is the last line.

```text
role        action                                 resource                                                  context                       decision
api         s3:PutObject                           <bucket>/jobs/x.json                                      If-None-Match                 allowed
api         s3:PutObject                           <bucket>/jobs/x.json                                      If-Match                      allowed
api         s3:PutObject                           <bucket>/jobs/x.json                                      unconditional                 implicitDeny
api         s3:PutObject                           <bucket>/results/x.json                                   If-None-Match                 implicitDeny
api         s3:GetObject                           <bucket>/results/x.json                                                                 allowed
api         s3:GetObject                           <bucket>/snapshots/x.json                                                               implicitDeny
api         s3:GetObject                           <bucket>/traces/x.json                                                                  implicitDeny
api         s3:DeleteObject                        <bucket>/jobs/x.json                                                                    implicitDeny
api         s3:ListBucket                          <bucket>                                                  prefix jobs/                  allowed
api         s3:ListBucket                          <bucket>                                                  prefix snapshots/             implicitDeny
api         s3:ListBucket                          <bucket>                                                  no prefix                     implicitDeny
api         lambda:InvokeFunction                  function:before-you-buy-worker                                                          allowed
api         lambda:InvokeFunction                  function:before-you-buy-authorizer                                                      implicitDeny
api         bedrock:InvokeModel                    inference-profile/us.anthropic.claude-sonnet-5-5                                        implicitDeny
api         ssm:GetParameter                       parameter/before-you-buy/access-code                                                    implicitDeny
worker      s3:PutObject                           <bucket>/results/x.json                                   If-None-Match                 allowed
worker      s3:PutObject                           <bucket>/results/x.json                                   unconditional                 implicitDeny
worker      s3:PutObject                           <bucket>/results/x.json                                   If-Match (overwrite)          implicitDeny
worker      s3:PutObject                           <bucket>/traces/x.json                                    If-None-Match                 allowed
worker      s3:PutObject                           <bucket>/jobs/x.json                                      If-Match                      allowed
worker      s3:PutObject                           <bucket>/jobs/x.json                                      If-None-Match (create)        implicitDeny
worker      s3:PutObject                           <bucket>/snapshots/x.json                                 If-None-Match                 implicitDeny
worker      s3:GetObject                           <bucket>/snapshots/x.json                                                               allowed
worker      s3:GetObject                           <bucket>/jobs/x.json                                                                    allowed
worker      s3:DeleteObject                        <bucket>/jobs/x.json                                                                    implicitDeny
worker      s3:ListBucket                          <bucket>                                                  prefix jobs/                  implicitDeny
worker      bedrock:InvokeModel                    inference-profile/us.anthropic.claude-sonnet-5-5                                        allowed
worker      bedrock:InvokeModel                    us-west-2::foundation-model/anthropic.claude-sonnet-5-5   via the profile               allowed
worker      bedrock:InvokeModel                    us-west-2::foundation-model/anthropic.claude-sonnet-5-5   direct, not via the profile   implicitDeny
worker      bedrock:InvokeModel                    inference-profile/us.anthropic.claude-fable-5-2           another model                 implicitDeny
worker      bedrock:InvokeModelWithResponseStream  inference-profile/us.anthropic.claude-sonnet-5-5                                        implicitDeny
worker      lambda:InvokeFunction                  function:before-you-buy-worker                                                          implicitDeny
worker      ssm:GetParameter                       parameter/before-you-buy/access-code                                                    implicitDeny
authorizer  ssm:GetParameter                       parameter/before-you-buy/access-code                                                    allowed
authorizer  ssm:GetParameter                       parameter/before-you-buy/other                                                          implicitDeny
authorizer  s3:GetObject                           <bucket>/jobs/x.json                                                                    implicitDeny
```

The simulator evaluates identity policies only. The allowed rows are also
proven by the live runs; the denied rows are simulation results.

## 10. No secret in the logs, the objects or the outputs

The access code was read inside the sandbox and counted, never returned:

| Where | Scanned | Occurrences of the access code | Occurrences of `bearer ` |
| --- | --- | --- | --- |
| `/aws/lambda/before-you-buy-worker`, all events since 23:00Z | 41 events | 0 | 0 |
| `/aws/lambda/before-you-buy-api` | 102 events | 0 | 0 |
| `/aws/lambda/before-you-buy-authorizer` | 18 events | 0 | 0 |
| `/aws/vendedlogs/apigateway/before-you-buy-http-api` | 43 events | 0 | 0 |
| Data bucket, every object | 9 objects | 0 | - |
| Output of the three smoke runs (`grep -c -F`) | 3 files | 0 | 0 |

`ssm:GetParameter` metadata: name `/before-you-buy/access-code`, type
`SecureString`, version 1, value length 48. The local copy used by the smoke
test (mode 600, outside the repository) was deleted when work was paused, and
the `transfer/` prefix of the artifacts bucket is empty.

## 11. Unit tests

    $ uv run --no-project --with pytest --with boto3 pytest backend/tests/service -q
    ........................................................................ [ 49%]
    ........................................................................ [ 98%]
    ..                                                                       [100%]
    146 passed in 0.29s

That command ran on Python 3.14.2 with boto3 1.44.3. With `--python 3.15`
(Python 3.15.2): `146 passed in 0.27s`.

| Required case | Tests |
| --- | --- |
| Idempotent job creation | `svc02`, `svc03`, `svc04`, `svc05`, `svc06`, `js01`, `js02` |
| 202 only after an accepted invoke | `svc01`, `svc08` |
| Invoke failure gives FAILED and an error response | `svc07`, `svc09` |
| Terminal immutability | `js05`, `js06`, `js08`, `wk05`, `wk06`, `svc20` |
| Duplicate worker delivery | `wk04`, `wk05` |
| Deadline gives FAILED | `svc19`, `wk13`, `wk14`, `wk15`, `wk16`, `wk17`, `wk25` |
| Unknown tool rejected | `wk07`, `ag07` (and invalid arguments: `wk08`, `ag02`) |
| Tool-round bound enforced | `wk09`, `wk10`, `ag16` |
| Authorizer accepts and rejects | `au01` to `au08` |
| The model cannot skip the calculation | `wk11`, `wk12` |
| Untrusted text cannot escape its data block; nothing sensitive is logged | `wk23`, `wk24`, `au07`, `lg02` |

Per file: API 39, worker 35, agents 30, authorizer 17, job store 16, logging 5,
packaging 4. Fourteen deliberately injected defects (for example "202
despite a failed dispatch", "terminal immutability removed", "worker success
after the deadline") were checked: thirteen were caught at once, and "worker
success after the deadline" survived until `wk25` was added.

## 12. Runs 1 and 2

Run 1 (first build, 23:18Z), investigation `inv_fec9ad9165c0306d18a4f39470777374`:
401 / 401 / 403, preflight 204, 400, 404, 202 in 0.536 s, duplicate with the
same id, 409, `t+1s QUEUED`, `t+2s RUNNING`, `t+5s SUCCEEDED steps=1`. Trace:
two Converse calls (770 ms `tool_use`, 1,618 ms `end_turn`), 2,380 input and 277
output tokens. Authorizer decisions logged: `mismatch` then `match`. A real
duplicate delivery was logged and ignored.

Run 2 (final build, 23:22Z), investigation `inv_2e82a727867efaff5483a582721a6bdb`:
every check passed; `t+1s RUNNING`, `t+4s SUCCEEDED steps=1`; 2,380 input and 284
output tokens; Bedrock latency 2,394 ms. Worker `REPORT`: `Duration: 2847.06 ms
Billed Duration: 3450 ms Memory Size: 512 MB Max Memory Used: 101 MB Init
Duration: 602.25 ms`. A duplicate delivery (`8c11f5e9…`) ended in 91.59 ms.

Run 2 came 232 s after run 1's authorizer decisions (23:18:16Z), inside the 300 s authorizer cache of API
Gateway: the authorizer log group has no event for it, and the access log shows
its 403 answered in 0 ms with `authorizerError: Forbidden`. Run 3 was made
after the cache had expired so that the final authorizer build was really
invoked (section 6).

## 13. Template validation

    cfn-lint 1.60.1 on infra/template.yaml      no finding (errors, warnings, informational)
    cfn-guard, Well-Architected Security Pillar, on the processed template returned by
    cloudformation:GetTemplate (TemplateStage=Processed)
        overall: FAIL | rules: 45 {'FAIL': 7, 'SKIP': 32, 'PASS': 6}
        FAIL  IAM_NO_INLINE_POLICY_CHECK, LAMBDA_INSIDE_VPC, CW_LOGGROUP_RETENTION_PERIOD_CHECK,
              S3_BUCKET_LOGGING_ENABLED, CLOUDWATCH_LOG_GROUP_ENCRYPTED, S3_BUCKET_VERSIONING_ENABLED,
              S3_BUCKET_SSL_REQUESTS_ONLY
        PASS  LAMBDA_FUNCTION_PUBLIC_ACCESS_PROHIBITED, S3_BUCKET_LEVEL_PUBLIC_ACCESS_PROHIBITED,
              S3_BUCKET_PUBLIC_READ_PROHIBITED, S3_BUCKET_PUBLIC_WRITE_PROHIBITED,
              S3_BUCKET_SERVER_SIDE_ENCRYPTION_ENABLED, S3_DEFAULT_ENCRYPTION_KMS
    CloudFormation change sets (create, then update)   CREATE_COMPLETE / AVAILABLE, no validation event

Two of the seven failures are false positives and five are accepted for this
prototype; each is explained in `infra/README.md`. The bucket uses SSE-S3
(AES256), not KMS, whatever the name of the last passing rule suggests.

## 14. Not proven here

- Failure paths were not provoked in AWS: dispatch failure, deadline expiry,
  Bedrock throttling, an unknown tool, the round limit and the 429 throttle are
  covered by unit tests with fakes only.
- The server-enforced calculation (`origin: "server"`) did not occur live: in
  all three runs the model called the tool itself with the right arguments.
- The explanation text is model-written and is not checked against evidence
  records in phase 1.
- The tool is a placeholder: no portfolio, holdings or rule data was read and
  no verdict was produced.
- The response shapes are phase-1 shapes, not yet those of `contracts/`.
