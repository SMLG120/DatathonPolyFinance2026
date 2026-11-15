# Visual review

Genuine screenshots of the built application, taken with Playwright (Chromium)
by `docs/review/capture.mjs`. Nothing here is a mock-up or a generated image.

Owner of this directory: the review session (branch `review/visual-verification`).

## How to reproduce

    cd frontend && npm ci && npm run build && cd ..
    node docs/review/capture.mjs docs/review/screenshots/<label>

## Baseline — commit `db0b90f` (WIP checkpoint), captured 2026-11-14

**Every screenshot in this set is FIXTURE data, not live output.** The app was
opened with `?fixtures=1`; no API call was made. The figures are recorded test
values (`calculation version: fixture-placeholder-0`), not results of a
financial engine: at this commit `backend/engine/` does not exist and the
deployed worker returns a placeholder. The screens show the "Test data —
fixtures" label for that reason.

Directory: `screenshots/baseline-db0b90f/`. Desktop is 1440 x 900, mobile is
390 x 844 at 2x. All are full-page except the evidence panel.

| File | Scenario | Data |
| --- | --- | --- |
| `01-workspace-robert.png` | Main workspace: Robert's fictional portfolio | Fixture |
| `02-rules-proposed.png` | Proposed rules, inactive until confirmed | Fixture |
| `03-policy-v1-confirmed.png` | Confirmed policy version 1 | Fixture |
| `04-purchase-nvda-25.png` | NVDA at a 25% final direct weight, funded from cash | Fixture |
| `05-investigation-running.png` | Investigation in progress (scripted fixture job) | Fixture |
| `06-investigation-done.png` | All reported investigation steps | Fixture |
| `07-verdict-failed-concentration.png` | Failed concentration check, exposure chart, scenario budget | Fixture |
| `08-evidence-panel.png` | Evidence drawer for the issuer-exposure figure | Fixture |
| `09-rule-change-preview.png` | Issuer cap 10% to 30% as a draft preview | Fixture |
| `10-rule-change-recalculated.png` | Policy version 2 and the old and new results side by side | Fixture |
| `11-mateo-clarification.png` | Mateo: the interpreter asks what "oil" means | Fixture |
| `12-mateo-missing-data-unknown.png` | Missing ESGV holdings shown as UNKNOWN with a possible range | Fixture |
| `mobile-01` to `mobile-07` | Robert's flow through the verdict at 390 px | Fixture |

No live screenshots exist yet. No hosted version exists yet.

## Checks run on `db0b90f` in this worktree

| Check | Result |
| --- | --- |
| `pytest backend/tests contracts/python/tests` (Python 3.14) | 665 passed |
| Frontend `vitest run` | passed (exit 0) |
| `npm run typecheck`, `npm run lint` | clean |
| `npm run build` (static export) | routes `/` and `/_not-found` |
| Playwright e2e incl. axe on every stage | 10 passed |
| Capture run | 19 screenshots, 0 browser console errors |

Measurements: `out/` is 1.0 MB; JavaScript totals 818 kB raw, 244 kB gzipped.
API latency, investigation duration and Lambda figures were **not** measured:
the review session was asked not to call the API while the stack is redeployed.

## Review findings (from the screenshots)

Works as intended in fixtures mode:

- PASS / FAIL / UNKNOWN use an icon and a word, not colour alone.
- Current vs proposed exposure, direct vs through-fund parts and the confirmed
  limit are on one chart with a table of the same numbers below it.
- Raising the cap to 30% shows `measured 26.5%` under both versions; only the
  limit and the status change. Exposure is not shown as having decreased.
- The 2022 replay is labelled "not a forecast"; terminal loss and deepest fall
  are separate rows.
- Policy version, valuation date, holdings dates and coverage are on screen.
- Arithmetic of the Robert fixture is internally consistent:
  25.0% + 20.0% x 7.5% = 26.5%; cash 30.0% - 25.0% = 5.0%; largest compliant
  weight 8.4% (loss budget binds before the 8.5% the issuer cap would allow).

Problems and risks:

1. The verdict page is very long: 5,935 px on desktop and about 9,200 CSS px
   on mobile (roughly eleven screens). The exposure chart starts below the
   first screen on both. A summary with in-page links, or collapsed secondary
   sections (coverage, sentences, about), would help.
2. The evidence drawer's "Calculation path" mixes three formula lines and
   three value lines in one numbered list; a reader cannot tell which are
   steps and which are definitions.
3. Mateo's fixture shows the controversy rule as UNKNOWN; the lead reports
   that real data gives FAIL. The screenshot documents the fixture, not the
   expected live result.
4. Fixture numbers look like results. The label is present at the top and in
   the footer, but a cropped screenshot of the verdict card alone carries no
   fixture marker.
5. After a rule change, the form above the comparison already targets
   "version 3" while the comparison below is about versions 1 and 2; the two
   blocks read as one and can confuse.
