# Requirements: Before You Buy

Three groups, kept apart on purpose: (1) what the datathon officially asks, (2) what we chose to build,
(3) what we assume and what is still open. Only group 1 has official force.

Citations: **Case p.N** = official case PDF, page N. **Deck s.N** = participant presentation (French), slide N.
**Workshop s.N** = investor workshop deck, slide N. **Starter README** = `data/starter/STARTER_README.md`.

Text we could not read: the asset-examples table (Case p.10), the data-families table (p.11) and the
evaluation grid (p.19) are images and gave no text; the running text of those pages was read. The weights in
1.3 therefore come from Deck s.10.

## 1. Official requirements and evaluation criteria

### 1.1 Eligibility and boundaries

| # | Requirement | Source |
|---|---|---|
| O1 | AWS is an eligibility condition: "AWS doit contribuer réellement et de manière démontrable au fonctionnement de la solution. Absence d'intégration effective = projet non admissible à l'évaluation finale." | Deck s.7 |
| O2 | Simulation only: "no real transactions are permitted"; prototypes "must not execute real transactions or present themselves as providing personalized financial advice". | Case p.10, p.17; Deck s.11 |
| O3 | No real client accounts or confidential banking information; portfolios and profiles may be fictional. | Case p.14; Deck s.11 |
| O4 | "Teams must distinguish facts, assumptions, and fictional scenarios, and communicate material uncertainties clearly." When data does not support a firm conclusion, the solution must say so. | Case p.17; Deck s.11 |
| O5 | No forecast: "The challenge does not ask teams to predict future returns from past performance." | Case p.18 |
| O6 | Tools, models and services are free "unless the official technical rules specify otherwise"; no asset, architecture or number of agents is mandatory. | Case p.10, p.15, p.17 |

### 1.2 The four deliverables

| # | Deliverable | Source |
|---|---|---|
| O7 | Prototype and source code: a complete, demonstrable use case with "an accessible explanation of the result, including sources, assumptions, key factors, and limitations"; repository and README (dependencies, data sources, configuration, reproduction). | Case p.15; Deck s.9 |
| O8 | Video, "approximately five minutes as a guide", end to end: problem, role of the agents, data and tools, result, explanation. | Case p.15; Deck s.9 |
| O9 | Technical documentation: logic, agent roles, controls; methods and why; sources, assets, processing, assumptions; the explainability mechanism with an example linking a conclusion to data or observable execution traces; validation, limitations, improvements. | Case p.15; Deck s.9 |
| O10 | One-pager, "at most one page": problem, agentic approach, originality, data sources, explainability, user benefits. | Case p.16; Deck s.9 |

"Deadlines, submission platforms, formats, and any infrastructure requirements will be confirmed in the
official Datathon logistics" (Case p.16). See Q1 and Q4.

### 1.3 Evaluation weights (Deck s.10; sum 100%)

| Solution | Agentic | Data | UX/UI | AWS | Pitch |
|---|---|---|---|---|---|
| 20% | 20% | 20% | 10% | 15% | 15% |
| Relevance, innovation, creativity, prototype | Architecture and explainability | Rigour, validation, visualization | Intuition, ergonomics, clarity | Quality of the integration | Presentation, business, marketing |

Case p.19 confirms six criteria with weightings and reserves the full grid for the jury. Case p.17:
"explanations faithful to data and observable actions matter more than complexity or historical asset
performance".

### 1.4 What each persona tests

| Persona | Profile | What it tests | Source |
|---|---|---|---|
| Amira | 26, risk High, 15 years or more | "How much risk will the system accept? It should account for an aggressive profile without interpreting 'high risk' as 'anything goes,' while respecting Amira's desire for diversification." | Case p.5; Deck s.4 |
| Mateo | 41, Moderate, 8-12 years | "Can the system incorporate more than return and risk? It should consider financial factors and personal preferences, rather than selecting solely for potential return." | Case p.6; Deck s.4 |
| Robert | 59, Low to moderate, 3-5 years | "Can the system challenge a request that conflicts with the investor's profile? It should identify the tension between Robert's immediate interest and his objectives, explain the risks, and avoid simply agreeing." | Case p.7; Deck s.4 |

Deck s.4 advises showing at least two contrasting situations.

### 1.5 Data duties

| # | Requirement | Source |
|---|---|---|
| O11 | The starter dataset is optional. "Sources, dates, processing, and terms of use must be documented." | Case p.10 |
| O12 | Traceability (source, date, currency, processing). Time consistency ("do not use information in a simulation before it was available"). Comparability (dividends, splits, selection bias, missing data, CAD/USD). Licences ("respect access, retention, and redistribution terms"). Privacy. | Case p.14 |
| O13 | Document sources, transformations, missing data and assumptions: "Without source + date + definition + limitations, a conclusion can look precise without being reliable." | Workshop s.11 |
| O14 | Limits of the starter data to carry into our documentation: listing-currency prices, no forward fill, no FX rows on Canadian holidays, `adj_close` changes on re-download, crypto rows are UTC days, survivorship bias, no ESG scores, news or fundamentals. | Starter README |

### 1.6 Explainability

| # | Requirement | Source |
|---|---|---|
| O15 | "Explanations should be concise, verifiable, and faithful to sources and observable actions, without inventing justifications or exposing detailed internal model reasoning." | Case p.17; Deck s.11 |
| O16 | Self-explaining: "connect results to sources, assumptions, observable steps, and limitations so users can understand and verify what supports a conclusion". "Explainability is expected; the component and architecture remain open to teams." | Case p.8, p.9 |
| O17 | Encouraged, not required: a governance check that flags "conflicts or missing information" and makes controls visible. A credible explanation answers: what data, why this choice, what limitations, what would change the answer. | Case p.9; Workshop s.12 |

## 2. Our product choices (not official requirements)

Decided in `docs/BUILD_BRIEF.md` and `docs/LEAD_DECISIONS.md` (D1 to D9), made precise in `contracts/`.
In brackets: the official items a choice answers.

- **C1 Product.** A pre-trade check on a fictional portfolio: the user confirms rules, proposes one
  cash-funded purchase and gets one verdict per rule with its evidence. No trade, no advice, no
  recommendation of what to buy [O2, O3, O5].
- **C2 Verdicts are computed, not generated.** A deterministic engine returns PASS, FAIL or UNKNOWN per rule.
  There is no overall "compliant" flag [O4, O15].
- **C3 Five rule types** (D3): single-company maximum and minimum, exclusion (named companies or a
  fund-reported sector label), controversy exclusion, 2022 loss budget. Anything else is reported as unsupported.
- **C4 No invented numbers.** A rule is evaluated only after the user confirmed its threshold [O4].
- **C5 Unknown is a result** (D4). Missing or partial fund holdings give a lower and an upper bound; a limit
  between them is UNKNOWN. A missing sector label or a company absent from the controversy registry is
  "not assessed", never "clean" [O4, O13].
- **C6 Purchase model** (D5): final direct weight of one instrument, funded from cash, no selling, no fees or
  taxes. Lack of cash is reported apart from the rule results.
- **C7 History is replayed, not forecast** (D6): calendar 2022 applied to the assumed allocation; no price
  older than 7 days, no proxy [O5, O12].
- **C8 Policies are versioned and immutable.** A changed rule creates a new version; earlier reports stay
  unchanged; a disputed fact is stored as unverified and alters no calculation.
- **C9 Agents** (BUILD_BRIEF section 6): Bedrock models interpret the user's words and narrate; they never
  produce a verdict. Displayed steps are real tool events; model sentences are kept only if they match
  evidence records; no model reasoning is displayed [O15 to O17].
- **C10 AWS** (D1, BUILD_BRIEF section 7): serverless backend in `us-east-1`, runtime model
  `us.anthropic.claude-sonnet-5-5` on Amazon Bedrock, asynchronous investigations [O1].
- **C11 Scenarios** (D7): Robert asks for NVDA at 25%; Mateo for SPY at 15% under an Energy-label exclusion
  and a controversy exclusion; Amira's ambiguous wording is answered by a question. Portfolios, thresholds
  and Mateo's "avoid oil" are our fictional wording; the case gives only the persona facts.
- **C12 Units and code** (D2): portfolio fractions (10% = 0.10), tolerance 1e-9; deployed code is Python
  standard library plus `boto3`.

## 3. Assumptions and open questions

Assumptions:

- **A1** The weights of Deck s.10 are the simplified grid of Case p.19, whose image we could not read.
- **A2** A fund's sector label is used as the issuer file reports it; labels are not harmonized across
  sources, and a sector label is not evidence of a controversy.
- **A3** Every number in `contracts/fixtures/` is synthetic and labelled so; none may be shown as real
  holdings, prices or research.

Open questions:

- **Q1** Submission deadline and time reserved for final testing and recording: unresolved.
- **Q2** AWS account expiry hour: the organizer cheat sheet says end of day Monday 2026-11-16, exact time
  given with the access code, which we do not have.
- **Q3** CIRO: partially verified; a CIRO news release dated 2026-03-12 announces guidance that "broadens the
  range of decision-making supports that OEO dealers can offer to clients without violating the rule that
  prohibits them from making recommendations"; it is guidance, with a safeguards condition, and does not
  mention pre-trade checks; the guidance text itself was not read.
- **Q4** Submission platform and file formats: deferred by Case p.16 to the official logistics; not in the
  documents we hold.
- **Q5** "Official technical rules" (Case p.15): we know of none beyond the AWS condition (O1); unconfirmed.
- **Q6** build_dataset.py: not located in the current checkout; user reports it exists in alphaforge_starter.
  Case p.12 and the Starter README name it as the script that rebuilds the starter data.
