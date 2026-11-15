# Lead decisions (frozen unless the lead changes this file)

These are **our product choices and assumptions**, made by the lead so that
dependent work is unambiguous. They are not official datathon requirements.
`contracts/` formalizes them; if a contract and this file disagree, raise it
with the lead rather than guessing.

## D1. Verified environment (2026-11-14)

| Item | Verified value | How |
| --- | --- | --- |
| Team AWS account | `010928212265` (Workshop Studio team account) | `sts:GetCallerIdentity` |
| Role | `WSParticipantRole` with `AdministratorAccess`, no permissions boundary | `iam:ListAttachedRolePolicies`, `iam:GetRole` |
| Region | `us-east-1` only: every other region is explicitly denied by `ws-default-policy` | policy document + denied calls in `us-west-2`, `ca-central-1` |
| Account lifetime | Deleted end of day Mon 2026-11-16 with all its data | AWS workshop cheat sheet |
| Bedrock | Converse succeeded for `us.anthropic.claude-haiku-5-5`, `us.anthropic.claude-sonnet-5-5`, `us.anthropic.claude-fable-5-2`, `us.amazon.nova-lite-v1:0` | real Converse calls |
| Lambda | 400 concurrent executions, 50 MB zipped / 250 MB unzipped | `lambda:GetAccountSettings` |

**Application model** (runtime agents): `us.anthropic.claude-sonnet-5-5`, a
stack parameter. This is deliberately separate from the **development model**
(Claude Fable 5.2 in Claude Code), which never appears in application code.

AWS access for development goes through the AWS MCP server tool
(`call_boto3`), not the AWS CLI. SAM CLI is not installed: the SAM template is
deployed through CloudFormation change sets (the `AWS::Serverless` transform
runs server-side) after a small packaging script uploads the code zip.

## D2. Tech constraints

- Engine and Lambda code: **Python standard library only** (plus `boto3`,
  which the Lambda runtime provides). No pandas/numpy in anything deployed.
- Engine is pure: no I/O, no AWS, no model, no clock. Data is passed in.
- Money-like quantities are portfolio fractions (`float`), compared with an
  absolute tolerance `EPS = 1e-9`. `value <= limit + EPS` passes; equality passes.
- Reporting currency CAD. Valuation date `2026-11-12` (last starter-data date).
- `calculation_version` is a string constant in the engine, bumped on any
  change to a formula.

## D3. Supported rule types (schema v1)

| `rule_type` | Meaning | Threshold | Notes |
| --- | --- | --- | --- |
| `max_issuer_exposure` | Maximum total equity exposure to a company, direct plus look-through via equity funds, share classes aggregated | `max_fraction` | `issuer_scope`: `"any"` or one `issuer_id`. Bond/commodity/crypto instruments are outside the rule's scope; that scope is printed on the rule card. |
| `min_issuer_exposure` | Minimum total exposure to one named issuer | `min_fraction` | Exists so a proven contradiction with a max rule can be demonstrated. |
| `exclusion` | Maximum tolerated total exposure to a precisely defined set | `max_fraction` (user-set; 0 means none) | `definition.kind`: `named_issuers` (list of `issuer_id`) or `fund_reported_sector` (sector label as reported in the fund issuer's holdings file, or the starter universe label for direct holdings). "Oil producers" and "fossil fuels" are **unsupported definitions** until we hold a sourced classification: the interpreter must offer the supported definitions and ask. |
| `controversy_exclusion` | No exposure to issuers with a registry record matching user-confirmed criteria | `max_fraction` | Issuers absent from the registry are UNKNOWN, never PASS. Kept separate from `exclusion`. |
| `scenario_loss_budget` | The assumed allocation, replayed through a named historical scenario, must not lose more than the budget | `max_loss_fraction` | Metric is **terminal loss over the scenario period**, not drawdown. |

Rule lifecycle: `PROPOSED` (inactive) → `CONFIRMED` (active) → `SUPERSEDED`
(replaced in a later policy version). Only `CONFIRMED` rules with a numeric
threshold are evaluated. `origin`: `USER_STATED`, `FICTIONAL_SCENARIO`,
`SYSTEM_PROPOSED`. A `SYSTEM_PROPOSED` rule always has a null threshold until
the user supplies one.

Objectives are stored separately from rules (`objectives[]` with the user's
original words). A rule may reference an `objective_id` as context; that link
never produces a PASS/FAIL by itself.

## D4. Interval semantics for missing or partial holdings

For a fund with portfolio weight `w` whose constituent data covers a fraction
`c` of the fund (`c = sum of reported weights`, never rescaled):

    known exposure   = w x reported issuer weight
    possible extra   = w x (1 - c)        (the uncovered part could be this issuer)
    lower bound = sum(known)              upper bound = lower + sum(possible extra)

A fund with no holdings file has `c = 0`. Rule status:

- `max` rule: PASS if `upper <= limit`; FAIL if `lower > limit`; else UNKNOWN.
- `min` rule: PASS if `lower >= limit`; FAIL if `upper < limit`; else UNKNOWN.

This is how a proven failure coexists with unknown checks, and how missing
holdings are never treated as zero.

## D5. Purchase simulation

Request = `{instrument_id, target_direct_weight}`. Funding path is always
`CASH`. Reject (execution/validation status, not a rule FAIL) when the target
is below the current direct weight, negative, above 1, or the instrument is
unsupported. `cash_after < 0` is the built-in feasibility result
`INSUFFICIENT_CASH`; it is reported separately from rule results and never
described as a policy contradiction.

## D6. 2022 replay scenario (`replay_2022`)

- Period: first to last trading observation of calendar 2022, base price = last
  `adj_close` on or before 2021-12-31, end price = last `adj_close` on or
  before 2022-12-30.
- Initial weights: the (post-purchase) allocation, applied at the base date.
- Buy and hold, **no rebalancing**. Cash return fixed at 0 (disclosed as an
  assumption; no interest credited).
- Each instrument's own adjusted series is used; ETFs use the ETF's series.
- USD series are converted to CAD with the latest Bank of Canada rate on or
  before each date (backward match); rate age in days is reported.
- Outputs, labelled separately:
  - `scenario_terminal_return` (used for the budget check),
  - `scenario_max_drawdown` (context only; daily, on the union calendar with
    each instrument's last available value carried forward).
- Because weights are fixed at the base date and cash earns 0, terminal return
  is **linear** in the target weight:
  `R(w) = R(w0) + (w - w0) x r_instrument`. That proof (not an assumption of
  monotonic feasibility) is what allows a closed-form boundary for the
  scenario-loss budget. Drawdown is not linear, so if a drawdown rule ever
  becomes a hard rule the all-rules maximum is withheld.

## D7. Fictional scenarios (labelled fictional everywhere)

Persona facts (age, horizon, objective wording) come from the official case,
pages 5–7. Portfolios and thresholds are **invented by us**; the personas in
the case give no numbers.

Robert — weights as portfolio fractions:

| Instrument | Weight |
| --- | --- |
| Cash (CAD) | 0.30 |
| XBB.TO | 0.30 |
| SPY | 0.20 |
| XIU.TO | 0.10 |
| RY.TO | 0.05 |
| JNJ | 0.05 |

- Objective (his words in the scenario): "Preserve my capital while keeping
  some growth potential over the next 3 to 5 years."
- Fictional-scenario rules offered for confirmation: `max_issuer_exposure`
  any issuer 0.10; `scenario_loss_budget` on `replay_2022` 0.10.
- Demo request: NVDA at a final direct weight of 0.25.
- Challenge: raise the issuer cap to 0.30 → new policy version; issuer rule
  re-evaluated; scenario-loss budget still evaluated and reported with
  measured loss, budget and gap.

Mateo:

| Instrument | Weight |
| --- | --- |
| Cash (CAD) | 0.25 |
| XBB.TO | 0.25 |
| XIU.TO | 0.20 |
| ESGV | 0.15 |
| MSFT | 0.05 |
| CNR.TO | 0.05 |
| FTS.TO | 0.05 |

- Objective: "Balanced growth over 8 to 12 years; ESG matters to me; I want to
  avoid oil and companies involved in significant controversies."
- Demo request: SPY at a final direct weight of 0.15.
- The interpreter must ask what "oil" means. Mateo confirms
  `exclusion / fund_reported_sector = Energy` with `max_fraction` 0.
- ESGV holdings are deliberately **not** acquired in the core phase, so ESGV
  demonstrates interval semantics (UNKNOWN coverage) honestly.
- XIU.TO already holds Energy issuers, so Mateo's *current* portfolio may
  already breach his exclusion. The engine must report that as a finding about
  the starting portfolio, distinct from the effect of the purchase.

Amira (after the core passes): the "maximum growth" + "strict
diversification" sentence must produce a clarification request, not a
contradiction verdict. A separate, explicit min ≥ 0.20 / max ≤ 0.10 pair on
the same issuer demonstrates the proven-contradiction path.

## D8. Authentication

The HTTP API uses a Lambda authorizer that checks a bearer access code against
a value held in SSM Parameter Store (SecureString). The code is typed by the
user at runtime and kept in `sessionStorage`; it is never in the bundle or the
repo. This is demo-grade access control, disclosed as such, not user identity.

## D9. Ownership map (no concurrent edits to shared files)

| Path | Owner |
| --- | --- |
| `contracts/`, `docs/requirements.md` | requirements-contracts |
| `backend/engine/`, `backend/tests/engine/` | finance-engine |
| `data/` (except `data/starter/`), `docs/data-sources.md` | data-evidence |
| `backend/api/`, `backend/worker/`, `backend/agents/`, `backend/tests/service/`, `infra/`, `scripts/` | aws-agents-backend |
| `frontend/` | frontend-ux-ui |
| `validation/` | independent-validator |
| `README.md`, `docs/` (other files), `CLAUDE.md`, `.claude/`, `.gitignore`, `.env.example` | lead |

Anyone needing a change outside their paths reports it to the lead in their
final message instead of editing.
