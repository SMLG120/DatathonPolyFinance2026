"""The CloudShell release helper (scripts/cloudshell_release.py), against in-memory fakes. No AWS call is made.

What must hold whatever the operator types:
  * a change set is executed only if it carries the planned code key, data snapshot and origin;
  * the site is published only in front of the backend it was built for (backend first);
  * ``verify`` fails when the stack does not run the planned code key and data snapshot;
  * a change-set name that was already executed never blocks a new attempt;
  * ``rollback`` prepares a change set and executes nothing.
"""

import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
ORIGIN = "https://main.example.amplifyapp.com"
OLD = {"CodeS3Key": "lambda/byb-backend-old0000000000000.zip", "DataSnapshotId": "snap-2026-11-12-aaaaaaaaaaaa", "AllowedOrigin": ORIGIN,
       "BedrockModelId": "model-x", "CodeS3Bucket": "byb-artifacts-010928212265-us-east-1"}
NEW_CODE, NEW_SNAPSHOT = "lambda/byb-backend-new1111111111111.zip", "snap-2026-11-12-bbbbbbbbbbbb"


class NotFound(Exception):
    pass


class FakeCloudFormation:
    class exceptions:  # noqa: N801 - mirrors the boto3 client attribute
        ChangeSetNotFoundException = NotFound

    def __init__(self, parameters, status="UPDATE_COMPLETE"):
        self.parameters, self.status = dict(parameters), status
        self.change_sets, self.executed, self.created = {}, [], []

    def describe_stacks(self, StackName):
        return {"Stacks": [{"StackStatus": self.status, "Outputs": [{"OutputKey": "DataBucketName", "OutputValue": "data-bucket"}],
                            "Parameters": [{"ParameterKey": k, "ParameterValue": v} for k, v in self.parameters.items()]}]}

    def describe_change_set(self, ChangeSetName, StackName=None):
        for change in self.change_sets.values():
            if ChangeSetName in (change["ChangeSetId"], change["ChangeSetName"]):
                return change
        raise NotFound(ChangeSetName)

    def create_change_set(self, **kwargs):
        self.created.append(kwargs)
        resolved = dict(self.parameters)
        for parameter in kwargs["Parameters"]:
            if "ParameterValue" in parameter:
                resolved[parameter["ParameterKey"]] = parameter["ParameterValue"]
        change_id = f"arn:aws:cloudformation:us-east-1:010928212265:changeSet/{kwargs['ChangeSetName']}/id"
        self.change_sets[change_id] = {
            "ChangeSetId": change_id, "ChangeSetName": kwargs["ChangeSetName"], "Status": "CREATE_COMPLETE", "ExecutionStatus": "AVAILABLE",
            "Parameters": [{"ParameterKey": k, "ParameterValue": v} for k, v in resolved.items()],
            "Changes": [{"ResourceChange": {"Action": "Modify", "LogicalResourceId": "ApiFunction", "ResourceType": "AWS::Lambda::Function",
                                            "Replacement": "False"}}]}
        return {"Id": change_id}

    def execute_change_set(self, ChangeSetName):
        self.executed.append(ChangeSetName)

    def get_template_summary(self, TemplateURL):
        return {"Parameters": [{"ParameterKey": k} for k in self.parameters]}


class FakeAmplify:
    def __init__(self):
        self.deployments = []

    def get_paginator(self, _name):
        class Pages:
            @staticmethod
            def paginate():
                return [{"apps": [{"name": "before-you-buy", "appId": "app1", "defaultDomain": "example.amplifyapp.com"}]}]
        return Pages()

    def list_branches(self, appId):
        return {"branches": [{"branchName": "main"}]}

    def create_deployment(self, **kwargs):
        self.deployments.append(kwargs)
        raise AssertionError("the test must stop before a deployment is created")


class FakeS3:
    def __init__(self, keys=()):
        self.keys, self.puts = set(keys), []

    def put_object(self, Bucket, Key, Body, **_):
        self.puts.append((Bucket, Key))
        self.keys.add((Bucket, Key))
        self._sizes = getattr(self, "_sizes", {})
        self._sizes[(Bucket, Key)] = len(Body)

    def head_object(self, Bucket, Key):
        if (Bucket, Key) not in self.keys:
            raise NotFound(f"{Bucket}/{Key}")
        return {"ContentLength": getattr(self, "_sizes", {}).get((Bucket, Key), 0)}


class FakeSession:
    def __init__(self, cf, s3=None):
        self.cf, self.amplify, self.s3 = cf, FakeAmplify(), s3 or FakeS3()

    def client(self, name):
        if name == "sts":
            class Sts:
                @staticmethod
                def get_caller_identity():
                    return {"Account": "010928212265"}
            return Sts()
        return {"cloudformation": self.cf, "amplify": self.amplify, "s3": self.s3}[name]


@pytest.fixture
def helper(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("cloudshell_release_under_test", REPO / "scripts" / "cloudshell_release.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    return module


def bundle(root, code=NEW_CODE, snapshot=NEW_SNAPSHOT):
    (root / "snapshots" / snapshot).mkdir(parents=True)
    (root / "snapshots" / snapshot / "manifest.json").write_text("{}")
    (root / code.split("/")[1]).write_bytes(b"zip")
    (root / "template.yaml").write_text("Resources: {}")


def plan_of(root):
    return json.loads((root / "release-plan.json").read_text())


def test_prepare_then_execute_then_verify_and_only_then_host(helper, tmp_path, capsys):
    bundle(tmp_path)
    cf = FakeCloudFormation(OLD)
    session = FakeSession(cf)
    assert helper.main(["prepare"], session) == 0
    plan = plan_of(tmp_path)
    assert (plan["code_key"], plan["snapshot_id"], plan["origin"]) == (NEW_CODE, NEW_SNAPSHOT, ORIGIN)
    assert plan["previous"] == {"CodeS3Key": OLD["CodeS3Key"], "DataSnapshotId": OLD["DataSnapshotId"], "AllowedOrigin": ORIGIN}
    assert cf.executed == [], "prepare never executes"

    # Backend first: the stack still runs the old release, so the site is refused and verify fails.
    (tmp_path / "frontend.zip").write_bytes(b"site")
    with pytest.raises(AssertionError, match="does not run the planned release"):
        helper.main(["host"], session)
    assert session.amplify.deployments == []
    assert helper.main(["verify"], session) == 1

    assert helper.main(["execute", "--change-set-id", plan["change_set_id"]], session) == 0
    assert cf.executed == [plan["change_set_id"]]
    cf.parameters.update(CodeS3Key=NEW_CODE, DataSnapshotId=NEW_SNAPSHOT)  # what CloudFormation does on completion
    capsys.readouterr()
    assert helper.main(["verify"], session) == 0
    assert json.loads(capsys.readouterr().out)["differs_from_plan"] == {}

    # The right backend is running, but it has not been checked yet: still no site.
    with pytest.raises(AssertionError, match="Backend checks not passed"):
        helper.main(["host"], session)
    passed = {"code_key": NEW_CODE, "snapshot_id": NEW_SNAPSHOT}
    (tmp_path / "backend-checks.json").write_text(json.dumps({"smoke": passed, "customize": dict(passed, snapshot_id=OLD["DataSnapshotId"])}))
    with pytest.raises(AssertionError, match="cloudshell_customize_check.py"):  # a pass on another snapshot does not count
        helper.main(["host"], session)
    (tmp_path / "backend-checks.json").write_text(json.dumps({"smoke": passed, "customize": passed}))
    with pytest.raises(AssertionError, match="the test must stop before a deployment is created"):  # every gate is open now
        helper.main(["host"], session)
    assert len(session.amplify.deployments) == 1
    capsys.readouterr()
    assert helper.main(["status"], session) == 0
    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert lines[0]["running"] == {"CodeS3Key": NEW_CODE, "DataSnapshotId": NEW_SNAPSHOT, "AllowedOrigin": ORIGIN}
    assert lines[1]["change_set_parameters"]["DataSnapshotId"] == NEW_SNAPSHOT and lines[1]["stack_differs_from_plan"] == {}


@pytest.mark.parametrize("name, value", [("DataSnapshotId", "snap-2026-11-12-cccccccccccc"), ("CodeS3Key", "lambda/byb-backend-other.zip")])
def test_execute_refuses_a_change_set_that_does_not_carry_the_planned_snapshot_or_code(helper, tmp_path, name, value):
    bundle(tmp_path)
    cf = FakeCloudFormation(OLD)
    session = FakeSession(cf)
    helper.main(["prepare"], session)
    plan = plan_of(tmp_path)
    for parameter in cf.change_sets[plan["change_set_id"]]["Parameters"]:
        if parameter["ParameterKey"] == name:
            parameter["ParameterValue"] = value
    with pytest.raises(AssertionError, match="does not carry the planned"):
        helper.main(["execute", "--change-set-id", plan["change_set_id"]], session)
    assert cf.executed == []


def test_a_change_set_name_that_was_already_executed_does_not_block_a_new_attempt(helper, tmp_path):
    bundle(tmp_path)
    cf = FakeCloudFormation(OLD)
    session = FakeSession(cf)
    helper.main(["prepare"], session)
    first = plan_of(tmp_path)["change_set_id"]
    cf.change_sets[first].update(Status="CREATE_COMPLETE", ExecutionStatus="EXECUTE_COMPLETE")
    helper.main(["prepare"], session)
    second = plan_of(tmp_path)["change_set_id"]
    assert second != first and cf.change_sets[second]["ExecutionStatus"] == "AVAILABLE"
    helper.main(["prepare"], session)
    assert plan_of(tmp_path)["change_set_id"] == second, "an unexecuted change set of the same plan is reused"


def test_prepare_refuses_a_directory_with_two_snapshots(helper, tmp_path):
    bundle(tmp_path)
    (tmp_path / "snapshots" / "snap-2026-11-12-dddddddddddd").mkdir()
    with pytest.raises(AssertionError, match="exactly one snapshot"):
        helper.main(["prepare"], FakeSession(FakeCloudFormation(OLD)))


def test_rollback_prepares_the_previous_code_on_the_snapshot_in_use_and_executes_nothing(helper, tmp_path):
    running = dict(OLD, CodeS3Key=NEW_CODE, DataSnapshotId=NEW_SNAPSHOT)
    cf = FakeCloudFormation(running)
    s3 = FakeS3({("byb-artifacts-010928212265-us-east-1", OLD["CodeS3Key"]), ("data-bucket", f"snapshots/{NEW_SNAPSHOT}/manifest.json")})
    session = FakeSession(cf, s3)
    assert helper.main(["rollback", "--code-key", OLD["CodeS3Key"]], session) == 0
    plan = plan_of(tmp_path)
    assert (plan["kind"], plan["code_key"], plan["snapshot_id"]) == ("rollback", OLD["CodeS3Key"], NEW_SNAPSHOT), "the data snapshot is kept"
    (created,) = cf.created
    assert created["UsePreviousTemplate"] is True and "TemplateURL" not in created
    sent = {p["ParameterKey"]: p for p in created["Parameters"]}
    assert sent["CodeS3Key"]["ParameterValue"] == OLD["CodeS3Key"] and sent["DataSnapshotId"]["ParameterValue"] == NEW_SNAPSHOT
    assert sent["AllowedOrigin"] == {"ParameterKey": "AllowedOrigin", "UsePreviousValue": True}
    assert cf.executed == [] and s3.puts == [], "a rollback uploads nothing and executes nothing"
    assert helper.main(["execute", "--change-set-id", plan["change_set_id"]], session) == 0


def test_rollback_refuses_a_code_key_or_snapshot_that_is_not_in_s3(helper, tmp_path):
    cf = FakeCloudFormation(dict(OLD, CodeS3Key=NEW_CODE))
    with pytest.raises(NotFound):
        helper.main(["rollback", "--code-key", "lambda/byb-backend-missing.zip"], FakeSession(cf))
    assert cf.created == []
