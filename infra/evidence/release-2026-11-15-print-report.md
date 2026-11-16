# Release 2026-11-15 (late evening): Print / Save as PDF

Frontend only. Times are UTC (2026-11-16) unless marked EST.

## What was published

| | |
|---|---|
| Feature | "Print / Save as PDF" on a finished report (PR #31, merged into `main` as `04cb17e`) |
| Deployed commit | `a1f3a5d3afbd4284d304c8b71eea062688e0884e` (on `main`'s history through PR #31) |
| Why that commit and not the tip of `main` | It is the source the site already served (`main` `8a6e668`, PR #27) plus this feature and nothing else. See "Not published" below. |
| `frontend.zip` | sha256 `fc2ebd76537e1076f07ba8ef2939bf314482b7ca8d4bd320d74d20b845be3502`, 42 files, built from a clean export of `a1f3a5d` with `NEXT_PUBLIC_API_BASE_URL=https://3t4hod912l.execute-api.us-east-1.amazonaws.com` |
| Amplify | app `dwtdk87nismj6`, branch `main`, job 7, `SUCCEED` at 03:08:26 (22:08:26 EST) |
| Published by | `scripts/cloudshell_release.py host` (boto3 with the workshop profile; the AWS MCP tool was not available, the AWS CLI was not used) |

Build inputs that differ between `8a6e668` and `a1f3a5d`: `globals.css` (print styles appended), `VerdictStage.tsx`,
`Report.tsx`, `WhatNext.tsx`, `ContextPanels.tsx` (one export), and the new `PrintReport.tsx`.

Checks on the bundle before publication: the only API host in it is the stack's `ApiBaseUrl`; no loopback address, no
account id, no access key pattern, no source map. After publication the hosted `index.html` is byte-identical to the
one in the zip.

## Backend, data, infrastructure, permissions: unchanged

Before and after: stack `before-you-buy` `UPDATE_COMPLETE`, last updated 01:41:30 (the Evidence Investigator release),
code key `lambda/byb-backend-3366f6357259c7ec.zip`, `DataSnapshotId` `snap-2026-11-12-2662b7a89c03`, `AllowedOrigin`
`https://main.dwtdk87nismj6.amplifyapp.com`. No change set was created, nothing was uploaded to S3, no parameter and no
IAM resource was touched.

`host` publishes only in front of a backend that passed its checks, so both were run again on the running backend
before publishing (no local record of the earlier passes existed on this machine):

- `scripts/cloudshell_smoke.py`: PASS, 23 checks, 0 warnings, 17 requests, investigation in MODEL mode.
- `scripts/cloudshell_customize_check.py`: PASS (exit 0).

The release plan used by `host` names the running code key and snapshot as the planned ones, with no change set.

## What was on the site before

Amplify job 6 (02:30:08). It has no record in this repository. From its content (the "What this means and what you
can do next" block is present, the ETHOS name is not) it was `main` at `8a6e668`, PR #27. That is an inference from
the served files, not from a record.

## Checks before the merge (branch `feat/print-report-pdf`)

Run on `a1f3a5d` (the deployed commit):

| Check | Result |
|---|---|
| Frontend unit tests | 653 passed |
| Type check, lint, contract copies | clean |
| `frontend/e2e` | 31 passed |
| `acceptance/fullstack` 01-07 on the real local stack, snapshot `2662b7a89c03` | 42 passed |

Run again on the PR head `b9e1976` (merge of `main` `ffe5b91`, which adds the ETHOS rebrand): 657 unit tests,
33 `frontend/e2e`, 42 `acceptance/fullstack`, type check and lint clean. PR #31: CodeRabbit and Vercel successful on
`b9e1976`; no branch protection, no required review; merged with a merge commit.

`acceptance/fullstack` needed two helpers and one label updated for the four-step journey of PR #27 (28 of its cases
stopped at the first navigation helper on `main`); no product assertion was changed.

## Checks on the hosted site after publication

`validation/print_report/hosted_check.py` (headless Chromium, the access code read from SSM and kept in memory):
**PASS, 78 of 78**, two real investigations on the deployed backend, both in agent mode MODEL.

1. Robert, customized (JNJ removed, SPY 15%, cash 40%), NVDA to 25%: `inv-988976e98c07949962c1afc3ca4a3c1a`,
   headline `HAS_FAIL`, portfolio `pf-robert-custom-d96acd4f3b7d`.
2. Mateo, limits 10% and 5%, SPY to 15%: `inv-518583724fdc01c6ba55bf050c001710`, headline `NO_FAIL_BUT_UNKNOWN`,
   both rules UNKNOWN.

For each report the check observed:

- The button "Print / Save as PDF" is on the report and calls the browser's print once. The print dialog itself is
  not driven: the call is recorded, and the PDF is produced by the browser's own PDF output.
- The print document exists only while printing, is never shown on screen, and in print media is shown alone: the
  banner, the interactive report and the controls are not printed; it holds no control, link or chart.
- Investigation id, policy version and id, valuation date (12 Nov 2026 = the result's `2026-11-12`), headline and
  counts equal the job's. Each rule's status equals the engine's, and its measured value, limit and gap are the
  same text as on the screen report. Each rule's reason is the engine's sentence.
- Customized weights: SPY 15.0%, cash 40.0%, no JNJ; the document says "Customized fictional portfolio" with the
  stored portfolio id.
- UNKNOWN: both of Mateo's rules print as UNKNOWN with "Why this is unknown" and "Unknown is not a pass"; the verdict
  says "Not determined" and "this is not a pass"; the block "What is unknown or not measured" comes straight after
  the verdict and lists both rules and every fund with missing or partial holdings; "No maximum is shown".
- Sources: the source ids recorded with the figures are printed (4 for Robert, 2 for Mateo), with the sentence that
  the source registry is not delivered to the page, and no URL.
- After printing, the document is removed, the interactive report is back, the evidence drawer opens. No error in
  the browser console.

The two PDFs written from the hosted site (4 pages each, Letter) were rasterized and looked at page by page: no
clipped text or table, no blank page, headings stay with their tables, text legible, page 1 is a self-contained
summary (identification, verdict, unknowns, first rule).

Regression checks on the hosted site:

- `validation/customize/hosted_check.py`: PASS, 22 checks.
- `validation/release_final/hosted_check.py`: **FAIL, 7 of 8**. The failing step waits for the Evidence Investigator
  heading in the same tab. Since PR #27 the header link opens that page in a new tab, so the script, written at
  `8a3656f`, is out of date. Checked separately on the hosted site: the link has `target="_blank"`, and the new tab
  shows `/evidence/` with its heading. The script was not changed here.

## Limitations

- **Sources: only source ids and holdings dates are printed.** Publisher, title, URL, retrieval date and terms of use
  are not delivered to the page by any route, and no citation is invented. Readable citations need a contract change.
- Four pages for these reports, not one or two. Nothing was removed to shorten the document.
- Tested with headless Chromium only. Safari, Firefox, mobile browsers and real printers were not tested and are not
  claimed to work. The print rule relies on the CSS `:has()` selector.
- The operating system's print dialog was not exercised by automation (see "Manual check").
- The document is in English. The rebrand and the French toggle on `main` are not in the published build.

## Manual check left to the owner

On the hosted site, in Chrome and in the browser used for the demonstration: finish a report, click
"Print / Save as PDF", and confirm that (1) the print dialog opens, (2) its preview shows the report document and
not the application page, (3) "Save as PDF" proposes a file name starting "Before You Buy simulation report",
(4) after closing the dialog the report is still on screen and usable. Repeat once with Cmd/Ctrl+P.

## Not published, and the state of `main`

`main` is ahead of the hosted site. Not in the published build:

- PR #29 and PR #30 (ETHOS rebrand). Tested together with this feature on `b9e1976` (results above), but publishing a
  rename of the product was outside this release.
- PR #28 (French language toggle), merged at 02:54 with its Vercel build failing. At `406eaa4` the frontend did not
  type-check (`Report.tsx` used `t` without importing it, 39 errors), one unit test failed
  (`LanguageToggle.test.tsx`: the language selector is no longer rendered in the header) and
  `sync-contracts --check` reported a stale generated file. PR #32 has since restored the import; the other two
  points were not re-checked here.

The next frontend release from `main` will therefore carry the rebrand and whatever state the French toggle is in;
the print document will then read "ETHOS: simulation report" (commit `b9e1976`).

## Rollback

Frontend only: publish the previous site again. A rebuild of `main` `8a6e668` was prepared before publishing
(`frontend.zip` sha256 `6dc404d81cd8d5b912995d76864ddfa2a199ce818b8dc095baff523f9ae47755`; it is a rebuild, not the
archive of job 6, which was not available). Put it in a release directory as `frontend.zip` and run
`python3 cloudshell_release.py host`. Nothing else needs to be rolled back.
