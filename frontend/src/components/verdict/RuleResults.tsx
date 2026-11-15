"use client";

import { EvidenceButton } from "@/components/evidence/EvidenceProvider";
import { StatusBadge } from "@/components/ui/Badge";
import type { CheckResult, Policy, RuleEvaluation, RuleResult } from "@/lib/contracts";
import { cn } from "@/lib/cn";
import { formatFraction, formatFractionRange, formatGap } from "@/lib/format";
import { limitNoun, ruleDirection, ruleTypeLabel } from "@/lib/rules";
import { findRule, statusText } from "@/lib/verdict";

export function measuredText(evaluation: RuleEvaluation): string {
  return evaluation.measured ? formatFractionRange(evaluation.measured.lower, evaluation.measured.upper) : "Not measured";
}

const ROW_BORDER = {
  PASS: "border-line",
  FAIL: "border-fail",
  UNKNOWN: "border-dashed border-unknown",
} as const;

interface RowProps {
  result: CheckResult;
  policy: Policy | null;
  ruleResult: RuleResult;
  /** The evaluation this row is about. */
  evaluation: RuleEvaluation;
  /** Words for the moment the evaluation describes, used in the evidence label. */
  moment: string;
  /** The other evaluation, shown on one line for comparison. */
  other?: { label: string; evaluation: RuleEvaluation } | null;
}

/** One rule: status as word + icon + shape, the measured value, the limit and the gap. */
function RuleResultRow({ result, policy, ruleResult, evaluation, moment, other }: RowProps) {
  const rule = findRule(policy, ruleResult.rule_id);
  const name = ruleTypeLabel(ruleResult.rule_type);
  const headingId = `rule-${moment.replace(/\s+/g, "-")}-${ruleResult.rule_id}`;
  return (
    <li>
      <article
        aria-labelledby={headingId}
        className={cn("space-y-3 rounded-lg border bg-surface p-4 sm:p-5", ROW_BORDER[evaluation.status])}
        data-testid="rule-result"
        data-rule-id={ruleResult.rule_id}
        data-status={evaluation.status}
      >
        <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
          <h3 id={headingId} className="text-lg font-semibold text-ink">
            {name}
          </h3>
          <StatusBadge status={evaluation.status} />
        </div>
        {rule ? <p className="text-sm text-ink-muted">{rule.scope_description}</p> : null}
        <dl className="grid gap-x-6 gap-y-3 sm:grid-cols-3">
          <div>
            <dt className="text-sm font-semibold text-ink-muted">Measured</dt>
            <dd className="tabular text-2xl font-bold text-ink" data-testid="rule-measured">
              {measuredText(evaluation)}
            </dd>
            <dd className="text-sm text-ink-muted">{evaluation.measured_label}</dd>
          </div>
          <div>
            <dt className="text-sm font-semibold text-ink-muted">{limitNoun(ruleResult.rule_type)} you confirmed</dt>
            <dd className="tabular text-2xl font-bold text-ink" data-testid="rule-limit">
              {formatFraction(evaluation.limit)}
            </dd>
          </div>
          <div>
            <dt className="text-sm font-semibold text-ink-muted">Gap</dt>
            <dd className="tabular text-lg font-semibold text-ink" data-testid="rule-gap">
              {formatGap(evaluation.gap, ruleDirection(ruleResult.rule_type))}
            </dd>
          </div>
        </dl>
        <p className="text-ink">{evaluation.reason}</p>
        {evaluation.status === "UNKNOWN" ? (
          <p className="rounded-md bg-unknown-soft px-3 py-2 text-ink">
            <span className="font-semibold">Unknown is not a pass.</span> The data needed to decide is missing or partial, so this rule is reported as
            not determined rather than assumed to be respected.
          </p>
        ) : null}
        {other ? (
          <p className="tabular text-sm text-ink-muted" data-testid="rule-other">
            {other.label}: <span className="font-semibold text-ink">{statusText(other.evaluation.status)}</span> · measured{" "}
            {measuredText(other.evaluation).toLowerCase()} ({other.evaluation.measured_label})
          </p>
        ) : null}
        <EvidenceButton label={`${name}, ${moment}`} result={result} evidenceIds={evaluation.evidence_ids} />
      </article>
    </li>
  );
}

/** The confirmed rules evaluated on the portfolio AFTER the purchase (or on the portfolio as is when there is none). */
export function PurchaseEffectList({ result, policy }: { result: CheckResult; policy: Policy | null }) {
  return (
    <ul className="space-y-4" data-testid="purchase-effect">
      {result.rule_results.map((ruleResult) => {
        const evaluation = ruleResult.proposed ?? ruleResult.starting;
        return (
          <RuleResultRow
            key={ruleResult.rule_id}
            result={result}
            policy={policy}
            ruleResult={ruleResult}
            evaluation={evaluation}
            moment={ruleResult.proposed ? "after the purchase" : "current portfolio"}
            other={ruleResult.proposed ? { label: "Before the purchase", evaluation: ruleResult.starting } : null}
          />
        );
      })}
    </ul>
  );
}

/** Rules the portfolio does not pass as it is today, whatever is bought. */
export function StartingFindingsList({ result, policy }: { result: CheckResult; policy: Policy | null }) {
  const findings = result.rule_results.filter((ruleResult) => ruleResult.starting.status !== "PASS");
  if (findings.length === 0) {
    return (
      <p className="text-ink" data-testid="starting-clear">
        Every confirmed rule passes on the portfolio as it is today, before any purchase.
      </p>
    );
  }
  return (
    <ul className="space-y-4" data-testid="starting-findings">
      {findings.map((ruleResult) => (
        <RuleResultRow
          key={ruleResult.rule_id}
          result={result}
          policy={policy}
          ruleResult={ruleResult}
          evaluation={ruleResult.starting}
          moment="before the purchase"
          other={ruleResult.proposed ? { label: "With the purchase", evaluation: ruleResult.proposed } : null}
        />
      ))}
    </ul>
  );
}
