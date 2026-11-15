# Workflows: Robert and Mateo

Two fictional investors, step by step, in user terms, mapped to the API routes
(`contracts/api.md`) and to the engine concepts (`contracts/SEMANTICS.md`).
Written for commit `d36e41f`.

Read this first:

- **Every expected figure below is a synthetic-fixture outcome** unless a line
  says "real data". The fixture universes use invented fund weights, prices
  and FX rates so that the arithmetic can be done by hand
  (`contracts/fixtures/engine/HAND_CALCS.md`). They are not the real holdings
  or prices of SPY, XIU.TO, NVDA or any company.
- The engine reproduces these outcomes: the engine tests run all 26 fixture
  cases and pass at this commit.
- **The end-to-end path does not exist yet.** At this commit the deployed API
  has only `POST /investigations` and `GET /investigations/{id}`, with a
  placeholder calculation and pre-contract shapes, and the interface runs on
  provisional fixtures. The routes named below are specified in
  `contracts/api.md`; the service code for them is in progress and not in this
  commit.
- Personas come from the official case; portfolios, thresholds and requests
  are invented by the team (`docs/LEAD_DECISIONS.md` D7). Nothing here is
  advice.

## Robert

Source: `contracts/scenarios/robert.json`; fixtures `R1.json`, `R2.json` and
`HAND_CALCS.md` sections R1 and R2; API examples in `contracts/fixtures/api/`.

Portfolio: cash 30%, XBB.TO 30%, SPY 20%, XIU.TO 10%, RY.TO 5%, JNJ 5%.
Objective, in his words: "Preserve my capital while keeping some growth
potential over the next 3 to 5 years."

| # | What the user does | Route | Engine concept | Expected outcome (synthetic fixture) |
| --- | --- | --- | --- | --- |
| 1 | Opens Robert and sees the portfolio | `GET /portfolios/robert` | Fictional scenario; the two scenario rules arrive as `PROPOSED`, inactive | `portfolio_robert.json` |
| 2 | Confirms the two proposed rules: any single company at most 10%; 2022 replay loss at most 10% | `POST /rules/confirm` | Explicit confirmation creates immutable policy version 1. The objective stays a separate object and produces no verdict by itself | Policy `version: 1`, both rules `CONFIRMED` (`confirm_robert_v1.json`) |
| 3 | Requests NVDA at a final direct weight of 25%, funded from cash | (preview: `POST /check`) | Purchase simulation: final direct weight, cash funding, nothing else changes | Additional purchase 25%, cash after 5%, `FEASIBLE` |
| 4 | Starts the investigation and watches the steps | `POST /investigations`, then `GET /investigations/{id}` | Job `QUEUED -> RUNNING -> SUCCEEDED`; steps are tool events; `check_rules` and `max_compliant_amount` are run by the server | Eight steps, the last two `initiated_by: "SERVER"` (`investigation_robert_succeeded.json`) |
| 5 | Reads the verdict | same job | Look-through exposure with bounds; scenario replay; per-rule status | **Single-company rule FAIL**: NVIDIA 26.2% to 26.4% (25% direct + 1.2% through SPY; the range comes from the 0.2% of the portfolio that the XIU.TO file does not report) against 10%, gap 16.2%. **Loss budget FAIL**: replayed 2022 loss 15.25% against 10%, gap 5.25%. Headline `HAS_FAIL`, 0 pass, 2 fail |
| 6 | Reads the largest weight that would pass every rule | same job | Maximum compliant weight: closed form, verified by re-running the evaluator | Final direct weight 8.6%, bound by the single-company rule, `verified_by_rerun: true` |
| 7 | Opens the evidence for a figure | same job | Evidence records: label, source, period, formula, calculation path | For example `ev-spy-nvda-weight` (`challenge_correct_fact.json`) |
| 8 | Challenges the rule: raises the single-company limit to 30% | `POST /investigations/{id}/challenge`, type `CHANGE_RULE` | A new confirmed policy version; the old rule is kept as `SUPERSEDED`; a child investigation starts | Policy `version: 2`, `parent_version: 1`; `robert-issuer-cap-1` superseded by `robert-issuer-cap-2` at 30% (`challenge_change_rule.json`) |
| 9 | Compares the two reports | `GET /investigations/{child id}` | A rule change does not change the facts | **Same measured exposure**, 26.2% to 26.4%. **Single-company rule PASS** against 30%. **Loss budget still FAIL**: loss 15.25%, budget 10%, gap 5.25%. Headline `HAS_FAIL`, 1 pass, 1 fail, 1 rule not evaluated (the superseded one). Maximum compliant weight 10.0%, now bound by the loss budget. Policy consistency stays `CONSISTENT`: one rule failing is not a contradiction between rules (`investigation_robert_after_challenge_succeeded.json`) |

Version 1 and its report stay retrievable and unchanged.

### Robert on the real data

The same request was run through the engine on the real snapshot
(`backend/engine/evidence/robert_max_compliant.md`, engine `byb-engine-1.0.1`,
holdings dated 2026-11-12, replay 2021-12-31 to 2022-12-30). The numbers
differ from the synthetic fixture, and so does the binding rule:

| | Synthetic fixture (R1, R2) | Real data (evidence note) |
| --- | --- | --- |
| NVIDIA exposure through SPY | 1.2% | 1.2275954% |
| NVIDIA after the purchase | 26.2% to 26.4% | 26.23% to 26.28% (0.25 + 0.012275954, plus at most 0.00048735 unreported; our sum of the note's inputs) |
| Replayed 2022 loss after the purchase | 15.25% | 17.78% |
| Maximum compliant final weight, policy v1 | 8.6%, bound by the single-company rule | 8.3924028% (about 8.39%), bound by the 2022 loss budget |
| Maximum compliant final weight, policy v2 | 10.0%, bound by the loss budget | 8.3924028%, unchanged: the loss budget binds in both versions |

Never quote one of these figures without saying which column it comes from. A
live run shows real-data figures only once the worker calls the engine on the
uploaded snapshot (in progress).

## Mateo

Source: `contracts/scenarios/mateo.json`; fixtures `M1.json`, `M2.json` and
`HAND_CALCS.md` sections "Mateo-shaped universe", M1 and M2.

Portfolio: cash 25%, XBB.TO 25%, XIU.TO 20%, ESGV 15%, MSFT 5%, CNR.TO 5%,
FTS.TO 5%. Objective, in his words: "Balanced growth over 8 to 12 years; ESG
matters to me; I want to avoid oil and companies involved in significant
controversies."

| # | What the user does | Route | Engine concept | Expected outcome (synthetic fixture) |
| --- | --- | --- | --- | --- |
| 1 | Opens Mateo and sees the portfolio | `GET /portfolios/mateo` | Fictional scenario | |
| 2 | Submits his sentence | `POST /rules/interpret` | The interpreter drafts; it never invents a number and never activates a rule | One clarification: "What should 'avoid oil' cover?" with four options. Supported: holdings labelled Energy in what the funds report; specific named companies. Shown as unsupported: companies that produce oil; all fossil fuels. A controversy exclusion is drafted with a null threshold (`interpret_mateo_clarification.json`) |
| 3 | Picks the Energy label and sets the tolerated exposure to 0; confirms the controversy exclusion at 0 | `POST /rules/confirm` | Two separate rules: `exclusion` by fund-reported sector, and `controversy_exclusion` by registry records (regulatory finding, court ruling or settlement). A sector label is not a controversy record | Policy version 1 with two confirmed rules |
| 4 | Requests SPY at a final direct weight of 15%, funded from cash | `POST /investigations` | Purchase simulation | Additional 15%, cash after 10%, `FEASIBLE` |
| 5 | Watches the steps | `GET /investigations/{id}` | Holdings, sector labels and registry lookups; no 2022 replay, because no scenario rule exists | Eight steps including `lookup_controversy_evidence` (`investigation_mateo_succeeded.json`) |
| 6 | Reads the verdict | same job | Starting-portfolio findings, kept apart from the effect of the purchase | **The starting portfolio already breaches both rules through XIU.TO**, before any purchase: Enbridge 0.8% and Canadian Natural Resources 0.6%, together 1.4% against a tolerance of 0. Two starting-portfolio findings |
| 7 | Reads each rule | same job | Interval semantics: a proven breach is FAIL; what is unknown stays in the upper bound and the causes | **Energy exclusion FAIL**: 1.4% proven, up to 31.8% possible. Causes of the unknown part: ESGV has no holdings file, XIU.TO is partly reported, no SPY row carries a sector label. What the SPY purchase adds is unresolved: 0 proven, up to 15% possible. **Controversy exclusion FAIL**: 1.7% proven (the purchase adds Exxon Mobil, 0.3%, through SPY), up to 65% possible, because a company without a registry record is "not assessed", never "clean". Headline `HAS_FAIL`, 0 pass, 2 fail, 2 starting-portfolio breaches |
| 8 | Looks for the largest purchase that would pass | same job | Maximum compliant weight | **`NO_FEASIBLE_PURCHASE`**: the Energy exclusion fails at every cash-funded target because the breach exists without the purchase. No number is shown. The purchase is not called a contradiction of the policy |
| 9 | Clarifies: "By oil I meant companies that produce oil, not pipelines or utilities." | `POST /investigations/{id}/challenge`, type `CLARIFY_PREFERENCE` | A new draft; nothing stored changes | "companies that produce oil" is reported as an unsupported definition: no sourced classification is held. The confirmed Energy-label rule stays until he confirms a change (`challenge_clarify_preference.json`) |

A separate what-if on the same portfolio shows a status that is itself
UNKNOWN (fixture M2, `check_mateo_preview_unknown.json`): a draft limit of 20%
on any single company measures 5.9% to 21.3%, because 15.4% of the portfolio
is not reported by any file (ESGV 15%, XIU.TO 0.4%). The limit falls inside
the range: the rule is UNKNOWN, there is no gap, and the maximum compliant
weight is `WITHHELD`. Unknown data never yields a number.

### Mateo on the real data

No engine result for Mateo on the real snapshot is recorded in this commit;
acceptance tests are in progress. What the committed data shows
(`docs/data-sources.md` sections 5.1, 5.3 and 7): XIU.TO's file labels nine
constituents Energy, together 16.66% of the fund; Enbridge is 3.59% and
Canadian Natural Resources 3.45% of XIU.TO, so a 20% XIU.TO position carries
1.408% known exposure to two issuers with a registry record; none of SPY's
503 rows has a sector label; ESGV has no holdings file. The same kind of
result is therefore expected (both rules breached by the starting portfolio,
with large unknown parts), with different figures. That expectation is ours
and is not a recorded test result.
