# Hand calculations for the engine fixtures

Every number in the `expected` block of `E01.json` ... `E22.json`, `R1.json`, `R2.json` and `M1.json` is derived
here by hand. **All inputs are synthetic**: the fund weights, coverage figures, prices, FX rates and the one
controversy record were invented so the arithmetic is short. None of it is real data about SPY, XIU.TO, NVDA or
any other instrument, even where a fixture borrows a real ticker.

The arithmetic was re-checked independently of how it was typed in: `contracts/python/tests/test_hand_calcs.py`
re-derives every expected number with a separate plain implementation (`reference_calc.py`), confirms every
maximum-compliant boundary with a brute-force scan over target weights, and proves with 30 deliberate mutations
that a wrong number is caught. If a fixture and this file ever disagree, the fixture is wrong.

## Conventions used below

Definitions are normative in `contracts/SEMANTICS.md`; this is the short form.

- All quantities are fractions of the portfolio (10% = 0.10). Comparisons use a tolerance of 1e-9.
- A purchase request sets the **final direct weight** `w` of one instrument. With starting weight `w0`:
  `additional = w - w0`, `cash_after = cash_before - additional`. Nothing else changes.
- Known exposure to an issuer = direct weights of all its share classes + sum over held equity funds of
  `fund weight x constituent weight`. This is the **lower** bound.
- Uncovered weight of a fund = `fund weight x (1 - coverage)` (the whole fund weight when no holdings file
  exists). `U` = the sum over held equity funds. The **upper** bound for one issuer is `lower + U`.
- Max-type rule: PASS if `upper <= limit`, FAIL if `lower > limit`, otherwise UNKNOWN.
  Min-type rule: PASS if `lower >= limit`, FAIL if `upper < limit`, otherwise UNKNOWN.
- `gap`: positive = size of the breach, zero or negative = headroom, null when UNKNOWN.
  Max-type: FAIL `lower - limit`, PASS `upper - limit`. Min-type: FAIL `limit - upper`, PASS `limit - lower`.
- Bond funds, commodity funds and crypto assets are outside the scope of the company-exposure rules: they add to
  neither bound and are listed as `out_of_scope`.
- Maximum compliant final weight: the largest `w` in `(w0, w0 + cash_before]` at which every evaluated rule is
  PASS. SUPPORTED when it exists; NO_FEASIBLE_PURCHASE when every such `w` has a proven FAIL (or is unfunded);
  WITHHELD otherwise.
- Scenario replay: a price (and, for USD instruments, an FX rate) is the latest one on or before the date being
  valued. At the base date and at the end date it must be at most 7 calendar days old; otherwise the instrument
  has no usable history and the whole replay is unknown (no proxy, no partial result).

## Synthetic universe (`synthetic_universe.json`)

Instruments: `SYN_A` (issuer ISS_A, CAD, Technology), `SYN_B1` and `SYN_B2` (two share classes of ISS_B, CAD,
Financials), `SYN_C` (ISS_C, USD, Energy), `SYN_D` (ISS_D, CAD, Financials), `SYN_E` (ISS_E, USD, no sector label),
equity funds `FUND_A`, `FUND_B`, `FUND_C`, `FUND_D`, bond fund `BOND_X` (out of scope).

| Fund | Constituent weights | Coverage | Uncovered share |
|---|---|---|---|
| FUND_A | ISS_A 0.20, ISS_B 0.10 (SYN_B1) + 0.05 (SYN_B2), ISS_C 0.25 (Energy), ISS_D 0.40 | 1.00 | 0.00 |
| FUND_B | ISS_A 0.30, ISS_C 0.10 (Energy), ISS_E 0.20 (sector label missing) | 0.60 | 0.40 |
| FUND_D | ISS_A 0.50, ISS_D 0.50 | 1.00 | 0.00 |
| FUND_C | no holdings file | 0.00 | 1.00 |

Prices (adjusted close) and FX (USDCAD):

| Date | SYN_A (CAD) | SYN_C (USD) | SYN_E (USD) | USDCAD |
|---|---|---|---|---|
| 2021-12-30 | 100 | none | none | 1.25 |
| 2021-12-31 | none | 50 | 20 | none |
| 2022-06-30 | 90 | 30 | 22 | 1.30 |
| 2022-09-30 | 85 | none | none | 1.36 |
| 2022-12-30 | 95 | 40 | none | 1.375 |

No other instrument has a price series. The SYN_E series deliberately stops on 2022-06-30.

Controversy registry: one record, `SYN-REC-1`, issuer ISS_C, nature REGULATORY_FINDING, event date 2024-05-01.
Only ISS_C was researched.

Unless stated otherwise the portfolio is **P**: cash 0.50, FUND_A 0.40, SYN_A 0.10. In P, through FUND_A:
ISS_A `0.40 x 0.20 = 0.08`, ISS_B `0.40 x (0.10 + 0.05) = 0.06`, ISS_C `0.40 x 0.25 = 0.10`,
ISS_D `0.40 x 0.40 = 0.16`. With the direct 0.10 of SYN_A, ISS_A = `0.10 + 0.08 = 0.18`. `U = 0`.

## E01 Direct plus indirect exposure through one fully covered fund

Portfolio P. Rule: no issuer above 0.25. Request: SYN_A to 0.15.

- Feasibility: additional `0.15 - 0.10 = 0.05`; cash after `0.50 - 0.05 = 0.45`. FEASIBLE.
- Starting: ISS_A 0.18, ISS_D 0.16, ISS_C 0.10, ISS_B 0.06. Largest 0.18 <= 0.25: PASS.
- Proposed: ISS_A `0.15 + 0.08 = 0.23`; the others are unchanged. Largest 0.23 <= 0.25: PASS.
  `gap = 0.23 - 0.25 = -0.02`.
- Maximum compliant: `w + 0.08 <= 0.25` gives `w <= 0.17`; cash allows `w <= 0.60`. Final 0.17, additional
  `0.17 - 0.10 = 0.07`, the rule binds.
- Summary: 1 PASS. Headline ALL_PASS.

## E02 Exact threshold equality passes

Portfolio P. Rule: no issuer above 0.25. Request: SYN_A to 0.17.

- Feasibility: additional 0.07; cash after `0.50 - 0.07 = 0.43`.
- Proposed: ISS_A `0.17 + 0.08 = 0.25`. `0.25 <= 0.25`: PASS (equality passes). `gap = 0.25 - 0.25 = 0`.
- Maximum compliant: 0.17, as in E01. The request is exactly at the boundary.

## E03 Two fund paths to the same issuer

Portfolio: cash 0.30, FUND_A 0.40, FUND_D 0.20, SYN_A 0.10. Rule: no issuer above 0.29. Request: SYN_A to 0.12.

- Starting: ISS_A `0.10 + 0.40 x 0.20 + 0.20 x 0.50 = 0.10 + 0.08 + 0.10 = 0.28`;
  ISS_D `0.40 x 0.40 + 0.20 x 0.50 = 0.16 + 0.10 = 0.26`. Largest 0.28 <= 0.29: PASS.
- Proposed: ISS_A `0.12 + 0.08 + 0.10 = 0.30 > 0.29`: FAIL. `gap = 0.30 - 0.29 = 0.01`. Breaching: ISS_A [0.30, 0.30].
- Feasibility: additional 0.02; cash after 0.28.
- Maximum compliant: `w + 0.18 <= 0.29` gives `w <= 0.11`; additional `0.11 - 0.10 = 0.01`; the rule binds.

## E04 Share classes of one issuer are aggregated

Portfolio: cash 0.40, FUND_A 0.40, SYN_B1 0.10, SYN_B2 0.10. Rule: ISS_B at most 0.30. Request: SYN_B2 to 0.15.

- Starting: ISS_B `0.10 + 0.10 + 0.40 x (0.10 + 0.05) = 0.20 + 0.06 = 0.26`: PASS.
- Proposed: ISS_B `0.10 + 0.15 + 0.06 = 0.31 > 0.30`: FAIL. `gap = 0.01`. Breaching: ISS_B [0.31, 0.31].
- Feasibility: additional 0.05; cash after 0.35.
- Maximum compliant: `0.10 + w + 0.06 <= 0.30` gives `w <= 0.14`; additional 0.04; the rule binds.

## E05 Partial holdings give an interval and an UNKNOWN verdict

Portfolio: cash 0.50, FUND_B 0.40, SYN_A 0.10. Rule: no issuer above 0.30. Request: SYN_A to 0.12.

- FUND_B covers 0.60 of itself: known ISS_A `0.40 x 0.30 = 0.12`, ISS_E `0.40 x 0.20 = 0.08`,
  ISS_C `0.40 x 0.10 = 0.04`. Uncovered `U = 0.40 x (1 - 0.60) = 0.16`.
- Starting: ISS_A lower `0.10 + 0.12 = 0.22`, upper `0.22 + 0.16 = 0.38`. `0.22 <= 0.30 < 0.38`: UNKNOWN.
- Proposed: lower `0.12 + 0.12 = 0.24`, upper `0.24 + 0.16 = 0.40`: UNKNOWN, gap null, cause PARTIAL_HOLDINGS.
- Coverage entry: weight 0.40, coverage 0.60, uncovered 0.16, PARTIAL; sector-labelled share
  `0.30 + 0.10 = 0.40` (the ISS_E row has no label).
- Maximum compliant: PASS would need `w + 0.12 + 0.16 <= 0.30`, i.e. `w <= 0.02`, below the starting 0.10, so no
  purchase is proven to pass. FAIL needs `w + 0.12 > 0.30`, i.e. `w > 0.18`, so targets in (0.10, 0.18] are not
  proven to fail either. WITHHELD.
- Summary: 1 UNKNOWN. Headline NO_FAIL_BUT_UNKNOWN.

## E06 Missing holdings: a proven failure next to an unknown check

Portfolio: cash 0.30, FUND_C 0.30, FUND_A 0.20, SYN_A 0.20. Rules: no issuer above 0.25; issuers [ISS_E] at most
0.05 in total. Request: SYN_A to 0.30.

- FUND_C has no holdings file: `U = 0.30`. FUND_A: ISS_A `0.20 x 0.20 = 0.04`.
- Cap, starting: lower `0.20 + 0.04 = 0.24`, upper `0.24 + 0.30 = 0.54`: UNKNOWN.
- Cap, proposed: lower `0.30 + 0.04 = 0.34 > 0.25`: FAIL although the upper bound (0.64) is uncertain.
  `gap = 0.34 - 0.25 = 0.09`. Breaching: ISS_A [0.34, 0.64]. Cause MISSING_HOLDINGS.
- Exclusion of ISS_E: known 0 (FUND_A does not hold it), upper `0 + 0.30 = 0.30 > 0.05`: UNKNOWN, before and after.
- Feasibility: additional 0.10; cash after 0.20.
- Coverage: FUND_C weight 0.30, coverage 0, uncovered 0.30, MISSING; FUND_A weight 0.20, COVERED.
- Maximum compliant: the cap can never be PASS (`w + 0.04 + 0.30 <= 0.25` is impossible) but it is not a proven
  FAIL for `w <= 0.21`. WITHHELD.
- Summary: 1 FAIL, 1 UNKNOWN. Headline HAS_FAIL.

## E07 Insufficient cash is a feasibility result, not a rule failure

Portfolio: cash 0.05, FUND_A 0.85, SYN_A 0.10. Rule: no issuer above 0.50. Request: SYN_A to 0.20.

- Feasibility: additional 0.10; cash after `0.05 - 0.10 = -0.05 < 0`: INSUFFICIENT_CASH.
- Rules are still evaluated at the requested weights. Starting: ISS_A `0.10 + 0.85 x 0.20 = 0.27`,
  ISS_D `0.85 x 0.40 = 0.34`; largest 0.34: PASS. Proposed: ISS_A `0.20 + 0.17 = 0.37`; largest 0.37 <= 0.50:
  PASS, `gap = 0.37 - 0.50 = -0.13`.
- Maximum compliant: cash allows `w <= 0.10 + 0.05 = 0.15`; the rule allows `w + 0.17 <= 0.50`, i.e. `w <= 0.33`.
  Final 0.15, additional 0.05, CASH binds.
- Summary: headline ALL_PASS with `feasibility_status` INSUFFICIENT_CASH shown beside it.

## E08 Maximum compliant weight: the tighter of two rules binds

Portfolio P. Rules: no issuer above 0.25 (`e08-cap-any`); ISS_A at most 0.22 (`e08-cap-a`). Request: SYN_A to 0.30.

- Proposed: ISS_A `0.30 + 0.08 = 0.38`. Both FAIL: gaps `0.38 - 0.25 = 0.13` and `0.38 - 0.22 = 0.16`.
- Feasibility: additional 0.20; cash after 0.30.
- Maximum compliant: `w <= 0.25 - 0.08 = 0.17` and `w <= 0.22 - 0.08 = 0.14`. Final 0.14, additional 0.04,
  `e08-cap-a` binds.

## E09 No feasible purchase: the starting portfolio already breaches

Portfolio: cash 0.30, FUND_A 0.50, SYN_A 0.20. Rule: no issuer above 0.25. Request: SYN_A to 0.25.

- Starting: ISS_A `0.20 + 0.50 x 0.20 = 0.30 > 0.25`: FAIL before any purchase, `gap = 0.05`. This is a
  starting-portfolio finding (ISS_D is `0.50 x 0.40 = 0.20`).
- Proposed: ISS_A `0.25 + 0.10 = 0.35`: FAIL, `gap = 0.10`. Purchase effect on the measure: `0.35 - 0.30 = +0.05`.
- Maximum compliant: every `w > 0.20` gives more than 0.30. NO_FEASIBLE_PURCHASE; the rule is the constraint.

## E10 Proven conflict: minimum above maximum for the same issuer

Portfolio P. Rules: ISS_A at least 0.20 (`e10-min-a`); ISS_A at most 0.10 (`e10-max-a`). Request: SYN_A to 0.15.

- Consistency: `0.20 > 0.10`, so no exposure to ISS_A satisfies both. PROVEN_CONFLICT, type
  MIN_EXCEEDS_MAX_SAME_ISSUER.
- Starting ISS_A 0.18: minimum FAIL (`0.18 < 0.20`, `gap = 0.20 - 0.18 = 0.02`); maximum FAIL
  (`0.18 > 0.10`, `gap = 0.08`). Two starting-portfolio findings.
- Proposed ISS_A 0.23: minimum PASS (`gap = 0.20 - 0.23 = -0.03`); maximum FAIL (`gap = 0.23 - 0.10 = 0.13`).
  Purchase effect +0.05 on both.
- Maximum compliant: WITHHELD (never computed under a proven conflict).
- Summary: 1 PASS, 1 FAIL, 2 starting breaches. Headline POLICY_CONFLICT (it outranks HAS_FAIL).

## E11 Minimum equal to maximum is not a conflict; a no-op purchase

Portfolio P. Rules: ISS_A at least 0.18; ISS_A at most 0.18. Request: SYN_A to 0.10 (its current weight).

- Consistency: `0.18 > 0.18` is false: CONSISTENT.
- Feasibility: additional 0; cash after 0.50.
- ISS_A stays 0.18: both rules PASS with `gap = 0`.
- Maximum compliant: any `w > 0.10` gives more than 0.18 and fails the maximum. NO_FEASIBLE_PURCHASE;
  `e11-max-a` is the constraint.

## E12 2022 replay with FX conversion, backward matching and the linear boundary

Portfolio: cash 0.40, SYN_A 0.40, SYN_C 0.20. Rule: replayed through 2022 the portfolio may lose at most 0.05.
Request: SYN_C to 0.30. Base date 2021-12-31, end date 2022-12-30, buy and hold, cash earns 0.

- Base values. SYN_A has no price on 2021-12-31: the latest earlier one is 100 on 2021-12-30 (price age 1 day).
  SYN_C is 50 USD on 2021-12-31. There is **no FX row on 2021-12-31**: the latest earlier one is 1.25 on
  2021-12-30 (FX age 1 day). SYN_C base value `50 x 1.25 = 62.5` CAD.
- End values. SYN_A 95. SYN_C `40 x 1.375 = 55` CAD.
- Instrument returns in CAD: SYN_A `95 / 100 - 1 = -0.05`; SYN_C `55 / 62.5 - 1 = -0.12`.
- Starting terminal return: `0.40 x (-0.05) + 0.20 x (-0.12) = -0.020 - 0.024 = -0.044`. Loss 0.044 <= 0.05: PASS.
- Proposed (SYN_C 0.30, cash 0.30): `0.40 x (-0.05) + 0.30 x (-0.12) = -0.020 - 0.036 = -0.056`.
  Loss 0.056 > 0.05: FAIL, `gap = 0.056 - 0.05 = 0.006`.
- D6 linear form: `R(w) = R(w0) + (w - w0) x r = -0.044 + (0.30 - 0.20) x (-0.12) = -0.056`. Same number.
- Maximum compliant: `0.044 + (w - 0.20) x 0.12 <= 0.05` gives `w <= 0.20 + 0.006 / 0.12 = 0.25`; additional 0.05;
  the rule binds.
- Drawdown (context only), portfolio value relative to 1 at the base date, on every date with a price:

| Date | SYN_A / base | SYN_C / base | Starting value | Proposed value |
|---|---|---|---|---|
| 2022-06-30 | `90 / 100 = 0.90` | `30 x 1.30 / 62.5 = 0.624` | `0.40 + 0.36 + 0.1248 = 0.8848` | `0.30 + 0.36 + 0.1872 = 0.8472` |
| 2022-09-30 | `85 / 100 = 0.85` | `30 x 1.36 / 62.5 = 0.6528` (price carried from 06-30, FX of the day) | `0.40 + 0.34 + 0.13056 = 0.87056` | `0.30 + 0.34 + 0.19584 = 0.83584` |
| 2022-12-30 | `0.95` | `55 / 62.5 = 0.88` | `0.40 + 0.38 + 0.176 = 0.956` | `0.30 + 0.38 + 0.264 = 0.944` |

  The running maximum is 1 (the base value). Deepest drawdown: starting `0.87056 - 1 = -0.12944`, proposed
  `0.83584 - 1 = -0.16416`, both on 2022-09-30.

## E13 Target below the current direct weight is an invalid request

Portfolio P. Request: SYN_A to 0.05, below its current 0.10. Reaching it would mean selling, which the cash-funded
purchase path does not support. Execution INVALID_REQUEST, code TARGET_BELOW_CURRENT_WEIGHT. Nothing is
evaluated: no feasibility, no rule results, consistency NOT_ASSESSED. Headline INVALID_REQUEST.

## E14 Unknown instrument is an invalid request

Portfolio P. Request: `NOPE` to 0.10. `NOPE` is not in the instrument registry. Execution INVALID_REQUEST, code
UNSUPPORTED_INSTRUMENT. Nothing is evaluated. Headline INVALID_REQUEST.

## E15 Sector exclusion already breached before the purchase, with unknown parts

Portfolio: cash 0.20, BOND_X 0.10, FUND_A 0.30, FUND_C 0.20, SYN_D 0.20. Rule: holdings labelled Energy at most 0.
Request: FUND_B to 0.10 (not held before).

- Out of scope: BOND_X 0.10 (bond fund), in neither bound.
- Starting, known Energy: FUND_A holds ISS_C (Energy) at 0.25: `0.30 x 0.25 = 0.075`. SYN_D is labelled
  Financials. Unknown: FUND_C has no holdings file, 0.20. Lower 0.075, upper `0.075 + 0.20 = 0.275`.
  `0.075 > 0`: FAIL before any purchase, `gap = 0.075`. Breaching: ISS_C [0.075, 0.275].
- Proposed adds FUND_B at 0.10: known Energy `0.10 x 0.10 = 0.01` (ISS_C); uncovered
  `0.10 x (1 - 0.60) = 0.04`; the ISS_E row has no sector label: `0.10 x 0.20 = 0.02` unclassified.
  Lower `0.075 + 0.01 = 0.085`. Upper `0.085 + 0.20 + 0.04 + 0.02 = 0.345`. FAIL, `gap = 0.085`.
- Breaching: ISS_C with its own bounds: lower 0.085, upper `0.085 + U = 0.085 + 0.24 = 0.325`
  (`U = 0.20 + 0.04`; the unclassified 0.02 belongs to ISS_E, so it is not part of ISS_C's bound).
- Purchase effect: lower `0.085 - 0.075 = +0.01`, upper `0.345 - 0.275 = +0.07`.
- Causes: MISSING_HOLDINGS (FUND_C), PARTIAL_HOLDINGS (FUND_B), UNCLASSIFIED_SECTOR (ISS_E row).
- Coverage: FUND_A 0.30 COVERED; FUND_C 0.20 MISSING, uncovered 0.20; FUND_B 0.10 PARTIAL, coverage 0.60,
  sector-labelled 0.40, uncovered 0.04.
- Feasibility: additional 0.10; cash after 0.10.
- Maximum compliant: the known Energy share is at least 0.075 at every target. NO_FEASIBLE_PURCHASE.

## E16 Controversy exclusion: a matching registry record proves a failure

Portfolio P. Rule: exposure to issuers with a REGULATORY_FINDING or COURT_RULING record at most 0.
Request: SYN_A to 0.15.

- ISS_C has a matching record (`SYN-REC-1`, REGULATORY_FINDING). Known exposure through FUND_A:
  `0.40 x 0.25 = 0.10`. That is the lower bound, before and after the purchase.
- Upper bound = all in-scope equity weight, because any issuer without a record is not assessed:
  starting `0.40 + 0.10 = 0.50`, proposed `0.40 + 0.15 = 0.55`.
- `0.10 > 0`: FAIL, `gap = 0.10`, already before the purchase (a starting-portfolio finding).
  Breaching: ISS_C [0.10, 0.10] (its own bounds; `U = 0`). Purchase effect: lower +0, upper +0.05.
- Cause REGISTRY_ABSENCE (the part between the bounds). NO_FEASIBLE_PURCHASE.

## E17 Controversy exclusion: no matching record is UNKNOWN, never PASS

Portfolio P. Rule: exposure to issuers with a COURT_RULING record at most 0. Request: SYN_A to 0.15.

- No record has that nature: lower 0. Upper: starting 0.50, proposed 0.55 (all in-scope equity weight).
- `0 <= 0 < 0.55`: UNKNOWN, gap null, cause REGISTRY_ABSENCE. Absence from the registry is not a pass.
- Maximum compliant: nothing proven to pass, nothing proven to fail. WITHHELD.

## E18 Unconfirmed rules are never evaluated

Portfolio P. Two rules, both PROPOSED: a system-proposed cap with no number, and a fictional-scenario loss budget
of 0.10 that nobody confirmed. Request: SYN_A to 0.15.

- Feasibility is still computed: additional 0.05, cash after 0.45.
- No rule is CONFIRMED, so `rule_results` is empty and both rules are listed in `rules_not_evaluated`.
  No scenario is computed. Headline NO_RULES_EVALUATED (never ALL_PASS). Maximum compliant WITHHELD.

## E19 The purchased instrument has no price history: the loss budget is UNKNOWN

Portfolio: cash 0.40, SYN_A 0.40, SYN_C 0.20 (as in E12). Rule: 2022 loss at most 0.05. Request: SYN_D to 0.10
(not held before). SYN_D is in the instrument registry, so the request is valid, but it has no price series.

- Feasibility: additional 0.10; cash after `0.40 - 0.10 = 0.30`. FEASIBLE.
- The replay needs every instrument of the proposed portfolio. SYN_D has no price on or before 2021-12-31:
  `missing_instruments = [SYN_D]`, scenario status INSUFFICIENT_HISTORY, no terminal return and no drawdown.
- One check uses one replay universe, so the starting evaluation of the rule is UNKNOWN as well, even though the
  starting portfolio alone could be replayed (E12 gives 0.044 for it). No starting-portfolio finding.
- The rows for the instruments that do have history are still reported: SYN_A -0.05, SYN_C -0.12 (as in E12).
  The return of the purchased instrument is null.
- Rule: UNKNOWN, measured null, gap null, cause INSUFFICIENT_HISTORY. No proxy is substituted.
- Maximum compliant: nothing proven to pass, nothing proven to fail. WITHHELD.
- Summary: 1 UNKNOWN. Headline NO_FAIL_BUT_UNKNOWN.

## E20 A stale end price is not carried forward: insufficient history

Portfolio: cash 0.40, SYN_A 0.40, SYN_E 0.20. Rule: 2022 loss at most 0.05. Request: SYN_A to 0.45.

- Feasibility: additional 0.05; cash after 0.35. FEASIBLE.
- SYN_E at the base date: price 20 on 2021-12-31 (age 0), FX 1.25 from 2021-12-30 (age 1 day): usable.
- SYN_E at the end date 2022-12-30: the latest price is 22 on 2022-06-30. Its age is
  `31 + 31 + 30 + 31 + 30 + 30 = 183` days, more than 7: not usable. `missing_instruments = [SYN_E]`,
  scenario status INSUFFICIENT_HISTORY.
- SYN_A has usable history: its row is reported (return -0.05), and since SYN_A is the purchased instrument the
  target instrument return is -0.05.
- Rule: UNKNOWN on the proposed and on the starting portfolio, measured null, cause INSUFFICIENT_HISTORY.
  Maximum compliant WITHHELD. Headline NO_FAIL_BUT_UNKNOWN.

## E21 No cash at all: no purchase can be funded

Portfolio: cash 0, FUND_A 0.90, SYN_A 0.10. Rule: no issuer above 0.50. Request: SYN_A to 0.15.

- Feasibility: additional 0.05; cash after `0 - 0.05 = -0.05`: INSUFFICIENT_CASH.
- Starting: ISS_A `0.10 + 0.90 x 0.20 = 0.28`; ISS_D `0.90 x 0.40 = 0.36`; ISS_C `0.90 x 0.25 = 0.225`;
  ISS_B `0.90 x 0.15 = 0.135`. Largest 0.36 (ISS_D): PASS.
- Proposed (the requested weights): ISS_A `0.15 + 0.18 = 0.33`; the largest is still ISS_D 0.36 <= 0.50: PASS,
  `gap = 0.36 - 0.50 = -0.14`.
- Maximum compliant: there is no cash, so no target above 0.10 can be funded. NO_FEASIBLE_PURCHASE with CASH as
  the constraint (not a rule: the rule passes).
- Summary: headline ALL_PASS with `feasibility_status` INSUFFICIENT_CASH beside it.

## E22 A minimum rule does not cap the purchase: cash is the only limit

Portfolio P. Rule: ISS_A at least 0.20. Request: SYN_A to 0.11.

- Starting: ISS_A 0.18 < 0.20: FAIL before any purchase, `gap = 0.20 - 0.18 = 0.02` (starting-portfolio finding).
- Proposed: ISS_A `0.11 + 0.08 = 0.19 < 0.20`: FAIL, `gap = 0.20 - 0.19 = 0.01`. Purchase effect +0.01.
- Feasibility: additional 0.01; cash after 0.49.
- Maximum compliant: the rule passes for every `w` with `w + 0.08 >= 0.20`, i.e. `w >= 0.12`, and nothing limits
  the purchase from above except cash: `w <= 0.10 + 0.50 = 0.60`. Final 0.60, additional 0.50, CASH binds.
  (The result is the largest passing target, not the smallest.)

## Robert-shaped universe (`robert_synthetic_universe.json`)

The instrument ids are those of Robert's fictional portfolio. The constituent weights, prices and FX rates are
**invented**; they are not the real holdings or prices of SPY, XIU.TO or any company.

- SPY (coverage 1.00): NVDA 0.06, AAPL 0.07, MSFT 0.06, JNJ 0.01, four filler companies 0.20 each.
- XIU.TO (coverage 0.98): RY.TO 0.08, three filler companies 0.30 each.
- XBB.TO is a bond fund (out of scope for company exposure; it is in the replay).

| Instrument | 2021-12-31 | 2022-06-30 | 2022-12-30 | Return in CAD |
|---|---|---|---|---|
| USDCAD | 1.25 | 1.25 | 1.30 | |
| XBB.TO (CAD) | 30 | 26.4 | 27 | `27 / 30 - 1 = -0.10` |
| SPY (USD) | 400 | 300 | 325 | `325 x 1.30 / (400 x 1.25) - 1 = 422.5 / 500 - 1 = -0.155` |
| XIU.TO (CAD) | 30 | 27 | 28.5 | `28.5 / 30 - 1 = -0.05` |
| RY.TO (CAD) | 100 | 95 | 98 | `-0.02` |
| JNJ (USD) | 150 | 150 | 150 | `150 x 1.30 / (150 x 1.25) - 1 = +0.04` |
| NVDA (USD) | 80 | 40 | 50 | `50 x 1.30 / (80 x 1.25) - 1 = 65 / 100 - 1 = -0.35` |

Portfolio: cash 0.30, XBB.TO 0.30, SPY 0.20, XIU.TO 0.10, RY.TO 0.05, JNJ 0.05.

## R1 Robert-shaped: NVDA to 0.25 under a 0.10 issuer cap and a 0.10 loss budget

Policy version 1: no issuer above 0.10; 2022 loss at most 0.10. Request: NVDA to 0.25 (not held before).

- Feasibility: additional 0.25; cash after `0.30 - 0.25 = 0.05`. FEASIBLE.
- Uncovered: XIU.TO `0.10 x (1 - 0.98) = 0.002`; SPY 0. `U = 0.002`.
- Starting exposures: Royal Bank `0.05 + 0.10 x 0.08 = 0.058`; Johnson & Johnson `0.05 + 0.20 x 0.01 = 0.052`;
  Apple `0.20 x 0.07 = 0.014`; NVIDIA `0.20 x 0.06 = 0.012`. Largest: lower 0.058, upper `0.058 + 0.002 = 0.060`: PASS.
- Proposed: NVIDIA `0.25 + 0.012 = 0.262`, upper `0.264`. `0.262 > 0.10`: FAIL, `gap = 0.262 - 0.10 = 0.162`.
  Breaching: NVIDIA [0.262, 0.264]. Cause PARTIAL_HOLDINGS. XBB.TO 0.30 is out of scope.
- Starting terminal return: `0.30 x (-0.10) + 0.20 x (-0.155) + 0.10 x (-0.05) + 0.05 x (-0.02) + 0.05 x 0.04`
  `= -0.030 - 0.031 - 0.005 - 0.001 + 0.002 = -0.065`. Loss 0.065 <= 0.10: PASS.
- Proposed terminal return: `-0.065 + 0.25 x (-0.35) = -0.065 - 0.0875 = -0.1525`. Loss 0.1525 > 0.10: FAIL,
  `gap = 0.0525`.
- Drawdown (context). Value on 2022-06-30 relative to the base: XBB.TO `26.4 / 30 = 0.88`, SPY `300 / 400 = 0.75`
  (FX unchanged at 1.25), XIU.TO 0.90, RY.TO 0.95, JNJ 1.00, NVDA 0.50.
  Starting: `0.30 + 0.30 x 0.88 + 0.20 x 0.75 + 0.10 x 0.90 + 0.05 x 0.95 + 0.05 x 1.00`
  `= 0.30 + 0.264 + 0.15 + 0.09 + 0.0475 + 0.05 = 0.9015`, drawdown `-0.0985`. At the end the value is 0.935.
  Proposed: `0.05 + 0.264 + 0.15 + 0.09 + 0.0475 + 0.05 + 0.25 x 0.50 = 0.7765`, drawdown `-0.2235`;
  at the end 0.8475. Deepest on 2022-06-30 in both cases.
- Maximum compliant: cap `w + 0.012 + 0.002 <= 0.10` gives `w <= 0.086`; budget `0.065 + 0.35 w <= 0.10` gives
  `w <= 0.10`; cash `w <= 0.30`. Final 0.086, additional 0.086, the issuer cap binds. At 0.086 the cap measures
  [0.098, 0.100] and the loss is `0.065 + 0.0301 = 0.0951`: both PASS.
- Summary: 2 FAIL. Headline HAS_FAIL.

## R2 Robert-shaped: cap raised to 0.30; the loss budget still fails with a gap

Policy version 2: the 0.10 cap is SUPERSEDED (kept, not evaluated) by a 0.30 cap confirmed by the user; the loss
budget is unchanged. Same portfolio and request as R1, so every measurement is the same.

- Cap: NVIDIA [0.262, 0.264] against 0.30: `0.264 <= 0.30`: PASS, `gap = 0.264 - 0.30 = -0.036`.
- Loss budget: loss 0.1525 against 0.10: FAIL, `gap = 0.0525`. This is one rule failing, not a contradiction
  between rules: consistency stays CONSISTENT.
- Maximum compliant: cap `w + 0.014 <= 0.30` gives `w <= 0.286`; budget `w <= 0.10`. Final 0.10, additional 0.10,
  the loss budget binds. At 0.10 the loss is `0.065 + 0.035 = 0.10`: PASS by equality.
- Summary: 1 PASS, 1 FAIL, 1 rule not evaluated (the superseded cap). Headline HAS_FAIL.

## Mateo-shaped universe (`mateo_synthetic_universe.json`)

Instrument ids from Mateo's fictional portfolio; constituent weights and sector rows are **invented**.

- XIU.TO (coverage 0.98, every row labelled): ENB.TO 0.04 Energy, CNQ.TO 0.03 Energy, RY.TO 0.08 Financials,
  CNR.TO 0.03 Industrials, four filler companies 0.20 each (Financials).
- SPY (coverage 1.00, every row labelled): XOM 0.02 Energy, MSFT 0.06 Information Technology, four filler
  companies 0.23 each (Industrials).
- ESGV: no holdings file. Controversy registry: empty, no issuer researched.

## M1 Mateo-shaped: SPY to 0.15 with an Energy-label exclusion and a controversy exclusion

Portfolio: cash 0.25, XBB.TO 0.25, XIU.TO 0.20, ESGV 0.15, MSFT 0.05, CNR.TO 0.05, FTS.TO 0.05.
Rules: holdings labelled Energy at most 0; issuers with a REGULATORY_FINDING, COURT_RULING or SETTLEMENT record
at most 0. Request: SPY to 0.15 (not held before).

- Feasibility: additional 0.15; cash after `0.25 - 0.15 = 0.10`.
- Out of scope: XBB.TO 0.25.
- Energy, starting. Known through XIU.TO: Enbridge `0.20 x 0.04 = 0.008`, Canadian Natural Resources
  `0.20 x 0.03 = 0.006`; total 0.014. Direct holdings are labelled Information Technology, Industrials and
  Utilities. Unknown: XIU.TO `0.20 x 0.02 = 0.004`, ESGV 0.15 (no file); `U = 0.154`. Lower 0.014, upper
  `0.014 + 0.154 = 0.168`. `0.014 > 0`: FAIL before any purchase, `gap = 0.014` (starting-portfolio finding).
- Energy, proposed. SPY adds Exxon Mobil `0.15 x 0.02 = 0.003` and nothing unknown. Lower `0.017`, upper
  `0.017 + 0.154 = 0.171`: FAIL, `gap = 0.017`. Purchase effect +0.003 on both bounds.
  Breaching: Enbridge [0.008, 0.162], Canadian Natural Resources [0.006, 0.160], Exxon Mobil [0.003, 0.157]
  (each lower bound plus `U = 0.154`).
- Controversy. No record matches: lower 0. Upper = in-scope equity weight: starting
  `0.20 + 0.15 + 0.05 + 0.05 + 0.05 = 0.50`, proposed `0.50 + 0.15 = 0.65`. UNKNOWN, gap null. Causes
  REGISTRY_ABSENCE, MISSING_HOLDINGS (ESGV), PARTIAL_HOLDINGS (XIU.TO).
- Coverage: XIU.TO 0.20, coverage 0.98, uncovered 0.004, PARTIAL; ESGV 0.15, MISSING, uncovered 0.15;
  SPY 0.15, COVERED.
- Maximum compliant: the known Energy share is at least 0.014 at every target. NO_FEASIBLE_PURCHASE; the Energy
  exclusion is the constraint.
- Summary: 1 FAIL, 1 UNKNOWN, 1 starting-portfolio breach. Headline HAS_FAIL.
