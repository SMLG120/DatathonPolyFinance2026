# Mateo acceptance: failing-input reports (Milestone 6)

Scope: Mateo's scenario, fixtures and engine behaviour, checked against the frozen documents
(`docs/LEAD_DECISIONS.md`, `docs/BUILD_BRIEF.md`, `contracts/SEMANTICS.md`, `contracts/api.md`).
Base commit `d36e41f`, engine `byb-engine-1.0.1`, data snapshot: holdings as of 2026-11-12 (retrieved
2026-11-14), controversy registry researched 2026-11-14.

Nothing outside `acceptance/mateo/` was edited. Each finding keeps a test marked `xfail(strict=True)` whose
reason starts with the finding id, so the suite stays green while the defect stays visible; when the defect
is fixed the test turns into an unexpected pass (a failure) and the marker must be removed.

Run every demonstration as a normal test (they then fail) with:

    uv run --no-project --python 3.14 --with pytest --with boto3 --with jsonschema \
      pytest acceptance/mateo -q --runxfail -k "E1 or E2 or L1"

**No verdict-level defect was found.** On the synthetic universe and on the real data, every status, bound,
gap, starting-portfolio finding, purchase effect, coverage row, unknown cause and maximum-compliant status
equals the value recomputed independently from the input files. The three findings below are about evidence
records only. None blocks Mateo's demonstration.

| Id | Owner | Severity | Summary | Blocks the demo |
|---|---|---|---|---|
| E1 | engine (A2 / finance-engine) | Medium | `controversy_record` evidence value is display text, not the registry `record_id` | No |
| E2 | engine (A2 / finance-engine) | Low | Sector-rule bound records do not cite the labels and constituent weights they are computed from; no record says the SPY rows are unlabelled | No |
| L1 | contracts (lead) | Low | API fixture `investigation_mateo_succeeded` shows numbers that no record of its `evidence[]` backs | No |

## E1. `controversy_record` evidence carries display text instead of the registry `record_id`

- **Severity:** Medium (contract divergence in a field the frontend and the `CORRECT_FACT` challenge read).
  No verdict, bound or status is affected.
- **Inputs:** `contracts/scenarios/mateo.json` (portfolio, both `scenario_rules` confirmed unchanged, request
  SPY to 0.15) on either universe: `contracts/fixtures/engine/mateo_synthetic_universe.json`, or
  `data/processed/{instruments,holdings,market_data,controversies}.json`. No override.
- **Reproduce:**
  `uv run --no-project --python 3.14 --with pytest --with boto3 --with jsonschema pytest acceptance/mateo/test_mateo_engine.py -q --runxfail -k E1`
  (test `test_E1_controversy_record_value_is_the_registry_record_id`, both universes).
- **Expected** (`contracts/SEMANTICS.md` section 13, "Text records"): "`controversy_record`: the value is the
  registry `record_id`, the subject is the issuer, `period` is the event date and `source_ids` are the
  record's sources." The contract fixture `contracts/fixtures/api/investigation_mateo_succeeded.json` shows it:
  `ev-record-enb.value == "SYN-MIRROR-2"`.
- **Actual** (`backend/engine/check.py`, `subject_evs`, line 464 at `d36e41f`): the value is
  `f"{nature} ({event_date}): {summary}"`, for example
  `"SETTLEMENT (2016-07-20): On July 20, 2016 the U.S. EPA and the U.S. Department of Justice announced ..."`.
  The `record_id` survives only inside the `evidence_id` (`ev-record-<record_id>`). Subject, period, source
  ids and the coverage note are correct (asserted by
  `test_controversy_evidence_is_dated_sourced_and_about_the_issuer`, which passes).
- **Consequence:** a client that resolves the registry record from `value`, as the contract says, finds
  nothing; a `CORRECT_FACT` challenge on this record would dispute a paragraph instead of a record id.
  `byb_contracts.check_result_errors` does not catch it (the unit is `text` either way).
- **Decision needed:** change the engine (a `calculation_version` bump) or amend SEMANTICS section 13 and the
  fixture. Until then the frontend should not parse `value`.

## E2. Sector-rule bounds do not cite the labels and weights they are computed from

- **Severity:** Low (evidence completeness; the reading of "calculation path" is ours, see the caveat).
- **Inputs:** as E1.
- **Reproduce:**
  `uv run --no-project --python 3.14 --with pytest --with boto3 --with jsonschema pytest acceptance/mateo/test_mateo_engine.py -q --runxfail -k E2`
  (test `test_E2_sector_rule_bounds_cite_the_labels_and_weights_they_are_computed_from`, both universes).
- **Expected** (`contracts/SEMANTICS.md` section 13): "`CALCULATION` is computed by the engine and carries
  `derived_from` (the calculation path) and a `formula` printed with the numbers used"; "`sector_label`: the
  label as the source reports it, or null when the source reports none for that subject (one constituent, or a
  whole fund when none of its rows has a label)". The contract fixture derives `ev-energy-upper` from
  `ev-spy-coverage` and `ev-spy-sector-labels` (a FUND-level `sector_label` record with value null).
- **Actual**, real data:
  - `ev-rule-mateo-excl-energy-1-lo-prop` (value 0.03332) has `derived_from == ["ev-w-XIU.TO-start"]` and the
    formula `0.2 x 0.1666 (via XIU.TO)`. The fund's Energy-labelled fraction 0.1666 is in no record, and the
    chain reaches no `fund_constituent_weight`, `issuer_exposure_via_fund` or `sector_label` record. The
    figure cannot be recomputed from the records the bound cites.
  - `ev-rule-mateo-excl-energy-1-up-prop` adds "≈0.149806987 (reported without a sector label)". Its chain
    reaches SPY's weight and coverage fraction, but the engine emits no `sector_label` record with a null
    value at all, so nothing in `evidence[]` states that the SPY file reports no sector label, although
    `UNCLASSIFIED_SECTOR` is a cause and that weight is half of the upper bound.
- **What does hold** (asserted by passing tests): with 10 or fewer breaching issuers, the rule's
  `evidence_ids` list each issuer's bounds, its sourced constituent weight and its `sector_label` record, and
  those issuer lower bounds sum to the rule's lower bound. The gap is in the rule-level record's own
  `derived_from`, and in the missing "no label" record.
- **Caveat:** SEMANTICS does not say that `derived_from` must be complete enough to recompute the value. If
  the lead reads section 13 more loosely, this is an enhancement, not a defect.

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
- **O4. `max_compliant.evidence_ids` is empty for `NO_FEASIBLE_PURCHASE`** in the engine, while the fixture
  cites the starting lower bound and the threshold. The engine's reason text contains no number, so section 13
  is not contradicted; citing the two records would make the statement inspectable.
- **O5. LEAD_DECISIONS D7 names only the Energy exclusion** as what Mateo confirms. The controversy rule's
  criteria (natures REGULATORY_FINDING, COURT_RULING, SETTLEMENT; no date limit; tolerance 0) exist only in
  `contracts/scenarios/mateo.json` and `docs/requirements.md` C11. Consistent, but D7 is silent on them.
