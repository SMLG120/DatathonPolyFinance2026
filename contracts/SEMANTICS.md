# Semantics (normative)

The JSON Schemas in `schemas/` fix the shape of every object. This file fixes what the numbers mean. It
formalizes `docs/LEAD_DECISIONS.md` (D2 to D7) and fills the gaps those decisions leave open. Where a helper
exists in `python/byb_contracts`, use it instead of re-deriving the value.

Worked examples for every rule below are in `fixtures/engine/HAND_CALCS.md` (cited as E01 ... M2).

## 1. Units, tolerance, rounding

- Every share of a portfolio or of a fund is a **fraction** (10% = 0.10). No field carries a percentage.
  Human-readable strings (`reason`, `text`, `message`) may print percentages; they are display text only.
- `EPS = 1e-9`. "a <= b" means `a <= b + EPS`; "a > b" means `a > b + EPS`; "a >= b" means `a >= b - EPS`;
  "a < b" means `a < b - EPS`. Exact equality with a limit passes (E02, E11).
- Results are not rounded, with one exception: `max_compliant.final_direct_weight` is rounded to 9 decimals.
- Reporting currency CAD. `valuation_date` is the date of the portfolio weights (2026-11-12 for the scenarios).

## 2. Inputs

The engine is pure. It receives: a portfolio, a policy (or draft rules), a purchase request, the instrument
registry, the holdings snapshot, market data and the controversy registry.

- **Instrument registry**: `issuer_id` groups the share classes of one company. `equity_scope` is true for
  equities and equity funds only. `is_fund` and `equity_scope` true means "look through with the holdings
  snapshot".
- **Holdings snapshot**: `coverage_fraction` is the plain sum of the reported constituent weights; weights are
  never rescaled. A fund absent from `funds` has no holdings file.
- **Market data**: `[date, adj_close]` rows, no forward fill; `fx_usdcad` rows are CAD per 1 USD.
- **Controversy registry**: dated, sourced records. An issuer without a record is not assessed.
- **Finite numbers**: every number in every input and output document is a finite IEEE-754 double. `NaN`,
  `+Infinity` and `-Infinity` are invalid input: they are rejected before any calculation, with the path of the
  offending value, never treated as missing data (missing data is an explicit `null` or an absent record, and
  yields UNKNOWN) and never coerced to zero. Every `validate_*` function of `byb_contracts` rejects them
  anywhere in a document, and the engine rejects them independently of the validators. A boolean or a numeric
  string is not a number.

## 3. Rules and policies

- A rule's number lives only in `threshold`. `threshold_kind` follows the rule type
  (`THRESHOLD_KIND_BY_RULE_TYPE`). Provenance invariants (enforced by `rule.schema.json`):

| `origin` | `threshold` | `threshold_source` | Meaning |
|---|---|---|---|
| `SYSTEM_PROPOSED` | null | null | A structure the system drafted. Always `PROPOSED`. It never carries a number. |
| `USER_STATED` | number | `USER_WORDS` (with `threshold_quote`) or `USER_ENTERED` | The user wrote or entered the number. |
| `FICTIONAL_SCENARIO` | number | `FICTIONAL_SCENARIO` | The number comes from our persona scenario. |

- `PROPOSED` rules carry no confirmation fields. `CONFIRMED` and `SUPERSEDED` rules carry a number,
  `confirmed_at` and `confirmed_by`.
- **Evaluated rules** (`rule_is_evaluated`): status `CONFIRMED` and a numeric threshold. In a preview
  (section 4) every draft with a number and status `PROPOSED` or `CONFIRMED`. Everything else is listed in
  `rules_not_evaluated` with a reason (E18, R2). "Policy order" is the order of `policy.rules`.
- A policy version is immutable. Changing a rule creates a new version in which the old rule stays as
  `SUPERSEDED` with `superseded_by_rule_id`, and the replacement has a **new** `rule_id` with
  `supersedes_rule_id` (R2). `content_hash = compute_content_hash(policy)`.
- An objective is never PASS or FAIL. `rule.objective_id` is a context link only.

## 4. Request validity, the proposed portfolio, feasibility

`target_direct_weight` (`w`) is the **final** direct weight of the instrument. `w0` is its starting direct weight
(0 if not held).

Execution status, first match wins. Any status other than `OK` evaluates nothing (section 9, E13, E14):

| Check | `execution.code` |
|---|---|
| the portfolio fails `validate_portfolio`, or holds an instrument missing from the registry | `INVALID_PORTFOLIO` |
| the policy fails `validate_policy` | `INVALID_POLICY` |
| the requested instrument is not in the registry | `UNSUPPORTED_INSTRUMENT` |
| `w < 0` | `TARGET_NEGATIVE` |
| `w > 1` | `TARGET_ABOVE_ONE` |
| `w < w0` (would need selling) | `TARGET_BELOW_CURRENT_WEIGHT` |
| an unexpected failure | status `ERROR`, code `ENGINE_ERROR` |

- **Proposed portfolio**: the starting positions with the instrument's weight set to `w` (added last if new);
  `cash_after = cash_before - (w - w0)`. No other weight changes. Fees and taxes are excluded.
- **Feasibility** (`feasibility_status`): `INSUFFICIENT_CASH` when `cash_after < 0`, else `FEASIBLE`. It is not
  a rule result and not a contradiction. With `INSUFFICIENT_CASH` the rules are still evaluated at the
  requested weights (E07, E21).
- **Preview**: when draft rules are evaluated instead of a stored policy version, the result has
  `preview: true`, `policy_id: null`, `policy_version: null`, and every evidence record has
  `policy_version: null`. Nothing is stored.

## 5. Look-through exposure and bounds (D4)

For one portfolio state (starting or proposed), over positions with a positive weight `w_p`:

- `equity_scope` false: the position is **out of scope**. It adds to neither bound and is listed in
  `rule_results[].out_of_scope` (not for the scenario rule).
- direct equity: `direct[issuer] += w_p`.
- equity fund with a holdings entry of coverage `c`: for each row, `via[issuer, fund] += w_p x weight_fraction`;
  `uncovered[fund] = w_p x max(0, 1 - c)`.
- equity fund without a holdings entry: `uncovered[fund] = w_p`.

Then `lower[issuer] = direct[issuer] + sum over funds of via[issuer, fund]`, `U = sum of uncovered`, and
`upper[issuer] = lower[issuer] + U` (E01, E03, E04, E05, E06).

Neither bound is capped at 1. With `INSUFFICIENT_CASH` the rules are evaluated at the requested weights
(section 4), which total more than 1, so a bound can exceed 1: a 0.15 target next to a 0.90 fund without a
holdings entry gives `upper = 0.15 + 0.90 = 1.05`. The same number is reported in `measured`, in
`breaching_subjects` and in `exposure`; `feasibility_status` says why it is not a reachable portfolio.

Fund coverage status (`coverage_status`): `MISSING` without a holdings entry; `COVERED` when `c >= 1`;
otherwise `PARTIAL`. A real fund that reports 0.9987 of its weight is therefore `PARTIAL`.

## 6. Rule evaluation

Every evaluated rule is evaluated on the proposed portfolio (`status`, `measured`, `gap`) and on the starting
portfolio (`starting`). `measured` is `{lower, upper}`.

Status (`status_from_bounds`): for a **max-type** rule (all types except `min_issuer_exposure`) PASS if
`upper <= limit`, FAIL if `lower > limit`, otherwise UNKNOWN. For `min_issuer_exposure` PASS if
`lower >= limit`, FAIL if `upper < limit`, otherwise UNKNOWN.

Gap (`gap_from_bounds`): positive = size of the breach, zero or negative = headroom, null when UNKNOWN.
Max-type: FAIL `lower - limit`, PASS `upper - limit`. Min-type: FAIL `limit - upper`, PASS `limit - lower`.

| Rule | `lower` | `upper` |
|---|---|---|
| `max_issuer_exposure`, scope `any` | largest `lower[issuer]` (0 if none) | that value `+ U` |
| `max_issuer_exposure`, one issuer | `lower[issuer]` | `lower[issuer] + U` |
| `min_issuer_exposure` | `lower[issuer]` | `lower[issuer] + U` |
| `exclusion`, `named_issuers` | sum of `lower[issuer]` over the named issuers | `lower + U` |
| `exclusion`, `fund_reported_sector` | exposure carrying exactly that label | `lower + U + unclassified` |
| `controversy_exclusion` | sum of `lower[issuer]` over flagged issuers | all in-scope equity weight |
| `scenario_loss_budget` | loss `L` | `L` |

- **Sector label** (E15, M1). The label is matched exactly, case-sensitively. For a fund constituent it is the
  `sector` of the holdings row; for a direct equity it is the registry `sector`. A fund's own registry label is
  never applied to its constituents. A row (or direct equity) whose `sector` is null is **unclassified**: its
  weight counts toward the upper bound only, and the label is not filled in from another source. A fund whose
  file has no labels therefore proves nothing and adds its whole listed weight as possible (M1).
  Label vocabularies of different sources are not harmonized.
- **Controversy** (E16, E17, M1). An issuer is flagged when at least one registry record has a `nature` in
  `criteria.natures` and, if `event_date_from` is set, an `event_date` on or after it. The upper bound is the
  total weight of in-scope positions (direct equities plus the whole weight of equity funds), because an issuer
  without a matching record is not assessed, including issuers the registry did research. The rule can only
  pass when the in-scope equity weight itself is within the limit.
- **Scenario loss** (section 7). `L = -scenario_terminal_return`. `L` can be negative (a gain).
- `breaching_subjects`: empty unless the status is FAIL; always empty for `min_issuer_exposure` and the
  scenario rule. Otherwise the issuers whose proven exposure causes the breach: for scope `any`, issuers with
  `lower[issuer] > limit`; for one issuer, that issuer; for exclusions, the named, labelled or flagged issuers
  with a positive known exposure. Each is reported with its own bounds `lower[issuer]` and `lower[issuer] + U`,
  sorted by `lower` descending then `subject_id`, at most 10.
- `unknown_causes` (of the proposed portfolio; may be non-empty with PASS or FAIL): `PARTIAL_HOLDINGS` when a held
  equity fund is PARTIAL;
  `MISSING_HOLDINGS` when one is MISSING; `UNCLASSIFIED_SECTOR` when `unclassified > 0` (sector rule);
  `REGISTRY_ABSENCE` when `upper > lower` (controversy rule); `INSUFFICIENT_HISTORY` (scenario rule). An UNKNOWN
  result names at least one cause.

## 7. Scenario replay `replay_2022` (D6)

Base date 2021-12-31, end date 2022-12-30 (`SCENARIOS`). The evaluated weights are applied at the base date and
held; cash earns 0.

- **Value of an instrument as of a date `t`**: the price is the latest `adj_close` on or before `t`; for a USD
  instrument it is converted with the latest `fx_usdcad` rate on or before **`t`** (a backward match on the as-of
  date, not on the price observation date; never a later rate, never interpolated) (E12). This one definition
  holds for every as-of valuation: the base date, the end date and every in-period date of this replay, and the
  valuation date wherever a position is valued for current weights (portfolio weights themselves are inputs as
  of `valuation_date`). Both observation dates and their ages in days relative to `t` are reported. Matching
  the rate to `t` and matching it to the price date give the same rate whenever a price exists on `t`.
- **Usable history**: at the base date and at the end date the price, and the FX rate for a USD instrument,
  must exist and be at most `MAX_PRICE_AGE_DAYS = 7` calendar days old. Otherwise the instrument is listed in
  `missing_instruments`. No proxy is ever substituted.
- **One replay universe per check**: usable history is required for every instrument of the proposed portfolio.
  If any is missing, `scenario.status` is `INSUFFICIENT_HISTORY`, `starting` and `proposed` are null, and every
  `scenario_loss_budget` rule is UNKNOWN with `measured` null on the proposed **and** on the starting portfolio
  (E19, E20). `instrument_returns` still lists the instruments that have usable history;
  `target_instrument_return` is null only when the requested instrument is missing.
- `V(t) = cash + sum of weight x value(t) / value(base date)`, so `V(base date) = 1`.
  `scenario_terminal_return = V(end date) - 1`. The budget rule measures `L = -scenario_terminal_return`.
- **Linearity**: `R(w) = R(w0) + (w - w0) x r`, where `r` is the CAD return of the requested instrument
  (`target_instrument_return`). This is what makes the budget boundary exact (E12, R1).
- `scenario_max_drawdown` is context only, never a rule: the lowest `V(t) / running maximum - 1` over every
  date in (base date, end date] on which a held instrument has a price row; the running maximum starts at 1.
  `max_drawdown_date` is the first date reaching it, null when the drawdown is 0.
- Price and FX ages in days at both dates are reported per instrument in `instrument_returns`.
- The scenario section exists only when an evaluated rule needs it; otherwise `scenario` is null.

## 8. Policy consistency

Schema version 1 can prove exactly one kind of conflict, `MIN_EXCEEDS_MAX_SAME_ISSUER`: an evaluated
`min_issuer_exposure` on issuer X with a limit greater than the limit of an evaluated `max_issuer_exposure`
whose scope is X or `any` (E10). Equal limits are not a conflict (E11). Conflicts are listed for each minimum
rule in policy order, then each maximum rule in policy order; `rule_ids` is `[minimum rule, maximum rule]`.

`CONSISTENT` means only "no supported calculation proved a conflict". Ambiguous wording, an infeasible
purchase and a failed rule are never reported as a conflict. `NOT_ASSESSED` is used only when execution is not
`OK`. Rules are still evaluated individually under a proven conflict.

## 9. Summary and headline

`summary = derive_summary(result)`; never author it. `headline` is the first match of:

1. execution `ERROR`: `EXECUTION_ERROR`
2. execution `INVALID_REQUEST`: `INVALID_REQUEST`
3. policy consistency `PROVEN_CONFLICT`: `POLICY_CONFLICT`
4. no evaluated rule: `NO_RULES_EVALUATED`
5. any rule FAIL: `HAS_FAIL`
6. any rule UNKNOWN: `NO_FAIL_BUT_UNKNOWN`
7. otherwise: `ALL_PASS`

`counts` counts `rule_results` by status. The headline covers rule results only: `feasibility_status` is a
separate member of the summary and must be displayed next to it (E07 is `ALL_PASS` with `INSUFFICIENT_CASH`).
There is no overall "compliant" flag anywhere.

When execution is not `OK`: `feasibility`, `scenario`, `max_compliant` and `exposure` are null, every list is
empty, policy consistency is `NOT_ASSESSED`.

## 10. Other sections of a result

- `rule_results`, `rules_not_evaluated` and `starting_portfolio_findings` are in policy order.
- `starting_portfolio_findings`: one entry for each evaluated rule whose `starting.status` is FAIL, and only
  those. `measured`, `gap` and `breaching_subjects` describe the starting portfolio;
  `purchase_effect = proposed bounds - starting bounds`. This keeps a breach that existed before the purchase
  apart from what the purchase adds (E09, E15, M1). `lower_change` is what the purchase is proven to add and
  `upper_change` the most it could add. When they differ, the effect is partly unresolved and is reported as
  that range, never as its lower end (M1, sector rule: 0 proven, up to 0.15 possible).
- `data_coverage`: one entry per equity fund held in the proposed portfolio, in portfolio order.
  `uncovered_portfolio_weight = portfolio_weight x max(0, 1 - coverage_fraction)`; `sector_labelled_fraction` is
  the sum of the weights of rows that carry a sector label; a MISSING fund has coverage 0 and null
  `holdings_date` and `source_id`.
- `exposure` (chart rows). `possible_extra` is `U` for each state. Issuers listed: the issuer of the requested
  instrument when it is a direct equity, every issuer named in an evaluated rule's parameters, every breaching
  subject (proposed or starting), then the issuers with the largest proposed `lower` until 10 are listed. The
  list is sorted by proposed `lower` descending, then `issuer_id`. `indirect_by_fund` lists, in portfolio order,
  the funds through which the issuer has a positive known exposure in that state. `name` is the registry name of
  the instrument with the smallest `instrument_id` among those of the issuer.
- `goal_context`: for each objective in policy order, one `LINKED_RULE_RESULTS` entry when an evaluated rule
  links to it, otherwise one `NOT_QUANTIFIED` entry. Then, attached to the first objective of kind `goal` (the
  first objective if there is none): one `CONCENTRATION` entry (largest single-issuer `lower` and its `upper`,
  starting and proposed) when the proposed portfolio has in-scope equity weight, and one `SCENARIO_DRAWDOWN`
  entry when the scenario is `COMPUTED`. Entries have no status. Empty when there is no objective.
- `disclosures`: `templates.DISCLOSURES`.
- All `reason` and `text` strings are rendered from templates by the engine or the service. Their wording is
  not part of the contract; the fixtures show examples.

## 11. Maximum compliant weight

Targets considered: `T = (w0, w0 + cash_before]`, that is, real purchases that cash can fund. On `T` every bound
is affine in `w`, so for each evaluated rule the targets where it is PASS form an interval, and so do the
targets where it is not FAIL. The ends solve a linear equation; no search is needed.

- `WITHHELD` (binding constraint null) when policy consistency is `PROVEN_CONFLICT` or no rule is evaluated.
- `NO_FEASIBLE_PURCHASE` with constraint `CASH` when `cash_before` is 0 (E21).
- `SUPPORTED` when some target in `T`, more than `EPS` above `w0`, makes every evaluated rule PASS.
  `final_direct_weight` is the largest such target, rounded to 9 decimals, and
  `additional_purchase = final_direct_weight - w0`. It is not capped at the requested target and can be below it
  (R1) or above it (E01, E22). The **binding constraint** is the first evaluated rule in policy order that stops
  passing just above that weight; `CASH` when none does and cash runs out there.
  `verified_by_rerun` must be true: the same evaluator, re-run at `final_direct_weight`, returns PASS for every
  evaluated rule and `FEASIBLE`. If the re-run does not confirm it, report `WITHHELD`.
- `NO_FEASIBLE_PURCHASE` when every target in `T` has at least one rule with a proven FAIL (E09, E11, E15, E16,
  M1). The constraint is the first evaluated rule in policy order that is FAIL just above `w0`.
- `WITHHELD` otherwise: no target is proven to pass, yet not every target is proven to fail (E05, E06, E17, M2).
  Unknown data never yields a number.

## 12. Engine fixtures and the subset match

Each `fixtures/engine/*.json` case has `inputs` (portfolio, policy, purchase request), names its data universe
and gives a **partial** `expected` result. The engine output matches when
`byb_contracts.subset_mismatches(case["expected"], output) == []`: every key in `expected` must be present and
equal (numbers within 1e-9); arrays have the same length, objects in them are paired by their id key, except
`rule_results`, `rules_not_evaluated`, `starting_portfolio_findings` and `conflicts`, which are compared in
order; arrays of scalars are compared ignoring order. Keys absent from `expected` are not asserted. The full
output must also pass `validate_check_result`.

All fixture numbers are synthetic. Never show them as real holdings or prices.

## 13. Evidence records and explanations

- Every number shown to the user is backed by a record in `evidence[]`; `evidence_id` is unique within a
  result; every id cited anywhere in the result exists in it. The ids used in the fixtures are examples.
- Labels: `FACT` is taken unchanged from a cited source (`source_ids` required) or is a threshold the user
  stated and confirmed; `FICTIONAL_SCENARIO` is invented for the simulation (persona weights, scenario
  thresholds, the hypothetical purchase, and the weights of a portfolio the user customized, which then say
  in `assumptions` that the user entered them); `ASSUMPTION` is a modelling choice or a draft value in a preview;
  `CALCULATION` is computed by the engine and carries `derived_from` (the calculation path) and a `formula`
  printed with the numbers used.
- `subject`, `unit`, `period` and `portfolio_state` say what the number is about. A statement may cite a record
  only for a claim about that metric, subject, unit and period. Matching digits is not validation.
- Text records. `sector_label`: the label as the source reports it, or null when the source reports none for
  that subject (one constituent, or a whole fund when none of its rows has a label). `controversy_record`: the
  value is the registry `record_id`, the subject is the issuer, `period` is the event date and `source_ids` are
  the record's sources. A record says that a dated event is on file; it is not a judgement of the company.
- Investigation `explanation[]`: `TEMPLATE` statements are rendered by the service. A `MODEL_VALIDATED`
  statement is model-written text accepted only after that check; it cites at least one record. If validation
  fails, the service drops the statement or falls back to templates (`agent.mode`
  `DETERMINISTIC_FALLBACK`). The model never produces or changes `result`.
- `steps[]` are real tool events with template-rendered summaries: never model reasoning.

## 14. Interpretation, confirmation, challenges

- An `interpretation` is a draft. Its rules are `PROPOSED`. A draft carries a number only when the user's own
  words contain it (`USER_WORDS`, with the quoted span); otherwise it is `SYSTEM_PROPOSED` with a null
  threshold. The interpreter never emits `FICTIONAL_SCENARIO` rules. Ambiguous wording yields a clarification
  with at least two options; an option the system cannot evaluate is listed with `supported: false`.
- Confirmation always carries the number the user accepted or entered. The server, not the client, writes the
  stored rule: `status` `CONFIRMED`, `confirmed_at`, `confirmed_by`, and the provenance. A scenario rule
  accepted with its scenario number unchanged stays `FICTIONAL_SCENARIO`; any other number makes it
  `USER_STATED` / `USER_ENTERED`, unless the submitted rule is `USER_WORDS` with the same number.
- Challenges: `CORRECT_FACT` stores an `UNVERIFIED` `proposed_correction` beside the disputed evidence and
  changes no result; `CLARIFY_PREFERENCE` returns a new draft interpretation; `CHANGE_RULE` is an explicit
  confirmation of a new number and creates a new policy version plus a new investigation. The earlier version
  and its report stay retrievable and unchanged.
