import type { RuntimeConfig } from "@/lib/config";
import type { ApiClient } from "./client";
import { createHttpClient } from "./http-client";

export { newIdempotencyKey } from "./client";
export type { ApiClient, IdempotentRequestOptions, RequestOptions } from "./client";
export { ApiError, describeError, isAbortError, isApiError } from "./errors";

export interface ApiClientDependencies {
  getAccessCode: () => string | null;
  onUnauthorized: () => void;
}

/**
 * The fixtures client and its recorded bodies are loaded on first use, so a
 * live session never downloads test data.
 */
function createLazyFixturesClient(config: RuntimeConfig): ApiClient {
  let loading: Promise<ApiClient> | null = null;
  const client = () => (loading ??= import("./fixtures-client").then((module) => module.createFixturesClient({ simulate: config.simulate })));
  return {
    mode: "fixtures",
    getPortfolio: async (...args) => (await client()).getPortfolio(...args),
    interpretRules: async (...args) => (await client()).interpretRules(...args),
    confirmRules: async (...args) => (await client()).confirmRules(...args),
    check: async (...args) => (await client()).check(...args),
    createInvestigation: async (...args) => (await client()).createInvestigation(...args),
    getInvestigation: async (...args) => (await client()).getInvestigation(...args),
    challengeInvestigation: async (...args) => (await client()).challengeInvestigation(...args),
  };
}

/** Picks the client for the resolved runtime mode. */
export function createApiClient(config: RuntimeConfig, dependencies: ApiClientDependencies): ApiClient {
  if (config.mode === "live" && config.apiBaseUrl) {
    return createHttpClient({
      baseUrl: config.apiBaseUrl,
      getAccessCode: dependencies.getAccessCode,
      onUnauthorized: dependencies.onUnauthorized,
    });
  }
  return createLazyFixturesClient(config);
}
