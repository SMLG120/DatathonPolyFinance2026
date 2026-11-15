# acceptance/mateo — Mateo acceptance (Milestone 6)

Independent acceptance of Mateo's demonstration: Energy-label exclusion and controversy exclusion, both with
tolerance 0, SPY to a final direct weight of 0.15, on a portfolio whose ESGV holdings are deliberately missing.
Read-only towards `backend/`, `contracts/` and `data/`: nothing outside this directory is edited, and no
expected value is typed in to make a test pass.

| File | What it is |
|---|---|
| `test_mateo_scenario_audit.py` | Scenario, engine fixtures (M1, M2), API fixtures and `HAND_CALCS.md` agree with each other and with LEAD_DECISIONS D7 / SEMANTICS; the fixtures' expected values are recomputed by hand-style arithmetic from the synthetic universe, without the engine |
| `test_mateo_engine.py` | `backend.engine.check_rules` on the synthetic universe **and** on `data/processed`: sector exclusion, controversy exclusion, starting-portfolio findings, evidence chains, coverage rows, maximum compliant weight, conflicts, which rules are evaluated, determinism, schema validity |
| `test_mateo_interpretation.py` | The interpretation fixtures: a question for "oil", supported and refused definitions, no invented threshold, words preserved, drafts inactive |
| `live_check.py` | Live-API check of the whole workflow (standard library only). **Prepared, never run against the deployment by this suite** |
| `test_live_check.py` | Unit tests of the script's pure parts, and an offline end-to-end run against a fake transport backed by the local engine |
| `mateo_invariants.py` | The invariants of a `check_result` (SEMANTICS sections 1, 5, 6, 9, 10, 11, 13), restated without `byb_contracts`; shared by the tests and the live script |
| `mateo_helpers.py` | Loaders, policy builders and the independent look-through (`hand_*`) |
| `FINDINGS.md` | Failing-input reports (E1, E2, L1) and observations |

## Run

From the repository root (no network, no AWS, no model):

    uv run --no-project --python 3.14 --with pytest --with boto3 --with jsonschema pytest acceptance/mateo -q

Tests parametrised `[real]` are skipped when `data/processed/{holdings,instruments,market_data}.json` are
absent (they are git-ignored). `test_real_data_outcome_is_reported` prints Mateo's real-data outcome.
The `xfail(strict=True)` tests are the findings; `--runxfail -k "E1 or E2 or L1"` shows them failing.

## Live check (after deployment)

    export BYB_ACCESS_CODE        # set it in your shell without echoing it, e.g.  read -s BYB_ACCESS_CODE
    python3 acceptance/mateo/live_check.py --base-url https://<api-id>.execute-api.us-east-1.amazonaws.com --compare-local

- `--dry-run` prints the ten planned requests and sends nothing (no access code needed).
- `--compare-local` also runs `backend.engine.check_rules` on the local `data/processed` with the portfolio
  and the policy the API returned, and requires the live `result` to be equal (numbers within 1e-9; it says
  whether the canonical JSON is byte-identical). Use it from a checkout whose data is the deployed snapshot.
- `--skip-interpret` leaves out the only model call. Without it, a 502/504 from the interpreter is a warning
  (the contract lets the scenario rules be confirmed without it); `--require-interpreter` makes it a failure.
- Exit codes: `0` every check passed, `1` an assertion failed, `2` the check could not run (no access code,
  bad arguments, network failure, 401/403, request budget exhausted).
- A real run creates **one policy and one investigation** in the deployment and sends at most 160 requests
  (9 workflow requests, at most 121 polls at the contract's 1500 ms, one final read, bounded retries). Polling
  stops on `SUCCEEDED`/`FAILED`, on 401/403/404/410, or 180 s after the 202.
- The access code is read from `BYB_ACCESS_CODE` only: never a command-line argument, never printed, never
  written to disk. The script writes no file and refuses a non-https base URL (except localhost) and redirects.

What it asserts, beyond response shapes (`byb_contracts.api_body_errors` when run from a checkout):
the D7 portfolio and offered rules; the interpreter asks about "oil" and invents no number; confirmation
stores both rules as `CONFIRMED` with their scenario provenance; `POST /check` twice gives the same document;
the preview is labelled and never shows UNKNOWN as a pass; the investigation is idempotent, terminates,
contains a server-run `check_rules` step, and its `result` equals the `/check` result; a terminal job does
not change; and every invariant of `mateo_invariants` plus Mateo's expected outcome (both rules already
breached by the starting portfolio, purchase effect reported as a range, ESGV `MISSING`, controversy upper
bound = in-scope equity weight, `NO_FEASIBLE_PURCHASE` bound by the Energy rule, no number).

## Assumptions where `contracts/api.md` is silent

1. `GET /portfolios/mateo` returns the content of `contracts/scenarios/mateo.json` (checked: D7 weights,
   objective, offered rule types and thresholds, the SPY request; not byte equality).
2. The demonstration confirms the two **scenario rules** unchanged (`FICTIONAL_SCENARIO`, threshold 0), as
   fixture M1 does, not the interpreter's drafts with a user-entered 0.
3. `POST /rules/confirm` with `policy_id: null` creates a new policy on every call (no idempotency), keeps the
   submitted `rule_id`s, and returns a server-chosen `policy_id` of any form.
4. `POST /check` and the investigation `result` are the same engine document for the same inputs (texts and
   evidence included), and two `/check` calls are identical.
5. `poll.path` is relative to the base URL given on the command line (a stage prefix, if any, is part of
   `--base-url`).
6. A structured request ends `SUCCEEDED` with `result` set and `clarification` null; `agent.mode` may be
   `MODEL` or `DETERMINISTIC_FALLBACK`; `steps` contains a completed `check_rules` step in both modes.
7. The interpreter's option ids and wording are free. Required: a clarification whose `about_words` contains
   "oil", a supported `exclusion / fund_reported_sector = Energy` draft with a null threshold, at least one
   unsupported option, and no exclusion rule proposed outright.
8. 429/5xx on `GET /portfolios`, `POST /check`, `POST /investigations` (same key) and the final read are
   retried once after 2 s; `POST /rules/confirm` and `POST /rules/interpret` are never retried.
9. `--compare-local` presumes the deployment runs the same engine version (`calculation_version` is compared
   first) on the same data snapshot, and passes no price/FX source labels that would change the document
   (Mateo has no scenario rule, so no price or FX evidence exists either way; a test asserts this).
