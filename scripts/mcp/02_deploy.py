# Sandbox snippet for the AWS MCP tool (run_script). Not a local script.
#
# Deploys infra/template.yaml as stack "before-you-buy" through a CloudFormation
# change set (the AWS::Serverless transform runs server-side, no SAM CLI).
#
# Before running: build the zip (scripts/package.py), upload the zip and the
# template to the artifacts bucket through presigned URLs (scripts/deploy.md),
# then set CODE_KEY and TEMPLATE_KEY below.
#
#   EXECUTE = False  -> create the change set, show validation results and the
#                       planned changes, stop.
#   EXECUTE = True   -> same, then execute it (re-uses the change set if it
#                       already exists) and wait for the stack.

ACCOUNT = "010928212265"
REGION = "us-east-1"
STACK = "before-you-buy"
ARTIFACTS_BUCKET = f"byb-artifacts-{ACCOUNT}-{REGION}"
CODE_KEY = "lambda/byb-backend-5cf91f80c5c1a2ce.zip"
TEMPLATE_KEY = "templates/template-e076af541c8b13f5.yaml"
PARAMETER_OVERRIDES = {}  # for example {"AllowedOrigin": "https://main.example.amplifyapp.com"}
EXECUTE = False
WAIT_SECONDS = 100

TEMPLATE_URL = f"https://{ARTIFACTS_BUCKET}.s3.{REGION}.amazonaws.com/{TEMPLATE_KEY}"
CHANGE_SET = "byb-" + TEMPLATE_KEY.rsplit("-", 1)[-1].split(".")[0] + "-" + CODE_KEY.rsplit("-", 1)[-1].split(".")[0]
TERMINAL = {
    "CREATE_COMPLETE", "CREATE_FAILED", "ROLLBACK_COMPLETE", "ROLLBACK_FAILED",
    "UPDATE_COMPLETE", "UPDATE_ROLLBACK_COMPLETE", "UPDATE_ROLLBACK_FAILED", "UPDATE_FAILED", "DELETE_COMPLETE",
}


async def aws(service, operation, **params):
    return await call_boto3(service_name=service, operation_name=operation, region_name=REGION, params=params)


async def stack_or_none():
    try:
        return (await aws("cloudformation", "DescribeStacks", StackName=STACK))["Stacks"][0]
    except Exception as error:
        if "does not exist" in str(error):
            return None
        raise


identity = await aws("sts", "GetCallerIdentity")
if identity.get("Account") != ACCOUNT:
    raise RuntimeError("Refusing to continue: this is not the authorized account.")

report = {"stack": STACK, "change_set": CHANGE_SET, "template_url": TEMPLATE_URL, "code_key": CODE_KEY}
for key in (CODE_KEY, TEMPLATE_KEY):
    head = await aws("s3", "HeadObject", Bucket=ARTIFACTS_BUCKET, Key=key)
    report.setdefault("artifacts", {})[key] = head.get("ContentLength")

stack = await stack_or_none()
change_set_type = "CREATE" if stack is None or stack["StackStatus"] == "REVIEW_IN_PROGRESS" else "UPDATE"
report["change_set_type"] = change_set_type
report["stack_status_before"] = stack["StackStatus"] if stack else None

values = {"CodeS3Bucket": ARTIFACTS_BUCKET, "CodeS3Key": CODE_KEY, **PARAMETER_OVERRIDES}
summary = await aws("cloudformation", "GetTemplateSummary", TemplateURL=TEMPLATE_URL)
previous = {p["ParameterKey"] for p in (stack or {}).get("Parameters", [])}
parameters = []
for declared in summary.get("Parameters", []):
    name = declared["ParameterKey"]
    if name in values:
        parameters.append({"ParameterKey": name, "ParameterValue": values[name]})
    elif change_set_type == "UPDATE" and name in previous:
        parameters.append({"ParameterKey": name, "UsePreviousValue": True})

try:
    described = await aws("cloudformation", "DescribeChangeSet", StackName=STACK, ChangeSetName=CHANGE_SET)
    report["change_set_action"] = "re-used"
except Exception as error:
    if "not found" not in str(error).lower() and "does not exist" not in str(error).lower():
        raise
    await aws(
        "cloudformation",
        "CreateChangeSet",
        StackName=STACK,
        ChangeSetName=CHANGE_SET,
        ChangeSetType=change_set_type,
        TemplateURL=TEMPLATE_URL,
        Parameters=parameters,
        Capabilities=["CAPABILITY_IAM", "CAPABILITY_AUTO_EXPAND"],
        Tags=[{"Key": "project", "Value": "before-you-buy"}],
        Description="Before You Buy backend: " + CODE_KEY,
    )
    report["change_set_action"] = "created"
    described = await aws("cloudformation", "DescribeChangeSet", StackName=STACK, ChangeSetName=CHANGE_SET)

for _ in range(40):
    if described["Status"] in ("CREATE_COMPLETE", "FAILED"):
        break
    await asyncio.sleep(3)
    described = await aws("cloudformation", "DescribeChangeSet", StackName=STACK, ChangeSetName=CHANGE_SET)
report["change_set_status"] = described["Status"]
report["change_set_status_reason"] = described.get("StatusReason")
report["execution_status"] = described.get("ExecutionStatus")
report["changes"] = [
    f'{c["ResourceChange"]["Action"]} {c["ResourceChange"]["ResourceType"]} {c["ResourceChange"]["LogicalResourceId"]}'
    + (f' (replacement: {c["ResourceChange"].get("Replacement")})' if c["ResourceChange"]["Action"] == "Modify" else "")
    for c in described.get("Changes", [])
]

# Pre-deployment validation results are only visible through DescribeEvents.
try:
    events = await aws("cloudformation", "DescribeEvents", ChangeSetName=described["ChangeSetId"])
    validations = [e for e in events.get("OperationEvents", []) if e.get("ValidationStatus") or e.get("ValidationName")]
    report["validation_events"] = [
        {k: e.get(k) for k in ("LogicalResourceId", "ValidationName", "ValidationStatus", "ValidationStatusReason", "ValidationPath", "ValidationFailureMode") if e.get(k)}
        for e in validations
    ]
    report["validation_event_count"] = len(validations)
    report["operation_event_count"] = len(events.get("OperationEvents", []))
except Exception as error:
    report["validation_events_error"] = str(error)[:300]

failed_validation = any(v.get("ValidationStatus") == "FAILED" for v in report.get("validation_events", []))
if EXECUTE and described["Status"] == "CREATE_COMPLETE" and described.get("ExecutionStatus") == "AVAILABLE" and not failed_validation:
    await aws("cloudformation", "ExecuteChangeSet", StackName=STACK, ChangeSetName=CHANGE_SET)
    report["executed"] = True
    waited = 0
    while waited < WAIT_SECONDS:
        await asyncio.sleep(5)
        waited += 5
        stack = await stack_or_none()
        # Match the change set id: right after ExecuteChangeSet the stack can still show its previous terminal status.
        if stack and stack.get("ChangeSetId") == described["ChangeSetId"] and stack["StackStatus"] in TERMINAL:
            break
    report["waited_seconds"] = waited
    report["stack_status"] = stack["StackStatus"] if stack else None
    report["stack_status_reason"] = (stack or {}).get("StackStatusReason")
    report["stack_last_updated"] = str((stack or {}).get("LastUpdatedTime"))
else:
    report["executed"] = False
result = report
result
