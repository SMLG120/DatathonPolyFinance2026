#!/usr/bin/env python3
"""Focused check of the rule interpreter on a deployed backend, with the real model (PR #22 behaviour).

    python3 cloudshell_interpreter_check.py                       # the stack's API, access code from SSM (in memory)
    BYB_ACCESS_CODE=... python3 cloudshell_interpreter_check.py --base-url https://...

POST /rules/interpret stores nothing and changes no policy, so this is safe to run at any time. Each case sends one
sentence an investor could write and checks what the SERVER drafted from it:

  A  an everyday maximum ("below 10%") becomes a proposed maximum with the investor's own number;
  B  an everyday minimum ("more than 20% in NVIDIA") becomes a proposed minimum, never a maximum;
  C  a negated comparative ("don't want more than 10%") stays a maximum;
  D  two limits that no portfolio can satisfy together become ONE question with three options, not two drafts.

In every case nothing is confirmed (all rules PROPOSED) and every number is the one in the sentence. A case is retried
once, because the model's reading of a sentence can vary; the attempts used are printed. Exit status 0 only if all pass.
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request

REGION, ACCOUNT, STACK = "us-east-1", "010928212265", "before-you-buy"


def call(base_url, code, text):
    body = json.dumps({"persona_id": "robert", "text": text, "policy_id": None, "policy_version": None}).encode("utf-8")
    request = urllib.request.Request(base_url.rstrip("/") + "/rules/interpret", data=body, method="POST",
                                     headers={"Authorization": "Bearer " + code, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=40) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        text = error.read().decode("utf-8", errors="replace")
        try:
            return error.code, json.loads(text)
        except ValueError:
            return error.code, {"raw": text[:200]}


def every_rule(draft):
    rules = list(draft.get("proposed_rules", []))
    for clarification in draft.get("clarifications", []):
        rules += [option["proposed_rule"] for option in clarification["options"] if option.get("proposed_rule")]
    return rules


def scope(rule):
    parameters = rule.get("parameters") or {}
    return parameters.get("issuer_scope") or parameters.get("issuer_id")


def brief(draft):
    return json.dumps({"proposed": [(r["rule_type"], scope(r), r["threshold"], r.get("threshold_quote")) for r in draft.get("proposed_rules", [])],
                       "questions": [(c["question"][:90], [o["option_id"] for o in c["options"]]) for c in draft.get("clarifications", [])]})


def close(a, b):
    return a is not None and abs(a - b) < 1e-9


def case_a(draft):
    caps = [r for r in draft["proposed_rules"] if r["rule_type"] == "max_issuer_exposure" and scope(r) == "any"]
    return len(caps) == 1 and close(caps[0]["threshold"], 0.10) and caps[0]["threshold_quote"] == "10%" and caps[0]["origin"] == "USER_STATED"


def case_b(draft):
    rules = every_rule(draft)
    no_max = not any(r["rule_type"] == "max_issuer_exposure" and r["threshold"] is not None for r in rules)
    minimums = [r for r in draft["proposed_rules"] if r["rule_type"] == "min_issuer_exposure" and scope(r) == "NVIDIA"]
    return no_max and len(minimums) == 1 and close(minimums[0]["threshold"], 0.20) and minimums[0]["threshold_quote"] == "20%"


def case_c(draft):
    caps = [r for r in draft["proposed_rules"] if r["rule_type"] == "max_issuer_exposure" and scope(r) == "any"]
    no_min = not any(r["rule_type"] == "min_issuer_exposure" for r in every_rule(draft))
    return no_min and len(caps) == 1 and close(caps[0]["threshold"], 0.10)


def case_d(draft):
    if draft["proposed_rules"]:
        return False
    questions = [c for c in draft["clarifications"] if "cannot both hold" in c["question"]]
    if len(questions) != 1:
        return False
    options = {o["option_id"]: o.get("proposed_rule") for o in questions[0]["options"]}
    first, second = options.get("keep-first-limit"), options.get("keep-second-limit")
    return (set(options) == {"keep-first-limit", "keep-second-limit", "keep-qualitative"} and options["keep-qualitative"] is None
            and first is not None and first["rule_type"] == "max_issuer_exposure" and close(first["threshold"], 0.05)
            and second is not None and second["rule_type"] == "min_issuer_exposure" and scope(second) == "NVIDIA" and close(second["threshold"], 0.10))


CASES = [
    ("A", "an everyday maximum is a proposed maximum with the investor's number", "Keep any single company below 10%.", case_a),
    ("B", "an everyday minimum is a proposed minimum, never a maximum", "I want more than 20% of my portfolio in NVIDIA.", case_b),
    ("C", "a negated comparative stays a maximum", "I don't want more than 10% in any single company.", case_c),
    ("D", "two limits no portfolio can meet together are one question, not two drafts",
     "At most 5% in any single company. At least 10% in NVIDIA.", case_d),
]


def run(base_url, code, out=print):
    failures = []
    for label, title, text, accept in CASES:
        passed, attempts, last = False, 0, None
        while not passed and attempts < 2:
            attempts += 1
            status, draft = call(base_url, code, text)
            last = (status, draft)
            if status != 200:
                continue
            nothing_confirmed = all(rule["status"] == "PROPOSED" for rule in every_rule(draft))
            passed = nothing_confirmed and accept(draft)
        status, draft = last
        out(f"[{'PASS' if passed else 'FAIL'}] {label}: {title} (attempts: {attempts})")
        out(f"       sentence: {text}")
        out(f"       drafted:  {brief(draft) if status == 200 else f'HTTP {status} ' + json.dumps(draft)[:200]}")
        if not passed:
            failures.append(label)
    return failures


def record_pass(name, parameters):
    """Leave a note that this check passed on exactly this backend."""
    from pathlib import Path

    path = Path(__file__).resolve().parent / "backend-checks.json"
    notes = json.loads(path.read_text()) if path.exists() else {}
    notes[name] = {"code_key": parameters.get("CodeS3Key"), "snapshot_id": parameters.get("DataSnapshotId")}
    path.write_text(json.dumps(notes, indent=2))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", help="check this API instead of the stack's (access code from BYB_ACCESS_CODE)")
    args = parser.parse_args(argv)
    parameters = None
    if args.base_url:
        code = os.environ.get("BYB_ACCESS_CODE")
        if not code:
            print("FAILED: set BYB_ACCESS_CODE in the environment for --base-url.")
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
    failures = run(base_url, code)
    if failures:
        print(f"FAILED: interpreter cases {failures} did not behave as expected.")
        return 1
    if parameters is not None:
        record_pass("interpreter", parameters)
    print(f"PASS: {len(CASES)} interpreter cases with the real model.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
