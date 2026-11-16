"""infra/template.yaml checked as text (no YAML dependency): routes, configuration, least privilege, timeouts.

Nothing here talks to AWS. The template is not deployed by this change; these tests keep it consistent with the code.
"""

import re

import pytest
from byb_contracts.constants import INTERPRET_TIMEOUT_SECONDS, INVESTIGATION_DEADLINE_SECONDS

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
                      "POST /investigations", "GET /investigations/{id}", "POST /investigations/{id}/challenge",
                      "POST /evidence/investigate"}
    api = Api(store=None, policies=None, snapshots=None, lambda_client=None, config=None, clock=None)
    assert set(api._routes) == routes
    assert "$default" not in block("ApiFunction") and len(re.findall(r"^ {12}PayloadFormatVersion: \"2\.0\"$", TEMPLATE, re.M)) == 8
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
    # The API function outlasts the interpreter's 20 s server deadline (so the handler, not Lambda, answers 504) and
    # stays under the 30 s HTTP API integration limit; only the two interpreter entry points get the longer integration.
    assert INTERPRET_TIMEOUT_SECONDS < api_timeout < 29
    integration = {route: int(block("ApiFunction").split(f"        {route}:", 1)[1].split("TimeoutInMillis: ", 1)[1].split("\n", 1)[0])
                   for route in ("CreateInvestigation", "GetInvestigation", "ChallengeInvestigation", "GetPortfolio", "InterpretRules", "ConfirmRules", "Check")}
    assert {route for route, millis in integration.items() if millis != 20000} == {"InterpretRules", "ChallengeInvestigation"}
    assert all(api_timeout * 1000 < integration[route] <= 30000 for route in ("InterpretRules", "ChallengeInvestigation"))
    from backend.api import handler

    assert handler.INTERPRETER_CALL_BUDGET_SECONDS < INTERPRET_TIMEOUT_SECONDS
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
                        "UpdateJobOnlyByCompareAndSwap", "ListJobsAndPoliciesPrefixesOnly", "DispatchToWorkerOnly",
                        "InterpreterConverseThroughInferenceProfile", "InterpreterRoutedFoundationModelsOnlyViaThatProfile"}
    assert set(re.findall(r"\$\{DataBucket\.Arn\}/(\w+)/\*", api["ReadJobsResultsPoliciesAndSnapshots"])) == {"jobs", "results", "policies", "snapshots"}
    assert "policies/*" in api["CreatePolicyVersionOnlyIfAbsent"] and "if-none-match" in api["CreatePolicyVersionOnlyIfAbsent"]
    assert re.findall(r"^ {22}- (\S+)$", api["ListJobsAndPoliciesPrefixesOnly"], re.M) == ["jobs/*", "policies/*"]
    assert "traces" not in "".join(api.values())
    # Bedrock for the rule interpreter only: Converse (InvokeModel) through the one inference profile, exactly as the worker.
    worker = statements("WorkerFunctionRole")
    for mine, theirs in (("InterpreterConverseThroughInferenceProfile", "ConverseThroughInferenceProfile"),
                         ("InterpreterRoutedFoundationModelsOnlyViaThatProfile", "RoutedFoundationModelsOnlyViaThatProfile")):
        assert api[mine].split("\n", 1)[1] == worker[theirs].split("\n", 1)[1]
    assert sorted(sid for sid, text in api.items() if "bedrock" in text) == ["InterpreterConverseThroughInferenceProfile", "InterpreterRoutedFoundationModelsOnlyViaThatProfile"]
    assert "InvokeModelWithResponseStream" not in block("ApiFunctionRole") and 'INTERPRETER_ENABLED: "true"' in block("ApiFunction")
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
    # the interpreter route calls the model: throttled, and no looser than the investigation routes
    interpret = block("ApiFunction").split("        InterpretRules:", 1)[1].split("        ConfirmRules:", 1)[0]
    assert "ThrottlingRateLimit: 2" in interpret and "ThrottlingBurstLimit: 5" in interpret
    assert "PublicAccessBlockConfiguration" in block("DataBucket") and block("DataBucket").count(": true") == 4


def test_tp09_a_rotated_access_code_stops_working_within_the_function_cache_only():
    """API Gateway caches no authorizer answer (it was 300 s), so the only delay is the function's own cache of the code."""
    assert re.findall(r"^\s+ReauthorizeEvery: (\d+)$", TEMPLATE, re.M) == ["0"]
    seconds = int(re.search(r'ACCESS_CODE_CACHE_SECONDS: "(\d+)"', block("AuthorizerFunction")).group(1))
    assert 0 < seconds <= 60
    from backend.common.config import AuthorizerConfig

    assert AuthorizerConfig(parameter_name="/p").cache_ttl_seconds <= 60
    assert AuthorizerConfig.from_env({"ACCESS_CODE_PARAMETER_NAME": "/p", "ACCESS_CODE_CACHE_SECONDS": str(seconds)}).cache_ttl_seconds == seconds
    with pytest.raises(Exception):  # a cache long enough to defeat rotation is a configuration error
        AuthorizerConfig.from_env({"ACCESS_CODE_PARAMETER_NAME": "/p", "ACCESS_CODE_CACHE_SECONDS": "900"})
    # The identity source stays, so a request without the header is refused by API Gateway without invoking anything.
    assert "- Authorization" in block("HttpApi") and "EnableSimpleResponses: true" in block("HttpApi")
    deploy_guide = (REPO_ROOT / "scripts" / "deploy.md").read_text(encoding="utf-8")
    assert f"{seconds} seconds" in deploy_guide and "ReauthorizeEvery" in deploy_guide


def test_tp09b_the_authorizer_really_drops_the_old_code_after_its_cache():
    from backend.api.authorizer import AccessCodeAuthorizer
    from backend.common.config import AuthorizerConfig
    from service_fakes import FakeClock, FakeSSM

    old, new = "old-access-code-0123456789", "new-access-code-9876543210"
    ssm, clock = FakeSSM(old), FakeClock()
    authorizer = AccessCodeAuthorizer(ssm, AuthorizerConfig(parameter_name="/p"), clock)

    def allowed(code):
        return authorizer.authorize({"routeKey": "POST /check", "identitySource": [f"Bearer {code}"]})["isAuthorized"]

    assert allowed(old) and not allowed(new)
    ssm.value = new  # rotation
    clock.advance(AuthorizerConfig(parameter_name="/p").cache_ttl_seconds + 1)
    assert not allowed(old) and allowed(new)


def _deploy_functions():
    """The pure helpers of the deploy snippet (the snippet itself runs only inside the AWS MCP sandbox)."""
    import ast

    source = (REPO_ROOT / "scripts" / "mcp" / "02_deploy.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    wanted = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in ("effective_parameter", "origin_refusal")]
    namespace: dict = {}
    exec(compile(ast.Module(body=wanted, type_ignores=[]), "02_deploy.py", "exec"), namespace)  # noqa: S102 - our own two pure functions
    return source, namespace["effective_parameter"], namespace["origin_refusal"]


def test_tp10_a_wildcard_cors_origin_is_never_deployed_by_default():
    source, effective_parameter, origin_refusal = _deploy_functions()
    # Validator finding F-08: the parameter has no default, so no deployment gets "*" without someone typing it.
    parameter = TEMPLATE.split("  AllowedOrigin:\n", 1)[1].split("  AccessCodeParameterName:", 1)[0]
    assert "Default:" not in parameter and "exact origin" in parameter
    pattern = re.compile(re.search(r"AllowedPattern: (\S+)", parameter).group(1).replace("\\\\", "\\"))
    for good in ("https://main.d1example.amplifyapp.com", "http://localhost:5173", "http://127.0.0.1:5173", "*"):
        assert pattern.fullmatch(good), good
    for bad in ("", "https://*.amplifyapp.com", "https://a.example/", "https://a.example/path", "http://example.org", "null", "* ", "https://a.example,https://b.example"):
        assert not pattern.fullmatch(bad), bad
    assert re.search(r"^ALLOW_WILDCARD_ORIGIN = False$", source, re.M) and re.search(r"^EXECUTE = False$", source, re.M)
    assert 'if EXECUTE and report["cors_refusal"]:' in source  # checked before ExecuteChangeSet
    assert source.index('if EXECUTE and report["cors_refusal"]:') < source.index('"ExecuteChangeSet"')

    template_parameters = [{"ParameterKey": "AllowedOrigin"}, {"ParameterKey": "DataSnapshotId"}]
    older_template = [{"ParameterKey": "AllowedOrigin", "DefaultValue": "*"}, {"ParameterKey": "DataSnapshotId"}]
    deployed = [{"ParameterKey": "AllowedOrigin", "ParameterValue": "*"}]
    origin = "https://main.d1example.amplifyapp.com"
    # a first deploy that does not state the origin has no value at all, and that is refused too
    assert effective_parameter("AllowedOrigin", {}, None, template_parameters) is None and origin_refusal(None, True)
    # an older template's default, an update keeping the deployed "*", explicit "*": all refused unless allowed on purpose
    for value in (effective_parameter("AllowedOrigin", {}, None, older_template),
                  effective_parameter("AllowedOrigin", {}, deployed, template_parameters),
                  effective_parameter("AllowedOrigin", {"AllowedOrigin": "*"}, deployed, template_parameters)):
        assert value == "*" and "NOT EXECUTED" in origin_refusal(value, False) and origin_refusal(value, True) is None
    assert effective_parameter("AllowedOrigin", {"AllowedOrigin": origin}, deployed, template_parameters) == origin
    assert origin_refusal(origin, False) is None and origin_refusal("http://localhost:5173", False) is None
    assert origin_refusal("http://example.org", False) and origin_refusal("", False) and origin_refusal(None, False)
    # a parameter without default and without previous value is reported as missing before any change set is created
    assert effective_parameter("DataSnapshotId", {}, deployed, []) is None
    assert effective_parameter("DataSnapshotId", {"DataSnapshotId": "snap-2026-11-12-0123456789ab"}, deployed, []) == "snap-2026-11-12-0123456789ab"
