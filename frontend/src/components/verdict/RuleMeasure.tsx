import type { RuleType, UnknownCause, VerdictStatus } from "@/lib/contracts";
import { formatFraction, formatFractionRange, formatGap, isRange } from "@/lib/format";
import { limitNoun, ruleDirection } from "@/lib/rules";
import { measuredNoun, unknownCauseText } from "@/lib/verdict";

export interface RuleMeasureProps {
  ruleType: RuleType;
  status: VerdictStatus;
  measured: { lower: number; upper: number } | null;
  limit: number;
  /** The service's gap: positive is the size of the breach, null when it cannot be determined. */
  gap: number | null;
  unknownCauses: UnknownCause[];
}

/** Decimals of the percentages of a rule's figures: a loss over a period is reported to two, like every return. */
export function measureDecimals(ruleType: RuleType): number {
  return ruleType === "scenario_loss_budget" ? 2 : 1;
}

/** What was measured for a rule, as one value or as the range it lies in. */
export function measuredText(ruleType: RuleType, measured: { lower: number; upper: number } | null): string {
  return measured ? formatFractionRange(measured.lower, measured.upper, { decimals: measureDecimals(ruleType) }) : "Could not be measured";
}

/** "a fund has no holdings file; a fund's holdings file reports only part of the fund" */
export function unknownCausesText(causes: UnknownCause[]): string {
  return causes.map(unknownCauseText).join("; ");
}

/**
 * The numbers of one rule result, as the service sent them: what was measured
 * (one value, or the range it lies in), the limit, the gap, and why part of
 * it is unknown. Nothing is recomputed: an UNKNOWN keeps its range and its
 * cause instead of a single number.
 */
export function RuleMeasure({ ruleType, status, measured, limit, gap, unknownCauses }: RuleMeasureProps) {
  const noun = limitNoun(ruleType);
  const ranged = measured !== null && isRange(measured.lower, measured.upper);
  return (
    <dl className="grid gap-x-6 gap-y-2 sm:grid-cols-3" data-testid="rule-measure">
      <div>
        <dt className="text-sm font-semibold text-ink-muted">{measuredNoun(ruleType)}</dt>
        <dd className="tabular text-lg font-semibold text-ink" data-testid="rule-measured">
          {measuredText(ruleType, measured)}
        </dd>
        {ranged ? <dd className="text-sm text-ink-muted">Proven at least the first figure; possibly as much as the second.</dd> : null}
      </div>
      <div>
        <dt className="text-sm font-semibold text-ink-muted">{noun}</dt>
        <dd className="tabular text-lg font-semibold text-ink" data-testid="rule-limit">
          {formatFraction(limit)}
        </dd>
      </div>
      <div>
        <dt className="text-sm font-semibold text-ink-muted">Gap</dt>
        <dd className="tabular text-lg font-semibold text-ink" data-testid="rule-gap">
          {formatGap(gap, ruleDirection(ruleType), noun.toLowerCase(), measureDecimals(ruleType))}
        </dd>
      </div>
      {unknownCauses.length > 0 ? (
        <div className="sm:col-span-3" data-testid="unknown-causes">
          <dt className="text-sm font-semibold text-ink-muted">{status === "UNKNOWN" ? "Why this is unknown" : "What is still unknown"}</dt>
          <dd className="text-ink">
            {status === "UNKNOWN" ? "The limit lies inside the possible range, because " : "Part of the range is unproven, because "}
            {unknownCausesText(unknownCauses)}. Missing data is never counted as zero.
          </dd>
        </div>
      ) : null}
    </dl>
  );
}
