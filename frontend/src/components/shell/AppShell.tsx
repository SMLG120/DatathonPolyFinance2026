"use client";

import { useMemo, type ReactNode } from "react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { formatDate } from "@/lib/format";
import { isTerminalJobStatus } from "@/lib/verdict";
import { useRuntime } from "@/state/runtime";
import { type StageId, useStage } from "@/state/stage";
import { useWorkflow } from "@/state/workflow";
import { Stepper } from "./Stepper";

export const SIMULATION_LABEL = "Simulation: fictional portfolio, not advice";
export const FIXTURES_LABEL = "Test data: fixtures";

const FIXTURES_REASONS = {
  "no-base-url": "This build has no service address, so every figure comes from recorded test data.",
  "invalid-base-url": "The configured service address is not a valid URL, so every figure comes from recorded test data.",
  requested: "Opened with ?fixtures=1, so every figure comes from recorded test data.",
} as const;

function useValuationDateText(): string {
  const { state } = useWorkflow();
  switch (state.portfolio.status) {
    case "ready":
      return formatDate(state.portfolio.data?.scenario.portfolio.valuation_date);
    case "loading":
      return "loading…";
    case "error":
      return "unavailable";
    case "idle":
      return "shown once a portfolio is loaded";
  }
}

function useCompletedStages(): ReadonlySet<StageId> {
  const { state, derived } = useWorkflow();
  return useMemo(() => {
    const done = new Set<StageId>();
    if (state.portfolio.status === "ready") done.add("persona");
    if (state.policies.length > 0) done.add("goals");
    if (state.investigationIds.length > 0) done.add("purchase");
    if (derived.latestInvestigation && isTerminalJobStatus(derived.latestInvestigation.status)) done.add("investigation");
    if (derived.latestReport) done.add("verdict");
    if (state.comparison || state.corrections.length > 0 || state.preferenceResponse) done.add("challenge");
    return done;
  }, [state.portfolio.status, state.policies.length, state.investigationIds.length, state.comparison, state.corrections.length, state.preferenceResponse, derived.latestInvestigation, derived.latestReport]);
}

/**
 * The frame around every stage: skip link, the persistent simulation notice,
 * the header with the stepper, the main region and the footer.
 */
export function AppShell({ children }: { children: ReactNode }) {
  const { config, needsAccessCode, forgetAccessCode } = useRuntime();
  const stage = useStage();
  const valuationDate = useValuationDateText();
  const completed = useCompletedStages();

  return (
    <div className="flex min-h-screen flex-col">
      <a
        href="#main-content"
        onClick={(event) => {
          // The hash carries the stage, so the skip link moves focus itself.
          event.preventDefault();
          document.getElementById("main-content")?.focus();
        }}
        className="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-[60] focus:rounded-md focus:bg-surface focus:px-4 focus:py-3 focus:font-semibold focus:text-accent focus:shadow-lg"
      >
        Skip to main content
      </a>

      {/* Always on screen, on every stage and at every scroll position. */}
      <section aria-label="Simulation notice" className="on-dark sticky top-0 z-30 bg-banner text-on-banner">
        <div className="mx-auto flex w-full max-w-6xl flex-wrap items-center gap-x-5 gap-y-1 px-4 py-2 text-sm sm:px-6">
          <p className="font-semibold" data-testid="simulation-label">
            {SIMULATION_LABEL}
          </p>
          <p className="sr-only" data-testid="valuation-date">
            Valuation date: <span className="tabular font-semibold text-on-banner">{valuationDate}</span>
          </p>
          {config.mode === "fixtures" ? (
            <p data-testid="fixtures-label" title={config.fixturesReason ? FIXTURES_REASONS[config.fixturesReason] : undefined}>
              <Badge tone="unknown" dashed className="py-0 leading-5">
                {FIXTURES_LABEL}
              </Badge>
            </p>
          ) : null}
        </div>
      </section>

      <header className="border-b border-line bg-surface">
        <div className="mx-auto w-full max-w-6xl px-4 py-5 sm:px-6 sm:py-6">
          <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
            <p className="flex items-center gap-3 text-xl font-semibold tracking-tight text-ink"><span aria-hidden="true" className="flex size-9 items-center justify-center rounded-xl bg-ink text-sm font-bold text-surface">B</span>Before You Buy</p>
            <p className="hidden text-sm text-ink-muted sm:block">Checks a proposed purchase against the rules you confirmed.</p>
          </div>
          <div className="mt-4">{needsAccessCode ? <div className="pb-4" /> : <Stepper current={stage} completed={completed} />}</div>
        </div>
      </header>

      <main id="main-content" tabIndex={-1} className="mx-auto w-full max-w-6xl flex-1 px-4 py-6 focus:outline-none sm:px-6 sm:py-10">
        {children}
      </main>

      <footer className="border-t border-line bg-surface">
        <div className="mx-auto w-full max-w-6xl space-y-2 px-4 py-5 text-sm text-ink-muted sm:px-6">
          <details><summary className="cursor-pointer font-medium">About this simulation and its data</summary><p className="mt-3">
            A fictional simulation built for a datathon. It gives no financial advice, makes no recommendation and no forecast, and places no
            trades. Fees and taxes are excluded from every calculation.
          </p>
          {config.mode === "fixtures" && config.fixturesReason ? (
            <p>
              <span className="font-semibold text-ink">{FIXTURES_LABEL}.</span> {FIXTURES_REASONS[config.fixturesReason]} Every figure shown is a
              recorded example answer built on synthetic inputs, not sourced market data. Each block of figures is marked &ldquo;Test data&rdquo;.
            </p>
          ) : null}
          </details>
          {config.mode === "live" && !needsAccessCode ? (
            <p>
              The access code is kept for this browser tab only.{" "}
              <Button variant="quiet" size="sm" onClick={forgetAccessCode} className="min-h-6 py-0">
                Forget the access code
              </Button>
            </p>
          ) : null}
        </div>
      </footer>
    </div>
  );
}
