import { describe, expect, it } from "vitest";
import {
  decimalsToDistinguish,
  formatChange,
  formatCoverage,
  formatDate,
  formatDateTime,
  formatFraction,
  formatFractionRange,
  formatGap,
  formatPoints,
  formatReturn,
  formatTime,
  fractionToPercentInput,
  isRange,
  percentInputToFraction,
  shiftDecimal,
  UNKNOWN_TEXT,
} from "./format";

describe("formatFraction", () => {
  it("shows a portfolio fraction as a percentage with one decimal", () => {
    expect(formatFraction(0.265)).toBe("26.5%");
    expect(formatFraction(0.1)).toBe("10.0%");
    expect(formatFraction(0)).toBe("0.0%");
    expect(formatFraction(1)).toBe("100.0%");
  });

  it("rounds on the decimal value, not on its binary approximation", () => {
    // 0.285 * 100 is 28.499999999999996 in binary floating point.
    expect(formatFraction(0.285)).toBe("28.5%");
    expect(formatFraction(0.12345, { decimals: 2 })).toBe("12.35%");
    expect(formatFraction(0.0005)).toBe("0.1%");
    expect(formatFraction(0.00049)).toBe("< 0.1%");
  });

  it("uses a real minus sign and never shows a negative zero", () => {
    expect(formatFraction(-0.1778)).toBe("−17.8%");
    expect(formatFraction(-0.0001)).toBe("> −0.1%");
    expect(formatFraction(-0)).toBe("0.0%");
  });

  describe("a value that is not zero but rounds to zero (finding F-06)", () => {
    it("is printed as a bound at the last decimal shown, never as zero", () => {
      // The value the acceptance run met: possible_extra.proposed of Mateo's request.
      expect(formatFraction(0.00048735)).toBe("< 0.1%");
      expect(formatFraction(0.00048735, { decimals: 2 })).toBe("0.05%");
      expect(formatFraction(0.00004, { decimals: 2 })).toBe("< 0.01%");
      expect(formatFraction(0.004, { decimals: 0 })).toBe("< 1%");
      expect(formatFraction(0.00000004, { decimals: 4 })).toBe("< 0.0001%");
    });

    it("keeps the sign of a negative value, as a bound from the other side", () => {
      expect(formatFraction(-0.00048735)).toBe("> −0.1%");
      expect(formatFraction(-0.00004, { decimals: 2 })).toBe("> −0.01%");
      expect(formatReturn(-0.00004)).toBe("> −0.01%");
    });

    it("signs a positive bound where positive values are signed", () => {
      expect(formatFraction(0.0004, { signed: true })).toBe("< +0.1%");
      expect(formatReturn(0.00004)).toBe("< +0.01%");
      expect(formatFraction(-0.0004, { signed: true })).toBe("> −0.1%");
    });

    it("leaves zero, and float noise within the contract's tolerance of zero, as zero", () => {
      expect(formatFraction(0)).toBe("0.0%");
      expect(formatFraction(-0)).toBe("0.0%");
      expect(formatFraction(1e-9)).toBe("0.0%");
      expect(formatFraction(-1e-9)).toBe("0.0%");
      expect(formatFraction(0.1 + 0.2 - 0.3)).toBe("0.0%");
      expect(formatFraction(2e-9)).toBe("< 0.1%");
      expect(formatFraction(0, { decimals: 2, signed: true })).toBe("0.00%");
    });

    it("changes nothing for a value that reaches the last decimal shown", () => {
      expect(formatFraction(0.0005)).toBe("0.1%");
      expect(formatFraction(0.001)).toBe("0.1%");
      expect(formatFraction(-0.0005)).toBe("−0.1%");
      expect(formatFraction(0.00005, { decimals: 2 })).toBe("0.01%");
      expect(formatFraction(0.005, { decimals: 0 })).toBe("1%");
    });

    it("applies to truncation too: a non-zero share is never shown as none", () => {
      expect(formatFraction(0.0009, { rounding: "down" })).toBe("< 0.1%");
      expect(formatCoverage(0.0009)).toBe("< 0.1%");
      expect(formatFraction(0.001, { rounding: "down" })).toBe("0.1%");
      expect(formatCoverage(0)).toBe("0.0%");
    });
  });

  it("can sign positive values for changes and returns", () => {
    expect(formatFraction(0.02, { signed: true })).toBe("+2.0%");
    expect(formatFraction(-0.02, { signed: true })).toBe("−2.0%");
    expect(formatFraction(0, { signed: true })).toBe("0.0%");
  });

  it("can truncate toward zero so a maximum is never overstated", () => {
    expect(formatFraction(0.084468, { decimals: 2, rounding: "down" })).toBe("8.44%");
    expect(formatFraction(0.084468, { decimals: 2 })).toBe("8.45%");
    expect(formatFraction(0.085, { decimals: 2, rounding: "down" })).toBe("8.50%");
    expect(formatFraction(0.0999, { decimals: 1, rounding: "down" })).toBe("9.9%");
  });

  it("words anything that is not a finite number as Unknown, never as 0%", () => {
    expect(formatFraction(null)).toBe(UNKNOWN_TEXT);
    expect(formatFraction(undefined)).toBe(UNKNOWN_TEXT);
    expect(formatFraction(Number.NaN)).toBe(UNKNOWN_TEXT);
    expect(formatFraction(Number.POSITIVE_INFINITY)).toBe(UNKNOWN_TEXT);
  });
});

describe("formatFractionRange", () => {
  it("words a possible range from lower to upper", () => {
    expect(formatFractionRange(0.03895, 0.18895)).toBe("3.9% to 18.9%");
  });

  it("collapses a range whose bounds are equal into one value", () => {
    expect(formatFractionRange(0.265, 0.265)).toBe("26.5%");
    expect(isRange(0.265, 0.265)).toBe(false);
    expect(isRange(0.265, 0.2650000000001)).toBe(false);
  });

  it("adds decimals when two different bounds would otherwise read the same", () => {
    expect(formatFractionRange(0.1001, 0.1004)).toBe("10.01% to 10.04%");
    expect(isRange(0.1001, 0.1004)).toBe(true);
  });

  it("gives a range that starts at zero the decimals that show its other bound (finding F-06)", () => {
    expect(formatFractionRange(0, 0.0003)).toBe("0.00% to 0.03%");
    expect(decimalsToDistinguish(0, 0.0003)).toBe(2);
    expect(formatFractionRange(0.0003, 0.0004)).toBe("0.03% to 0.04%");
  });

  it("never words a non-zero bound as zero, even at the most decimals it shows (finding F-06)", () => {
    expect(formatFractionRange(0, 0.0000001)).toBe("0.0000% to < 0.0001%");
    expect(formatFractionRange(0.0000001, 0.0000002)).toBe("< 0.0001%");
    expect(formatFractionRange(0.10000001, 0.10000002)).toBe("10.0000%");
  });

  it("is Unknown when either bound is missing", () => {
    expect(formatFractionRange(null, 0.2)).toBe(UNKNOWN_TEXT);
    expect(formatFractionRange(0.1, undefined)).toBe(UNKNOWN_TEXT);
    expect(isRange(null, 0.2)).toBe(false);
  });
});

describe("decimalsToDistinguish", () => {
  it("keeps one decimal when the values already read differently", () => {
    expect(decimalsToDistinguish(0.265, 0.1)).toBe(1);
  });

  it("finds the precision at which a value just over a limit is visibly over it", () => {
    expect(decimalsToDistinguish(0.1004, 0.1)).toBe(2);
    expect(formatFraction(0.1004, { decimals: 2 })).toBe("10.04%");
    expect(decimalsToDistinguish(0.10004, 0.1)).toBe(3);
  });

  it("does not add decimals for values that are equal", () => {
    expect(decimalsToDistinguish(0.1, 0.1)).toBe(1);
  });
});

describe("formatPoints and formatGap", () => {
  it("words a difference in percentage points", () => {
    expect(formatPoints(0.165)).toBe("16.5 points");
    expect(formatPoints(-0.035)).toBe("3.5 points");
    expect(formatPoints(0.01)).toBe("1.0 point");
    expect(formatPoints(null)).toBe(UNKNOWN_TEXT);
  });

  it("says which side of a maximum the measured value is on", () => {
    expect(formatGap(0.165)).toBe("16.5 points over the limit");
    expect(formatGap(-0.035)).toBe("3.5 points under the limit");
  });

  it("states exact equality instead of a zero gap", () => {
    expect(formatGap(0)).toBe("Exactly at the limit");
    expect(formatGap(1e-12)).toBe("Exactly at the limit");
    expect(formatGap(0, "min")).toBe("Exactly at the minimum");
  });

  it("does not round a small real gap down to zero points", () => {
    expect(formatGap(0.0004)).toBe("0.04 points over the limit");
  });

  it("reads the gap as the contract defines it for a minimum too: positive is the size of the breach", () => {
    expect(formatGap(0.05, "min")).toBe("5.0 points below the minimum");
    expect(formatGap(-0.05, "min")).toBe("5.0 points above the minimum");
  });

  it("names the limit as the caller asks, and starts at the decimals asked for", () => {
    expect(formatGap(0.0525, "max", "budget", 2)).toBe("5.25 points over the budget");
    expect(formatGap(0.162, "max", "limit")).toBe("16.2 points over the limit");
  });

  it("says a gap cannot be determined when it is unknown", () => {
    expect(formatGap(null)).toBe("Cannot be determined");
    expect(formatGap(undefined)).toBe("Cannot be determined");
  });
});

describe("formatCoverage and formatReturn", () => {
  it("truncates a coverage, so a fund just short of complete never reads 100.0%", () => {
    expect(formatCoverage(0.9987)).toBe("99.8%");
    expect(formatCoverage(0.9996)).toBe("99.9%");
    expect(formatCoverage(0.99999)).toBe("99.9%");
    expect(formatCoverage(0.98)).toBe("98.0%");
    expect(formatCoverage(1)).toBe("100.0%");
    expect(formatCoverage(0)).toBe("0.0%");
    expect(formatCoverage(null)).toBe(UNKNOWN_TEXT);
  });

  it("shows a return signed, to two decimals", () => {
    expect(formatReturn(-0.1525)).toBe("−15.25%");
    expect(formatReturn(0.04)).toBe("+4.00%");
    expect(formatReturn(0)).toBe("0.00%");
    expect(formatReturn(null)).toBe(UNKNOWN_TEXT);
  });
});

describe("dates and times", () => {
  it("formats an ISO date without shifting it across a time zone", () => {
    expect(formatDate("2026-11-12")).toBe("12 Nov 2026");
    expect(formatDate("2021-12-31")).toBe("31 Dec 2021");
    expect(formatDate("2026-01-01T23:59:59Z")).toBe("1 Jan 2026");
  });

  it("is Unknown for a missing or malformed date", () => {
    expect(formatDate(null)).toBe(UNKNOWN_TEXT);
    expect(formatDate("12/11/2026")).toBe(UNKNOWN_TEXT);
    expect(formatDate("2026-13-01")).toBe(UNKNOWN_TEXT);
  });

  it("formats a timestamp in UTC", () => {
    expect(formatTime("2026-11-14T15:02:11Z")).toBe("15:02:11 UTC");
    expect(formatDateTime("2026-11-14T15:02:11Z")).toBe("14 Nov 2026, 15:02:11 UTC");
    expect(formatTime("2026-11-14")).toBe(UNKNOWN_TEXT);
    expect(formatDateTime(undefined)).toBe(UNKNOWN_TEXT);
  });
});

describe("percentage form fields", () => {
  it("turns a fraction into the text of a percentage field", () => {
    expect(fractionToPercentInput(0.1)).toBe("10");
    expect(fractionToPercentInput(0.125)).toBe("12.5");
    expect(fractionToPercentInput(0)).toBe("0");
    expect(fractionToPercentInput(0.3)).toBe("30");
  });

  it("leaves the field empty when there is no value", () => {
    expect(fractionToPercentInput(null)).toBe("");
    expect(fractionToPercentInput(undefined)).toBe("");
  });

  it("reads typed text back into an exact fraction", () => {
    expect(percentInputToFraction("10")).toBe(0.1);
    expect(percentInputToFraction("12.5")).toBe(0.125);
    expect(percentInputToFraction(" 30 % ")).toBe(0.3);
    expect(percentInputToFraction("0")).toBe(0);
    expect(percentInputToFraction(".5")).toBe(0.005);
  });

  it("reads empty or malformed text as no value, never as zero", () => {
    expect(percentInputToFraction("")).toBeNull();
    expect(percentInputToFraction("   ")).toBeNull();
    expect(percentInputToFraction("abc")).toBeNull();
    expect(percentInputToFraction("-5")).toBeNull();
    expect(percentInputToFraction("1e2")).toBeNull();
    expect(percentInputToFraction("10,5")).toBeNull();
  });
});

describe("shiftDecimal", () => {
  it("moves the decimal point exactly", () => {
    expect(shiftDecimal(0.265, 3)).toBe(265);
    expect(shiftDecimal(12.5, -2)).toBe(0.125);
    expect(shiftDecimal(0, 5)).toBe(0);
    expect(shiftDecimal(1e-7, 7)).toBe(1);
  });
});

describe("formatChange", () => {
  it("words a change in percentage points with its direction", () => {
    expect(formatChange(0.25)).toBe("+25.0 points");
    expect(formatChange(-0.25)).toBe("\u221225.0 points");
    expect(formatChange(0.01)).toBe("+1.0 point");
  });

  it("says 'No change' for zero and 'Unknown' for a missing value", () => {
    expect(formatChange(0)).toBe("No change");
    expect(formatChange(1e-12)).toBe("No change");
    expect(formatChange(null)).toBe("Unknown");
    expect(formatChange(Number.NaN)).toBe("Unknown");
  });
});
