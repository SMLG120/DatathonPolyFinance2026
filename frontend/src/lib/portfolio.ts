import type { AssetClass, Instrument, InstrumentId, Portfolio, PurchaseRequest } from "@/lib/contracts";
import { formatFraction } from "@/lib/format";
import { t, tf } from "@/lib/i18n";

/**
 * Read-only helpers over a portfolio and the purchase form.
 *
 * Nothing here calculates: cash after a purchase, the amount added, the
 * before/after figures and every rule result come from the service
 * (`CheckResult.feasibility`, `summary`, `max_compliant`). This module only
 * names things and reads what the user typed.
 */

/** How every purchase in this simulation is funded. Stated wherever a purchase is shown. */
export const FUNDING_STATEMENT = "Funded from existing cash; all other positions unchanged; fees and taxes excluded.";

export type InstrumentRegistry = Record<InstrumentId, Instrument>;

export interface PortfolioRow {
  key: string;
  /** Null for the cash row. */
  instrument_id: string | null;
  name: string;
  kind: string;
  weight: number;
}

const ASSET_CLASS_LABELS: Record<AssetClass, string> = {
  equity: "Share",
  etf_equity: "Equity fund",
  etf_bond: "Bond fund",
  etf_commodity: "Commodity fund",
  crypto: "Crypto asset",
};

export function assetClassLabel(assetClass: AssetClass): string {
  return t(ASSET_CLASS_LABELS[assetClass]);
}

/** The registry name of an instrument, or its id when the registry has no entry for it. */
export function instrumentName(instruments: InstrumentRegistry, instrumentId: InstrumentId): string {
  return instruments[instrumentId]?.name ?? instrumentId;
}

function instrumentKind(instruments: InstrumentRegistry, instrumentId: InstrumentId): string {
  const instrument = instruments[instrumentId];
  return instrument ? assetClassLabel(instrument.asset_class) : t("Not in the registry");
}

export function cashRowName(portfolio: Portfolio): string {
  return tf("Cash ({currency})", { currency: portfolio.base_currency });
}

/** The direct weight held now, or null when the instrument is not held. Read from the portfolio, never computed. */
export function heldWeight(portfolio: Portfolio, instrumentId: string): number | null {
  return portfolio.positions.find((position) => position.instrument_id === instrumentId)?.weight ?? null;
}

/** Positions in the order supplied, then cash. */
export function portfolioRows(portfolio: Portfolio, instruments: InstrumentRegistry): PortfolioRow[] {
  return [
    ...portfolio.positions.map((position) => ({
      key: position.instrument_id,
      instrument_id: position.instrument_id,
      name: instrumentName(instruments, position.instrument_id),
      kind: instrumentKind(instruments, position.instrument_id),
      weight: position.weight,
    })),
    { key: "__cash__", instrument_id: null, name: cashRowName(portfolio), kind: t("Cash"), weight: portfolio.cash_weight },
  ];
}

export type PurchaseProblemCode = "NO_INSTRUMENT" | "UNSUPPORTED_INSTRUMENT" | "NO_TARGET" | "OUT_OF_RANGE";

export interface PurchaseProblem {
  code: PurchaseProblemCode;
  /** Which form field the message belongs to. */
  field: "instrument" | "target";
  message: string;
}

export interface PurchaseInput {
  instrumentId: string | null;
  /** The FINAL direct weight, as a fraction, or null while the field is empty or unreadable. */
  target: number | null;
}

export interface PurchaseForm {
  /** The request as it would be sent, or null while the form cannot be sent. */
  request: PurchaseRequest | null;
  /** Why the form cannot be sent. Whether a sendable request can be executed is the service's answer. */
  problem: PurchaseProblem | null;
}

/**
 * Reads the purchase form into a request. Only the form is checked here (an
 * instrument is chosen, the weight is a share between 0% and 100%). Whether
 * the request can be executed (enough cash, not below the weight already
 * held) is decided by the service and shown from its answer.
 *
 * `scripted` are the scenario's own requests: when the form holds exactly one
 * of them, its sentence travels with the request as the original words.
 */
export function readPurchaseForm(purchasableIds: InstrumentId[], input: PurchaseInput, scripted: PurchaseRequest[] = []): PurchaseForm {
  const { instrumentId, target } = input;
  if (instrumentId === null || instrumentId === "") {
    return { request: null, problem: { code: "NO_INSTRUMENT", field: "instrument", message: t("Choose the instrument to buy.") } };
  }
  if (!purchasableIds.includes(instrumentId)) {
    return { request: null, problem: { code: "UNSUPPORTED_INSTRUMENT", field: "instrument", message: t("This instrument is not supported.") } };
  }
  if (target === null) {
    return { request: null, problem: { code: "NO_TARGET", field: "target", message: t("Enter the final direct weight as a percentage, for example 25.") } };
  }
  if (target < 0 || target > 1) {
    return {
      request: null,
      problem: { code: "OUT_OF_RANGE", field: "target", message: t("The final weight must be between 0% and 100% of the portfolio. Shorting and leverage are not supported.") },
    };
  }
  const match = scripted.find((request) => request.instrument_id === instrumentId && request.target_direct_weight === target);
  return {
    request: { instrument_id: instrumentId, target_direct_weight: target, funding: "CASH", original_words: match?.original_words ?? null },
    problem: null,
  };
}

/** "NVDA at a final direct weight of 25.0%" */
export function describePurchase(purchase: PurchaseRequest): string {
  return tf("{instrument} at a final direct weight of {weight}", { instrument: purchase.instrument_id, weight: formatFraction(purchase.target_direct_weight) });
}
