import { describe, expect, it } from "vitest";
import type { CustomPortfolio } from "@/lib/contracts";
import { FIXTURES } from "@/lib/fixtures";
import {
  applyCustomPortfolio,
  customPortfolioOfReport,
  fractionToWeightText,
  hundredthsToFraction,
  hundredthsToText,
  isScenarioPortfolio,
  MAX_OBJECTIVE_LENGTH,
  portfolioCheckedLabel,
  readCustomizeForm,
  readWeight,
  restatedObjective,
  TOTAL_MESSAGE,
  withCustomPortfolio,
} from "./customize";

const robert = FIXTURES.portfolioRobert.response;
const scenarioPortfolio = robert.scenario.portfolio;
const purchasable = robert.purchasable_instrument_ids;
const scenarioRows = () => scenarioPortfolio.positions.map((position) => ({ instrumentId: position.instrument_id, text: fractionToWeightText(position.weight) }));
const scenarioForm = () => ({ rows: scenarioRows(), cashText: fractionToWeightText(scenarioPortfolio.cash_weight), objectiveText: "Keep my capital." });
const withRow = (instrumentId: string, text: string) => ({ ...scenarioForm(), rows: scenarioRows().map((row) => (row.instrumentId === instrumentId ? { ...row, text } : row)) });

describe("readWeight: a typed percentage, read from its digits", () => {
  it("reads whole hundredths of a percent without floating point", () => {
    expect(readWeight("12.5", "position")).toEqual({ ok: true, hundredths: 1250 });
    expect(readWeight(" 30 % ", "position")).toEqual({ ok: true, hundredths: 3000 });
    expect(readWeight("0.01", "position")).toEqual({ ok: true, hundredths: 1 });
    expect(readWeight(".5", "position")).toEqual({ ok: true, hundredths: 50 });
    expect(readWeight("12.50", "position")).toEqual({ ok: true, hundredths: 1250 });
    expect(readWeight("100", "cash")).toEqual({ ok: true, hundredths: 10_000 });
    expect(readWeight("0", "cash")).toEqual({ ok: true, hundredths: 0 });
  });

  it("refuses a negative weight as shorting", () => {
    const reading = readWeight("-5", "position");
    expect(reading).toMatchObject({ ok: false, code: "NEGATIVE" });
    expect(reading.ok ? "" : reading.message).toContain("Shorting is not supported");
    expect(readWeight("-0.01", "cash")).toMatchObject({ ok: false, code: "NEGATIVE" });
  });

  it("refuses a position at zero, but accepts cash at zero", () => {
    expect(readWeight("0", "position")).toMatchObject({ ok: false, code: "ZERO_POSITION" });
    expect(readWeight("0.00", "position")).toMatchObject({ ok: false, code: "ZERO_POSITION" });
    expect(readWeight("0.00", "cash")).toEqual({ ok: true, hundredths: 0 });
  });

  it("refuses more than 2 decimals, text that is not a number, an empty field and more than 100%", () => {
    expect(readWeight("12.345", "position")).toMatchObject({ ok: false, code: "TOO_PRECISE" });
    expect(readWeight("0.001", "cash")).toMatchObject({ ok: false, code: "TOO_PRECISE" });
    for (const text of ["abc", "1e2", "12,5", "1.2.3", ".", "--5"]) expect(readWeight(text, "position")).toMatchObject({ ok: false, code: "MALFORMED" });
    expect(readWeight("  ", "position")).toMatchObject({ ok: false, code: "EMPTY" });
    expect(readWeight("100.01", "cash")).toMatchObject({ ok: false, code: "ABOVE_FULL" });
    expect(readWeight("99999999999999999999", "cash")).toMatchObject({ ok: false, code: "ABOVE_FULL" });
  });

  it("writes hundredths back as text and as the fraction the JSON text names", () => {
    expect(hundredthsToText(9550)).toBe("95.50");
    expect(hundredthsToText(10_000)).toBe("100.00");
    expect(hundredthsToText(5)).toBe("0.05");
    expect(hundredthsToFraction(1250)).toBe(0.125);
    expect(hundredthsToFraction(3000)).toBe(0.3);
    expect(hundredthsToFraction(1)).toBe(0.0001);
    expect(fractionToWeightText(0.3)).toBe("30");
    expect(fractionToWeightText(0.125)).toBe("12.5");
    expect(fractionToWeightText(0.0525)).toBe("5.25");
    // Finer than a hundredth of a percent: written in full, so the field can say it has too many decimals.
    expect(fractionToWeightText(0.123456)).toBe("12.3456");
  });
});

describe("readCustomizeForm", () => {
  it("accepts the scenario portfolio as typed, and builds the weights to send in row order", () => {
    const reading = readCustomizeForm(scenarioForm(), purchasable);
    expect(reading.valid).toBe(true);
    expect(reading.totalHundredths).toBe(10_000);
    expect(reading.portfolio).toEqual({ cash_weight: scenarioPortfolio.cash_weight, positions: scenarioPortfolio.positions });
  });

  it("adds tenths exactly: 0.1 + 0.2 + 99.7 is 100, which floating point would not give", () => {
    const reading = readCustomizeForm({ rows: [{ instrumentId: "SPY", text: "0.1" }, { instrumentId: "NVDA", text: "0.2" }], cashText: "99.7", objectiveText: null }, purchasable);
    expect(reading.totalHundredths).toBe(10_000);
    expect(reading.valid).toBe(true);
    expect(reading.portfolio).toEqual({ cash_weight: 0.997, positions: [{ instrument_id: "SPY", weight: 0.001 }, { instrument_id: "NVDA", weight: 0.002 }] });
  });

  it("refuses a total that is not exactly 100%, above or below, and never rescales", () => {
    for (const cashText of ["29.99", "30.01", "35", "0"]) {
      const reading = readCustomizeForm({ ...scenarioForm(), cashText }, purchasable);
      expect(reading.valid).toBe(false);
      expect(reading.portfolio).toBeNull();
      expect(reading.totalError).toBe(TOTAL_MESSAGE);
    }
    expect(TOTAL_MESSAGE).toBe("Weights must total 100%. Leverage is not supported and weights are never rescaled.");
  });

  it("refuses a negative weight, a zero position and more than 2 decimals, each next to its row", () => {
    expect(readCustomizeForm(withRow("SPY", "-20"), purchasable).rowErrors.SPY).toContain("Shorting is not supported");
    expect(readCustomizeForm(withRow("SPY", "0"), purchasable).rowErrors.SPY).toContain("must be above 0%");
    expect(readCustomizeForm(withRow("SPY", "20.005"), purchasable).rowErrors.SPY).toContain("at most 2 decimals");
    for (const text of ["-20", "0", "20.005"]) {
      const reading = readCustomizeForm(withRow("SPY", text), purchasable);
      expect(reading.valid).toBe(false);
      expect(reading.portfolio).toBeNull();
    }
    // No total is stated while a weight cannot be read.
    expect(readCustomizeForm(withRow("SPY", "-20"), purchasable).totalHundredths).toBeNull();
  });

  it("refuses an asset listed twice and an asset that cannot be held", () => {
    const twice = readCustomizeForm({ rows: [{ instrumentId: "SPY", text: "50" }, { instrumentId: "SPY", text: "20" }], cashText: "30", objectiveText: null }, purchasable);
    expect(twice.valid).toBe(false);
    expect(twice.listError).toBe("An asset can be listed only once.");
    const unsupported = readCustomizeForm({ rows: [{ instrumentId: "TSLA", text: "70" }], cashText: "30", objectiveText: null }, purchasable);
    expect(unsupported.valid).toBe(false);
    expect(unsupported.listError).toContain("TSLA cannot be held");
  });

  it("needs an objective that is not empty and has at most 2000 characters", () => {
    expect(readCustomizeForm({ ...scenarioForm(), objectiveText: "   " }, purchasable)).toMatchObject({ valid: false, objectiveError: expect.stringContaining("cannot be empty") });
    expect(readCustomizeForm({ ...scenarioForm(), objectiveText: "a".repeat(MAX_OBJECTIVE_LENGTH) }, purchasable).valid).toBe(true);
    expect(readCustomizeForm({ ...scenarioForm(), objectiveText: "a".repeat(MAX_OBJECTIVE_LENGTH + 1) }, purchasable)).toMatchObject({
      valid: false,
      objectiveError: expect.stringContaining("at most 2000 characters"),
    });
  });
});

describe("one value for what is shown and what is sent", () => {
  const custom: CustomPortfolio = { cash_weight: 0.35, positions: [{ instrument_id: "XBB.TO", weight: 0.5 }, { instrument_id: "NVDA", weight: 0.15 }] };

  it("leaves the member out altogether without a customization, so the request is what it always was", () => {
    const body = { persona_id: "robert", draft_rules: null };
    expect(withCustomPortfolio(body, null)).toBe(body);
    expect("custom_portfolio" in withCustomPortfolio(body, null)).toBe(false);
    expect(JSON.stringify(withCustomPortfolio(body, null))).toBe(JSON.stringify(body));
    expect(withCustomPortfolio(body, custom)).toEqual({ ...body, custom_portfolio: custom });
    expect(withCustomPortfolio(body, custom).custom_portfolio).toBe(custom);
  });

  it("shows the scenario portfolio with exactly the customized cash and positions", () => {
    expect(applyCustomPortfolio(scenarioPortfolio, null)).toBe(scenarioPortfolio);
    const shown = applyCustomPortfolio(scenarioPortfolio, custom);
    expect(shown.positions).toBe(custom.positions);
    expect(shown.cash_weight).toBe(custom.cash_weight);
    expect(shown).toMatchObject({ persona_id: "robert", valuation_date: scenarioPortfolio.valuation_date, base_currency: "CAD", fictional: true });
  });

  it("treats the scenario's own weights, in any order, as the scenario portfolio", () => {
    expect(isScenarioPortfolio({ cash_weight: scenarioPortfolio.cash_weight, positions: [...scenarioPortfolio.positions].reverse() }, scenarioPortfolio)).toBe(true);
    expect(isScenarioPortfolio(custom, scenarioPortfolio)).toBe(false);
    expect(isScenarioPortfolio({ cash_weight: scenarioPortfolio.cash_weight, positions: scenarioPortfolio.positions.slice(1) }, scenarioPortfolio)).toBe(false);
  });

  it("names a report's stored portfolio by its id, and reproduces a customized one for a preview about that report", () => {
    const stored = { ...scenarioPortfolio, portfolio_id: "pf-robert-custom-0123456789ab", cash_weight: custom.cash_weight, positions: custom.positions };
    expect(portfolioCheckedLabel(stored, scenarioPortfolio, "Robert")).toBe("Customized fictional portfolio");
    expect(portfolioCheckedLabel(scenarioPortfolio, scenarioPortfolio, "Robert")).toBe("Robert’s original fictional portfolio");
    expect(customPortfolioOfReport(stored, scenarioPortfolio)).toEqual(custom);
    expect(customPortfolioOfReport(scenarioPortfolio, scenarioPortfolio)).toBeNull();
    expect(customPortfolioOfReport(undefined, scenarioPortfolio)).toBeNull();
  });

  it("restates an objective with the user's words only: same id and kind, stated by the user, no case reference", () => {
    const original = robert.scenario.objectives[0];
    if (!original) throw new Error("Robert's scenario has no objective.");
    expect(restatedObjective(original, "  My own words.  ")).toEqual({
      objective_id: original.objective_id,
      kind: original.kind,
      original_words: "  My own words.  ",
      source: "USER_STATED",
      case_reference: null,
    });
  });
});
