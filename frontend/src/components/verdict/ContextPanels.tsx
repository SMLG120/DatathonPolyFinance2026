"use client";

import { EvidenceButton } from "@/components/evidence/EvidenceProvider";
import { EmptyBlock, UnknownBlock } from "@/components/ui/AsyncStates";
import { CoverageBadge } from "@/components/ui/Badge";
import { Notice } from "@/components/ui/Notice";
import type { CheckResult, FundCoverage, GoalContext, GoalContextType, MaxCompliant, Objective } from "@/lib/contracts";
import { EPS, formatCoverage, formatDate, formatFraction } from "@/lib/format";
import { ruleTypeLabel } from "@/lib/rules";
import { bindingConstraintText, coverageText } from "@/lib/verdict";
import type { RuleLookup } from "./RuleResults";
import { t } from "@/lib/i18n";

const CONTEXT_LABEL: Record<GoalContextType, string> = {
  LINKED_RULE_RESULTS: "Rules linked to this objective",
  CONCENTRATION: "Concentration",
  SCENARIO_DRAWDOWN: "Deepest fall in the replay",
  NOT_QUANTIFIED: "Not measured",
};

/** Qualitative context about objectives. Deliberately has no status, no tick and no cross. */
export function GoalContextList({ result, objectives }: { result: CheckResult; objectives: Objective[] }) {
  const items = result.goal_context;
  if (items.length === 0) {
    return (
      <EmptyBlock title={t("No context was recorded for your objectives")}>
        <p>{t("Objectives are kept as context. None of the measured values was linked to one in this report.")}</p>
      </EmptyBlock>
    );
  }
  const objectiveIds = items.map((item) => item.objective_id).filter((id, index, all) => all.indexOf(id) === index);
  return (
    <ul className="space-y-4" data-testid="goal-context">
      {objectiveIds.map((objectiveId) => {
        const objective = objectives.find((candidate) => candidate.objective_id === objectiveId);
        return (
          <li key={objectiveId} className="rounded-md border border-line bg-canvas p-3 sm:p-4">
            {objective ? (
              <figure>
                <figcaption className="text-sm font-semibold text-ink-muted">{t("Objective, in the words it was given")}</figcaption>
                <blockquote className="mt-1 border-l-4 border-line-strong pl-3 text-ink">{t("&ldquo;")}{objective.original_words}{t("&rdquo;")}</blockquote>
              </figure>
            ) : (
              <p className="text-sm font-semibold text-ink-muted">{t("Objective")} {objectiveId}</p>
            )}
            <ul className="mt-3 space-y-3">
              {items
                .filter((item) => item.objective_id === objectiveId)
                .map((item) => (
                  <ContextItem key={`${item.context_type}-${item.text}`} result={result} item={item} />
                ))}
            </ul>
          </li>
        );
      })}
    </ul>
  );
}

function ContextItem({ result, item }: { result: CheckResult; item: GoalContext }) {
  return (
    <li data-testid="goal-context-item" data-context-type={item.context_type}>
      <p className="text-sm font-semibold text-ink-muted">{CONTEXT_LABEL[item.context_type]}</p>
      <p className="text-ink">{item.text}</p>
      {item.evidence_ids.length > 0 ? (
        <div className="mt-1">
          <EvidenceButton label={`${CONTEXT_LABEL[item.context_type].toLowerCase()} (objective context)`} result={result} evidenceIds={item.evidence_ids} />
        </div>
      ) : null}
    </li>
  );
}

/**
 * The largest purchase that still respects every confirmed rule — shown only
 * when the engine supports it. Otherwise the reason it is withheld, or that no
 * purchase is feasible, is shown instead of a number. The two figures are the
 * engine's; they are displayed rounded down and never recomputed.
 */
export function MaxCompliantBlock({ result, lookup, maxCompliant }: { result: CheckResult; lookup: RuleLookup; maxCompliant: MaxCompliant | null }) {
  const ruleLabel = (ruleId: string) => {
    const rule = lookup(ruleId);
    return rule ? ruleTypeLabel(rule.rule_type) : ruleId;
  };
  if (!maxCompliant) {
    return (
      <EmptyBlock title={t("Not calculated for this result")}>
        <p data-testid="max-compliant" data-status="NONE">
          {t("The service returned no maximum, so none is shown.")}</p>
      </EmptyBlock>
    );
  }
  if (maxCompliant.status === "WITHHELD") {
    return (
      <div data-testid="max-compliant" data-status="WITHHELD">
        <UnknownBlock title={t("No maximum is shown")}>
          <p data-testid="max-reason">{maxCompliant.reason}</p>
          <p>{t("A maximum is given only when every confirmed rule can be evaluated at the boundary. A guess is not shown in its place.")}</p>
        </UnknownBlock>
      </div>
    );
  }
  if (maxCompliant.status === "NO_FEASIBLE_PURCHASE") {
    return (
      <div className="space-y-3" data-testid="max-compliant" data-status="NO_FEASIBLE_PURCHASE">
        <Notice tone="caution" title={t("No purchase of this instrument respects every confirmed rule")}>
          <p data-testid="max-reason">{maxCompliant.reason}</p>
          <p>{t("What stands in the way:")} {bindingConstraintText(maxCompliant.binding_constraint, ruleLabel)}.</p>
        </Notice>
        <EvidenceButton label={t("why no purchase is compliant")} result={result} evidenceIds={maxCompliant.evidence_ids} />
      </div>
    );
  }
  return (
    <div className="space-y-4" data-testid="max-compliant" data-status="SUPPORTED">
      <dl className="grid gap-x-6 gap-y-4 sm:grid-cols-2">
        <div>
          <dt className="text-sm font-semibold text-ink-muted">{t("As a final direct weight")}</dt>
          <dd className="tabular text-2xl font-bold text-ink" data-testid="max-final-weight">
            {formatFraction(maxCompliant.final_direct_weight, { rounding: "down" })}
          </dd>
          <dd className="text-sm text-ink-muted">{t("the most this position could weigh in the portfolio")}</dd>
        </div>
        <div>
          <dt className="text-sm font-semibold text-ink-muted">{t("As an additional purchase")}</dt>
          <dd className="tabular text-2xl font-bold text-ink" data-testid="max-additional">
            {formatFraction(maxCompliant.additional_purchase, { rounding: "down" })}
          </dd>
          <dd className="text-sm text-ink-muted">{t("on top of what is held directly today")}</dd>
        </div>
      </dl>
      <dl className="space-y-2">
        <div>
          <dt className="text-sm font-semibold text-ink-muted">{t("Limited by")}</dt>
          <dd className="text-ink" data-testid="max-binding">
            {bindingConstraintText(maxCompliant.binding_constraint, ruleLabel)}
          </dd>
        </div>
        <div>
          <dt className="text-sm font-semibold text-ink-muted">{t("Checked at the boundary")}</dt>
          <dd className="text-ink">{t("Yes — the same checks were run again at this weight.")}</dd>
        </div>
      </dl>
      <p className="text-ink" data-testid="max-reason">
        {maxCompliant.reason}
      </p>
      <p className="text-sm text-ink-muted">
        {t("Both figures are shown rounded down, so they never overstate the boundary. This is where your own confirmed rules stop — not a suggestion to buy that amount.")}</p>
      <EvidenceButton label={t("the largest compliant purchase")} result={result} evidenceIds={maxCompliant.evidence_ids} />
    </div>
  );
}

/**
 * What a fund's holdings file reports, in words. A fund below full coverage
 * reads "Partial" with the percentage truncated, so 99.96% is never shown as
 * "100.0%" beside the word "Partial".
 */
export function coverageSentence(fund: Pick<FundCoverage, "status" | "coverage_fraction">): string {
  if (fund.status === "MISSING") return "No holdings file";
  return `${coverageText(fund.status)} — ${formatCoverage(fund.coverage_fraction)} of the fund reported`;
}

/** How much of the fund holdings behind the numbers is actually reported, fund by fund. */
export function CoverageBlock({ funds, instrumentName }: { funds: FundCoverage[]; instrumentName: (fundId: string) => string }) {
  if (funds.length === 0) {
    return (
      <EmptyBlock title={t("No fund is held")}>
        <p data-testid="data-coverage" data-funds="0">
          {t("This result lists no fund, so nothing was looked through.")}</p>
      </EmptyBlock>
    );
  }
  const incomplete = funds.some((fund) => fund.status !== "COVERED");
  return (
    <div className="space-y-4" data-testid="data-coverage" data-funds={funds.length}>
      {incomplete ? (
        <p className="text-ink">
          {t("Holdings that are not reported widen results into ranges. They are never counted as zero, and reported holdings are never rescaled to 100%.")}</p>
      ) : null}
      <ul className="grid gap-3 md:grid-cols-2">
        {funds.map((fund) => (
          <li key={fund.fund_id} className="rounded-md border border-line bg-canvas p-3" data-testid="fund-coverage" data-fund-id={fund.fund_id} data-coverage-status={fund.status}>
            <div className="flex flex-wrap items-start justify-between gap-2">
              <p className="font-semibold text-ink">
                {instrumentName(fund.fund_id)} <span className="tabular block text-sm font-normal text-ink-muted">{fund.fund_id}</span>
              </p>
              <CoverageBadge status={fund.status} />
            </div>
            <p className="tabular mt-2 font-semibold text-ink" data-testid="coverage-sentence">
              {coverageSentence(fund)}
            </p>
            <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
              <div>
                <dt className="font-semibold text-ink-muted">{t("Weight in the portfolio")}</dt>
                <dd className="tabular text-ink">{formatFraction(fund.portfolio_weight)}</dd>
              </div>
              <div>
                <dt className="font-semibold text-ink-muted">{t("Portfolio weight not reported")}</dt>
                <dd className="tabular text-ink">{fund.uncovered_portfolio_weight > EPS ? formatFraction(fund.uncovered_portfolio_weight) : "None"}</dd>
              </div>
              <div>
                <dt className="font-semibold text-ink-muted">{t("Holdings with a sector label")}</dt>
                <dd className="tabular text-ink">{fund.sector_labelled_fraction > EPS ? `${formatCoverage(fund.sector_labelled_fraction)} of the fund` : "None"}</dd>
              </div>
              <div>
                <dt className="font-semibold text-ink-muted">{t("Holdings dated")}</dt>
                <dd className="tabular text-ink">{fund.holdings_date ? formatDate(fund.holdings_date) : "No holdings file"}</dd>
              </div>
              <div className="col-span-2">
                <dt className="font-semibold text-ink-muted">{t("Source")}</dt>
                <dd className="text-ink [overflow-wrap:anywhere]">{fund.source_id ?? "None"}</dd>
              </div>
            </dl>
          </li>
        ))}
      </ul>
    </div>
  );
}
