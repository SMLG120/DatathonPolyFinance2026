# Data sources and evidence

Owner: data-evidence agent. Everything below was produced on **2026-11-14 (UTC)** by the scripts in
`data/scripts/`; every number comes from a file whose SHA-256 is listed here or in
`data/manifests/raw_files_manifest.json`. The text was revised on 2026-11-15 (Milestone 1 closeout); no data
file changed. Fictional simulation only: nothing here is advice.

Read first:

- Holdings are **one dated snapshot (as of 2026-11-12)**. It is used only for today's look-through and is
  **not a historical composition** (section 5).
- In the SPY holdings file **all 503 constituent sectors are null**, so sector rules are **UNKNOWN through SPY**
  (section 5.3).
- The SPY and XIU holdings files were downloaded by script and are **kept by the owner's decision**, because
  their provenance and contents validate (section 5.5).
- Redistribution of the issuer-derived files is **not settled** (section 6). They are git-ignored until the lead decides.
- The controversy registry holds 3 records for 3 issuers. **Absence means "not assessed", never "no controversy"** (section 7).

## 1. Reproduce

Standard library only, Python 3. `-I` isolates the interpreter because the scripts read downloaded files.

```bash
python3 -I data/scripts/audit_starter.py [--also-search DIR]     # read-only audit of data/starter/
python3 -I data/scripts/acquire_holdings.py                      # SPY holdings + SPY product page (2 GETs)
python3 -I data/scripts/acquire_holdings.py --item XIU --from-file <XIU_holdings.csv> --retrieved-at <UTC ISO>
python3 -I data/scripts/acquire_evidence.py                      # 4 evidence pages, 3 terms pages, CIRO listing
python3 -I data/scripts/acquire_evidence.py --item BLACKROCK_CA_TERMS --from-file <saved page> --retrieved-at <UTC ISO>
python3 -I data/scripts/acquire_evidence.py --reverify           # no network: re-check stored pages
python3 -I data/scripts/build_processed.py                       # writes data/processed/*.json (deterministic)
python3 -I data/scripts/quality_checks.py                        # exit 1 on any FAIL
python3 -I data/scripts/selftest_quality_checks.py               # seeds 30 defects, each must be caught
uv run --no-project --with openpyxl --with defusedxml python3 -I data/scripts/quality_checks.py --openpyxl
```

- The build and the checks read local files only; only `acquire_*.py` use the network, and only when a person
  runs them. They do not fetch XIU or the BlackRock terms page by default (BlackRock's terms, section 6). The
  holdings files already held are used as they are (section 5.5).
- Raw files live in `data/raw/` (git-ignored, read-only, never overwritten). A later acquisition creates a new
  file and a new `source_id` (suffix = UTC retrieval date); the build uses the latest snapshot per fund, or the
  one pinned with `--use SOURCE_ID`. **A new snapshot changes the numbers in this document.**
- **Fresh clone.** Git carries neither `data/raw/`, nor the two Yahoo-derived starter files (`prices_daily.csv`,
  `corporate_actions.csv`), nor, until the lead decides (section 6), the four issuer-derived processed files.
  Until they are restored, the audit and the build stop with a message that names what is missing. To rebuild:
  copy the organizers' starter package into `data/starter/`, restore `data/raw/etf_holdings/` and
  `data/raw/etf_product_pages/` (or re-acquire them: new snapshot, new numbers), then run
  `build_processed.py --allow-missing-evidence` and `quality_checks.py --allow-missing-raw` (checks that need an
  absent raw page become SKIP). With the same starter and raw files the seven outputs are byte-identical
  (tested on a copy holding only the files git would track plus those restored files).
- Last run on 2026-11-14: build exit 0, two consecutive builds byte-identical; quality checks 80 passed,
  0 failed, 1 warning (SPY sectors), 0 skipped (81 with `--openpyxl`); self-test 30 of 30 defects detected.

Outputs in `data/processed/`:

| File | Content | In git |
| --- | --- | --- |
| `holdings.json` | SPY and XIU.TO constituents, weights as fractions | ignored, pending decision (section 6) |
| `instruments.json` | 574 instruments: 31 starter + 543 further constituents | ignored, pending decision |
| `market_data.json` | adj_close per instrument, USD/CAD rates, valuation date 2026-11-12 | ignored (Yahoo-derived) |
| `sources.json` | 12 source records used by the files above | yes |
| `controversies.json` | registry scope + 3 records | yes |
| `fund_sector_breakdowns.json` | supplementary: SPY fund-level sector totals published by State Street | ignored, pending decision |
| `build_report.json` | supplementary: the numbers behind this document | ignored, pending decision |

## 2. Sources

Retrieval times are UTC. "Relevant date" is the date the content describes, never the retrieval date.
Full `processing`, `terms` and `limitations` text per source: `data/processed/sources.json`.

### 2.1 Organizer starter files (`data/starter/`, read-only, retrieved by the organizers on 2026-11-13)

| source_id | Publisher / URL | Relevant date | SHA-256 |
| --- | --- | --- | --- |
| `starter_assets_universe` | Datathon organizers (no URL) | 2026-11-13 | `f78de8ecb36d914a3448db63498cc9a04a34d805bccb79c481dda1650755467d` |
| `starter_prices_daily` | Yahoo Finance via yfinance, compiled by the organizers, https://finance.yahoo.com | 2021-11-12 to 2026-11-12 | `ff2a3f2d0a7d72ea835e8d616d041e0510f018340cef3d3e55b918830e8a569d` |
| `starter_fx_usdcad` | Bank of Canada Valet, series FXUSDCAD, https://www.bankofcanada.ca/valet/observations/FXUSDCAD/json | 2021-11-12 to 2026-11-12 | `f04e218ac5b0145fd552b3d0dcfbf73e5e17bb9a6fb4562460dbec95cb8972b3` |
| `starter_corporate_actions` | Yahoo Finance via yfinance, https://finance.yahoo.com | 2021-11-12 to 2026-11-12 | `37d99f1472f9f1c7360432835353488bdf72bb055295ec66155211a30d8312b1` |
| `starter_macro_rates` | Bank of Canada Valet and FRED, https://www.bankofcanada.ca/valet/docs, https://fred.stlouisfed.org | 2021-11-12 to 2026-11-12 | `2c04b0ca5590396fee1f0de13c0b2a95731125a61c79166d553d106f0375c73e` |

- Processing: `assets_universe.csv` gives name, asset class, currency and sector of the 31 starter instruments.
  `prices_daily.csv` → `adj_close` only, copied unchanged (no forward-fill, no alignment, no re-adjustment).
  `fx_usdcad_daily.csv` → `usdcad` copied unchanged. Corporate actions and macro rates: audit only, used by no output.
- Terms (organizers' `sources_metadata.csv`): universe "Free to use within the datathon"; Yahoo terms
  https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html; Bank of Canada terms https://www.bankofcanada.ca/terms/;
  FRED terms https://fred.stlouisfed.org/legal/. Yahoo-derived files are never committed.
- Limitations: sector labels are organizer-assigned and simplified, not an official classification; `adj_close`
  is back-adjusted and shifts when re-downloaded; Yahoo data is not exchange-certified; one FX rate per Canadian
  business day; section 3 findings.

### 2.2 Files retrieved for this project (`data/raw/`, hashes in the manifest)

| source_id (all end `_2026-11-14`) | Publisher | URL | Relevant date | Retrieved (UTC) | Bytes | SHA-256 |
| --- | --- | --- | --- | --- | --- | --- |
| `ssga_spy_holdings` | State Street Investment Management | https://www.ssga.com/library-content/products/fund-data/etfs/us/holdings-daily-us-en-spy.xlsx | 2026-11-12 ("As of 12-Nov-2026") | 22:42:15 | 54,492 | `ed54e8453c6fd9f6efdda93394e2e569adfb5303b03884a45006a5b7f4175c10` |
| `ssga_spy_product_page` | State Street Investment Management | https://www.ssga.com/us/en/intermediary/etfs/state-street-spdr-sp-500-etf-trust-spy | 2026-11-12 | 22:42:16 | 238,459 | `d89aa13878ce43d6b4fb46fe4c8f79b3a330d92c68e5e926fb3e6086396bf603` |
| `ishares_xiu_holdings` | BlackRock Asset Management Canada (iShares) | https://www.blackrock.com/ca/investors/en/products/239832/ishares-sptsx-60-index-etf/1464253357814.ajax?fileType=csv&fileName=XIU_holdings&dataType=fund | 2026-11-12 ("Nov 12, 2026") | 22:30:01 | 11,137 | `9caae3aa6b3aa4ad4faf2b37c9f96fd604f2a10c8cb60831f388ad0a28947527` |
| `epa_exxonmobil_caa_settlement` | U.S. EPA | https://www.epa.gov/enforcement/exxon-mobil-corporationexxonmobil-oil-corporation-clean-air-act-settlement | 2017-10-31 | 23:15:30 | 70,547 | `07e28d21d8cf264a859624b89ab85965708ce705b36539c354e2d6e801ac6a3e` |
| `epa_enbridge_cwa_settlement` | U.S. EPA | https://www.epa.gov/enforcement/enbridge-clean-water-act-settlement | 2016-07-20 | 23:15:31 | 68,078 | `de006b9f318c5428d3f70b43e906dc546e10fcb5fdc23b84353052646311d209` |
| `epa_enbridge_dredging_order` | U.S. EPA | https://www.epa.gov/enforcement/case-summary-epa-orders-enbridge-inc-perform-additional-dredging-remove-oil-kalamazoo | 2013-03-14 | 23:15:32 | 63,067 | `e4ae23f90a95d85da5ee5a15349e8e4c0076b556bec8b83baeb5fb3aa070dad4` |
| `aer_cnrl_penalty_news_release` | Alberta Energy Regulator | https://www.aer.ca/about-aer/media-centre/news-releases/news-release-2024-07-15 | 2024-07-15 | 23:15:34 | 141,430 | `adaa36e100e573af43cf79268162646d126e7043c0b1dc142a27877541d03a92` |
| `ssga_terms_and_conditions` | State Street Investment Management | https://www.ssga.com/us/en/intermediary/footer/terms-and-conditions | no date printed | 23:15:35 | 59,965 | `c7f27b231536d3c29f8be45a6ec54b6d1f279603604c230263063d88750017e3` |
| `blackrock_ca_terms_and_conditions` | BlackRock Asset Management Canada | https://www.blackrock.com/ca/investors/en/terms-and-conditions | "February 2020" | 22:34:58 | 81,868 | `aa34ee4db4ed8f1402dc0b0225cc6c1ee6316c2ea591d87ef1d4c8f24f381caa` |
| `epa_disclaimers` | U.S. EPA | https://www.epa.gov/web-policies-and-procedures/epa-disclaimers | page updated 2026-09-21 | 23:15:36 | 62,565 | `6f0484f971d70b4eb8473ac282ea8f10b53cbe363da6062ff35ed7baede5a4da` |
| `aer_copyright_and_disclaimer` | Alberta Energy Regulator | https://www.aer.ca/copyright-and-disclaimer | no date printed | 23:15:38 | 131,841 | `8ccf7b3739b008d38ad818994ba84a0fa5983b65e0d0f5c44658d6ab837105b0` |
| `cnw_ciro_release_listing` | CNW / Cision, CIRO's press-release listing | https://www.newswire.ca/news/canadian-investment-regulatory-organization-%28ciro%29/?page=2&pagesize=100 | 2026-03-12 | 23:26:16 | 341,612 | `b6559eee966eaafd9c8be79e22c8ffd39df56f294d8ac18abbeb30376723c7c7` |

All were HTTP 200. Retrieval method: one HTTP GET per file by `acquire_*.py` (User-Agent
`before-you-buy-datathon-prototype/1.0`), **except** two BlackRock files that the agent fetched with `curl`
while exploring and then registered with `--from-file`: the XIU CSV (22:30:01, before BlackRock's terms had
been read) and the terms page itself (22:34:58, `curl` run with a browser-like User-Agent string). The owner
has decided to keep both holdings files as fetched (section 5.5).

**State on 2026-11-15** (manifest records `*_2026-11-15` were added that day):

- SPY holdings and product page were fetched again by `acquire_holdings.py` (19:06:40Z and 19:11:28Z). The
  holdings spreadsheet is byte-identical to the 2026-11-14 one (same SHA-256, as of 12-Nov-2026); the build now
  reads `SPY_2026-11-15.xlsx` and `SPY_PAGE_2026-11-15.html` (as of Nov 12 2026, SHA-256 `7644e3e9…5d39`; its
  fund-level sector figures are the ones printed in section 5.3).
- An XIU file was downloaded by hand in a browser and registered (`XIU_2026-11-15.csv`, SHA-256 `681023d8…7970`).
  It is "as of Nov 13, 2026", one day **after** the valuation date, so it is **not used**: the build takes the
  latest file dated on or before the valuation date (`build_processed.py`, `pick_record`), and quality check Q29
  fails if a later one is ever in `holdings.json`. The official case (p. 14, "Time consistency") requires this:
  "do not use information in a simulation before it was available".
- The file in use for XIU.TO is the one of the table above, `XIU_2026-11-14.csv` (as of Nov 12, 2026). It was
  restored on 2026-11-15 from a teammate's copy and verified against the manifest: SHA-256
  `9caae3aa6b3aa4ad4faf2b37c9f96fd604f2a10c8cb60831f388ad0a28947527`, 11,137 bytes.
- For a few hours on 2026-11-15 the processed data and the deployed snapshot `snap-2026-11-12-c2289f2b406d` were
  built from the Nov 13 file. The corrected snapshot is `snap-2026-11-12-2662b7a89c03`.

Every other automated request made to blackrock.com, all on 2026-11-14: the XIU product page and a first test
of the CSV URL (22:26, before the terms were read), and `robots.txt` (22:36:39, 75 seconds after the clause on
automated access had been read). Nothing was requested from blackrock.com after that.

While locating these pages the agent also made exploratory requests with `curl` (to blackrock.com, ssga.com,
ciro.ca and newswire.ca partly with a browser-like User-Agent string) and with a web-fetch tool. Where a site
refused automated requests (ciro.ca, securities-administrators.ca, mass.gov, the newswire.ca release page) it
was left alone: no challenge was solved or bypassed. None of the exploratory copies is used.

The first seven rows are in `sources.json`. The four terms pages and the CIRO listing feed no processed file
and are recorded in the manifest only.

Processing, per kind:

- **Holdings (SPY xlsx, XIU csv).** Parsed completely before anything is written; an unknown line type or layout
  stops the run. Percent weights are divided by 100 and **never rescaled**. Neither issuer prints a publication
  date, so `publication_date` is null (the SPY server's `Last-Modified` header was Fri, 13 Nov 2026 11:23:37 GMT;
  that is server metadata, not a stated publication date).
- **SPY product page.** Only the embedded "Fund Sector Breakdown" block is read (section 5.3).
- **Evidence, terms and listing pages.** A page is accepted only if every sentence we rely on is literally
  present in its visible text; those sentences are stored in the manifest (`verified_phrases`) and re-checked by
  `quality_checks.py` (Q26, Q27). Registry summaries are our own wording.

Terms: section 6. Limitations: sections 5, 7, 8 and 9.

## 3. Audit of the starter files (`audit_starter.py`, exit 0)

| File | Data rows | Finding |
| --- | --- | --- |
| `assets_universe.csv` | 31 | 20 equity, 4 etf_equity, 4 etf_bond, 1 etf_commodity, 2 crypto; `.TO` tickers are CAD, others USD |
| `prices_daily.csv` | 40,049 | 31 tickers, each 2021-11-12 to 2026-11-12; 0 duplicate (date, ticker); 0 missing or non-positive `adj_close`; 0 weekend rows for non-crypto |
| `corporate_actions.csv` | 658 | 651 dividends, 7 splits |
| `fx_usdcad_daily.csv` | 1,245 | 2021-11-12 to 2026-11-12; 0 duplicates; 0 missing; range 1.2451 to 1.4603 |
| `macro_rates.csv` | 8,281 | 9 series; 0 duplicates; not used |

- **Calendars.** 13 TSX tickers × 1,255 rows, 16 U.S. tickers × 1,255 rows, 2 crypto tickers × 1,827 rows.
  27 dates have TSX rows but no U.S. rows and 27 the reverse (union 1,282 dates); 545 dates are crypto-only.
- **FX gaps.** 60 Monday-to-Friday dates inside the range have no rate. U.S. price dates without a same-day
  rate: 37 of 1,255; TSX: 10; crypto: 582 of 1,827. Every price date has a rate on or before it. Rate age for
  U.S. price dates: 0 days on 1,218 dates, 1 on 9, 2 on 2, 3 on 23, **4 on 3 (2021-12-28, 2022-12-27, 2023-12-26)**.
  Maximum age: 4 days (U.S., crypto), 3 days (TSX).
- **ZST.TO** has one zero-volume row, 2022-07-06 (price present). No other zero or missing volume.
- **CNQ.TO, 2022-08-22.** The file lists a 0.75 CAD dividend and a "split" of ratio 1.021 on the same date.
  From 2022-08-19 to 2022-08-22 `close` moves +0.6050% but `adj_close` +2.7794%; the step in `adj_close/close`
  is 1.021614, equal to a dividend-only adjustment 1/(1 − 0.75/35.450539) = 1.021613. Earlier dividends are also
  scaled by 1/1.021 (0.367287 × 1.021 = 0.375). Reading, from the file alone: one special distribution appears
  to be counted twice in CNQ.TO's `adj_close` (about +2.1 percentage points across that date). Not checked
  against the company's investor relations. CNQ.TO is in neither core demo portfolio; a replay that includes
  it inherits this.
- **2022 replay coverage** (base = last `adj_close` on or before 2021-12-31, end = last on or before 2022-12-30).
  For all ten instruments (Robert: XBB.TO, SPY, XIU.TO, RY.TO, JNJ, proposed NVDA; Mateo: XBB.TO, XIU.TO, ESGV,
  MSFT, CNR.TO, FTS.TO, proposed SPY) the base observation is **2021-12-31** and the end observation is
  **2022-12-30**, with 250 (TSX) or 251 (U.S.) observations after the base. A USD/CAD rate exists on both dates
  (age 0 days; 1.2678 and 1.3544); the oldest rate used inside the window is 4 days old.
- **`build_dataset.py`** (mentioned by `STARTER_README.md`):
  Not located in the current checkout; user reports it exists in alphaforge_starter.
  What the audit searched: file names only, in this repository and in
  `/Users/smlgmac/Datathon PolyFinance 2026`; no file or archive was opened. Whether the organizers delivered
  the script was not verified here (`docs/PLAN.md`, P5).
- `data_quality_warnings.txt` says "No warnings."; the three findings above (ZST.TO, CNQ.TO, FX gaps) are ours.

## 4. Calendar and FX conventions

- No forward-fill and no calendar alignment anywhere in `market_data.json`: a row exists only on a day a price
  was reported. `series` is `[date, adj_close]` in the listing currency, strictly ascending.
- `adj_close` already includes splits and dividends. `corporate_actions.csv` is never applied to it.
- "Price on date D" means the last observation on or before D. Consumers report the observation date.
- `fx_usdcad` is CAD per 1 USD (Bank of Canada). A USD value as of date D is converted with the latest rate on
  or before D, the as-of date (backward match), not the date of the price observation; the two coincide
  whenever a price exists on D. The rate's date and age in days are reported. Never a later rate, never
  interpolation. Normative definition: `contracts/SEMANTICS.md` section 7.
- Crypto rows are UTC calendar days, seven days a week; weekend rows use a rate up to 4 days old.
- Valuation date: 2026-11-12, the last date of every price series and of the FX series.

## 5. ETF holdings

### 5.1 Coverage per fund (never rescaled)

| | SPY | XIU.TO |
| --- | --- | --- |
| Holdings date printed in the file | 2026-11-12 | 2026-11-12 |
| Lines in the file | 505 | 65 |
| Equity constituents (`n_holdings`) | 503 | 60 |
| `coverage_fraction` = sum of constituent weights | **0.99871325** | **0.9977** |
| Uncovered fraction = `1 − coverage_fraction` | 0.00128675 | 0.0023 |
| Cash lines, as printed | "US DOLLAR" 0.00096144 | "CAD CASH" 0.0020; "USD CASH" 0.0004; "CASH COLLATERAL CAD MLPFT" 0.0001 |
| Futures lines, as printed | none | "S&P/TSE 60 INDEX DEC 26" (`PTZ6`): weight 0.0000, notional value 39,219,180.00 |
| Other lines, as printed | "CONTRA HOLOGIC INCORPO" (`2602335D`) 0.00000003 | "CONSTELLATION SOFTWARE INC" (`2299955D`): weight 0.0000, market value 0.98 |
| `non_constituent_weight` = the three rows above | 0.00096147 | 0.0025 |
| All printed lines | 0.99967472 | 1.0002 |
| Remaining gap = `1 − all printed lines` | 0.00032528 | −0.0002 |
| Printed precision of a weight | 6 decimals of a percent | 2 decimals of a percent |
| Largest total rounding error at that precision | 505 lines × 0.000000005 = 0.000002525 | 65 lines × 0.00005 = 0.00325 |
| The remaining gap is | **unresolved**: about 129 times the rounding bound, and no line or note in the file accounts for it | **rounding**: well inside the bound (cross-check below) |

- **Coverage residuals.** These are the printed weights, summed as printed; nothing is normalized. SPY's
  uncovered 0.00128675 is cash 0.00096144, one unlisted line 0.00000003 and an unresolved 0.00032528. XIU.TO's
  uncovered 0.0023 is cash and cash collateral 0.0025, less 0.0002 of rounding. XIU's index future is printed
  with weight 0 (its notional is 0.00165520 of the lines' total market value) and is not looked through.
- **How the engine treats it** (lead decision D4): for a fund held at weight `w`, `w × (1 − coverage_fraction)`
  is possible exposure to any issuer and is added to the upper bound. Cash lines are not netted out, the
  uncovered fraction is never treated as zero, and no weight is rescaled.
- Cross-checks: every stored weight equals the printed percent / 100 (Q12). Each XIU printed weight equals
  market value / total market value within 0.004984 percentage points; by market value the constituents are
  0.99749446 of all lines and cash is 0.00250554. An independent read of the SPY spreadsheet with `openpyxl`
  returns the same 4,061 cells (Q25). The SPY file has no market-value column, so its weights cannot be
  recomputed from the file.
- ESGV and QQQ are absent from `holdings.json`: no holdings file, coverage 0, **entirely unknown exposure**.

Numbers for the demos:

| SPY weight | | XIU.TO weight | |
| --- | --- | --- | --- |
| NVDA | 0.06137977 | RY.TO | 0.0958 |
| MSFT | 0.05926991 | SHOP.TO | 0.0605 |
| Alphabet (GOOGL 0.02675267 + GOOG 0.02142682) | 0.04817949 | ENB.TO | 0.0359 |
| XOM | 0.01065439 | CNQ.TO | 0.0345 |
| JNJ | 0.01042601 | Energy, 9 constituents | 0.1666 |

### 5.2 Identity: instruments, issuers, share classes

- `instrument_id`: U.S. tickers as printed (`BRK.B`, `BF.B`). Every Toronto-listed XIU constituent is
  `<ticker as printed>.TO` (`RY` → `RY.TO`, `BIP.UN` → `BIP.UN.TO`), which is the starter universe's form.
  This is needed: XIU's `T`, `L` and `PPL` (TELUS, Loblaw, Pembina) would otherwise collide with SPY's
  `T`, `L` and `PPL` (AT&T, Loews, PPL Corp).
- `issuer_id` is company-level and derived from the name as printed, after removing share-class designators and
  legal forms (`ALPHABET INC CL C` → `ALPHABET`). Starter equities take theirs from the starter name and are
  joined to the fund line **by ticker**: all 20 starter equities are held by SPY or XIU and all 20 join
  (Q16). Funds and crypto assets use their own `instrument_id` as `issuer_id`.
- **Share-class groups** (issuers with more than one instrument), all in SPY, detected from the names and
  confirmed against the CUSIP issuer prefix (500 name groups = 500 CUSIP-6 groups, identical):

  | issuer_id | Instruments | Aggregated SPY weight |
  | --- | --- | --- |
  | `ALPHABET` | GOOGL (class A), GOOG (class C) | 0.04817949 |
  | `FOX` | FOXA (class A), FOX (class B) | 0.00044985 |
  | `NEWS` | NWSA (class A), NWS (class B) | 0.00020115 |

  Berkshire Hathaway appears once (`BRK.B`). XIU has no multi-class group; the CUSIP cross-check is not
  available for XIU (the CSV carries no identifier).
- No company name appears in both funds. Six first-word matches were reviewed and are different companies
  (for example Royal Bank of Canada / Royal Caribbean). A cross-listed company held through both a U.S. and a
  Toronto line would need a manual alias (`MANUAL_NAME_KEY_ALIASES`, currently empty).
- Limits: grouping is name-based; State Street truncates names (for example `MCDONALD S CORP`), so some
  issuer ids look odd (`MCDONALD_S`). They are opaque keys.

### 5.3 Sector

- A constituent's `sector` is only what the fund's own file prints; otherwise null. Nothing is inferred from an
  ETF label such as "Broad market (U.S.)".
- **XIU.TO**: all 60 constituents carry BlackRock's label. Totals: Financials 0.4126, Energy 0.1666, Materials
  0.1275, Information Technology 0.0962, Industrials 0.0825, Consumer Staples 0.0351, Consumer Discretionary
  0.0333, Utilities 0.0260, Communication 0.0157, Real Estate 0.0022. Energy = ENB 0.0359, CNQ 0.0345, SU
  0.0276, TRP 0.0229, CVE 0.0129, CCO 0.0106, PPL 0.0099, IMO 0.0065, TOU 0.0058.
- **SPY**: the Sector column is "-" on **all 503** lines. All 503 constituent sectors are therefore null, no
  constituent-level sector total exists, and **sector rules are UNKNOWN through SPY**. The same issuer's
  product page publishes fund-level totals as of 2026-11-12, kept in `fund_sector_breakdowns.json` (not part of
  the contracts): Information Technology 0.3615, Financials 0.1250, Health Care 0.1038, Consumer Discretionary
  0.0953, Communication Services 0.0888, Industrials 0.0822, Consumer Staples 0.0508, **Energy 0.0358**,
  Utilities 0.0210, Real Estate 0.0185, Materials 0.0173 (sum 1.0000, so the breakdown appears to exclude
  cash). These totals do not say which constituent is in which sector.
- The 31 starter instruments keep the organizers' label in `instruments.json` (`sector_source`
  `starter_assets_universe`); 50 further XIU constituents carry BlackRock's label; the other 493 have none.
- Labels are stored verbatim and differ between sources ("Communication" at BlackRock, "Communication Services"
  at State Street and in the starter file).
- Consequence for a `fund_reported_sector = Energy` rule: 0.1666 of any XIU.TO position is known Energy
  exposure. Through SPY the rule is UNKNOWN: the whole SPY position is possible Energy exposure (upper bound),
  never zero. The fund-level figure (0.0358) classifies no constituent and is not part of the contracts.

### 5.4 Assumptions

- **Snapshot, not history.** The holdings are those of 2026-11-12 and are used only for the look-through of the
  portfolio as it stands today. They say nothing about what SPY or XIU held in 2022. The 2022 replay uses each
  fund's own `adj_close` series, never today's constituents.
- **Survivorship and selection bias.** The 31 starter assets were chosen in 2026 and all have a complete
  2021-11-12 to 2026-11-12 history; companies that were delisted, merged or dropped from an index are absent.
  A replay on this universe understates what an investor in 2022 could have held and lost.
- The index future in XIU and the two unlisted lines are not looked through.

### 5.5 Local holdings files

- **Directory.** `data/raw/etf_holdings/` is the local directory for issuer holdings files; it is git-ignored.
  The build reads holdings only from there: it takes the file named in the manifest, checks its SHA-256 and
  stops if the file is missing or differs. The build and the demo read local files only and never depend on
  live issuer access: `build_processed.py` makes no network request, and the demo reads a snapshot of the
  processed files (`docs/PLAN.md`, P6).
- **Decision.** Both files in use were downloaded by script. The owner has decided to keep them, because their
  provenance and contents validate:

  | Check | `SPY_2026-11-14.xlsx` | `XIU_2026-11-14.csv` |
  | --- | --- | --- |
  | URL | issuer's own site, ssga.com (section 2.2) | issuer's own site, blackrock.com (section 2.2) |
  | HTTP status | 200 | 200 |
  | Retrieval timestamp (UTC) | 2026-11-14T22:42:15Z | 2026-11-14T22:30:01Z |
  | SHA-256 (full value in section 2.2) | `ed54e845…5c10` | `9caae3aa…7527` |
  | As-of date printed in the file | "As of 12-Nov-2026" | "Nov 12, 2026" |
  | Parser cross-check | 505 lines parsed; `openpyxl` reads the same 4,061 cells | 65 lines parsed; each printed weight equals market value / total within 0.004984 percentage points |
  | How it was fetched | one GET by `acquire_holdings.py` | `curl`, before BlackRock's terms had been read |

  The retrieval disclosures stay in section 2.2 and the issuers' terms in section 6.
- **How a person obtains each file** (link labels as shown on 2026-11-14; the XIU label was read from an
  exploratory page copy that is not in the manifest):
  - SPY: open https://www.ssga.com/us/en/intermediary/etfs/state-street-spdr-sp-500-etf-trust-spy, go to
    "Top Holdings" and click "Daily" after "Download All Holdings:". Then run
    `python3 -I data/scripts/acquire_holdings.py --item SPY --from-file <saved .xlsx> --retrieved-at <UTC ISO time>`.
  - XIU: open https://www.blackrock.com/ca/investors/en/products/239832/ishares-sptsx-60-index-etf, go to
    "Holdings" and click "Download Holdings". Then run
    `python3 -I data/scripts/acquire_holdings.py --item XIU --from-file <saved .csv> --retrieved-at <UTC ISO time>`.
  - `--retrieved-at` is the time of the download with a time zone, for example `2026-11-15T14:00:00Z`.
    Registration makes no network request. It validates the file, copies it read-only to
    `data/raw/etf_holdings/<FUND>_<UTC date>.<ext>` and records it in the manifest. A file with a new date is
    a new snapshot: the build then uses it, and the numbers in this document change.
  - To rebuild from the two files already held, copy them into `data/raw/etf_holdings/` under the names above;
    their manifest records already exist.

## 6. Terms of use and redistribution

Quotations are verified against the retrieved terms pages (`data/scripts/_terms.py`, checks Q27).
"Our reading" is an interpretation by the team, not legal advice.

- **State Street** (https://www.ssga.com/us/en/intermediary/footer/terms-and-conditions): "You may not copy,
  reproduce, duplicate, modify, adopt or lend, sell, disseminate or otherwise transfer, in whole or in part, any
  of the information contained in this Site, except for the purpose of accessing the Site and producing
  print-outs for your own personal use, or making a reasonable number of copies of such pages for internal use
  within your organization in accordance with this Agreement." A further clause forbids causing information
  from its databases "to be published, redistributed or retransmitted for other than use for or on behalf of
  yourself". No clause about automated access was found on the page; `robots.txt` does not disallow the two URLs.
- **BlackRock Canada** (https://www.blackrock.com/ca/investors/en/terms-and-conditions, "February 2020"; the
  page served at this investors-site address carries the HTML title "Terms and Conditions - Institutional |
  BlackRock"): "Such content is solely for your personal, non-commercial use." "You may download material
  displayed on this Website for your personal use provided you also retain all copyright and other proprietary
  notices contained on the materials." "You may not distribute, modify, transmit, reuse, repost, or use the content of this
  Website for public or commercial purposes" [...] "without BlackRock's written permission". Prohibited: "Use
  any robot, spider, intelligent agent, other automatic device, or manual process to search, monitor or copy
  this Website or the reports, data, information, content, software, products services, or other materials on,
  generated by or obtained from this Website" [...] "provided that generally available third-party web browsers
  may be used without such permission".
- **EPA** (https://www.epa.gov/web-policies-and-procedures/epa-disclaimers): "These documents may be freely
  distributed and used for non-commercial, scientific and educational purposes." EPA says the disclaimers on
  that page apply only where it states so.
- **AER** (https://www.aer.ca/copyright-and-disclaimer): "the information may be reproduced, in whole or in
  part and by any means, without charge or further permission from the AER." (non-commercial or educational
  use; the AER must be named as the source and a copy must not be presented as official).

Our reading:

| Question | Reading |
| --- | --- |
| Commit raw issuer files? | No, for both issuers. `data/raw/` is git-ignored. |
| Publish the normalized snapshot (`holdings.json`, `instruments.json`, `fund_sector_breakdowns.json`, `build_report.json`) in a public repository? | **Not permitted on a plain reading of either issuer's terms without permission. Legally unclear** for bare facts such as weights. **The lead decides.** Until then the four files are ignored by `data/.gitignore`; deleting four lines there publishes them. |
| Automated retrieval of XIU? | BlackRock's terms do not permit it without permission; a web browser is allowed. `acquire_holdings.py` therefore refuses XIU unless `--from-file` or `--allow-automated XIU` is given. The registered XIU file was fetched with `curl` before the terms were read (section 2.2). **Owner's decision: the script-downloaded SPY and XIU files are kept**, because their provenance and contents validate (section 5.5). |
| Cite and summarise EPA and AER pages? | Permitted for non-commercial educational use with attribution. |

## 7. Controversy registry (`controversies.json`)

Scope: three issuers researched on 2026-11-14 (`EXXON_MOBIL` in SPY; `ENBRIDGE` and
`CANADIAN_NATURAL_RESOURCES` in XIU), in two official listings only: the U.S. EPA list "Civil and Cleanup
Enforcement Cases and Settlements" and the Alberta Energy Regulator news-release listing, pages 1 to 3 (30
releases dated 2023-06-06 to 2025-04-09). **Every other issuer is not assessed.** A record states what the cited
page says; it does not judge whether an event is "significant". A sector label is never a controversy record.

| record_id | Issuer | Event date | Nature | What the source says | Sources |
| --- | --- | --- | --- | --- | --- |
| `exxon-mobil-2017-10-31-epa-clean-air-act-settlement` | EXXON_MOBIL | 2017-10-31 | SETTLEMENT | Proposed settlement resolving **allegations** of Clean Air Act violations at eight petrochemical plants; $2.5 million civil penalty. Subject to public comment and court approval; outcome not reported. | `epa_exxonmobil_caa_settlement_2026-11-14` |
| `enbridge-2016-07-20-epa-clean-water-act-settlement` | ENBRIDGE | 2016-07-20 | SETTLEMENT | Settlement of Clean Water Act claims over two 2010 pipeline oil spills; $62 million in civil penalties, at least $110 million in measures. Revised consent decree submitted 2017-01-19; penalties paid; no court ruling on liability reported. | `epa_enbridge_cwa_settlement_2026-11-14`, `epa_enbridge_dredging_order_2026-11-14` |
| `canadian-natural-resources-2024-07-15-aer-administrative-penalty` | CANADIAN_NATURAL_RESOURCES | 2024-07-15 | REGULATORY_FINDING | The regulator **determined** a contravention of section 155 of Alberta's Environmental Protection and Enhancement Act (May 21 to August 4, 2022; bird fatalities) and ordered payment of $278,000. Appeal status not stated. | `aer_cnrl_penalty_news_release_2026-11-14` |

Consequence for a controversy rule: all three issuers are fund constituents (Enbridge 0.0359 and Canadian
Natural Resources 0.0345 of XIU.TO; Exxon Mobil 0.01065439 of SPY). A portfolio that holds XIU.TO or SPY
therefore has **known, non-zero exposure** to an issuer with a SETTLEMENT or REGULATORY_FINDING record, for
example 0.20 × (0.0359 + 0.0345) = 0.01408 for a 0.20 position in XIU.TO. A rule with tolerance 0 on those
natures is then exceeded by known exposure, not merely unknown. Exposure to every other issuer stays not assessed.

Limits to state whenever a record is shown:

- **Entity links.** EPA's 2016 page names "Enbridge Energy Limited Partnership and several related Enbridge
  companies", not Enbridge Inc.; the link to the listed company rests on EPA's 2013 case summary, which names
  Enbridge Inc. for the same July 2010 spill. EPA's 2017 page names Exxon Mobil Corporation; the SPY file prints
  the XOM line as "EXXONMOBIL HOLDINGS CORP". No corporate reorganisation was researched.
- **Read but not recorded:** EPA's "ExxonMobil Mayflower Clean Water Settlement" (2015). It names ExxonMobil
  Pipeline Company and Mobil Pipeline Company and does not state their relationship to the listed company, so
  attributing it would have relied on memory.
- **Listed but not read:** three other EPA entries naming ExxonMobil entities. Other events exist.
- **Not searched:** courts, securities filings, Canadian federal regulators, U.S. state regulators (mass.gov
  refused the request), any other country, news media. No record of nature ALLEGATION, COURT_RULING or
  COMPANY_DISCLOSURE was sourced.
- Consent decrees, the AER decision and court dockets were not retrieved: outcomes after the cited pages are unknown.

## 8. Regulatory claim check

Claim in the project draft: "in March 2026 CIRO widened the decision-support tools that order-execution-only
dealers may offer, as long as they recommend nothing (CIRO release)".

**Result: partially verified.** The substance is supported by CIRO's own press release as distributed by
CNW/Cision. It was **not verified on ciro.ca**, and the guidance itself was not read.

| Item | Status | Evidence |
| --- | --- | --- |
| A CIRO release titled "CIRO Publishes New Guidance for Order Execution Only Dealers", stamped "Mar 12, 2026, 11:00 ET" | Verified in a hashed file | `cnw_ciro_release_listing_2026-11-14` (CIRO's listing on newswire.ca) |
| Body of the release, https://www.newswire.ca/news-releases/ciro-publishes-new-guidance-for-order-execution-only-dealers-891040380.html, dateline "TORONTO, March 12, 2026 /CNW/", source line "Canadian Investment Regulatory Organization (CIRO)" | Read through a web-fetch tool only: **no raw copy, no hash** (the page answers `curl` with HTTP 403, a bot challenge that was not bypassed) | wording below |
| ciro.ca (release and guidance, link target https://www.ciro.ca/newsroom/publications/new-guidance-order-execution-only-account-services-and-activities) | **Not verified**: every ciro.ca page requested returned HTTP 403 (bot challenge); its `robots.txt` disallows `/newsroom/publications` | none |
| CSA (securities-administrators.ca) | Not verified: HTTP 403. The release does not mention the CSA. | none |
| OSC page listing CIRO rule reviews (osc.ca) | Consulted: no order-execution-only item found, which is consistent with guidance rather than a rule amendment. Not registered, no hash. | none |

Wording of the release as returned by the tool (requested verbatim in pieces, joined by us; re-check in a browser):

- "The Canadian Investment Regulatory Organization (CIRO) has published new guidance that will allow Order
  Execution Only (OEO) dealers to expand the range of decision-making supports they can offer to clients."
- "The new guidance broadens the range of decision-making supports that OEO dealers can offer to clients
  without violating the rule that prohibits them from making recommendations."
- "[...] the new guidance clarifies that OEO dealers are allowed to provide informative resources and
  decision-making supports to clients as long as they do not endorse a specific investment decision and are
  provided with adequate safeguards."
- Supports "can include": "Alerts and notifications;" "Self-help tools;" "Educational information."
- "Key safeguards include": disclosures and disclaimers; clear descriptors and objective criteria; addressing
  conflicts of interest; regular monitoring and updates.

What the pitch may and may not say:

- It is **guidance**, not a rule change; the prohibition on recommendations remains. No effective date is given.
- "as long as they recommend nothing" is looser than the source: the condition is that supports "do not endorse
  a specific investment decision and are provided with adequate safeguards".
- The release does not mention pre-trade checks, portfolios, concentration, risk or suitability. **Whether a tool
  like this prototype is a permitted "decision-making support" is not established.**
- Safer sentence: "On March 12, 2026 CIRO published new guidance that, in its words, 'broadens the range of
  decision-making supports that OEO dealers can offer to clients without violating the rule that prohibits them
  from making recommendations' (CIRO news release)."
- Before the pitch, a person should open the release and the guidance on ciro.ca in a browser.

## 9. Not covered

- **ESGV and QQQ holdings**: deliberately not acquired. Exposure through them is unknown, never zero.
- **Controversies** beyond the three issuers and two listings of section 7.
- **Sector granularity**: no constituent sector for SPY; sector-level labels only for XIU. The XIU file gives
  no sub-industry, so its nine Energy constituents (which include Pembina Pipeline and Cameco as well as
  Canadian Natural Resources) cannot be split. "Oil producers" and "fossil fuels" cannot be evaluated.
- **History**: no past index composition, no delisted assets, no intraday or bid/ask data.
- **Bond, commodity and crypto look-through**: XBB.TO, ZST.TO, AGG, TLT, GLD, BTC-USD and ETH-USD have
  `equity_scope` false and no constituents.
- **Legal review** of the redistribution question and of the regulatory claim.

## 10. What the quality checks assert

`quality_checks.py` recomputes from the raw files and the starter CSVs where it can. It fails on: weights not
in fractions or rescaled to 1; duplicate (fund, instrument); `n_holdings` or coverage not equal to the listed
rows; coverage of an index fund outside [0.95, 1.0005]; a holding whose issuer is missing from the registry;
share classes not aggregated (Alphabet, Fox, News Corp); NVDA or XOM missing from SPY or implausible; a starter
equity not joined to its fund line; a sector that the issuer file does not print; a holdings date in the future
or confused with the retrieval date; a fund composition dated after the valuation date (Q29, no look-ahead); a source without hash, dates or terms; a price series that differs from
the starter file; a controversy record without retrieved evidence, with an event date that is not printed on a
cited page, or a registry that does not say absence means "not assessed"; a terms quotation that is not in the
retrieved terms page; and any output that the validators in `contracts/python/byb_contracts` reject (Q28,
skipped when that package is absent).
