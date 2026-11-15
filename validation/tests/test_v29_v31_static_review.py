"""V29-V31: static review of the infrastructure template, the repository and the frontend source.

V29  infra/template.yaml: every IAM statement, bucket exposure, TLS, CORS, throttling, retention, authorizer coverage
V30  repository: no committed secret, no restricted data file, real data stays git-ignored
V31  frontend source (PRELIMINARY: the frontend is mid-migration): storage of the access code, HTML injection,
     fixture labelling, arithmetic and verdict logic in the browser

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
    "ApiFunctionRole": {"logs:CreateLogStream", "logs:PutLogEvents", "s3:GetObject", "s3:PutObject", "s3:ListBucket", "lambda:InvokeFunction"},
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
    assert "bedrock:InvokeModel" not in by_role["ApiFunctionRole"], "the API function never calls the model"
    assert "lambda:InvokeFunction" not in by_role["WorkerFunctionRole"], "the worker cannot start other functions"
    assert "ssm:GetParameter" not in by_role["ApiFunctionRole"] | by_role["WorkerFunctionRole"], "only the authorizer can read the access code"
    assert not any(a.startswith(("s3:", "lambda:", "bedrock:")) for a in by_role["AuthorizerFunctionRole"])
    api_writes = [s for s in statements(resources()["ApiFunctionRole"]) if "s3:PutObject" in s["actions"]]
    assert all("results/" not in s["resources"] and "traces/" not in s["resources"] for s in api_writes), "the API function cannot write a result"
    invoke = [s for s in statements(resources()["ApiFunctionRole"]) if "lambda:InvokeFunction" in s["actions"]]
    assert [s["resources"] for s in invoke] == ["!GetAtt WorkerFunction.Arn"]
    ssm = [s for s in statements(resources()["AuthorizerFunctionRole"]) if "ssm:GetParameter" in s["actions"]]
    assert len(ssm) == 1 and ssm[0]["resources"].endswith("parameter${AccessCodeParameterName}")


@pytest.mark.vcase("V29")
def test_v29_bedrock_access_is_one_model_through_one_inference_profile():
    found = [s for s in statements(resources()["WorkerFunctionRole"]) if "bedrock:InvokeModel" in s["actions"]]
    assert len(found) == 2
    for statement in found:
        assert "*" not in statement["resources"], "no model wildcard"
        if "foundation-model/" in statement["resources"]:
            assert "bedrock:InferenceProfileArn" in statement["condition"], "foundation models are reachable only via the named profile"
    roles_text = "\n".join(resources()[role] for role in ROLES)
    assert "bedrock:InvokeModelWithResponseStream" not in roles_text and "bedrock:*" not in roles_text


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


@pytest.mark.vcase("V29")
def test_v29_declared_routes_are_only_those_this_review_covered():
    """On the release candidate this fails until the new routes are re-reviewed and added here: every route must keep
    the authorizer and a throttle (contracts/api.md, Authentication: "Every route requires ...")."""
    text = TEMPLATE.read_text()
    routes = set(re.findall(r"Method: (GET|POST|PUT|DELETE|PATCH|ANY)\s*\n\s+Path: (\S+)", text))
    reviewed = {("POST", "/investigations"), ("GET", "/investigations/{id}")}
    canonical = reviewed | {("GET", "/portfolios/{persona_id}"), ("POST", "/rules/interpret"), ("POST", "/rules/confirm"), ("POST", "/check"),
                            ("POST", "/investigations/{id}/challenge")}
    assert routes <= canonical, f"routes outside contracts/api.md: {sorted(routes - canonical)}"
    if routes != reviewed:
        assert routes == canonical, f"a release candidate must declare all seven routes; missing: {sorted(canonical - routes)}"


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
@pytest.mark.xfail(strict=True, reason="V29a: CORS AllowedOrigin defaults to \"*\" (infra/template.yaml Parameters.AllowedOrigin); "
                                       "the template's own rule (HttpApi Metadata `must`): temporary, set it to the Amplify origin once known")
def test_v29_cors_origin_is_restricted_to_the_hosted_frontend():
    text = TEMPLATE.read_text()
    default = re.search(r"  AllowedOrigin:\s*\n\s+Type: String\s*\n(\s+Default: (\S+)\s*\n)?", text)
    assert default and default.group(2) not in ('"*"', "'*'", "*"), "the default origin must not be a wildcard"


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


# =========================================================================== V31 frontend (preliminary)

def frontend_sources() -> list[Path]:
    if not (FRONTEND / "src").is_dir():
        pytest.skip("frontend/src is not present in this checkout")
    return [p for p in sorted((FRONTEND / "src").rglob("*")) if p.suffix in (".ts", ".tsx") and ".test." not in p.name and "/test/" not in str(p)]


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


@pytest.mark.vcase("V31")
def test_v31_no_html_injection_sink_in_the_frontend():
    assert _hits(r"dangerouslySetInnerHTML|\.innerHTML\s*=|\.outerHTML\s*=|insertAdjacentHTML|document\.write\(|\beval\(|new Function\(") == []


@pytest.mark.vcase("V31")
def test_v31_access_code_is_kept_in_session_storage_only():
    assert _hits(r"localStorage|document\.cookie|indexedDB|caches\.open") == [], "the access code and results must not be persisted beyond the tab"
    storage = _hits(r"sessionStorage")
    assert storage and all("src/lib/access-code.ts" in hit for hit in storage), f"sessionStorage is used outside lib/access-code.ts: {storage}"
    code_in_url = _hits(r"(searchParams|URLSearchParams|location\.(search|hash)).*(code|token)", re.I)
    assert code_in_url == [], f"the access code must never travel in a URL: {code_in_url}"
    assert _hits(r"console\.(log|info|debug|warn|error)\(.*(accessCode|access_code|Authorization|Bearer)", re.I) == []


@pytest.mark.vcase("V31")
def test_v31_no_secret_or_fixed_code_in_the_frontend_bundle_inputs():
    assert _hits(r"Bearer\s+[A-Za-z0-9_\-]{12,}") == [], "a literal bearer value in frontend source"
    env = _hits(r"process\.env\.(?!NEXT_PUBLIC_API_BASE_URL\b|NODE_ENV\b)[A-Z_]+")
    assert env == [], f"unreviewed environment variables are compiled into the bundle: {env}"
    assert _hits(r"NEXT_PUBLIC_[A-Z_]*(CODE|SECRET|TOKEN|KEY)") == []


@pytest.mark.vcase("V31")
def test_v31_fixture_mode_is_labelled_in_the_shell():
    shell = (FRONTEND / "src" / "components" / "shell" / "AppShell.tsx")
    if not shell.is_file():
        pytest.skip("frontend/src/components/shell/AppShell.tsx is not present (the frontend is mid-migration); re-run the manual review")
    text = shell.read_text()
    assert re.search(r'FIXTURES_LABEL = "Test data', text) and text.count("{FIXTURES_LABEL}") >= 2, "fixture data must be labelled where it is shown"


@pytest.mark.vcase("V31")
@pytest.mark.xfail(strict=True, reason="V31a (preliminary): frontend/src/lib/portfolio.ts previewPurchase computes additional purchase, cash after "
                                       "and insufficient-cash in the browser (BUILD_BRIEF 1: rules are checked using deterministic Python; D5 purchase simulation)")
def test_v31_no_feasibility_arithmetic_in_the_browser():
    assert _hits(r"cash_weight\s*-\s*\w+|target\s*-\s*startingDirect|insufficient_cash:\s*\w+.*<") == []


@pytest.mark.vcase("V31")
@pytest.mark.xfail(strict=True, reason="V31b (preliminary): frontend/src/lib/verdict.ts derives the headline from status counts in the browser "
                                       "instead of rendering summary.headline of the check result (SEMANTICS headline order incl. POLICY_CONFLICT, "
                                       "INVALID_REQUEST, EXECUTION_ERROR)")
def test_v31_the_headline_is_taken_from_the_service_not_recomputed():
    verdict = FRONTEND / "src" / "lib" / "verdict.ts"
    if not verdict.is_file():
        pytest.skip("frontend/src/lib/verdict.ts is not present (the frontend is mid-migration); re-run the manual review")
    text = verdict.read_text()
    assert "summary.headline" in text or "summary?.headline" in text, "the client must render the server's headline"
    assert not re.search(r"if \(fail > 0\)|if \(unknown > 0\)", text), "the client re-derives the verdict from counts"
