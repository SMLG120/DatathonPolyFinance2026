# Mateo acceptance: failing-input reports (Milestone 6)

Scope: Mateo's scenario, fixtures, engine behaviour and (second pass) the backend handlers, checked against the
frozen documents (`docs/LEAD_DECISIONS.md`, `docs/BUILD_BRIEF.md`, `contracts/SEMANTICS.md`, `contracts/api.md`).

- First pass: base `d36e41f`, engine `byb-engine-1.0.1`.
- Second pass: base `df33dd6` (`integration/rc` merged), engine `byb-engine-1.0.8`, A2's API handler, worker and
  authorizer. Data snapshot unchanged: holdings as of 2026-11-12 (retrieved 2026-11-14), controversy registry
  researched 2026-11-14.

Nothing outside `acceptance/mateo/` was edited. Each open finding keeps a test marked `xfail(strict=True)` whose
reason starts with the finding id, so the suite stays green while the defect stays visible; when the defect
is fixed the test turns into an unexpected pass (a failure) and the marker must be removed. That is what
happened to E1 and E2 in the second pass.

Run the open demonstrations as normal tests (they then fail) with:

    uv run --no-project --python 3.14 --with pytest --with boto3 --with jsonschema \
      pytest acceptance/mateo -q --runxfail -k "L1 or B1_an_idempotent"

**No verdict-level defect and no regression.** On the synthetic universe and on the real data, every status,
bound, gap, starting-portfolio finding, purchase effect, coverage row, unknown cause and maximum-compliant
status equals the value recomputed independently from the input files, under 1.0.1 and under 1.0.8. No open
finding blocks Mateo's demonstration.

| Id | Owner | Severity | Summary | State | Blocks the demo |
|---|---|---|---|---|---|
| E1 | engine | Medium | `controversy_record` evidence value was display text, not the registry `record_id` | **Closed** in 1.0.8 | No |
| E2 | engine | Low | Sector-rule bound records did not cite the labels and constituent weights they are computed from; no record said the SPY rows are unlabelled | **Closed** in 1.0.8 | No |
| L1 | contracts (lead) | Low | API fixture `investigation_mateo_succeeded` shows numbers that no record of its `evidence[]` backs | Open | No |
| B1 | backend (A2) | Low | Replaying `POST /investigations` while the job is `QUEUED` invokes the worker Lambda a second time | Open (deliberate; needs a contract sentence or a code change) | No |

## Second pass: what changed for Mateo between engine 1.0.1 and 1.0.8

Real data, scenario rules confirmed unchanged, SPY to 0.15 (printed by `test_real_data_outcome_is_reported`):

| | 1.0.1 (first report) | 1.0.8 |
|---|---|---|
| Energy exclusion, starting | FAIL [0.03332, 0.18378] | same |
| Energy exclusion, proposed | FAIL [0.03332, 0.33378], gap 0.03332, causes PARTIAL / MISSING / UNCLASSIFIED_SECTOR | same |
| Controversy exclusion, starting | FAIL [0.01408, 0.50] | same |
| Controversy exclusion, proposed | FAIL [0.0156781585, 0.65] | same |
| Purchase effect | Energy (0, 0.15); controversy (0.0015981585, 0.15) | same |
| Coverage | XIU.TO PARTIAL 0.9977; ESGV MISSING; SPY PARTIAL 0.99871325 | same |
| Maximum compliant weight | NO_FEASIBLE_PURCHASE, bound by `mateo-excl-energy-1`, no number | same |
| Summary | HAS_FAIL, 0 pass / 2 fail / 0 unknown | same |

Differences, all in evidence or metadata: `calculation_version`; `max_compliant.evidence_ids` is now
`["ev-rule-mateo-excl-energy-1-lo-start", "ev-thr-mateo-excl-energy-1"]` (was empty, O4); new records
`ev-secw-XIU.TO-mateo-excl-energy-1` (0.1666, sourced) and `ev-sector-SPY-none` (null label, sourced);
`controversy_record.value` is the record id, with the description moved to `assumptions`.

Of the 10 tests that failed after the merge: 4 were the E1/E2 strict xfails tripping on both universes
(markers removed, assertions strengthened, below); the other 6 pinned superseded behaviour (the exact set of
`sector_label` records, and `max_compliant.evidence_ids == []`) and were rewritten to assert the documented
behaviour more strictly, not less. None was a regression.

## E1. CLOSED in engine 1.0.8 — `controversy_record` value is the registry `record_id`

- **Was** (1.0.1): the value was `"<nature> (<event_date>): <summary>"`; SEMANTICS section 13 says "the value is
  the registry `record_id`, the subject is the issuer, `period` is the event date and `source_ids` are the
  record's sources".
- **Now:** on both universes every `controversy_record` has `value == record_id`, the issuer as subject, the
  event date as `period`, the registry record's `source_ids`, label `FACT`; the summary, the nature and the
  registry coverage note are in `assumptions`. On the synthetic universe the values equal the fixture's
  (`ev-record-enb.value == "SYN-MIRROR-2"`).
- **Evidence:** `test_E1_controversy_record_value_is_the_registry_record_id` passes without a marker on
  `[synthetic]` and `[real]`; it asserts each of the clauses above against the registry file, not just the id.

## E2. CLOSED in engine 1.0.8 — sector-rule bounds cite the labels and weights they are computed from

- **Was** (1.0.1): `ev-rule-mateo-excl-energy-1-lo-*` derived only from the XIU.TO position weight (the fund's
  Energy fraction 0.1666 was in no record), and no record stated that the SPY file carries no sector label.
- **Now:**
  - the lower bound's `derived_from` is exactly the XIU.TO position weight and a new sourced, dated
    `fund_constituent_weight` record at FUND level (`ev-secw-XIU.TO-mateo-excl-energy-1`) whose value equals the
    sum of the Energy-labelled rows of the holdings file (0.1666 on real data); multiplying the two cited
    values reproduces the bound;
  - the proposed upper bound cites a FUND-level `sector_label` record with value null for SPY
    (`ev-sector-SPY-none`, sourced and dated), as the fixture does with `ev-spy-sector-labels`, and the bound
    is recomputed from the records it cites; the starting upper bound, where SPY is not held, does not cite it.
- **Evidence:** `test_E2_sector_rule_bounds_cite_the_labels_and_weights_they_are_computed_from` and
  `test_sector_label_evidence_quotes_the_fund_file` pass without a marker on both universes.

## L1. Fixture `investigation_mateo_succeeded` shows numbers that no evidence record backs

- **Severity:** Low (an illustrative fixture; it teaches a thinner evidence list than the rule it illustrates).
- **Inputs:** `contracts/fixtures/api/investigation_mateo_succeeded.json`, `response_body.result`.
- **Reproduce:**
  `uv run --no-project --python 3.14 --with pytest --with boto3 --with jsonschema pytest acceptance/mateo/test_mateo_scenario_audit.py -q --runxfail -k L1`
- **Expected** (`contracts/SEMANTICS.md` section 13): "Every number shown to the user is backed by a record in
  `evidence[]`".
- **Actual:** the upper bound of every breaching subject (Enbridge 0.162, Canadian Natural Resources 0.16,
  Exxon Mobil 0.157, in `rule_results` and in `starting_portfolio_findings`) and the gap of both starting
  findings in the STARTING state (0.014) have no record with that metric, subject and portfolio state anywhere
  in the fixture's `evidence[]`. The engine output for the same case does carry them
  (`mateo_invariants.decisive_number_problems` returns no problem on it).
- **Consequence:** a frontend built against the fixture cannot open an evidence drawer for those numbers and
  may not exercise that path. The fixture validators pass because they check that cited ids exist, not that
  every displayed number is cited.

## B1. A replayed `POST /investigations` invokes the worker a second time while the job is `QUEUED`

- **Severity:** Low. No second job, no second calculation, no second model call, no change to the stored job.
  Cost: one extra asynchronous Lambda invocation that exits at once.
- **Inputs:** `POST /rules/confirm` (Mateo's two scenario rules), then the same `POST /investigations` body with
  the same `Idempotency-Key` twice before the worker has run (what `live_check.py` does, and what a browser
  retry does). In process, synthetic or real snapshot.
- **Reproduce:**
  `uv run --no-project --python 3.14 --with pytest --with boto3 --with jsonschema pytest acceptance/mateo/test_live_check_inprocess.py -q --runxfail -k B1_an_idempotent`
- **Expected** (`contracts/api.md` section 6, server rule 2): "returns 202 with the **same** `id`; `status` is
  the job's current status; no second job and no second worker are created."
- **Actual** (`backend/api/handler.py`, `_store_and_dispatch`, lines 353-361 at `df33dd6`): same id, status
  `QUEUED`, and `lambda.invoke` is called again ("Still QUEUED: the first request may have died before
  dispatching. Dispatching again is safe because only one worker can claim a job."). The second delivery logs
  `worker_duplicate_delivery` and returns.
- **What bounds it** (passing test `test_B1_the_second_delivery_is_a_no_op_one_model_call_one_terminal_state`):
  one Bedrock call, one terminal state, terminal members identical on a later read. A replay after the worker
  claimed the job does not invoke again.
- **Decision needed:** the behaviour is arguably better than the contract's (it recovers a job whose first
  request died between store and dispatch). Either add that sentence to api.md, or stop re-dispatching.

## Second pass: `live_check.py` against the real handlers, in process

`inprocess_backend.py` puts A2's API handler, worker and authorizer (unmodified, on A2's in-memory S3 / Lambda
/ Bedrock / SSM fakes, snapshot built by `scripts/build_snapshot.py` from `data/processed`) behind the script's
transport seam. `test_live_check_inprocess.py`, 18 tests:

| Run | Exit | Result line |
|---|---|---|
| default | 0 | `PASS (20 checks, 1 warnings, 11 requests sent)`; the warning is `POST /rules/interpret` HTTP 502 |
| `--skip-interpret` | 0 | `PASS (20 checks, 1 warnings, 10 requests sent)` |
| `--compare-local` | 0 | `PASS (21 checks, ...)`; live result **byte-identical** (canonical JSON) to the local engine |
| `--require-interpreter` | 1 | stops at `HTTP 502 (INTERPRETER_FAILED), expected 200`; nothing stored, nothing invoked |
| wrong access code | 2 | `COULD NOT RUN`, one request, no handler reached |
| worker never runs | 1 | server answers `FAILED / DEADLINE_EXCEEDED` at poll 101 (150 s), before the 180 s client deadline |
| synthetic snapshot behind the API | 1 | stops at step 1: `SPY is not purchasable` (the synthetic universe has no price series) |

**The script needed no change**: every assumption listed in README held against the real handlers (policy
created per confirm; `poll.interval_ms` 1500; `/check` twice identical; the investigation `result` identical to
`/check`; a `SERVER` `check_rules` step; terminal immutability; `Cache-Control: no-store` on all 11 responses).

Backend against api.md, error paths probed directly (all pass): the 502 uses the contract error envelope;
404 `NOT_FOUND` for an unknown persona, policy, policy version and investigation; 400 `VALIDATION_ERROR` for an
unknown property, a `"15%"` string and a missing member; 400 with `path: "headers.Idempotency-Key"` when the key
is missing; 409 `IDEMPOTENCY_KEY_REUSED`; 422 `INVALID_PURCHASE_REQUEST` whose `details[0].issue` starts with
`TARGET_BELOW_CURRENT_WEIGHT` and which stores and invokes nothing; 409 `POLICY_VERSION_CONFLICT`.

Deviations found: **B1 only.** Known and expected, not a deviation: `POST /rules/interpret` always answers 502
`INTERPRETER_FAILED` because no interpreter exists, so the "oil" clarification of Mateo's demo is exercised
only on fixtures (`test_mateo_interpretation.py`), never on a real answer.

Not verified here (see README, "Unverifiable until a real deployment"): the `agent mode MODEL` reported in
these runs is the fake Bedrock returning an empty explanation, not a model.

## Observations (not defects; no failing test)

- **O1. Order of `unknown_causes`.** The engine emits `["PARTIAL_HOLDINGS", "MISSING_HOLDINGS", ...]` (the
  order of `byb_contracts.UNKNOWN_CAUSES`); the fixtures and the `api.md` excerpt print
  `["MISSING_HOLDINGS", "PARTIAL_HOLDINGS", ...]`. SEMANTICS section 12 compares arrays of scalars ignoring
  order, so nothing is contradicted, but a client or snapshot test must not depend on the order.
- **O2. The synthetic fixture is cleaner than the real snapshot in one respect.** In M1 SPY is `COVERED`
  (1.00); the real SPY file sums to 0.99871325 and is `PARTIAL`. HAND_CALCS claims only that the missing SPY
  labels and the three registry issuers follow the processed data, so there is no contradiction; the real
  result differs in every number (Energy lower bound 0.03332 through nine issuers, not 0.014 through two).
  Fixture numbers must not be shown as Mateo's real result.
- **O3. Mateo's exposure chart on real data lists only breaching issuers.** SEMANTICS section 10 lists
  breaching subjects first and then fills up to 10. The real demo has nine Energy issuers plus Exxon Mobil, so
  the list is full and Microsoft (the largest single-company exposure, 0.0589 to 0.2095) is not a chart row;
  it appears only in the `CONCENTRATION` goal context. This follows the contract; the UI should expect it.
- **O4. Resolved in 1.0.8.** `max_compliant.evidence_ids` for `NO_FEASIBLE_PURCHASE` now cites the binding
  rule's starting lower bound and its threshold, as the fixture does (asserted exactly by
  `test_demo_max_compliant_is_no_feasible_purchase_with_a_reason_and_no_number` and `test_max_compliant_gives_no_number_unless_supported`); still no number.
- **O5. LEAD_DECISIONS D7 names only the Energy exclusion** as what Mateo confirms. The controversy rule's
  criteria (natures REGULATORY_FINDING, COURT_RULING, SETTLEMENT; no date limit; tolerance 0) exist only in
  `contracts/scenarios/mateo.json` and `docs/requirements.md` C11. Consistent, but D7 is silent on them.
- **O6. Authorizer log lines carry no request id of their own.** In the in-process run each
  `authorizer_decision` line shows the `request_id` (once a `job_id`) left by the previous API request, because
  both handlers share one process there. In a deployment the authorizer is its own Lambda, so this is probably
  an artefact of the harness; worth one look at the first real CloudWatch lines before correlating on it.
- **O7. A deployment on a synthetic snapshot offers nothing to buy.** `purchasable_instrument_ids` needs a
  price series (api.md section 2) and the synthetic universes have none. Correct, and the live script stops on it.
