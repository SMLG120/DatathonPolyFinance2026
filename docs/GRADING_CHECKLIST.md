# Grading alignment — critical checklist

Reviewed 2026-11-15 against `Datathon - Case Officiel 2026 ENG.pdf`, especially
the six weighted criteria on p.19, deliverables on pp.15–16 and boundaries on
pp.17–18. Code reviewed: `9531380`. The full jury rubric is private; this is
an evidence review, not a predicted grade. Checked = demonstrated baseline;
unchecked = material gap or unverified completion, not necessarily absent code.

**Verdict: coherent and strongly aligned, but not every criterion is closed.**
Checking an investor's own confirmed rules is a defensible decision-support
use case. Recommendations, forecasts, more agents and every asset class are
not required. Two contrasting personas are expressly acceptable (p.8).

## Six weighted criteria

- [x] **20% — Quality, relevance and innovation of the solution.** Hidden ETF
  exposure, explicit rule confirmation and preserved before/after challenges
  solve a concrete problem. Robert's live challenge demonstrates the value.
  Originality is the contestable evidence workflow; a 3D chart alone is not
  innovation. Rule compliance does not establish overall financial suitability.
- [ ] **20% — Agentic intelligence and explainability: strong, incomplete.**
  Live investigations used model-selected tools; Mateo's interpreter clarified
  “oil.” Deterministic checks and templated explanations prevent invented
  numbers. However, the evidence drawer explicitly lacks source titles,
  publishers, retrieval dates and links. Source IDs alone are insufficient for
  convenient user verification. Demonstrate what the agent contributes beyond
  the deterministic fallback, using observable actions rather than reasoning.
- [ ] **20% — Data analysis and processing capacity: strong, bounded.**
  Look-through exposure, missing-data intervals, adjusted returns, backward FX
  matching and the dated 2022 replay are substantive. Provenance and processing
  are documented in [data-sources.md](data-sources.md). Coverage remains narrow:
  two funds, no ESGV/QQQ holdings, no SPY constituent sectors, three controversy
  records. Do not market this as comprehensive ESG analysis. Reproduction still
  requires gitignored inputs; redistribution terms remain unresolved.
- [x] **10% — User experience UX/UI: core demonstrated.** Three-step journey,
  explicit confirmation, per-rule results and revision comparison worked live.
  Mateo's result fit 390px without horizontal overflow. Remaining weaknesses:
  long evidence/results sections, technical source IDs, and “0 unknown” counts
  that can be mistaken for complete data despite wide uncertainty intervals.
  This was a smoke check, not a complete accessibility/usability study.
- [x] **15% — Quality of AWS integration: happy path demonstrated.** The Amplify
  site called API Gateway; three investigations succeeded in `MODEL` mode with
  3/2/2 tool rounds and the interpreter returned HTTP 200. SAM defines Lambda,
  S3, IAM and bounded execution. This does not verify deployed IAM, failure
  recovery, cost, load behaviour or deployment of the exact audited commit.
- [ ] **15% — Presentation, business value and marketing: not submission-ready.**
  Clear promise and a strong Robert story; no user research or measured benefit
  found. README, architecture, one-pager and demo script retain obsolete
  deployment/status claims. They currently contradict the working site.

## Required deliverables and boundaries

- [x] Demonstrable prototype and accessible repository with setup instructions.
- [x] Fictional portfolios, user-confirmed thresholds, no real trades/advice;
  historical replay is labelled as history, not a future-loss guarantee.
- [x] Facts, assumptions and missing coverage are distinguished; model text
  cannot replace financial verdicts. See [BUILD_BRIEF.md](BUILD_BRIEF.md).
- [ ] Finish and verify the approximately five-minute video. A script exists;
  no finished recording or submission link was found in the repository.
- [ ] Update concise technical documentation to the tested deployment and
  current validation. Existing documents cover the subjects but are stale.
- [ ] Export and verify an **at-most-one-page** one-pager. The current Markdown
  is approximately 741 words; existence does not prove one-page compliance.
- [ ] Verify submission deadline/platform and preserve demo/data access before
  the documented workshop-account deletion on 2026-11-16.

## Live evidence and next priorities

Authenticated Chromium check of [the hosted site](https://main.dwtdk87nismj6.amplifyapp.com/#/persona),
2026-11-15 around 22:59–23:05 UTC, without fixtures:
Robert NVDA 25% → exposure 26.23–26.28%, replay loss 17.78%, both FAIL;
cap 10%→30% → exposure unchanged, issuer PASS, loss still FAIL, old report kept.
Mateo → “oil” clarification → SPY 15% → both exclusions FAIL, existing breaches
separated from purchase effects; Energy approximately 3.35–33.41%, controversy
1.58–65.00%. No uncaught page errors observed. Amira's full flow was not tested.

Prior audit: 2,679 Python and 532 frontend tests passed; 838 skipped and two
expected failures. Typecheck/lint/build passed. These are not live-cloud tests.

**Priority:** (1) resolve source IDs into usable citations; (2) refresh the
submission documents and record the working live demo; (3) record deployed
commit/snapshot and a failure-path check; (4) provide permitted reproduction
inputs and finish submission logistics. Prefer these to expanding features.
