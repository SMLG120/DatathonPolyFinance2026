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
import { t, tf } from "@/lib/i18n";
import { tn } from "@/lib/i18n-nodes";
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
  return tf("{brand} simulation report - {persona} - {job}", { brand: BRAND_NAME, persona: job.persona_id, job: job.id });
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
          <dt>{t("Gap")}</dt>
          <dd data-testid="print-rule-gap">{formatGap(ruleResult.gap, ruleDirection(ruleResult.rule_type), noun.toLowerCase(), measureDecimals(ruleResult.rule_type))}</dd>
        </div>
        <div>
          <dt>{t("Before the purchase")}</dt>
          <dd>
            {statusText(ruleResult.starting.status)}: {measuredText(ruleResult.rule_type, ruleResult.starting.measured).toLowerCase()}
          </dd>
        </div>
      </dl>
      {ranged ? <p className="pr-note">{t("Measured as a range: proven at least the first figure, possibly as much as the second.")}</p> : null}
      <p lang="en">{ruleResult.reason}</p>
      {ruleResult.unknown_causes.length > 0 ? (
        <p data-testid="print-unknown-causes">
          <strong>{ruleResult.status === "UNKNOWN" ? t("Why this is unknown: ") : t("What is still unknown: ")}</strong>
          {tf(
            ruleResult.status === "UNKNOWN"
              ? "the limit lies inside the possible range, because {causes}. Missing data is never counted as zero."
              : "part of the range is unproven, because {causes}. Missing data is never counted as zero.",
            { causes: unknownCausesText(ruleResult.unknown_causes) },
          )}
        </p>
      ) : null}
      {ruleResult.status === "UNKNOWN" ? (
        <p className="pr-unknown-note" data-testid="print-unknown-note">
          <strong>{t("Unknown is not a pass.")}</strong>{" "}
          {t("The data needed to decide is missing or partial, so this rule is reported as not determined rather than assumed to be respected.")}
        </p>
      ) : null}
      {ruleResult.breaching_subjects.length > 0 ? (
        <p>
          <strong>{t("Companies whose proven exposure causes the breach: ")}</strong>
          {ruleResult.breaching_subjects.map((subject) => `${issuerName(result, subject.subject_id)} ${formatFractionRange(subject.lower, subject.upper)}`).join("; ")}
        </p>
      ) : null}
      {ruleResult.out_of_scope.length > 0 ? (
        <div>
          <p>
            <strong>{t("Positions outside the scope of this rule:")}</strong>
          </p>
          <ul>
            {ruleResult.out_of_scope.map((position) => (
              <li key={position.instrument_id}>
                {position.instrument_id} {formatFraction(position.weight)}: <span lang="en">{position.reason}</span>
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
            <strong>{tf("{rule}: UNKNOWN.", { rule: ruleTypeLabel(ruleResult.rule_type) })}</strong>{" "}
            {ruleResult.unknown_causes.length > 0
              ? tf("It could not be determined, because {causes}. It is not counted as respected.", { causes: unknownCausesText(ruleResult.unknown_causes) })
              : t("It could not be determined. It is not counted as respected.")}
          </>
        ),
      });
    } else if (ruleResult.unknown_causes.length > 0) {
      items.push({
        key: `partial-${ruleResult.rule_id}`,
        text: (
          <>
            <strong>{tf("{rule}: {status}, with part of the measured range unproven", { rule: ruleTypeLabel(ruleResult.rule_type), status: statusText(ruleResult.status) })}</strong>
            {tf(", because {causes}.", { causes: unknownCausesText(ruleResult.unknown_causes) })}
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
          <strong>{tf("{rule} ({status}): not evaluated.", { rule: ruleName(lookup, item.rule_id), status: ruleStatusLabel(item.status) })}</strong>{" "}
          <span lang="en">{item.reason}</span>
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
          {fund.uncovered_portfolio_weight > EPS ? tf("{weight} of the portfolio is held through it without reported holdings.", { weight: formatFraction(fund.uncovered_portfolio_weight) }) : ""}
        </>
      ),
    });
  }
  if (result.exposure && result.exposure.possible_extra.proposed > EPS) {
    items.push({
      key: "possible-extra",
      text: (
        <>
          <strong>{tf("{weight} of the portfolio", { weight: formatFraction(result.exposure.possible_extra.proposed) })}</strong>{" "}
          {t("is fund weight that the holdings files do not attribute to any company. It could belong to any of them, so company exposures are ranges from what is proven to what is possible.")}
        </>
      ),
    });
  }
  if (result.exposure === null || result.exposure.issuers.length === 0) {
    items.push({ key: "no-exposure", text: t("This result carries no company exposure rows. That is not an exposure of zero: the exposure was not reported.") });
  }
  if (result.scenario?.status === "INSUFFICIENT_HISTORY") {
    items.push({
      key: "scenario-history",
      text: (
        <>
          <strong>{t("Historical replay: not computed.")}</strong>{" "}
          {result.scenario.missing_instruments.length > 0
            ? tf("No usable price history for: {instruments}.", { instruments: result.scenario.missing_instruments.join(", ") })
            : t("The price history is insufficient.")}
        </>
      ),
    });
  } else if (result.scenario && result.scenario.missing_instruments.length > 0) {
    items.push({ key: "scenario-missing", text: tf("Historical replay: no usable price history for {instruments}.", { instruments: result.scenario.missing_instruments.join(", ") }) });
  }
  if (result.max_compliant?.status === "WITHHELD") {
    items.push({
      key: "max-withheld",
      text: (
        <>
          <strong>{t("Largest compliant purchase: no figure is shown.")}</strong> <span lang="en">{result.max_compliant.reason}</span>
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
    if (fund.source_id) add(
        fund.source_id,
        fund.holdings_date
          ? tf("holdings of {fund} ({id}), dated {date}", { fund: instrumentName(instruments, fund.fund_id), id: fund.fund_id, date: formatDate(fund.holdings_date) })
          : tf("holdings of {fund} ({id})", { fund: instrumentName(instruments, fund.fund_id), id: fund.fund_id }),
      );
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
      <td className="pr-num">{fund.uncovered_portfolio_weight > EPS ? formatFraction(fund.uncovered_portfolio_weight) : t("None")}</td>
      <td className="pr-nowrap">{fund.holdings_date ? formatDate(fund.holdings_date) : t("No holdings file")}</td>
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
          {t(SIMULATION_LABEL)}
          {testData ? ` · ${t(FIXTURES_LABEL)}` : ""}
        </p>
        <h1>{tf("{brand}: simulation report", { brand: BRAND_NAME })}</h1>
        <p data-testid="print-not-advice">{t(PRINT_NOT_ADVICE)}</p>
        {testData ? (
          <p data-testid="print-test-data">
            <strong>{t("Recorded test data.")}</strong> {t("This page was not connected to the service: every figure below comes from recorded test data.")}
          </p>
        ) : null}
      </header>

      <dl className="pr-facts" data-testid="print-facts">
        <div>
          <dt>{t("Persona")}</dt>
          <dd data-testid="print-persona">
            {personaName ?? t("Not available on this page")} <span className="pr-id">({result.persona_id})</span>
          </dd>
        </div>
        <div>
          <dt>{t("Portfolio checked")}</dt>
          <dd data-testid="print-portfolio-label" data-customized={portfolio ? String(customized) : undefined}>
            {portfolio ? portfolioCheckedLabel(portfolio, scenarioPortfolio, personaName ?? t("This persona")) : t("Not stored with this report")}{" "}
            <span className="pr-id">({result.portfolio_id})</span>
          </dd>
        </div>
        <div>
          <dt>{t("Valuation date")}</dt>
          <dd data-testid="print-valuation-date">{formatDate(result.valuation_date)}</dd>
        </div>
        <div>
          <dt>{t("Simulated purchase")}</dt>
          <dd data-testid="print-purchase">{describePurchase(purchase)}</dd>
        </div>
        <div>
          <dt>{t("Finished")}</dt>
          <dd>{formatDateTime(job.updated_at)}</dd>
        </div>
        <div>
          <dt>{t("Confirmed policy")}</dt>
          <dd data-testid="print-policy">
            {result.policy_version === null ? t("None") : tf("Version {version}", { version: result.policy_version })}
            {result.policy_id ? <span className="pr-id"> ({result.policy_id})</span> : null}
          </dd>
        </div>
        <div className="pr-wide">
          <dt>{t("Investigation")}</dt>
          <dd className="pr-id pr-nowrap" data-testid="print-investigation-id">
            {job.id}
          </dd>
        </div>
        <div>
          <dt>{t("Calculation version")}</dt>
          <dd className="pr-id">{result.calculation_version}</dd>
        </div>
        <div className="pr-wide">
          <dt>{t("How it was run")}</dt>
          <dd>
            {job.agent.mode === "MODEL"
              ? tf("A model chose the tool calls ({model}); the verdict is the calculation's", { model: job.agent.model_id ?? t("model not reported") })
              : t("Fixed sequence of tools, no model")}
          </dd>
        </div>
      </dl>
      <p className="pr-note">{t(FUNDING_STATEMENT)}</p>

      <section className={`pr-verdict pr-verdict-${headline.tone}`} data-testid="print-verdict" data-headline={result.summary.headline}>
        <h2>{t("Verdict on the portfolio after the purchase")}</h2>
        <p className="pr-headline" data-testid="print-headline">
          {headline.title}
        </p>
        <p data-testid="print-counts">
          {headline.detail}{" "}
          {tf("Confirmed rules evaluated: {evaluated}. Pass: {pass}. Fail: {fail}. Unknown: {unknown}.", {
            evaluated: result.summary.rules_evaluated,
            pass: result.summary.counts.pass,
            fail: result.summary.counts.fail,
            unknown: result.summary.counts.unknown,
          })}
          {result.summary.rules_not_evaluated > 0 ? ` ${tf("Not evaluated: {count}.", { count: result.summary.rules_not_evaluated })}` : ""}
        </p>
        {feasibility ? (
          <p data-testid="print-feasibility" data-feasibility={feasibility.status}>
            <strong>{t("Feasibility, reported separately from the rules:")}</strong>{" "}
            {tf(
              feasibility.status === "FEASIBLE"
                ? "the purchase can be funded from cash. Cash goes from {before} to {after} of the portfolio."
                : "not feasible with cash alone. Cash would go from {before} to {after} of the portfolio.",
              { before: formatFraction(feasibility.cash_before), after: formatFraction(feasibility.cash_after) },
            )}
          </p>
        ) : null}
        <p>
          <strong>{t("Before any purchase:")}</strong>{" "}
          {startingBreaches === 0
            ? t("no confirmed rule was already failing.")
            : tf(
                startingBreaches === 1
                  ? "{count} confirmed rule was already not respected; it is listed apart from the effect of the purchase."
                  : "{count} confirmed rules were already not respected; they are listed apart from the effect of the purchase.",
                { count: startingBreaches },
              )}
        </p>
        {result.policy_consistency.status === "PROVEN_CONFLICT" ? (
          <div data-testid="print-policy-conflicts">
            <p>
              <strong>{t("Two confirmed rules cannot both be respected:")}</strong>
            </p>
            <ul>
              {result.policy_consistency.conflicts.map((conflict) => (
                <li key={conflict.rule_ids.join("|")} lang="en">
                  {conflict.calculation}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </section>

      <section className="pr-limits" data-testid="print-limitations" data-count={limitations.length}>
        <h2>{t("What is unknown or not measured")}</h2>
        {limitations.length > 0 ? (
          <>
            <p>{t("Missing data is never counted as zero, and an unknown result is never counted as a pass.")}</p>
            <ul>
              {limitations.map((item) => (
                <li key={item.key}>{item.text}</li>
              ))}
            </ul>
          </>
        ) : (
          <p>
            {t("This result reports no unknown rule, no rule left unevaluated and no fund with missing or partial holdings. The assumptions and what the simulation leaves out are listed at the end.")}
          </p>
        )}
      </section>

      <Section title={t("Confirmed rules, on the portfolio after the purchase")} testId="print-rules">
        {result.rule_results.length > 0 ? (
          result.rule_results.map((ruleResult) => <RuleBlock key={ruleResult.rule_id} result={result} lookup={lookup} ruleResult={ruleResult} />)
        ) : (
          <p>{t("This report contains no rule result, so it says nothing about whether the purchase fits the rules.")}</p>
        )}
        {result.rules_not_evaluated.length > 0 ? (
          <div data-testid="print-rules-not-evaluated">
            <h3>{t("Rules in this policy version that were not evaluated")}</h3>
            <ul>
              {result.rules_not_evaluated.map((item) => (
                <li key={item.rule_id}>
                  <strong>{ruleName(lookup, item.rule_id)}</strong> ({ruleStatusLabel(item.status)}): <span lang="en">{item.reason}</span>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </Section>

      {result.starting_portfolio_findings.length > 0 ? (
        <Section
          title={t("Already not respected before the purchase")}
          note={t("These describe the portfolio as it is today. They would be there whether or not anything is bought.")}
          testId="print-starting"
        >
          {result.starting_portfolio_findings.map((finding) => {
            const ruleType = lookup(finding.rule_id)?.rule_type ?? result.rule_results.find((ruleResult) => ruleResult.rule_id === finding.rule_id)?.rule_type;
            const resolved = Math.abs(finding.purchase_effect.upper_change - finding.purchase_effect.lower_change) <= EPS;
            return (
              <article key={finding.rule_id} className="pr-rule pr-status-fail" data-testid="print-starting-finding">
                <header>
                  <h3>{ruleType ? ruleTypeLabel(ruleType) : finding.rule_id}</h3>
                  <Status status={finding.status} prefix={t("Before the purchase:")} />
                </header>
                <dl className="pr-figures">
                  <div>
                    <dt>{ruleType ? measuredNoun(ruleType) : t("Measured")}</dt>
                    <dd>{ruleType ? measuredText(ruleType, finding.measured) : formatFractionRange(finding.measured.lower, finding.measured.upper)}</dd>
                  </div>
                  <div>
                    <dt>{ruleType ? limitNoun(ruleType) : t("Limit")}</dt>
                    <dd>{formatFraction(finding.limit)}</dd>
                  </div>
                  <div>
                    <dt>{t("Gap")}</dt>
                    <dd>{ruleType ? formatGap(finding.gap, ruleDirection(ruleType), limitNoun(ruleType).toLowerCase(), measureDecimals(ruleType)) : formatFraction(finding.gap)}</dd>
                  </div>
                  <div>
                    <dt>{t("What the purchase adds")}</dt>
                    <dd>
                      {tf("{change} of the portfolio", { change: formatFractionRange(finding.purchase_effect.lower_change, finding.purchase_effect.upper_change, { signed: true }) })}
                      {resolved ? "" : ` ${t("(unresolved: proven at least the first figure, at most the second)")}`}
                    </dd>
                  </div>
                </dl>
                <p lang="en">{finding.reason}</p>
              </article>
            );
          })}
        </Section>
      ) : null}

      <div className="pr-pair">
      {portfolio ? (
        <Section
          keep
          title={t("Portfolio checked")}
          note={t("The weights this report was checked against, as the service stored them with the investigation.")}
          testId="print-portfolio"
        >
          <table>
            <thead>
              <tr>
                <th>{t("Position")}</th>
                <th>{t("Kind")}</th>
                <th className="pr-num">{t("Weight")}</th>
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
        <Section keep title={t("The purchase and the cash that funds it")} note={t(FUNDING_STATEMENT)} testId="print-cash">
          <table>
            <thead>
              <tr>
                <th>{instrumentName(instruments, purchase.instrument_id)}</th>
                <th className="pr-num">{t("Before")}</th>
                <th className="pr-num">{t("After")}</th>
                <th className="pr-num">{t("Change")}</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>{tf("Direct weight of {instrument}", { instrument: purchase.instrument_id })}</td>
                <td className="pr-num">{formatFraction(feasibility.starting_direct_weight)}</td>
                <td className="pr-num">{formatFraction(feasibility.target_direct_weight)}</td>
                <td className="pr-num">{formatChange(feasibility.additional_purchase)}</td>
              </tr>
              <tr>
                <td>{t("Cash")}</td>
                <td className="pr-num">{formatFraction(feasibility.cash_before)}</td>
                <td className="pr-num">{formatFraction(feasibility.cash_after)}</td>
                <td className="pr-num">{feasibility.status === "FEASIBLE" ? t("Sufficient") : t("Insufficient cash")}</td>
              </tr>
            </tbody>
          </table>
        </Section>
      ) : null}

      </div>

      {result.exposure && result.exposure.issuers.length > 0 ? (
        <Section
          keep
          title={t("Exposure to single companies")}
          note={t("Direct holdings plus holdings through funds. A range runs from what is proven to what is possible.")}
          testId="print-exposure"
        >
          <table>
            <thead>
              <tr>
                <th>{t("Company")}</th>
                <th className="pr-num">{t("Before the purchase")}</th>
                <th className="pr-num">{t("After: held directly")}</th>
                <th>{t("After: through funds")}</th>
                <th className="pr-num">{t("After: total")}</th>
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
                      : t("None reported")}
                  </td>
                  <td className="pr-num">{formatFractionRange(issuer.proposed.lower, issuer.proposed.upper)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="pr-note" lang="en">
            {result.exposure.selection_note}
          </p>
        </Section>
      ) : null}

      {scenario ? (
        <Section
          title={tf("Historical replay: {label}", { label: scenario.label })}
          note={t("A replay of the past on an assumed allocation. It is a separate test, not a forecast.")}
          testId="print-scenario"
        >
          <p>{tf("Period: {start} to {end}.", { start: formatDate(scenario.base_date), end: formatDate(scenario.end_date) })}</p>
          {scenario.status === "COMPUTED" ? (
            <table>
              <thead>
                <tr>
                  <th>{t("Portfolio")}</th>
                  <th className="pr-num">{t("Return over the period")}</th>
                  <th className="pr-num">{t("Deepest fall (context only)")}</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>{t("Before the purchase")}</td>
                  <td className="pr-num">{scenario.starting ? formatReturn(scenario.starting.scenario_terminal_return) : t("Not computed")}</td>
                  <td className="pr-num">{scenario.starting ? formatReturn(scenario.starting.scenario_max_drawdown) : t("Not computed")}</td>
                </tr>
                <tr>
                  <td>{t("After the purchase")}</td>
                  <td className="pr-num">{scenario.proposed ? formatReturn(scenario.proposed.scenario_terminal_return) : t("Not computed")}</td>
                  <td className="pr-num">{scenario.proposed ? formatReturn(scenario.proposed.scenario_max_drawdown) : t("Not computed")}</td>
                </tr>
              </tbody>
            </table>
          ) : (
            <p data-testid="print-scenario-insufficient">
              <strong>{t("Not computed.")}</strong>{" "}
              {scenario.missing_instruments.length > 0
                ? tf("No usable price history for: {instruments}.", { instruments: scenario.missing_instruments.join(", ") })
                : t("The price history is insufficient.")}
            </p>
          )}
          {scenario.status === "COMPUTED" && scenario.target_instrument_return !== null ? (
            <p>
              {tf("{instrument} alone over the same period: {return}, in the portfolio's currency.", {
                instrument: purchase.instrument_id,
                return: formatReturn(scenario.target_instrument_return),
              })}
            </p>
          ) : null}
          {scenario.status === "COMPUTED" && scenario.missing_instruments.length > 0 ? <p>{tf("No usable price history for: {instruments}.", { instruments: scenario.missing_instruments.join(", ") })}</p> : null}
          {scenario.assumptions.length > 0 ? (
            <div className="pr-keep" data-testid="print-scenario-assumptions">
              <h3>{t("Assumptions of the replay")}</h3>
              <ul className="pr-columns" lang="en">
                {scenario.assumptions.map((assumption) => (
                  <li key={assumption}>{assumption}</li>
                ))}
              </ul>
            </div>
          ) : null}
        </Section>
      ) : null}

      <Section keep title={t("Largest purchase that respects every confirmed rule")} testId="print-max">
        {!maxCompliant ? <p>{t("The service returned no maximum, so none is shown.")}</p> : null}
        {maxCompliant?.status === "SUPPORTED" ? (
          <>
            <p data-testid="print-max-supported">
              {tn("As a final direct weight: {final}. As an additional purchase: {additional}. Limited by: {constraint}. The same checks were run again at this weight.", {
                final: <strong>{formatFraction(maxCompliant.final_direct_weight, { rounding: "down" })}</strong>,
                additional: <strong>{formatFraction(maxCompliant.additional_purchase, { rounding: "down" })}</strong>,
                constraint: bindingConstraintText(maxCompliant.binding_constraint, (ruleId) => ruleName(lookup, ruleId)),
              })}
            </p>
            <p lang="en">{maxCompliant.reason}</p>
            <p className="pr-note">
              {t("Both figures are shown rounded down, so they never overstate the boundary. This is where the confirmed rules stop: not a suggestion to buy that amount.")}
            </p>
          </>
        ) : null}
        {maxCompliant?.status === "WITHHELD" ? (
          <p data-testid="print-max-withheld">
            <strong>{t("No maximum is shown.")}</strong> <span lang="en">{maxCompliant.reason}</span>{" "}
            {t("A maximum is given only when every confirmed rule can be evaluated at the boundary. A guess is not shown in its place.")}
          </p>
        ) : null}
        {maxCompliant?.status === "NO_FEASIBLE_PURCHASE" ? (
          <p data-testid="print-max-none">
            <strong>{t("No purchase of this instrument respects every confirmed rule.")}</strong> <span lang="en">{maxCompliant.reason}</span>{" "}
            {tf("What stands in the way: {constraint}.", { constraint: bindingConstraintText(maxCompliant.binding_constraint, (ruleId) => ruleName(lookup, ruleId)) })}
          </p>
        ) : null}
      </Section>

      {result.goal_context.length > 0 ? (
        <Section
          title={t("Context for the objectives")}
          note={t("Objectives are not rules. This is qualitative context: it is not scored and has no pass or fail.")}
          testId="print-objectives"
        >
          {contextObjectiveIds.map((objectiveId) => {
            const objective = quoted.find((candidate) => candidate.objective_id === objectiveId);
            return (
              <div key={objectiveId} className="pr-objective">
                <p>
                  <strong>
                    {objective
                      ? tn("Objective, in the words it was given: “{words}”", { words: <span lang="en">{objective.original_words}</span> })
                      : tf("Objective {id}", { id: objectiveId })}
                  </strong>
                </p>
                <ul>
                  {result.goal_context
                    .filter((item) => item.objective_id === objectiveId)
                    .map((item) => (
                      <li key={`${item.context_type}-${item.text}`}>
                        {t(CONTEXT_LABEL[item.context_type])}: <span lang="en">{item.text}</span>
                      </li>
                    ))}
                </ul>
              </div>
            );
          })}
        </Section>
      ) : null}

      <Section keep title={t("Data coverage")} note={t("How much of each fund's holdings behind these numbers was actually reported.")} testId="print-coverage">
        {result.data_coverage.length > 0 ? (
          <>
            <table>
              <thead>
                <tr>
                  <th>{t("Fund")}</th>
                  <th>{t("Holdings reported")}</th>
                  <th className="pr-num">{t("Weight in the portfolio")}</th>
                  <th className="pr-num">{t("Portfolio weight not reported")}</th>
                  <th>{t("Holdings dated")}</th>
                </tr>
              </thead>
              <tbody>
                {result.data_coverage.map((fund) => (
                  <CoverageRow key={fund.fund_id} fund={fund} instruments={instruments} />
                ))}
              </tbody>
            </table>
            {result.data_coverage.some((fund) => fund.status !== "COVERED") ? (
              <p>{t("Holdings that are not reported widen results into ranges. They are never counted as zero, and reported holdings are never rescaled to 100%.")}</p>
            ) : null}
          </>
        ) : (
          <p>{t("This result lists no fund, so nothing was looked through.")}</p>
        )}
      </Section>

      <Section keep title={t("Assumptions")} testId="print-assumptions">
        {assumptions.length > 0 ? (
          <ul className="pr-columns" lang="en">
            {assumptions.map((assumption) => (
              <li key={assumption}>{assumption}</li>
            ))}
          </ul>
        ) : (
          <p>
            {scenario && scenario.assumptions.length > 0
              ? t("No other assumption is recorded with the figures of this result.")
              : t("No assumption is recorded with the figures of this result.")}
          </p>
        )}
        {scenario && scenario.assumptions.length > 0 ? <p className="pr-note">{t("The assumptions of the historical replay are listed with the replay, above.")}</p> : null}
        <p className="pr-note">
          {t("Consistency of the confirmed rules:")}{" "}
          {result.policy_consistency.status === "PROVEN_CONFLICT"
            ? t("a contradiction between confirmed rules was proven (see the verdict).")
            : result.policy_consistency.status === "CONSISTENT"
              ? t("no supported calculation proved a contradiction between the confirmed rules.")
              : t("not assessed.")}
        </p>
      </Section>

      <Section keep title={t("Sources recorded with the figures")} testId="print-sources">
        {sources.length > 0 ? (
          <ul>
            {sources.map((source) => (
              <li key={source.sourceId} data-testid="print-source">
                <span className="pr-id">{source.sourceId}</span>: {source.uses.join("; ")}
              </li>
            ))}
          </ul>
        ) : (
          <p>{t("No source id is recorded with the figures of this result.")}</p>
        )}
        <p className="pr-note" data-testid="print-source-note">
          {t(SOURCE_DETAILS_NOTE)}
        </p>
      </Section>

      {job.explanation.length > 0 ? (
        <Section
          keep
          title={t("The result in sentences")}
          note={t("The sentences restate the figures above. The verdict is the list of confirmed rules, decided by the calculation, never by these words.")}
          testId="print-sentences"
        >
          <ul>
            {job.explanation.map((statement) => (
              <li key={statement.statement_id}>
                <span lang="en">{statement.text}</span> <span className="pr-note">[{t(originOf(statement.rendered_by).label)}]</span>
              </li>
            ))}
          </ul>
        </Section>
      ) : null}

      <div className="pr-keep">
        <Section title={t("What this simulation is and is not")} testId="print-disclosures">
          <ul className="pr-columns">
            {result.disclosures.map((disclosure) => (
              <li key={disclosure} lang="en">
                {disclosure}
              </li>
            ))}
            <li>{t("It is not personalized financial advice, not a recommendation to buy or sell, and not a forecast.")}</li>
          </ul>
        </Section>
        <p className="pr-footer" data-testid="print-footer">
          {tf("{brand} · {job} · policy version {version} · valuation date {date} · simulation on a fictional portfolio, not advice", {
            brand: BRAND_NAME,
            job: job.id,
            version: result.policy_version ?? t("none"),
            date: formatDate(result.valuation_date),
          })}
        </p>
      </div>
    </div>
  );
}
