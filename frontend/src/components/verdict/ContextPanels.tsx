"use client";

import { EvidenceButton } from "@/components/evidence/EvidenceProvider";
import { EmptyBlock, UnknownBlock } from "@/components/ui/AsyncStates";
import { CoverageBadge } from "@/components/ui/Badge";
import { Notice } from "@/components/ui/Notice";
import type { CheckResult, DataCoverage, GoalContext, MaxCompliant, Policy } from "@/lib/contracts";
import { formatDate, formatFraction } from "@/lib/format";
import { ruleTypeLabel } from "@/lib/rules";
import { findRule } from "@/lib/verdict";

/** Qualitative context about objectives. Deliberately has no status, no tick and no cross. */
export function GoalContextList({ result, policy, items }: { result: CheckResult; policy: Policy | null; items: GoalContext[] }) {
  if (items.length === 0) {
    return (
      <EmptyBlock title="No context was recorded for your objectives">
        <p>Objectives are kept as context. None of the measured values was linked to one in this report.</p>
      </EmptyBlock>
    );
  }
  return (
    <ul className="space-y-3" data-testid="goal-context">
      {items.map((item) => {
        const objective = policy?.objectives.find((o) => o.objective_id === item.objective_id);
        return (
          <li key={item.objective_id} className="rounded-md border border-line bg-canvas p-3 sm:p-4">
            {objective ? (
              <figure>
                <figcaption className="text-sm font-semibold text-ink-muted">Your objective, in your words</figcaption>
                <blockquote className="mt-1 border-l-4 border-line-strong pl-3 text-ink">&ldquo;{objective.original_words}&rdquo;</blockquote>
              </figure>
            ) : null}
            <p className="mt-2 text-ink">{item.text}</p>
            <div className="mt-1">
              <EvidenceButton label="this objective context" result={result} evidenceIds={item.evidence_ids} />
            </div>
          </li>
        );
      })}
    </ul>
  );
}

/**
 * The largest purchase that still respects every confirmed rule — shown only
 * when the engine supports it. Otherwise the reason it is withheld, or that no
 * purchase is feasible, is shown instead of a number.
 */
export function MaxCompliantBlock({ result, policy, maxCompliant }: { result: CheckResult; policy: Policy | null; maxCompliant: MaxCompliant | null }) {
  if (!maxCompliant) {
    return (
      <EmptyBlock title="Not calculated for this report">
        <p>No maximum was requested or returned, so none is shown.</p>
      </EmptyBlock>
    );
  }
  if (maxCompliant.status === "WITHHELD") {
    return (
      <div data-testid="max-compliant" data-status="WITHHELD">
        <UnknownBlock title="No maximum is shown">
          <p>{maxCompliant.reason}</p>
          <p>A maximum is given only when every confirmed rule can be evaluated at the boundary. A guess is not shown in its place.</p>
        </UnknownBlock>
      </div>
    );
  }
  if (maxCompliant.status === "NO_FEASIBLE_PURCHASE") {
    return (
      <div data-testid="max-compliant" data-status="NO_FEASIBLE_PURCHASE">
        <Notice tone="caution" title="No purchase of this instrument respects the confirmed rules">
          <p>{maxCompliant.reason}</p>
        </Notice>
      </div>
    );
  }
  const binding = maxCompliant.binding_rule_ids.map((ruleId) => {
    const rule = findRule(policy, ruleId);
    return rule ? ruleTypeLabel(rule.rule_type) : ruleId;
  });
  return (
    <div className="space-y-4" data-testid="max-compliant" data-status="SUPPORTED">
      <dl className="grid gap-x-6 gap-y-4 sm:grid-cols-2">
        <div>
          <dt className="text-sm font-semibold text-ink-muted">As a final direct weight</dt>
          <dd className="tabular text-2xl font-bold text-ink" data-testid="max-final-weight">
            {formatFraction(maxCompliant.final_direct_weight, { rounding: "down" })}
          </dd>
          <dd className="text-sm text-ink-muted">the most this position could weigh in the portfolio</dd>
        </div>
        <div>
          <dt className="text-sm font-semibold text-ink-muted">As an additional purchase</dt>
          <dd className="tabular text-2xl font-bold text-ink" data-testid="max-additional">
            {formatFraction(maxCompliant.additional_purchase, { rounding: "down" })}
          </dd>
          <dd className="text-sm text-ink-muted">on top of what is held directly today</dd>
        </div>
      </dl>
      <dl className="space-y-2">
        <div>
          <dt className="text-sm font-semibold text-ink-muted">Limited by</dt>
          <dd className="text-ink">{binding.length > 0 ? binding.join("; ") : "Not reported"}</dd>
        </div>
        <div>
          <dt className="text-sm font-semibold text-ink-muted">Checked at the boundary</dt>
          <dd className="text-ink">
            {maxCompliant.verified_by_rerun
              ? "Yes — the same evaluation was run again at this weight."
              : "No — this boundary was not confirmed by a second run. Treat it as unverified."}
          </dd>
        </div>
      </dl>
      <p className="text-ink">{maxCompliant.reason}</p>
      <p className="text-sm text-ink-muted">
        Both figures are rounded down, so they never overstate the boundary. This is where your own confirmed rules stop — not a suggestion to buy
        that amount.
      </p>
      <EvidenceButton label="the largest compliant purchase" result={result} evidenceIds={maxCompliant.evidence_ids} />
    </div>
  );
}

/** How much of the fund holdings behind the numbers is actually reported. */
export function CoverageBlock({ coverage }: { coverage: DataCoverage }) {
  return (
    <div className="space-y-4" data-testid="data-coverage" data-coverage-status={coverage.status}>
      <p className="flex flex-wrap items-center gap-2 text-ink">
        <span className="font-semibold">Overall:</span> <CoverageBadge status={coverage.status} />
        {coverage.status !== "COVERED" ? <span>Missing holdings widen results into ranges; they are never counted as zero.</span> : null}
      </p>
      {coverage.funds.length > 0 ? (
        <ul className="grid gap-3 md:grid-cols-2">
          {coverage.funds.map((fund) => (
            <li key={fund.fund_id} className="rounded-md border border-line bg-canvas p-3" data-testid="fund-coverage">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <p className="font-semibold text-ink">
                  {fund.fund_name} <span className="tabular block text-sm font-normal text-ink-muted">{fund.fund_id}</span>
                </p>
                <CoverageBadge status={fund.status} />
              </div>
              <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
                <div>
                  <dt className="font-semibold text-ink-muted">Weight in the portfolio</dt>
                  <dd className="tabular text-ink">{formatFraction(fund.portfolio_weight)}</dd>
                </div>
                <div>
                  <dt className="font-semibold text-ink-muted">Holdings reported</dt>
                  <dd className="tabular text-ink">
                    {fund.coverage === null ? (fund.status === "NOT_APPLICABLE" ? "Look-through not used" : "None") : `${formatFraction(fund.coverage)} of the fund`}
                  </dd>
                </div>
                <div className="col-span-2">
                  <dt className="font-semibold text-ink-muted">Holdings date</dt>
                  <dd className="tabular text-ink">{fund.holdings_date ? formatDate(fund.holdings_date) : "No holdings file"}</dd>
                </div>
              </dl>
              <p className="mt-2 text-sm text-ink-muted">{fund.note}</p>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-ink-muted">This portfolio holds no fund, so no look-through was needed.</p>
      )}
      {coverage.notes.length > 0 ? (
        <ul className="list-disc space-y-1 pl-5 text-ink">
          {coverage.notes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
