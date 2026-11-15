"use client";

import { useEffect, useId, useRef, useState } from "react";
import { PurchaseExposureExplorerSlot } from "@/components/exposure3d/ExposureExplorerSlots";
import { FeasibilityTable } from "@/components/portfolio/FeasibilityTable";
import { StageFrame } from "@/components/shell/StageFrame";
import { EmptyBlock, ErrorBlock, LoadingBlock } from "@/components/ui/AsyncStates";
import { Button, LinkButton } from "@/components/ui/Button";
import { describedBy, Field, Select } from "@/components/ui/Field";
import { ArrowRightIcon, ErrorIcon } from "@/components/ui/icons";
import { Notice } from "@/components/ui/Notice";
import { Fact, Facts, Panel } from "@/components/ui/Panel";
import { ExecutionState } from "@/components/verdict/ExecutionState";
import { useDebouncedPreview } from "@/hooks/useDebouncedPreview";
import { describeError, isApiError } from "@/lib/api";
import { cn } from "@/lib/cn";
import type { CheckResult, Policy, PurchaseRequest } from "@/lib/contracts";
import { formatFraction, fractionToPercentInput, percentInputToFraction } from "@/lib/format";
import { assetClassLabel, FUNDING_STATEMENT, heldWeight, instrumentName } from "@/lib/portfolio";
import { assessResult } from "@/lib/result";
import { ruleSummary } from "@/lib/rules";
import { activeRules } from "@/lib/verdict";
import { usePurchaseForm } from "@/state/purchase";
import { useRuntime } from "@/state/runtime";
import { goToStage, stageHref } from "@/state/stage";
import { useWorkflow } from "@/state/workflow";

/** The label of every figure shown before the investigation has run. */
export const PURCHASE_PREVIEW_LABEL = "Preview — computed by the service for the request above";

interface FeasibilityInput {
  request: PurchaseRequest;
  policy: Policy;
}

/** Stage 3: the purchase as an instrument and the FINAL direct weight it should have. */
export function PurchaseStage() {
  const { state, actions, derived } = useWorkflow();
  const { api, timing } = useRuntime();
  const instrumentId = useId();
  const targetId = useId();
  const instrumentRef = useRef<HTMLSelectElement>(null);
  const targetRef = useRef<HTMLInputElement>(null);
  const [attempted, setAttempted] = useState(false);

  const policy = derived.currentPolicy;
  const data = state.portfolio.data;
  const personaId = state.personaId;
  const form = usePurchaseForm();
  const request = form.request;

  // The figures of a purchase are the service's: POST /check on the stored policy, debounced, latest answer only.
  const preview = useDebouncedPreview<FeasibilityInput, CheckResult>(async (input, signal) => {
    if (!personaId) throw new Error("No persona is selected.");
    return api.check(
      { persona_id: personaId, policy_id: input.policy.policy_id, policy_version: input.policy.version, purchase_request: input.request, draft_rules: null },
      { signal },
    );
  }, timing.previewDebounceMs);
  const { schedule, clear } = preview;
  useEffect(() => {
    if (request && policy) schedule({ request, policy });
    else clear();
  }, [request, policy, schedule, clear]);

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

  const { scenario, instruments, purchasable_instrument_ids: purchasable } = data;
  const targetMalformed = state.purchase.targetText.trim() !== "" && percentInputToFraction(state.purchase.targetText) === null;
  const problem = form.problem;
  // A field left empty is not an error until the user tries to start.
  const showProblem = problem !== null && (attempted || (problem.code !== "NO_INSTRUMENT" && problem.code !== "NO_TARGET"));
  const instrumentError = showProblem && problem.field === "instrument" ? problem.message : null;
  const targetError = targetMalformed ? "Enter a number such as 25 or 12.5." : showProblem && problem.field === "target" ? problem.message : null;
  const held = state.purchase.instrumentId === "" ? null : heldWeight(scenario.portfolio, state.purchase.instrumentId);
  const starting = state.start.status === "loading";
  const canStart = request !== null && policy !== null;
  const active = activeRules(policy);

  const assessment = preview.status === "ready" ? assessResult(preview.result) : null;
  const previewed = assessment?.kind === "ok" ? assessment.result : null;
  const notRecorded = preview.status === "error" && isApiError(preview.error) && preview.error.kind === "no_fixture";

  async function start() {
    setAttempted(true);
    if (!request) {
      (problem?.field === "instrument" ? instrumentRef.current : targetRef.current)?.focus();
      return;
    }
    if (!policy) return;
    const id = await actions.startInvestigation(request);
    if (id) goToStage("investigation");
  }

  return (
    <StageFrame
      stage="purchase"
      lead="Describe the purchase to check: which instrument, and the final weight it should have in the portfolio. Nothing is bought; this is a simulation."
    >
      <Panel title="Purchase request" figures>
        <div className="space-y-5">
          {scenario.demo_requests.length > 0 ? (
            <div className="rounded-md border border-line bg-canvas p-3" data-testid="scenario-requests">
              <p className="text-sm font-semibold text-ink-muted">Requests written for this fictional scenario</p>
              <ul className="mt-1 space-y-2">
                {scenario.demo_requests.map((demo) => {
                  const inForm = request?.instrument_id === demo.purchase_request.instrument_id && request.target_direct_weight === demo.purchase_request.target_direct_weight;
                  return (
                    <li key={demo.request_id} className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1">
                      <span className="text-ink">
                        {demo.purchase_request.original_words ? <>&ldquo;{demo.purchase_request.original_words}&rdquo; </> : null}
                        <span className="text-sm text-ink-muted">{demo.label}.</span>
                      </span>
                      {inForm ? (
                        <span className="text-sm font-semibold text-accent-strong">In the form below</span>
                      ) : (
                        <Button
                          size="sm"
                          onClick={() =>
                            actions.setPurchase({
                              instrumentId: demo.purchase_request.instrument_id,
                              targetText: fractionToPercentInput(demo.purchase_request.target_direct_weight),
                            })
                          }
                        >
                          Fill in this request
                        </Button>
                      )}
                    </li>
                  );
                })}
              </ul>
            </div>
          ) : null}

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
                {purchasable.map((id) => {
                  const instrument = instruments[id];
                  return (
                    <option key={id} value={id}>
                      {id} — {instrumentName(instruments, id)}
                      {instrument ? ` (${assetClassLabel(instrument.asset_class)})` : ""}
                    </option>
                  );
                })}
              </Select>
            </Field>

            <div className="space-y-1.5">
              <label htmlFor={targetId} className="block font-semibold text-ink">
                Final direct weight of this position
              </label>
              <p id={`${targetId}-hint`} className="text-sm text-ink-muted">
                The share of the whole portfolio the position should have <strong className="font-semibold text-ink">after</strong> the purchase — not
                the amount added.{" "}
                {state.purchase.instrumentId === "" ? null : (
                  <span data-testid="held-now">
                    Held directly now: {held === null ? "nothing" : <span className="tabular">{formatFraction(held)}</span>}.
                  </span>
                )}
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
            {request ? (
              <Facts>
                <Fact label="Final direct weight you entered">
                  <span className="tabular text-xl font-bold" data-testid="entered-target">
                    {formatFraction(request.target_direct_weight)}
                  </span>{" "}
                  <span className="text-ink-muted">in {request.instrument_id}</span>
                </Fact>
                <Fact label="Amount added and cash left">
                  <span data-testid="figures-after-check">
                    Computed by the service, not by this page: they appear as a preview below once the service answers, and in the report after the
                    check.
                  </span>
                </Fact>
              </Facts>
            ) : (
              <p className="text-ink-muted">Choose an instrument and a final weight. The amount added and the cash left are then computed by the service.</p>
            )}
          </div>
        </div>
      </Panel>

      <Panel title="Effect on the position and on cash" eyebrow="Preview" figures={previewed !== null} description={FUNDING_STATEMENT}>
        <div role="status" aria-live="polite" className="space-y-4" data-testid="purchase-preview" data-preview-status={preview.status}>
          {!request ? (
            <EmptyBlock title="Nothing to preview yet">
              <p>The figures appear once the request above is complete.</p>
            </EmptyBlock>
          ) : !policy ? (
            <EmptyBlock title="No preview without a confirmed policy">
              <p>The service checks a purchase against a confirmed policy. Confirm at least one rule first; the figures also appear in the report after the check.</p>
            </EmptyBlock>
          ) : null}

          {preview.status === "waiting" || preview.status === "loading" ? <LoadingBlock label="Asking the service what this purchase does to the position and to cash…" /> : null}

          {previewed?.feasibility ? (
            <>
              <p className="text-sm font-semibold text-ink" data-testid="purchase-preview-label">
                {PURCHASE_PREVIEW_LABEL}
              </p>
              <FeasibilityTable
                feasibility={previewed.feasibility}
                purchase={previewed.purchase_request}
                instrumentName={instrumentName(instruments, previewed.purchase_request.instrument_id)}
              />
              {previewed.feasibility.status === "INSUFFICIENT_CASH" ? (
                <Notice tone="caution" title="Not feasible with cash alone">
                  <p>
                    The service reports that this purchase needs more cash than the portfolio holds: cash after the purchase would be{" "}
                    <span className="tabular font-semibold">{formatFraction(previewed.feasibility.cash_after)}</span>. This is a feasibility result,
                    reported separately from the rule results. Selling other positions is not part of this simulation.
                  </p>
                </Notice>
              ) : (
                <p className="text-sm text-ink-muted">
                  The service reports enough cash for this purchase. Whether it respects your rules is the result of the investigation, not of this
                  preview.
                </p>
              )}
            </>
          ) : null}

          {assessment?.kind === "not_executed" ? <ExecutionState execution={assessment.result.execution} context="preview" /> : null}

          {assessment?.kind === "unreadable" ? (
            <Notice tone="caution" title="The preview could not be read">
              <p>The service sent an answer this page does not understand. Nothing is shown in its place.</p>
            </Notice>
          ) : null}

          {notRecorded ? (
            <Notice tone="info" title="No preview for this request in the test data">
              <p data-testid="purchase-preview-not-recorded">{describeError(preview.error)}</p>
              <p>The figures appear in the report after the check.</p>
            </Notice>
          ) : null}

          {preview.status === "error" && !notRecorded ? (
            <Notice
              tone="error"
              title="The preview could not be calculated"
              action={
                request && policy ? (
                  <Button size="sm" onClick={() => schedule({ request, policy })}>
                    Try again
                  </Button>
                ) : undefined
              }
            >
              <p data-testid="purchase-preview-error">{describeError(preview.error)}</p>
              <p>No figure is shown rather than a guessed one. The investigation can still be started.</p>
            </Notice>
          ) : null}
        </div>

        <PurchaseExposureExplorerSlot result={previewed} />
      </Panel>

      <Panel title="Rules the purchase will be checked against" eyebrow={policy ? `Confirmed policy — version ${policy.version}` : undefined} figures={policy !== null}>
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
          state.start.kind === "no_fixture" ? (
            <Notice tone="info" role="alert" title="The test data holds no investigation of this request">
              <p data-testid="start-not-recorded">{state.start.error}</p>
              <p>No investigation was created.</p>
            </Notice>
          ) : (
            <ErrorBlock title="The investigation could not be started" message={state.start.error ?? "The request failed."} onRetry={() => void start()}>
              <p>No investigation was created.</p>
            </ErrorBlock>
          )
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
