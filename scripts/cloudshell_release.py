#!/usr/bin/env python3
"""Run from an unpacked release bundle in AWS CloudShell. No credentials exported.

prepare   uploads immutable artifacts and creates, but never executes, a change set.
status    prints the stack state, its code key and data snapshot, and the planned change set with its parameters.
execute   requires the exact change-set id printed by prepare or rollback, and refuses a change set whose
          code key, data snapshot or allowed origin are not the planned ones.
verify    after UPDATE_COMPLETE: fails unless the stack runs the planned code key and data snapshot.
host      deploys the static site, only when the stack already runs the planned code key and data snapshot
          AND the backend checks (cloudshell_smoke.py, cloudshell_customize_check.py) recorded a pass on exactly
          that backend, so a new frontend is never published in front of an old or unchecked backend.
rollback  creates, but never executes, a change set that puts back a given code key (and, if asked, a data
          snapshot) with the template the stack already has. Review it with status, then run execute.
"""
import argparse
import hashlib
import json
from pathlib import Path
import time
import urllib.request

import boto3

ACCOUNT = "010928212265"
REGION = "us-east-1"
STACK = "before-you-buy"
ARTIFACTS = f"byb-artifacts-{ACCOUNT}-{REGION}"
ROOT = Path(__file__).resolve().parent
PLAN = "release-plan.json"
TRACKED = ("CodeS3Key", "DataSnapshotId", "AllowedOrigin")  # what a release changes, and what every step checks


def save(name, value):
    (ROOT / name).write_text(json.dumps(value, indent=2, default=str))


def load_plan():
    path = ROOT / PLAN
    if not path.exists():
        raise RuntimeError("No release-plan.json here: run prepare (or rollback) first")
    return json.loads(path.read_text())


def stack_parameters(stack):
    return {p["ParameterKey"]: p.get("ParameterValue") for p in stack["Parameters"]}


def planned(plan):
    return {"CodeS3Key": plan["code_key"], "DataSnapshotId": plan["snapshot_id"], "AllowedOrigin": plan["origin"]}


def differences(actual, plan):
    """Tracked parameters whose value is not the planned one, as {name: [actual, planned]}."""
    return {name: [actual.get(name), value] for name, value in planned(plan).items() if actual.get(name) != value}


def missing_backend_checks(plan):
    """The check scripts that have not recorded a pass on the planned code key and data snapshot.

    cloudshell_smoke.py (the existing flow, real model) is required for every plan; cloudshell_customize_check.py
    (customized portfolios, corrected snapshot) for a release. A rollback puts back a backend that predates it.
    """
    path = ROOT / "backend-checks.json"
    notes = json.loads(path.read_text()) if path.exists() else {}
    required = {"smoke": "cloudshell_smoke.py"}
    if plan.get("kind", "release") == "release":
        required["customize"] = "cloudshell_customize_check.py"
    expected = {"code_key": plan["code_key"], "snapshot_id": plan["snapshot_id"]}
    return [script for name, script in required.items() if notes.get(name) != expected]


def new_change_set(cf, name, **kwargs):
    """Create a change set under ``name``; a name already used by an executed or failed change set gets a suffix.

    CloudFormation keeps a change-set name after it was executed, and such a change set can never be executed
    again. Reusing the bundle of an earlier release (for a rollback, or a second attempt) must not stop there.
    """
    try:
        existing = cf.describe_change_set(StackName=STACK, ChangeSetName=name)
    except cf.exceptions.ChangeSetNotFoundException:
        existing = None
    if existing is not None:
        if existing["Status"] in ("CREATE_COMPLETE", "CREATE_IN_PROGRESS", "CREATE_PENDING") and existing["ExecutionStatus"] in ("AVAILABLE", "UNAVAILABLE"):
            return existing["ChangeSetId"]  # the same plan, prepared before and not executed: reuse it
        name = f"{name}-{time.strftime('%Y%m%d%H%M%S', time.gmtime())}"
    return cf.create_change_set(StackName=STACK, ChangeSetName=name, ChangeSetType="UPDATE",
                                Capabilities=["CAPABILITY_IAM", "CAPABILITY_AUTO_EXPAND"], **kwargs)["Id"]


def main(argv=None, session=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=["prepare", "status", "execute", "verify", "host", "rollback"])
    parser.add_argument("--change-set-id")
    parser.add_argument("--code-key", help="rollback: the code key to put back, e.g. lambda/byb-backend-<sha16>.zip")
    parser.add_argument("--snapshot-id", help="rollback: the data snapshot to use (default: keep the one in use)")
    args = parser.parse_args(argv)
    session = session or boto3.Session(region_name=REGION)
    assert session.client("sts").get_caller_identity()["Account"] == ACCOUNT
    cf = session.client("cloudformation")
    stack = cf.describe_stacks(StackName=STACK)["Stacks"][0]
    outputs = {v["OutputKey"]: v["OutputValue"] for v in stack["Outputs"]}
    current = stack_parameters(stack)

    if args.action == "status":
        print(json.dumps({"status": stack["StackStatus"], "running": {name: current.get(name) for name in TRACKED}, "outputs": outputs}))
        if (ROOT / PLAN).exists():
            plan = load_plan()
            change = cf.describe_change_set(ChangeSetName=plan["change_set_id"])
            proposed = {p["ParameterKey"]: p.get("ParameterValue") for p in change.get("Parameters", [])}
            print(json.dumps({"change_set_id": change["ChangeSetId"], "status": change["Status"],
                              "execution": change["ExecutionStatus"], "reason": change.get("StatusReason"),
                              "planned": planned(plan), "change_set_parameters": {name: proposed.get(name) for name in TRACKED},
                              "change_set_differs_from_plan": differences(proposed, plan),
                              "stack_differs_from_plan": differences(current, plan),
                              "changes": [c["ResourceChange"] for c in change.get("Changes", [])]}, default=str))
        return 0

    if args.action == "verify":
        plan = load_plan()
        wrong = differences(current, plan)
        ok = stack["StackStatus"] == "UPDATE_COMPLETE" and not wrong
        print(json.dumps({"verified": ok, "status": stack["StackStatus"], "running": {name: current.get(name) for name in TRACKED},
                          "differs_from_plan": wrong}))
        return 0 if ok else 1

    amplify = session.client("amplify")
    apps = [a for page in amplify.get_paginator("list_apps").paginate() for a in page["apps"] if a["name"] == STACK]
    if len(apps) > 1:
        raise RuntimeError("Multiple hosting apps: select explicitly before proceeding")
    if not apps and args.action != "prepare":
        raise RuntimeError("Run prepare first")
    app = apps[0] if apps else amplify.create_app(name=STACK, platform="WEB")["app"]
    branches = amplify.list_branches(appId=app["appId"])["branches"]
    if not any(b["branchName"] == "main" for b in branches):
        amplify.create_branch(appId=app["appId"], branchName="main", stage="PRODUCTION")
    origin = "https://main." + app["defaultDomain"]

    if args.action == "host":
        plan = load_plan()
        assert stack["StackStatus"] == "UPDATE_COMPLETE", stack["StackStatus"]
        assert current.get("AllowedOrigin") == origin
        # Backend first: this site is only published in front of the backend it was built for.
        wrong = differences(current, plan)
        assert not wrong, f"The stack does not run the planned release (execute it first, then verify): {wrong}"
        # ... and only after the backend checks passed on exactly this code key and data snapshot.
        missing = missing_backend_checks(plan)
        assert not missing, f"Backend checks not passed on this backend yet, run them first: {missing}"
        deployment = amplify.create_deployment(appId=app["appId"], branchName="main")
        request = urllib.request.Request(deployment["zipUploadUrl"], data=(ROOT / "frontend.zip").read_bytes(), method="PUT", headers={"Content-Type": "application/zip"})
        with urllib.request.urlopen(request, timeout=120) as response:
            assert response.status == 200
        job = amplify.start_deployment(appId=app["appId"], branchName="main", jobId=deployment["jobId"])
        print(json.dumps({"origin": origin, "job": job["jobSummary"]}, default=str))
        return 0

    if args.action == "execute":
        plan = load_plan()
        assert args.change_set_id == plan["change_set_id"], "Supply the reviewed change-set ARN"
        change = cf.describe_change_set(ChangeSetName=args.change_set_id)
        assert change["Status"] == "CREATE_COMPLETE" and change["ExecutionStatus"] == "AVAILABLE"
        for c in change["Changes"]:
            resource = c["ResourceChange"]
            assert resource["Action"] != "Remove", resource
            replacement = resource.get("Replacement", "False")
            # SAM may recreate this invocation permission when the API definition changes.
            # This is not replacement of the API, authorizer function, or stored data.
            conditional_permission = (
                resource["LogicalResourceId"] == "HttpApiAccessCodeAuthorizerAuthorizerPermission"
                and resource["ResourceType"] == "AWS::Lambda::Permission"
                and replacement == "Conditional"
            )
            assert replacement == "False" or conditional_permission, resource
        parameters = {p["ParameterKey"]: p.get("ParameterValue") for p in change["Parameters"]}
        assert parameters["AllowedOrigin"] == origin
        wrong = differences(parameters, plan)
        assert not wrong, f"The change set does not carry the planned code key and data snapshot: {wrong}"
        cf.execute_change_set(ChangeSetName=args.change_set_id)
        print("Execution started. Run status until UPDATE_COMPLETE, then verify.")
        return 0

    assert stack["StackStatus"] in ("UPDATE_COMPLETE", "UPDATE_ROLLBACK_COMPLETE")
    s3 = session.client("s3")

    if args.action == "rollback":
        assert args.code_key, "rollback needs --code-key (the key to put back)"
        snapshot_id = args.snapshot_id or current["DataSnapshotId"]
        # Both must already be in S3: nothing is uploaded by a rollback.
        s3.head_object(Bucket=ARTIFACTS, Key=args.code_key)
        s3.head_object(Bucket=outputs["DataBucketName"], Key=f"snapshots/{snapshot_id}/manifest.json")
        save("stack-before-rollback.json", {"parameters": stack["Parameters"], "outputs": outputs})
        overrides = {"CodeS3Key": args.code_key, "DataSnapshotId": snapshot_id}
        parameters = [{"ParameterKey": key, "ParameterValue": overrides[key]} if key in overrides else {"ParameterKey": key, "UsePreviousValue": True}
                      for key in current]
        fingerprint = hashlib.sha256(json.dumps(overrides, sort_keys=True).encode()).hexdigest()[:20]
        change_id = new_change_set(cf, "rollback-" + fingerprint, UsePreviousTemplate=True, Parameters=parameters)
        plan = {"change_set_id": change_id, "origin": origin, "app_id": app["appId"], "snapshot_id": snapshot_id, "code_key": args.code_key,
                "kind": "rollback"}
        save(PLAN, plan)
        print(json.dumps(plan, indent=2))
        print("Rollback prepared only. Review status, then execute, then verify. Put the matching frontend.zip here before host.")
        return 0

    save("previous-stack.json", {"parameters": stack["Parameters"], "outputs": outputs})
    snapshots = [p for p in (ROOT / "snapshots").iterdir() if p.is_dir()]
    codes = sorted(ROOT.glob("byb-backend-*.zip"))
    assert len(snapshots) == 1 and len(codes) == 1, "The bundle must hold exactly one snapshot and one backend zip: extract it into a fresh directory"
    snapshot, code = snapshots[0], codes[0]
    files = sorted(snapshot.rglob("*.json"), key=lambda p: (p.name == "manifest.json", str(p)))
    for path in files:
        key = "snapshots/" + snapshot.name + "/" + path.relative_to(snapshot).as_posix()
        s3.put_object(Bucket=outputs["DataBucketName"], Key=key, Body=path.read_bytes(), ContentType="application/json")
        assert s3.head_object(Bucket=outputs["DataBucketName"], Key=key)["ContentLength"] == path.stat().st_size
    code_key = "lambda/" + code.name
    template = (ROOT / "template.yaml").read_bytes()
    template_key = "templates/template-" + hashlib.sha256(template).hexdigest()[:16] + ".yaml"
    s3.put_object(Bucket=ARTIFACTS, Key=code_key, Body=code.read_bytes())
    s3.put_object(Bucket=ARTIFACTS, Key=template_key, Body=template)
    url = f"https://{ARTIFACTS}.s3.{REGION}.amazonaws.com/{template_key}"
    summary = cf.get_template_summary(TemplateURL=url)
    overrides = {"CodeS3Bucket": ARTIFACTS, "CodeS3Key": code_key, "DataSnapshotId": snapshot.name, "AllowedOrigin": origin}
    previous = set(current)
    parameters = []
    for p in summary["Parameters"]:
        key = p["ParameterKey"]
        if key in overrides:
            parameters.append({"ParameterKey": key, "ParameterValue": overrides[key]})
        elif key in previous:
            parameters.append({"ParameterKey": key, "UsePreviousValue": True})
    fingerprint = hashlib.sha256(json.dumps([template_key, overrides], sort_keys=True).encode()).hexdigest()[:20]
    change_id = new_change_set(cf, "release-" + fingerprint, TemplateURL=url, Parameters=parameters)
    plan = {"change_set_id": change_id, "origin": origin, "app_id": app["appId"], "snapshot_id": snapshot.name, "code_key": code_key,
            "kind": "release", "previous": {name: current.get(name) for name in TRACKED}}
    save(PLAN, plan)
    print(json.dumps(plan, indent=2))
    print("Prepared only. Review status and permissions before execute.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
