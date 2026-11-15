# Deploying the backend through the AWS MCP tool

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

Add `--with-engine` once `backend/engine/` exists, and
`--include contracts/python=<archive prefix>` if the contracts package must
ship (phase 2).

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
example `{"AllowedOrigin": "https://main.<app-id>.amplifyapp.com"}`.

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

`PutParameter` with `Overwrite=True` on the same name (generate the value in
the sandbox, as the bootstrap does). No redeploy. The new code is accepted
within 60 seconds (the authorizer's in-memory cache). The old code can still be
accepted for up to 300 seconds, because API Gateway caches the authorizer's
answer for each `Authorization` header value.

## 8. Teardown

1. `DeleteStack` on `before-you-buy`. The data bucket is retained on purpose.
2. Empty and delete the data bucket (stack output `DataBucketName`).
3. Empty and delete `byb-artifacts-010928212265-us-east-1`.
4. `DeleteParameter` on `/before-you-buy/access-code`.

The whole account is deleted after 2026-11-16, which removes all of it anyway.
