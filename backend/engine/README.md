# backend/engine

Pure, deterministic calculation engine for Before You Buy. Standard library
only, plus the shared `byb_contracts` package (`contracts/python`), which it
imports for constants, validators and the status/gap/summary derivations.
No AWS, no model, no clock; every input is a plain dict in the contract shape.
Normative definitions: `contracts/SEMANTICS.md`.

```python
from backend.engine import (CALCULATION_VERSION, check_rules, compute_exposure,
                            max_compliant_amount, replay_period, simulate_change)
```

| Function | Returns |
| --- | --- |
| `check_rules(portfolio, policy, purchase_request, instruments, holdings, market_data, controversies, *, draft_rules=None, data_sources=None)` | a full `check_result` document |
| `simulate_change(portfolio, purchase_request, instruments, policy=None, *, draft_rules=None)` | `execution`, `feasibility`, `starting_portfolio`, `proposed_portfolio` |
| `compute_exposure(portfolio, instruments, holdings)` | look-through exposure of one portfolio state with lower/upper bounds |
| `replay_period(portfolio, market_data, scenario_id="replay_2022", *, required_instruments=None)` | terminal return and maximum drawdown, reported separately |
| `max_compliant_amount(portfolio, policy, purchase_request, instruments, holdings, market_data, controversies, *, draft_rules=None)` | the `max_compliant` section (closed form, verified by re-running `check_rules` at the boundary) |

`draft_rules` makes the result a preview. `data_sources={"prices": id, "fx_usdcad": id}`
labels price and FX evidence as FACT; without it they are labelled ASSUMPTION.

`CALCULATION_VERSION` is `byb-engine-1.0.7`.

Change from 1.0.6 (the engine's own range checks, `guard.py`; no result for valid input changed). The checks below
are made by the engine itself, before and independently of the contract validators (the tests replace every
validator by one that accepts anything and the engine still refuses):

- cash weight and every position weight: a finite number in [0, 1], otherwise `INVALID_REQUEST / INVALID_PORTFOLIO`.
  A position is never dropped because its weight is unusable;
- rule and draft-rule thresholds: null, or a finite number in [0, 1], otherwise `INVALID_REQUEST / INVALID_POLICY`;
- purchase target: not a finite number raises `ContractError`; below 0 or above 1 stays `TARGET_NEGATIVE` /
  `TARGET_ABOVE_ONE`;
- holdings row weights in [0, 1]; coverage fractions in [0, 1.01] (published weights are rounded, so a sum slightly
  above 1 is accepted, as in the contract) and equal to the sum of the rows; prices and USD/CAD rates above 0:
  otherwise `ERROR / ENGINE_ERROR`, nothing calculated.

Regression for the reported false PASS (a NaN-weight position holding 20% of an issuer under a 10% cap):
`test_the_reported_false_pass_...` in `backend/tests/engine/test_engine_input_guards.py`.

Change from 1.0.5 (input guards, `guard.py`; no result for valid input changed). A number that is not finite, or
data that contradicts itself, is refused before any calculation and never yields a verdict:

- NaN or infinity in the portfolio, the policy or the draft rules: `execution` `INVALID_REQUEST`
  (`INVALID_PORTFOLIO` / `INVALID_POLICY`). Before, a NaN position weight was dropped and the rest could PASS.
- NaN or infinity in the purchase request: `ContractError` (no result can carry the request).
- NaN or infinity anywhere in the instrument registry, holdings, market data or controversy registry; a fund whose
  declared `coverage_fraction` differs from the sum of its reported rows (tolerance `COVERAGE_SUM_TOLERANCE`); a
  holdings row or an instrument without an `issuer_id`; a negative row weight: `execution` `ERROR`
  (`ENGINE_ERROR`), nothing calculated. `max_compliant_amount` raises `ValueError` for the same data.
- A result holding a non-finite number is replaced by `execution` `ERROR` (last line of defence).
- The `ERROR` message is fixed text and no longer contains the exception class or message.

The data check costs about 35 ms per call on the real data set (measured locally) and is skipped in the boundary
re-run. Tests: `backend/tests/engine/test_engine_input_guards.py`.

Change from 1.0.4 (citations only): a `max_compliant` of `NO_FEASIBLE_PURCHASE` now cites its proof in
`evidence_ids` - for a binding rule, the bound measured on the starting portfolio and the rule's threshold; for
cash, the starting cash weight. It was an empty list before.

Change from 1.0.3 (evidence records only; no number, status or boundary changed), for a sector-label rule:

- the lower bound's `derived_from` now includes, for each fund that contributes, a record holding the share of the
  fund labelled with that sector (`fund_constituent_weight`, subject the fund), so `weight x fraction` is
  recomputable from the calculation path;
- when `UNCLASSIFIED_SECTOR` is a cause, a fund whose holdings file has no sector label on any row gets a
  `sector_label` record with a null value (SEMANTICS section 13), cited by the rule result and by the upper bound.
  A fund with labels on only some rows, or a directly held instrument without a label, does not get one: their
  unlabelled weight is still in the upper bound and its formula, backed by the position-weight records.

Change from 1.0.2 (one evidence record; no number, status or boundary changed): the `value` of a
`controversy_record` evidence record is the registry `record_id` (SEMANTICS section 13), with the event date as its
period. The registry's own description (nature, summary, coverage note) is carried in `assumptions`, not in the value.
Test: `backend/tests/engine/test_engine_evidence_records.py`.

Change from 1.0.1 (boundary rounding): the maximum compliant final weight is the closed-form end rounded **down** to
9 decimals (`boundary.floor_to_grid`), not to the nearest. Rounding to the nearest could return a weight up to 5e-10
above the exact end, which passed the re-run only through the `EPS = 1e-9` comparison tolerance and carried a positive
`gap`. The re-run now also requires every rule to pass and cash to suffice without that tolerance (1e-12 of
floating-point noise is all that is allowed). No contract fixture value changed. Regression tests:
`backend/tests/engine/test_engine_boundary_rounding.py`. `evidence/robert_max_compliant.md` was generated with 1.0.1
and its numbers are unchanged by this fix (the real-data boundary 0.083924028 was already below the exact end).

Change from 1.0.0 to 1.0.1 (evidence and display text only; no serialized
number, status or boundary changed):

- `ev-max-final` and `ev-max-added` now list in `derived_from` every record the closed-form boundary uses, for the
  binding and the non-binding constraints: thresholds, the starting scenario return and the instrument's scenario
  return, the purchased issuer's look-through records and bounds before the purchase, the unattributed fund weight,
  starting cash and the starting direct weight.
- Formula and reason text prints up to 9 decimals and marks a rounded number with "≈" (formulas) or "about"
  (sentences), so the text never contradicts the serialized value. The unrounded boundary is not part of the result;
  `evidence/robert_max_compliant.py` reproduces it.

Tests, from the repository root:

```
uv run --no-project --python 3.14 --with pytest pytest backend/tests/engine -q
```

The test `conftest.py` puts the repository root and `contracts/python` on the
path. The real-data test is skipped unless `data/processed/holdings.json`,
`instruments.json` and `market_data.json` exist; it prints its key numbers.
A deployment must ship `contracts/python/byb_contracts` and `contracts/schemas`
next to the engine (see `byb_contracts/schema.py` for the lookup order).
