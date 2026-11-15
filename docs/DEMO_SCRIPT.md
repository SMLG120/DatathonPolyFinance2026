# Demo script

A recording script of about four minutes: Robert as the main act, Mateo as a
short second act. Written for commit `d36e41f`. The case suggests a video of
"approximately five minutes" covering the problem, the role of the agents, the
data and tools, the result and the explanation (`docs/requirements.md` O8), so
about one minute is left for an architecture slide if wanted
(`docs/ARCHITECTURE.md` section 1).

**This script cannot be recorded live today.** The steps depend on work that
is in progress and not in this commit. Each dependency is a gate:

| Gate | Meaning | State at `d36e41f` |
| --- | --- | --- |
| G1 | Backend phase 2 deployed: real engine in the worker, the contract routes, the data snapshot in S3 | In progress |
| G2 | Frontend on contract types and connected to the live API | In progress |
| G3 | Frontend hosted (`docs/DEPLOYMENT.md`), or served locally with `npm start` against the live API | Not started |
| G4 | Mateo acceptance tests pass on the real data | In progress |
| G5 | Independent validation has no open blocker | In progress |

Button and field labels below are those of the interface at `d36e41f`
(`frontend/src/components/`). Re-check every label after G2.

## Rules for the presenter

Read figures **from the screen**, never from this script. The "expected"
values below exist to catch a wrong build before recording, and each names its
source. If the screen disagrees with the expected value, stop and find out
why; do not record.

Claims the presenter must not make:

- No forecast: never "NVIDIA will lose", "this portfolio would lose", "the
  maximum loss is". Say "replayed through 2022, this allocation ended the year
  X lower".
- No advice or recommendation: never "you should buy 8%", "the right amount
  is", "a better choice is". The maximum compliant weight is "the largest
  weight that passes his own rules", not a suggestion.
- Never "safe", "risk-free", "protected", "guaranteed", "compliant" as a
  general quality. "PASS" means consistent with the investor's own confirmed
  rules.
- No regulatory approval: never "approved by CIRO", "compliant with CIRO".
  Allowed, word for word and nothing stronger: a CIRO news release dated
  2026-03-12 announces guidance that, in its words, "broadens the range of
  decision-making supports that OEO dealers can offer to clients without
  violating the rule that prohibits them from making recommendations". We did
  not read the guidance itself.
- Never "no controversy" or "clean" for a company without a registry record:
  say "not assessed".
- Never "real client", "real account" or "real trade": everything is a
  fictional simulation.
- Never present the fund holdings as historical composition, or the fixtures
  as live results.
- Never "the AI decided": the engine computes the verdict; the model
  interprets words and explains.

## Pre-recording checklist

- [ ] Gates G1 to G3 met (G4 for the Mateo act). Otherwise use the fallback
      and say so on camera.
- [ ] The deployed backend commit and the hosted frontend commit are written
      down: commit SHA, stack output `CodeArtifact`, and the Amplify
      deployment. Nothing in the interface shows the commit at `d36e41f`
      (`docs/DEPLOYMENT.md` section 8).
- [ ] The data snapshot date is known and matches the screen: holdings dated
      2026-11-12, valuation date 2026-11-12 (`docs/data-sources.md`).
- [ ] The access code was typed **off camera** and the access-code screen is
      not in the recording. The code is never spoken, shown or pasted into a
      visible field. Close the browser's developer tools.
- [ ] Live mode: the label "Test data — fixtures" is **absent** from the
      header and the footer, and the address bar has no `?fixtures=1`.
- [ ] The persistent simulation label and the valuation date are visible.
- [ ] One complete dry run of both acts was made on the same deployment within
      the hour, and its investigation ids were noted.
- [ ] A fresh browser session (no earlier reports listed).
- [ ] The recording is saved locally before 2026-11-16: the AWS account, and
      with it any hosted URL, is deleted at the end of that day.

## Act 1: Robert (about 2 min 45 s)

| Time | Click or action | Say | The screen must show | Requires |
| --- | --- | --- | --- | --- |
| 0:00 | Title or the first stage, idle | "Before you change your portfolio, our agent investigates whether the decision respects your own rules, and shows evidence you can challenge. Everything you will see is a fictional simulation. It is not advice." | The simulation label | G3 |
| 0:20 | Stage 1, "Persona & portfolio": choose Robert, click **Use Robert's portfolio** | "Robert is 59 and wants to preserve his capital. His portfolio is invented for this demonstration: 30% cash, bonds, two equity funds and two stocks." | Cash 30%, XBB.TO 30%, SPY 20%, XIU.TO 10%, RY.TO 5%, JNJ 5%; valuation date 2026-11-12 | G2 |
| 0:40 | Stage 2, "Goals & rules": click **Propose rules from this text**, then **Confirm all 2 rules that have a threshold** | "His goal is words. A rule is a number he confirms. Two rules from our fictional scenario: no single company above 10%, and a 2022 replay loss of at most 10%. Nothing is checked until he confirms. That is policy version 1." | Two rule cards going from proposed to confirmed, with their origin; "version 1" | G1, G2 |
| 1:05 | Stage 3, "Proposed purchase": instrument NVDA, **Final direct weight of this position** = 25 | "He wants NVIDIA at 25% of the portfolio, paid from cash." | Target 25%, funding from cash, cash after the purchase 5%; fees and taxes excluded | G1, G2 |
| 1:20 | Click **Start the investigation** | "The agent now investigates. These are the steps the job actually ran: portfolio, policy, fund holdings, exposure, the 2022 replay. The last checks are run by the server whatever the model does." | Steps appearing as they complete, then a finished state. A step marked as run by the server | G1, G2 |
| 1:45 | Click **See the verdict and evidence** | "Two rules, two results. NVIDIA would not be 25% of the portfolio: his S&P 500 fund already holds it." Then read the exposure range and the limit from the screen. | Single-company rule **FAIL**, with a range, the 10% limit and the gap. Expected on real data: about 26.23% to 26.28% (source: `backend/engine/evidence/robert_max_compliant.md`, inputs summed by us) | G1, G2 |
| 2:00 | Point at the loss-budget result | "Replayed through 2022, this allocation ended the year lower than his budget allows. That is a test of one past year, not a forecast." Read the loss and the budget from the screen. | Loss budget **FAIL**; period 2021-12-31 to 2022-12-30; drawdown shown separately as context. Expected on real data: loss about 17.78% against 10% (same source) | G1, G2 |
| 2:10 | Point at the maximum compliant weight, then open one evidence record | "The largest weight that passes his own rules is shown with the rule that binds it. And every figure opens: source, date, formula, and the records it was computed from." | A maximum with its binding rule and "verified by re-running". Expected on real data: about 8.39%, bound by the 2022 loss budget (same source). The evidence drawer with source, date and calculation path | G1, G2 |
| 2:25 | Stage 6, "Challenge": tab **Change a rule**, new limit 30, click **Confirm the change and check again under version 2** | "Robert disagrees and raises his limit to 30%. That is his right. It creates policy version 2; version 1 and its report are kept." | "Version 2"; a second investigation running, then finished | G1, G2 |
| 2:40 | The comparison of the two reports | "The measured exposure has not moved. The limit moved, so that rule now passes. His loss budget still fails, with the measured loss, the budget and the gap. The system does not simply agree." | Same exposure range in both reports; single-company rule **PASS** under v2; loss budget still **FAIL**; both reports openable | G1, G2 |

Expected values in **fixtures mode** are different and synthetic: NVIDIA 26.2%
to 26.4%, loss 15.25%, maximum 8.6% bound by the single-company rule under v1
and 10.0% bound by the loss budget under v2 (`docs/WORKFLOWS.md`). If the
screen shows these in what is supposed to be live mode, the build is in
fixtures mode.

## Act 2: Mateo (about 50 s)

| Time | Click or action | Say | The screen must show | Requires |
| --- | --- | --- | --- | --- |
| 2:55 | Stage 1: choose Mateo, **Use Mateo's portfolio** | "Mateo wants to avoid oil and companies involved in significant controversies." | His portfolio, including ESGV 15% and XIU.TO 20% | G2 |
| 3:05 | Stage 2: **Propose rules from this text** | "'Oil' has no single meaning, so the agent asks instead of guessing. It offers only the definitions we hold sourced data for." | A clarification question with supported options and options shown as unsupported ("companies that produce oil", "all fossil fuels") | G1, G2 |
| 3:15 | Choose the Energy label, set the tolerated exposure to 0, confirm; confirm the controversy exclusion | "He picks the Energy label as his funds report it, at zero, and a separate rule on controversies." | Two confirmed rules, shown as separate rules | G1, G2 |
| 3:25 | Stage 3: SPY, final direct weight 15; **Start the investigation**; **See the verdict and evidence** | "He asks for an S&P 500 fund at 15%. The first finding is not about the purchase: his portfolio already breaches both rules through a Canadian fund he holds." | Two findings about the starting portfolio, apart from the effect of the purchase; both rules **FAIL** | G1, G2, G4 |
| 3:35 | Point at the data coverage and the unknown parts | "And it says what it could not see. One fund has no holdings file, and this fund's file has no sector labels. That is shown as unknown, not as zero. A company without a record is not assessed; it is never called clean." | Coverage per fund (ESGV missing; SPY without sector labels); ranges with their causes; no maximum compliant weight shown | G1, G2, G4 |

Expected statuses for Mateo come from the synthetic fixture M1
(`docs/WORKFLOWS.md`). No real-data result for Mateo is recorded in this
commit, so no expected figure is given: read the screen.

## Close (about 15 s)

| Time | Say |
| --- | --- |
| 3:45 | "The verdicts come from deterministic code. The model interprets words and explains; it cannot change a number. Two funds are covered, three issuers were researched for controversies, and what is missing is shown as unknown. This is a fictional simulation, not advice." |

## Fallback if the live API is unavailable

Use fixtures mode. It needs no backend.

1. Open the same address with `?fixtures=1` added, or run a build made with no
   API base URL (`frontend/src/lib/config.ts`).
2. Check that the label **"Test data — fixtures"** is visible in the header
   and the footer. Keep it in frame.
3. **Say on camera, before the first click:** "The live service is not
   available for this recording. What you see now is recorded test data with
   invented numbers. It shows the interface and the kind of result, not a live
   calculation."
4. Run the same clicks. Say "in this test data" whenever a figure is read.
5. Do not say "the agent investigates" in the present tense about a fixture
   replay. Say "this is how an investigation is displayed".
6. Show the AWS part with the recorded evidence instead:
   `infra/evidence/milestone2.md` is real output of the deployed pipeline with
   a placeholder calculation. Say that it is a placeholder.

Requires: G2 for the figures in `docs/WORKFLOWS.md` to appear. At `d36e41f`
fixtures mode shows hand-written provisional objects
(`frontend/src/lib/provisional-fixtures.ts`), not the contract fixtures; do
not quote expected values against it.
