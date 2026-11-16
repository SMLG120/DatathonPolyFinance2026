"use client";

import { useCallback, useEffect } from "react";
import { RuleMeasure } from "@/components/verdict/RuleMeasure";
import { StatusBadge } from "@/components/ui/Badge";
import { ErrorIcon, InfoIcon } from "@/components/ui/icons";
import { TestDataTag } from "@/components/ui/TestDataTag";
import { useDebouncedPreview, type DebouncedPreview } from "@/hooks/useDebouncedPreview";
import { describeError, isApiError } from "@/lib/api";
import { canonical } from "@/lib/canonical";
import type { CheckResult, CustomPortfolio, PersonaId, Policy, PurchaseRequest, Rule, RuleType } from "@/lib/contracts";
import { withCustomPortfolio } from "@/lib/customize";
import { formatFraction, percentInputToFraction } from "@/lib/format";
import { describePurchase } from "@/lib/portfolio";
import { assessResult } from "@/lib/result";
import { limitNoun, ruleTypeLabel, validateThreshold } from "@/lib/rules";
import { useRuntime } from "@/state/runtime";
import { t, tf } from "@/lib/i18n";

/** The label every preview carries. A preview is never the confirmed result. */
export const PREVIEW_LABEL = "Preview with draft threshold: not your confirmed policy";

export interface DraftInput {
  threshold: number;
}

export type DraftPreviewState = DebouncedPreview<DraftInput, CheckResult>;

export interface UseDraftPreviewOptions {
  personaId: PersonaId | null;
  /** The stored policy version the drafts would stand in for, when there is one. */
  policy: Policy | null;
  /** The purchase the draft is tried on. A check always needs one; without it nothing is previewed. */
  purchase: PurchaseRequest | null;
  /**
   * The customized fictional portfolio the draft is tried on, or null for the persona's scenario portfolio.
   * Required, so that every caller says which portfolio its preview is about: the applied customization
   * for a rule not yet confirmed, the portfolio of the report for a rule change against that report.
   */
  customPortfolio: CustomPortfolio | null;
  /** The full rule set to evaluate, with the draft threshold applied to the rule being edited. */
  buildRules: (threshold: number) => Rule[];
}

/**
 * Debounced POST /check, with `draft_rules`, for a threshold that is still
 * being typed.
 *
 * The answer stays inside this hook: it is never written to the policy, to a
 * report or to the workflow store, so a preview cannot replace a confirmed
 * result. Answers for an older draft are dropped (see useDebouncedPreview).
 */
export function useDraftPreview({ personaId, policy, purchase, customPortfolio, buildRules }: UseDraftPreviewOptions): {
  preview: DraftPreviewState;
  /** Call with the field's text on every change. */
  onDraftChange: (text: string) => void;
} {
  const { api, timing } = useRuntime();
  const preview = useDebouncedPreview<DraftInput, CheckResult>(async (input, signal) => {
    if (!personaId || !purchase) throw new Error(t("A preview needs a persona and a purchase."));
    return api.check(
      withCustomPortfolio(
        {
          persona_id: personaId,
          policy_id: policy?.policy_id ?? null,
          policy_version: policy?.version ?? null,
          purchase_request: purchase,
          draft_rules: buildRules(input.threshold),
        },
        customPortfolio,
      ),
      { signal },
    );
  }, timing.previewDebounceMs);

  const { schedule, clear } = preview;
  // A preview belongs to the portfolio it was asked for. When that portfolio changes, the preview on screen
  // and any call in flight are dropped, so a figure for the earlier weights is never shown for the new ones.
  const portfolioKey = canonical(customPortfolio);
  useEffect(() => {
    clear();
  }, [portfolioKey, clear]);
  const canPreview = personaId !== null && purchase !== null;
  const onDraftChange = useCallback(
    (text: string) => {
      const threshold = percentInputToFraction(text);
      if (!canPreview || threshold === null || validateThreshold(threshold) !== null) clear();
      else schedule({ threshold });
    },
    [schedule, clear, canPreview],
  );

  return { preview, onDraftChange };
}

export interface DraftPreviewPanelProps {
  preview: DraftPreviewState;
  ruleId: string;
  ruleType: RuleType;
  /** The purchase the draft is tried on, or null when none has been entered yet. */
  purchase: PurchaseRequest | null;
}

/** Shows a preview and nothing else. Dashed and labelled so it cannot be mistaken for a confirmed result. */
export function DraftPreviewPanel({ preview, ruleId, ruleType, purchase }: DraftPreviewPanelProps) {
  const noun = limitNoun(ruleType).toLowerCase();
  const draftText = preview.input ? formatFraction(preview.input.threshold) : "";
  const assessment = preview.status === "ready" ? assessResult(preview.result) : null;
  const ruleResult = assessment?.kind === "ok" ? assessment.result.rule_results.find((result) => result.rule_id === ruleId) : undefined;
  const notRecorded = preview.status === "error" && isApiError(preview.error) && preview.error.kind === "no_fixture";

  return (
    // A named group, not a landmark: there is one of these per rule card, and landmarks must be few and uniquely named.
    <div
      role="group"
      aria-label={tf("Draft preview: {rule}", { rule: ruleTypeLabel(ruleType) })}
      className="rounded-md border border-dashed border-line-strong bg-sunken p-3 sm:p-4"
      data-testid="draft-preview"
      data-figures={preview.status === "ready" ? "true" : undefined}
    >
      <p className="flex flex-wrap items-center gap-2 text-sm font-semibold text-ink">
        {t(PREVIEW_LABEL)}
        {preview.status === "ready" ? <TestDataTag /> : null}
      </p>

      {preview.status === "idle" ? (
        <p className="mt-1 text-sm text-ink-muted">
          {purchase
            ? tf("Change the number to see how the portfolio after the purchase entered in stage 3 ({purchase}) compares with it. A preview is never saved; it changes no confirmed rule and no report.", { purchase: describePurchase(purchase) })
            : t("A preview tries a number on a purchase. Enter a purchase in stage 3 first; until then nothing is previewed.")}
        </p>
      ) : null}

      {preview.status === "waiting" || preview.status === "loading" ? (
        <p className="mt-1 text-sm text-ink-muted" data-testid="draft-preview-pending">
          {t("Asking the service for a preview with a draft")} {noun} {t("of")} <span className="tabular font-semibold text-ink">{draftText}</span>…
        </p>
      ) : null}

      {/* Only finished previews are announced, so typing is not interrupted by progress messages. */}
      <div role="status" aria-live="polite">
        {assessment?.kind === "ok" ? (
          ruleResult ? (
            <div className="mt-2 space-y-2" data-testid="draft-preview-result">
              <p className="flex flex-wrap items-center gap-x-3 gap-y-1">
                <StatusBadge status={ruleResult.status} prefix="Preview:" />
                <span className="text-ink">
                  {t("draft")} {noun} <span className="tabular font-semibold">{draftText}</span>
                  {purchase ? tf(", after {purchase}", { purchase: describePurchase(purchase) }) : ""}
                </span>
              </p>
              <RuleMeasure
                ruleType={ruleResult.rule_type}
                status={ruleResult.status}
                measured={ruleResult.measured}
                limit={ruleResult.limit}
                gap={ruleResult.gap}
                unknownCauses={ruleResult.unknown_causes}
              />
              <p className="text-sm text-ink-muted">{ruleResult.reason}</p>
            </div>
          ) : (
            <p className="mt-1 text-sm text-ink">{t("The preview returned no result for this rule, so nothing can be shown for this draft.")}</p>
          )
        ) : null}

        {assessment?.kind === "not_executed" ? (
          <p className="mt-2 flex items-start gap-1.5 text-sm text-ink" data-testid="draft-preview-not-executed">
            <InfoIcon size={16} className="mt-0.5 flex-none text-ink-muted" />
            <span>
              <span className="font-semibold">{t("The service could not evaluate this request, so there is no preview.")}</span>{" "}
              {assessment.result.execution.message}
            </span>
          </p>
        ) : null}

        {assessment?.kind === "unreadable" ? (
          <p className="mt-2 text-sm text-ink" data-testid="draft-preview-unreadable">
            {t("The service sent a preview this page could not read. Nothing is shown in its place.")}</p>
        ) : null}

        {notRecorded ? (
          <p className="mt-2 flex items-start gap-1.5 text-sm text-ink" data-testid="draft-preview-not-recorded">
            <InfoIcon size={16} className="mt-0.5 flex-none text-ink-muted" />
            <span>
              <span className="font-semibold">{t("No preview for this draft value in the test data.")}</span> {describeError(preview.error)} {t("Your confirmed rules and reports are unchanged.")}</span>
          </p>
        ) : null}

        {preview.status === "error" && !notRecorded ? (
          <p className="mt-2 flex items-start gap-1.5 text-sm text-ink" data-testid="draft-preview-error">
            <ErrorIcon size={16} className="mt-0.5 flex-none text-fail" />
            <span>
              <span className="font-semibold">{t("The preview could not be calculated.")}</span> {describeError(preview.error)} {t("Your confirmed rules and reports are unchanged.")}</span>
          </p>
        ) : null}
      </div>
    </div>
  );
}
