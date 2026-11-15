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

`CALCULATION_VERSION` is `byb-engine-1.0.1`. Change from 1.0.0 (evidence and display text only; no serialized
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
