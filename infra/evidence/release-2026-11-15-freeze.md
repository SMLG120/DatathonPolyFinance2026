# Code freeze record, 2026-11-15 (about 22:45 EST)

Written by the release coordinator at the freeze. Nothing was deployed for this record: the deployed inputs already
match the final code.

## What is deployed

| Item | Value |
| --- | --- |
| Site | https://main.dwtdk87nismj6.amplifyapp.com/ , Amplify app `dwtdk87nismj6`, branch `main`, **job 8**, `SUCCEED` 22:21 EST (`release-2026-11-15-ethos.md`) |
| Site source | commit `d1dc98a`; final `main` differs from it only by release records, validation scripts and one unit test |
| Backend code | `lambda/byb-backend-3366f6357259c7ec.zip`, sha256 `3366f6357259c7ec2deb4a272cb85e80ce80dbd877abc4c3dee7376c6780e977` |
| Data snapshot | `snap-2026-11-12-2662b7a89c03` (XIU.TO as of 2026-11-12; no look-ahead) |
| Stack | `before-you-buy`, `UPDATE_COMPLETE`, last updated 2026-11-16 01:41:30Z; no pending change set |
| Release language | English. The French toggle is not exposed |

## How the match between code and deployment was checked (22:35 to 22:43 EST)

- **Backend:** `scripts/package.py` on final `main` produces `byb-backend-3366f6357259c7ec.zip`; the `CodeSha256` of the API,
  worker and authorizer functions equals the sha256 of that zip.
- **Site:** a production build of final `main` references the same 11 content-hashed bundles as the hosted page, and each
  hosted bundle is byte-identical to the local one. (`index.html` itself differs between two builds of the same source, so
  it is not compared.) The only API address in the build is the stack's `ApiBaseUrl`.
- The zip published as job 8 (`dist/ethos-frontend-d1dc98a.zip`, sha256 `bd13c1e0...ab183cda` according to
  `release-2026-11-15-ethos.md`) was built in another session and is **not on the coordinator's machine**: its hash was not
  re-verified. A reference build of final `main` is kept locally as `dist/frontend-freeze/frontend.zip`
  (sha256 `915208874b83f6d984e97a604bf255581f3b0697395b1460776d1be32a8e79f3`, 43 files, git-ignored).

## Checks at the freeze (actual results)

| Check | Result |
| --- | --- |
| `acceptance/fullstack` specs 01 to 07 on final `main`, real handlers on loopback, fresh build | **42 passed** (3.0 min) |
| Hosted site, `validation/print_report/hosted_check.py` (job 8, real model) | **78 of 78**; investigations `inv-2084c6ff659409c961d96146db7e0ef7` (Robert customized) and `inv-27736f66c4852ebae23247f08a55289d` (Mateo, UNKNOWN), both agent mode `MODEL` |
| `cloudshell_customize_check.py` on the deployed backend | **17 of 17**, investigation in `MODEL` mode |
| `cloudshell_smoke.py` on the deployed backend | First run: 23 checks pass but the investigation ended in `DETERMINISTIC_FALLBACK` (`TOOL_ROUNDS_EXCEEDED` in the worker log), so the script reported failure. Rerun: **PASS, 23 checks, `MODEL` mode** |
| Frontend unit tests | 659 passed, 1 skipped (the French round trip, see below) |
| Frontend type check and lint | clean |
| Not re-run at the freeze | Python suites (backend unchanged since it was deployed and checked) and `frontend/e2e` |

Job 8's own record says no investigation had been run on the hosted site after it was published; the hosted check above closes that gap.

## Known limitations at the freeze

- **Occasional fallback of the investigator.** In the last 25 minutes before the freeze, 1 of 6 live investigations
  exceeded the model's tool-round limit and was completed by the deterministic path. The verdict and every figure are
  the same in both modes; the report says which mode ran. In a live demonstration, a rerun normally shows `MODEL`.
- **French is not available.** The translation catalogue is in the build, but the language selector was dropped from the
  header in a merge and is not exposed. The interface reads a saved preference (`byb.locale` in the browser's local
  storage for the site's origin); no published version of the site has ever offered a way to save one, so ordinary
  returning visitors get English. Someone who sets that value by hand would see a partly translated interface with no
  selector. `LanguageToggle.test.tsx` now states the release behaviour; the French round trip is skipped until the
  selector returns.
- The banner's valuation date is visually hidden; evidence shows source identifiers, not publisher and link; one shared
  access code; the AWS account is deleted at the end of 2026-11-16.
- `validation/release_final/hosted_check.py` fails 7 of 8 since PR #27 (it expects the Evidence Investigator in the same
  tab); stale, not a product defect (`release-2026-11-15-print-report.md`).

## Rollback, if ever needed

Site: publish the `frontend.zip` of job 7 (sha256 `fc2ebd76537e1076f07ba8ef2939bf314482b7ca8d4bd320d74d20b845be3502`).
Backend: `cloudshell_release.py rollback --code-key lambda/byb-backend-3a2220a805a80ce1.zip` (`scripts/deploy.md`, "Rollback").
