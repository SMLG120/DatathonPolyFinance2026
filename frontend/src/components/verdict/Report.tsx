"use client";

import { EvidenceButton } from "@/components/evidence/EvidenceProvider";
import { EmptyBlock } from "@/components/ui/AsyncStates";
import { Notice } from "@/components/ui/Notice";
import { Fact, Facts, Panel } from "@/components/ui/Panel";
import type { CheckResult, Policy } from "@/lib/contracts";
import { formatDate, formatFraction } from "@/lib/format";
import { describePurchase, FUNDING_STATEMENT } from "@/lib/portfolio";
import { countResult } from "@/lib/verdict";
import { CoverageBlock, GoalContextList, MaxCompliantBlock } from "./ContextPanels";
import { ExposurePanel } from "./ExposurePanel";
import { PurchaseEffectList, StartingFindingsList } from "./RuleResults";
import { ScenarioPanel } from "./ScenarioPanel";
import { VerdictSummary } from "./VerdictSummary";

export interface ReportProps {
  result: CheckResult;
  /** The policy version the result was checked against, when this page still holds it. */
  policy: Policy | null;
}

/**
 * One immutable report: the headline, then each kind of finding in its own
 * panel so that different questions are never blended into one score —
 * effect of the purchase, exposure, scenario budget, the largest compliant
 * purchase, findings that exist without the purchase, objective context and
 * data coverage.
 */
export function Report({ result, policy }: ReportProps) {
  const counts = countResult(result);
  const startingCounts = countResult(result, "starting");
  const purchase = result.purchase;
  const feasibility = result.feasibility;

  return (
    <div className="space-y-6" data-testid="report">
      <VerdictSummary
        counts={counts}
        scope={
          purchase ? (
            <>
              After the purchase of <span className="tabular">{describePurchase(purchase)}</span> · confirmed policy version {result.policy_version ?? "none"}
            </>
          ) : (
            <>The portfolio as it is · confirmed policy version {result.policy_version ?? "none"}</>
          )
        }
      >
        {purchase ? <p className="text-ink">{FUNDING_STATEMENT}</p> : null}
        {feasibility ? (
          <p className="text-ink" data-testid="feasibility" data-feasibility={feasibility.status}>
            <span className="font-semibold">Feasibility, reported separately from the rules:</span>{" "}
            {feasibility.status === "FEASIBLE" ? (
              <>
                the purchase can be funded from cash. Cash goes from <span className="tabular">{formatFraction(feasibility.cash_before)}</span> to{" "}
                <span className="tabular font-semibold">{formatFraction(feasibility.cash_after)}</span>.
              </>
            ) : (
              <>
                not feasible with cash alone. Cash would go from <span className="tabular">{formatFraction(feasibility.cash_before)}</span> to{" "}
                <span className="tabular font-semibold">{formatFraction(feasibility.cash_after)}</span>.
              </>
            )}
          </p>
        ) : null}
        {purchase ? (
          <p className="text-ink" data-testid="starting-counts">
            <span className="font-semibold">Before any purchase:</span>{" "}
            <span className="tabular">
              {startingCounts.fail} fail, {startingCounts.unknown} unknown, {startingCounts.pass} pass
            </span>
            . Findings that already exist are listed in their own section below.
          </p>
        ) : null}
      </VerdictSummary>

      {result.policy_consistency.status === "PROVEN_CONFLICT" ? (
        <Notice tone="error" title="Two confirmed rules cannot both be respected" role="alert">
          <ul className="list-disc space-y-1 pl-5">
            {result.policy_consistency.findings.map((finding) => (
              <li key={finding.text}>{finding.text}</li>
            ))}
          </ul>
        </Notice>
      ) : null}

      <Panel
        title={purchase ? "Effect of the purchase on each confirmed rule" : "Each confirmed rule on the current portfolio"}
        description="Every confirmed rule is listed with what was measured, the limit you confirmed and the gap between them."
      >
        {result.rule_results.length > 0 ? (
          <PurchaseEffectList result={result} policy={policy} />
        ) : (
          <EmptyBlock title="No confirmed rule was checked">
            <p>This report contains no rule result, so it says nothing about whether the purchase fits your rules.</p>
          </EmptyBlock>
        )}
      </Panel>

      {result.exposures.map((exposure) => (
        <Panel
          key={exposure.rule_id}
          title="Exposure: held directly and through funds"
          description="The same company can be held directly and inside a fund. Both parts are added, and the part that cannot be measured is drawn as a range."
        >
          <ExposurePanel result={result} exposure={exposure} />
        </Panel>
      ))}

      <Panel title="Scenario risk budget" eyebrow="A separate test, not a forecast">
        {result.scenario ? (
          <ScenarioPanel result={result} scenario={result.scenario} />
        ) : (
          <EmptyBlock title="No scenario budget was checked">
            <p>This policy has no confirmed loss budget for a historical replay, so no replay was run.</p>
          </EmptyBlock>
        )}
      </Panel>

      {purchase ? (
        <Panel title="Largest purchase that respects your confirmed rules" eyebrow="Shown only when it can be supported">
          <MaxCompliantBlock result={result} policy={policy} maxCompliant={result.max_compliant} />
        </Panel>
      ) : null}

      {purchase ? (
        <Panel
          title="Starting portfolio: findings that exist without the purchase"
          eyebrow="Separate from the effect of the purchase"
          description="These describe the portfolio as it is today. They would be there whether or not anything is bought."
        >
          <StartingFindingsList result={result} policy={policy} />
        </Panel>
      ) : null}

      <Panel
        title="Context for your objectives"
        eyebrow="Qualitative — not scored"
        description="Objectives are not rules. What follows relates measured values to your words, without a pass or a fail."
      >
        <GoalContextList result={result} policy={policy} items={result.goal_context} />
      </Panel>

      <Panel title="Data coverage" description="How much of the fund holdings behind these numbers was actually reported.">
        <CoverageBlock coverage={result.data_coverage} />
      </Panel>

      {result.explanation.length > 0 ? (
        <Panel title="The result in sentences" description="Each sentence is built from the figures above and links to its evidence.">
          <ul className="space-y-3" data-testid="explanation">
            {result.explanation.map((statement) => (
              <li key={statement.text} className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 border-b border-line pb-3 last:border-b-0 last:pb-0">
                <p className="min-w-0 flex-1 basis-80 text-ink">{statement.text}</p>
                <EvidenceButton label="this sentence" result={result} evidenceIds={statement.evidence_ids} />
              </li>
            ))}
          </ul>
        </Panel>
      ) : null}

      <Panel title="About this report" tone="sunken">
        <Facts className="sm:grid-cols-3">
          <Fact label="Confirmed policy">{result.policy_version === null ? "None" : `Version ${result.policy_version}`}</Fact>
          <Fact label="Valuation date">
            <span className="tabular">{formatDate(result.valuation_date)}</span>
          </Fact>
          <Fact label="Calculation version">
            <span className="break-all font-mono text-sm">{result.calculation_version}</span>
          </Fact>
          <Fact label="Consistency of the confirmed rules" wide>
            {result.policy_consistency.status === "PROVEN_CONFLICT"
              ? "A contradiction between confirmed rules was proven (see above)."
              : "No contradiction between confirmed rules was proven."}
          </Fact>
        </Facts>
      </Panel>
    </div>
  );
}
