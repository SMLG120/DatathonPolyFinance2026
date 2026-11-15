/**
 * Runtime configuration.
 *
 * The API base URL is a build-time, non-secret value. The demo access code is
 * NOT configuration: it is typed at runtime (see `access-code.ts`).
 */

import { POLL_DEADLINE_MS, POLL_INTERVAL_MS } from "@/lib/contracts";

export type AppMode = "fixtures" | "live";

/** Failure states that can be requested in fixtures mode to exercise the interface. */
export const FIXTURE_SIMULATIONS = ["job-failed", "poll-timeout", "portfolio-error", "check-error"] as const;
export type FixtureSimulation = (typeof FIXTURE_SIMULATIONS)[number];

export type FixturesReason = "no-base-url" | "invalid-base-url" | "requested";

export interface RuntimeConfig {
  mode: AppMode;
  /** Normalized base URL without a trailing slash, or null. */
  apiBaseUrl: string | null;
  /** Why the app runs on fixtures; null in live mode. */
  fixturesReason: FixturesReason | null;
  /** Only honoured in fixtures mode. */
  simulate: FixtureSimulation | null;
}

export function normalizeBaseUrl(raw: string | undefined | null): { url: string | null; invalid: boolean } {
  const trimmed = (raw ?? "").trim();
  if (trimmed === "") return { url: null, invalid: false };
  try {
    const parsed = new URL(trimmed);
    if (parsed.protocol !== "https:" && parsed.protocol !== "http:") return { url: null, invalid: true };
    return { url: trimmed.replace(/\/+$/, ""), invalid: false };
  } catch {
    return { url: null, invalid: true };
  }
}

function parseSimulation(value: string | null): FixtureSimulation | null {
  return (FIXTURE_SIMULATIONS as readonly string[]).includes(value ?? "") ? (value as FixtureSimulation) : null;
}

/**
 * Fixtures mode is used when no API base URL was configured at build time, or
 * when the page is opened with `?fixtures=1`.
 */
export function resolveRuntimeConfig(input: { apiBaseUrl: string | undefined | null; search: string }): RuntimeConfig {
  const { url, invalid } = normalizeBaseUrl(input.apiBaseUrl);
  const params = new URLSearchParams(input.search);
  const requested = params.get("fixtures") === "1";

  let fixturesReason: FixturesReason | null = null;
  if (requested) fixturesReason = "requested";
  else if (invalid) fixturesReason = "invalid-base-url";
  else if (url === null) fixturesReason = "no-base-url";

  const mode: AppMode = fixturesReason === null ? "live" : "fixtures";
  return {
    mode,
    apiBaseUrl: url,
    fixturesReason,
    simulate: mode === "fixtures" ? parseSimulation(params.get("simulate")) : null,
  };
}

/** Inlined by Next.js at build time. Not a secret. */
export function readBuildTimeApiBaseUrl(): string | undefined {
  return process.env.NEXT_PUBLIC_API_BASE_URL;
}

/** Timing for the investigation job poll (BUILD_BRIEF §7: polling has a deadline). */
export interface Timing {
  pollIntervalMs: number;
  pollDeadlineMs: number;
  previewDebounceMs: number;
}

/**
 * The poll interval and deadline are the shared contract's: the deadline is
 * longer than the server's own job deadline, so the page always outlasts the
 * job and shows its real outcome. The same values are used on test data.
 */
export const TIMING: Timing = {
  pollIntervalMs: POLL_INTERVAL_MS,
  pollDeadlineMs: POLL_DEADLINE_MS,
  previewDebounceMs: 400,
};

/** Fixtures mode with `?simulate=poll-timeout`: a job that never finishes reaches its visible deadline quickly. */
export const SIMULATED_TIMEOUT_DEADLINE_MS = 4_000;
