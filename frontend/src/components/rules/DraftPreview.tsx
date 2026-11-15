"use client";

import { useCallback } from "react";
import { StatusBadge } from "@/components/ui/Badge";
import { ErrorIcon } from "@/components/ui/icons";
import { useDebouncedPreview, type DebouncedPreview } from "@/hooks/useDebouncedPreview";
import { describeError } from "@/lib/api";
import type { CheckResult, PersonaId, PurchaseRequest, Rule, RuleType } from "@/lib/contracts";
import { formatFraction, formatFractionRange, formatGap, percentInputToFraction } from "@/lib/format";
import { limitNoun, ruleDirection, ruleTypeLabel, validateThreshold } from "@/lib/rules";
import { decisiveEvaluation } from "@/lib/verdict";
import { useRuntime } from "@/state/runtime";

/** The label every preview carries. A preview is never the confirmed result. */
export const PREVIEW_LABEL = "Preview with draft threshold — not your confirmed policy";

export interface DraftInput {
  threshold: number;
}

export type DraftPreviewState = DebouncedPreview<DraftInput, CheckResult>;

export interface UseDraftPreviewOptions {
  personaId: PersonaId | null;
  /** Null previews the current portfolio; a purchase previews the portfolio after it. */
  purchase: PurchaseRequest | null;
  /** The full rule set to evaluate, with the draft threshold applied to the rule being edited. */
  buildRules: (threshold: number) => Rule[];
}

/**
 * Debounced POST /check for a threshold that is still being typed.
 *
 * The answer stays inside this hook: it is never written to the policy, to a
 * report or to the workflow store, so a preview cannot replace a confirmed
 * result. Answers for an older draft are dropped (see useDebouncedPreview).
 */
export function useDraftPreview({ personaId, purchase, buildRules }: UseDraftPreviewOptions): {
  preview: DraftPreviewState;
  /** Call with the field's text on every change. */
  onDraftChange: (text: string) => void;
} {
  const { api, timing } = useRuntime();
  const preview = useDebouncedPreview<DraftInput, CheckResult>(async (input, signal) => {
    if (!personaId) throw new Error("No persona is selected.");
    const response = await api.check({ persona_id: personaId, purchase, rules: buildRules(input.threshold), is_draft_preview: true }, { signal });
    return response.result;
  }, timing.previewDebounceMs);

  const { schedule, clear } = preview;
  const onDraftChange = useCallback(
    (text: string) => {
      const threshold = percentInputToFraction(text);
      if (threshold === null || validateThreshold(threshold) !== null) clear();
      else schedule({ threshold });
    },
    [schedule, clear],
  );

  return { preview, onDraftChange };
}

export interface DraftPreviewPanelProps {
  preview: DraftPreviewState;
  ruleId: string;
  ruleType: RuleType;
  /** What the draft is measured on: "the current portfolio" or "the portfolio after the purchase". */
  subject: string;
}

/** Shows a preview and nothing else. Dashed and labelled so it cannot be mistaken for a confirmed result. */
export function DraftPreviewPanel({ preview, ruleId, ruleType, subject }: DraftPreviewPanelProps) {
  const noun = limitNoun(ruleType).toLowerCase();
  const draftText = preview.input ? formatFraction(preview.input.threshold) : "";
  const ruleResult = preview.result?.rule_results.find((r) => r.rule_id === ruleId);
  const evaluation = ruleResult ? decisiveEvaluation(ruleResult) : null;

  return (
    // A named group, not a landmark: there is one of these per rule card, and landmarks must be few and uniquely named.
    <div
      role="group"
      aria-label={`Draft preview: ${ruleTypeLabel(ruleType)}`}
      className="rounded-md border border-dashed border-line-strong bg-sunken p-3 sm:p-4"
      data-testid="draft-preview"
    >
      <p className="text-sm font-semibold text-ink">{PREVIEW_LABEL}</p>

      {preview.status === "idle" ? (
        <p className="mt-1 text-sm text-ink-muted">
          Change the threshold to see how {subject} compares with it. A preview is never saved; it changes no confirmed rule and no report.
        </p>
      ) : null}

      {preview.status === "waiting" || preview.status === "loading" ? (
        <p className="mt-1 text-sm text-ink-muted" data-testid="draft-preview-pending">
          Calculating a preview for a draft {noun} of <span className="tabular font-semibold text-ink">{draftText}</span>…
        </p>
      ) : null}

      {/* Only finished previews are announced, so typing is not interrupted by progress messages. */}
      <div role="status" aria-live="polite">
        {preview.status === "ready" ? (
          evaluation ? (
            <div className="mt-2 space-y-1.5" data-testid="draft-preview-result">
              <p className="flex flex-wrap items-center gap-x-3 gap-y-1">
                <StatusBadge status={evaluation.status} prefix="Preview:" />
                <span className="text-ink">
                  draft {noun} <span className="tabular font-semibold">{draftText}</span>, measured on {subject}
                </span>
              </p>
              <p className="tabular text-ink">
                {evaluation.measured_label}: {evaluation.measured ? formatFractionRange(evaluation.measured.lower, evaluation.measured.upper) : "not measured"}
                {evaluation.gap !== null ? ` — ${formatGap(evaluation.gap, ruleDirection(ruleType)).toLowerCase()}` : ""}
              </p>
              <p className="text-sm text-ink-muted">{evaluation.reason}</p>
            </div>
          ) : (
            <p className="mt-1 text-sm text-ink">The preview returned no result for this rule, so nothing can be shown for this draft.</p>
          )
        ) : null}

        {preview.status === "error" ? (
          <p className="mt-2 flex items-start gap-1.5 text-sm text-ink" data-testid="draft-preview-error">
            <ErrorIcon size={16} className="mt-0.5 flex-none text-fail" />
            <span>
              <span className="font-semibold">The preview could not be calculated.</span> {describeError(preview.error)} Your confirmed rules and
              reports are unchanged.
            </span>
          </p>
        ) : null}
      </div>
    </div>
  );
}
