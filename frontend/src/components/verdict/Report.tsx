"use client";

import { FeasibilityTable } from "@/components/portfolio/FeasibilityTable";
import { EmptyBlock } from "@/components/ui/AsyncStates";
import { Disclosure } from "@/components/ui/Disclosure";
import { Notice } from "@/components/ui/Notice";
import { Fact, Facts, Panel } from "@/components/ui/Panel";
import { PortfolioChecked } from "@/components/portfolio/PortfolioChecked";
import type { CheckResult, InvestigationJob, Objective, Policy, Portfolio } from "@/lib/contracts";
import { formatCoverage, formatDate, formatDateTime, formatFraction } from "@/lib/format";
import { t, tf } from "@/lib/i18n";
import { tn } from "@/lib/i18n-nodes";
import { describePurchase, FUNDING_STATEMENT, instrumentName, type InstrumentRegistry } from "@/lib/portfolio";
import { coverageText } from "@/lib/verdict";
import { CoverageBlock, GoalContextList, MaxCompliantBlock } from "./ContextPanels";
import { ExplanationList } from "./Explanation";
import { ExposurePanel } from "./ExposurePanel";
import { ruleLookup, RuleResultsList, StartingFindingsList } from "./RuleResults";
import { ScenarioPanel } from "./ScenarioPanel";
import { VerdictSummary, type SummaryLink } from "./VerdictSummary";
import { WhatNext } from "./WhatNext";

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
  if (result.data_coverage.length === 0) return t("No fund is held");
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
export function Report({ job, result, policy, objectives, instruments, scenarioPortfolio = null, personaName = t("This persona"), onPrint }: ReportProps) {
  const lookup = ruleLookup(policy);
  const purchase = result.purchase_request;
  const feasibility = result.feasibility;
  const summary = result.summary;
  const startingBreaches = summary.starting_portfolio_breaches;
  const targetIssuerId = instruments[purchase.instrument_id]?.issuer_id ?? null;

  const links: SummaryLink[] = [
    { id: "report-rules", label: t("See the checks") },
    { id: "report-exposure", label: t("Explore my exposures") },
    { id: "report-coverage", label: t("Sources and missing data") },
  ];

  return (
    <div className="space-y-6" data-testid="report" data-job-id={job.id} data-policy-version={result.policy_version ?? undefined}>
      <VerdictSummary
        summary={summary}
        links={links}
        scope={
          <>
            {tn("After the purchase of {purchase}", { purchase: <span className="tabular">{describePurchase(purchase)}</span> })}
          </>
        }
      >

        {feasibility ? (
          <p className="text-ink" data-testid="feasibility" data-feasibility={feasibility.status}>
            <span className="font-semibold">{t("Feasibility, reported separately from the rules:")}</span>{" "}
            {tn(
              feasibility.status === "FEASIBLE"
                ? "the purchase can be funded from cash. Cash goes from {before} to {after} of the portfolio."
                : "not feasible with cash alone. Cash would go from {before} to {after} of the portfolio.",
              {
                before: <span className="tabular">{formatFraction(feasibility.cash_before)}</span>,
                after: <span className="tabular font-semibold">{formatFraction(feasibility.cash_after)}</span>,
              },
            )}
          </p>
        ) : null}
        <p className="text-ink" data-testid="starting-breaches" data-count={startingBreaches}>
          <span className="font-semibold">{t("Before any purchase:")}</span>{" "}
          {startingBreaches === 0
            ? t("no confirmed rule was already failing.")
            : tn(
                startingBreaches === 1
                  ? "{count} confirmed rule was already not respected. It is listed apart from the effect of the purchase, below."
                  : "{count} confirmed rules were already not respected. They are listed apart from the effect of the purchase, below.",
                { count: <span className="tabular">{startingBreaches}</span> },
              )}
        </p>
        {summary.rules_not_evaluated > 0 ? (
          <p className="text-ink" data-testid="not-evaluated-count">
            {tn(
              summary.rules_not_evaluated === 1
                ? "{count} rule of this policy version was not evaluated; it is listed with the confirmed rules."
                : "{count} rules of this policy version were not evaluated; they are listed with the confirmed rules.",
              { count: <span className="tabular">{summary.rules_not_evaluated}</span> },
            )}
          </p>
        ) : null}
      </VerdictSummary>
      <WhatNext result={result} onPrint={onPrint} />

      {/* The job's own stored portfolio, never the customization applied now: a report keeps what it was checked against. */}
      {job.portfolio ? <PortfolioChecked portfolio={job.portfolio} scenarioPortfolio={scenarioPortfolio} instruments={instruments} personaName={personaName} /> : null}

      {result.policy_consistency.status === "PROVEN_CONFLICT" ? (
        <Notice tone="error" title={t("Two confirmed rules cannot both be respected")} role="alert">
          <ul className="list-disc space-y-1 pl-5" data-testid="policy-conflicts">
            {result.policy_consistency.conflicts.map((conflict) => (
              <li key={conflict.rule_ids.join("|")} lang="en">
                {conflict.calculation}
              </li>
            ))}
          </ul>
        </Notice>
      ) : null}

      <Panel
        id="report-rules"
        focusableHeading
        figures
        title={t("What fits and what doesn’t")}
        description={t("Your confirmed limit compared with this simulated purchase.")}
      >
        {result.rule_results.length > 0 || result.rules_not_evaluated.length > 0 ? (
          <RuleResultsList result={result} lookup={lookup} />
        ) : (
          <EmptyBlock title={t("No confirmed rule was checked")}>
            <p>{t("This report contains no rule result, so it says nothing about whether the purchase fits the rules.")}</p>
          </EmptyBlock>
        )}
      </Panel>

      <Panel collapsible
        id="report-exposure"
        focusableHeading
        figures
        title={t("Explore my exposures")}
        description={t("The same company can be held directly and inside a fund. Each part is shown, and the part that cannot be measured is drawn as a range.")}
      >
        <ExposurePanel result={result} lookup={lookup} openIssuerId={targetIssuerId} />
      </Panel>

      {result.starting_portfolio_findings.length > 0 ? (
        <Panel
          id="report-starting"
          focusableHeading
          figures
          title={t("Already not respected before the purchase")}
          eyebrow={t("Separate from the effect of the purchase")}
          description={t("These describe the portfolio as it is today. They would be there whether or not anything is bought. What the purchase adds to each is shown as its own line.")}
        >
          <StartingFindingsList result={result} lookup={lookup} />
        </Panel>
      ) : null}

      <Disclosure id="report-details" title={t("More analysis and sources")} hint={coverageHint(result)} figures>
      <div className="space-y-4">
      {feasibility ? (
        <Panel collapsible id="report-cash" focusableHeading figures title={t("The purchase and the cash that funds it")} description={t(FUNDING_STATEMENT)}>
          <FeasibilityTable feasibility={feasibility} purchase={purchase} instrumentName={instrumentName(instruments, purchase.instrument_id)} />
        </Panel>
      ) : null}

      {result.scenario ? (
        <Panel collapsible id="report-replay" focusableHeading figures title={t("Historical replay")} eyebrow={t("A separate test, not a forecast")}>
          <ScenarioPanel result={result} scenario={result.scenario} />
        </Panel>
      ) : null}

      <Panel collapsible id="report-max" focusableHeading figures title={t("Largest purchase that respects every confirmed rule")} eyebrow={t("Shown only when it can be supported")}>
        <MaxCompliantBlock result={result} lookup={lookup} maxCompliant={result.max_compliant} />
      </Panel>

      <Panel collapsible
        id="report-objectives"
        focusableHeading
        figures
        title={t("Context for the objectives")}
        eyebrow={t("Qualitative: not scored")}
        description={t("Objectives are not rules. What follows relates measured values to the words of each objective, without a pass or a fail.")}
      >
        <GoalContextList result={result} objectives={policy?.objectives ?? objectives} />
      </Panel>

      <Disclosure id="report-coverage" figures title={t("Data coverage")} hint={coverageHint(result)}>
        <p className="mb-4 max-w-prose text-ink-muted">{t("How much of each fund&apos;s holdings behind these numbers was actually reported.")}</p>
        <CoverageBlock funds={result.data_coverage} instrumentName={(fundId) => instrumentName(instruments, fundId)} />
      </Disclosure>

      {job.explanation.length > 0 ? (
        <Disclosure
          id="report-sentences"
          figures
          title={t("The result in sentences")}
          hint={tf(job.explanation.length === 1 ? "{count} sentence, each linked to its evidence" : "{count} sentences, each linked to its evidence", { count: job.explanation.length })}
        >
          <p className="mb-4 max-w-prose text-ink-muted">
            {t("The sentences restate the figures above. The verdict is the list of confirmed rules, decided by the calculation, never by these words.")}</p>
          <ExplanationList result={result} statements={job.explanation} />
        </Disclosure>
      ) : null}

      <Disclosure id="report-about" title={t("About this report")} hint={t("Versions, dates and what this simulation leaves out")}>
        <Facts className="sm:grid-cols-3">
          <Fact label={t("Confirmed policy")}>
            {result.policy_version === null ? t("None") : tf("Version {version}", { version: result.policy_version })}
            {result.policy_id ? <span className="block break-all font-mono text-sm text-ink-muted">{result.policy_id}</span> : null}
          </Fact>
          <Fact label={t("Valuation date")}>
            <span className="tabular">{formatDate(result.valuation_date)}</span>
          </Fact>
          <Fact label={t("Calculation version")}>
            <span className="break-all font-mono text-sm">{result.calculation_version}</span>
          </Fact>
          <Fact label={t("Investigation")}>
            <span className="break-all font-mono text-sm">{job.id}</span>
          </Fact>
          <Fact label={t("Finished")}>
            <span className="tabular">{formatDateTime(job.updated_at)}</span>
          </Fact>
          <Fact label={t("How it was run")}>
            {job.agent.mode === "MODEL" ? tf("A model chose the tool calls ({model})", { model: job.agent.model_id ?? t("model not reported") }) : t("Fixed sequence of tools, no model")}
          </Fact>
          <Fact label={t("Consistency of the confirmed rules")} wide>
            <span data-testid="policy-consistency" data-consistency={result.policy_consistency.status}>
              {result.policy_consistency.status === "PROVEN_CONFLICT"
                ? t("A contradiction between confirmed rules was proven (see the notice at the top of the report).")
                : result.policy_consistency.status === "CONSISTENT"
                  ? t("No supported calculation proved a contradiction between the confirmed rules.")
                  : t("Not assessed.")}
            </span>
          </Fact>
        </Facts>
        {result.disclosures.length > 0 ? (
          <div className="mt-4">
            <h3 className="font-semibold text-ink">{t("What this simulation is and is not")}</h3>
            <ul className="mt-1 list-disc space-y-1 pl-5 text-ink" data-testid="disclosures" lang="en">
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
