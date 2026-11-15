# Demo script

A recording script of about four minutes: Robert as the main act, Mateo as a
short second act. The case suggests a video of "approximately five minutes"
covering the problem, the role of the agents, the data and tools, the result
and the explanation (`docs/requirements.md` O8), so about one minute is left
for an architecture slide (`docs/ARCHITECTURE.md` section 1).

**Candidate described:** local branch `integration/rc` at `deec650`, plus fixes in progress.

**This script has been walked through locally, never against AWS.** The clicks
and labels below are those of the candidate's frontend, taken from its
components and from the browser specs in `acceptance/fullstack/specs/`. The
same path ran in a browser against the real handlers on one machine, on the
real data; its 14 screens are in `acceptance/fullstack/screenshots/` and are
referred to below as "local backend, real data". A live recording needs these
gates:

| Gate | Meaning | State |
| --- | --- | --- |
| G1 | The candidate's backend is deployed and the post-deploy checks pass (`docs/DEPLOYMENT.md` section 4) | Not done |
| G2 | The frontend is hosted on the origin the API allows (`docs/DEPLOYMENT.md` sections 5 and 6) | Not done |
| G3 | A successful live interpreter call (real Bedrock model) for Mateo's sentence | Never made |
| G4 | Validation finding F-20 closed; the fourth validation pass has no open blocker | In progress |

Without G1 and G2, use a fallback (last section) and say so on camera.

## Rules for the presenter

Read figures **from the screen**, never from this script. The "expected"
values below exist to catch a wrong build before recording, and each names its
source. If the screen disagrees, stop and find out why; do not record.

Claims the presenter must not make:

- No forecast: never "NVIDIA will lose", "this portfolio would lose", "the
  maximum loss is". Say "replayed through 2022, this allocation ended the year
  X lower".
- No advice or recommendation: never "you should buy 8%", "the right amount
  is", "a better choice is". The maximum compliant weight is "the largest
  weight that passes his own rules", not a suggestion.
- Never "safe", "risk-free", "protected", "guaranteed", or "compliant" as a
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
- Never present the fund holdings as historical composition, the fixtures as
  live results, or a local run as an AWS run.
- Never "the AI decided" or "the AI explains": the engine computes the
  verdict and the server writes every sentence; the model reads the investor's
  words, chooses which tools to call and selects evidence.
- If the steps panel says "Deterministic fallback", say so: the model was not
  available and the server ran the same checks without it.

## Pre-recording checklist

- [ ] Gates G1 and G2 met; G3 for the interpreter step of the Mateo act.
- [ ] Written down: the commit that was deployed and hosted; the stack outputs
      `CodeArtifact` and `DataSnapshotId`; the Amplify job id. The interface
      does not show a commit; the explorer's context line shows the policy
      version and the engine's `calculation_version`.
- [ ] Data snapshot date matches the screen: holdings dated 2026-11-12,
      valuation date 2026-11-12.
- [ ] The access code was typed **off camera** on the screen "Enter the access
      code" and that screen is not in the recording. The code is never spoken,
      shown or pasted into a visible field. Developer tools are closed.
- [ ] Live mode: the label "Test data — fixtures" is **absent**, no "Test
      data" tag appears, and the address bar has no `?fixtures=1`.
- [ ] The label "Simulation — fictional portfolio, not advice" is visible.
- [ ] One complete dry run of both acts on the same deployment within the
      hour; investigation ids noted; the agent mode of each run noted (model
      or deterministic fallback).
- [ ] A fresh browser session (a reload starts a new one; earlier reports are
      not listed).
- [ ] Known rough edges are avoided or explained (`acceptance/fullstack/FINDINGS.md`):
      a value below 0.05% can print as "0.0%" (F-06); the evidence drawer has a
      placeholder sentence about source details (F-07); after three failed
      polls the page says the status could not be fetched, and "Check again"
      works (F-02).
- [ ] The recording is saved locally before 2026-11-16: the AWS account, and
      with it any hosted URL, is deleted at the end of that day.

## Act 1: Robert (about 2 min 45 s)

| Time | Click or action | Say | The screen must show | Requires |
| --- | --- | --- | --- | --- |
| 0:00 | Stage 1, idle. Robert is selected when the page opens | "Before you change your portfolio, our agent investigates whether the decision respects your own rules, and shows evidence you can challenge. Everything you will see is a fictional simulation. It is not advice." | "Simulation — fictional portfolio, not advice" | G1, G2 |
| 0:20 | Point at the portfolio table | "Robert is 59 and wants to preserve his capital. His portfolio is invented for this demonstration: 30% cash, bonds, two equity funds and two stocks." | Cash 30%, XBB.TO 30%, SPY 20%, XIU.TO 10%, RY.TO 5%, JNJ 5% | G1, G2 |
| 0:35 | Link **Continue to Goals & rules**; then button **Confirm these 2 rules with their numbers** | "His goal is words. A rule is a number he confirms. Two rules from our fictional scenario: no single company above 10%, and a 2022 replay loss of at most 10%. Nothing is checked until he confirms. That is policy version 1." | Two offered rule cards, then the heading "Confirmed policy — version 1" with both limits. Screen 02 (local backend, real data) | G1, G2 |
| 1:00 | Link **Continue to Proposed purchase**; **Instrument to buy**: NVDA; **Final direct weight of this position**: 25 | "He wants NVIDIA at 25% of the portfolio, paid from cash. This first figure is a preview." | A block labelled "Preview"; cash after the purchase 5%; the exposure explorer in 3D (a flat chart on a narrow window or without WebGL). Screen 03 | G1, G2 |
| 1:20 | Button **Start the investigation** | "The agent now investigates. These are the steps the job actually ran. The rule checks are run by the server whatever the model does." | Steps appearing, a step count, and the agent mode. Screen 04 shows the deterministic fallback | G1, G2 |
| 1:45 | Button **See the verdict and evidence** | "Two rules, two results. NVIDIA would not be 25% of the portfolio: his S&P 500 fund already holds it." Read the range and the limit from the screen. | Single-company rule **FAIL** with a range, the 10% limit and the gap. Expected on real data: 26.23% to 26.28% (0.262275954 to 0.262763304; coordinator's local run). Screen 05 | G1, G2 |
| 2:00 | Point at the loss-budget result | "Replayed through 2022, this allocation ended the year lower than his budget allows. That is a test of one past year, not a forecast." Read the loss and the budget from the screen. | Loss budget **FAIL**; period 2021-12-31 to 2022-12-30. Expected on real data: 17.78% (0.177835413) against 10% (same source) | G1, G2 |
| 2:10 | Point at the largest compliant weight; then a button **Evidence for …** on a rule card | "The largest weight that passes his own rules is shown with the rule that binds it. And every figure opens: source, date, formula, and the records it was computed from." | A maximum with its binding rule. Expected on real data: about 8.39% (0.083924028), bound by the 2022 loss budget (same source). The evidence drawer. Screen 06 | G1, G2 |
| 2:25 | Link **Challenge this result**; tab **Change a rule**; **New value**: 30; then **Confirm the change and check again under a new version** | "Robert disagrees and raises his limit to 30%. That is his right. It creates policy version 2; version 1 and its report are kept." | The current limit, a line starting "Preview:", then a second investigation and the comparison | G1, G2 |
| 2:40 | The comparison; optionally **Open report 1** | "The measured exposure has not moved. The limit moved, so that rule now passes. His loss budget still fails. The system does not simply agree." | The same exposure range in both reports; single-company rule **PASS** under version 2; loss budget still **FAIL**; after "Open report 1": "You are reading an earlier report, checked against policy version 1". Screen 07 | G1, G2 |

If the screen shows 26.2% to 26.4%, a loss of 15.25% or a maximum of 8.6%, the
site is in **fixtures mode**: those are the synthetic figures
(`docs/WORKFLOWS.md`).

## Act 2: Mateo (about 50 s)

| Time | Click or action | Say | The screen must show | Requires |
| --- | --- | --- | --- | --- |
| 2:55 | Stage 1: button **Use Mateo’s portfolio** | "Mateo wants to avoid oil and companies involved in significant controversies." | His portfolio, including ESGV 15% and XIU.TO 20% | G1, G2 |
| 3:05 | **Continue to Goals & rules**; **Use the scenario’s sentence**; **Interpret these words** | "'Oil' has no single meaning, so the agent asks instead of guessing. It offers only the definitions we hold sourced data for." | A question about "oil" with supported options and options listed as unsupported. **Requires a successful live interpreter call** | G1, G2, **G3** |
| 3:15 | Choose the Energy definition, **Use this definition**, enter 0; confirm the rules | "He picks the Energy label as his funds report it, at zero, and a separate rule on controversies." | Two confirmed rules, shown as separate rules; "Confirmed policy — version 1" | G1, G2 |
| 3:25 | **Continue to Proposed purchase**: SPY, 15; **Start the investigation**; **See the verdict and evidence** | "He asks for an S&P 500 fund at 15%. The first finding is not about the purchase: his portfolio already breaches both rules through a Canadian fund he holds." | Both rules **FAIL**, with findings about the starting portfolio kept apart from the effect of the purchase. Expected on real data: Energy 3.33% to 33.38% (starting 3.33% to 18.38%); controversy 1.57% to 65% (`acceptance/mateo/FINDINGS.md`). Screen 11 | G1, G2 |
| 3:35 | Point at the coverage and the ranges | "And it says what it could not see. One fund has no holdings file, and this fund's file has no sector labels. That is shown as unknown, not as zero. A company without a record is not assessed; it is never called clean." | ESGV missing; SPY without sector labels; ranges; no largest-purchase figure | G1, G2 |

**Interpreter fallback (no G3, or the call fails on camera).** The page shows
an alert titled "Your words could not be read" with **Try again**, keeps the
sentence, and still lists the scenario's two offered rules (screen 10, local
backend, real data). Say: "The interpreter is not available right now. The
service says so and nothing is lost. Mateo confirms the two rules the scenario
offers instead." Then click **Confirm these 2 rules with their numbers** and
continue at 3:25. Do not describe the clarification as if it had been shown.

## Close (about 15 s)

| Time | Say |
| --- | --- |
| 3:45 | "The verdicts come from deterministic code, and the server writes every sentence. The model reads the investor's words, chooses tools and selects evidence; it cannot change a number. Two funds are covered, three issuers were researched for controversies, and what is missing is shown as unknown. This is a fictional simulation, not advice." |

## Fallbacks

Choose the highest one that works, and say which one it is before the first
click.

**1. Local backend, real data (no AWS).** The real handlers, engine and data
snapshot on this machine, with S3, Lambda invocation and Bedrock replaced
(`acceptance/fullstack/README.md`, "To look at the stack by hand"). It needs
the git-ignored data files. Say on camera: "The cloud deployment is not
available for this recording. This is the same code running on this laptop,
on the real data. No AWS service and no model is involved; the steps panel
says deterministic fallback." The figures are the real-data figures. The
interpreter step is not available: use the interpreter fallback above. Do not
call this an AWS demonstration.

**2. Fixtures mode (test data).** It needs no backend.

1. Open the site with `?fixtures=1` added, or use a build made with no API
   base URL (`frontend/src/lib/config.ts`).
2. Check that the label **"Test data — fixtures"** is visible. Keep it in
   frame.
3. **Say on camera, before the first click:** "The live service is not
   available for this recording. What you see now is recorded test data with
   invented numbers. It shows the interface and the kind of result, not a live
   calculation."
4. Run the same clicks. Say "in this test data" whenever a figure is read. The
   figures are the synthetic ones of `docs/WORKFLOWS.md`.
5. Do not say "the agent investigates" in the present tense about a fixture
   replay. Say "this is how an investigation is displayed".

In either fallback, the AWS part can be shown only with the recorded evidence
of the earlier slice (`infra/evidence/milestone2.md`): real output of the
deployed pipeline with a **placeholder calculation**. Say that it is a
placeholder and an earlier version.
