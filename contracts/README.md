# contracts/

The shapes and meanings shared by the engine, the backend, the frontend and the validator. One owner
(the requirements-contracts agent, `docs/LEAD_DECISIONS.md` D9); everyone else reads and does not edit.
If code and contract disagree, the contract wins until its owner changes it.

## Files

| Path | What it is |
|---|---|
| `schemas/*.schema.json` | 19 JSON Schemas (draft 2020-12): the shape of every object. Every property is required; an absent value is an explicit `null`. |
| `SEMANTICS.md` | Normative: what the numbers mean (units, bounds, PASS / FAIL / UNKNOWN, summary, 2022 replay, maximum compliant weight, evidence). |
| `api.md` | The seven routes: requests, responses, status codes, error body, idempotency, polling. |
| `scenarios/` | `robert.json`, `mateo.json`, `amira.json`: fictional personas, portfolios, scenario rules, demo scripts. |
| `fixtures/engine/` | 26 hand-calculated cases (`E01` to `E22`, `R1`, `R2`, `M1`, `M2`), 3 synthetic universes, and `HAND_CALCS.md` with the arithmetic. |
| `fixtures/api/` | 24 example exchanges, one per file, indexed in `api.md` section 9. |
| `python/byb_contracts/` | Standard-library package: constants, `validate_*` and `*_errors` functions, `derive_summary`, `status_from_bounds`, `compute_content_hash`, `subset_mismatches`. |
| `python/tools/` | The hand-entered specs and `build_fixtures.py`, which writes every JSON file under `fixtures/` and `scenarios/`. |
| `python/tests/` | The checks listed below. |
| `typescript/contracts.ts` | TypeScript mirror of the schemas: types, string-literal unions, constants. |

Every number in `fixtures/` is synthetic and every portfolio is fictional; each file says so. Never show
fixture numbers as real holdings, prices or research.

## How to use it

- **Engine**: for each `fixtures/engine/*.json` case, run the engine on `inputs` with the named universe; the
  output must satisfy `byb_contracts.subset_mismatches(case["expected"], output) == []` and
  `validate_check_result(output)`.
- **Backend**: validate every body with `byb_contracts.validate_api_body(schema_ref, body)`. The package
  reads the schema files at run time: ship `schemas/` with it (a `schemas` folder next to the package, or
  set `BYB_SCHEMA_DIR`).
- **Frontend**: import `typescript/contracts.ts` unchanged; use `fixtures/api/*.json` as typed examples.
- Do not edit the JSON files under `fixtures/` or `scenarios/` by hand. Change the spec in `python/tools/`,
  write the arithmetic in `HAND_CALCS.md` first, then regenerate.

## Checks

Run from the repository root:

```sh
python3 contracts/python/tools/build_fixtures.py            # regenerate the JSON files
python3 contracts/python/tools/build_fixtures.py --check    # fail if a file on disk is stale
uv run --no-project --with pytest --with jsonschema pytest contracts/python/tests -q
frontend/node_modules/.bin/tsc --noEmit --strict --target ES2020 --module ESNext \
  --moduleResolution bundler --isolatedModules --verbatimModuleSyntax contracts/typescript/contracts.ts
```

The tests validate every fixture and scenario twice (standard-library validators and `jsonschema`), re-derive
every hand-calculated number with a separate plain implementation, reject deliberately broken documents,
compare `contracts.ts` and `api.md` with the schemas and fixtures, and confirm the generated files are fresh.

## Versioning rule

`schema_version` is one value for the whole contract: the `const` in every schema, `SCHEMA_VERSION` in
`constants.py` and in `contracts.ts`. It is `1.0.0`.

- **Major** (`2.0.0`): a document that was valid becomes invalid, or a field changes meaning (a property
  added, removed or renamed; a type or an enum value changed or removed; a rule in `SEMANTICS.md` changed).
- **Minor** (`1.1.0`): every document that was valid stays valid and no meaning changes (a new enum value,
  a new route).
- **Patch** (`1.0.1`), or no change of version during the datathon: descriptions, examples, fixtures and
  documentation, with no change of shape or meaning.
- A version change is one change set made by the contract owner: schemas, `constants.py`, `contracts.ts`,
  regenerated fixtures, all checks passing, and a note to the lead. Producers write the current version;
  a consumer rejects a document carrying another version instead of converting it.
- Stored policy versions (`policy.version`) are data and are unrelated to `schema_version`.
