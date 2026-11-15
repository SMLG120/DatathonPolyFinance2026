# Robert, NVDA: maximum compliant weight on the real data (evidence note)

Fictional simulation. Not advice, not a forecast, no transaction. The 2022 figures are a historical replay of an
assumed allocation.

Regenerate every number in sections A to D (they are the verbatim output of the script, floats printed unrounded):

    python3 -B backend/engine/evidence/robert_max_compliant.py

The script only reads `data/processed/{instruments,holdings,market_data,controversies}.json` and
`contracts/scenarios/robert.json`, builds policy v1 (both scenario rules confirmed) and v2 (cap superseded by a 0.30
cap), and calls the engine. Last generated with Python 3.15.2, engine `byb-engine-1.0.1`. Version 1.0.1 changed evidence links and display text
only: every number, status and boundary below is identical to the 1.0.0 run.

## 1. Result

| | Policy v1 (cap 0.10, loss budget 0.10) | Policy v2 (cap 0.30, loss budget 0.10) |
|---|---|---|
| Engine `max_compliant.status` | SUPPORTED, `verified_by_rerun` true | SUPPORTED, `verified_by_rerun` true |
| Final direct weight of NVDA, as reported (9 decimals) | 0.083924028 | 0.083924028 |
| Additional purchase, as reported (w0 = 0) | 0.083924028 | 0.083924028 |
| Exact unrounded boundary (final weight = additional purchase) | 0.08392402835504706 | 0.08392402835504706 |
| Binding constraint | `robert-loss-budget-1` (2022 loss budget) | `robert-loss-budget-1` (2022 loss budget) |
| Loss budget on its own | 0.08392402835504706 | 0.08392402835504706 |
| Issuer cap on its own, upper-bound version (cap is PASS up to here) | 0.087236696 | 0.287236696 |
| Issuer cap on its own, lower-bound version (cap is a proven FAIL above here) | 0.087724046 | 0.287724046 |
| Cash on its own | 0.3 | 0.3 |

The boundary is the same in both versions because the loss budget, not the issuer cap, binds in both. Raising the
cap to 0.30 does not raise the maximum.

## 2. Closed-form derivation with the actual inputs

Scenario `replay_2022`: base date 2021-12-31, end date 2022-12-30. Every price and FX rate used has an age of 0 days.

- NVDA adjusted close: 29.28561 USD on 2021-12-31, 14.565303 USD on 2022-12-30.
- USDCAD (Bank of Canada, backward matched to each date): 1.2678 on 2021-12-31, 1.3544 on 2022-12-30.
- NVDA CAD replay return: `r = (14.565303 x 1.3544) / (29.28561 x 1.2678) - 1 = -0.46867353694376046`.
- Starting replay terminal return (cash 0.30 earning 0, weights held from the base date):
  `R(w0) = 0.30 x (-0.11664547504707456) [XBB.TO] + 0.20 x (-0.1258614751506265) [SPY] + 0.10 x (-0.06348093756335771) [XIU.TO]`
  `+ 0.05 x (-0.015196957889073714) [RY.TO] + 0.05 x 0.13213700797530947 [JNJ] = -0.06066702879627166`.
  The engine reports -0.060667028796271616 (it sums `cash + sum(weight x (1 + return)) - 1`; the difference is 4e-17).
- D6 linearity: `R(w) = R(w0) + (w - w0) x r`, so the loss is `L(w) = 0.06066702879627166 + 0.46867353694376046 x w`.
  Check at the requested 0.25: linear form -0.17783541303221173, full replay -0.17783541303221173.
- Loss budget: `L(w) <= 0.10` gives `w <= (0.10 - 0.06066702879627166) / 0.46867353694376046 = 0.08392402835504706`.
- Issuer cap (any issuer), NVIDIA is the largest issuer once `w > 0.047304`: known exposure `w + 0.20 x 0.06137977 = w + 0.012275954`
  (through SPY); unattributed fund weight `U = 0.20 x (1 - 0.99871325) + 0.10 x (1 - 0.9977) = 0.00025735 + 0.00023 = 0.00048735`.
  PASS needs `w + 0.012275954 + 0.00048735 <= limit`; a proven FAIL needs `w + 0.012275954 > limit`.
- Cash: `w - w0 <= 0.30`.
- Maximum = min(0.08392402835504706, 0.087236696 [v1] or 0.287236696 [v2], 0.3) = 0.08392402835504706, rounded by the
  contract to 9 decimals: 0.083924028. The rounding moved the weight down by 3.55e-10, so the reported weight passes
  strictly, without leaning on the 1e-9 comparison tolerance (loss there: 0.09999999983359875).

No search was used: each end is the solution of one linear equation, then the same evaluator was re-run at the result.

## 3. Funding and replay assumptions

- The purchase is funded from existing cash only. Every other position keeps its weight. No selling, no shorting,
  no leverage. Fees and taxes are excluded.
- `target_direct_weight` is the final direct weight; the additional purchase is `w - w0` and `w0 = 0` for NVDA.
- Replay: the evaluated weights are applied at the base date and held (buy and hold, no rebalancing); cash earns a
  return of 0; each instrument uses its own adjusted-close series (a fund uses the fund's series, not its
  constituents); USD prices are converted to CAD with the latest Bank of Canada rate on or before each date.
- The loss-budget rule uses the terminal loss over the period. The maximum drawdown inside the period is reported
  separately as context and is not part of this boundary.

## 4. Could unresolved exposure invalidate the claimed maximum?

No. At the boundary no rule is UNKNOWN, and the unresolved part is already inside the bound that was tested.

- Unresolved exposure in this portfolio is the unreported part of the two equity funds: SPY (coverage 0.99871325,
  PARTIAL) contributes 0.00025735 and XIU.TO (coverage 0.9977, PARTIAL) contributes 0.00023; `U = 0.00048735`.
- NVIDIA at the boundary 0.083924028: direct 0.083924028, known through SPY 0.012275954, lower bound 0.096199982,
  **upper bound 0.096687332**. The upper bound assumes that all of the unreported 0.00048735 is NVIDIA.
- Issuer cap at the boundary: v1 `0.096687332 <= 0.10`: **PASS** (headroom 0.003312668), not UNKNOWN. v2: PASS
  (headroom 0.203312668). The largest other issuer is Royal Bank of Canada, 0.05958 to 0.06006735.
  The result carries `unknown_causes: [PARTIAL_HOLDINGS]` together with PASS: the interval is not a point, but all
  of it is inside the limit. The cap would only become UNKNOWN at this weight if the unattributed weight were about
  0.0038 or more (it is 0.00048735).
- Loss budget at the boundary: loss 0.09999999983359875 against 0.10: **PASS**. This rule does not use holdings
  look-through at all (it replays each instrument's own price series), so fund coverage cannot move it.
- The binding constraint is the loss budget (0.083924028...). Both versions of the cap boundary (0.087236696 with
  all unreported weight counted as NVIDIA, 0.087724046 with none of it) are above it, so the answer is the same
  whichever way the unresolved exposure falls.
- XBB.TO (0.30) is a bond fund, outside the scope of the issuer cap by the rule's own definition. It adds to
  neither bound, is listed in `out_of_scope`, and is not "unknown exposure" under the rule. It is fully included in
  the replay with its own price series (return -0.11664547504707456).
- Engine verdict: `max_compliant.status` is **SUPPORTED**, because targets up to the boundary are proven to pass
  every evaluated rule and the re-run of `check_rules` at 0.083924028 returns PASS, PASS and FEASIBLE. Immediately
  above (step +1e-6, target 0.083925028) the loss budget is FAIL (loss 0.10000046850713584) while the cap is still PASS.
- Is that the right call under `contracts/SEMANTICS.md`? Yes. Section 6: a max-type rule is PASS only when its
  **upper** bound is within the limit, so a PASS already covers the worst case of the unreported fund weight.
  Section 11: SUPPORTED when a funded target makes every evaluated rule PASS, the result is the largest such target
  rounded to 9 decimals, and the re-run must confirm it; WITHHELD is for the case where no target is proven to pass.
  The engine does not claim a supported maximum while a rule is UNKNOWN at that weight: SUPPORTED is returned only
  after the re-run shows PASS for every evaluated rule, otherwise the section is WITHHELD.

What the interval does not protect against (limits of the data, not of the calculation):

- The holdings files themselves (SPY and XIU.TO, holdings date 2026-11-12, the valuation date) and the mapping of
  their rows to issuers are taken as given. Only the weight the files do not report is treated as unknown.
- The cap measures equity exposure only. Any exposure to a company through the bond fund is outside the rule.
- The boundary is as good as the price and FX series (`starter_prices_daily`, `starter_fx_usdcad`).
- The engine solves the exact inequality and does not spend the 1e-9 tolerance as extra budget. Under the tolerance
  the evaluator would still say PASS up to about 0.0839240305; the reported 0.083924028 is on the cautious side by 2e-9.

## 5. Defects found in engine 1.0.0 while writing this note, and their state in 1.0.1

1. **Incomplete calculation path on `ev-max-final`: closed.** In 1.0.0 its `derived_from` listed only the two
   thresholds, `ev-cash-start` and `ev-w-NVDA-start`. In 1.0.1 `ev-max-final` cites every record the closed form
   uses, for the binding and the non-binding constraint: `ev-thr-robert-issuer-cap-1` (or `-2`),
   `ev-via-NVIDIA-SPY-start`, `ev-lo-NVIDIA-start`, `ev-up-NVIDIA-start`, `ev-unattr-SPY-start`,
   `ev-unattr-XIU.TO-start`, `ev-thr-robert-loss-budget-1`, `ev-scn-ret-start`, `ev-ret-NVDA`, `ev-cash-start`,
   `ev-w-NVDA-start`. `ev-max-added` cites `ev-max-final` and the same records. The engine tests recompute the
   boundary from the cited records alone and fail if any one of them is removed.
2. **Formula text printed with too few digits: closed.** In 1.0.0 `ev-max-added.formula` read
   `0.083924 - 0 = 0.083924` against a value of 0.083924028. In 1.0.1 formulas print up to 9 decimals and mark a
   rounded number with "≈"; sentences say "about". `ev-max-added.formula` is now `0.083924028 - 0 = 0.083924028`
   and the reason text carries 0.083924028 next to "about 8.39%". Display rounding remains a presentation choice.
3. **The unrounded boundary is not part of `check_result`: unchanged, by contract** (the contract asks for 9
   decimals). This script is the place that reproduces it, both independently and from the engine's internal
   interval (0.08392402835504707).

None of these changed a status or a number in `rule_results` or `max_compliant`.

# Generated numbers (verbatim script output)

## A. Inputs

- CALCULATION_VERSION: `byb-engine-1.0.1`
- Portfolio `pf-robert-fictional-1` (fictional), valuation date 2026-11-12: cash 0.3; XBB.TO 0.3, SPY 0.2, XIU.TO 0.1, RY.TO 0.05, JNJ 0.05
- Request: NVDA to a final direct weight of 0.25, funding CASH; starting direct weight 0.0
- Scenario `replay_2022`: base date 2021-12-31, end date 2022-12-30, status COMPUTED
- Holdings snapshot: SPY holdings_date 2026-11-12, source `ssga_spy_holdings_2026-11-14`, coverage 0.99871325 (PARTIAL); XIU.TO holdings_date 2026-11-12, source `ishares_xiu_holdings_2026-11-14`, coverage 0.9977 (PARTIAL)
- market_data valuation_date 2026-11-12; price source id `starter_prices_daily`, FX source id `starter_fx_usdcad`

## B. 2022 replay inputs (adjusted close, backward-matched FX to CAD)

| instrument | currency | base price (date) | base USDCAD (date, age d) | end price (date) | end USDCAD (date, age d) | CAD return, recomputed here | CAD return, engine | starting weight | weight x return |
|---|---|---|---|---|---|---|---|---|---|
| XBB.TO | CAD | 27.222239 (2021-12-31) | n/a | 24.046888 (2022-12-30) | n/a | -0.11664547504707456 | -0.11664547504707456 | 0.3 | -0.03499364251412237 |
| SPY | USD | 445.791931 (2021-12-31) | 1.2678 (2021-12-31, 0) | 364.767609 (2022-12-30) | 1.3544 (2022-12-30, 0) | -0.1258614751506265 | -0.1258614751506265 | 0.2 | -0.025172295030125302 |
| XIU.TO | CAD | 28.36075 (2021-12-31) | n/a | 26.560383 (2022-12-30) | n/a | -0.06348093756335771 | -0.06348093756335771 | 0.1 | -0.006348093756335771 |
| RY.TO | CAD | 112.37986 (2021-12-31) | n/a | 110.672028 (2022-12-30) | n/a | -0.015196957889073714 | -0.015196957889073714 | 0.05 | -0.0007598478944536857 |
| JNJ | USD | 149.750198 (2021-12-31) | 1.2678 (2021-12-31, 0) | 158.69754 (2022-12-30) | 1.3544 (2022-12-30, 0) | 0.13213700797530947 | 0.13213700797530947 | 0.05 | 0.006606850398765474 |
| NVDA | USD | 29.28561 (2021-12-31) | 1.2678 (2021-12-31, 0) | 14.565303 (2022-12-30) | 1.3544 (2022-12-30, 0) | -0.46867353694376046 | -0.46867353694376046 | 0.0 | -0.0 |

- Starting replay terminal return R(w0), recomputed here as the sum of weight x return (cash x 0): `-0.06066702879627166`
- Starting replay terminal return reported by the engine: `-0.060667028796271616` (starting loss 0.060667028796271616)
- NVDA CAD replay return r: recomputed `-0.46867353694376046`, engine `-0.46867353694376046`
- Replay at the requested 0.25: terminal return `-0.17783541303221173`; linear form R(w0) + 0.25 x r = `-0.17783541303221173`

## C. Exposure inputs (starting portfolio; none of them changes when NVDA is bought directly)

- NVIDIA known exposure through funds: `0.012275954` = 0.012275954 via SPY
- Unattributed fund weight U: `0.0004873499999999975` = 0.00025735000000000064 (SPY) + 0.0002299999999999969 (XIU.TO)
- Largest other issuer: ROYAL_BANK_OF_CANADA lower `0.05958`, upper `0.06006735`
- Out of equity scope (in neither bound): XBB.TO 0.3
- Cash before the purchase: `0.3`

## D. Policy v1 (issuer cap 0.10, 2022 loss budget 0.10)

Policy `pol-robert-real` version 1, content hash `sha256:1d548d463d690612d070a472afa969d838c397323c4a05801f8f725cb24296ff`.

### Closed form, each constraint on its own (final direct weight w of NVDA, w0 = 0)

| constraint | condition | boundary w | computed as |
|---|---|---|---|
| 2022 loss budget | L(w) = -R(w0) - w x r <= 0.1 | `0.08392402835504706` | (0.1 - 0.06066702879627166) / 0.46867353694376046 |
| issuer cap, upper-bound version (rule is PASS up to here) | w + via + U <= 0.1 | `0.087236696` | 0.1 - 0.012275954 - 0.0004873499999999975 |
| issuer cap, lower-bound version (rule is a proven FAIL above here) | w + via > 0.1 | `0.087724046` | 0.1 - 0.012275954 |
| cash | w - w0 <= cash_before | `0.3` | 0.0 + 0.3 |

- Unrounded boundary, recomputed here = min(budget, cap upper-bound version, cash): `0.08392402835504706`
- Engine's internal PASS intervals in d = w - w0 (lower end, upper end), before rounding: robert-issuer-cap-1 `(-inf, 0.087236696)`; robert-loss-budget-1 `(-inf, 0.08392402835504707)`
- Engine `max_compliant`: status SUPPORTED, final_direct_weight `0.083924028` (rounded to 9 decimals), additional_purchase `0.083924028`, binding_constraint `{"type": "RULE", "rule_id": "robert-loss-budget-1"}`, verified_by_rerun True
- Rounding moved the weight by `-3.550470611957124e-10` (comparison tolerance EPS = 1e-09)
- Engine reason text: The largest final direct weight of NVDA at which every evaluated rule passes with cash funding is 0.083924028 of the portfolio (about 8.39%), an additional purchase of 0.083924028 (about 8.39%); the rule robert-loss-budget-1 stops passing just above it. Verified by re-running the same checks at that weight.

### Evidence ids (in the check_result for the requested 0.25)

- max_compliant.evidence_ids: ['ev-max-final', 'ev-max-added']
  - `ev-max-final`: max_compliant_final_weight = 0.083924028; derived_from ['ev-thr-robert-issuer-cap-1', 'ev-via-NVIDIA-SPY-start', 'ev-lo-NVIDIA-start', 'ev-up-NVIDIA-start', 'ev-unattr-SPY-start', 'ev-unattr-XIU.TO-start', 'ev-thr-robert-loss-budget-1', 'ev-scn-ret-start', 'ev-ret-NVDA', 'ev-cash-start', 'ev-w-NVDA-start']; formula: upper end of each constraint, as starting direct weight + (limit - measured value before the purchase) / (change of that value per unit of weight bought): robert-issuer-cap-1 (NVIDIA): 0 + (0.1 - 0.012763304) / 1 = 0.087236696; robert-loss-budget-1: 0 + (0.1 - ≈0.060667029) / ≈0.468673537 ≈ 0.083924028; cash: 0 + 0.3 = 0.3. Largest final direct weight at which every evaluated rule passes: the smallest of these, rounded to 9 decimals = 0.083924028
  - `ev-max-added`: max_compliant_additional_purchase = 0.083924028; derived_from ['ev-max-final', 'ev-w-NVDA-start', 'ev-thr-robert-issuer-cap-1', 'ev-via-NVIDIA-SPY-start', 'ev-lo-NVIDIA-start', 'ev-up-NVIDIA-start', 'ev-unattr-SPY-start', 'ev-unattr-XIU.TO-start', 'ev-thr-robert-loss-budget-1', 'ev-scn-ret-start', 'ev-ret-NVDA', 'ev-cash-start']; formula: 0.083924028 - 0 = 0.083924028
- Records cited by `ev-max-final.derived_from` (the inputs of the closed form):
  - `ev-thr-robert-issuer-cap-1`: FICTIONAL_SCENARIO rule_threshold = 0.1, state NOT_APPLICABLE, period {"type": "AS_OF", "date": "2026-11-12"}, sources []
  - `ev-via-NVIDIA-SPY-start`: CALCULATION issuer_exposure_via_fund = 0.012275954, state STARTING, period {"type": "AS_OF", "date": "2026-11-12"}, sources []
  - `ev-lo-NVIDIA-start`: CALCULATION exposure_lower = 0.012275954, state STARTING, period {"type": "AS_OF", "date": "2026-11-12"}, sources []
  - `ev-up-NVIDIA-start`: CALCULATION exposure_upper = 0.012763303999999998, state STARTING, period {"type": "AS_OF", "date": "2026-11-12"}, sources []
  - `ev-unattr-SPY-start`: CALCULATION unattributed_fund_weight = 0.00025735000000000064, state STARTING, period {"type": "AS_OF", "date": "2026-11-12"}, sources []
  - `ev-unattr-XIU.TO-start`: CALCULATION unattributed_fund_weight = 0.0002299999999999969, state STARTING, period {"type": "AS_OF", "date": "2026-11-12"}, sources []
  - `ev-thr-robert-loss-budget-1`: FICTIONAL_SCENARIO rule_threshold = 0.1, state NOT_APPLICABLE, period {"type": "AS_OF", "date": "2026-11-12"}, sources []
  - `ev-scn-ret-start`: CALCULATION scenario_terminal_return = -0.060667028796271616, state STARTING, period {"type": "RANGE", "start_date": "2021-12-31", "end_date": "2022-12-30"}, sources []
  - `ev-ret-NVDA`: CALCULATION scenario_instrument_return = -0.46867353694376046, state NOT_APPLICABLE, period {"type": "RANGE", "start_date": "2021-12-31", "end_date": "2022-12-30"}, sources []
  - `ev-cash-start`: FICTIONAL_SCENARIO cash_weight = 0.3, state STARTING, period {"type": "AS_OF", "date": "2026-11-12"}, sources []
  - `ev-w-NVDA-start`: FICTIONAL_SCENARIO position_weight = 0.0, state STARTING, period {"type": "AS_OF", "date": "2026-11-12"}, sources []
- Source records one step behind them (prices, FX rates, constituent weight, coverage, holdings dates):
  - `ev-px-NVDA-base`: FACT price_adj_close = 29.28561, state NOT_APPLICABLE, period {"type": "AS_OF", "date": "2021-12-31"}, sources ['starter_prices_daily']
  - `ev-px-NVDA-end`: FACT price_adj_close = 14.565303, state NOT_APPLICABLE, period {"type": "AS_OF", "date": "2022-12-30"}, sources ['starter_prices_daily']
  - `ev-fx-2021-12-31`: FACT fx_usdcad = 1.2678, state NOT_APPLICABLE, period {"type": "AS_OF", "date": "2021-12-31"}, sources ['starter_fx_usdcad']
  - `ev-fx-2022-12-30`: FACT fx_usdcad = 1.3544, state NOT_APPLICABLE, period {"type": "AS_OF", "date": "2022-12-30"}, sources ['starter_fx_usdcad']
  - `ev-cw-SPY-NVIDIA`: FACT fund_constituent_weight = 0.06137977, state NOT_APPLICABLE, period {"type": "AS_OF", "date": "2026-11-12"}, sources ['ssga_spy_holdings_2026-11-14']
  - `ev-cov-SPY`: CALCULATION fund_coverage_fraction = 0.99871325, state NOT_APPLICABLE, period {"type": "AS_OF", "date": "2026-11-12"}, sources ['ssga_spy_holdings_2026-11-14']
  - `ev-cov-XIU.TO`: CALCULATION fund_coverage_fraction = 0.9977, state NOT_APPLICABLE, period {"type": "AS_OF", "date": "2026-11-12"}, sources ['ishares_xiu_holdings_2026-11-14']
  - `ev-hdate-SPY`: FACT holdings_date = '2026-11-12', state NOT_APPLICABLE, period {"type": "AS_OF", "date": "2026-11-12"}, sources ['ssga_spy_holdings_2026-11-14']
  - `ev-hdate-XIU.TO`: FACT holdings_date = '2026-11-12', state NOT_APPLICABLE, period {"type": "AS_OF", "date": "2026-11-12"}, sources ['ishares_xiu_holdings_2026-11-14']

### check_rules exactly at the boundary (target_direct_weight = 0.083924028)

| rule_id | status | measured lower | measured upper | limit | gap | unknown_causes | breaching_subjects |
|---|---|---|---|---|---|---|---|
| robert-issuer-cap-1 | PASS | 0.096199982 | 0.096687332 | 0.1 | -0.0033126680000000047 | PARTIAL_HOLDINGS | none |
| robert-loss-budget-1 | PASS | 0.09999999983359875 | 0.09999999983359875 | 0.1 | -1.6640125388711624e-10 | none | none |

Feasibility: FEASIBLE, cash_after 0.216075972. Headline: ALL_PASS. Contract validation errors: none.

NVIDIA at the boundary: direct 0.083924028, known via funds [('SPY', 0.012275954)], lower 0.096199982, upper 0.096687332 (possible_extra 0.0004873499999999975); headroom of the upper bound to the cap: 0.0033126680000000047.
Replay at the boundary: terminal return -0.09999999983359875; loss minus budget: -1.6640125388711624e-10.
max_compliant reported by the run at the boundary: SUPPORTED, final 0.083924028.

### check_rules immediately above the boundary (step +1e-06: target_direct_weight = 0.083925028)

| rule_id | status | measured lower | measured upper | limit | gap | unknown_causes | breaching_subjects |
|---|---|---|---|---|---|---|---|
| robert-issuer-cap-1 | PASS | 0.096200982 | 0.096688332 | 0.1 | -0.0033116680000000037 | PARTIAL_HOLDINGS | none |
| robert-loss-budget-1 | FAIL | 0.10000046850713584 | 0.10000046850713584 | 0.1 | 4.6850713583679315e-07 | none | none |

Feasibility: FEASIBLE, cash_after 0.21607497199999998. Headline: HAS_FAIL. Contract validation errors: none.

Rules that are not PASS at the boundary: none.

## D. Policy v2 (issuer cap 0.30, 2022 loss budget 0.10)

Policy `pol-robert-real` version 2, content hash `sha256:80d685693ac78b3c609bb7184d08790547a102ff2fef6eae97e971e9bc8fafd1`.

### Closed form, each constraint on its own (final direct weight w of NVDA, w0 = 0)

| constraint | condition | boundary w | computed as |
|---|---|---|---|
| 2022 loss budget | L(w) = -R(w0) - w x r <= 0.1 | `0.08392402835504706` | (0.1 - 0.06066702879627166) / 0.46867353694376046 |
| issuer cap, upper-bound version (rule is PASS up to here) | w + via + U <= 0.3 | `0.287236696` | 0.3 - 0.012275954 - 0.0004873499999999975 |
| issuer cap, lower-bound version (rule is a proven FAIL above here) | w + via > 0.3 | `0.287724046` | 0.3 - 0.012275954 |
| cash | w - w0 <= cash_before | `0.3` | 0.0 + 0.3 |

- Unrounded boundary, recomputed here = min(budget, cap upper-bound version, cash): `0.08392402835504706`
- Engine's internal PASS intervals in d = w - w0 (lower end, upper end), before rounding: robert-issuer-cap-2 `(-inf, 0.287236696)`; robert-loss-budget-1 `(-inf, 0.08392402835504707)`
- Engine `max_compliant`: status SUPPORTED, final_direct_weight `0.083924028` (rounded to 9 decimals), additional_purchase `0.083924028`, binding_constraint `{"type": "RULE", "rule_id": "robert-loss-budget-1"}`, verified_by_rerun True
- Rounding moved the weight by `-3.550470611957124e-10` (comparison tolerance EPS = 1e-09)
- Engine reason text: The largest final direct weight of NVDA at which every evaluated rule passes with cash funding is 0.083924028 of the portfolio (about 8.39%), an additional purchase of 0.083924028 (about 8.39%); the rule robert-loss-budget-1 stops passing just above it. Verified by re-running the same checks at that weight.

### Evidence ids (in the check_result for the requested 0.25)

- max_compliant.evidence_ids: ['ev-max-final', 'ev-max-added']
  - `ev-max-final`: max_compliant_final_weight = 0.083924028; derived_from ['ev-thr-robert-issuer-cap-2', 'ev-via-NVIDIA-SPY-start', 'ev-lo-NVIDIA-start', 'ev-up-NVIDIA-start', 'ev-unattr-SPY-start', 'ev-unattr-XIU.TO-start', 'ev-thr-robert-loss-budget-1', 'ev-scn-ret-start', 'ev-ret-NVDA', 'ev-cash-start', 'ev-w-NVDA-start']; formula: upper end of each constraint, as starting direct weight + (limit - measured value before the purchase) / (change of that value per unit of weight bought): robert-issuer-cap-2 (NVIDIA): 0 + (0.3 - 0.012763304) / 1 = 0.287236696; robert-loss-budget-1: 0 + (0.1 - ≈0.060667029) / ≈0.468673537 ≈ 0.083924028; cash: 0 + 0.3 = 0.3. Largest final direct weight at which every evaluated rule passes: the smallest of these, rounded to 9 decimals = 0.083924028
  - `ev-max-added`: max_compliant_additional_purchase = 0.083924028; derived_from ['ev-max-final', 'ev-w-NVDA-start', 'ev-thr-robert-issuer-cap-2', 'ev-via-NVIDIA-SPY-start', 'ev-lo-NVIDIA-start', 'ev-up-NVIDIA-start', 'ev-unattr-SPY-start', 'ev-unattr-XIU.TO-start', 'ev-thr-robert-loss-budget-1', 'ev-scn-ret-start', 'ev-ret-NVDA', 'ev-cash-start']; formula: 0.083924028 - 0 = 0.083924028
- Records cited by `ev-max-final.derived_from` (the inputs of the closed form):
  - `ev-thr-robert-issuer-cap-2`: FACT rule_threshold = 0.3, state NOT_APPLICABLE, period {"type": "AS_OF", "date": "2026-11-12"}, sources []
  - `ev-via-NVIDIA-SPY-start`: CALCULATION issuer_exposure_via_fund = 0.012275954, state STARTING, period {"type": "AS_OF", "date": "2026-11-12"}, sources []
  - `ev-lo-NVIDIA-start`: CALCULATION exposure_lower = 0.012275954, state STARTING, period {"type": "AS_OF", "date": "2026-11-12"}, sources []
  - `ev-up-NVIDIA-start`: CALCULATION exposure_upper = 0.012763303999999998, state STARTING, period {"type": "AS_OF", "date": "2026-11-12"}, sources []
  - `ev-unattr-SPY-start`: CALCULATION unattributed_fund_weight = 0.00025735000000000064, state STARTING, period {"type": "AS_OF", "date": "2026-11-12"}, sources []
  - `ev-unattr-XIU.TO-start`: CALCULATION unattributed_fund_weight = 0.0002299999999999969, state STARTING, period {"type": "AS_OF", "date": "2026-11-12"}, sources []
  - `ev-thr-robert-loss-budget-1`: FICTIONAL_SCENARIO rule_threshold = 0.1, state NOT_APPLICABLE, period {"type": "AS_OF", "date": "2026-11-12"}, sources []
  - `ev-scn-ret-start`: CALCULATION scenario_terminal_return = -0.060667028796271616, state STARTING, period {"type": "RANGE", "start_date": "2021-12-31", "end_date": "2022-12-30"}, sources []
  - `ev-ret-NVDA`: CALCULATION scenario_instrument_return = -0.46867353694376046, state NOT_APPLICABLE, period {"type": "RANGE", "start_date": "2021-12-31", "end_date": "2022-12-30"}, sources []
  - `ev-cash-start`: FICTIONAL_SCENARIO cash_weight = 0.3, state STARTING, period {"type": "AS_OF", "date": "2026-11-12"}, sources []
  - `ev-w-NVDA-start`: FICTIONAL_SCENARIO position_weight = 0.0, state STARTING, period {"type": "AS_OF", "date": "2026-11-12"}, sources []
- Source records one step behind them (prices, FX rates, constituent weight, coverage, holdings dates):
  - `ev-px-NVDA-base`: FACT price_adj_close = 29.28561, state NOT_APPLICABLE, period {"type": "AS_OF", "date": "2021-12-31"}, sources ['starter_prices_daily']
  - `ev-px-NVDA-end`: FACT price_adj_close = 14.565303, state NOT_APPLICABLE, period {"type": "AS_OF", "date": "2022-12-30"}, sources ['starter_prices_daily']
  - `ev-fx-2021-12-31`: FACT fx_usdcad = 1.2678, state NOT_APPLICABLE, period {"type": "AS_OF", "date": "2021-12-31"}, sources ['starter_fx_usdcad']
  - `ev-fx-2022-12-30`: FACT fx_usdcad = 1.3544, state NOT_APPLICABLE, period {"type": "AS_OF", "date": "2022-12-30"}, sources ['starter_fx_usdcad']
  - `ev-cw-SPY-NVIDIA`: FACT fund_constituent_weight = 0.06137977, state NOT_APPLICABLE, period {"type": "AS_OF", "date": "2026-11-12"}, sources ['ssga_spy_holdings_2026-11-14']
  - `ev-cov-SPY`: CALCULATION fund_coverage_fraction = 0.99871325, state NOT_APPLICABLE, period {"type": "AS_OF", "date": "2026-11-12"}, sources ['ssga_spy_holdings_2026-11-14']
  - `ev-cov-XIU.TO`: CALCULATION fund_coverage_fraction = 0.9977, state NOT_APPLICABLE, period {"type": "AS_OF", "date": "2026-11-12"}, sources ['ishares_xiu_holdings_2026-11-14']
  - `ev-hdate-SPY`: FACT holdings_date = '2026-11-12', state NOT_APPLICABLE, period {"type": "AS_OF", "date": "2026-11-12"}, sources ['ssga_spy_holdings_2026-11-14']
  - `ev-hdate-XIU.TO`: FACT holdings_date = '2026-11-12', state NOT_APPLICABLE, period {"type": "AS_OF", "date": "2026-11-12"}, sources ['ishares_xiu_holdings_2026-11-14']

### check_rules exactly at the boundary (target_direct_weight = 0.083924028)

| rule_id | status | measured lower | measured upper | limit | gap | unknown_causes | breaching_subjects |
|---|---|---|---|---|---|---|---|
| robert-issuer-cap-2 | PASS | 0.096199982 | 0.096687332 | 0.3 | -0.20331266799999997 | PARTIAL_HOLDINGS | none |
| robert-loss-budget-1 | PASS | 0.09999999983359875 | 0.09999999983359875 | 0.1 | -1.6640125388711624e-10 | none | none |

Feasibility: FEASIBLE, cash_after 0.216075972. Headline: ALL_PASS. Contract validation errors: none.

NVIDIA at the boundary: direct 0.083924028, known via funds [('SPY', 0.012275954)], lower 0.096199982, upper 0.096687332 (possible_extra 0.0004873499999999975); headroom of the upper bound to the cap: 0.20331266799999997.
Replay at the boundary: terminal return -0.09999999983359875; loss minus budget: -1.6640125388711624e-10.
max_compliant reported by the run at the boundary: SUPPORTED, final 0.083924028.

### check_rules immediately above the boundary (step +1e-06: target_direct_weight = 0.083925028)

| rule_id | status | measured lower | measured upper | limit | gap | unknown_causes | breaching_subjects |
|---|---|---|---|---|---|---|---|
| robert-issuer-cap-2 | PASS | 0.096200982 | 0.096688332 | 0.3 | -0.203311668 | PARTIAL_HOLDINGS | none |
| robert-loss-budget-1 | FAIL | 0.10000046850713584 | 0.10000046850713584 | 0.1 | 4.6850713583679315e-07 | none | none |

Feasibility: FEASIBLE, cash_after 0.21607497199999998. Headline: HAS_FAIL. Contract validation errors: none.

Rules that are not PASS at the boundary: none.

