"use client";

import { createContext, useCallback, useContext, useMemo, useState, useSyncExternalStore, type ReactNode } from "react";
import { clearAccessCode, readAccessCode, storeAccessCode, subscribeAccessCode } from "@/lib/access-code";
import { createApiClient, type ApiClient } from "@/lib/api";
import { createHttpClient } from "@/lib/api/http-client";
import { DataModeProvider } from "@/components/ui/TestDataTag";
import { readBuildTimeApiBaseUrl, resolveRuntimeConfig, SIMULATED_TIMEOUT_DEADLINE_MS, TIMING, type RuntimeConfig, type Timing } from "@/lib/config";

export interface Runtime {
  config: RuntimeConfig;
  api: ApiClient;
  timing: Timing;
  /** Live mode only: true while no access code is held, so the form must be shown. */
  needsAccessCode: boolean;
  /** True after the service refused the code that was in use. */
  accessCodeRejected: boolean;
  /**
   * Checks a typed code against the service and keeps it (in sessionStorage)
   * only if it is accepted. Rejects with an ApiError otherwise.
   */
  submitAccessCode: (code: string) => Promise<void>;
  /** Forgets the access code and shows the form again. */
  forgetAccessCode: () => void;
}

const RuntimeContext = createContext<Runtime | null>(null);

export interface RuntimeProviderProps {
  children: ReactNode;
  /** Test seams. The app itself passes none of these. */
  config?: RuntimeConfig;
  api?: ApiClient;
  timing?: Timing;
  verifyAccessCode?: (code: string) => Promise<void>;
}

function timingFor(config: RuntimeConfig): Timing {
  // A simulated job that never finishes should reach its visible deadline quickly.
  if (config.mode === "fixtures" && config.simulate === "poll-timeout") return { ...TIMING, pollDeadlineMs: SIMULATED_TIMEOUT_DEADLINE_MS };
  return TIMING;
}

/**
 * Resolves how the app runs (fixtures or live), builds the API client and
 * holds the access-code gate. Must be rendered in the browser only: it reads
 * the page URL.
 */
export function RuntimeProvider({ children, config: configOverride, api: apiOverride, timing: timingOverride, verifyAccessCode }: RuntimeProviderProps) {
  const [config] = useState<RuntimeConfig>(
    () => configOverride ?? resolveRuntimeConfig({ apiBaseUrl: readBuildTimeApiBaseUrl(), search: window.location.search }),
  );
  const [rejected, setRejected] = useState(false);
  const accessCode = useSyncExternalStore(subscribeAccessCode, readAccessCode, () => null);

  const [api] = useState<ApiClient>(
    () =>
      apiOverride ??
      createApiClient(config, {
        getAccessCode: readAccessCode,
        onUnauthorized: () => {
          clearAccessCode();
          setRejected(true);
        },
      }),
  );

  const submitAccessCode = useCallback(
    async (code: string) => {
      const candidate = code.trim();
      if (verifyAccessCode) {
        await verifyAccessCode(candidate);
      } else if (config.apiBaseUrl) {
        // A throwaway client that carries the candidate, so the code is stored
        // only once the service has accepted it.
        await createHttpClient({ baseUrl: config.apiBaseUrl, getAccessCode: () => candidate }).getPortfolio("robert");
      }
      storeAccessCode(candidate);
      setRejected(false);
    },
    [config.apiBaseUrl, verifyAccessCode],
  );

  const forgetAccessCode = useCallback(() => {
    clearAccessCode();
    setRejected(false);
  }, []);

  const value = useMemo<Runtime>(
    () => ({
      config,
      api,
      timing: timingOverride ?? timingFor(config),
      needsAccessCode: config.mode === "live" && !accessCode,
      accessCodeRejected: rejected,
      submitAccessCode,
      forgetAccessCode,
    }),
    [config, api, timingOverride, accessCode, rejected, submitAccessCode, forgetAccessCode],
  );

  return (
    <RuntimeContext.Provider value={value}>
      <DataModeProvider value={config.mode}>{children}</DataModeProvider>
    </RuntimeContext.Provider>
  );
}

export function useRuntime(): Runtime {
  const runtime = useContext(RuntimeContext);
  if (!runtime) throw new Error("useRuntime must be used inside <RuntimeProvider>");
  return runtime;
}
