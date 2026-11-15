"use client";

import { useId, useRef, useState, type ReactNode } from "react";
import { Badge, RuleStatusBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { CheckIcon } from "@/components/ui/icons";
import type { Objective, PersonaId, Rule } from "@/lib/contracts";
import { cn } from "@/lib/cn";
import { percentInputToFraction } from "@/lib/format";
import {
  originDescription,
  originLabel,
  ruleStatusDescription,
  ruleTypeLabel,
  thresholdHint,
  thresholdLabel,
  thresholdText,
  validateThreshold,
  withRuleThreshold,
} from "@/lib/rules";
import { DraftPreviewPanel, useDraftPreview } from "./DraftPreview";
import { ThresholdInput } from "./ThresholdInput";

const WORDS_LABEL: Record<Rule["origin"], string> = {
  USER_STATED: "Your words",
  FICTIONAL_SCENARIO: "Words from the fictional scenario",
  SYSTEM_PROPOSED: "Your words that led to this proposal",
};

/** The parts every rule card shows, whatever its status: words, scope, origin, status and the linked objective. */
function RuleDetails({ rule, objective }: { rule: Rule; objective: Objective | undefined }) {
  return (
    <div className="space-y-4">
      <figure>
        <figcaption className="text-sm font-semibold text-ink-muted">{WORDS_LABEL[rule.origin]}</figcaption>
        <blockquote className="mt-1 border-l-4 border-line-strong pl-3 text-ink" data-testid="rule-original-words">
          &ldquo;{rule.original_words}&rdquo;
        </blockquote>
      </figure>
      {/* Each group is a direct child of the list: a <dl> may hold <div> groups, but not groups nested in a layout wrapper. */}
      <dl className="grid gap-3 sm:grid-cols-2">
        <div className="sm:col-span-2">
          <dt className="text-sm font-semibold text-ink-muted">Exactly what is checked</dt>
          <dd className="text-ink" data-testid="rule-scope">
            {rule.scope_description}
          </dd>
        </div>
        <div>
          <dt className="text-sm font-semibold text-ink-muted">Origin</dt>
          <dd className="text-ink">
            <span className="font-semibold">{originLabel(rule.origin)}.</span> {originDescription(rule.origin)}
          </dd>
        </div>
        <div>
          <dt className="text-sm font-semibold text-ink-muted">Status</dt>
          <dd className="text-ink">{ruleStatusDescription(rule.status)}</dd>
        </div>
        {objective ? (
          <div className="sm:col-span-2">
            <dt className="text-sm font-semibold text-ink-muted">Related objective — context only</dt>
            <dd className="text-ink">
              &ldquo;{objective.original_words}&rdquo;
              <span className="mt-0.5 block text-sm text-ink-muted">
                The link is context for reading results. The objective does not set this threshold and is never marked pass or fail.
              </span>
            </dd>
          </div>
        ) : null}
      </dl>
    </div>
  );
}

function RuleHeader({ rule, headingId, aside }: { rule: Rule; headingId: string; aside?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
      <h3 id={headingId} className="text-lg font-semibold text-ink">
        {ruleTypeLabel(rule.rule_type)}
      </h3>
      <div className="flex flex-wrap items-center gap-2">
        <RuleStatusBadge status={rule.status} />
        <Badge tone="neutral" dashed={rule.origin === "SYSTEM_PROPOSED"}>
          {originLabel(rule.origin)}
        </Badge>
        {aside}
      </div>
    </div>
  );
}

export interface ProposedRuleCardProps {
  rule: Rule;
  objective: Objective | undefined;
  personaId: PersonaId | null;
  /** The threshold field's text, as a percentage. "" = not set. */
  thresholdText: string;
  onThresholdChange: (text: string) => void;
  /** Confirms this rule with the threshold in the field. */
  onConfirm: () => void;
  confirming: boolean;
}

/**
 * A PROPOSED rule. It is inactive: nothing checks it until the user confirms
 * it, and it can only be confirmed with a threshold the user can see in the
 * field. A system-proposed rule arrives with an empty field.
 */
export function ProposedRuleCard({ rule, objective, personaId, thresholdText: text, onThresholdChange, onConfirm, confirming }: ProposedRuleCardProps) {
  const headingId = useId();
  const fieldId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const [attempted, setAttempted] = useState(false);

  const threshold = percentInputToFraction(text);
  const problem = text.trim() !== "" && threshold === null ? "Enter a number such as 10 or 12.5." : validateThreshold(threshold);
  const canConfirm = problem === null;
  // An empty field is not an error until the user tries to confirm it.
  const shownError = problem !== null && (attempted || text.trim() !== "") ? problem : null;

  const { preview, onDraftChange } = useDraftPreview({
    personaId,
    purchase: null,
    buildRules: (draft) => [withRuleThreshold(rule, draft)],
  });

  return (
    <li>
      <article
        aria-labelledby={headingId}
        className="space-y-5 rounded-lg border border-dashed border-line-strong bg-surface p-4 sm:p-5"
        data-testid="rule-card"
        data-rule-id={rule.rule_id}
        data-rule-origin={rule.origin}
      >
        <RuleHeader rule={rule} headingId={headingId} />
        <RuleDetails rule={rule} objective={objective} />

        {rule.origin === "SYSTEM_PROPOSED" && text.trim() === "" ? (
          <p className="rounded-md bg-unknown-soft px-3 py-2 text-ink" data-testid="threshold-empty-note">
            <span className="font-semibold">No threshold has been set.</span> The system proposes the kind of rule, never the number. Enter the value
            you want before confirming.
          </p>
        ) : null}

        <ThresholdInput
          id={fieldId}
          inputRef={inputRef}
          label={thresholdLabel(rule.rule_type)}
          hint={thresholdHint(rule.rule_type)}
          value={text}
          error={shownError}
          onChange={(next) => {
            onThresholdChange(next);
            onDraftChange(next);
          }}
        />

        <DraftPreviewPanel preview={preview} ruleId={rule.rule_id} ruleType={rule.rule_type} subject="the current portfolio" />

        <div className="flex flex-wrap items-center gap-3">
          <Button
            variant="secondary"
            softDisabled={!canConfirm}
            busy={confirming}
            busyLabel="Confirming…"
            icon={<CheckIcon />}
            aria-describedby={headingId}
            data-testid="confirm-rule"
            onClick={() => {
              if (!canConfirm) {
                // Explain instead of doing nothing: the button stays reachable.
                setAttempted(true);
                inputRef.current?.focus();
                return;
              }
              onConfirm();
            }}
          >
            Confirm this rule
          </Button>
          <p className="text-sm text-ink-muted">{canConfirm ? "Confirming makes it active in a new policy version." : "Needs a threshold before it can be confirmed."}</p>
        </div>
      </article>
    </li>
  );
}

/** A rule of a confirmed policy version: read-only. CONFIRMED rules are active; SUPERSEDED ones are kept for the record. */
export function PolicyRuleCard({ rule, objective, className }: { rule: Rule; objective: Objective | undefined; className?: string }) {
  const headingId = useId();
  return (
    <li>
      <article
        aria-labelledby={headingId}
        className={cn("space-y-4 rounded-lg border p-4 sm:p-5", rule.status === "CONFIRMED" ? "border-accent bg-surface" : "border-line bg-canvas", className)}
        data-testid="policy-rule-card"
        data-rule-id={rule.rule_id}
      >
        <RuleHeader rule={rule} headingId={headingId} />
        <p>
          <span className="block text-sm font-semibold text-ink-muted">{thresholdLabel(rule.rule_type)}</span>
          <span className={cn("tabular text-3xl font-bold", rule.status === "CONFIRMED" ? "text-ink" : "text-ink-muted line-through decoration-2")}>
            {thresholdText(rule)}
          </span>
          {rule.status === "SUPERSEDED" ? <span className="ml-2 text-sm font-semibold text-ink-muted">no longer in force</span> : null}
        </p>
        <RuleDetails rule={rule} objective={objective} />
      </article>
    </li>
  );
}
