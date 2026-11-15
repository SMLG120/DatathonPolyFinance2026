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

Tests, from the repository root:

```
uv run --no-project --python 3.14 --with pytest pytest backend/tests/engine -q
```

The test `conftest.py` puts the repository root and `contracts/python` on the
path. The real-data test is skipped unless `data/processed/holdings.json`,
`instruments.json` and `market_data.json` exist; it prints its key numbers.
A deployment must ship `contracts/python/byb_contracts` and `contracts/schemas`
next to the engine (see `byb_contracts/schema.py` for the lookup order).
