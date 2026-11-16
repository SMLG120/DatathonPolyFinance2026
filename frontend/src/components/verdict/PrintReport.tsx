"use client";

import { useCallback, useEffect, useLayoutEffect, useState, type ReactNode } from "react";
import { flushSync } from "react-dom";
import { SOURCE_DETAILS_NOTE } from "@/components/evidence/EvidenceContent";
import { FIXTURES_LABEL, SIMULATION_LABEL } from "@/components/shell/AppShell";
import { BRAND_NAME } from "@/components/shell/BrandHero";
import type { CheckResult, FundCoverage, InvestigationJob, Objective, Policy, Portfolio, RuleResult, VerdictStatus } from "@/lib/contracts";
import { isCustomizedPortfolio, portfolioCheckedLabel } from "@/lib/customize";
import { metricLabel } from "@/lib/evidence";
import { EPS, formatChange, formatDate, formatDateTime, formatFraction, formatFractionRange, formatGap, formatReturn, isRange } from "@/lib/format";
import { describePurchase, FUNDING_STATEMENT, instrumentName, portfolioRows, type InstrumentRegistry } from "@/lib/portfolio";
import { limitNoun, ruleDirection, ruleParametersText, ruleStatusLabel, ruleTypeLabel } from "@/lib/rules";
import { bindingConstraintText, issuerName, measuredNoun, statusText, verdictHeadline } from "@/lib/verdict";
import { CONTEXT_LABEL, coverageSentence } from "./ContextPanels";
import { originOf } from "./Explanation";
import { measureDecimals, measuredText, unknownCausesText } from "./RuleMeasure";
import { ruleLookup, type RuleLookup } from "./RuleResults";

/** The label of the export button and the name of the feature, in one place. */
export const PRINT_REPORT_LABEL = "Print / Save as PDF";

/** What the printed document is, said on its first lines. */
export const PRINT_REPORT_TITLE = `${BRAND_NAME}: simulation report`;
export const PRINT_NOT_ADVICE =
  "This is the report of a simulation on a fictional portfolio. It is not personalized financial advice, not a recommendation to buy or sell, and not a forecast. It says only whether one simulated purchase respects the rules that were confirmed, and what could not be determined.";

/** The browser proposes the page title as the PDF file name. */
export function printDocumentTitle(job: Pick<InvestigationJob, "id" | "persona_id">): string {
  return `${BRAND_NAME} simulation report - ${job.persona_id} - ${job.id}`;
}

/**
 * Printing the report on screen.
 *
 * `printing` is true from just before the browser lays the page out for print until it has finished,
 * whether printing was started by the export button or by the browser's own Print command. The print
 * document is rendered only during that time, so the interactive page never carries a second copy of
 * the report. The state is flushed synchronously: the browser takes its print snapshot as soon as the
 * `beforeprint` handlers return.
 */
export function useReportPrint(documentTitle: string | null): { printing: boolean; print: () => void } {
  const [printing, setPrinting] = useState(false);

  useEffect(() => {
    const before = () => flushSync(() => setPrinting(true));
    const after = () => setPrinting(false);
    window.addEventListener("beforeprint", before);
    window.addEventListener("afterprint", after);
    return () => {
      window.removeEventListener("beforeprint", before);
      window.removeEventListener("afterprint", after);
    };
  }, []);

  // The file name a browser proposes for "Save as PDF" is the page title: name the report while it prints.
  useLayoutEffect(() => {
    if (!printing || documentTitle === null) return;
    const previous = document.title;
    document.title = documentTitle;
    return () => {
      document.title = previous;
    };
  }, [printing, documentTitle]);

  const print = useCallback(() => {
    flushSync(() => setPrinting(true));
    window.print();
  }, []);

  return { printing, print };
}

export interface PrintReportProps {
  job: InvestigationJob;
  /** The job's result. The caller has checked that its execution status is OK. */
  result: CheckResult;
  /** The policy version the result was checked against, when this page still holds it. */
  policy: Policy | null;
  /** Objectives to quote when the policy version is not held. */
  objectives: Objective[];
  instruments: InstrumentRegistry;
  scenarioPortfolio: Portfolio | null;
  /** Null when the page does not hold the persona's name. */
  personaName: string | null;
  /** True when every figure comes from recorded test data instead of the service. */
  testData: boolean;
}

const STATUS_CLASS: Record<VerdictStatus, string> = { PASS: "pr-status-pass", FAIL: "pr-status-fail", UNKNOWN: "pr-status-unknown" };

/** A status as a word in a box whose outline differs by status, so it reads without colour. */
function Status({ status, prefix }: { status: VerdictStatus; prefix?: string }) {
  return (
    <span className={`pr-status ${STATUS_CLASS[status]}`}>
      {prefix ? `${prefix} ` : ""}
      {statusText(status).toUpperCase()}
    </span>
  );
}

function Section({ title, note, children, testId, keep = false }: { title: string; note?: string; children: ReactNode; testId: string; keep?: boolean }) {
  return (
    <section className={keep ? "pr-section pr-keep" : "pr-section"} data-testid={testId}>
      <h2>{title}</h2>
      {note ? <p className="pr-note">{note}</p> : null}
      {children}
    </section>
  );
}

function ruleName(lookup: RuleLookup, ruleId: string, fallbackType?: RuleResult["rule_type"]): string {
  const type = lookup(ruleId)?.rule_type ?? fallbackType;
  return type ? ruleTypeLabel(type) : ruleId;
}

/** One evaluated rule: the same members, the same wording helpers and the same decimals as the report on screen. */
function RuleBlock({ result, lookup, ruleResult }: { result: CheckResult; lookup: RuleLookup; ruleResult: RuleResult }) {
  const rule = lookup(ruleResult.rule_id);
  const noun = limitNoun(ruleResult.rule_type);
  const ranged = ruleResult.measured !== null && isRange(ruleResult.measured.lower, ruleResult.measured.upper);
  return (
    <article className={`pr-rule ${STATUS_CLASS[ruleResult.status]}`} data-testid="print-rule" data-rule-id={ruleResult.rule_id} data-status={ruleResult.status}>
      <header>
        <h3>{ruleTypeLabel(ruleResult.rule_type)}</h3>
        <Status status={ruleResult.status} />
      </header>
      {rule ? <p className="pr-note">{ruleParametersText(rule)}</p> : null}
      <dl className="pr-figures">
        <div>
          <dt>{measuredNoun(ruleResult.rule_type)}</dt>
          <dd data-testid="print-rule-measured">{measuredText(ruleResult.rule_type, ruleResult.measured)}</dd>
        </div>
        <div>
          <dt>{noun}</dt>
          <dd data-testid="print-rule-limit">{formatFraction(ruleResult.limit)}</dd>
        </div>
        <div>
          <dt>Gap</dt>
          <dd data-testid="print-rule-gap">{formatGap(ruleResult.gap, ruleDirection(ruleResult.rule_type), noun.toLowerCase(), measureDecimals(ruleResult.rule_type))}</dd>
        </div>
        <div>
          <dt>Before the purchase</dt>
          <dd>
            {statusText(ruleResult.starting.status)}: {measuredText(ruleResult.rule_type, ruleResult.starting.measured).toLowerCase()}
          </dd>
        </div>
      </dl>
      {ranged ? <p className="pr-note">Measured as a range: proven at least the first figure, possibly as much as the second.</p> : null}
      <p>{ruleResult.reason}</p>
      {ruleResult.unknown_causes.length > 0 ? (
        <p data-testid="print-unknown-causes">
          <strong>{ruleResult.status === "UNKNOWN" ? "Why this is unknown: " : "What is still unknown: "}</strong>
          {ruleResult.status === "UNKNOWN" ? "the limit lies inside the possible range, because " : "part of the range is unproven, because "}
          {unknownCausesText(ruleResult.unknown_causes)}. Missing data is never counted as zero.
        </p>
      ) : null}
      {ruleResult.status === "UNKNOWN" ? (
        <p className="pr-unknown-note" data-testid="print-unknown-note">
          <strong>Unknown is not a pass.</strong> The data needed to decide is missing or partial, so this rule is reported as not determined rather
          than assumed to be respected.
        </p>
      ) : null}
      {ruleResult.breaching_subjects.length > 0 ? (
        <p>
          <strong>Companies whose proven exposure causes the breach: </strong>
          {ruleResult.breaching_subjects.map((subject) => `${issuerName(result, subject.subject_id)} ${formatFractionRange(subject.lower, subject.upper)}`).join("; ")}
        </p>
      ) : null}
      {ruleResult.out_of_scope.length > 0 ? (
        <div>
          <p>
            <strong>Positions outside the scope of this rule:</strong>
          </p>
          <ul>
            {ruleResult.out_of_scope.map((position) => (
              <li key={position.instrument_id}>
                {position.instrument_id} {formatFraction(position.weight)}: {position.reason}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </article>
  );
}

interface Limitation {
  key: string;
  text: ReactNode;
}

/**
 * Everything in the result that says "not known" or "not measured", gathered where it cannot be missed.
 * Each line restates a member of the result; nothing is derived here beyond choosing which members to list.
 */
function limitationsOf(result: CheckResult, lookup: RuleLookup, instruments: InstrumentRegistry): Limitation[] {
  const items: Limitation[] = [];
  for (const ruleResult of result.rule_results) {
    if (ruleResult.status === "UNKNOWN") {
      items.push({
        key: `unknown-${ruleResult.rule_id}`,
        text: (
          <>
            <strong>{ruleTypeLabel(ruleResult.rule_type)}: UNKNOWN.</strong> It could not be determined
            {ruleResult.unknown_causes.length > 0 ? `, because ${unknownCausesText(ruleResult.unknown_causes)}` : ""}. It is not counted as respected.
          </>
        ),
      });
    } else if (ruleResult.unknown_causes.length > 0) {
      items.push({
        key: `partial-${ruleResult.rule_id}`,
        text: (
          <>
            <strong>
              {ruleTypeLabel(ruleResult.rule_type)}: {statusText(ruleResult.status)}, with part of the measured range unproven
            </strong>
            , because {unknownCausesText(ruleResult.unknown_causes)}.
          </>
        ),
      });
    }
  }
  for (const item of result.rules_not_evaluated) {
    items.push({
      key: `not-evaluated-${item.rule_id}`,
      text: (
        <>
          <strong>
            {ruleName(lookup, item.rule_id)} ({ruleStatusLabel(item.status)}): not evaluated.
          </strong>{" "}
          {item.reason}
        </>
      ),
    });
  }
  for (const fund of result.data_coverage) {
    if (fund.status === "COVERED") continue;
    items.push({
      key: `coverage-${fund.fund_id}`,
      text: (
        <>
          <strong>
            {instrumentName(instruments, fund.fund_id)} ({fund.fund_id}): {coverageSentence(fund).toLowerCase()}.
          </strong>{" "}
          {fund.uncovered_portfolio_weight > EPS ? `${formatFraction(fund.uncovered_portfolio_weight)} of the portfolio is held through it without reported holdings.` : ""}
        </>
      ),
    });
  }
  if (result.exposure && result.exposure.possible_extra.proposed > EPS) {
    items.push({
      key: "possible-extra",
      text: (
        <>
          <strong>{formatFraction(result.exposure.possible_extra.proposed)} of the portfolio</strong> is fund weight that the holdings files do not
          attribute to any company. It could belong to any of them, so company exposures are ranges from what is proven to what is possible.
        </>
      ),
    });
  }
  if (result.exposure === null || result.exposure.issuers.length === 0) {
    items.push({ key: "no-exposure", text: "This result carries no company exposure rows. That is not an exposure of zero: the exposure was not reported." });
  }
  if (result.scenario?.status === "INSUFFICIENT_HISTORY") {
    items.push({
      key: "scenario-history",
      text: (
        <>
          <strong>Historical replay: not computed.</strong>{" "}
          {result.scenario.missing_instruments.length > 0 ? `No usable price history for: ${result.scenario.missing_instruments.join(", ")}.` : "The price history is insufficient."}
        </>
      ),
    });
  } else if (result.scenario && result.scenario.missing_instruments.length > 0) {
    items.push({ key: "scenario-missing", text: `Historical replay: no usable price history for ${result.scenario.missing_instruments.join(", ")}.` });
  }
  if (result.max_compliant?.status === "WITHHELD") {
    items.push({
      key: "max-withheld",
      text: (
        <>
          <strong>Largest compliant purchase: no figure is shown.</strong> {result.max_compliant.reason}
        </>
      ),
    });
  }
  return items;
}

interface SourceLine {
  sourceId: string;
  /** What the source is recorded against, in the words the evidence drawer uses for those figures. */
  uses: string[];
}

/** The source ids recorded with the figures of the result, in the order they appear, each with what it is recorded against. */
function sourcesOf(result: CheckResult, instruments: InstrumentRegistry): SourceLine[] {
  const lines = new Map<string, string[]>();
  const add = (sourceId: string, use: string) => {
    const uses = lines.get(sourceId) ?? [];
    if (!uses.includes(use)) uses.push(use);
    lines.set(sourceId, uses);
  };
  for (const fund of result.data_coverage) {
    if (fund.source_id) add(fund.source_id, `holdings of ${instrumentName(instruments, fund.fund_id)} (${fund.fund_id})${fund.holdings_date ? `, dated ${formatDate(fund.holdings_date)}` : ""}`);
  }
  for (const record of result.evidence) {
    for (const sourceId of record.source_ids) add(sourceId, metricLabel(record.metric_id).toLowerCase());
  }
  return [...lines.entries()].map(([sourceId, uses]) => ({ sourceId, uses }));
}

/**
 * The assumptions recorded with the figures, each once, in the order they first appear. Those of the
 * historical replay are printed with the replay, so they are not repeated in this list.
 */
function assumptionsOf(result: CheckResult): string[] {
  const withReplay = result.scenario?.assumptions ?? [];
  const seen: string[] = [];
  for (const record of result.evidence) {
    for (const assumption of record.assumptions) if (!seen.includes(assumption) && !withReplay.includes(assumption)) seen.push(assumption);
  }
  return seen;
}

function CoverageRow({ fund, instruments }: { fund: FundCoverage; instruments: InstrumentRegistry }) {
  return (
    <tr data-testid="print-coverage-row" data-coverage-status={fund.status}>
      <td>
        {instrumentName(instruments, fund.fund_id)} <span className="pr-id">({fund.fund_id})</span>
      </td>
      <td>{coverageSentence(fund)}</td>
      <td className="pr-num">{formatFraction(fund.portfolio_weight)}</td>
      <td className="pr-num">{fund.uncovered_portfolio_weight > EPS ? formatFraction(fund.uncovered_portfolio_weight) : "None"}</td>
      <td className="pr-nowrap">{fund.holdings_date ? formatDate(fund.holdings_date) : "No holdings file"}</td>
    </tr>
  );
}

/**
 * The report as a static document for printing or saving as PDF.
 *
 * It is built from the same job and result as the report on screen, with the same wording and
 * formatting helpers. Every figure is a member of the engine's result: nothing is added, subtracted,
 * rounded differently or counted here. It has no control, no link and no chart; exposures are a table.
 * Sections the screen keeps closed (coverage, assumptions, notes) are all written out, and what is
 * unknown or not measured is listed directly under the verdict.
 */
export function PrintReport({ job, result, policy, objectives, instruments, scenarioPortfolio, personaName, testData }: PrintReportProps) {
  const lookup = ruleLookup(policy);
  const headline = verdictHeadline(result.summary);
  const purchase = result.purchase_request;
  const feasibility = result.feasibility;
  const startingBreaches = result.summary.starting_portfolio_breaches;
  const limitations = limitationsOf(result, lookup, instruments);
  const sources = sourcesOf(result, instruments);
  const assumptions = assumptionsOf(result);
  const portfolio = job.portfolio ?? null;
  const customized = portfolio ? isCustomizedPortfolio(portfolio, scenarioPortfolio) : false;
  const quoted = policy?.objectives ?? objectives;
  const contextObjectiveIds = result.goal_context.map((item) => item.objective_id).filter((id, index, all) => all.indexOf(id) === index);
  const scenario = result.scenario;
  const maxCompliant = result.max_compliant;

  return (
    <div className="print-report" data-testid="print-report" data-job-id={job.id}>
      <header className="pr-header">
        <p className="pr-banner" data-testid="print-simulation-label">
          {SIMULATION_LABEL}
          {testData ? ` · ${FIXTURES_LABEL}` : ""}
        </p>
        <h1>{PRINT_REPORT_TITLE}</h1>
        <p data-testid="print-not-advice">{PRINT_NOT_ADVICE}</p>
        {testData ? (
          <p data-testid="print-test-data">
            <strong>Recorded test data.</strong> This page was not connected to the service: every figure below comes from recorded test data.
          </p>
        ) : null}
      </header>

      <dl className="pr-facts" data-testid="print-facts">
        <div>
          <dt>Persona</dt>
          <dd data-testid="print-persona">
            {personaName ?? "Not available on this page"} <span className="pr-id">({result.persona_id})</span>
          </dd>
        </div>
        <div>
          <dt>Portfolio checked</dt>
          <dd data-testid="print-portfolio-label" data-customized={portfolio ? String(customized) : undefined}>
            {portfolio ? portfolioCheckedLabel(portfolio, scenarioPortfolio, personaName ?? "This persona") : "Not stored with this report"}{" "}
            <span className="pr-id">({result.portfolio_id})</span>
          </dd>
        </div>
        <div>
          <dt>Valuation date</dt>
          <dd data-testid="print-valuation-date">{formatDate(result.valuation_date)}</dd>
        </div>
        <div>
          <dt>Simulated purchase</dt>
          <dd data-testid="print-purchase">{describePurchase(purchase)}</dd>
        </div>
        <div>
          <dt>Finished</dt>
          <dd>{formatDateTime(job.updated_at)}</dd>
        </div>
        <div>
          <dt>Confirmed policy</dt>
          <dd data-testid="print-policy">
            {result.policy_version === null ? "None" : `Version ${result.policy_version}`}
            {result.policy_id ? <span className="pr-id"> ({result.policy_id})</span> : null}
          </dd>
        </div>
        <div className="pr-wide">
          <dt>Investigation</dt>
          <dd className="pr-id pr-nowrap" data-testid="print-investigation-id">
            {job.id}
          </dd>
        </div>
        <div>
          <dt>Calculation version</dt>
          <dd className="pr-id">{result.calculation_version}</dd>
        </div>
        <div className="pr-wide">
          <dt>How it was run</dt>
          <dd>{job.agent.mode === "MODEL" ? `A model chose the tool calls (${job.agent.model_id ?? "model not reported"}); the verdict is the calculation's` : "Fixed sequence of tools, no model"}</dd>
        </div>
      </dl>
      <p className="pr-note">{FUNDING_STATEMENT}</p>

      <section className={`pr-verdict pr-verdict-${headline.tone}`} data-testid="print-verdict" data-headline={result.summary.headline}>
        <h2>Verdict on the portfolio after the purchase</h2>
        <p className="pr-headline" data-testid="print-headline">
          {headline.title}
        </p>
        <p data-testid="print-counts">
          {headline.detail} Confirmed rules evaluated: {result.summary.rules_evaluated}. Pass: {result.summary.counts.pass}. Fail: {result.summary.counts.fail}. Unknown:{" "}
          {result.summary.counts.unknown}.{result.summary.rules_not_evaluated > 0 ? ` Not evaluated: ${result.summary.rules_not_evaluated}.` : ""}
        </p>
        {feasibility ? (
          <p data-testid="print-feasibility" data-feasibility={feasibility.status}>
            <strong>Feasibility, reported separately from the rules:</strong>{" "}
            {feasibility.status === "FEASIBLE" ? "the purchase can be funded from cash. Cash goes from " : "not feasible with cash alone. Cash would go from "}
            {formatFraction(feasibility.cash_before)} to {formatFraction(feasibility.cash_after)} of the portfolio.
          </p>
        ) : null}
        <p>
          <strong>Before any purchase:</strong>{" "}
          {startingBreaches === 0
            ? "no confirmed rule was already failing."
            : `${startingBreaches} confirmed ${startingBreaches === 1 ? "rule was" : "rules were"} already not respected; ${startingBreaches === 1 ? "it is" : "they are"} listed apart from the effect of the purchase.`}
        </p>
        {result.policy_consistency.status === "PROVEN_CONFLICT" ? (
          <div data-testid="print-policy-conflicts">
            <p>
              <strong>Two confirmed rules cannot both be respected:</strong>
            </p>
            <ul>
              {result.policy_consistency.conflicts.map((conflict) => (
                <li key={conflict.rule_ids.join("|")}>{conflict.calculation}</li>
              ))}
            </ul>
          </div>
        ) : null}
      </section>

      <section className="pr-limits" data-testid="print-limitations" data-count={limitations.length}>
        <h2>What is unknown or not measured</h2>
        {limitations.length > 0 ? (
          <>
            <p>Missing data is never counted as zero, and an unknown result is never counted as a pass.</p>
            <ul>
              {limitations.map((item) => (
                <li key={item.key}>{item.text}</li>
              ))}
            </ul>
          </>
        ) : (
          <p>
            This result reports no unknown rule, no rule left unevaluated and no fund with missing or partial holdings. The assumptions and what the
            simulation leaves out are listed at the end.
          </p>
        )}
      </section>

      <Section title="Confirmed rules, on the portfolio after the purchase" testId="print-rules">
        {result.rule_results.length > 0 ? (
          result.rule_results.map((ruleResult) => <RuleBlock key={ruleResult.rule_id} result={result} lookup={lookup} ruleResult={ruleResult} />)
        ) : (
          <p>This report contains no rule result, so it says nothing about whether the purchase fits the rules.</p>
        )}
        {result.rules_not_evaluated.length > 0 ? (
          <div data-testid="print-rules-not-evaluated">
            <h3>Rules in this policy version that were not evaluated</h3>
            <ul>
              {result.rules_not_evaluated.map((item) => (
                <li key={item.rule_id}>
                  <strong>{ruleName(lookup, item.rule_id)}</strong> ({ruleStatusLabel(item.status)}): {item.reason}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </Section>

      {result.starting_portfolio_findings.length > 0 ? (
        <Section
          title="Already not respected before the purchase"
          note="These describe the portfolio as it is today. They would be there whether or not anything is bought."
          testId="print-starting"
        >
          {result.starting_portfolio_findings.map((finding) => {
            const ruleType = lookup(finding.rule_id)?.rule_type ?? result.rule_results.find((ruleResult) => ruleResult.rule_id === finding.rule_id)?.rule_type;
            const resolved = Math.abs(finding.purchase_effect.upper_change - finding.purchase_effect.lower_change) <= EPS;
            return (
              <article key={finding.rule_id} className="pr-rule pr-status-fail" data-testid="print-starting-finding">
                <header>
                  <h3>{ruleType ? ruleTypeLabel(ruleType) : finding.rule_id}</h3>
                  <Status status={finding.status} prefix="Before the purchase:" />
                </header>
                <dl className="pr-figures">
                  <div>
                    <dt>{ruleType ? measuredNoun(ruleType) : "Measured"}</dt>
                    <dd>{ruleType ? measuredText(ruleType, finding.measured) : formatFractionRange(finding.measured.lower, finding.measured.upper)}</dd>
                  </div>
                  <div>
                    <dt>{ruleType ? limitNoun(ruleType) : "Limit"}</dt>
                    <dd>{formatFraction(finding.limit)}</dd>
                  </div>
                  <div>
                    <dt>Gap</dt>
                    <dd>{ruleType ? formatGap(finding.gap, ruleDirection(ruleType), limitNoun(ruleType).toLowerCase(), measureDecimals(ruleType)) : formatFraction(finding.gap)}</dd>
                  </div>
                  <div>
                    <dt>What the purchase adds</dt>
                    <dd>
                      {formatFractionRange(finding.purchase_effect.lower_change, finding.purchase_effect.upper_change, { signed: true })} of the portfolio
                      {resolved ? "" : " (unresolved: proven at least the first figure, at most the second)"}
                    </dd>
                  </div>
                </dl>
                <p>{finding.reason}</p>
              </article>
            );
          })}
        </Section>
      ) : null}

      <div className="pr-pair">
      {portfolio ? (
        <Section
          keep
          title="Portfolio checked"
          note="The weights this report was checked against, as the service stored them with the investigation."
          testId="print-portfolio"
        >
          <table>
            <thead>
              <tr>
                <th>Position</th>
                <th>Kind</th>
                <th className="pr-num">Weight</th>
              </tr>
            </thead>
            <tbody>
              {portfolioRows(portfolio, instruments).map((row) => (
                <tr key={row.key} data-testid="print-portfolio-row">
                  <td>
                    {row.name}
                    {row.instrument_id ? <span className="pr-id"> ({row.instrument_id})</span> : null}
                  </td>
                  <td>{row.kind}</td>
                  <td className="pr-num">{formatFraction(row.weight)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Section>
      ) : null}

      {feasibility ? (
        <Section keep title="The purchase and the cash that funds it" note={FUNDING_STATEMENT} testId="print-cash">
          <table>
            <thead>
              <tr>
                <th>{instrumentName(instruments, purchase.instrument_id)}</th>
                <th className="pr-num">Before</th>
                <th className="pr-num">After</th>
                <th className="pr-num">Change</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>Direct weight of {purchase.instrument_id}</td>
                <td className="pr-num">{formatFraction(feasibility.starting_direct_weight)}</td>
                <td className="pr-num">{formatFraction(feasibility.target_direct_weight)}</td>
                <td className="pr-num">{formatChange(feasibility.additional_purchase)}</td>
              </tr>
              <tr>
                <td>Cash</td>
                <td className="pr-num">{formatFraction(feasibility.cash_before)}</td>
                <td className="pr-num">{formatFraction(feasibility.cash_after)}</td>
                <td className="pr-num">{feasibility.status === "FEASIBLE" ? "Sufficient" : "Insufficient cash"}</td>
              </tr>
            </tbody>
          </table>
        </Section>
      ) : null}

      </div>

      {result.exposure && result.exposure.issuers.length > 0 ? (
        <Section
          keep
          title="Exposure to single companies"
          note="Direct holdings plus holdings through funds. A range runs from what is proven to what is possible."
          testId="print-exposure"
        >
          <table>
            <thead>
              <tr>
                <th>Company</th>
                <th className="pr-num">Before the purchase</th>
                <th className="pr-num">After: held directly</th>
                <th>After: through funds</th>
                <th className="pr-num">After: total</th>
              </tr>
            </thead>
            <tbody>
              {result.exposure.issuers.map((issuer) => (
                <tr key={issuer.issuer_id} data-testid="print-exposure-row">
                  <td>{issuer.name}</td>
                  <td className="pr-num">{formatFractionRange(issuer.starting.lower, issuer.starting.upper)}</td>
                  <td className="pr-num">{formatFraction(issuer.proposed.direct)}</td>
                  <td>
                    {issuer.proposed.indirect_by_fund.length > 0
                      ? issuer.proposed.indirect_by_fund.map((part) => `${part.fund_id} ${formatFraction(part.known, { decimals: 2 })}`).join(", ")
                      : "None reported"}
                  </td>
                  <td className="pr-num">{formatFractionRange(issuer.proposed.lower, issuer.proposed.upper)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="pr-note">{result.exposure.selection_note}</p>
        </Section>
      ) : null}

      {scenario ? (
        <Section title={`Historical replay: ${scenario.label}`} note="A replay of the past on an assumed allocation. It is a separate test, not a forecast." testId="print-scenario">
          <p>
            Period: {formatDate(scenario.base_date)} to {formatDate(scenario.end_date)}.
          </p>
          {scenario.status === "COMPUTED" ? (
            <table>
              <thead>
                <tr>
                  <th>Portfolio</th>
                  <th className="pr-num">Return over the period</th>
                  <th className="pr-num">Deepest fall (context only)</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>Before the purchase</td>
                  <td className="pr-num">{scenario.starting ? formatReturn(scenario.starting.scenario_terminal_return) : "Not computed"}</td>
                  <td className="pr-num">{scenario.starting ? formatReturn(scenario.starting.scenario_max_drawdown) : "Not computed"}</td>
                </tr>
                <tr>
                  <td>After the purchase</td>
                  <td className="pr-num">{scenario.proposed ? formatReturn(scenario.proposed.scenario_terminal_return) : "Not computed"}</td>
                  <td className="pr-num">{scenario.proposed ? formatReturn(scenario.proposed.scenario_max_drawdown) : "Not computed"}</td>
                </tr>
              </tbody>
            </table>
          ) : (
            <p data-testid="print-scenario-insufficient">
              <strong>Not computed.</strong>{" "}
              {scenario.missing_instruments.length > 0 ? `No usable price history for: ${scenario.missing_instruments.join(", ")}.` : "The price history is insufficient."}
            </p>
          )}
          {scenario.status === "COMPUTED" && scenario.target_instrument_return !== null ? (
            <p>
              {purchase.instrument_id} alone over the same period: {formatReturn(scenario.target_instrument_return)}, in the portfolio&apos;s currency.
            </p>
          ) : null}
          {scenario.status === "COMPUTED" && scenario.missing_instruments.length > 0 ? <p>No usable price history for: {scenario.missing_instruments.join(", ")}.</p> : null}
          {scenario.assumptions.length > 0 ? (
            <div className="pr-keep" data-testid="print-scenario-assumptions">
              <h3>Assumptions of the replay</h3>
              <ul className="pr-columns">
                {scenario.assumptions.map((assumption) => (
                  <li key={assumption}>{assumption}</li>
                ))}
              </ul>
            </div>
          ) : null}
        </Section>
      ) : null}

      <Section keep title="Largest purchase that respects every confirmed rule" testId="print-max">
        {!maxCompliant ? <p>The service returned no maximum, so none is shown.</p> : null}
        {maxCompliant?.status === "SUPPORTED" ? (
          <>
            <p data-testid="print-max-supported">
              As a final direct weight: <strong>{formatFraction(maxCompliant.final_direct_weight, { rounding: "down" })}</strong>. As an additional purchase:{" "}
              <strong>{formatFraction(maxCompliant.additional_purchase, { rounding: "down" })}</strong>. Limited by:{" "}
              {bindingConstraintText(maxCompliant.binding_constraint, (ruleId) => ruleName(lookup, ruleId))}. The same checks were run again at this weight.
            </p>
            <p>{maxCompliant.reason}</p>
            <p className="pr-note">
              Both figures are shown rounded down, so they never overstate the boundary. This is where the confirmed rules stop: not a suggestion to buy
              that amount.
            </p>
          </>
        ) : null}
        {maxCompliant?.status === "WITHHELD" ? (
          <p data-testid="print-max-withheld">
            <strong>No maximum is shown.</strong> {maxCompliant.reason} A maximum is given only when every confirmed rule can be evaluated at the boundary.
            A guess is not shown in its place.
          </p>
        ) : null}
        {maxCompliant?.status === "NO_FEASIBLE_PURCHASE" ? (
          <p data-testid="print-max-none">
            <strong>No purchase of this instrument respects every confirmed rule.</strong> {maxCompliant.reason} What stands in the way:{" "}
            {bindingConstraintText(maxCompliant.binding_constraint, (ruleId) => ruleName(lookup, ruleId))}.
          </p>
        ) : null}
      </Section>

      {result.goal_context.length > 0 ? (
        <Section title="Context for the objectives" note="Objectives are not rules. This is qualitative context: it is not scored and has no pass or fail." testId="print-objectives">
          {contextObjectiveIds.map((objectiveId) => {
            const objective = quoted.find((candidate) => candidate.objective_id === objectiveId);
            return (
              <div key={objectiveId} className="pr-objective">
                <p>
                  <strong>{objective ? `Objective, in the words it was given: “${objective.original_words}”` : `Objective ${objectiveId}`}</strong>
                </p>
                <ul>
                  {result.goal_context
                    .filter((item) => item.objective_id === objectiveId)
                    .map((item) => (
                      <li key={`${item.context_type}-${item.text}`}>
                        {CONTEXT_LABEL[item.context_type]}: {item.text}
                      </li>
                    ))}
                </ul>
              </div>
            );
          })}
        </Section>
      ) : null}

      <Section keep title="Data coverage" note="How much of each fund's holdings behind these numbers was actually reported." testId="print-coverage">
        {result.data_coverage.length > 0 ? (
          <>
            <table>
              <thead>
                <tr>
                  <th>Fund</th>
                  <th>Holdings reported</th>
                  <th className="pr-num">Weight in the portfolio</th>
                  <th className="pr-num">Portfolio weight not reported</th>
                  <th>Holdings dated</th>
                </tr>
              </thead>
              <tbody>
                {result.data_coverage.map((fund) => (
                  <CoverageRow key={fund.fund_id} fund={fund} instruments={instruments} />
                ))}
              </tbody>
            </table>
            {result.data_coverage.some((fund) => fund.status !== "COVERED") ? (
              <p>Holdings that are not reported widen results into ranges. They are never counted as zero, and reported holdings are never rescaled to 100%.</p>
            ) : null}
          </>
        ) : (
          <p>This result lists no fund, so nothing was looked through.</p>
        )}
      </Section>

      <Section keep title="Assumptions" testId="print-assumptions">
        {assumptions.length > 0 ? (
          <ul className="pr-columns">
            {assumptions.map((assumption) => (
              <li key={assumption}>{assumption}</li>
            ))}
          </ul>
        ) : (
          <p>{scenario && scenario.assumptions.length > 0 ? "No other assumption is recorded with the figures of this result." : "No assumption is recorded with the figures of this result."}</p>
        )}
        {scenario && scenario.assumptions.length > 0 ? <p className="pr-note">The assumptions of the historical replay are listed with the replay, above.</p> : null}
        <p className="pr-note">
          Consistency of the confirmed rules:{" "}
          {result.policy_consistency.status === "PROVEN_CONFLICT"
            ? "a contradiction between confirmed rules was proven (see the verdict)."
            : result.policy_consistency.status === "CONSISTENT"
              ? "no supported calculation proved a contradiction between the confirmed rules."
              : "not assessed."}
        </p>
      </Section>

      <Section keep title="Sources recorded with the figures" testId="print-sources">
        {sources.length > 0 ? (
          <ul>
            {sources.map((source) => (
              <li key={source.sourceId} data-testid="print-source">
                <span className="pr-id">{source.sourceId}</span>: {source.uses.join("; ")}
              </li>
            ))}
          </ul>
        ) : (
          <p>No source id is recorded with the figures of this result.</p>
        )}
        <p className="pr-note" data-testid="print-source-note">
          {SOURCE_DETAILS_NOTE}
        </p>
      </Section>

      {job.explanation.length > 0 ? (
        <Section
          keep
          title="The result in sentences"
          note="The sentences restate the figures above. The verdict is the list of confirmed rules, decided by the calculation, never by these words."
          testId="print-sentences"
        >
          <ul>
            {job.explanation.map((statement) => (
              <li key={statement.statement_id}>
                {statement.text} <span className="pr-note">[{originOf(statement.rendered_by).label}]</span>
              </li>
            ))}
          </ul>
        </Section>
      ) : null}

      <div className="pr-keep">
        <Section title="What this simulation is and is not" testId="print-disclosures">
          <ul className="pr-columns">
            {result.disclosures.map((disclosure) => (
              <li key={disclosure}>{disclosure}</li>
            ))}
            <li>It is not personalized financial advice, not a recommendation to buy or sell, and not a forecast.</li>
          </ul>
        </Section>
        <p className="pr-footer" data-testid="print-footer">
          {BRAND_NAME} · {job.id} · policy version {result.policy_version ?? "none"} · valuation date {formatDate(result.valuation_date)} · simulation on a fictional
          portfolio, not advice
        </p>
      </div>
    </div>
  );
}
