# Code freeze record, 2026-11-15 (22:52 EST)

Written by the release coordinator at the freeze. The backend was not redeployed. The site was published once more
(job 9) because PR #35 was merged into `main` at 22:41 EST, during the freeze checks, and changed two frontend files.

## What is deployed

| Item | Value |
| --- | --- |
| Site | https://main.dwtdk87nismj6.amplifyapp.com/ , Amplify app `dwtdk87nismj6`, branch `main`, **job 9**, `SUCCEED` 22:50:46 EST |
| Site source | `main` at `22b2d9d6` (merge of PR #35); the merge of this record adds one unit test and this file, no site file |
| Site zip | `frontend.zip` sha256 `96ed3bc7ef3dd5087e6a4e5bd288dbeb6c6a8249f9a57fe5582068f7c48cd68f`, built from that source; only API address in it: the stack's `ApiBaseUrl`; kept locally as `dist/frontend-22b2d9d/frontend.zip` (git-ignored) |
| Previous site | job 8, source `d1dc98a` (`release-2026-11-15-ethos.md`): the rollback target |
| Backend code | `lambda/byb-backend-3366f6357259c7ec.zip`, sha256 `3366f6357259c7ec2deb4a272cb85e80ce80dbd877abc4c3dee7376c6780e977` |
| Data snapshot | `snap-2026-11-12-2662b7a89c03` (XIU.TO as of 2026-11-12; no look-ahead) |
| Stack | `before-you-buy`, `UPDATE_COMPLETE`, last updated 2026-11-16 01:41:30Z; no pending change set |
| Release language | English. The French toggle is not exposed |

## Sequence at the freeze

1. 22:36: final `main` was `70435c1`. Checked on it: fullstack 42 of 42; hosted site (job 8) 78 of 78 with the real model;
   the hosted bundles byte-identical to a build of that `main`; the Lambda code hashes equal to the zip packaged from it.
2. 22:41: PR #35 ("Start the journey at step 1 instead of jumping to later steps") was merged on GitHub by a teammate:
   `BrandHero.tsx`, `PersonaStage.tsx` and their tests. `main` became `22b2d9d`, one product change ahead of the site.
3. 22:45 to 22:50: the same checks were run again on `22b2d9d` (below), all green, and the site was published from it
   with `cloudshell_release.py host` (gates: the stack runs the planned backend; both backend checks recorded a pass on it).
4. 22:51: hosted check on job 9.

## Checks on the final source (`22b2d9d` plus this record's test), actual results

| Check | Result |
| --- | --- |
| Frontend unit tests | 659 passed, 1 skipped (the French round trip, see below) |
| Frontend type check and lint | clean |
| `acceptance/fullstack` specs 01 to 07, real handlers on loopback, fresh build | **42 passed** (3.0 min) |
| `frontend/e2e` (fixtures mode, accessibility checks included) | **33 passed** |
| Backend: `scripts/package.py` on this source | `byb-backend-3366f6357259c7ec.zip`; the `CodeSha256` of the API, worker and authorizer functions equals its sha256 |
| `cloudshell_customize_check.py` on the deployed backend | **17 of 17**, investigation in `MODEL` mode |
| `cloudshell_smoke.py` on the deployed backend | First run: 23 checks pass but the investigation ended in `DETERMINISTIC_FALLBACK` (`TOOL_ROUNDS_EXCEEDED` in the worker log), so the script reported failure. Rerun: **PASS, 23 checks, `MODEL` mode** |
| Hosted site after job 9, `validation/print_report/hosted_check.py` (real model) | **78 of 78**; investigations `inv-f240ad26d8e2092976820177df921c2e` (Robert customized) and `inv-3b763893b14c0d92299fdf7ea7e89104` (Mateo, UNKNOWN), both agent mode `MODEL` |
| Not re-run at the freeze | Python suites (the backend is unchanged since it was deployed and checked) |

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

Site: publish again the site of job 8 (source `d1dc98a`; a build of that source is `dist/frontend-freeze/frontend.zip`, sha256
`915208874b83f6d984e97a604bf255581f3b0697395b1460776d1be32a8e79f3`, kept locally), or the `frontend.zip` of job 7
(sha256 `fc2ebd76537e1076f07ba8ef2939bf314482b7ca8d4bd320d74d20b845be3502`).
Backend: `cloudshell_release.py rollback --code-key lambda/byb-backend-3a2220a805a80ce1.zip` (`scripts/deploy.md`, "Rollback").
