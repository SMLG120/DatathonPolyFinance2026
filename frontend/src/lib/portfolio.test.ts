import { describe, expect, it } from "vitest";
import type { Instrument, Portfolio } from "@/lib/contracts";
import { describePurchase, portfolioRows, previewPurchase, totalWeight } from "./portfolio";

const NVDA: Instrument = { instrument_id: "NVDA", name: "NVIDIA Corporation", asset_type: "EQUITY", currency: "USD" };
const RY: Instrument = { instrument_id: "RY.TO", name: "Royal Bank of Canada", asset_type: "EQUITY", currency: "CAD" };
const SPY: Instrument = { instrument_id: "SPY", name: "SPDR S&P 500 ETF Trust", asset_type: "EQUITY_FUND", currency: "USD" };

const portfolio: Portfolio = {
  portfolio_id: "p",
  persona_id: "robert",
  valuation_date: "2026-11-12",
  reporting_currency: "CAD",
  cash_weight: 0.3,
  positions: [
    { ...SPY, weight: 0.65 },
    { ...RY, weight: 0.05 },
  ],
  is_fictional: true,
};
const instruments = [NVDA, RY, SPY];

describe("portfolio rows", () => {
  it("lists the positions and then cash, adding up to the whole portfolio", () => {
    const rows = portfolioRows(portfolio);
    expect(rows.map((r) => r.name)).toEqual(["SPDR S&P 500 ETF Trust", "Royal Bank of Canada", "Cash (CAD)"]);
    expect(rows.at(-1)).toMatchObject({ instrument_id: null, kind: "Cash", weight: 0.3 });
    expect(totalWeight(portfolio)).toBeCloseTo(1, 12);
  });
});

describe("previewPurchase", () => {
  it("funds a new position from cash and leaves every other position unchanged", () => {
    const preview = previewPurchase(portfolio, instruments, "NVDA", 0.25);

    expect(preview.problem).toBeNull();
    expect(preview.request).toEqual({ instrument_id: "NVDA", target_direct_weight: 0.25 });
    expect(preview.starting_direct).toBe(0);
    expect(preview.additional).toBe(0.25);
    expect(preview.cash_after).toBeCloseTo(0.05, 12);
    expect(preview.insufficient_cash).toBe(false);

    const byKey = Object.fromEntries(preview.rows.map((r) => [r.key, r]));
    expect(byKey["SPY"]).toMatchObject({ before: 0.65, after: 0.65, changed: false });
    expect(byKey["RY.TO"]).toMatchObject({ before: 0.05, after: 0.05, changed: false });
    expect(byKey["NVDA"]).toMatchObject({ before: 0, after: 0.25, changed: true });
    expect(byKey["__cash__"]!.before).toBe(0.3);
    expect(byKey["__cash__"]!.after).toBeCloseTo(0.05, 12);
    // Nothing is created or lost: the portfolio still adds up to 100%.
    expect(preview.rows.reduce((sum, r) => sum + r.after, 0)).toBeCloseTo(1, 12);
  });

  it("treats the target as the FINAL weight of a position already held, not as an amount to add", () => {
    const preview = previewPurchase(portfolio, instruments, "RY.TO", 0.15);

    expect(preview.starting_direct).toBe(0.05);
    expect(preview.additional).toBeCloseTo(0.1, 12);
    expect(preview.cash_after).toBeCloseTo(0.2, 12);
    expect(preview.rows.find((r) => r.key === "RY.TO")).toMatchObject({ before: 0.05, after: 0.15, changed: true });
    expect(preview.rows.filter((r) => r.key === "RY.TO")).toHaveLength(1);
  });

  it("accepts a target equal to the weight already held: nothing is bought", () => {
    const preview = previewPurchase(portfolio, instruments, "RY.TO", 0.05);
    expect(preview.problem).toBeNull();
    expect(preview.additional).toBe(0);
    expect(preview.cash_after).toBe(0.3);
  });

  it("accepts a purchase that uses exactly all the cash", () => {
    const preview = previewPurchase(portfolio, instruments, "NVDA", 0.3);
    expect(preview.problem).toBeNull();
    expect(preview.insufficient_cash).toBe(false);
    expect(preview.cash_after).toBeCloseTo(0, 12);
  });

  it("reports insufficient cash as a feasibility finding, not as an invalid request", () => {
    const preview = previewPurchase(portfolio, instruments, "NVDA", 0.4);
    expect(preview.problem).toBeNull();
    expect(preview.request).not.toBeNull();
    expect(preview.insufficient_cash).toBe(true);
    expect(preview.cash_after).toBeCloseTo(-0.1, 12);
  });

  it("rejects a target below the weight already held: the simulation does not sell", () => {
    const preview = previewPurchase(portfolio, instruments, "RY.TO", 0.02);
    expect(preview.problem).toMatchObject({ code: "BELOW_CURRENT", field: "target" });
    expect(preview.request).toBeNull();
    expect(preview.cash_after).toBeNull();
    // An invalid request changes nothing in the table.
    expect(preview.rows.every((r) => r.before === r.after && !r.changed)).toBe(true);
  });

  it.each([
    [-0.01, "NEGATIVE"],
    [1.01, "ABOVE_ONE"],
    [null, "NO_TARGET"],
  ] as const)("rejects a target of %s", (target, code) => {
    expect(previewPurchase(portfolio, instruments, "NVDA", target).problem?.code).toBe(code);
  });

  it("rejects a missing or unsupported instrument", () => {
    expect(previewPurchase(portfolio, instruments, null, 0.1).problem).toMatchObject({ code: "NO_INSTRUMENT", field: "instrument" });
    expect(previewPurchase(portfolio, instruments, "DOGE", 0.1).problem).toMatchObject({ code: "UNSUPPORTED_INSTRUMENT", field: "instrument" });
  });
});

describe("describePurchase", () => {
  it("always states that the number is a final direct weight", () => {
    expect(describePurchase({ instrument_id: "NVDA", target_direct_weight: 0.25 })).toBe("NVDA at a final direct weight of 25.0%");
  });
});
