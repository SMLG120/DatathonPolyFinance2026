# UX improvement report (2026-11-15)

Branch `agent/beginner-ux-improvements`, from `main` e2cd74d. Not merged, not deployed.
Frontend only: no backend, engine, contract or API change.

## 1–2. Audit findings, by severity

Full table: `docs/BEGINNER_UX_AUDIT.md` (observed in a real browser on the deployed site, test-data mode).

| Severity | Finding | Status |
| --- | --- | --- |
| Critical | The "Evidence Investigator" link drops `?fixtures=1`: test-data users hit the access-code form | Fixed |
| High | Opening the investigator in the same tab loses all progress (state is in memory only) | Fixed (new tab) |
| High | Reloading the result shows an unexplained empty page | Fixed (explained, with the way back) |
| High | Setting limits was a hidden step; "Step 2 of 3: Your limits" under a stepper highlighting "Test an idea" | Fixed (four steps) |
| High | Disabled "Check my idea" unreadable (grey on the dark gradient) | Fixed |
| High | First screen does not say what the tool does | Fixed (introduction) |
| Medium | Result has no plain reading or gathered next actions; "largest compliant purchase" buried | Fixed |
| Medium | Investigator summary percentages do not add up (cash unnamed); starter questions not matched to the selection or the persona's rules | Reported, not changed (component of the evidence agent) |
| Low | Two stacked legends with different wording in the exposure explorer | Reported, not changed |

## 3–4. Changes and files

- `frontend/src/components/shell/AppShell.tsx`: investigator link keeps `?fixtures=1` when requested, opens in a new tab (`rel="opener"` keeps the access code's session copy), accessible name says progress is kept.
- `frontend/src/components/evidence-investigator/EvidenceInvestigatorPage.tsx`: its back link keeps `?fixtures=1` (one attribute).
- `frontend/src/components/ui/Button.tsx`: unavailable style adds `bg-none`.
- `frontend/src/components/stages/VerdictStage.tsx`, `InvestigationStage.tsx`, `ChallengeStage.tsx`: empty states use the current step names; the result's says a reload starts a new session.
- `frontend/src/state/stage.ts`, `frontend/src/components/shell/StageFrame.tsx`, `frontend/src/components/stages/PurchaseStage.tsx`: four-step journey and its Back/Continue links.
- `frontend/src/components/stages/PersonaStage.tsx`: "What this tool does" with the four steps.
- `frontend/src/components/verdict/WhatNext.tsx` (new), `verdict/Report.tsx`: plain reading from `summaryCounts` (the engine's counts) and the next actions.
- Tests: `src/components/BeginnerJourney.test.tsx` (new, 9), `e2e/beginner.spec.ts` (new, 2); updated for four steps: `src/test/app.tsx`, `Stepper.test.tsx`, `App.test.tsx`, `PurchaseStage.test.tsx`, `CustomizeFollowUp.test.tsx`, `EvidenceInvestigatorChat.test.tsx`, `Report.test.tsx`, `e2e/helpers.ts`, `journey.spec.ts`, `mobile.spec.ts`, `states.spec.ts`.

## 5. Visual evidence

Before/after screenshots (git-ignored, local): `frontend/.scratch/audit/before/` (live site) and
`frontend/.scratch/audit/after/` (this branch, local build); `e2e/beginner.spec.ts` writes
`frontend/test-results/screens/beginner-{step1,result}.png`. Disabled button, computed style: before
`linear-gradient(...)` behind `rgb(79,95,125)` text; after `background-image: none` on `rgb(237,243,255)`.

## 6. Graph

Not changed. The exposure explorer already has rotate/zoom/reset, keyboard-selectable parts, a "How to read
this" list, a flat chart below 640 px or without WebGL, and every value in a table; edges are real ownership
paths (direct, through a fund, not attributed). Not implemented: search, filters by fund/sector/evidence status,
a node detail panel beyond the existing parts table. The duplicated legend remains.

## 7. Navigation and onboarding

Before: Profile → Idea (banner: confirm limits first) → Limits ("Step 2 of 3") → Idea → Result; the
investigator link left the session. After: Profile → Set your limits → Test an idea → Understand the result,
each with Back and Continue; the investigator opens beside the session; a reload is explained.
State still lives in memory only: a reload starts a new session (now said on screen, not fixed).

## 8. Tests (final head)

- Unit (vitest): 634 passed of 634 (baseline 625 of 625).
- e2e (Playwright, desktop + mobile projects, fixtures build): 31 passed of 31. Baseline on `main` e2cd74d in a clean worktree: 29 passed of 29.
- Typecheck, lint: clean. Contrast report: 42 pairs, 0 below minimum. Static build: compiled.
- Only the final head was tested, not each intermediate commit.
- Live mode: not tested (needs the access code).

## 9. Remaining limitations

- Workflow state is not persisted: reload or a saved link still starts over.
- Investigator summary denominators and starter questions (finding 8–9) unchanged.
- Graph: no search, filter or detail panel; duplicate legend.
- The result page stays long on mobile.

## 10. Integration

1. Open a PR from `agent/beginner-ux-improvements` into `main`. It touches frontend files only; no open PR and no other branch changed `frontend/` since e2cd74d (checked against `origin/main` e225b79).
2. In `frontend/`: `npm ci && npm test && npm run typecheck && npx eslint . && npm run test:e2e`.
3. Deploy only with authorization, as in `docs/DEPLOYMENT.md` 5.1–5.2 (build with `NEXT_PUBLIC_API_BASE_URL`, manual Amplify deployment), then check the live site with the access code.
