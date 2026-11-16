import { describe, expect, it } from "vitest";
import { FIXTURES } from "@/lib/fixtures";
import { ApiError } from "./errors";
import { asJob } from "./validate";

const job = FIXTURES.jobs.robertSucceeded.response;
const portfolio = FIXTURES.portfolioRobert.response.scenario.portfolio;

function refusal(value: unknown): ApiError | null {
  try {
    asJob(value, 200);
  } catch (error) {
    if (error instanceof ApiError) return error;
    throw error;
  }
  return null;
}

describe("asJob: the optional portfolio of a job (contracts/api.md section 2a)", () => {
  it("accepts a job without the member: one stored before jobs kept their portfolio", () => {
    expect("portfolio" in job).toBe(false);
    expect(asJob(job)).toBe(job);
  });

  it("accepts a job that carries a portfolio document", () => {
    const withPortfolio = { ...job, portfolio };
    expect(asJob(withPortfolio).portfolio).toBe(portfolio);
  });

  it("refuses null: the service leaves the member out and the schema forbids null", () => {
    expect(refusal({ ...job, portfolio: null })?.kind).toBe("invalid_response");
  });

  it("refuses a malformed portfolio instead of showing part of it", () => {
    const malformed: unknown[] = [
      "pf-robert-fictional-1",
      {},
      { ...portfolio, portfolio_id: 7 },
      { ...portfolio, cash_weight: "0.3" },
      { ...portfolio, positions: null },
      { ...portfolio, positions: [{ instrument_id: "SPY" }] },
      { ...portfolio, positions: [{ instrument_id: "SPY", weight: "0.2" }] },
    ];
    for (const value of malformed) expect(refusal({ ...job, portfolio: value })?.kind, JSON.stringify(value)).toBe("invalid_response");
  });
});
