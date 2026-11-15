import type { Instrument, Portfolio, PurchaseRequest } from "@/lib/contracts";
import { EPS, formatFraction } from "@/lib/format";

/**
 * Read-only helpers over a portfolio, and the arithmetic of the purchase
 * request itself (BUILD_BRIEF §2). Nothing here produces a verdict: rule
 * results always come from the service.
 */

/** How every purchase in this simulation is funded (BUILD_BRIEF §2). Stated wherever a purchase is shown. */
export const FUNDING_STATEMENT = "Funded from existing cash; all other positions unchanged; fees and taxes excluded.";

export interface PortfolioRow {
  key: string;
  /** Null for the cash row. */
  instrument_id: string | null;
  name: string;
  kind: string;
  weight: number;
}

const ASSET_TYPE_LABELS: Record<Instrument["asset_type"], string> = {
  EQUITY: "Share",
  EQUITY_FUND: "Equity fund",
  BOND_FUND: "Bond fund",
  COMMODITY: "Commodity",
  CRYPTO: "Crypto asset",
};

export function assetTypeLabel(assetType: Instrument["asset_type"]): string {
  return ASSET_TYPE_LABELS[assetType];
}

export function cashRowName(portfolio: Portfolio): string {
  return `Cash (${portfolio.reporting_currency})`;
}

export function directWeightOf(portfolio: Portfolio, instrumentId: string): number {
  return portfolio.positions.find((position) => position.instrument_id === instrumentId)?.weight ?? 0;
}

/** Positions in the order supplied, then cash. */
export function portfolioRows(portfolio: Portfolio): PortfolioRow[] {
  return [
    ...portfolio.positions.map((position) => ({
      key: position.instrument_id,
      instrument_id: position.instrument_id,
      name: position.name,
      kind: assetTypeLabel(position.asset_type),
      weight: position.weight,
    })),
    { key: "__cash__", instrument_id: null, name: cashRowName(portfolio), kind: "Cash", weight: portfolio.cash_weight },
  ];
}

export function totalWeight(portfolio: Portfolio): number {
  return portfolio.positions.reduce((sum, position) => sum + position.weight, portfolio.cash_weight);
}

export type PurchaseProblemCode =
  | "NO_INSTRUMENT"
  | "UNSUPPORTED_INSTRUMENT"
  | "NO_TARGET"
  | "NEGATIVE"
  | "ABOVE_ONE"
  | "BELOW_CURRENT";

export interface PurchaseProblem {
  code: PurchaseProblemCode;
  /** Which form field the message belongs to. */
  field: "instrument" | "target";
  message: string;
}

export interface BeforeAfterRow {
  key: string;
  instrument_id: string | null;
  name: string;
  before: number;
  after: number;
  /** True for the instrument being bought and for cash: the only rows a purchase changes. */
  changed: boolean;
}

export interface PurchasePreview {
  /** The request as it would be sent, or null while the form is invalid. */
  request: PurchaseRequest | null;
  /** A request the service would reject outright (LEAD_DECISIONS D5). */
  problem: PurchaseProblem | null;
  starting_direct: number;
  /** Target minus starting direct weight. */
  additional: number | null;
  cash_before: number;
  cash_after: number | null;
  /** D5: a feasibility result, reported apart from rule results. */
  insufficient_cash: boolean;
  rows: BeforeAfterRow[];
}

/**
 * Works out what a purchase request means for the portfolio:
 *
 *   cash after = starting cash - (target direct weight - starting direct weight)
 *
 * Funded from existing cash, every other position unchanged, fees and taxes
 * excluded. This is a restatement of the request for the user to check before
 * sending; the service recomputes it and its answer is the one that counts.
 */
export function previewPurchase(
  portfolio: Portfolio,
  instruments: Instrument[],
  instrumentId: string | null,
  target: number | null,
): PurchasePreview {
  const instrument = instrumentId === null ? undefined : instruments.find((i) => i.instrument_id === instrumentId);
  const startingDirect = instrumentId === null ? 0 : directWeightOf(portfolio, instrumentId);

  let problem: PurchaseProblem | null = null;
  if (instrumentId === null || instrumentId === "") {
    problem = { code: "NO_INSTRUMENT", field: "instrument", message: "Choose the instrument to buy." };
  } else if (!instrument) {
    problem = { code: "UNSUPPORTED_INSTRUMENT", field: "instrument", message: "This instrument is not supported." };
  } else if (target === null) {
    problem = { code: "NO_TARGET", field: "target", message: "Enter the final direct weight as a percentage, for example 25." };
  } else if (target < 0) {
    problem = { code: "NEGATIVE", field: "target", message: "The final weight cannot be negative. Shorting is not supported." };
  } else if (target > 1 + EPS) {
    problem = { code: "ABOVE_ONE", field: "target", message: "The final weight cannot be more than 100% of the portfolio. Leverage is not supported." };
  } else if (target < startingDirect - EPS) {
    problem = {
      code: "BELOW_CURRENT",
      field: "target",
      message: `The final weight cannot be below the ${formatFraction(startingDirect)} already held. This simulation only buys; it does not sell.`,
    };
  }

  const valid = problem === null && instrument !== undefined && target !== null;
  const additional = valid ? target - startingDirect : null;
  const cashAfter = additional === null ? null : portfolio.cash_weight - additional;

  const rows: BeforeAfterRow[] = portfolio.positions.map((position) => {
    const isTarget = valid && position.instrument_id === instrument.instrument_id;
    return {
      key: position.instrument_id,
      instrument_id: position.instrument_id,
      name: position.name,
      before: position.weight,
      after: isTarget ? target : position.weight,
      changed: isTarget,
    };
  });
  if (valid && !portfolio.positions.some((position) => position.instrument_id === instrument.instrument_id)) {
    rows.push({
      key: instrument.instrument_id,
      instrument_id: instrument.instrument_id,
      name: instrument.name,
      before: 0,
      after: target,
      changed: true,
    });
  }
  rows.push({
    key: "__cash__",
    instrument_id: null,
    name: cashRowName(portfolio),
    before: portfolio.cash_weight,
    after: cashAfter ?? portfolio.cash_weight,
    changed: valid,
  });

  return {
    request: valid ? { instrument_id: instrument.instrument_id, target_direct_weight: target } : null,
    problem,
    starting_direct: startingDirect,
    additional,
    cash_before: portfolio.cash_weight,
    cash_after: cashAfter,
    insufficient_cash: cashAfter !== null && cashAfter < -EPS,
    rows,
  };
}

/** "NVDA at a final direct weight of 25.0%" */
export function describePurchase(purchase: PurchaseRequest): string {
  return `${purchase.instrument_id} at a final direct weight of ${formatFraction(purchase.target_direct_weight)}`;
}
