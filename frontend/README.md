# Before You Buy — frontend

A static single-page app (Next.js App Router, `output: "export"`) for the six
stages of the simulation: persona and portfolio, goals and rules, proposed
purchase, investigation steps, verdict and evidence, challenge. It is a
fictional simulation: it shows what the deterministic engine returned and
never computes a verdict or a financial figure itself.

## Setup

Node 22.12 or newer (developed on Node 24).

The scoped `minimatch` override patches GHSA-g3hv-75wg-m249 in
`@typescript-eslint/typescript-estree`'s development dependency. Remove it
when that package requires a patched release itself; keep the lockfile in sync.

```
npm ci
npm run dev        # http://localhost:3000, fixtures mode unless a base URL is set
npm run build      # static site in out/
npm start          # serves out/ on http://127.0.0.1:4173
```

## Scripts

| Script | What it does |
| --- | --- |
| `npm run build` | Static export into `out/`. |
| `npm run lint` / `npm run typecheck` | ESLint; `next typegen` + `tsc --noEmit` (strict). |
| `npm test` | `sync-contracts --check` (fails when the contract copy is stale), then Vitest + Testing Library (jsdom). |
| `npm run test:e2e` | Builds `out/` and `out-live/`, then runs Playwright (Chromium) with axe. First time: `npm run test:e2e:install`. |
| `npm run contrast` | Computes WCAG contrast for the design-token pairs in `src/app/globals.css`; fails below the minimum. |
| `npm run sync:contracts` | Copies `../contracts` TypeScript, API fixtures and scenarios into `src/generated/contracts/` (marked generated, do not edit). Run it whenever `contracts/` changes. |

## Configuration

| Name | Where | Meaning |
| --- | --- | --- |
| `NEXT_PUBLIC_API_BASE_URL` | build time (`.env.local`, see `.env.example`) | Base URL of the HTTP API. Not a secret. Empty or invalid means fixtures mode. |

- **Fixtures mode** is used when no base URL was built in, or when the page is
  opened with `?fixtures=1`. No request leaves the browser. See the next
  section.
- **Access code** (live mode): typed into a form at runtime, checked against
  the service, then kept in `sessionStorage` for the tab. It is never in the
  bundle, a URL, `localStorage`, a cookie or the console. It is sent as
  `Authorization: Bearer <code>`; the API must allow the headers
  `authorization`, `content-type` and `idempotency-key` and the site origin in
  CORS. A 401 or 403 removes the code and shows the form again; its body is
  never read. Once a code is accepted again, the request that was refused is
  shown as failed, with what happened and a way to make it again. It is not
  repeated automatically.
- **Errors:** a body in the contract's error shape is shown with its message
  and, for a refused request, its `details[].issue`. A body in any other
  shape comes from API Gateway: nothing is read from it and the page words
  the failure itself, from the status. A request the service refused as sent
  (400, 404, 409, 422) is not offered a retry that could only fail again.
- **Idempotency:** `POST /investigations`, and the `CHANGE_RULE` challenge
  that starts a new investigation, carry an `Idempotency-Key` from
  `crypto.randomUUID()`: one key per user action, reused when that action is
  retried (after a 429 or a network error, for example). After
  `503 WORKER_INVOCATION_FAILED` the retry carries a new key.
- **Policy conflict:** on `409 POLICY_VERSION_CONFLICT` the page sets the
  policy it held aside and starts the rule stage again: every rule is a
  proposal and the next confirmation creates a new policy. Reports already
  made keep the version they were checked against.
- **Timing:** the poll interval and deadline are the contract's
  `POLL_INTERVAL_MS` and `POLL_DEADLINE_MS`, in both modes. A failed poll
  (network, timeout, 429, 5xx) is retried at the same interval until the
  deadline; 401, 403, 404 and 410 stop it.
  Individual HTTP timeouts and caller cancellation cover response bodies as
  well as headers. Selecting a persona cancels the previous session's actions;
  even late responses that ignore cancellation cannot update the new session.
- **Ids from the interpreter:** it numbers questions, drafts and objectives
  from 1 in every answer. A question is keyed by its answer
  (`interpretation_id`) and its id; an objective is recognised by its words; a
  draft whose id another rule already has is listed under an id of its own
  (`draft-excl-1-2`), because a policy cannot hold two rules under one id.
- **Small figures:** a value that is not zero is never printed as zero:
  `< 0.1%` (or `> −0.1%`) at the decimals shown.
- No AWS SDK and no credentials in the browser.

## Fixtures mode: what it replays

The fixtures client (`src/lib/api/fixtures-client.ts`) replays the recorded
bodies of `contracts/fixtures/api`. It calculates nothing and writes no
result. A request with no recorded answer is refused with a calm "the test
data holds no recorded answer" message that says what is recorded; nothing is
invented in its place.

Every block of figures carries a visible **Test data** tag in this mode
(including the verdict summary card), and the banner shows "Test data —
fixtures" on every screen. In live mode neither appears.

What can be done on test data:

- **Robert:** portfolio; the scenario's two rules confirmed as policy
  version 1; a draft preview of the single-company limit at 20%; the
  investigation of NVDA at a final weight of 25%; the rule change to 30%
  (policy version 2 and a second investigation, compared with the first); a
  corrected fact (shown as unverified, used in no calculation); a request the
  service cannot evaluate (RY.TO at 2%, below what is held).
- **Mateo:** portfolio; his sentence interpreted into a clarification
  question; the investigation of SPY at 15% (two rules not respected, both
  already not respected before the purchase, one fund without a holdings
  file); a clarified preference. His recorded UNKNOWN preview is covered by
  component tests; no path in the interface sends that request.
- **Amira** is the third persona. Her portfolio is replayed from `portfolio_amira` in test data and comes from `GET /portfolios/amira` in live mode; her sentence gets a clarification question. The explicit min/max conflict pair in her scenario (`alternative_rule_sets`) is not offered in the interface.
- `?simulate=job-failed`, `poll-timeout`, `portfolio-error` or `check-error`
  exercises the failure states.

Five answers are not recordings of the route they answer. Each is kept small
and is listed in the header of the fixtures client:

1. `GET /portfolio` is recorded for Robert only. For Mateo the answer is the
   contract's scenario file with the registry entries it names.
2. A confirmation writes the stored rules the way `contracts/SEMANTICS.md`
   §14 describes (status, provenance, a new rule id on a change).
3. The queued and running snapshots of a job that has only a final recording
   are that job cut short (no result, fewer steps).
4. A `CORRECT_FACT` challenge echoes the user's assertion as an unverified
   correction.
5. `POST /check` on a stored policy version answers with the recorded result
   of the investigation of the same request under the same rules.

## Where things are

- `src/generated/contracts/` — the copy of `../contracts` (generated).
  `src/lib/contracts.ts` and `src/lib/fixtures.ts` are the only doors to it;
  components import from these two modules only.
- `src/lib/format.ts` — the one module that turns portfolio fractions
  (10% = 0.10) into text. Data stays fractions everywhere else.
- `src/lib/result.ts` — decides, before anything is drawn, whether a result
  body may be shown as a verdict (execution status `OK`), is an execution
  state, or is unreadable. `src/lib/verdict.ts` — the wording of statuses,
  headlines and counts as the service sent them. Neither decides a status.
- `src/lib/api/` — `ApiClient` interface, the live `fetch` client and the
  fixtures client.
- `src/state/` — runtime (mode, access code), stage (URL hash), workflow store.
- `src/hooks/` — `usePolling` (deadline, visible failure), `useDebouncedPreview`
  and `useLatestRequest` (a stale answer never replaces a newer one).
- `src/components/` — `ui/` kit, `shell/`, one folder per stage area.
- `src/components/explorer/` — the exposure explorer: one company before and
  after the purchase, as a 3D drawing with its values in a table. `model.ts`
  copies the figures out of a `CheckResult`; `capability.ts` decides between
  the drawing and the fallback; `ExposureScene.tsx` is the only file that
  imports `three` and is loaded with `import()`.
- `src/components/exposure3d/ExposureExplorerSlots.tsx` — where the explorer
  is mounted. Each slot takes the `CheckResult` as its only data prop:
  `VerdictExposureExplorerSlot` (`result: CheckResult`, beside the 2D chart in
  `verdict/ExposurePanel.tsx`) and `PurchaseExposureExplorerSlot`
  (`result: CheckResult | null`, under the preview in
  `stages/PurchaseStage.tsx`; nothing is rendered for `null`).
- `src/test/` — test helpers. `probes.ts` holds the recorded bodies handed to
  tests and the few derived inputs no recording covers.
- `e2e/` — Playwright specs. `scripts/` — static server, contrast report,
  contract sync, e2e builds.

## What the interface never does

- **No financial arithmetic.** Cash after the purchase, the additional
  purchase, before and after figures, the headline, the counts and the maximum
  compliant weight are fields of the API response. Before a result exists the
  purchase stage shows the entered target and says the figures appear after
  the check; a figure shown earlier comes from `POST /check` and is labelled a
  preview.
- **No verdict without an executed check.** Pass and fail styling requires
  execution status `OK`. Anything else shows the execution state.
- **Unknown is not a pass.** An unknown rule shows its cause from
  `unknown_causes`. A fund below full coverage reads "Partial" with the
  percentage cut, never rounded up to 100.
- **No markup from a sentence, and no model-written sentence promised.**
  Explanation sentences are rendered as plain text. The service writes them
  all (`rendered_by: TEMPLATE`), so the page says of none that a model wrote
  it; any other marker gets a neutral label.
- **No arithmetic in the explorer.** Its figures are copied from the result
  (`direct`, `known`, `lower`, `upper`, `possible_extra`, the rule's `limit`).
  The only numbers it works out are the three labels of the drawing's scale.
- **No source registry.** No route delivers it, so the evidence drawer shows
  the source ids, dates and assumptions of the evidence records and says
  plainly, on test data and on the live service alike, that only the ids are
  available. It promises nothing more.

## Accessibility

- **Landmarks and headings:** banner notice, header with the stage navigation,
  one `main`, footer; one `h1` per stage. A stage change moves focus to the
  `h1`, scrolls to the top and updates the page title.
- **Status is never colour alone:** every status has a word, an icon with its
  own shape (circle, octagon, diamond) and a border style.
- **Live regions:** investigation steps (`role="log"`), previews and saved
  actions (`role="status"`), failures (`role="alert"`).
- **Buttons that cannot act yet** stay focusable (`aria-disabled`) and say why
  when activated, instead of disappearing from the tab order.
- **Motion:** `prefers-reduced-motion` removes animations and transitions.
- **Verdict page:** headline, per-rule statuses and the exposure chart come
  first. Coverage, the explanation sentences and the about text are native
  `details` elements (Enter or Space). Links in the headline card jump to a
  section and open it.
- **Chart:** each company is a native `details` row. Enter, Space, a click or
  a tap opens a table with the value of every segment; nothing depends on
  hover and there are no `title` tooltips. The ranges are text beside the
  bars. Measured exposure is solid; possible but unmeasured exposure is hollow
  and dashed; `forced-colors` gets textures. On a narrow screen the limit
  label is a line of its own above the bars.
- **Exposure explorer:** an enhancement beside the chart, which stays on
  screen. The 3D drawing is shown only with WebGL, a screen at least 768 px
  wide, no forced colours and no request for reduced motion; its script is
  fetched only then. Otherwise, and if the script or the drawing fails, the
  flat chart of the same company takes its place with the reason in a
  sentence, and nothing is reported as an error. The canvas is hidden from
  assistive technology and is not a tab stop: every value is in the table
  next to it, every part is an HTML button, and the view is turned, zoomed
  and reset with ordinary buttons.
- **Evidence drawer:** the formula as recorded by the engine is one block and
  the values it was computed from are another.
- **Challenge stage:** the rule-change form and the comparison of the two
  policy versions are separate sections with their own headings.
- **Small screens:** no sideways scrolling at 360 px, with every section open.
  The replay's table of returns stacks its rows on a phone and keeps its table
  roles.
- **Primitives:** Radix Dialog (evidence drawer: focus trap, inert background,
  Escape, focus return) and Radix Tabs (challenge paths: roving focus, arrow
  keys) because those behaviours are easy to get wrong by hand. Everything
  else is a native element: `button`, `a`, `select`, `input type="range"`,
  `details`. The threshold field is `type="text" inputmode="decimal"` so an
  empty value stays empty and is never coerced to 0.

### Keyboard

| Key | Where | Effect |
| --- | --- | --- |
| Tab / Shift+Tab | everywhere | Next / previous control, in reading order. First stop: "Skip to main content". |
| Enter | links, buttons, stage navigation | Activate; a stage link opens that stage. |
| Enter / Space | report sections, chart rows | Open or close. |
| Space | buttons, checkboxes, radios | Activate / toggle. |
| Arrow keys | threshold slider | Change by 0.5 points (Home / End: ends of the range). |
| Arrow keys | challenge tabs, radio groups | Move between options. |
| Escape | evidence drawer | Close; focus returns to the control that opened it. |
| Browser Back / Forward | everywhere | Previous / next stage (the stage is in the URL hash). |

### Contrast (computed, WCAG 2.x)

`npm run contrast` checks 42 token pairs; all pass. Lowest ratios per group:

| Pair | Ratio | Minimum |
| --- | --- | --- |
| Body text `ink` on `sunken` | 14.17:1 | 4.5 |
| Secondary text `ink-muted` on `accent-soft` | 6.59:1 | 4.5 |
| Links `accent` on `accent-soft` | 7.18:1 | 4.5 |
| Primary button `on-accent` on `accent` | 8.39:1 | 4.5 |
| Pass / Fail / Unknown badge text on its soft background | 6.59 / 7.05 / 6.80:1 | 4.5 |
| Banner `on-banner-muted` on `banner` | 10.68:1 | 4.5 |
| Control borders `line-strong` on `sunken` | 4.07:1 | 3 |
| Focus ring `accent` on `canvas` | 7.69:1 | 3 |
| Chart, through-funds segment on the track | 3.14:1 | 3 |

## Tests

- **Unit / component** (`src/**/*.test.ts(x)`). Expected values are the
  recorded contract bodies. Covered: formatting; the stale-response guards;
  polling deadline and failure; rule cards and draft previews; the report
  (page order, sections, figures shown as sent, Mateo's result, the UNKNOWN
  preview, coverage wording, plain-text explanation); the exposure chart; the
  historical replay; the evidence drawer; the purchase stage; the six-stage
  flow in jsdom, including idempotency keys, the corrected fact, the rule
  change and the live-mode access code.
- **Guard** (`src/guard.test.ts`): no hand-written result object anywhere
  under `src/` outside `generated/`, no `innerHTML` or
  `dangerouslySetInnerHTML`, no `Math.random`, no AWS SDK and no
  `@react-three/*`. `three` may be imported only under
  `src/components/explorer/`, and no page may reach it through static
  imports: the file that imports it is loaded with `import()` only. `src/test/probes.ts` is the one
  file allowed to replace named fields of a recorded body, and it may not
  write a whole result. Those probes exist to show that a screen reads a value
  instead of working it out (figures that no arithmetic connects), or that it
  does not draw a verdict it must not draw.
- **End to end** (`e2e/`, static builds, Chromium, axe WCAG 2.2 A/AA plus
  best-practice rules on every stage). No spec talks to the real API.
  - `journey.spec.ts` — the six stages with the keyboard only: focus order,
    focus rings, report sections, chart rows, drawer focus trap and focus
    return.
  - `states.spec.ts` — Mateo, and the states other than the happy path.
  - `explorer.spec.ts` — the exposure explorer: `three` is fetched only when
    the drawing is about to be shown and a frame is really drawn (skipped
    with a message where the browser has no WebGL); the flat chart without
    WebGL, with reduced motion requested, and when the drawing's script
    cannot be loaded.
  - `mobile.spec.ts` — 390×844 and 360 px with taps, no element wider than
    the viewport.
  - `live.spec.ts` — the access-code gate of a live-mode build whose API
    address is a local mock on `127.0.0.1` (made-up codes; no real service).

## Known limits

- Workflow state is in memory: a reload starts again at stage 1 (the access
  code survives a reload in its tab).
- Light theme only.
- A confirmed rule is changed through the Challenge stage, which creates a
  new policy version; it cannot be edited in place.
- On test data only the recorded requests have an answer: other weights,
  other instruments and free text get the "no recorded answer" message.
- Source titles, publishers, retrieval dates and terms of use are not shown:
  no route delivers the source registry. Only source ids are.
- The explorer shows the first company the engine lists (the largest proven
  exposure after the purchase); it has no selector for the others, which stay
  in the chart beside it. It draws a limit only when exactly one single-company
  limit was evaluated.
- The live client has been exercised against the local mock only, not
  against the deployed API.
- ESLint is held at 9: `eslint-config-next` does not accept ESLint 10 yet.
  jsdom is held at 29 and TypeScript at 5.x for the same kind of peer-range
  reason.

Next.js documentation matching the installed version is in
`node_modules/next/dist/docs/`.
