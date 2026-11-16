"use client";

import { useEffect, useId, useRef, useState } from "react";
import { PurchaseExposureExplorerSlot } from "@/components/exposure3d/ExposureExplorerSlots";
import { FeasibilityTable } from "@/components/portfolio/FeasibilityTable";
import { StageFrame } from "@/components/shell/StageFrame";
import { EmptyBlock, ErrorBlock, LoadingBlock } from "@/components/ui/AsyncStates";
import { Badge } from "@/components/ui/Badge";
import { Button, LinkButton } from "@/components/ui/Button";
import { describedBy, Field, Select } from "@/components/ui/Field";
import { ArrowRightIcon, ErrorIcon } from "@/components/ui/icons";
import { Notice } from "@/components/ui/Notice";
import { Panel } from "@/components/ui/Panel";
import { ExecutionState } from "@/components/verdict/ExecutionState";
import { useDebouncedPreview } from "@/hooks/useDebouncedPreview";
import { describeError, isApiError } from "@/lib/api";
import { cn } from "@/lib/cn";
import type { CheckResult, CustomPortfolio, Policy, PurchaseRequest } from "@/lib/contracts";
import { CUSTOMIZED_LABEL, withCustomPortfolio } from "@/lib/customize";
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
export const PURCHASE_PREVIEW_LABEL = "Preview: computed by the service for the request above";

interface FeasibilityInput {
  request: PurchaseRequest;
  policy: Policy;
  /** The applied customization the preview is for, or null for the scenario portfolio. */
  customPortfolio: CustomPortfolio | null;
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
  // The one value that is both shown (through `effectivePortfolio`) and sent with every check.
  const customPortfolio = derived.customPortfolio;
  const startingPortfolio = derived.effectivePortfolio;
  const data = state.portfolio.data;
  const personaId = state.personaId;
  const form = usePurchaseForm();
  const request = form.request;

  // The figures of a purchase are the service's: POST /check on the stored policy, debounced, latest answer only.
  const preview = useDebouncedPreview<FeasibilityInput, CheckResult>(async (input, signal) => {
    if (!personaId) throw new Error("No persona is selected.");
    return api.check(
      withCustomPortfolio(
        { persona_id: personaId, policy_id: input.policy.policy_id, policy_version: input.policy.version, purchase_request: input.request, draft_rules: null },
        input.customPortfolio,
      ),
      { signal },
    );
  }, timing.previewDebounceMs);
  const { schedule, clear } = preview;
  // The preview is asked again whenever the request, the policy or the customized portfolio changes: a
  // preview of the earlier weights is dropped, never left on screen for the new ones.
  useEffect(() => {
    if (request && policy) schedule({ request, policy, customPortfolio });
    else clear();
  }, [request, policy, customPortfolio, schedule, clear]);

  if (state.portfolio.status !== "ready" || !data || !startingPortfolio) {
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
  const held = state.purchase.instrumentId === "" ? null : heldWeight(startingPortfolio, state.purchase.instrumentId);
  const starting = state.start.status === "loading";
  const canStart = request !== null && policy !== null;
  const active = activeRules(policy);

  const assessment = preview.status === "ready" ? assessResult(preview.result) : null;
  const previewed = assessment?.kind === "ok" ? assessment.result : null;
  const notRecorded = preview.status === "error" && isApiError(preview.error) && preview.error.kind === "no_fixture";
  // The preview is the engine's answer to this same request. When it says the request cannot be evaluated,
  // the service refuses to start an investigation of it for the same reason (contract section 6, rule 3).
  const previewRefusal = assessment?.kind === "not_executed" && assessment.result.execution.status === "INVALID_REQUEST" ? assessment.result.execution : null;
  // 400, 404, 409 and 422 are answers to the request as it was sent: sent again unchanged, it is refused again.
  const startRefused = state.start.kind === "validation" || state.start.kind === "not_found";
  // The same holds for a preview: what the service refused, it refuses again, so no retry is offered for it.
  const previewError = preview.status === "error" && !notRecorded ? preview.error : null;
  const previewIssues = isApiError(previewError) ? previewError.details.map((detail) => detail.issue) : [];
  const previewRefused = isApiError(previewError) && (previewError.kind === "validation" || previewError.kind === "not_found");

  async function start() {
    setAttempted(true);
    if (!request) {
      (problem?.field === "instrument" ? instrumentRef.current : targetRef.current)?.focus();
      return;
    }
    if (!policy) return;
    const id = await actions.startInvestigation(request);
    if (id) goToStage("verdict");
  }

  return (
    <StageFrame
      stage="purchase"
      lead="Choose an investment and its target share. We’ll check it against your confirmed limits."
    >
      {!policy ? (
        <Notice tone="info" title="First, confirm your limits" action={<LinkButton href={stageHref("goals")} variant="primary">Set my limits</LinkButton>}>
          <p>Choose what matters to you before checking an idea.</p>
        </Notice>
      ) : <p className="text-sm text-ink-muted">{active.length} confirmed limits · <LinkButton href={stageHref("goals")} variant="quiet" size="sm">Review limits</LinkButton></p>}
      <Panel title="What would you like to try?" figures>
        <div className="space-y-5">
          {customPortfolio ? (
            <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-ink" data-testid="purchase-portfolio-note">
              <span data-testid="customized-badge">
                <Badge tone="accent" dashed>
                  {CUSTOMIZED_LABEL}
                </Badge>
              </span>
              <span>
                This idea is checked against the weights you entered in step 1, not against {scenario.persona.display_name}&rsquo;s original fictional
                portfolio.
              </span>
            </p>
          ) : null}
          {scenario.demo_requests.length > 0 ? (
            <details className="rounded-md border border-line bg-canvas p-3" data-testid="scenario-requests">
              <summary className="cursor-pointer text-sm font-semibold text-ink-muted">Try an example</summary>
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
            </details>
          ) : null}

          <div className="grid gap-5 md:grid-cols-2">
            <Field htmlFor={instrumentId} label="Which investment?" hint="Only supported investments are listed." error={instrumentError}>
              <Select
                id={instrumentId}
                ref={instrumentRef}
                value={state.purchase.instrumentId}
                onChange={(event) => actions.setPurchase({ instrumentId: event.target.value })}
                aria-invalid={instrumentError ? true : undefined}
                aria-describedby={describedBy(instrumentId, { hint: true, error: Boolean(instrumentError) })}
              >
                <option value="">Choose an investment</option>
                {purchasable.map((id) => {
                  const instrument = instruments[id];
                  return (
                    <option key={id} value={id}>
                      {id}: {instrumentName(instruments, id)}
                      {instrument ? ` (${assetClassLabel(instrument.asset_class)})` : ""}
                    </option>
                  );
                })}
              </Select>
            </Field>

            <div className="space-y-1.5">
              <label htmlFor={targetId} className="block font-semibold text-ink">
                Share of the portfolio after buying
              </label>
              <p id={`${targetId}-hint`} className="text-sm text-ink-muted">
                Total share <strong className="font-semibold text-ink">after</strong> buying, including what you already hold.{" "}
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

          <p className="text-sm text-ink-muted" data-testid="funding-statement">{FUNDING_STATEMENT}</p>
      <div className="space-y-3">
        {state.start.status === "error" ? (
          state.start.kind === "no_fixture" ? (
            <Notice tone="info" role="alert" title="The test data holds no investigation of this request">
              <p data-testid="start-not-recorded">{state.start.error}</p>
              <p>No investigation was created.</p>
            </Notice>
          ) : (
            <ErrorBlock
              title="The investigation could not be started"
              message={state.start.error ?? "The request failed."}
              onRetry={startRefused ? undefined : () => void start()}
            >
              {state.start.issues.length > 0 ? (
                <ul className="list-disc space-y-1 pl-5" data-testid="start-issues">
                  {state.start.issues.map((issue, index) => (
                    <li key={`${index}-${issue}`}>{issue}</li>
                  ))}
                </ul>
              ) : null}
              <p>No investigation was created.</p>
              {startRefused ? (
                <p data-testid="start-refused">The service refused the request as it was sent, so sending it again unchanged would be refused again. Change it above, then start again.</p>
              ) : null}
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
            busyLabel="Checking your idea…"
            iconAfter={<ArrowRightIcon />}
            onClick={() => void start()}
            data-testid="start-investigation"
          >
            Check my idea
          </Button>
          <p className="text-sm text-ink-muted" role="status">
            {canStart && previewRefusal ? (
              <span data-testid="start-preview-refusal">
                The preview above says this request cannot be evaluated{previewRefusal.code ? ` (${previewRefusal.code})` : ""}. Started as it is, it is refused for the
                same reason and no investigation is created. Change the request first.
              </span>
            ) : canStart
              ? "Checks your limits. No trade is placed."
              : !policy
                ? "Needs at least one confirmed rule."
                : attempted
                  ? "The request above is not complete yet."
                  : "Needs an instrument and a final weight."}
          </p>
        </div>
      </div>
        </div>
      </Panel>

      <Panel collapsible title="Preview cash and exposures" eyebrow="Preview" figures={previewed !== null} description={FUNDING_STATEMENT}>
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

          {previewError !== null ? (
            <Notice
              tone="error"
              title="The preview could not be calculated"
              action={
                request && policy && !previewRefused ? (
                  <Button size="sm" onClick={() => schedule({ request, policy, customPortfolio })}>
                    Try again
                  </Button>
                ) : undefined
              }
            >
              <p data-testid="purchase-preview-error">{describeError(previewError)}</p>
              {previewIssues.length > 0 ? (
                <ul className="list-disc space-y-1 pl-5" data-testid="purchase-preview-issues">
                  {previewIssues.map((issue, index) => (
                    <li key={`${index}-${issue}`}>{issue}</li>
                  ))}
                </ul>
              ) : null}
              {previewRefused ? (
                <p data-testid="purchase-preview-refused">
                  No figure is shown rather than a guessed one. The service refused the request as it was sent, so sending it again unchanged would be
                  refused again, and an investigation of it would be refused for the same reason. Change the request above, or the portfolio in step 1.
                </p>
              ) : (
                <p>No figure is shown rather than a guessed one. The investigation can still be started.</p>
              )}
            </Notice>
          ) : null}
        </div>

        <PurchaseExposureExplorerSlot result={previewed} />
      </Panel>

      <Panel collapsible title="Review your confirmed limits"  figures={policy !== null}>
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
                Set your limits
              </LinkButton>
            }
          >
            <p>A purchase is checked against confirmed rules only. Confirm at least one rule first.</p>
          </EmptyBlock>
        )}
      </Panel>


    </StageFrame>
  );
}
