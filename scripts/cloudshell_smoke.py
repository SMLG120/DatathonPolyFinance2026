#!/usr/bin/env python3
"""Verify the deployed Mateo flow with a real model; run inside the release bundle.

The existing SSM code stays in memory, is never printed or passed as a CLI argument.
"""
import boto3
import live_check


def main():
    session = boto3.Session(region_name="us-east-1")
    assert session.client("sts").get_caller_identity()["Account"] == "010928212265"
    stack = session.client("cloudformation").describe_stacks(StackName="before-you-buy")["Stacks"][0]
    outputs = {o["OutputKey"]: o["OutputValue"] for o in stack["Outputs"]}
    parameters = {p["ParameterKey"]: p.get("ParameterValue") for p in stack["Parameters"]}
    code = session.client("ssm").get_parameter(Name=outputs["AccessCodeParameterName"], WithDecryption=True)["Parameter"]["Value"]
    lines = []

    def report(line):
        lines.append(line)
        print(line, flush=True)

    result = live_check.main(["--base-url", outputs["ApiBaseUrl"], "--require-interpreter"],
                             environ={"BYB_ACCESS_CODE": code}, out=report)
    if result:
        return result
    if not any("agent mode MODEL" in line for line in lines):
        print("FAILED: the investigation did not demonstrate MODEL mode. A fallback is not a real-agent success.")
        return 1
    record_pass("smoke", parameters)
    print("PASS: interpreter and investigation ran against AWS; investigation used MODEL mode.")
    return 0


def record_pass(name, parameters):
    """Leave a note that this check passed on exactly this backend; `cloudshell_release.py host` requires it."""
    import json
    from pathlib import Path

    path = Path(__file__).resolve().parent / "backend-checks.json"
    notes = json.loads(path.read_text()) if path.exists() else {}
    notes[name] = {"code_key": parameters.get("CodeS3Key"), "snapshot_id": parameters.get("DataSnapshotId")}
    path.write_text(json.dumps(notes, indent=2))


if __name__ == "__main__":
    raise SystemExit(main())
