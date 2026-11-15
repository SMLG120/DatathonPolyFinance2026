"""infra/template.yaml checked as text (no YAML dependency): routes, configuration, least privilege, timeouts.

Nothing here talks to AWS. The template is not deployed by this change; these tests keep it consistent with the code.
"""

import re

import pytest
from byb_contracts.constants import INVESTIGATION_DEADLINE_SECONDS

from backend.api.handler import Api
from service_fakes import REPO_ROOT

TEMPLATE = (REPO_ROOT / "infra" / "template.yaml").read_text(encoding="utf-8")


def block(name: str) -> str:
    """Text of one top-level resource (two-space indented key) up to the next one."""
    match = re.search(rf"^  {name}:\n(.*?)(?=^  [A-Za-z]|\Z)", TEMPLATE, re.S | re.M)
    assert match, name
    return match.group(1)


def statements(role: str) -> dict[str, str]:
    text = block(role).split("Policies:", 1)[1]
    parts = re.split(r"^ {14}- Sid: ", text, flags=re.M)[1:]
    return {part.split("\n", 1)[0].strip(): part for part in parts}


def test_tp01_every_contract_route_has_an_event_and_a_handler():
    events = set(zip(re.findall(r"^ {12}Method: (\w+)$", TEMPLATE, re.M), re.findall(r"^ {12}Path: (\S+)$", TEMPLATE, re.M)))
    routes = {f"{method} {path}" for method, path in events}
    assert routes == {"GET /portfolios/{persona_id}", "POST /rules/interpret", "POST /rules/confirm", "POST /check",
                      "POST /investigations", "GET /investigations/{id}", "POST /investigations/{id}/challenge"}
    api = Api(store=None, policies=None, snapshots=None, lambda_client=None, config=None, clock=None)
    assert set(api._routes) == routes
    assert "$default" not in block("ApiFunction") and len(re.findall(r"^ {12}PayloadFormatVersion: \"2\.0\"$", TEMPLATE, re.M)) == 7
    assert "DefaultAuthorizer: AccessCodeAuthorizer" in block("HttpApi")


def test_tp02_both_functions_get_the_snapshot_id_and_the_bundled_schemas():
    for function in ("ApiFunction", "WorkerFunction"):
        text = block(function)
        assert "DATA_SNAPSHOT_ID: !Ref DataSnapshotId" in text and "BYB_SCHEMA_DIR: /var/task/byb_contracts/schemas" in text
        assert "DATA_BUCKET: !Ref DataBucket" in text
    parameter = TEMPLATE.split("  DataSnapshotId:\n", 1)[1].split("  WorkerReservedConcurrency:", 1)[0]
    assert "Default:" not in parameter and "AllowedPattern: ^snap-" in parameter  # must be chosen at deploy time
    assert "DATA_SNAPSHOT_ID" not in block("AuthorizerFunction")


def test_tp03_timeouts_agree_with_the_contract_deadline():
    assert f'JOB_DEADLINE_SECONDS: "{INVESTIGATION_DEADLINE_SECONDS}"' in block("ApiFunction")
    worker_timeout = int(re.search(r"^      Timeout: (\d+)$", block("WorkerFunction"), re.M).group(1))
    api_timeout = int(re.search(r"^      Timeout: (\d+)$", block("ApiFunction"), re.M).group(1))
    assert worker_timeout >= INVESTIGATION_DEADLINE_SECONDS + 10 and worker_timeout <= 900
    assert api_timeout < 20 and set(re.findall(r"TimeoutInMillis: (\d+)", TEMPLATE)) == {"20000"}  # under the 30 s integration limit
    assert "MaximumRetryAttempts: 0" in block("WorkerFunction") and "ReservedConcurrentExecutions: !Ref WorkerReservedConcurrency" in block("WorkerFunction")


def test_tp04_no_wildcard_actions_or_resources_in_any_role():
    for role in ("ApiFunctionRole", "WorkerFunctionRole", "AuthorizerFunctionRole"):
        policy = block(role).split("Policies:", 1)[1]
        assert not re.search(r"Action:\s*['\"]?\*|Action:\s*\w+:\*|- \w+:\*\s*$", policy, re.M), role
        assert not re.search(r"Resource:\s*['\"]?\*['\"]?\s*$", policy, re.M), role
        assert "ManagedPolicyArns" not in block(role)
        assert "s3:DeleteObject" not in policy and "s3:PutBucket" not in policy


def test_tp05_snapshots_are_read_only_and_every_write_is_conditional():
    for role in ("ApiFunctionRole", "WorkerFunctionRole"):
        found = statements(role)
        for sid, text in found.items():
            if "s3:PutObject" in text:
                assert "snapshots/" not in text, (role, sid)
                assert ("s3:if-none-match: \"false\"" in text) != ("s3:if-match: \"false\"" in text), (role, sid)
        assert any("s3:GetObject" in text and "/snapshots/*" in text for text in found.values()), role
    assert "snapshots" not in block("AuthorizerFunctionRole") and "s3:" not in block("AuthorizerFunctionRole").split("Policies:", 1)[1]


def test_tp06_api_role_reads_and_writes_exactly_what_the_routes_need():
    api = statements("ApiFunctionRole")
    assert set(api) == {"WriteOwnLogs", "ReadJobsResultsPoliciesAndSnapshots", "CreatePolicyVersionOnlyIfAbsent", "CreateJobOnlyIfAbsent",
                        "UpdateJobOnlyByCompareAndSwap", "ListJobsAndPoliciesPrefixesOnly", "DispatchToWorkerOnly"}
    assert set(re.findall(r"\$\{DataBucket\.Arn\}/(\w+)/\*", api["ReadJobsResultsPoliciesAndSnapshots"])) == {"jobs", "results", "policies", "snapshots"}
    assert "policies/*" in api["CreatePolicyVersionOnlyIfAbsent"] and "if-none-match" in api["CreatePolicyVersionOnlyIfAbsent"]
    assert re.findall(r"^ {22}- (\S+)$", api["ListJobsAndPoliciesPrefixesOnly"], re.M) == ["jobs/*", "policies/*"]
    assert "bedrock" not in "".join(api.values()) and "traces" not in "".join(api.values())
    assert "Resource: !GetAtt WorkerFunction.Arn" in api["DispatchToWorkerOnly"]
    put_targets = {target for text in api.values() if "s3:PutObject" in text for target in re.findall(r"\}/(\w+)/\*", text)}
    assert put_targets == {"jobs", "policies"}


def test_tp07_worker_role_cannot_write_policies_or_create_jobs():
    worker = statements("WorkerFunctionRole")
    put = {sid: text for sid, text in worker.items() if "s3:PutObject" in text}
    assert set(put) == {"UpdateJobOnlyByCompareAndSwap", "WriteResultAndTraceOnce"}
    assert "if-match" in put["UpdateJobOnlyByCompareAndSwap"] and "if-none-match" not in put["UpdateJobOnlyByCompareAndSwap"]
    assert set(re.findall(r"\}/(\w+)/\*", put["WriteResultAndTraceOnce"])) == {"results", "traces"}
    assert set(re.findall(r"\}/(\w+)/\*", worker["ReadJobsPoliciesAndSnapshots"])) == {"jobs", "policies", "snapshots"}
    assert "lambda:" not in "".join(worker.values()) and "ssm:" not in "".join(worker.values()) and "s3:ListBucket" not in "".join(worker.values())
    assert all("inference-profile/${BedrockModelId}" in text for sid, text in worker.items() if "bedrock:" in text)


def test_tp08_cors_allows_the_idempotency_header_and_the_code_is_never_in_the_template():
    cors = block("HttpApi").split("CorsConfiguration:", 1)[1].split("DefaultRouteSettings:", 1)[0]
    assert re.findall(r"^ {10}- (\S+)$", cors.split("AllowHeaders:", 1)[1].split("MaxAge", 1)[0], re.M) == ["authorization", "content-type", "idempotency-key"]
    assert "SecureString" not in block("AuthorizerFunction") and "ACCESS_CODE:" not in TEMPLATE and "NoEcho" not in TEMPLATE
    assert "ACCESS_CODE_PARAMETER_NAME: !Ref AccessCodeParameterName" in block("AuthorizerFunction")
    for route in ("CreateInvestigation", "ChallengeInvestigation"):
        text = block("ApiFunction").split(f"        {route}:", 1)[1].split("PayloadFormatVersion", 1)[1][:400]
        assert "ThrottlingRateLimit: 5" in text and "ThrottlingBurstLimit: 10" in text, route
    assert "PublicAccessBlockConfiguration" in block("DataBucket") and block("DataBucket").count(": true") == 4
