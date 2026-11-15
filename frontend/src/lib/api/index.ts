import type { RuntimeConfig } from "@/lib/config";
import type { ApiClient } from "./client";
import { createFixturesClient } from "./fixtures-client";
import { createHttpClient } from "./http-client";

export type { ApiClient, RequestOptions } from "./client";
export { ApiError, describeError, isAbortError, isApiError } from "./errors";

export interface ApiClientDependencies {
  getAccessCode: () => string | null;
  onUnauthorized: () => void;
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
  return createFixturesClient({ simulate: config.simulate });
}
