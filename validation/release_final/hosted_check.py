#!/usr/bin/env python3
"""Final-integration check of the hosted site and the live API (interpreter workflows A and B, Evidence Investigator
workflows C, D and E, the header link). The access code is read from SSM, kept in memory and handed to the browser
process through its environment only; it is never printed, logged or written to disk.

    AWS_PROFILE=<workshop profile> uv run --no-project --with 'boto3[crt]' python validation/release_final/hosted_check.py
"""
import os
import subprocess
import sys
from pathlib import Path

import boto3

REPO = Path(__file__).resolve().parents[2]
session = boto3.Session(region_name="us-east-1")
assert session.client("sts").get_caller_identity()["Account"] == "010928212265"
stack = session.client("cloudformation").describe_stacks(StackName="before-you-buy")["Stacks"][0]
outputs = {o["OutputKey"]: o["OutputValue"] for o in stack["Outputs"]}
parameters = {p["ParameterKey"]: p.get("ParameterValue") for p in stack["Parameters"]}
print(f"[INFO] stack {stack['StackStatus']}: code {parameters['CodeS3Key']}, snapshot {parameters['DataSnapshotId']}, site {parameters['AllowedOrigin']}")
code = session.client("ssm").get_parameter(Name=outputs["AccessCodeParameterName"], WithDecryption=True)["Parameter"]["Value"]
env = dict(os.environ, BYB_ACCESS_CODE=code, BYB_ORIGIN=parameters["AllowedOrigin"], BYB_API=outputs["ApiBaseUrl"],
           BYB_FRONTEND_DIR=str(REPO / "frontend"), BYB_SHOTS="/tmp/byb-release-final-shots")
sys.exit(subprocess.run(["node", str(Path(__file__).with_name("hosted_check.mjs"))], env=env).returncode)
