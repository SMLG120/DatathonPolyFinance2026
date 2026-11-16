# Release 2026-11-15 (late evening): ETHOS on the hosted site

Frontend only. Times are UTC (2026-11-16). Requested by the owner: the product name ETHOS implemented and published
on both hosts.

## What was published

| | |
|---|---|
| Deployed commit | `d1dc98a` on `fix/ethos-title` (PR #34). Its `frontend/` is `main` `de5cc31` plus the one-line title fix of PR #34 |
| What is new on the site | The ETHOS rebrand (PR #29, #30), the French toggle merge in its current state (PR #28, #32), Print / Save as PDF as on `main` (PR #31), and the title fix (PR #34) |
| Zip | `dist/ethos-frontend-d1dc98a.zip`, sha256 `bd13c1e00a45ac55d3c0a1fc0fceba977ede1457aafadb29d9e47883ab183cda`, 43 files, built with `NEXT_PUBLIC_API_BASE_URL=https://3t4hod912l.execute-api.us-east-1.amazonaws.com` |
| Amplify | app `dwtdk87nismj6`, branch `main`, job 8, `SUCCEED` at 03:21:00 |
| Published with | The AWS MCP tool (`CreateDeployment`, upload of the zip, `StartDeployment`, `GetJob`), not `cloudshell_release.py host` |

Backend, data, infrastructure and permissions were not touched. Before publishing: stack `before-you-buy`
`UPDATE_COMPLETE`, last updated 01:41:30, code key `lambda/byb-backend-3366f6357259c7ec.zip`, snapshot
`snap-2026-11-12-2662b7a89c03`, `AllowedOrigin` `https://main.dwtdk87nismj6.amplifyapp.com`: the values of the
previous record.

## Checks

On the bundle before publication: the only API host is the stack's `ApiBaseUrl`; no loopback address, no account id,
no access key pattern, no source map. The 31 strings of 48 hexadecimal characters are colour palettes of
`d3-scale-chromatic`.

On the source (`d1dc98a`): type check and lint clean, production build passes, 658 unit tests pass and 1 fails
(`LanguageToggle.test.tsx`, see below). `frontend/e2e` was not run on this commit.

On the hosted site, headless Chromium:

- `index.html` is byte-identical to the one in the zip; its title is `ETHOS: fictional simulation`.
- Arriving without a code: the access screen, title `Access code: ETHOS: fictional simulation`, the ETHOS wordmark
  and tagline, no "Test data" label, no console error.
- A deliberately wrong code: `GET /portfolios/robert` answers 403 and the page says "The service did not accept this
  code". The page reaches the real API through CORS and the authorizer.
- With `?fixtures=1`: the headline, the subtitle and both calls to action are there.

**Not checked:** no investigation was run on the hosted site with the real access code, and
`cloudshell_smoke.py`, `cloudshell_customize_check.py` and the `validation/*/hosted_check.py` scripts were not run
for this release. The backend is the one those scripts passed on for the previous release.

## Known state of this build

- The French toggle cannot be reached: the merge of `main` into its branch dropped the language selector from the
  header and the `t()` calls of `PersonaStage.tsx`. The interface is in English. `LanguageToggle.test.tsx` fails for
  this reason.
- Internal names are unchanged: the Amplify app and the stack are still called `before-you-buy`.

## Vercel

The Vercel project builds every push and pull request of the repository without an API address, so it always runs
on test data ("Test data: fixtures"). It is a preview, not the demonstration site: the API allows only the Amplify
origin. Its production build follows `main`; it carries the title fix once PR #34 is merged.

## Rollback

Publish the previous site again: the `frontend.zip` of job 7 (sha256
`fc2ebd76537e1076f07ba8ef2939bf314482b7ca8d4bd320d74d20b845be3502`, see `release-2026-11-15-print-report.md`).
Nothing else needs to be rolled back.
