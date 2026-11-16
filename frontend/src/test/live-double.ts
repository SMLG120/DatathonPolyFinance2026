import { vi } from "vitest";
import type { ApiClient } from "@/lib/api";
import { createFixturesClient, type FixturesClientOptions } from "@/lib/api/fixtures-client";
import type { Portfolio } from "@/lib/contracts";
import { FIXTURES } from "@/lib/fixtures";

/** The portfolio id this stand-in gives a customized portfolio. Only its difference from a scenario's id matters. */
export const customPortfolioId = (personaId: string) => `pf-${personaId}-custom-0123456789ab`;

/**
 * A stand-in for the live service, for tests of what the page SENDS and of which portfolio a job names.
 *
 * It is the fixtures client in live mode, for any persona. It cannot calculate, so it answers a request on
 * a customized portfolio with the recording made for the same request on the original one, and refuses
 * (as the fixtures client does) a request that has no recording: tests of such a request read the request
 * body only, never a figure. Like the service, it stores the portfolio a job was created with and returns
 * it as `portfolio` of GET /investigations/{id}.
 */
export function liveDouble(options: { simulate?: FixturesClientOptions["simulate"] } = {}) {
  const fixtures = createFixturesClient({ latencyMs: 0, simulate: options.simulate });
  const stored = new Map<string, Portfolio>();
  const check = vi.fn<ApiClient["check"]>(async (body, requestOptions) => {
    const rest = { ...body };
    delete rest.custom_portfolio;
    return fixtures.check(rest, requestOptions);
  });
  const createInvestigation = vi.fn<ApiClient["createInvestigation"]>(async (body, requestOptions) => {
    const rest = { ...body };
    delete rest.custom_portfolio;
    const accepted = await fixtures.createInvestigation(rest, requestOptions);
    const scenario = FIXTURES.scenarios[body.persona_id]?.portfolio;
    const custom = body.custom_portfolio;
    if (scenario) {
      stored.set(accepted.id, custom ? { ...scenario, portfolio_id: customPortfolioId(body.persona_id), cash_weight: custom.cash_weight, positions: custom.positions } : scenario);
    }
    return accepted;
  });
  const getInvestigation = vi.fn<ApiClient["getInvestigation"]>(async (id, requestOptions) => {
    const job = await fixtures.getInvestigation(id, requestOptions);
    const portfolio = stored.get(id);
    return portfolio ? { ...job, portfolio } : job;
  });
  const confirmRules = vi.fn(fixtures.confirmRules);
  const interpretRules = vi.fn(fixtures.interpretRules);
  // Like the service: the job of a rule change is checked against its parent's stored portfolio.
  const challengeInvestigation = vi.fn<ApiClient["challengeInvestigation"]>(async (id, body, requestOptions) => {
    const response = await fixtures.challengeInvestigation(id, body, requestOptions);
    const parent = stored.get(id);
    if (response.investigation && parent) stored.set(response.investigation.id, parent);
    return response;
  });
  const api: ApiClient = { ...fixtures, mode: "live", check, createInvestigation, getInvestigation, confirmRules, interpretRules, challengeInvestigation };
  return { api, stored, check, createInvestigation, getInvestigation, confirmRules, interpretRules, challengeInvestigation };
}
