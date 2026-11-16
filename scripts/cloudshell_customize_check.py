#!/usr/bin/env python3
"""API-level check of a release that carries "Customize this profile" and the corrected data snapshot.

Run inside the release bundle in CloudShell, AFTER the backend change set is UPDATE_COMPLETE and BEFORE the
frontend is published:

    python3 cloudshell_customize_check.py

It reads the API URL from the stack outputs and the access code from SSM; the code stays in memory and is
never printed or passed on a command line. Against another deployment (the local harness, for example):

    BYB_ACCESS_CODE=... python3 cloudshell_customize_check.py --base-url http://127.0.0.1:4184

What it proves, with requests only (fictional portfolios, no advice, no trade):
  1. Amira's scenario is served.
  2. The data snapshot in use is the corrected one: XIU.TO holdings are dated on or before the valuation date
     and Robert's NVIDIA upper bound is the figure of that file.
  3. A customized portfolio is checked as sent: its own portfolio id, its own cash, the user-entered note.
  4. A portfolio whose weights do not total 100% is refused and nothing is calculated.
  5. A real investigation on a customized portfolio succeeds and the job stores that portfolio.
Exit status 0 only if every check passes.
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid

REGION = "us-east-1"
ACCOUNT = "010928212265"
STACK = "before-you-buy"
EXPECTED_SNAPSHOT_FIGURE = 0.262763304   # Robert, NVDA to 25%: upper bound with XIU.TO as of 2026-11-12 (coverage 0.9977)
LOOK_AHEAD_FIGURE = 0.262803304          # the same bound on the snapshot built from the file dated 2026-11-13
CUSTOM = {"cash_weight": 0.2, "positions": [{"instrument_id": "XBB.TO", "weight": 0.3}, {"instrument_id": "SPY", "weight": 0.3},
                                            {"instrument_id": "NVDA", "weight": 0.2}]}
NOTE = "entered by the user in a customized fictional portfolio"
POLL_SECONDS, DEADLINE_SECONDS = 1.5, 170


class Client:
    def __init__(self, base_url, code):
        self._base, self._code = base_url.rstrip("/"), code

    def call(self, method, path, body=None, key=None):
        headers = {"Authorization": "Bearer " + self._code}
        data = None
        if body is not None:
            data, headers["Content-Type"] = json.dumps(body).encode("utf-8"), "application/json"
        if key:
            headers["Idempotency-Key"] = key
        request = urllib.request.Request(self._base + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=40) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            text = error.read().decode("utf-8", errors="replace")
            try:
                return error.code, json.loads(text)
            except ValueError:
                return error.code, {"raw": text[:200]}


def run(client, out=print):
    failures = []

    def check(ok, label, detail=""):
        out(("[PASS] " if ok else "[FAIL] ") + label + (f": {detail}" if detail and not ok else ""))
        if not ok:
            failures.append(label)
        return ok

    status, amira = client.call("GET", "/portfolios/amira")
    check(status == 200 and amira.get("scenario", {}).get("persona", {}).get("persona_id") == "amira", "GET /portfolios/amira is served", f"HTTP {status}")

    status, robert = client.call("GET", "/portfolios/robert")
    if not check(status == 200, "GET /portfolios/robert", f"HTTP {status}"):
        return failures
    scenario = robert["scenario"]
    rules = scenario["scenario_rules"]
    status, confirmed = client.call("POST", "/rules/confirm", {
        "persona_id": "robert", "policy_id": None, "base_version": None, "objectives": scenario["objectives"],
        "confirmations": [{"rule": rule, "threshold": rule["threshold"]} for rule in rules], "withdraw_rule_ids": [],
        "change_note": "Release check: scenario rules confirmed by the release operator."})
    if not check(status == 201, "POST /rules/confirm creates a policy version", f"HTTP {status} {str(confirmed)[:200]}"):
        return failures
    policy = confirmed["policy"]
    purchase = {"instrument_id": "NVDA", "target_direct_weight": 0.25, "funding": "CASH", "original_words": None}
    head = {"persona_id": "robert", "policy_id": policy["policy_id"], "policy_version": policy["version"]}

    # 2. the data snapshot in use
    status, default = client.call("POST", "/check", dict(head, purchase_request=purchase, draft_rules=None))
    if check(status == 200, "POST /check on the scenario portfolio", f"HTTP {status} {str(default)[:200]}"):
        valuation = default["valuation_date"]
        dates = {fund["fund_id"]: fund["holdings_date"] for fund in default["data_coverage"] if fund["holdings_date"]}
        check(bool(dates) and all(date <= valuation for date in dates.values()), "no fund holdings are dated after the valuation date", f"{dates} vs {valuation}")
        cap = next(r for r in default["rule_results"] if r["rule_type"] == "max_issuer_exposure")
        upper = cap["measured"]["upper"]
        check(abs(upper - EXPECTED_SNAPSHOT_FIGURE) < 1e-9, "the corrected data snapshot is in use (Robert, NVIDIA upper bound)",
              f"got {upper!r}; expected {EXPECTED_SNAPSHOT_FIGURE}" + (" (this is the look-ahead snapshot's figure)" if abs(upper - LOOK_AHEAD_FIGURE) < 1e-9 else ""))
        check(default["portfolio_id"] == scenario["portfolio"]["portfolio_id"], "a request without custom_portfolio checks the scenario portfolio")

    # 3. a customized portfolio is checked as sent
    status, custom = client.call("POST", "/check", dict(head, purchase_request=purchase, draft_rules=None, custom_portfolio=CUSTOM))
    if check(status == 200, "POST /check with custom_portfolio", f"HTTP {status} {str(custom)[:200]} (400 here means the backend is the previous release)"):
        check(custom["portfolio_id"].startswith("pf-robert-custom-"), "the result names a customized portfolio id", custom["portfolio_id"])
        check(custom["feasibility"]["cash_before"] == 0.2 and custom["feasibility"]["starting_direct_weight"] == 0.2, "the engine used the customized cash and weights")
        cash = next(r for r in custom["evidence"] if r["metric_id"] == "cash_weight" and r["subject"]["portfolio_state"] == "STARTING")
        check(NOTE in " ".join(cash["assumptions"]), "the evidence says the starting weights were entered by the user")

    # 4. weights that do not total 100% are refused
    broken = {"cash_weight": 0.1, "positions": CUSTOM["positions"]}
    status, refused = client.call("POST", "/check", dict(head, purchase_request=purchase, draft_rules=None, custom_portfolio=broken))
    check(status == 400 and refused.get("error", {}).get("code") == "VALIDATION_ERROR" and "rule_results" not in refused,
          "a portfolio totalling 90% is refused with 400 and no result", f"HTTP {status}")

    # 5. a real investigation on the customized portfolio
    status, accepted = client.call("POST", "/investigations", dict(head, request=purchase, parent_investigation_id=None, custom_portfolio=CUSTOM),
                                   key=str(uuid.uuid4()))
    if check(status == 202, "POST /investigations with custom_portfolio is accepted", f"HTTP {status} {str(accepted)[:200]}"):
        started, job = time.time(), None
        while time.time() - started < DEADLINE_SECONDS:
            status, job = client.call("GET", f"/investigations/{accepted['id']}")
            if status == 200 and job["status"] in ("SUCCEEDED", "FAILED"):
                break
            time.sleep(POLL_SECONDS)
        if check(bool(job) and job.get("status") == "SUCCEEDED", "the investigation succeeds", str((job or {}).get("failure") or (job or {}).get("status"))):
            stored = job.get("portfolio") or {}
            check(stored.get("portfolio_id", "").startswith("pf-robert-custom-") and stored.get("portfolio_id") == job["result"]["portfolio_id"],
                  "the job stores the customized portfolio it was checked against")
            check({"cash_weight": stored.get("cash_weight"), "positions": stored.get("positions")} == CUSTOM, "the stored weights are exactly the weights sent")
            check("rule_results" in custom and job["result"]["rule_results"] == custom["rule_results"],
                  "the investigation's rule results equal the check's for the same portfolio")
            out(f"[INFO] investigation {job['id']}: agent mode {job['agent']['mode']}, {len(job['steps'])} steps")
    return failures


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", help="check this API instead of the stack's (the access code is then read from BYB_ACCESS_CODE)")
    args = parser.parse_args(argv)
    parameters = None
    if args.base_url:
        code = os.environ.get("BYB_ACCESS_CODE")
        if not code:
            print("FAILED: set BYB_ACCESS_CODE in the environment for --base-url (it is never taken from the command line).")
            return 2
        base_url = args.base_url
    else:
        import boto3

        session = boto3.Session(region_name=REGION)
        assert session.client("sts").get_caller_identity()["Account"] == ACCOUNT
        stack = session.client("cloudformation").describe_stacks(StackName=STACK)["Stacks"][0]
        outputs = {o["OutputKey"]: o["OutputValue"] for o in stack["Outputs"]}
        parameters = {p["ParameterKey"]: p.get("ParameterValue") for p in stack["Parameters"]}
        print(f"[INFO] stack {stack['StackStatus']}: code {parameters.get('CodeS3Key')}, snapshot {parameters.get('DataSnapshotId')}")
        base_url = outputs["ApiBaseUrl"]
        code = session.client("ssm").get_parameter(Name=outputs["AccessCodeParameterName"], WithDecryption=True)["Parameter"]["Value"]
    failures = run(Client(base_url, code))
    if failures:
        print(f"FAILED: {len(failures)} check(s) failed. Do not publish the frontend.")
        return 1
    if parameters is not None:  # only a check of the stack itself counts for publishing the frontend
        record_pass("customize", parameters)
    print("PASS: customized portfolios are checked and investigated as sent, on the corrected data snapshot.")
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
    sys.exit(main())
