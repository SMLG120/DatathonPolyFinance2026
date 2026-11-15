# Sandbox snippet for the AWS MCP tool (run_script). Not a local script.
#
# Waits for the stack to settle, then prints its status, outputs and - if
# anything failed - the failing events (root causes first).

ACCOUNT = "010928212265"
REGION = "us-east-1"
STACK = "before-you-buy"
WAIT_SECONDS = 100
SETTLED = ("_COMPLETE", "_FAILED")


async def aws(service, operation, **params):
    return await call_boto3(service_name=service, operation_name=operation, region_name=REGION, params=params)


identity = await aws("sts", "GetCallerIdentity")
if identity.get("Account") != ACCOUNT:
    raise RuntimeError("Refusing to continue: this is not the authorized account.")

waited = 0
while True:
    stack = (await aws("cloudformation", "DescribeStacks", StackName=STACK))["Stacks"][0]
    if stack["StackStatus"].endswith(SETTLED) or waited >= WAIT_SECONDS:
        break
    await asyncio.sleep(5)
    waited += 5

report = {
    "stack_status": stack["StackStatus"],
    "stack_status_reason": stack.get("StackStatusReason"),
    "outputs": {o["OutputKey"]: o["OutputValue"] for o in stack.get("Outputs", [])},
    "parameters": {p["ParameterKey"]: p.get("ParameterValue") for p in stack.get("Parameters", [])},
}
events = (await aws("cloudformation", "DescribeStackEvents", StackName=STACK)).get("StackEvents", [])
failed = [e for e in events if "FAILED" in e.get("ResourceStatus", "")]
report["failed_events_oldest_first"] = [
    f'{e["Timestamp"]} {e["LogicalResourceId"]} ({e["ResourceType"]}) {e["ResourceStatus"]}: {str(e.get("ResourceStatusReason"))[:500]}'
    for e in reversed(failed)
][:12]
resources = (await aws("cloudformation", "ListStackResources", StackName=STACK)).get("StackResourceSummaries", [])
report["resources"] = [f'{r["LogicalResourceId"]} {r["ResourceType"]} {r["ResourceStatus"]}' for r in resources]
result = report
result
