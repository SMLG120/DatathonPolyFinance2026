import { describe, expect, it } from "vitest";
import { FIXTURES } from "@/lib/fixtures";
import { describePurchase, FUNDING_STATEMENT, heldWeight, instrumentName, portfolioRows, readPurchaseForm } from "./portfolio";

// The recorded answer of GET /portfolios/robert.
const { scenario, instruments, purchasable_instrument_ids: purchasable } = FIXTURES.portfolioRobert.response;
const portfolio = scenario.portfolio;
const scripted = scenario.demo_requests.map((demo) => demo.purchase_request);

describe("portfolio rows", () => {
  it("lists the positions in the order supplied, then cash, each with the weight the portfolio states", () => {
    const rows = portfolioRows(portfolio, instruments);
    expect(rows.map((row) => row.instrument_id)).toEqual([...portfolio.positions.map((position) => position.instrument_id), null]);
    expect(rows.map((row) => row.weight)).toEqual([...portfolio.positions.map((position) => position.weight), portfolio.cash_weight]);
    expect(rows.at(-1)).toMatchObject({ name: "Cash (CAD)", kind: "Cash" });
  });

  it("names instruments from the registry and falls back to the id", () => {
    expect(instrumentName(instruments, "NVDA")).toBe("NVIDIA");
    expect(instrumentName(instruments, "SPY")).toBe("SPDR S&P 500 ETF Trust");
    expect(instrumentName(instruments, "ZZZ")).toBe("ZZZ");
    expect(portfolioRows(portfolio, {})[0]).toMatchObject({ name: "XBB.TO", kind: "Not in the registry" });
  });

  it("reads the weight held now from the portfolio, and none for an instrument that is not held", () => {
    expect(heldWeight(portfolio, "RY.TO")).toBe(0.05);
    expect(heldWeight(portfolio, "NVDA")).toBeNull();
  });
});

describe("readPurchaseForm", () => {
  it("turns a complete form into a request for a FINAL direct weight, funded from cash", () => {
    const form = readPurchaseForm(purchasable, { instrumentId: "JNJ", target: 0.08 });
    expect(form.problem).toBeNull();
    expect(form.request).toEqual({ instrument_id: "JNJ", target_direct_weight: 0.08, funding: "CASH", original_words: null });
  });

  it("is exactly the scenario's recorded request, words included, when the form holds it", () => {
    expect(readPurchaseForm(purchasable, { instrumentId: "NVDA", target: 0.25 }, scripted).request).toEqual(scripted[0]);
    expect(scripted[0]?.original_words).toBe("Everyone is talking about Nvidia. I want it to be 25% of my portfolio.");
  });

  it("does not attach the scenario's words to a different request", () => {
    expect(readPurchaseForm(purchasable, { instrumentId: "NVDA", target: 0.2 }, scripted).request?.original_words).toBeNull();
  });

  it("works out nothing: no cash after the purchase, no amount added, no check against what is held", () => {
    // A target below the weight held, and one larger than the cash available, are both sendable forms:
    // whether they can be executed is the service's answer (execution status, feasibility).
    const below = readPurchaseForm(purchasable, { instrumentId: "RY.TO", target: 0.02 });
    const beyondCash = readPurchaseForm(purchasable, { instrumentId: "NVDA", target: 0.9 });
    expect(below.problem).toBeNull();
    expect(beyondCash.problem).toBeNull();
    expect(Object.keys(below.request ?? {}).sort()).toEqual(["funding", "instrument_id", "original_words", "target_direct_weight"]);
  });

  it.each([
    [{ instrumentId: null, target: 0.1 }, "NO_INSTRUMENT", "instrument"],
    [{ instrumentId: "", target: 0.1 }, "NO_INSTRUMENT", "instrument"],
    [{ instrumentId: "TSLA", target: 0.1 }, "UNSUPPORTED_INSTRUMENT", "instrument"],
    [{ instrumentId: "NVDA", target: null }, "NO_TARGET", "target"],
    [{ instrumentId: "NVDA", target: -0.01 }, "OUT_OF_RANGE", "target"],
    [{ instrumentId: "NVDA", target: 1.01 }, "OUT_OF_RANGE", "target"],
  ] as const)("says what is missing in the form: %j", (input, code, field) => {
    const form = readPurchaseForm(purchasable, input);
    expect(form.request).toBeNull();
    expect(form.problem).toMatchObject({ code, field });
  });

  it("accepts 0% and 100% as form values", () => {
    expect(readPurchaseForm(purchasable, { instrumentId: "NVDA", target: 0 }).problem).toBeNull();
    expect(readPurchaseForm(purchasable, { instrumentId: "NVDA", target: 1 }).problem).toBeNull();
  });
});

describe("describePurchase", () => {
  it("always states that the number is a final direct weight", () => {
    expect(describePurchase(scripted[0] as (typeof scripted)[number])).toBe("NVDA at a final direct weight of 25.0%");
  });

  it("states how every purchase is funded", () => {
    expect(FUNDING_STATEMENT).toBe("Funded from existing cash; all other positions unchanged; fees and taxes excluded.");
  });
});
