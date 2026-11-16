"use client";

import { useId, type ReactNode, type Ref } from "react";
import { Badge, RuleStatusBadge } from "@/components/ui/Badge";
import { TestDataTag } from "@/components/ui/TestDataTag";
import type { Objective, PersonaId, Policy, PurchaseRequest, Rule } from "@/lib/contracts";
import { cn } from "@/lib/cn";
import { formatDateTime, percentInputToFraction } from "@/lib/format";
import {
  originDescription,
  originLabel,
  ruleParametersText,
  ruleStatusDescription,
  ruleTypeLabel,
  thresholdHint,
  thresholdLabel,
  thresholdSourceText,
  thresholdText,
  validateThreshold,
} from "@/lib/rules";
import { DraftPreviewPanel, useDraftPreview } from "./DraftPreview";
import { ThresholdInput } from "./ThresholdInput";
import { t } from "@/lib/i18n";

const WORDS_LABEL: Record<Rule["origin"], string> = {
  USER_STATED: "Your words",
  FICTIONAL_SCENARIO: "Words from the fictional scenario",
  SYSTEM_PROPOSED: "Your words that led to this proposal",
};

/** The parts every rule card shows, whatever its status: words, scope, origin, status and the linked objective. */
function RuleDetails({ rule, objective }: { rule: Rule; objective: Objective | undefined }) {
  return (
    <details className="space-y-4"><summary className="cursor-pointer text-sm font-medium text-ink-muted">{t("Source and definition")}</summary>
      <figure>
        <figcaption className="text-sm font-semibold text-ink-muted">{WORDS_LABEL[rule.origin]}</figcaption>
        <blockquote className="mt-1 border-l-4 border-line-strong pl-3 text-ink" data-testid="rule-original-words">
          {t("&ldquo;")}{rule.original_words}{t("&rdquo;")}</blockquote>
      </figure>
      {/* Each group is a direct child of the list: a <dl> may hold <div> groups, but not groups nested in a layout wrapper. */}
      <dl className="grid gap-3 sm:grid-cols-2">
        <div className="sm:col-span-2">
          <dt className="text-sm font-semibold text-ink-muted">{t("Exactly what is checked")}</dt>
          <dd className="text-ink" data-testid="rule-scope">
            {rule.scope_description}
          </dd>
        </div>
        <div className="sm:col-span-2">
          <dt className="text-sm font-semibold text-ink-muted">{t("Set to")}</dt>
          <dd className="text-ink" data-testid="rule-parameters">
            {ruleParametersText(rule)}
          </dd>
        </div>
        <div>
          <dt className="text-sm font-semibold text-ink-muted">{t("Origin")}</dt>
          <dd className="text-ink">
            <span className="font-semibold">{originLabel(rule.origin)}.</span> {originDescription(rule.origin)}
          </dd>
        </div>
        <div>
          <dt className="text-sm font-semibold text-ink-muted">{t("Status")}</dt>
          <dd className="text-ink">
            {ruleStatusDescription(rule.status)}
            {rule.confirmed_at ? (
              <span className="mt-0.5 block text-sm text-ink-muted">
                {t("Confirmed")} <span className="tabular">{formatDateTime(rule.confirmed_at)}</span>. {thresholdSourceText(rule)}.
              </span>
            ) : null}
          </dd>
        </div>
        {objective ? (
          <div className="sm:col-span-2">
            <dt className="text-sm font-semibold text-ink-muted">{t("Related objective — context only")}</dt>
            <dd className="text-ink">
              {t("&ldquo;")}{objective.original_words}{t("&rdquo;")}<span className="mt-0.5 block text-sm text-ink-muted">
                {t("The link is context for reading results. The objective does not set this threshold and is never marked pass or fail.")}</span>
            </dd>
          </div>
        ) : null}
      </dl>
    </details>
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
  /** The policy in force, when there is one: a preview tries the draft in its place. */
  policy: Policy | null;
  /** The purchase a preview is tried on (the one entered in stage 3), or null. */
  purchase: PurchaseRequest | null;
  /** The threshold field's text, as a percentage. "" = not set. */
  thresholdText: string;
  onThresholdChange: (text: string) => void;
  /** The full rule set a preview evaluates when this rule carries the given draft number. */
  buildPreviewRules: (threshold: number) => Rule[];
  /** True once the user tried to confirm: an empty field is then explained. */
  attempted: boolean;
  inputRef?: Ref<HTMLInputElement>;
}

/** Why the text of a threshold field cannot be confirmed yet, or null when it can. */
export function thresholdProblem(text: string): string | null {
  const threshold = percentInputToFraction(text);
  return text.trim() !== "" && threshold === null ? "Enter a number such as 10 or 12.5." : validateThreshold(threshold);
}

/**
 * A PROPOSED rule. It is inactive: nothing checks it until the user confirms
 * it, and it can only be confirmed with a threshold the user can see in the
 * field. A system-proposed rule arrives with an empty field.
 */
export function ProposedRuleCard({ rule, objective, personaId, policy, purchase, thresholdText: text, onThresholdChange, buildPreviewRules, attempted, inputRef }: ProposedRuleCardProps) {
  const headingId = useId();
  const fieldId = useId();

  const problem = thresholdProblem(text);
  // An empty field is not an error until the user tries to confirm it.
  const shownError = problem !== null && (attempted || text.trim() !== "") ? problem : null;

  const { preview, onDraftChange } = useDraftPreview({ personaId, policy, purchase, buildRules: buildPreviewRules });

  return (
    <li>
      <article
        aria-labelledby={headingId}
        className="space-y-5 rounded-lg border border-dashed border-line-strong bg-surface p-4 sm:p-5"
        data-testid="rule-card"
        data-rule-id={rule.rule_id}
        data-rule-origin={rule.origin}
        data-figures="true"
      >
        <RuleHeader rule={rule} headingId={headingId} aside={<TestDataTag />} />
        <RuleDetails rule={rule} objective={objective} />

        {text.trim() === "" ? (
          <p className="rounded-md bg-unknown-soft px-3 py-2 text-ink" data-testid="threshold-empty-note">
            <span className="font-semibold">{t("No threshold has been set.")}</span>{" "}
            {rule.origin === "SYSTEM_PROPOSED"
              ? "The system proposes the kind of rule, never the number. Enter the value you want before confirming."
              : "A rule with an empty number is left out of the confirmation and stays proposed."}
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

        <details><summary className="cursor-pointer text-sm font-medium text-ink-muted">{t("Preview this limit")}</summary><DraftPreviewPanel preview={preview} ruleId={rule.rule_id} ruleType={rule.rule_type} purchase={purchase} /></details>
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
        data-figures="true"
      >
        <RuleHeader rule={rule} headingId={headingId} aside={<TestDataTag />} />
        <p>
          <span className="block text-sm font-semibold text-ink-muted">{thresholdLabel(rule.rule_type)}</span>
          <span
            className={cn("tabular text-3xl font-bold", rule.status === "CONFIRMED" ? "text-ink" : "text-ink-muted line-through decoration-2")}
            data-testid="policy-rule-threshold"
          >
            {thresholdText(rule)}
          </span>
          {rule.status === "SUPERSEDED" ? <span className="ml-2 text-sm font-semibold text-ink-muted">{t("no longer in force")}</span> : null}
        </p>
        <RuleDetails rule={rule} objective={objective} />
      </article>
    </li>
  );
}
