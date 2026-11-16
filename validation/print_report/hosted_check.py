#!/usr/bin/env python3
"""Check "Print / Save as PDF" on the hosted site in a real browser, after a frontend release.

The access code is read from SSM, kept in memory and handed to the browser process through its environment only; it
is never printed, logged or written to disk. The check creates fictional policies and investigations, as any visitor
does; it changes no configuration. PDFs are written to BYB_PDF_DIR (default: a temporary directory), never into the
repository.

    python3 validation/print_report/hosted_check.py
"""
import os
import subprocess
import sys
import tempfile
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
pdf_dir = os.environ.get("BYB_PDF_DIR") or tempfile.mkdtemp(prefix="byb-hosted-pdf-")
env = dict(os.environ, BYB_ACCESS_CODE=code, BYB_ORIGIN=parameters["AllowedOrigin"], BYB_PDF_DIR=pdf_dir,
           BYB_FRONTEND_DIR=os.environ.get("BYB_FRONTEND_DIR", str(REPO / "frontend")))
sys.exit(subprocess.run(["node", str(Path(__file__).with_name("hosted_check.mjs"))], env=env).returncode)
