# Beginner UX audit (2026-11-15)

**Method.** A real Chromium browser (Playwright) walked the deployed site
https://main.dwtdk87nismj6.amplifyapp.com/ as a first-time user, at 1366 x 900
and 390 x 844 (touch). The live service needs an access code that this audit
did not use, so the walk ran in the deployed build's test-data mode
(`?fixtures=1`): same code, recorded answers. The live-mode screen was checked
only up to the access-code form. Screenshots are kept locally in
`frontend/.scratch/audit/before/` (git-ignored). Everything below was observed
unless marked *expected*.

## Findings

| # | Workflow | What the user tried | What happened | Severity | Fix | Where |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Evidence investigation, navigation | Open "Evidence Investigator" from the header while using test data | The link drops `?fixtures=1`: the new page asks for an access code. The demo dead-ends | Critical | Keep `?fixtures=1` when it was requested | `components/shell/AppShell.tsx`, `evidence-investigator/EvidenceInvestigatorPage.tsx` |
| 2 | Navigation, recovery | Go to the investigator and come back | It is a separate page in the same tab; workflow state lives in memory only, so coming back starts a new session (confirmed limits and reports gone) | High | Open the investigator in a new tab and say so in the link's name | `AppShell.tsx` |
| 3 | Navigation, recovery | Reload the result page | "Your result" shows "There is no result yet" and "Go to Proposed purchase", a stage name used nowhere else. Nothing says the reload cleared the session | High | Say that a reload or a saved link starts a new session, and what to do; use the current step names | `stages/VerdictStage.tsx`, `InvestigationStage.tsx`, `ChallengeStage.tsx` |
| 4 | Rule confirmation, navigation | Follow the stepper (Profile, Idea, Result) | Setting limits is not a step: "Test an idea" leads to a banner "First, confirm your limits"; the limits page is titled "Step 2 of 3" while the stepper highlights "Test an idea" | High | Make "Set your limits" step 2 of 4; step 1 continues to it; "Back to your limits" from the idea | `state/stage.ts`, `shell/StageFrame.tsx` |
| 5 | Decision submission, accessibility | Read the "Check my idea" button before limits are confirmed | Grey label on the dark primary gradient: unreadable. The unavailable style did not remove the gradient (`background-image`) | High | Add `bg-none` to the unavailable style | `ui/Button.tsx` |
| 6 | First visit, onboarding | Understand the product in 10 seconds | Only a one-line tagline ("Checks a proposed purchase against the rules you confirmed") then three persona cards; nothing says what a limit is, why it matters, or what the steps are | High | A short "What this tool does" block with the four steps, before the profiles | `stages/PersonaStage.tsx` |
| 7 | Verdict | Understand the practical takeaway | Headline and counts are clear ("2 of 2 confirmed rules are not respected"), but the next actions are two buttons with no plain reading; "Largest purchase that respects every confirmed rule" is three levels deep in "More analysis and sources" | Medium | A "What this means and what you can do next" block worded from the engine's counts, with links to the next actions and to that section | `verdict/Report.tsx`, new `verdict/WhatNext.tsx` |
| 8 | Evidence investigation | Read the evidence summary for the whole portfolio | "Verified holdings 69.8%" and "Unresolved holdings 0.2%" do not add up to 100%; the 30% cash is not named, so the denominator is unclear | Medium | Name what the rest is (cash, direct holdings) | `evidence-investigator/EvidenceInvestigatorChat.tsx` (not changed here; another agent's component) |
| 9 | Evidence investigation | Use the starter questions | "What data is missing from this ETF?" is offered while "Whole portfolio" is selected; "Could missing holdings violate my technology limit?" is offered for Robert, who has no technology limit | Medium | Word the starters from the current selection and the persona's rules | same file (not changed here) |
| 10 | Graph interaction | Read the exposure explorer | It works: keyboard-selectable parts, rotate/zoom/reset, a "How to read this" list, a flat chart fallback on narrow screens. Two legends with different wording are stacked ("Through a fund, from its reported holdings" and "Through a fund (light blue)") | Low | One legend | `explorer/*` (not changed: works, and a rewrite would risk the WebGL tests) |
| 11 | Portfolio | See what is in the portfolio | The holdings table is inside a closed panel "View the fictional portfolio"; the case facts are a second closed panel inside it | Low | Kept: the closed panel keeps step 1 short; the intro now says to look at the portfolio | `PersonaStage.tsx` |
| 12 | Mobile | Same journey at 390 px | No sideways scroll on any screen; the stepper shows short labels; the result page is long (3,459 px collapsed, 21,514 px with every section open) | Low | None in this pass | — |
| 13 | Adding a limit | "Add a limit in your own words" | Closed optional panel at the bottom of the limits page; the scenario sentence button and the interpreter work in test data | Low | None in this pass | `stages/GoalsStage.tsx` |

No browser console error and no page error were recorded on any screen.

## Kept as they are (working well for a beginner)

- The persistent banner "Simulation: fictional portfolio, not advice" and the "Test data" tags.
- Proposed rules are visibly "Proposed: inactive" and need an explicit "Confirm these 2 rules with their numbers".
- Each rule result shows measured range, limit and gap, and says what is unknown and that missing data is never counted as zero.
- The Evidence Investigator separates "verified", "hypothetical: not measured" and "what needs to be verified next", and says it uses the data snapshot only.
