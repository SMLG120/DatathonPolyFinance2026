"""V29-V31: static review of the infrastructure template, the repository and the frontend source.

V29  infra/template.yaml: every IAM statement, bucket exposure, TLS, CORS, throttling, retention, authorizer coverage
V30  repository: no committed secret, no restricted data file, real data stays git-ignored
V31  frontend source and built site (candidate d223714): storage of the access code, HTML injection, fixture labelling,
     arithmetic and verdict logic in the browser, wording, lazy loading of three.js and of the test data

Nothing here executes the template or the frontend; the checks read text. The template is parsed by indentation
(no YAML library is allowed in this suite), which is sufficient for the flat structure it has.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = REPO_ROOT / "infra" / "template.yaml"
FRONTEND = REPO_ROOT / "frontend"


# --------------------------------------------------------------------------- template helpers

def _template_lines() -> list[str]:
    return TEMPLATE.read_text().splitlines()


def _section(name: str) -> list[str]:
    lines, out, inside = _template_lines(), [], False
    for line in lines:
        if re.match(r"^[A-Za-z]", line):
            inside = line.startswith(name + ":")
            continue
        if inside:
            out.append(line)
    return out


def resources() -> dict[str, str]:
    blocks, current = {}, None
    for line in _section("Resources"):
        match = re.match(r"^  ([A-Za-z0-9]+):\s*$", line)
        if match:
            current = match.group(1)
            blocks[current] = []
        elif current:
            blocks[current].append(line)
    return {name: "\n".join(body) for name, body in blocks.items()}


def resource_type(body: str) -> str:
    return re.search(r"^    Type: (\S+)", body, re.M).group(1)


def statements(body: str) -> list[dict]:
    """Identity-policy statements of a role block: sid, actions, resources, has_condition, text."""
    policies = body.split("      Policies:", 1)
    if len(policies) < 2:
        return []
    out = []
    for chunk in re.split(r"\n\s+- Sid: ", policies[1])[1:]:
        text = chunk.split("\n      Tags:")[0]
        sid = text.splitlines()[0].strip()
        actions = re.findall(r"\b((?:s3|logs|lambda|bedrock|ssm|iam|sts|kms|dynamodb|sqs|sns|ec2|cloudwatch|secretsmanager|execute-api):[A-Za-z*]+)", text.split("Resource:")[0])
        resource_text = text.split("Resource:", 1)[1].split("Condition:")[0]
        out.append({"sid": sid, "actions": actions, "resources": resource_text.strip(), "condition": text.split("Condition:", 1)[1] if "Condition:" in text else "", "text": text})
    return out


ROLES = {"ApiFunctionRole", "WorkerFunctionRole", "AuthorizerFunctionRole"}

# Every action each role may hold. A new action or role is a review item, not an automatic failure of the product:
# the test fails so that a human re-reads the statement (see REPORT.md, "checks to re-run on the release candidate").
REVIEWED_ACTIONS = {
    # bedrock:InvokeModel added on deec650 for the rule interpreter (audited in the fourth pass, REPORT.md section 6).
    "ApiFunctionRole": {"logs:CreateLogStream", "logs:PutLogEvents", "s3:GetObject", "s3:PutObject", "s3:ListBucket", "lambda:InvokeFunction", "bedrock:InvokeModel"},
    "WorkerFunctionRole": {"logs:CreateLogStream", "logs:PutLogEvents", "s3:GetObject", "s3:PutObject", "bedrock:InvokeModel"},
    "AuthorizerFunctionRole": {"logs:CreateLogStream", "logs:PutLogEvents", "ssm:GetParameter"},
}


# =========================================================================== V29 infrastructure

@pytest.mark.vcase("V29")
def test_v29_the_set_of_iam_roles_and_policies_is_the_reviewed_one():
    found = {name for name, body in resources().items() if resource_type(body) == "AWS::IAM::Role"}
    assert found == ROLES, f"IAM roles changed since the review of d36e41f: {sorted(found ^ ROLES)}"
    other_iam = {name: resource_type(body) for name, body in resources().items() if resource_type(body).startswith("AWS::IAM::") and name not in ROLES}
    assert other_iam == {}, f"unreviewed IAM resources: {other_iam}"
    text = TEMPLATE.read_text()
    assert "ManagedPolicyArns" not in text and "\n      Policies:\n        - AWS" not in text, "no AWS managed policy may be attached (they carry wildcards)"
    assert not re.search(r"^\s+Policies:\s*\n\s+- [A-Z][A-Za-z0-9]+(Policy|Access)\b", text, re.M), "no SAM policy template on a function"


@pytest.mark.vcase("V29")
@pytest.mark.parametrize("role", sorted(ROLES))
def test_v29_every_identity_statement_is_least_privilege(role):
    body = resources()[role]
    found = statements(body)
    assert found, f"{role}: no inline statements found"
    actions = {action for statement in found for action in statement["actions"]}
    assert actions == REVIEWED_ACTIONS[role], f"{role}: actions differ from the reviewed set: {sorted(actions ^ REVIEWED_ACTIONS[role])}"
    for statement in found:
        assert "Effect: Allow" in statement["text"]
        assert all("*" not in action for action in statement["actions"]), f"{role}/{statement['sid']}: wildcard action"
        resource_lines = [line.strip().lstrip("- ").strip() for line in statement["resources"].splitlines() if line.strip()] or [statement["resources"]]
        for resource in resource_lines:
            assert resource not in ('"*"', "'*'", "*"), f"{role}/{statement['sid']}: Resource \"*\""
            if "*" in resource:
                # The only resource wildcards allowed are key prefixes inside the project's own bucket.
                assert re.fullmatch(r"!Sub \$\{DataBucket\.Arn\}/(jobs|results|traces|snapshots|policies)/\*", resource), f"{role}/{statement['sid']}: unreviewed wildcard resource {resource}"
        assert "NotAction" not in statement["text"] and "NotResource" not in statement["text"]
    assert "iam:PassRole" not in body and "sts:AssumeRole" not in body.split("Policies:")[1]


@pytest.mark.vcase("V29")
@pytest.mark.parametrize("role", sorted(ROLES))
def test_v29_every_s3_write_is_conditional_and_nothing_can_delete(role):
    for statement in statements(resources()[role]):
        if "s3:PutObject" in statement["actions"]:
            condition = statement["condition"]
            assert '"Null":' in condition and re.search(r's3:if-(none-)?match: "false"', condition), f"{role}/{statement['sid']}: unconditional s3:PutObject"
    assert "s3:Delete" not in resources()[role] and "s3:PutBucket" not in resources()[role] and "s3:PutObjectAcl" not in resources()[role]


@pytest.mark.vcase("V29")
def test_v29_separation_of_duties_between_the_three_functions():
    by_role = {role: {a for s in statements(resources()[role]) for a in s["actions"]} for role in ROLES}
    # Fourth pass (deec650): the API function may call the model, for the rule interpreter only. What still separates
    # the two functions: only the worker can write a result or a trace, only the worker's output is a report, the API
    # function cannot read a trace, and neither can touch the snapshot or the access code.
    api_grants, worker_grants = _grants("ApiFunctionRole"), _grants("WorkerFunctionRole")
    assert {g for g in api_grants if g[0].startswith("bedrock:")} == {g for g in worker_grants if g[0].startswith("bedrock:")}, "same model, same profile, nothing more than the worker"
    assert not [g for g in api_grants if g[0] in ("s3:GetObject", "s3:PutObject") and g[1].startswith("traces/")], "the API function cannot read or write a trace"
    assert not [g for g in api_grants if g[0] == "s3:PutObject" and g[1].startswith(("results/", "snapshots/"))]
    assert [g for g in worker_grants if g[0] == "s3:PutObject" and g[1] == "results/*"] == [("s3:PutObject", "results/*", "if-none-match")]
    assert "lambda:InvokeFunction" not in by_role["WorkerFunctionRole"], "the worker cannot start other functions"
    assert "ssm:GetParameter" not in by_role["ApiFunctionRole"] | by_role["WorkerFunctionRole"], "only the authorizer can read the access code"
    assert not any(a.startswith(("s3:", "lambda:", "bedrock:")) for a in by_role["AuthorizerFunctionRole"])
    api_writes = [s for s in statements(resources()["ApiFunctionRole"]) if "s3:PutObject" in s["actions"]]
    assert all("results/" not in s["resources"] and "traces/" not in s["resources"] for s in api_writes), "the API function cannot write a result"
    invoke = [s for s in statements(resources()["ApiFunctionRole"]) if "lambda:InvokeFunction" in s["actions"]]
    assert [s["resources"] for s in invoke] == ["!GetAtt WorkerFunction.Arn"]
    ssm = [s for s in statements(resources()["AuthorizerFunctionRole"]) if "ssm:GetParameter" in s["actions"]]
    assert len(ssm) == 1 and ssm[0]["resources"].endswith("parameter${AccessCodeParameterName}")


PROFILE_ARN = "!Sub arn:${AWS::Partition}:bedrock:${AWS::Region}:${AWS::AccountId}:inference-profile/${BedrockModelId}"


@pytest.mark.vcase("V29")
@pytest.mark.parametrize("role", ["ApiFunctionRole", "WorkerFunctionRole"])
def test_v29_bedrock_access_is_one_model_through_one_inference_profile(role):
    """Audited statement by statement on deec650 for both roles. bedrock:InvokeModel is the action Converse needs (the
    streaming action is absent, so ConverseStream and InvokeModelWithResponseStream are denied). Resources: the one
    inference profile of this account and Region, and the foundation model in the three Regions the profile routes to,
    the latter only when the call comes through that profile (StringEquals on bedrock:InferenceProfileArn)."""
    found = [s for s in statements(resources()[role]) if any(a.startswith("bedrock:") for a in s["actions"])]
    assert len(found) == 2 and all(s["actions"] == ["bedrock:InvokeModel"] for s in found)
    profile, models = sorted(found, key=lambda s: "foundation-model/" in s["resources"])
    assert profile["resources"] == PROFILE_ARN and profile["condition"] == ""
    lines = [line.strip().lstrip("- ").strip() for line in models["resources"].splitlines() if line.strip()]
    assert lines == [f"!Sub arn:${{AWS::Partition}}:bedrock:{region}::foundation-model/${{BedrockFoundationModelId}}" for region in ("us-east-1", "us-east-2", "us-west-2")]
    condition = [line.strip() for line in models["condition"].splitlines() if line.strip()]
    assert condition == ["StringEquals:", "bedrock:InferenceProfileArn: " + PROFILE_ARN], "exactly one condition: the call comes through the named profile"
    for statement in found:
        assert "*" not in statement["resources"], "no model wildcard"
    roles_text = "\n".join(resources()[name] for name in ROLES)
    for broader in ("bedrock:InvokeModelWithResponseStream", "bedrock:Converse", "bedrock:*", "bedrock:InvokeAgent", "bedrock:Retrieve", "bedrock:ApplyGuardrail",
                    "bedrock:Get", "bedrock:List", "bedrock:Create", "application-inference-profile", "provisioned-model", "custom-model"):
        assert broader not in roles_text, broader
    assert not any(a.startswith("bedrock:") for s in statements(resources()["AuthorizerFunctionRole"]) for a in s["actions"])


@pytest.mark.vcase("V29")
def test_v29_interpreter_timeouts_fit_under_the_gateway_limit_and_the_contract_deadline():
    """deec650: API function timeout 25 s; integration timeout 29 s on the two routes that can run the interpreter,
    20 s elsewhere. The handler's own deadline is 20 s (contracts/api.md, INTERPRET_TIMEOUT_SECONDS): it must fire
    before the function is killed, and the function before API Gateway's 30 s cut, so the client gets the contract's
    504 body and not a gateway error."""
    from byb_contracts.constants import INTERPRET_TIMEOUT_SECONDS
    api_function = resources()["ApiFunction"]
    function_timeout = int(re.search(r"^      Timeout: (\d+)", api_function, re.M).group(1))
    integration = dict(re.findall(r"Path: (\S+)\n\s+PayloadFormatVersion: \"2\.0\"\n(?:\s+#.*\n)*\s+TimeoutInMillis: (\d+)", api_function))
    assert set(integration) == {path for _, path in CANONICAL_ROUTES}
    slow = {"/rules/interpret", "/investigations/{id}/challenge"}
    assert {path for path, value in integration.items() if int(value) != 20000} == slow
    assert INTERPRET_TIMEOUT_SECONDS == 20 and INTERPRET_TIMEOUT_SECONDS + 3 <= function_timeout
    assert all(function_timeout * 1000 + 2000 <= int(integration[path]) <= 30000 - 1000 for path in slow)
    handler = (REPO_ROOT / "backend" / "api" / "handler.py").read_text()
    connect = int(re.search(r"INTERPRETER_CONNECT_TIMEOUT_SECONDS = (\d+)", handler).group(1))
    read = int(re.search(r"INTERPRETER_READ_TIMEOUT_SECONDS = (\d+)", handler).group(1))
    assert connect + read <= INTERPRET_TIMEOUT_SECONDS - 5 and 2 * (connect + read) > INTERPRET_TIMEOUT_SECONDS, "one long call fits; two long calls cannot both start"
    assert '"total_max_attempts": 1' in handler, "the SDK's own retries are off for the interpreter"


@pytest.mark.vcase("V29")
def test_v29_interpreter_switches_are_plain_settings_of_the_api_function_only():
    api_function, worker, authorizer = (resources()[name] for name in ("ApiFunction", "WorkerFunction", "AuthorizerFunction"))
    assert 'INTERPRETER_ENABLED: "true"' in api_function
    limit = int(re.search(r'INTERPRETER_OUTPUT_LIMIT: "(\d+)"', api_function).group(1))
    assert 256 <= limit <= 4096, "the output limit bounds the cost of one call"
    assert "INTERPRETER_" not in worker and "INTERPRETER_" not in authorizer
    config = (REPO_ROOT / "backend" / "common" / "config.py").read_text()
    assert 'interpreter_enabled=env.get("INTERPRETER_ENABLED", "").strip().lower() == "true"' in config, "anything but the word true means off (fail closed)"
    assert "interpreter_enabled: bool = False" in config


@pytest.mark.vcase("V29")
def test_v29_every_route_that_can_reach_the_model_has_its_own_throttle_below_the_default():
    """Closes F-22 (fourth pass: POST /rules/interpret kept the default 20 rps). Pinned as reviewed on b7f43aa:
    interpret 2 rps / burst 5; the two routes that start an investigation or run CLARIFY_PREFERENCE 5 rps / burst 10;
    every other route is the default 20 / 40 and reaches no model.
    Residual, disclosed (LOW): the API function has no reserved concurrency, and the template's own note says route
    throttling is best effort, so the interpreter path has no hard bound on concurrent Bedrock calls as the worker has."""
    api_function = resources()["ApiFunction"]
    throttles = {}
    for block in api_function.split("Type: HttpApi")[1:]:
        path, method = re.search(r"Path: (\S+)", block).group(1), re.search(r"Method: (\S+)", block).group(1)
        own = re.search(r"RouteSettings:\n(?:\s+#.*\n)*\s+ThrottlingBurstLimit: (\d+)\s*\n\s+ThrottlingRateLimit: (\d+)", block)
        throttles[(method, path)] = (int(own.group(2)), int(own.group(1))) if own else None
    assert throttles[("POST", "/rules/interpret")] == (2, 5)
    assert throttles[("POST", "/investigations")] == (5, 10) and throttles[("POST", "/investigations/{id}/challenge")] == (5, 10)
    assert {route for route, own in throttles.items() if own} == {("POST", "/rules/interpret"), ("POST", "/investigations"), ("POST", "/investigations/{id}/challenge")}
    http_api = resources()["HttpApi"]
    assert re.search(r"DefaultRouteSettings:\s*\n\s+ThrottlingBurstLimit: 40\s*\n\s+ThrottlingRateLimit: 20", http_api)
    assert "ReservedConcurrentExecutions" not in api_function, "pinned as observed: if a bound is added, re-review and say so in the report"
    assert "ReservedConcurrentExecutions: !Ref WorkerReservedConcurrency" in resources()["WorkerFunction"]


@pytest.mark.vcase("V29")
@pytest.mark.parametrize("role", sorted(ROLES))
def test_v29_trust_policies_name_the_lambda_service_with_confused_deputy_conditions(role):
    trust = resources()[role].split("      Policies:")[0]
    assert "Service: lambda.amazonaws.com" in trust and trust.count("Effect: Allow") == 1
    assert "aws:SourceAccount" in trust and "aws:SourceArn" in trust
    assert 'AWS: "*"' not in trust and "Principal: \"*\"" not in trust
    wildcards = re.findall(r"function:\$\{AWS::StackName\}-[a-z]+:\*", trust)
    assert len(wildcards) == trust.count(":*"), "the only wildcard in a trust policy is the version qualifier of the role's own function"


@pytest.mark.vcase("V29")
def test_v29_bucket_is_private_encrypted_tls_only_and_expires_job_data():
    bucket = resources()["DataBucket"]
    for flag in ("BlockPublicAcls", "BlockPublicPolicy", "IgnorePublicAcls", "RestrictPublicBuckets"):
        assert f"{flag}: true" in bucket, f"{flag} must be true"
    assert "SSEAlgorithm:" in bucket and "BucketOwnerEnforced" in bucket
    assert "AccessControl: Public" not in bucket and "WebsiteConfiguration" not in bucket and "CorsConfiguration" not in bucket
    assert re.findall(r"ExpirationInDays: (\d+)", bucket) and all(int(d) <= 7 for d in re.findall(r"ExpirationInDays: (\d+)", bucket))
    policy = resources()["DataBucketPolicy"]
    assert policy.count("Effect:") == 1 and "Effect: Deny" in policy, "the bucket policy holds one statement and it is a Deny"
    assert 'aws:SecureTransport: "false"' in policy and "Action: s3:*" in policy and "${DataBucket.Arn}/*" in policy
    buckets = [n for n, b in resources().items() if resource_type(b) == "AWS::S3::Bucket"]
    assert buckets == ["DataBucket"], "a second bucket needs its own review"


@pytest.mark.vcase("V29")
def test_v29_every_route_is_behind_the_authorizer_and_there_is_no_default_route():
    api = resources()["HttpApi"]
    assert "DefaultAuthorizer: AccessCodeAuthorizer" in api and "EnableSimpleResponses: true" in api
    assert re.search(r"Identity:\s*\n\s+Headers:\s*\n\s+- Authorization", api), "the authorizer is keyed on the Authorization header"
    text = TEMPLATE.read_text()
    routes = re.findall(r"Type: HttpApi\s*\n\s+Properties:\s*\n((?:\s{12}.*\n)+)", text)
    assert len(routes) >= 2
    for route in routes:
        assert "ApiId: !Ref HttpApi" in route, "a route attached to another API would not inherit the authorizer"
        assert "Auth:" not in route and "Authorizer: NONE" not in route, f"a route overrides the default authorizer:\n{route}"
        assert "$default" not in route and "Path: /{proxy+}" not in route
    assert not re.search(r"(RouteKey|Path):\s*['\"]?\$default", text), "a $default route would catch every path"
    assert "FunctionUrlConfig" not in text and "AWS::Lambda::Url" not in text, "a function URL would bypass the authorizer"
    assert "AWS::Lambda::Permission" not in text or "apigateway.amazonaws.com" in text
    functions = [n for n, b in resources().items() if resource_type(b) == "AWS::Serverless::Function"]
    assert sorted(functions) == ["ApiFunction", "AuthorizerFunction", "WorkerFunction"]
    assert "Events:" not in resources()["WorkerFunction"], "the worker has no public trigger"


CANONICAL_ROUTES = {("GET", "/portfolios/{persona_id}"), ("POST", "/rules/interpret"), ("POST", "/rules/confirm"), ("POST", "/check"),
                    ("POST", "/investigations"), ("GET", "/investigations/{id}"), ("POST", "/investigations/{id}/challenge")}


@pytest.mark.vcase("V29")
def test_v29_declared_routes_are_exactly_the_seven_of_the_contract():
    """Re-reviewed on the candidate df33dd6: the seven routes of contracts/api.md, all events of ApiFunction, all attached
    to HttpApi (default authorizer), none with its own Auth block. The two routes that start an investigation carry
    the tighter throttle."""
    text = TEMPLATE.read_text()
    routes = re.findall(r"Method: (GET|POST|PUT|DELETE|PATCH|ANY)\s*\n\s+Path: (\S+)", text)
    assert len(routes) == len(set(routes)) and set(routes) == CANONICAL_ROUTES, sorted(set(routes) ^ CANONICAL_ROUTES)
    api_function = resources()["ApiFunction"]
    assert api_function.count("Type: HttpApi") == 7 and api_function.count("ApiId: !Ref HttpApi") == 7
    for path in ("/investigations", "/investigations/{id}/challenge"):
        block = api_function.split(f"Path: {path}\n", 1)[1].split("Type: HttpApi")[0]
        assert re.search(r"ThrottlingBurstLimit: 10\s*\n\s+ThrottlingRateLimit: 5\b", block), f"{path} starts model work and needs the tight throttle"


# Every identity statement of the candidate, read one by one on df33dd6: (action, key prefix or resource, write condition).
REVIEWED_STATEMENTS = {
    "ApiFunctionRole": {
        ("logs:CreateLogStream", "!GetAtt ApiLogGroup.Arn", ""), ("logs:PutLogEvents", "!GetAtt ApiLogGroup.Arn", ""),
        ("s3:GetObject", "jobs/*", ""), ("s3:GetObject", "results/*", ""), ("s3:GetObject", "policies/*", ""), ("s3:GetObject", "snapshots/*", ""),
        ("s3:PutObject", "policies/*", "if-none-match"), ("s3:PutObject", "jobs/*", "if-none-match"), ("s3:PutObject", "jobs/*", "if-match"),
        ("s3:ListBucket", "!GetAtt DataBucket.Arn", "prefix:jobs/*,policies/*"),
        ("lambda:InvokeFunction", "!GetAtt WorkerFunction.Arn", ""),
        # deec650, rule interpreter: Converse through the one inference profile; foundation models only via that profile.
        ("bedrock:InvokeModel", "inference-profile", ""), ("bedrock:InvokeModel", "foundation-model", "profile"),
    },
    "WorkerFunctionRole": {
        ("logs:CreateLogStream", "!GetAtt WorkerLogGroup.Arn", ""), ("logs:PutLogEvents", "!GetAtt WorkerLogGroup.Arn", ""),
        ("s3:GetObject", "jobs/*", ""), ("s3:GetObject", "policies/*", ""), ("s3:GetObject", "snapshots/*", ""),
        ("s3:PutObject", "jobs/*", "if-match"), ("s3:PutObject", "results/*", "if-none-match"), ("s3:PutObject", "traces/*", "if-none-match"),
        ("bedrock:InvokeModel", "inference-profile", ""), ("bedrock:InvokeModel", "foundation-model", "profile"),
    },
    "AuthorizerFunctionRole": {
        ("logs:CreateLogStream", "!GetAtt AuthorizerLogGroup.Arn", ""), ("logs:PutLogEvents", "!GetAtt AuthorizerLogGroup.Arn", ""),
        ("ssm:GetParameter", "parameter${AccessCodeParameterName}", ""),
    },
}


def _grants(role: str) -> set[tuple[str, str, str]]:
    out = set()
    for statement in statements(resources()[role]):
        condition = statement["condition"]
        if "s3:if-none-match" in condition:
            kind = "if-none-match"
        elif "s3:if-match" in condition:
            kind = "if-match"
        elif "s3:prefix" in condition:
            kind = "prefix:" + ",".join(re.findall(r"- (\S+)", condition))
        elif "bedrock:InferenceProfileArn" in condition:
            kind = "profile"
        else:
            assert condition.strip() == "", f"{role}/{statement['sid']}: unreviewed condition"
            kind = ""
        lines = [line.strip().lstrip("- ").strip() for line in statement["resources"].splitlines() if line.strip()]
        for action in statement["actions"]:
            for resource in lines:
                prefix = re.fullmatch(r"!Sub \$\{DataBucket\.Arn\}/(\w+/\*)", resource)
                if prefix:
                    resource = prefix.group(1)
                elif "inference-profile/${BedrockModelId}" in resource:
                    resource = "inference-profile"
                elif re.search(r":bedrock:us-(east-1|east-2|west-2)::foundation-model/\$\{BedrockFoundationModelId\}$", resource):
                    resource = "foundation-model"
                elif resource.endswith("parameter${AccessCodeParameterName}"):
                    resource = "parameter${AccessCodeParameterName}"
                out.add((action, resource, kind))
    return out


@pytest.mark.vcase("V29")
@pytest.mark.parametrize("role", sorted(ROLES))
def test_v29_every_grant_is_the_one_reviewed_on_the_candidate(role):
    """Second pass (df33dd6). New since d36e41f and judged acceptable: the API function reads policies/ and snapshots/
    (POST /check runs the engine there), creates a policy version only if absent, and lists only jobs/ and policies/;
    the worker reads policies/ and snapshots/. Nobody can write snapshots/, nobody can delete, the API function cannot
    write results/ or traces/ or read traces/, the worker cannot write policies/ or list the bucket."""
    assert _grants(role) == REVIEWED_STATEMENTS[role], sorted(_grants(role) ^ REVIEWED_STATEMENTS[role])


@pytest.mark.vcase("V29")
def test_v29_no_role_can_write_the_data_snapshot_or_overwrite_a_policy_version():
    for role in ROLES:
        for action, resource, kind in _grants(role):
            if action == "s3:PutObject":
                assert resource != "snapshots/*", f"{role} could change the data a verdict is computed from"
                assert resource != "policies/*" or (role == "ApiFunctionRole" and kind == "if-none-match"), "a confirmed policy version is write-once"
                assert resource not in ("results/*", "traces/*") or (role == "WorkerFunctionRole" and kind == "if-none-match")


@pytest.mark.vcase("V29")
def test_v29_a_rotated_access_code_stops_working_within_the_function_cache_only():
    """Closes F-09: API Gateway no longer caches the authorizer's answer (ReauthorizeEvery 0); the only delay is the
    function's own cache of the SSM value (30 s)."""
    api, authorizer = resources()["HttpApi"], resources()["AuthorizerFunction"]
    assert re.search(r"^\s+ReauthorizeEvery: 0\s*$", api, re.M)
    seconds = re.search(r'ACCESS_CODE_CACHE_SECONDS: "(\d+)"', authorizer)
    assert seconds and int(seconds.group(1)) <= 60


@pytest.mark.vcase("V29")
def test_v29_both_functions_are_pinned_to_one_data_snapshot_and_the_packaged_schemas():
    for name in ("ApiFunction", "WorkerFunction"):
        body = resources()[name]
        assert "DATA_SNAPSHOT_ID: !Ref DataSnapshotId" in body and "BYB_SCHEMA_DIR: /var/task/byb_contracts/schemas" in body
    parameter = "\n".join(_section("Parameters")).split("  DataSnapshotId:", 1)[1].split("\n  WorkerReservedConcurrency:")[0]
    assert "Default:" not in parameter and "AllowedPattern: ^snap-" in parameter, "the snapshot id has no default: a deployment names its data"
    assert "BEDROCK" not in "".join(re.findall(r"^          ([A-Z_]+): ", resources()["AuthorizerFunction"], re.M))


@pytest.mark.vcase("V29")
def test_v29_the_deploy_script_refuses_a_wildcard_origin_by_default():
    """F-08, the remaining path. The template no longer has a default, but a stack that was deployed with "*" keeps it
    as the previous value on an update. This script computes the value the stack will have (override, else the stack's
    current value) and does not execute when it is "*". Limit: the guard is a constant in one script; an update made
    by any other means (console, CLI) keeps "*" silently. Only the live check of the deployed parameter settles it."""
    script = (REPO_ROOT / "scripts" / "mcp" / "02_deploy.py").read_text()
    assert re.search(r"^ALLOW_WILDCARD_ORIGIN = False\s*$", script, re.M), "the committed default must refuse"
    guard = script.index('if EXECUTE and report["cors_refusal"]')
    assert guard < script.index('"ExecuteChangeSet"'), "the refusal is evaluated before the change set is executed"
    source = script[script.index("def effective_parameter("):script.index("TEMPLATE_URL =")]
    scope: dict = {}
    exec(compile(source, "deploy_guard", "exec"), scope)  # two pure functions, read above
    refusal, effective = scope["origin_refusal"], scope["effective_parameter"]
    assert refusal("*", False) and refusal(" * ", False) and refusal("", False) and refusal(None, False)
    assert refusal("http://evil.example", False) and refusal("//evil.example", False) and refusal("null", False)
    # The remaining path: a stack deployed from the older template keeps "*" as its previous value on an update.
    old_stack = [{"ParameterKey": "AllowedOrigin", "ParameterValue": "*"}, {"ParameterKey": "DataSnapshotId", "ParameterValue": "snap-2026-11-12-3390e023b308"}]
    template = [{"ParameterKey": "AllowedOrigin"}]
    assert effective("AllowedOrigin", {}, old_stack, template) == "*" and refusal(effective("AllowedOrigin", {}, old_stack, template), False), "kept wildcard is refused"
    assert refusal(effective("AllowedOrigin", {"AllowedOrigin": "https://main.abc123.amplifyapp.com"}, old_stack, template), False) is None
    assert refusal(effective("AllowedOrigin", {}, None, template), False), "a first deployment without the parameter is refused"
    assert 'report["allowed_origin"] = effective_parameter("AllowedOrigin", values, (stack or {}).get("Parameters"), summary.get("Parameters"))' in script
    assert refusal("https://main.abc123.amplifyapp.com", False) is None and refusal("*", True) is None


@pytest.mark.vcase("V29")
def test_v29_throttling_concurrency_timeouts_and_retention_are_bounded():
    api, text = resources()["HttpApi"], TEMPLATE.read_text()
    default = re.search(r"DefaultRouteSettings:\s*\n\s+ThrottlingBurstLimit: (\d+)\s*\n\s+ThrottlingRateLimit: (\d+)", api)
    assert default and int(default.group(1)) <= 100 and int(default.group(2)) <= 50, "a default throttle must exist and stay modest"
    create = re.search(r"Path: /investigations\n(?:.*\n){1,4}?\s+RouteSettings:\s*\n\s+ThrottlingBurstLimit: (\d+)\s*\n\s+ThrottlingRateLimit: (\d+)", text)
    assert create and int(create.group(2)) <= int(default.group(2)), "the route that costs model calls has its own, tighter throttle"
    worker = resources()["WorkerFunction"]
    assert "ReservedConcurrentExecutions:" in worker and "MaximumRetryAttempts: 0" in worker
    concurrency = re.search(r"WorkerReservedConcurrency:\s*\n(?:.*\n){0,6}?\s+Default: (\d+)", text)
    assert concurrency and 1 <= int(concurrency.group(1)) <= 10
    assert int(re.search(r"^      Timeout: (\d+)", worker, re.M).group(1)) >= 160, "worker timeout must cover the 150 s job deadline"
    assert int(re.search(r"^      Timeout: (\d+)", resources()["ApiFunction"], re.M).group(1)) < 30
    assert int(re.search(r"^      Timeout: (\d+)", resources()["AuthorizerFunction"], re.M).group(1)) < 10
    assert 'JOB_DEADLINE_SECONDS: "150"' in resources()["ApiFunction"]
    groups = [b for b in resources().values() if resource_type(b) == "AWS::Logs::LogGroup"]
    assert len(groups) == 4 and all("RetentionInDays: !Ref LogRetentionDays" in b for b in groups), "every log group has a retention"
    retention = re.search(r"LogRetentionDays:\s*\n(?:.*\n){0,6}?\s+Default: (\d+)", text)
    assert retention and int(retention.group(1)) <= 30


@pytest.mark.vcase("V29")
def test_v29_cors_allows_only_the_needed_methods_and_headers_and_no_credentials():
    api = resources()["HttpApi"]
    assert re.search(r"AllowMethods:\s*\n\s+- GET\s*\n\s+- POST\s*\n\s+- OPTIONS\s*\n\s+AllowHeaders:", api)
    assert re.search(r"AllowHeaders:\s*\n\s+- authorization\s*\n\s+- content-type\s*\n\s+- idempotency-key\s*\n\s+MaxAge:", api)
    assert "AllowCredentials" not in api, "credentials with a wildcard origin would be a defect"


@pytest.mark.vcase("V29")
def test_v29_cors_origin_has_no_default_and_must_be_an_exact_origin_or_a_typed_wildcard():
    """Closes the template part of F-08 (5cb6ce1): a new stack cannot be created without stating the origin, and only
    an exact https origin (or localhost) or a deliberately typed "*" is accepted."""
    block = "\n".join(_section("Parameters")).split("  AllowedOrigin:", 1)[1].split("\n  AccessCodeParameterName:")[0]
    assert "Default:" not in block, "the origin must be stated by every deployment"
    pattern = re.search(r"AllowedPattern: (\S+)", block).group(1)
    for good in ("https://main.d1abc2def3.amplifyapp.com", "https://example.org:8443", "http://localhost:3000", "http://127.0.0.1", "*"):
        assert re.fullmatch(pattern, good), good
    for bad in ("", "null", "https://*.amplifyapp.com", "https://a.example/", "https://a.example/path", "http://evil.example", "https://a.example,https://b.example",
                "https://a.example https://b.example", "**", "* ", "//a.example", "https://a.example?x", "https://user@a.example", "file://x", "https://"):
        assert not re.fullmatch(pattern, bad), bad
    api = resources()["HttpApi"]
    assert re.search(r"AllowOrigins:\s*\n\s+- !Ref AllowedOrigin\s*\n", api) and api.count("!Ref AllowedOrigin") == 1


@pytest.mark.vcase("V29")
def test_v29_access_code_is_never_a_parameter_environment_variable_or_output():
    text = TEMPLATE.read_text()
    for section in ("Parameters", "Outputs"):
        names = re.findall(r"^  ([A-Za-z0-9]+):\s*$", "\n".join(_section(section)), re.M)
        assert not [n for n in names if re.search(r"code|secret|token|password", n, re.I) and n not in ("AccessCodeParameterName", "CodeS3Bucket", "CodeS3Key", "CodeArtifact")], names
    assert "NoEcho" not in text, "a NoEcho parameter would mean a secret is passed through CloudFormation"
    variables = re.findall(r"^          ([A-Z_]+): (.+)$", text, re.M)
    for name, value in variables:
        assert name == "BEDROCK_MAX_TOKENS" or not re.search(r"SECRET|TOKEN|PASSWORD|API_KEY", name), name
        if "ACCESS_CODE" in name:
            assert name in ("ACCESS_CODE_PARAMETER_NAME", "ACCESS_CODE_CACHE_SECONDS"), f"{name} looks like the code itself"
    assert "{{resolve:ssm-secure" not in text and "{{resolve:secretsmanager" not in text, "the code must not be resolved into the template"
    log_format = re.search(r"Format: '(.+)'", text).group(1)
    assert "authorization" not in log_format.lower().replace("authorizer.error", "") and "$context.identity" not in log_format, "access logs carry no credential or IP"


# =========================================================================== V30 repository

def tracked_files() -> list[str]:
    done = subprocess.run(["git", "ls-files"], cwd=REPO_ROOT, capture_output=True, text=True, check=True)
    return done.stdout.splitlines()


SECRET_PATTERNS = {
    "AWS access key id": re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b"),
    "AWS secret key assignment": re.compile(r"aws_secret_access_key\s*[=:]\s*['\"]?[A-Za-z0-9/+=]{40}"),
    "private key": re.compile(r"-----BEGIN (RSA |EC |OPENSSH |)PRIVATE KEY-----"),
    "bearer token literal": re.compile(r"Bearer\s+[A-Za-z0-9_\-\.]{32,}"),
    "provider API key": re.compile(r"\b(sk-ant-[A-Za-z0-9_\-]{20,}|sk-[A-Za-z0-9]{40,}|ghp_[A-Za-z0-9]{36}|xox[baprs]-[A-Za-z0-9-]{20,})"),
}


# Literals read one by one during the review of d36e41f: made-up words used as wrong or dummy tokens in tests and in the
# smoke script. Anything else that looks like a bearer value fails the test.
REVIEWED_PLACEHOLDERS = {
    "Bearer wrong-code-wrong-code-wrong-code",
    "Bearer some-other-secret-looking-token-value",
    "Bearer this-is-not-the-access-code-0000",
}


@pytest.mark.vcase("V30")
def test_v30_no_secret_is_committed():
    hits = []
    for name in tracked_files():
        path = REPO_ROOT / name
        if not path.is_file() or path.stat().st_size > 2_000_000 or name == "frontend/package-lock.json":
            continue
        try:
            text = path.read_text()
        except UnicodeDecodeError:
            continue
        for label, pattern in SECRET_PATTERNS.items():
            for match in pattern.finditer(text):
                if match.group(0) in REVIEWED_PLACEHOLDERS:
                    continue
                line = text.count("\n", 0, match.start()) + 1
                hits.append(f"{name}:{line}: {label}")
    assert hits == [], "possible committed secrets:\n" + "\n".join(hits[:20])


@pytest.mark.vcase("V30")
def test_v30_no_env_file_credential_file_or_restricted_data_is_tracked():
    bad = []
    for name in tracked_files():
        base = name.rsplit("/", 1)[-1]
        if re.fullmatch(r"\.env(\..+)?", base) and base != ".env.example":
            bad.append(name)
        if re.search(r"credential|\.pem$|\.p12$|id_rsa|\.tfstate", name, re.I):
            bad.append(name)
        if name in ("data/starter/prices_daily.csv", "data/starter/corporate_actions.csv") or name.startswith(("data/raw/", "reference/")):
            bad.append(name)
        if name.startswith("data/processed/") and base in ("market_data.json", "holdings.json", "instruments.json", "fund_sector_breakdowns.json", "build_report.json"):
            bad.append(name)
        if re.search(r"\.(xlsx|xls|parquet|zip|sqlite|db)$", name, re.I):
            bad.append(name)
    assert bad == [], f"tracked files that must not be in the repository: {bad}"
    processed = sorted(name for name in tracked_files() if name.startswith("data/processed/"))
    assert processed == ["data/processed/controversies.json", "data/processed/sources.json"], (
        f"only the curated controversy and source registries may be tracked under data/processed (data/.gitignore): {processed}")
    example = (REPO_ROOT / "frontend" / ".env.example").read_text()
    values = [line.split("=", 1)[1].strip() for line in example.splitlines() if "=" in line and not line.lstrip().startswith("#")]
    assert all(len(v) < 100 and not re.search(r"[A-Za-z0-9]{32,}", v) for v in values), ".env.example must not hold a real value"


@pytest.mark.vcase("V30")
@pytest.mark.parametrize("path", ["data/processed/market_data.json", "data/processed/holdings.json", "data/processed/instruments.json",
                                  "data/processed/fund_sector_breakdowns.json", "data/processed/build_report.json",
                                  "data/starter/prices_daily.csv", "data/starter/corporate_actions.csv", "data/raw/anything.csv", ".env", "frontend/.env.local"])
def test_v30_real_and_licence_pending_data_is_git_ignored(path):
    done = subprocess.run(["git", "check-ignore", "-q", path], cwd=REPO_ROOT)
    assert done.returncode == 0, f"{path} is not ignored by git: a plain `git add` would publish it"


@pytest.mark.vcase("V30")
@pytest.mark.xfail(strict=True, reason="V30a: the AWS account id and the execute-api host name of the deployed stack are committed in docs, "
                                       "evidence and scripts (not a credential; avoidable disclosure, LOW)")
def test_v30_no_account_identifier_or_live_endpoint_is_committed():
    hits = []
    for name in tracked_files():
        path = REPO_ROOT / name
        if name.startswith("validation/") or not path.is_file() or path.stat().st_size > 2_000_000:
            continue
        try:
            text = path.read_text()
        except UnicodeDecodeError:
            continue
        if re.search(r"(?<![0-9])[0-9]{12}(?![0-9])\.dkr|arn:aws:[a-z0-9-]+:[a-z0-9-]*:[0-9]{12}:|[a-z0-9]{10}\.execute-api\.[a-z0-9-]+\.amazonaws\.com|account[^\n]{0,20}\b[0-9]{12}\b", text, re.I):
            hits.append(name)
    assert hits == [], f"{len(hits)} tracked files name the account or the live endpoint: {hits[:8]}"


@pytest.mark.vcase("V30")
def test_v30_production_code_has_no_order_execution_recommendation_or_forecast_surface():
    """BUILD_BRIEF 2/6: no trade tool, no recommendation, no forecast. Checked on names that would be callable surface:
    functions, tool names and routes of the backend, and the template."""
    forbidden = re.compile(r"\b(def|class)\s+\w*(execute_trade|place_order|submit_order|buy_order|sell_order|recommend|forecast|predict|rebalance|optimi[sz]e_portfolio)\w*", re.I)
    tool_name = re.compile(r"[\"'](execute_trade|place_order|submit_order|recommend_\w+|forecast_\w+|predict_\w+|optimi[sz]e_\w+|web_search|run_code|execute_code)[\"']")
    hits = []
    for name in tracked_files():
        if not name.startswith(("backend/", "infra/")) or "/tests/" in name or not name.endswith((".py", ".yaml")):
            continue
        text = (REPO_ROOT / name).read_text()
        for pattern in (forbidden, tool_name):
            for match in pattern.finditer(text):
                hits.append(f"{name}:{text.count(chr(10), 0, match.start()) + 1}: {match.group(0)}")
    assert hits == [], "\n".join(hits)
    for name in tracked_files():
        if name.startswith("backend/") and name.endswith(".py") and "/tests/" not in name:
            text = (REPO_ROOT / name).read_text()
            assert not re.search(r"^\s*(import|from)\s+(requests|urllib3|httpx|aiohttp|socket|subprocess)\b", text, re.M), f"{name}: unexpected network or process import"
            assert not re.search(r"\b(eval|exec)\(", text), f"{name}: eval/exec in production code"


@pytest.mark.vcase("V30")
def test_v30_the_engine_has_no_model_network_or_clock_dependency():
    """The trusted calculation must be deterministic Python: no boto3, no agents, no time, no randomness."""
    for path in sorted((REPO_ROOT / "backend" / "engine").glob("*.py")):
        text = path.read_text()
        imports = re.findall(r"^\s*(?:import|from)\s+([A-Za-z0-9_.]+)", text, re.M)
        for module in imports:
            root = module.lstrip(".").split(".")[0]
            assert root not in {"boto3", "botocore", "random", "time", "datetime_now", "requests", "urllib", "socket", "os", "subprocess", "secrets", "uuid"}, f"{path.name} imports {module}"
            assert not module.startswith(("backend.agents", "backend.worker", "backend.api")), f"{path.name} imports {module}"
        assert "datetime.now" not in text and "time.time" not in text and "utcnow" not in text, f"{path.name} reads the clock"


# =========================================================================== V31 frontend (candidate d223714)
#
# Third pass: frontend/ is the candidate's (contract-typed, static export, 3D exposure explorer). Static review of the
# source, plus checks of the built site in frontend/out when a build is present (the build is not tracked).

def frontend_sources() -> list[Path]:
    if not (FRONTEND / "src").is_dir():
        pytest.skip("frontend/src is not present in this checkout")
    return [p for p in sorted((FRONTEND / "src").rglob("*")) if p.suffix in (".ts", ".tsx") and ".test." not in p.name
            and "/test/" not in str(p) and "/generated/" not in str(p)]


def _code_lines(path: Path):
    """(number, stripped line, code without string literals, comments and JSX attribute names)."""
    for number, line in enumerate(path.read_text().splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith(("*", "//", "/*", "import ")):
            continue
        code = re.sub(r'"[^"]*"|\'[^\']*\'', '""', stripped)
        code = re.sub(r"`[^`]*`", '""', code)
        code = re.sub(r"//.*$", "", code)
        code = re.sub(r"\b[a-z]+(?:-[a-z]+)+=", "", code)
        yield number, stripped, code


def _hits(pattern: str, flags: int = 0) -> list[str]:
    out = []
    for path in frontend_sources():
        for number, line in enumerate(path.read_text().splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith(("*", "//", "/*")):
                continue
            if re.search(pattern, line, flags):
                out.append(f"{path.relative_to(REPO_ROOT)}:{number}: {stripped[:120]}")
    return out


def _source(relative: str) -> str:
    path = FRONTEND / "src" / relative
    assert path.is_file(), f"frontend/src/{relative} is missing: re-run the manual review"
    return path.read_text()


@pytest.mark.vcase("V31")
def test_v31_no_html_injection_sink_in_the_frontend():
    assert _hits(r"dangerouslySetInnerHTML|\.innerHTML\s*=|\.outerHTML\s*=|insertAdjacentHTML|document\.write\(|\beval\(|new Function\(|srcDoc|__html") == []


@pytest.mark.vcase("V31")
def test_v31_sentences_steps_and_user_words_are_rendered_as_text_nodes():
    """Explanation sentences, step summaries, clarification words and error messages are placed as React text children."""
    assert re.search(r"<p[^>]*data-testid=\"explanation-text\"[^>]*>\s*\{statement\.text\}\s*</p>", _source("components/verdict/Explanation.tsx"))
    timeline = _source("components/timeline/StepTimeline.tsx")
    assert "{step.input_summary}</dd>" in timeline and '{step.result_summary ?? "Not available yet"}</dd>' in timeline
    assert _hits(r"href=\{[^}]*(statement|step|clarification|evidence|record|source)\.[a-z_]*(text|summary|words|url|title)") == [], "no link is built from result text"


@pytest.mark.vcase("V31")
def test_v31_access_code_is_kept_in_session_storage_only():
    assert _hits(r"localStorage|document\.cookie|indexedDB|caches\.open") == [], "the access code and results must not be persisted beyond the tab"
    storage = _hits(r"\bsessionStorage\b")
    assert storage and all("src/lib/access-code.ts" in hit for hit in storage), f"sessionStorage is used outside lib/access-code.ts: {storage}"
    code_in_url = _hits(r"(searchParams|URLSearchParams|location\.(search|hash)).*(code|token)", re.I)
    assert code_in_url == [], f"the access code must never travel in a URL: {code_in_url}"
    assert _hits(r"console\.(log|info|debug|warn|error)\(.*(accessCode|access_code|Authorization|Bearer)", re.I) == []
    client = _source("lib/api/http-client.ts")
    assert "headers.Authorization = `Bearer ${accessCode}`" in client and 'credentials: "omit"' in client
    assert client.count("accessCode") <= 4 and "accessCode" not in "".join(re.findall(r"new URL\([^)]*\)|`\$\{[^`]*\?[^`]*`", client)), "the code is sent in the header only"
    runtime = _source("state/runtime.tsx")
    assert runtime.index("await createHttpClient(") < runtime.index("storeAccessCode(candidate)"), "a code is stored only after the service accepted it"


@pytest.mark.vcase("V31")
def test_v31_no_secret_or_fixed_code_in_the_frontend_bundle_inputs():
    assert _hits(r"Bearer\s+[A-Za-z0-9_\-]{12,}") == [], "a literal bearer value in frontend source"
    env = _hits(r"process\.env\.(?!NEXT_PUBLIC_API_BASE_URL\b|NODE_ENV\b)[A-Z_]+")
    assert env == [], f"unreviewed environment variables are compiled into the bundle: {env}"
    assert _hits(r"NEXT_PUBLIC_[A-Z_]*(CODE|SECRET|TOKEN|KEY)") == []
    assert _hits(r"[a-z0-9]{10}\.execute-api\.|arn:aws:|(?<![0-9])[0-9]{12}(?![0-9])") == [], "no account identifier or live endpoint in frontend source"


@pytest.mark.vcase("V31")
def test_v31_test_data_cannot_be_shown_without_its_label_nor_the_label_lost_in_live_mode():
    """One value decides both: RuntimeConfig.mode. The HTTP client is built only when mode is live; otherwise the
    fixtures client is. The banner label, the footer text and the tag on every block of figures read the same mode."""
    index = _source("lib/api/index.ts")
    assert re.search(r'if \(config\.mode === "live" && config\.apiBaseUrl\) \{\s*return createHttpClient\(', index)
    assert index.rstrip().endswith("return createLazyFixturesClient(config);\n}".rstrip()) and index.count("createHttpClient(") == 1
    config = _source("lib/config.ts")
    assert 'const mode: AppMode = fixturesReason === null ? "live" : "fixtures";' in config
    assert re.search(r"else if \(url === null\) fixturesReason = \"no-base-url\";", config), "no service address means fixtures, never a silent live mode"
    shell = _source("components/shell/AppShell.tsx")
    assert re.search(r'FIXTURES_LABEL = "Test data', shell) and shell.count("{FIXTURES_LABEL}") >= 2
    assert re.search(r'\{config\.mode === "fixtures" \? \(\s*<p data-testid="fixtures-label"', shell), "the banner label depends on the mode only"
    assert "sticky top-0" in shell.split('data-testid="fixtures-label"')[0].rsplit("<section", 1)[1], "the label sits in the always-visible banner"
    runtime = _source("state/runtime.tsx")
    assert "<DataModeProvider value={config.mode}>{children}</DataModeProvider>" in runtime
    tag = _source("components/ui/TestDataTag.tsx")
    assert 'useContext(DataModeContext) === "fixtures"' in tag
    assert "{figures ? <TestDataTag /> : null}" in _source("components/ui/Panel.tsx")
    # Recorded bodies are reachable only through the fixtures client, and that client only through a dynamic import.
    importers = [h for h in _hits(r"from \"@/lib/fixtures\"|generated/contracts/fixtures|generated/contracts/scenarios") if "src/lib/fixtures.ts" not in h]
    assert importers and all("src/lib/api/fixtures-client.ts" in h for h in importers), importers
    clients = _hits(r"fixtures-client")
    assert [h for h in clients if "import(" in h] and all("src/lib/api/index.ts" in h or "src/lib/api/fixtures-client.ts" in h or "src/lib/fixtures.ts" in h for h in clients), clients
    assert _hits(r"from \"\./fixtures-client\"|from \"@/lib/api/fixtures-client\"") == [], "a static import would ship test data to a live session"


# Arithmetic the review accepted, line by line: none of it produces a figure of the result.
REVIEWED_ARITHMETIC = {
    ("components/challenge/ChangeRuleForm.tsx", "Math.abs(threshold - current) <= EPS"),   # form check: the new number equals the current one
    ("components/rules/ThresholdInput.tsx", "fraction * 100"),                             # shows the number the user typed, as a percentage
    ("components/rules/ThresholdInput.tsx", "Math.ceil(percent / 10) * 10"),               # upper end of the slider
    ("components/verdict/RuleResults.tsx", "Math.abs(upper - lower) <= EPS"),              # one number or a range: display decision on the engine's two ends
}
# Files whose arithmetic is formatting or drawing only (rounding for display, pixel and world coordinates, axis ticks),
# and the fixtures client (labelled test data, never used in live mode).
ARITHMETIC_EXEMPT = {"lib/format.ts", "components/explorer/ExposureScene.tsx", "components/verdict/ExposureChart.tsx", "lib/api/fixtures-client.ts"}
_FINANCIAL = (r"(threshold|current|upper|lower|fraction|percent|limit|target|cash\w*|weight\w*|gap|known|direct|exposure\w*|additional\w*|possible\w*|"
              r"measured|value|total|pass|fail|unknown|loss|drawdown|coverage\w*|headroom)")
_ARITHMETIC = re.compile(rf"(?<![\w.\"'`$-])(?:\w+\.)*{_FINANCIAL}\b\)?\s*[-+*/](?![=>/*])\s*[\w(.]|[\w)\]]\s*[-+*/](?![=>/*])\s*(?:\w+\.)*{_FINANCIAL}\b(?![\w\"'`-])", re.I)


@pytest.mark.vcase("V31")
def test_v31_no_financial_arithmetic_in_the_browser():
    """Closes F-11. BUILD_BRIEF 1: rules are checked by deterministic Python. Additional purchase, cash after, gaps,
    bounds, counts and the maximum are read from the service's answer; the browser only formats and draws."""
    portfolio = _source("lib/portfolio.ts")
    assert "previewPurchase" not in portfolio and not re.search(r"cash_weight\s*-|-\s*\w*\.weight", portfolio)
    found = []
    for path in frontend_sources():
        relative = str(path.relative_to(FRONTEND / "src"))
        if relative in ARITHMETIC_EXEMPT:
            continue
        for number, stripped, code in _code_lines(path):
            if _ARITHMETIC.search(code) and not any(relative == name and snippet in stripped for name, snippet in REVIEWED_ARITHMETIC):
                found.append(f"{relative}:{number}: {stripped[:140]}")
    assert found == [], "arithmetic on a financial value outside the reviewed lines:\n" + "\n".join(found)
    assert _hits(r"\.reduce\(") == [] or all("fixtures-client" in h or "ExposureScene" in h for h in _hits(r"\.reduce\(")), "nothing is summed in the browser"
    feasibility = _source("components/portfolio/FeasibilityTable.tsx")
    assert "feasibility.additional_purchase" in feasibility and not re.search(r"cash_before\s*-|target\w*\s*-", feasibility)


@pytest.mark.vcase("V31")
def test_v31_the_explorer_draws_only_numbers_of_the_api_result():
    model = _source("components/explorer/model.ts")
    body = model.replace(model[model.index("function axisTop("):model.index("export function buildExplorerModel(")], "")
    arithmetic = [stripped for path in [FRONTEND / "src" / "components" / "explorer" / "model.ts"] for _, stripped, code in _code_lines(path)
                  if re.search(r"[\w)\]]\s[-+*/]\s[\w(]", code) and stripped in body]
    assert arithmetic == [], f"the view model computes: {arithmetic}"
    for copied in ("value: breakdown.direct", "value: path.known", "value: possibleExtra", "known: breakdown.lower, upper: breakdown.upper", "value: cap.limit",
                   "result.exposure.possible_extra.starting", "result.exposure.possible_extra.proposed", "isDraft: result.preview"):
        assert copied in model, f"expected the model to copy {copied}"
    assert 'if (result.execution.status !== "OK") return unavailable("EXECUTION_NOT_OK"' in model, "no drawing for a request that was not evaluated"
    slots = _source("components/exposure3d/ExposureExplorerSlots.tsx")
    assert 'dataOrigin: isTestData ? "FIXTURE" : "LIVE"' in slots, "the explorer is told by the runtime whether its numbers are test data"


@pytest.mark.vcase("V31")
def test_v31_the_headline_is_the_services_and_all_pass_is_never_said_with_a_fail_or_an_unknown():
    """Closes F-13. The headline is chosen by summary.headline; the counts are summary.counts. The browser never counts
    statuses, and it refuses to say 'respected' when the service's own counts contradict its headline."""
    verdict = _source("lib/verdict.ts")
    assert "switch (summary.headline)" in verdict and "const { pass, fail, unknown } = summary.counts;" in verdict
    for headline in ("EXECUTION_ERROR", "INVALID_REQUEST", "NO_RULES_EVALUATED", "POLICY_CONFLICT", "HAS_FAIL", "NO_FAIL_BUT_UNKNOWN", "ALL_PASS"):
        assert f'"{headline}"' in verdict, f"{headline} is not handled"
    assert verdict.count('tone: "pass"') == 1
    assert verdict.index("if (fail > 0 || unknown > 0) return inconsistent;") < verdict.index('tone: "pass"')
    assert "but this is not a pass" in verdict and "not counted as passed" in verdict
    counting = _hits(r"\.filter\([^)]*status\s*===\s*\"(PASS|FAIL|UNKNOWN)\"[^)]*\)\s*\.length|rule_results\.(every|some)\(")
    assert counting == [], f"the browser derives a verdict from rule statuses: {counting}"
    result = _source("lib/result.ts")
    assert 'if (value.execution.status !== "OK") return { kind: "not_executed", result: value };' in result, "a request that was not evaluated is never drawn as a verdict"


@pytest.mark.vcase("V31")
def test_v31_unknown_is_never_styled_or_worded_as_a_pass():
    badge = _source("components/ui/Badge.tsx")
    assert re.search(r'UNKNOWN: \{ tone: "unknown", Icon: UnknownIcon, dashed: true \}', badge)
    assert re.search(r'PASS: \{ tone: "pass"', badge) and re.search(r'FAIL: \{ tone: "fail"', badge)
    assert 'UNKNOWN: "border-dashed border-unknown"' in _source("components/verdict/RuleResults.tsx")
    assert 'const STATUS_TEXT: Record<VerdictStatus, string> = { PASS: "Pass", FAIL: "Fail", UNKNOWN: "Unknown" };' in _source("lib/verdict.ts")
    wrong = _hits(r"(UNKNOWN|MISSING|PARTIAL|WITHHELD)[\"']?\s*[:?]\s*[^,\n]*[\"'](pass|success|ok)[\"']", re.I)
    assert wrong == [], f"an unknown or missing state mapped to a pass style: {wrong}"
    assert _hits(r"\?\?\s*0\b.*(lower|upper|weight|exposure|coverage)|(lower|upper|exposure|coverage_fraction)\s*\?\?\s*0\b") == [], "a missing figure is never replaced by zero"


@pytest.mark.vcase("V31")
def test_v31_a_maximum_is_shown_only_when_the_service_supports_it():
    panels = _source("components/verdict/ContextPanels.tsx")
    block = panels[panels.index("export function MaxCompliantBlock("):]
    order = [block.index("if (!maxCompliant)"), block.index('maxCompliant.status === "WITHHELD"'), block.index('maxCompliant.status === "NO_FEASIBLE_PURCHASE"'),
             block.index('data-status="SUPPORTED"'), block.index("maxCompliant.final_direct_weight")]
    assert order == sorted(order), "the figure is rendered only after the three early returns"
    assert block.count("maxCompliant.final_direct_weight") == 1 and "A guess is not shown in its place." in block
    users = [h for h in _hits(r"final_direct_weight|max_compliant\b") if "/lib/api/" not in h and "/lib/contracts" not in h and "explorer/contract-types" not in h]
    assert all("ContextPanels.tsx" in h or "Report.tsx" in h or "StepTimeline.tsx" in h for h in users), users
    assert 'formatFraction(maxCompliant.final_direct_weight, { rounding: "down" })' in block, "the maximum is never rounded up for display"


@pytest.mark.vcase("V31")
def test_v31_a_draft_preview_is_never_presented_as_a_confirmed_result():
    preview = _source("components/rules/DraftPreview.tsx")
    assert "aria-label={`Draft preview: ${ruleTypeLabel(ruleType)}`}" in preview and "A preview is never saved" in preview
    assert "assessResult(preview.result)" in preview, "a preview that was not evaluated shows no verdict"
    assert "isDraft: result.preview" in _source("components/explorer/model.ts")
    assert _hits(r"status:\s*\"CONFIRMED\"") == [] or all("fixtures-client" in h for h in _hits(r"status:\s*\"CONFIRMED\"")), "the browser never marks a rule CONFIRMED itself"


# Sentences that contain one of the words below in order to DENY it; read one by one.
REVIEWED_DENIALS = ("It gives no financial advice, makes no recommendation and no forecast", "not a forecast", "predicts nothing and guarantees nothing",
                    "It is not a forecast and not a guarantee")


@pytest.mark.vcase("V31")
def test_v31_no_advice_or_forecast_wording_in_the_interface():
    """AC-H3 / AC-N2, UI part: the replay is called a replay of the past; nothing in the interface advises or predicts."""
    hits = _hits(r"you should|we recommend|recommend(ed|s)? |advis|forecast|predict|expected return|will (rise|fall|go up|grow|increase|recover)|safe to buy|"
                 r"good (buy|investment|idea)|guarantee|\bbest\b|optimal|outperform|opportunit|undervalued|bargain", re.I)
    unexpected = [h for h in hits if not any(denial in h for denial in REVIEWED_DENIALS)]
    assert unexpected == [], "\n".join(unexpected)
    scenario = _source("components/verdict/ScenarioPanel.tsx")
    assert 'title="A replay of the past — not a forecast"' in scenario
    assert 'SIMULATION_LABEL = "Simulation — fictional portfolio, not advice"' in _source("components/shell/AppShell.tsx")


@pytest.mark.vcase("V31")
def test_v31_the_page_outlasts_the_job_deadline():
    generated = (FRONTEND / "src" / "generated" / "contracts" / "contracts.ts").read_text()
    poll = int(re.search(r"POLL_DEADLINE_MS = (\d+);", generated).group(1))
    job = int(re.search(r'JOB_DEADLINE_SECONDS: "(\d+)"', TEMPLATE.read_text()).group(1))
    assert poll == 180_000 and poll > job * 1000 + 10_000, "the poll deadline must exceed the job deadline, so the page shows the job's real outcome"
    assert "pollDeadlineMs: POLL_DEADLINE_MS" in _source("lib/config.ts")
    polling = _source("hooks/usePolling.ts")
    assert 'setTimeout(() => finish("timed_out"), deadlineMs)' in polling and "controller.abort()" in polling


@pytest.mark.vcase("V31")
def test_v31_three_js_is_loaded_only_when_the_explorer_is_opened():
    importers = _hits(r"from \"three(/[^\"]*)?\"")
    assert importers and all("components/explorer/ExposureScene.tsx" in h for h in importers), importers
    scene_users = [h for h in _hits(r"ExposureScene\"") if "ExposureScene.tsx" not in h and ": import type {" not in h]  # type imports are erased
    assert scene_users and all('lazy(() => import("./ExposureScene"))' in h for h in scene_users), scene_users


def _built_site() -> Path:
    out = FRONTEND / "out"
    if not (out / "index.html").is_file():
        pytest.skip("frontend/out is not built in this checkout (run `npm ci && npm run build` in frontend/; the build is not tracked)")
    return out


@pytest.mark.vcase("V31")
def test_v31_the_built_site_holds_no_secret_account_identifier_or_source_map():
    out = _built_site()
    text = "".join(p.read_text(errors="ignore") for p in out.rglob("*") if p.is_file() and p.suffix in (".js", ".html", ".txt", ".css", ".json"))
    for label, pattern in {"account id": r"(?<![0-9.])[0-9]{12}(?![0-9])", "execute-api host": r"[a-z0-9]{10}\.execute-api\.", "access key": r"(AKIA|ASIA)[0-9A-Z]{16}",
                           "bearer literal": r"Bearer\s+[A-Za-z0-9_\-]{12,}", "ARN": r"arn:aws:", "source map": r"sourceMappingURL"}.items():
        assert not re.search(pattern, text), f"{label} in the built site"
    assert list(out.rglob("*.map")) == [] and not [p for p in out.rglob("*") if p.name.startswith(".env")]


@pytest.mark.vcase("V31")
def test_v31_the_built_main_page_does_not_load_three_js_or_the_test_data():
    out = _built_site()
    html = (out / "index.html").read_text()
    referenced = set(re.findall(r"/_next/static/chunks/([^\"'\\ ]+\.js)", html))
    assert referenced
    heavy = {}
    for chunk in (out / "_next" / "static" / "chunks").rglob("*.js"):
        text = chunk.read_text(errors="ignore")
        if "WebGLRenderer" in text:
            heavy[chunk.name] = "three.js"
        elif "synthetic_note" in text:
            heavy[chunk.name] = "recorded test data"
    assert set(heavy.values()) == {"three.js", "recorded test data"}, heavy
    assert not referenced & set(heavy), f"loaded by the main page: {referenced & set(heavy)}"
