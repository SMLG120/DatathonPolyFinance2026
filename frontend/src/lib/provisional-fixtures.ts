/**
 * PROVISIONAL FIXTURE DATA — PHASE 1 ONLY. DELETE IN PHASE 2.
 *
 * `contracts/fixtures/api/*.json` and `contracts/scenarios/*.json` did not
 * exist when the interface shell was built. This file stands in for them so
 * all six stages can be walked and tested.
 *
 * WHAT IS REAL HERE: the persona portfolios, objective wording, scenario rule
 * values and demonstration purchases, which are copied from
 * `docs/LEAD_DECISIONS.md` D7 (themselves fictional).
 *
 * WHAT IS NOT REAL: every measured number — fund constituent weights, sector
 * weights, registry coverage, 2022 returns and drawdowns. They are PLACEHOLDERS
 * chosen only to be internally consistent and to exercise PASS, FAIL, UNKNOWN,
 * ranges and missing coverage. They were not produced by the engine and do not
 * come from any source. The interface shows "Test data — fixtures" whenever
 * they are on screen, and every source record below says so.
 *
 * Nothing imports this file except `src/lib/fixtures.ts`.
 */
import type {
  ClarificationRequest,
  ExposureBreakdown,
  FundCoverage,
  FundPath,
  Instrument,
  InterpretResponse,
  PersonaId,
  PortfolioResponse,
  Rule,
  RuleType,
  SourceRecord,
  UnsupportedRequest,
} from "@/lib/contracts";

export const FIXTURE_VALUATION_DATE = "2026-11-12";
export const FIXTURE_CALCULATION_VERSION = "fixture-placeholder-0";
/** Fixed so the recorded timeline reads the same on every run. */
export const FIXTURE_CLOCK_START = "2026-11-14T15:02:00Z";

const PLACEHOLDER_LIMITATION =
  "Placeholder written for interface testing. Not sourced data and not engine output.";

/** Removes binary floating-point noise from sums of placeholder values. */
function tidy(value: number): number {
  return Math.round(value * 1e10) / 1e10;
}

function path(
  fundId: string,
  fundWeight: number,
  subjectWeightInFund: number | null,
  coverage: number,
  holdingsDate: string | null,
): FundPath {
  return {
    fund_id: fundId,
    fund_weight: fundWeight,
    subject_weight_in_fund: subjectWeightInFund,
    known_exposure: subjectWeightInFund === null ? 0 : tidy(fundWeight * subjectWeightInFund),
    coverage,
    possible_extra: tidy(fundWeight * (1 - coverage)),
    holdings_date: holdingsDate,
  };
}

function breakdown(direct: number, paths: FundPath[]): ExposureBreakdown {
  const indirectKnown = tidy(paths.reduce((sum, p) => sum + p.known_exposure, 0));
  const possibleExtra = tidy(paths.reduce((sum, p) => sum + p.possible_extra, 0));
  const lower = tidy(direct + indirectKnown);
  return {
    direct,
    indirect_known: indirectKnown,
    possible_extra: possibleExtra,
    lower,
    upper: tidy(lower + possibleExtra),
    paths,
  };
}

/** A measured range that does not come from fund look-through (for example registry coverage). */
function interval(lower: number, upper: number): ExposureBreakdown {
  return { direct: lower, indirect_known: 0, possible_extra: tidy(upper - lower), lower, upper, paths: [] };
}

const HOLDINGS_DATE = "2026-10-31";

const INSTRUMENTS = {
  XBB: { instrument_id: "XBB.TO", name: "iShares Core Canadian Universe Bond Index ETF", asset_type: "BOND_FUND", currency: "CAD" },
  SPY: { instrument_id: "SPY", name: "SPDR S&P 500 ETF Trust", asset_type: "EQUITY_FUND", currency: "USD" },
  XIU: { instrument_id: "XIU.TO", name: "iShares S&P/TSX 60 Index ETF", asset_type: "EQUITY_FUND", currency: "CAD" },
  ESGV: { instrument_id: "ESGV", name: "Vanguard ESG U.S. Stock ETF", asset_type: "EQUITY_FUND", currency: "USD" },
  RY: { instrument_id: "RY.TO", name: "Royal Bank of Canada", asset_type: "EQUITY", currency: "CAD" },
  JNJ: { instrument_id: "JNJ", name: "Johnson & Johnson", asset_type: "EQUITY", currency: "USD" },
  NVDA: { instrument_id: "NVDA", name: "NVIDIA Corporation", asset_type: "EQUITY", currency: "USD" },
  MSFT: { instrument_id: "MSFT", name: "Microsoft Corporation", asset_type: "EQUITY", currency: "USD" },
  CNR: { instrument_id: "CNR.TO", name: "Canadian National Railway Company", asset_type: "EQUITY", currency: "CAD" },
  FTS: { instrument_id: "FTS.TO", name: "Fortis Inc.", asset_type: "EQUITY", currency: "CAD" },
} as const satisfies Record<string, Instrument>;

const PURCHASABLE: Instrument[] = [
  INSTRUMENTS.NVDA,
  INSTRUMENTS.SPY,
  INSTRUMENTS.MSFT,
  INSTRUMENTS.RY,
  INSTRUMENTS.JNJ,
  INSTRUMENTS.XIU,
];

export const FIXTURE_SOURCES: SourceRecord[] = [
  {
    source_id: "fx-src-scenario",
    publisher: "Before You Buy team",
    title: "Fictional persona portfolios and scenario rules (LEAD_DECISIONS D7)",
    url: null,
    relevant_date: FIXTURE_VALUATION_DATE,
    retrieval_date: null,
    sha256: null,
    processing: "Copied from the project's frozen scenario definition.",
    terms: "Invented for this simulation.",
    known_limitations: ["Fictional. The official case gives the personas no portfolios and no numbers."],
  },
  {
    source_id: "fx-src-holdings",
    publisher: "Placeholder — stands in for the fund issuers' holdings files",
    title: "Fund holdings snapshot (placeholder values)",
    url: null,
    relevant_date: HOLDINGS_DATE,
    retrieval_date: null,
    sha256: null,
    processing: "None. Constituent and sector weights were typed in by hand as placeholders.",
    terms: "Not applicable.",
    known_limitations: [PLACEHOLDER_LIMITATION],
  },
  {
    source_id: "fx-src-prices",
    publisher: "Placeholder — stands in for the adjusted price and FX history",
    title: "2022 adjusted returns in CAD (placeholder values)",
    url: null,
    relevant_date: "2022-12-30",
    retrieval_date: null,
    sha256: null,
    processing: "None. Returns were typed in by hand as placeholders.",
    terms: "Not applicable.",
    known_limitations: [PLACEHOLDER_LIMITATION],
  },
  {
    source_id: "fx-src-registry",
    publisher: "Placeholder — stands in for the controversy registry",
    title: "Controversy registry coverage (placeholder values)",
    url: null,
    relevant_date: null,
    retrieval_date: null,
    sha256: null,
    processing: "None.",
    terms: "Not applicable.",
    known_limitations: [PLACEHOLDER_LIMITATION, "Absence from a registry is unknown, not proof of no controversy."],
  },
];

/** What a rule type measures for one persona, before and after the recorded purchase. */
export interface FixtureRuleMeasure {
  starting: { label: string; breakdown: ExposureBreakdown };
  proposed: { label: string; breakdown: ExposureBreakdown };
  /** The exposure drawn in the chart, when it differs from what the rule measured. */
  chart: { subject_label: string; starting: ExposureBreakdown; proposed: ExposureBreakdown } | null;
  source_ids: string[];
  assumptions: string[];
  calculation_path: string[];
}

export interface FixtureScenarioReplay {
  scenario_id: string;
  scenario_label: string;
  period_start: string;
  period_end: string;
  starting: { scenario_terminal_return: number; scenario_max_drawdown: number };
  proposed: { scenario_terminal_return: number; scenario_max_drawdown: number };
  /** D6: terminal return is linear in the target weight; this is the slope. */
  instrument_return: number;
  assumptions: string[];
}

export interface FixtureScenario {
  persona_id: PersonaId;
  portfolio_response: PortfolioResponse;
  interpretation: InterpretResponse;
  /** Proposed rules released by answering a clarification, keyed by option id. */
  clarification_outcomes: Record<string, { proposed_rules: Rule[]; unsupported: UnsupportedRequest[] }>;
  measures: Partial<Record<RuleType, FixtureRuleMeasure>>;
  replay: FixtureScenarioReplay | null;
  funds: { starting: FundCoverage[]; proposed: FundCoverage[] };
  coverage_notes: string[];
  /** Qualitative context per objective id. `{value}` is replaced with the proposed exposure. */
  goal_context: { objective_id: string; text: string }[];
}

// ---------------------------------------------------------------------------
// Robert — primary demonstration
// ---------------------------------------------------------------------------

const ROBERT_OBJECTIVE = "Preserve my capital while keeping some growth potential over the next 3 to 5 years.";

const robert: FixtureScenario = {
  persona_id: "robert",
  portfolio_response: {
    portfolio: {
      portfolio_id: "fx-portfolio-robert",
      persona_id: "robert",
      valuation_date: FIXTURE_VALUATION_DATE,
      reporting_currency: "CAD",
      cash_weight: 0.3,
      positions: [
        { ...INSTRUMENTS.XBB, weight: 0.3 },
        { ...INSTRUMENTS.SPY, weight: 0.2 },
        { ...INSTRUMENTS.XIU, weight: 0.1 },
        { ...INSTRUMENTS.RY, weight: 0.05 },
        { ...INSTRUMENTS.JNJ, weight: 0.05 },
      ],
      is_fictional: true,
    },
    scenario_objective_text: ROBERT_OBJECTIVE,
    scenario_purchase: { instrument_id: "NVDA", target_direct_weight: 0.25 },
    purchasable_instruments: PURCHASABLE,
  },
  interpretation: {
    objectives: [{ objective_id: "obj-robert-1", original_words: ROBERT_OBJECTIVE, origin: "FICTIONAL_SCENARIO" }],
    proposed_rules: [
      {
        rule_id: "rule-robert-issuer-cap",
        rule_type: "max_issuer_exposure",
        status: "PROPOSED",
        origin: "FICTIONAL_SCENARIO",
        original_words: "I do not want any single company to be more than 10% of my portfolio.",
        scope_description:
          "Total equity exposure to any single company: shares held directly plus the company's share of each equity fund you hold, with share classes combined. Bond, commodity and crypto instruments are outside this rule.",
        objective_id: "obj-robert-1",
        supersedes_rule_id: null,
        issuer_scope: "any",
        max_fraction: 0.1,
      },
      {
        rule_id: "rule-robert-loss-budget",
        rule_type: "scenario_loss_budget",
        status: "PROPOSED",
        origin: "FICTIONAL_SCENARIO",
        original_words: "If this allocation had been held through 2022, I would not accept it losing more than 10%.",
        scope_description:
          "Loss of the allocation from the last price of 2021 to the last price of 2022, in CAD: bought once and held, no rebalancing, cash earning 0%. This is the loss at the end of the period, not the deepest fall during it.",
        objective_id: "obj-robert-1",
        supersedes_rule_id: null,
        scenario_id: "replay_2022",
        max_loss_fraction: 0.1,
      },
    ],
    clarifications: [],
    unsupported: [],
    notes: [],
  },
  clarification_outcomes: {},
  measures: {
    max_issuer_exposure: {
      starting: {
        label: "Largest single-company exposure: Royal Bank of Canada",
        breakdown: breakdown(0.05, [path("XIU.TO", 0.1, 0.062, 1, HOLDINGS_DATE)]),
      },
      proposed: {
        label: "Largest single-company exposure: NVIDIA Corporation",
        breakdown: breakdown(0.25, [path("SPY", 0.2, 0.075, 1, HOLDINGS_DATE)]),
      },
      chart: {
        subject_label: "NVIDIA Corporation",
        starting: breakdown(0, [path("SPY", 0.2, 0.075, 1, HOLDINGS_DATE)]),
        proposed: breakdown(0.25, [path("SPY", 0.2, 0.075, 1, HOLDINGS_DATE)]),
      },
      source_ids: ["fx-src-scenario", "fx-src-holdings"],
      assumptions: ["Share classes of one company are combined.", "Bond fund XBB.TO is outside the scope of this rule."],
      calculation_path: [
        "direct weight of the company",
        "plus, for each equity fund: fund weight x company weight in that fund",
        "possible extra for each fund: fund weight x (1 - holdings coverage)",
      ],
    },
  },
  replay: {
    scenario_id: "replay_2022",
    scenario_label: "2022 replay",
    period_start: "2021-12-31",
    period_end: "2022-12-30",
    starting: { scenario_terminal_return: -0.0603, scenario_max_drawdown: -0.105 },
    proposed: { scenario_terminal_return: -0.1778, scenario_max_drawdown: -0.232 },
    instrument_return: -0.47,
    assumptions: [
      "Weights are applied once at the last price of 2021 and then held: no rebalancing.",
      "Cash earns 0%: no interest is credited.",
      "USD prices are converted to CAD with the latest Bank of Canada rate on or before each date.",
      "Each instrument uses its own adjusted price series; a fund uses the fund's series, not its holdings.",
      "Fees and taxes are excluded.",
    ],
  },
  funds: {
    starting: [
      fund("SPY", INSTRUMENTS.SPY.name, 0.2, 1, "COVERED", "Holdings file covers the whole fund."),
      fund("XIU.TO", INSTRUMENTS.XIU.name, 0.1, 1, "COVERED", "Holdings file covers the whole fund."),
      fund("XBB.TO", INSTRUMENTS.XBB.name, 0.3, null, "NOT_APPLICABLE", "Bond fund: outside the scope of the company-exposure rule."),
    ],
    proposed: [
      fund("SPY", INSTRUMENTS.SPY.name, 0.2, 1, "COVERED", "Holdings file covers the whole fund."),
      fund("XIU.TO", INSTRUMENTS.XIU.name, 0.1, 1, "COVERED", "Holdings file covers the whole fund."),
      fund("XBB.TO", INSTRUMENTS.XBB.name, 0.3, null, "NOT_APPLICABLE", "Bond fund: outside the scope of the company-exposure rule."),
    ],
  },
  coverage_notes: ["Fund holdings are a dated snapshot. They describe the funds on the holdings date, not their past composition."],
  goal_context: [
    {
      objective_id: "obj-robert-1",
      text: "After this purchase one company would be {value} of the portfolio. A position that concentrated can sit uneasily with an objective of preserving capital. This is context for you to weigh. It is not a calculated contradiction, and no rule or number follows from the objective by itself.",
    },
  ],
};

// ---------------------------------------------------------------------------
// Mateo — second demonstration
// ---------------------------------------------------------------------------

const MATEO_OBJECTIVE =
  "Balanced growth over 8 to 12 years; ESG matters to me; I want to avoid oil and companies involved in significant controversies.";

const MATEO_OIL_CLARIFICATION: ClarificationRequest = {
  clarification_id: "clar-mateo-oil",
  original_words: "I want to avoid oil",
  question: "“Oil” can be read in several ways. Which definition should a rule use?",
  options: [
    {
      option_id: "energy-sector",
      label: "The Energy sector, as reported in fund holdings files",
      description:
        "Uses the sector label each fund publishes for its holdings, and the starter-universe label for shares held directly. Broader than oil: it also includes gas and energy services.",
      supported: true,
    },
    {
      option_id: "named-issuers",
      label: "A list of companies that you name",
      description: "Only the companies you list are counted.",
      supported: true,
    },
    {
      option_id: "oil-producers",
      label: "Companies that produce oil",
      description: "Not available: we hold no sourced classification of oil producers.",
      supported: false,
    },
    {
      option_id: "fossil-fuels",
      label: "All fossil fuels",
      description: "Not available: we hold no sourced classification of fossil-fuel involvement.",
      supported: false,
    },
  ],
};

const MATEO_ENERGY_STARTING = breakdown(0, [
  path("XIU.TO", 0.2, 0.17, 1, HOLDINGS_DATE),
  path("ESGV", 0.15, null, 0, null),
]);
const MATEO_ENERGY_PROPOSED = breakdown(0, [
  path("XIU.TO", 0.2, 0.17, 1, HOLDINGS_DATE),
  path("SPY", 0.15, 0.033, 1, HOLDINGS_DATE),
  path("ESGV", 0.15, null, 0, null),
]);

const mateo: FixtureScenario = {
  persona_id: "mateo",
  portfolio_response: {
    portfolio: {
      portfolio_id: "fx-portfolio-mateo",
      persona_id: "mateo",
      valuation_date: FIXTURE_VALUATION_DATE,
      reporting_currency: "CAD",
      cash_weight: 0.25,
      positions: [
        { ...INSTRUMENTS.XBB, weight: 0.25 },
        { ...INSTRUMENTS.XIU, weight: 0.2 },
        { ...INSTRUMENTS.ESGV, weight: 0.15 },
        { ...INSTRUMENTS.MSFT, weight: 0.05 },
        { ...INSTRUMENTS.CNR, weight: 0.05 },
        { ...INSTRUMENTS.FTS, weight: 0.05 },
      ],
      is_fictional: true,
    },
    scenario_objective_text: MATEO_OBJECTIVE,
    scenario_purchase: { instrument_id: "SPY", target_direct_weight: 0.15 },
    purchasable_instruments: PURCHASABLE,
  },
  interpretation: {
    objectives: [
      { objective_id: "obj-mateo-1", original_words: "Balanced growth over 8 to 12 years", origin: "FICTIONAL_SCENARIO" },
      { objective_id: "obj-mateo-2", original_words: "ESG matters to me", origin: "FICTIONAL_SCENARIO" },
    ],
    proposed_rules: [
      {
        rule_id: "rule-mateo-controversy",
        rule_type: "controversy_exclusion",
        status: "PROPOSED",
        origin: "SYSTEM_PROPOSED",
        original_words: "I want to avoid … companies involved in significant controversies.",
        scope_description:
          "Total exposure to companies that have a matching record in the controversy registry, held directly or through funds. A company that is missing from the registry is reported as unknown, never as a pass.",
        objective_id: "obj-mateo-2",
        supersedes_rule_id: null,
        criteria_text: "Any record in the controversy registry",
        max_fraction: null,
      },
    ],
    clarifications: [MATEO_OIL_CLARIFICATION],
    unsupported: [],
    notes: [],
  },
  clarification_outcomes: {
    "energy-sector": {
      proposed_rules: [
        {
          rule_id: "rule-mateo-energy",
          rule_type: "exclusion",
          status: "PROPOSED",
          origin: "SYSTEM_PROPOSED",
          original_words: "I want to avoid oil",
          scope_description:
            "Total exposure to holdings labelled Energy: the sector each fund reports in its holdings file, and the starter-universe label for shares held directly. A fund with no holdings file counts as possibly Energy in full.",
          objective_id: "obj-mateo-2",
          supersedes_rule_id: null,
          definition: { kind: "fund_reported_sector", sector: "Energy" },
          max_fraction: null,
        },
      ],
      unsupported: [],
    },
    "named-issuers": {
      proposed_rules: [],
      unsupported: [
        {
          original_words: "I want to avoid oil",
          reason:
            "Test data holds no recorded list of named companies. Choose the Energy sector definition to continue the recorded scenario; the live service lets you name companies.",
        },
      ],
    },
  },
  measures: {
    exclusion: {
      starting: { label: "Holdings labelled Energy", breakdown: MATEO_ENERGY_STARTING },
      proposed: { label: "Holdings labelled Energy", breakdown: MATEO_ENERGY_PROPOSED },
      chart: null,
      source_ids: ["fx-src-scenario", "fx-src-holdings"],
      assumptions: [
        "ESGV has no holdings file, so all of it is counted as possibly Energy.",
        "Reported holdings are never rescaled to 100%.",
      ],
      calculation_path: [
        "direct weight of holdings labelled Energy",
        "plus, for each fund: fund weight x Energy weight reported in that fund",
        "possible extra for each fund: fund weight x (1 - holdings coverage)",
      ],
    },
    controversy_exclusion: {
      starting: {
        label: "Companies with a registry record",
        breakdown: interval(0, 0.5),
      },
      proposed: {
        label: "Companies with a registry record",
        breakdown: interval(0, 0.65),
      },
      chart: null,
      source_ids: ["fx-src-registry"],
      assumptions: ["A company missing from the registry is unknown, not clear."],
      calculation_path: [
        "exposure to companies with a matching registry record",
        "possible extra: exposure to companies the registry does not cover",
      ],
    },
  },
  replay: null,
  funds: {
    starting: [
      fund("XIU.TO", INSTRUMENTS.XIU.name, 0.2, 1, "COVERED", "Holdings file covers the whole fund."),
      fund("ESGV", INSTRUMENTS.ESGV.name, 0.15, 0, "MISSING", "No holdings file: its contents are unknown, not zero."),
      fund("XBB.TO", INSTRUMENTS.XBB.name, 0.25, null, "NOT_APPLICABLE", "Bond fund: outside the scope of the look-through rules."),
    ],
    proposed: [
      fund("XIU.TO", INSTRUMENTS.XIU.name, 0.2, 1, "COVERED", "Holdings file covers the whole fund."),
      fund("SPY", INSTRUMENTS.SPY.name, 0.15, 1, "COVERED", "Holdings file covers the whole fund."),
      fund("ESGV", INSTRUMENTS.ESGV.name, 0.15, 0, "MISSING", "No holdings file: its contents are unknown, not zero."),
      fund("XBB.TO", INSTRUMENTS.XBB.name, 0.25, null, "NOT_APPLICABLE", "Bond fund: outside the scope of the look-through rules."),
    ],
  },
  coverage_notes: [
    "ESGV holdings were not acquired, so its share of the portfolio is treated as an unknown range.",
    "A sector label is how a fund classifies a holding. It is not proof about a company's conduct.",
  ],
  goal_context: [
    {
      objective_id: "obj-mateo-2",
      text: "You said ESG matters to you. The checks here use fund sector labels and registry records, which are not evidence about a company's conduct, and ESGV's holdings are unknown. This is context for you to weigh, not a verdict on the objective.",
    },
  ],
};

function fund(
  fundId: string,
  fundName: string,
  portfolioWeight: number,
  coverage: number | null,
  status: FundCoverage["status"],
  note: string,
): FundCoverage {
  return {
    fund_id: fundId,
    fund_name: fundName,
    portfolio_weight: portfolioWeight,
    coverage,
    status,
    holdings_date: coverage ? HOLDINGS_DATE : null,
    source_id: coverage ? "fx-src-holdings" : null,
    note,
  };
}

export const FIXTURE_SCENARIOS: Partial<Record<PersonaId, FixtureScenario>> = { robert, mateo };
