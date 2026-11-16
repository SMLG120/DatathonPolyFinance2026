"use client";

import { FeasibilityTable } from "@/components/portfolio/FeasibilityTable";
import { Button, LinkButton } from "@/components/ui/Button";
import { stageHref } from "@/state/stage";
import { EmptyBlock } from "@/components/ui/AsyncStates";
import { Disclosure } from "@/components/ui/Disclosure";
import { Notice } from "@/components/ui/Notice";
import { Fact, Facts, Panel } from "@/components/ui/Panel";
import { PortfolioChecked } from "@/components/portfolio/PortfolioChecked";
import type { CheckResult, InvestigationJob, Objective, Policy, Portfolio } from "@/lib/contracts";
import { formatCoverage, formatDate, formatDateTime, formatFraction } from "@/lib/format";
import { describePurchase, FUNDING_STATEMENT, instrumentName, type InstrumentRegistry } from "@/lib/portfolio";
import { coverageText } from "@/lib/verdict";
import { CoverageBlock, GoalContextList, MaxCompliantBlock } from "./ContextPanels";
import { ExplanationList } from "./Explanation";
import { ExposurePanel } from "./ExposurePanel";
import { PRINT_REPORT_LABEL } from "./PrintReport";
import { ruleLookup, RuleResultsList, StartingFindingsList } from "./RuleResults";
import { ScenarioPanel } from "./ScenarioPanel";
import { VerdictSummary, type SummaryLink } from "./VerdictSummary";

export interface ReportProps {
  /** The finished job the report belongs to: its explanation sentences and how it was run. */
  job: InvestigationJob;
  /** The job's result. The caller has checked that its execution status is OK. */
  result: CheckResult;
  /** The policy version the result was checked against, when this page still holds it. */
  policy: Policy | null;
  /** Objectives to quote when the policy version is not held. */
  objectives: Objective[];
  instruments: InstrumentRegistry;
  /** The persona's scenario portfolio, to name the portfolio stored with the job as the original or a customized one. */
  scenarioPortfolio?: Portfolio | null;
  /** Whose fictional portfolio this is, for the caption of the "Portfolio checked" table. */
  personaName?: string;
  /** Prints this report, or saves it as PDF, through the browser. The export button is shown only when this is given. */
  onPrint?: () => void;
}

/** "SPY complete · XIU.TO partial (98.0%)": what stays visible while the coverage section is closed. */
function coverageHint(result: CheckResult): string {
  if (result.data_coverage.length === 0) return "No fund is held";
  return result.data_coverage
    .map((fund) => {
      const status = coverageText(fund.status).toLowerCase();
      return fund.status === "PARTIAL" ? `${fund.fund_id} ${status} (${formatCoverage(fund.coverage_fraction)})` : `${fund.fund_id} ${status}`;
    })
    .join(" · ");
}

/**
 * One immutable report.
 *
 * Order: the headline, each confirmed rule, and where the exposure comes from.
 * Then the findings that exist without the purchase, the cash that funds it,
 * the historical replay, the largest compliant purchase and the objective
 * context, each in its own panel so different questions are never blended
 * into one score. Data coverage, the result in sentences and the notes about
 * the report are closed sections that open from the keyboard, by click or by
 * tap. The headline card links to every section.
 *
 * Every figure is a field of the engine's result. Nothing is added, subtracted
 * or counted here.
 */
export function Report({ job, result, policy, objectives, instruments, scenarioPortfolio = null, personaName = "This persona", onPrint }: ReportProps) {
  const lookup = ruleLookup(policy);
  const purchase = result.purchase_request;
  const feasibility = result.feasibility;
  const summary = result.summary;
  const startingBreaches = summary.starting_portfolio_breaches;
  const targetIssuerId = instruments[purchase.instrument_id]?.issuer_id ?? null;

  const links: SummaryLink[] = [
    { id: "report-rules", label: "See the checks" },
    { id: "report-exposure", label: "Explore my exposures" },
    { id: "report-coverage", label: "Sources and missing data" },
  ];

  return (
    <div className="space-y-6" data-testid="report" data-job-id={job.id} data-policy-version={result.policy_version ?? undefined}>
      <VerdictSummary
        summary={summary}
        links={links}
        scope={
          <>
            After the purchase of <span className="tabular">{describePurchase(purchase)}</span>
          </>
        }
      >

        {feasibility ? (
          <p className="text-ink" data-testid="feasibility" data-feasibility={feasibility.status}>
            <span className="font-semibold">Feasibility, reported separately from the rules:</span>{" "}
            {feasibility.status === "FEASIBLE" ? "the purchase can be funded from cash. Cash goes from " : "not feasible with cash alone. Cash would go from "}
            <span className="tabular">{formatFraction(feasibility.cash_before)}</span> to{" "}
            <span className="tabular font-semibold">{formatFraction(feasibility.cash_after)}</span> of the portfolio.
          </p>
        ) : null}
        <p className="text-ink" data-testid="starting-breaches" data-count={startingBreaches}>
          <span className="font-semibold">Before any purchase:</span>{" "}
          {startingBreaches === 0 ? (
            "no confirmed rule was already failing."
          ) : (
            <>
              <span className="tabular">{startingBreaches}</span> confirmed {startingBreaches === 1 ? "rule was" : "rules were"} already not respected.{" "}
              {startingBreaches === 1 ? "It is" : "They are"} listed apart from the effect of the purchase, below.
            </>
          )}
        </p>
        {summary.rules_not_evaluated > 0 ? (
          <p className="text-ink" data-testid="not-evaluated-count">
            <span className="tabular">{summary.rules_not_evaluated}</span> {summary.rules_not_evaluated === 1 ? "rule" : "rules"} of this policy version{" "}
            {summary.rules_not_evaluated === 1 ? "was" : "were"} not evaluated; {summary.rules_not_evaluated === 1 ? "it is" : "they are"} listed with
            the confirmed rules.
          </p>
        ) : null}
      </VerdictSummary>
      <div className="flex flex-wrap gap-3" data-testid="result-actions"><LinkButton href={stageHref("purchase")} variant="primary">Modify my idea</LinkButton><LinkButton href={stageHref("challenge")}>Review or dispute this result</LinkButton>{onPrint ? <Button onClick={onPrint} data-testid="print-report-button" title="Opens the browser's print dialog, where the report can be printed or saved as a PDF file">{PRINT_REPORT_LABEL}</Button> : null}</div>

      {/* The job's own stored portfolio, never the customization applied now: a report keeps what it was checked against. */}
      {job.portfolio ? <PortfolioChecked portfolio={job.portfolio} scenarioPortfolio={scenarioPortfolio} instruments={instruments} personaName={personaName} /> : null}

      {result.policy_consistency.status === "PROVEN_CONFLICT" ? (
        <Notice tone="error" title="Two confirmed rules cannot both be respected" role="alert">
          <ul className="list-disc space-y-1 pl-5" data-testid="policy-conflicts">
            {result.policy_consistency.conflicts.map((conflict) => (
              <li key={conflict.rule_ids.join("|")}>{conflict.calculation}</li>
            ))}
          </ul>
        </Notice>
      ) : null}

      <Panel
        id="report-rules"
        focusableHeading
        figures
        title="What fits and what doesn’t"
        description="Your confirmed limit compared with this simulated purchase."
      >
        {result.rule_results.length > 0 || result.rules_not_evaluated.length > 0 ? (
          <RuleResultsList result={result} lookup={lookup} />
        ) : (
          <EmptyBlock title="No confirmed rule was checked">
            <p>This report contains no rule result, so it says nothing about whether the purchase fits the rules.</p>
          </EmptyBlock>
        )}
      </Panel>

      <Panel collapsible
        id="report-exposure"
        focusableHeading
        figures
        title="Explore my exposures"
        description="The same company can be held directly and inside a fund. Each part is shown, and the part that cannot be measured is drawn as a range."
      >
        <ExposurePanel result={result} lookup={lookup} openIssuerId={targetIssuerId} />
      </Panel>

      {result.starting_portfolio_findings.length > 0 ? (
        <Panel
          id="report-starting"
          focusableHeading
          figures
          title="Already not respected before the purchase"
          eyebrow="Separate from the effect of the purchase"
          description="These describe the portfolio as it is today. They would be there whether or not anything is bought. What the purchase adds to each is shown as its own line."
        >
          <StartingFindingsList result={result} lookup={lookup} />
        </Panel>
      ) : null}

      <Disclosure id="report-details" title="More analysis and sources" hint={coverageHint(result)} figures>
      <div className="space-y-4">
      {feasibility ? (
        <Panel collapsible id="report-cash" focusableHeading figures title="The purchase and the cash that funds it" description={FUNDING_STATEMENT}>
          <FeasibilityTable feasibility={feasibility} purchase={purchase} instrumentName={instrumentName(instruments, purchase.instrument_id)} />
        </Panel>
      ) : null}

      {result.scenario ? (
        <Panel collapsible id="report-replay" focusableHeading figures title="Historical replay" eyebrow="A separate test, not a forecast">
          <ScenarioPanel result={result} scenario={result.scenario} />
        </Panel>
      ) : null}

      <Panel collapsible id="report-max" focusableHeading figures title="Largest purchase that respects every confirmed rule" eyebrow="Shown only when it can be supported">
        <MaxCompliantBlock result={result} lookup={lookup} maxCompliant={result.max_compliant} />
      </Panel>

      <Panel collapsible
        id="report-objectives"
        focusableHeading
        figures
        title="Context for the objectives"
        eyebrow="Qualitative: not scored"
        description="Objectives are not rules. What follows relates measured values to the words of each objective, without a pass or a fail."
      >
        <GoalContextList result={result} objectives={policy?.objectives ?? objectives} />
      </Panel>

      <Disclosure id="report-coverage" figures title="Data coverage" hint={coverageHint(result)}>
        <p className="mb-4 max-w-prose text-ink-muted">How much of each fund&apos;s holdings behind these numbers was actually reported.</p>
        <CoverageBlock funds={result.data_coverage} instrumentName={(fundId) => instrumentName(instruments, fundId)} />
      </Disclosure>

      {job.explanation.length > 0 ? (
        <Disclosure
          id="report-sentences"
          figures
          title="The result in sentences"
          hint={`${job.explanation.length} ${job.explanation.length === 1 ? "sentence" : "sentences"}, each linked to its evidence`}
        >
          <p className="mb-4 max-w-prose text-ink-muted">
            The sentences restate the figures above. The verdict is the list of confirmed rules, decided by the calculation, never by these words.
          </p>
          <ExplanationList result={result} statements={job.explanation} />
        </Disclosure>
      ) : null}

      <Disclosure id="report-about" title="About this report" hint="Versions, dates and what this simulation leaves out">
        <Facts className="sm:grid-cols-3">
          <Fact label="Confirmed policy">
            {result.policy_version === null ? "None" : `Version ${result.policy_version}`}
            {result.policy_id ? <span className="block break-all font-mono text-sm text-ink-muted">{result.policy_id}</span> : null}
          </Fact>
          <Fact label="Valuation date">
            <span className="tabular">{formatDate(result.valuation_date)}</span>
          </Fact>
          <Fact label="Calculation version">
            <span className="break-all font-mono text-sm">{result.calculation_version}</span>
          </Fact>
          <Fact label="Investigation">
            <span className="break-all font-mono text-sm">{job.id}</span>
          </Fact>
          <Fact label="Finished">
            <span className="tabular">{formatDateTime(job.updated_at)}</span>
          </Fact>
          <Fact label="How it was run">{job.agent.mode === "MODEL" ? `A model chose the tool calls (${job.agent.model_id ?? "model not reported"})` : "Fixed sequence of tools, no model"}</Fact>
          <Fact label="Consistency of the confirmed rules" wide>
            <span data-testid="policy-consistency" data-consistency={result.policy_consistency.status}>
              {result.policy_consistency.status === "PROVEN_CONFLICT"
                ? "A contradiction between confirmed rules was proven (see the notice at the top of the report)."
                : result.policy_consistency.status === "CONSISTENT"
                  ? "No supported calculation proved a contradiction between the confirmed rules."
                  : "Not assessed."}
            </span>
          </Fact>
        </Facts>
        {result.disclosures.length > 0 ? (
          <div className="mt-4">
            <h3 className="font-semibold text-ink">What this simulation is and is not</h3>
            <ul className="mt-1 list-disc space-y-1 pl-5 text-ink" data-testid="disclosures">
              {result.disclosures.map((disclosure) => (
                <li key={disclosure}>{disclosure}</li>
              ))}
            </ul>
          </div>
        ) : null}
      </Disclosure>
      </div>
      </Disclosure>
    </div>
  );
}
