"use client";

import { EvidenceButton } from "@/components/evidence/EvidenceProvider";
import { Badge, StatusBadge } from "@/components/ui/Badge";
import type { BreachingSubject, CheckResult, Policy, Rule, RuleResult, StartingFinding } from "@/lib/contracts";
import { cn } from "@/lib/cn";
import { EPS, formatFraction, formatFractionRange } from "@/lib/format";
import { ruleParametersText, ruleStatusLabel, ruleTypeLabel } from "@/lib/rules";
import { findRule, issuerName } from "@/lib/verdict";
import { measuredText, RuleMeasure } from "./RuleMeasure";
import { t } from "@/lib/i18n";

const ROW_BORDER = {
  PASS: "border-line",
  FAIL: "border-fail",
  UNKNOWN: "border-dashed border-unknown",
} as const;

/** Looks a rule up by id: in the stored policy version, or among the draft rules of a preview. */
export type RuleLookup = (ruleId: string) => Rule | undefined;

export function ruleLookup(policy: Policy | null, drafts: Rule[] = []): RuleLookup {
  return (ruleId) => drafts.find((rule) => rule.rule_id === ruleId) ?? findRule(policy, ruleId);
}

/** "Maximum exposure to a single company" — the rule type, which every result row carries. */
export function ruleResultName(ruleResult: Pick<RuleResult, "rule_type">): string {
  return ruleTypeLabel(ruleResult.rule_type);
}

function BreachingSubjects({ result, subjects }: { result: CheckResult; subjects: BreachingSubject[] }) {
  if (subjects.length === 0) return null;
  return (
    <div data-testid="breaching-subjects">
      <p className="text-sm font-semibold text-ink-muted">{t("Companies whose proven exposure causes the breach")}</p>
      <ul className="mt-1 flex flex-wrap gap-x-5 gap-y-1 text-ink">
        {subjects.map((subject) => (
          <li key={subject.subject_id} className="tabular">
            <span className="font-semibold">{issuerName(result, subject.subject_id)}</span> {formatFractionRange(subject.lower, subject.upper)}
          </li>
        ))}
      </ul>
    </div>
  );
}

/** One evaluated rule on the portfolio after the purchase: status as word + icon + shape, the measured value, the limit and the gap. */
function RuleResultRow({ result, lookup, ruleResult }: { result: CheckResult; lookup: RuleLookup; ruleResult: RuleResult }) {
  const rule = lookup(ruleResult.rule_id);
  const name = ruleResultName(ruleResult);
  const headingId = `rule-result-${ruleResult.rule_id}`;
  return (
    <li>
      <article
        aria-labelledby={headingId}
        className={cn("space-y-3 rounded-lg border bg-surface p-4 sm:p-5", ROW_BORDER[ruleResult.status])}
        data-testid="rule-result"
        data-rule-id={ruleResult.rule_id}
        data-status={ruleResult.status}
      >
        <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
          <h3 id={headingId} className="text-lg font-semibold text-ink">
            {name}
          </h3>
          <StatusBadge status={ruleResult.status} />
        </div>
        {rule ? <p className="text-sm text-ink-muted">{ruleParametersText(rule)}</p> : null}
        <RuleMeasure
          ruleType={ruleResult.rule_type}
          status={ruleResult.status}
          measured={ruleResult.measured}
          limit={ruleResult.limit}
          gap={ruleResult.gap}
          unknownCauses={ruleResult.unknown_causes}
        />
        <p className="text-ink" data-testid="rule-reason">
          {ruleResult.reason}
        </p>
        {ruleResult.status === "UNKNOWN" ? (
          <p className="rounded-md bg-unknown-soft px-3 py-2 text-ink" data-testid="unknown-note">
            <span className="font-semibold">{t("Unknown is not a pass.")}</span> {t("The data needed to decide is missing or partial, so this rule is reported as not determined rather than assumed to be respected.")}</p>
        ) : null}
        <BreachingSubjects result={result} subjects={ruleResult.breaching_subjects} />
        <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-ink" data-testid="rule-starting" data-starting-status={ruleResult.starting.status}>
          <span className="font-semibold text-ink-muted">{t("Before the purchase:")}</span>
          <StatusBadge status={ruleResult.starting.status} />
          <span className="tabular">
            {measuredText(ruleResult.rule_type, ruleResult.starting.measured).toLowerCase()}
          </span>
        </p>
        {ruleResult.out_of_scope.length > 0 ? (
          <details className="text-sm">
            <summary className="min-h-6 cursor-pointer font-semibold text-ink-muted">{t("Positions outside the scope of this rule (")}{ruleResult.out_of_scope.length})</summary>
            <ul className="mt-1 space-y-1 text-ink" data-testid="out-of-scope">
              {ruleResult.out_of_scope.map((position) => (
                <li key={position.instrument_id}>
                  <span className="tabular font-semibold">
                    {position.instrument_id} {formatFraction(position.weight)}
                  </span>{" "}
                  — {position.reason}
                </li>
              ))}
            </ul>
          </details>
        ) : null}
        <EvidenceButton label={`${name}, after the purchase`} result={result} evidenceIds={ruleResult.evidence_ids} />
      </article>
    </li>
  );
}

/** Every confirmed rule the engine evaluated, in policy order, on the portfolio AFTER the purchase. */
export function RuleResultsList({ result, lookup }: { result: CheckResult; lookup: RuleLookup }) {
  return (
    <div className="space-y-4">
      <ul className="space-y-4" data-testid="rule-results">
        {result.rule_results.map((ruleResult) => (
          <RuleResultRow key={ruleResult.rule_id} result={result} lookup={lookup} ruleResult={ruleResult} />
        ))}
      </ul>
      {result.rules_not_evaluated.length > 0 ? (
        <div data-testid="rules-not-evaluated">
          <p className="text-sm font-semibold text-ink-muted">{t("Rules in this policy version that were not evaluated")}</p>
          <ul className="mt-1 space-y-1 text-ink">
            {result.rules_not_evaluated.map((item) => {
              const rule = lookup(item.rule_id);
              return (
                <li key={item.rule_id}>
                  <span className="font-semibold">{rule ? ruleTypeLabel(rule.rule_type) : item.rule_id}</span> ({ruleStatusLabel(item.status)}): {item.reason}
                </li>
              );
            })}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

/**
 * What the purchase adds to a measure that was already over its limit. The
 * two changes are the engine's (`purchase_effect`); when they differ, the
 * effect is unresolved and both ends are shown instead of one number.
 */
function PurchaseEffectLine({ finding }: { finding: StartingFinding }) {
  const { lower_change: lower, upper_change: upper } = finding.purchase_effect;
  const resolved = Math.abs(upper - lower) <= EPS;
  return (
    <div data-testid="purchase-effect" data-resolved={resolved ? "true" : "false"}>
      <p className="text-sm font-semibold text-ink-muted">{t("What the purchase adds to this measure")}</p>
      <p className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-ink">
        {/* The spaces keep the words apart for a screen reader; in the flex row they take no room. */}
        {resolved ? null : (
          <>
            <Badge tone="unknown" dashed>
              {t("Unresolved")}</Badge>{" "}
          </>
        )}
        <span className="tabular text-lg font-semibold">{formatFractionRange(lower, upper, { signed: true })}</span> <span>{t("of the portfolio")}</span>
      </p>
      {resolved ? null : (
        <p className="text-sm text-ink-muted">
          {t("The first figure is proven; the second is the most it could be. The data needed to say more is missing, so it is not narrowed to one number.")}</p>
      )}
    </div>
  );
}

/** Rules the portfolio already fails before any purchase, kept apart from what the purchase changes. */
export function StartingFindingsList({ result, lookup }: { result: CheckResult; lookup: RuleLookup }) {
  return (
    <ul className="space-y-4" data-testid="starting-findings">
      {result.starting_portfolio_findings.map((finding) => {
        const rule = lookup(finding.rule_id);
        const ruleType = rule?.rule_type ?? result.rule_results.find((ruleResult) => ruleResult.rule_id === finding.rule_id)?.rule_type;
        const name = ruleType ? ruleTypeLabel(ruleType) : finding.rule_id;
        const headingId = `starting-finding-${finding.rule_id}`;
        return (
          <li key={finding.rule_id}>
            <article
              aria-labelledby={headingId}
              className="space-y-3 rounded-lg border border-fail bg-surface p-4 sm:p-5"
              data-testid="starting-finding"
              data-rule-id={finding.rule_id}
            >
              <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
                <h3 id={headingId} className="text-lg font-semibold text-ink">
                  {name}
                </h3>
                <StatusBadge status={finding.status} prefix="Before the purchase:" />
              </div>
              {rule ? <p className="text-sm text-ink-muted">{ruleParametersText(rule)}</p> : null}
              {ruleType ? (
                <RuleMeasure ruleType={ruleType} status={finding.status} measured={finding.measured} limit={finding.limit} gap={finding.gap} unknownCauses={[]} />
              ) : null}
              <PurchaseEffectLine finding={finding} />
              <p className="text-ink">{finding.reason}</p>
              <BreachingSubjects result={result} subjects={finding.breaching_subjects} />
              <EvidenceButton label={`${name}, before the purchase`} result={result} evidenceIds={finding.evidence_ids} />
            </article>
          </li>
        );
      })}
    </ul>
  );
}
