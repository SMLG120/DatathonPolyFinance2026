"use client";

import { useId, useRef, useState } from "react";
import { BeforeAfterTable } from "@/components/portfolio/BeforeAfterTable";
import { StageFrame } from "@/components/shell/StageFrame";
import { EmptyBlock, ErrorBlock, LoadingBlock } from "@/components/ui/AsyncStates";
import { Button, LinkButton } from "@/components/ui/Button";
import { describedBy, Field, Select } from "@/components/ui/Field";
import { ArrowRightIcon, ErrorIcon } from "@/components/ui/icons";
import { Notice } from "@/components/ui/Notice";
import { Fact, Facts, Panel } from "@/components/ui/Panel";
import { cn } from "@/lib/cn";
import { formatFraction, percentInputToFraction } from "@/lib/format";
import { assetTypeLabel, FUNDING_STATEMENT, previewPurchase } from "@/lib/portfolio";
import { ruleSummary } from "@/lib/rules";
import { activeRules } from "@/lib/verdict";
import { goToStage, stageHref } from "@/state/stage";
import { useWorkflow } from "@/state/workflow";

/** Stage 3: the purchase as an instrument and the FINAL direct weight it should have. */
export function PurchaseStage() {
  const { state, actions, derived } = useWorkflow();
  const instrumentId = useId();
  const targetId = useId();
  const instrumentRef = useRef<HTMLSelectElement>(null);
  const targetRef = useRef<HTMLInputElement>(null);
  const [attempted, setAttempted] = useState(false);

  const policy = derived.currentPolicy;
  const data = state.portfolio.data;

  if (state.portfolio.status !== "ready" || !data) {
    return (
      <StageFrame stage="purchase" lead="Describe the purchase to check: which instrument, and the final weight it should have in the portfolio.">
        {state.portfolio.status === "error" ? (
          <ErrorBlock title="The portfolio could not be loaded" message={state.portfolio.error ?? "The request failed."} onRetry={actions.retryPortfolio}>
            <p>A purchase is described relative to a portfolio, so this stage needs it.</p>
          </ErrorBlock>
        ) : (
          <LoadingBlock label="Loading the portfolio this purchase applies to…" />
        )}
      </StageFrame>
    );
  }

  const { portfolio, purchasable_instruments: instruments } = data;
  const target = percentInputToFraction(state.purchase.targetText);
  const targetMalformed = state.purchase.targetText.trim() !== "" && target === null;
  const preview = previewPurchase(portfolio, instruments, state.purchase.instrumentId || null, target);
  const problem = preview.problem;
  // A field left empty is not an error until the user tries to start.
  const showProblem = problem !== null && (attempted || (problem.code !== "NO_INSTRUMENT" && problem.code !== "NO_TARGET") || targetMalformed);
  const instrumentError = showProblem && problem.field === "instrument" ? problem.message : null;
  const targetError = targetMalformed ? "Enter a number such as 25 or 12.5." : showProblem && problem.field === "target" ? problem.message : null;
  const starting = state.start.status === "loading";
  const canStart = preview.request !== null && policy !== null;
  const active = activeRules(policy);

  async function start() {
    setAttempted(true);
    if (!preview.request) {
      (problem?.field === "instrument" ? instrumentRef.current : targetRef.current)?.focus();
      return;
    }
    if (!policy) return;
    const id = await actions.startInvestigation(preview.request);
    if (id) goToStage("investigation");
  }

  return (
    <StageFrame
      stage="purchase"
      lead="Describe the purchase to check: which instrument, and the final weight it should have in the portfolio. Nothing is bought; this is a simulation."
    >
      <Panel title="Purchase request">
        <div className="space-y-5">
          <div className="grid gap-5 md:grid-cols-2">
            <Field htmlFor={instrumentId} label="Instrument to buy" hint="Only instruments this simulation holds data for." error={instrumentError}>
              <Select
                id={instrumentId}
                ref={instrumentRef}
                value={state.purchase.instrumentId}
                onChange={(event) => actions.setPurchase({ instrumentId: event.target.value })}
                aria-invalid={instrumentError ? true : undefined}
                aria-describedby={describedBy(instrumentId, { hint: true, error: Boolean(instrumentError) })}
              >
                <option value="">Choose an instrument</option>
                {instruments.map((instrument) => (
                  <option key={instrument.instrument_id} value={instrument.instrument_id}>
                    {instrument.instrument_id} — {instrument.name} ({assetTypeLabel(instrument.asset_type)})
                  </option>
                ))}
              </Select>
            </Field>

            <div className="space-y-1.5">
              <label htmlFor={targetId} className="block font-semibold text-ink">
                Final direct weight of this position
              </label>
              <p id={`${targetId}-hint`} className="text-sm text-ink-muted">
                The share of the whole portfolio the position should have <strong className="font-semibold text-ink">after</strong> the purchase — not
                the amount added. Held directly now: <span className="tabular">{formatFraction(preview.starting_direct)}</span>.
              </p>
              <div className="flex items-center gap-2">
                <input
                  id={targetId}
                  ref={targetRef}
                  type="text"
                  inputMode="decimal"
                  autoComplete="off"
                  value={state.purchase.targetText}
                  onChange={(event) => actions.setPurchase({ targetText: event.target.value })}
                  aria-invalid={targetError ? true : undefined}
                  aria-describedby={describedBy(targetId, { hint: true, error: Boolean(targetError) })}
                  className={cn(
                    "tabular min-h-11 w-28 rounded-md border border-line-strong bg-surface px-3 text-right text-lg font-semibold text-ink",
                    "aria-invalid:border-2 aria-invalid:border-fail",
                  )}
                />
                <span className="text-lg font-semibold text-ink" aria-hidden="true">
                  %
                </span>
              </div>
              {targetError ? (
                <p id={`${targetId}-error`} className="flex items-start gap-1.5 text-sm font-semibold text-fail">
                  <ErrorIcon size={16} className="mt-0.5 flex-none" />
                  <span>{targetError}</span>
                </p>
              ) : null}
            </div>
          </div>

          <Notice tone="info" title="How the purchase is funded">
            <p data-testid="funding-statement">{FUNDING_STATEMENT}</p>
          </Notice>

          <div aria-live="polite">
            {preview.request ? (
              <Facts className="sm:grid-cols-3">
                <Fact label="Final direct weight">
                  <span className="tabular text-xl font-bold">{formatFraction(preview.request.target_direct_weight)}</span>
                </Fact>
                <Fact label="Additional purchase">
                  <span className="tabular text-xl font-bold">{formatFraction(preview.additional)}</span>
                  <span className="block text-sm text-ink-muted">
                    final weight minus the <span className="tabular">{formatFraction(preview.starting_direct)}</span> held now
                  </span>
                </Fact>
                <Fact label="Cash after the purchase">
                  <span className="tabular text-xl font-bold" data-testid="cash-after">
                    {formatFraction(preview.cash_after)}
                  </span>
                  <span className="block text-sm text-ink-muted">
                    from <span className="tabular">{formatFraction(preview.cash_before)}</span> now
                  </span>
                </Fact>
              </Facts>
            ) : (
              <p className="text-ink-muted">Choose an instrument and a final weight to see the additional purchase and the cash left.</p>
            )}
          </div>

          {preview.insufficient_cash ? (
            <Notice tone="caution" title="Not feasible with cash alone" role="status">
              <p>
                The purchase needs more cash than the portfolio holds: cash after the purchase would be{" "}
                <span className="tabular font-semibold">{formatFraction(preview.cash_after)}</span>. This is a feasibility result, reported separately
                from the rule results. Selling other positions is not part of this simulation.
              </p>
            </Notice>
          ) : null}
        </div>
      </Panel>

      <Panel title="Portfolio before and after" description={FUNDING_STATEMENT}>
        {preview.request ? (
          <BeforeAfterTable rows={preview.rows} />
        ) : (
          <EmptyBlock title="Nothing to compare yet">
            <p>The before and after columns appear once the request above is complete.</p>
          </EmptyBlock>
        )}
      </Panel>

      <Panel title="Rules the purchase will be checked against" eyebrow={policy ? `Confirmed policy — version ${policy.policy_version}` : undefined}>
        {policy ? (
          <ul className="list-disc space-y-1 pl-5 text-ink" data-testid="purchase-policy-rules">
            {active.map((rule) => (
              <li key={rule.rule_id} className="tabular">
                {ruleSummary(rule)}
              </li>
            ))}
          </ul>
        ) : (
          <EmptyBlock
            title="No confirmed rule yet"
            action={
              <LinkButton href={stageHref("goals")} size="sm">
                Go to Goals &amp; rules
              </LinkButton>
            }
          >
            <p>A purchase is checked against confirmed rules only. Confirm at least one rule first.</p>
          </EmptyBlock>
        )}
      </Panel>

      <div className="space-y-3">
        {state.start.status === "error" ? (
          <ErrorBlock title="The investigation could not be started" message={state.start.error ?? "The request failed."} onRetry={() => void start()}>
            <p>No investigation was created.</p>
          </ErrorBlock>
        ) : null}
        {state.investigationIds.length > 0 ? (
          <p className="text-ink-muted">
            {state.investigationIds.length === 1 ? "One investigation has" : `${state.investigationIds.length} investigations have`} already run in this
            session. Starting again creates a new one; earlier reports stay available.
          </p>
        ) : null}
        <div className="flex flex-wrap items-center gap-3">
          <Button
            variant="primary"
            softDisabled={!canStart}
            busy={starting}
            busyLabel="Starting the investigation…"
            iconAfter={<ArrowRightIcon />}
            onClick={() => void start()}
            data-testid="start-investigation"
          >
            Start the investigation
          </Button>
          <p className="text-sm text-ink-muted" role="status">
            {canStart
              ? "Runs the check against the confirmed policy and shows each step as it completes."
              : !policy
                ? "Needs at least one confirmed rule."
                : attempted
                  ? "The request above is not complete yet."
                  : "Needs an instrument and a final weight."}
          </p>
        </div>
      </div>
    </StageFrame>
  );
}
