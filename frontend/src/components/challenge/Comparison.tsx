"use client";

import { ErrorBlock, LoadingBlock, UnknownBlock } from "@/components/ui/AsyncStates";
import { Badge, StatusBadge } from "@/components/ui/Badge";
import { Button, LinkButton } from "@/components/ui/Button";
import { TestDataTag } from "@/components/ui/TestDataTag";
import { measuredText } from "@/components/verdict/RuleMeasure";
import type { InvestigationJob, Policy, Portfolio, RuleResult } from "@/lib/contracts";
import { cn } from "@/lib/cn";
import { portfolioCheckedLabel } from "@/lib/customize";
import { formatFraction } from "@/lib/format";
import { assessResult } from "@/lib/result";
import { limitNoun, ruleTypeLabel, thresholdText } from "@/lib/rules";
import { isTerminalJobStatus, pairRuleResults, diffPolicies, summaryCounts, verdictHeadline, type RuleChangeKind } from "@/lib/verdict";
import { goToStage, stageHref } from "@/state/stage";
import { useWorkflow } from "@/state/workflow";
import { t } from "@/lib/i18n";

const CHANGE_TEXT: Record<RuleChangeKind, string> = {
  CHANGED: "Changed",
  ADDED: "Added",
  REMOVED: "Removed",
  UNCHANGED: "Unchanged",
};

/** The rules in force in two policy versions, side by side, with what changed in words. */
export function PolicyDiffTable({ older, newer }: { older: Policy; newer: Policy }) {
  const rows = diffPolicies(older, newer);
  return (
    <table className="w-full border-collapse text-left" data-testid="policy-diff">
      <caption className="pb-2 text-left text-sm text-ink-muted">
        {t("Rules in force in policy version")} {older.version} {t("and in version")} {newer.version}.
      </caption>
      <thead>
        <tr className="border-b-2 border-line-strong text-sm text-ink-muted">
          <th scope="col" className="py-2 pr-3 font-semibold">
            {t("Rule")}</th>
          <th scope="col" className="py-2 pl-3 text-right font-semibold">
            {t("Version")} {older.version}
          </th>
          <th scope="col" className="py-2 pl-3 text-right font-semibold">
            {t("Version")} {newer.version}
          </th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => {
          const rule = row.after ?? row.before;
          if (!rule) return null;
          return (
            <tr key={rule.rule_id} className={cn("border-b border-line", row.kind !== "UNCHANGED" && "bg-accent-soft")} data-testid="policy-diff-row" data-change={row.kind}>
              <th scope="row" className="py-2.5 pl-2 pr-3 font-normal">
                <span className="block font-semibold text-ink">{ruleTypeLabel(rule.rule_type)}</span>
                <Badge tone={row.kind === "UNCHANGED" ? "neutral" : "accent"} className="mt-1 py-0 leading-5">
                  {t(CHANGE_TEXT[row.kind])}
                </Badge>
              </th>
              <td className="tabular py-2.5 pl-3 text-right text-lg text-ink">{row.before ? thresholdText(row.before) : t("Not in this version")}</td>
              <td className={cn("tabular py-2.5 pl-3 pr-2 text-right text-lg text-ink", row.kind === "CHANGED" && "font-bold")}>
                {row.after ? thresholdText(row.after) : t("Not in this version")}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function ResultCell({ ruleResult }: { ruleResult: RuleResult | null }) {
  if (!ruleResult) return   <span className="text-ink-muted">{t("Not checked in this version")}</span>;
  return (
    <span className="flex flex-col items-end gap-1">
      <StatusBadge status={ruleResult.status} />
      <span className="tabular text-sm text-ink">
        {t("measured")} {measuredText(ruleResult.rule_type, ruleResult.measured).toLowerCase()} · {limitNoun(ruleResult.rule_type).toLowerCase()}{" "}
        {formatFraction(ruleResult.limit)}
      </span>
    </span>
  );
}

function ReportCard({ label, job, onOpen }: { label: string; job: InvestigationJob | undefined; onOpen: () => void }) {
  const assessment = job?.status === "SUCCEEDED" && job.result !== null ? assessResult(job.result) : null;
  return (
    <div className="flex flex-col gap-3 rounded-lg border border-line bg-surface p-4" data-testid="comparison-report" data-figures={assessment?.kind === "ok" ? "true" : undefined}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <p className="text-sm font-semibold text-ink-muted">{label}</p>
        {assessment?.kind === "ok" ? <TestDataTag /> : null}
      </div>
      {assessment?.kind === "ok" ? (
        <>
          <p className="text-lg font-bold text-ink" data-testid="comparison-headline">
            {verdictHeadline(assessment.result.summary).title}
          </p>
          <p className="tabular text-ink" data-testid="comparison-counts">
            {summaryCounts(assessment.result.summary).fail} {t("fail ·")} {summaryCounts(assessment.result.summary).unknown} {t("unknown ·")}{" "}
            {summaryCounts(assessment.result.summary).pass} {t("pass")}</p>
          <div className="mt-auto">
            <Button size="sm" onClick={onOpen}>
              {t("Open this report")}</Button>
          </div>
        </>
      ) : assessment?.kind === "not_executed" ? (
        <UnknownBlock title={t("The check did not run")}>
          <p>{assessment.result.execution.message ?? "The service gave no reason."} {t("No rule was evaluated, so there is no verdict.")}</p>
        </UnknownBlock>
      ) : assessment?.kind === "unreadable" ? (
        <UnknownBlock title={t("The result could not be read")} />
      ) : job?.status === "FAILED" ? (
        <ErrorBlock title={t("This investigation failed")} message={job.failure?.message ?? "No result was produced."} />
      ) : job && isTerminalJobStatus(job.status) ? (
        <UnknownBlock title={t("No result was returned")} />
      ) : (
        <>
          <LoadingBlock
            label={job ? `Checking again: ${job.steps.length} ${job.steps.length === 1 ? "step" : "steps"} reported so far.` : "Checking again: waiting for the first status."}
          />
          <div>
            <LinkButton href={stageHref("investigation")} size="sm">
              {t("See the investigation steps")}</LinkButton>
          </div>
        </>
      )}
    </div>
  );
}

/**
 * Whether the two reports were checked against the same portfolio, as far as the two jobs say:
 * - "same": both jobs carry a portfolio and the ids are equal;
 * - "different": both carry one and the ids differ;
 * - "legacy": both jobs are known and neither carries one (stored before jobs kept their portfolio:
 *   each was then checked against the scenario portfolio, contracts/api.md section 2a);
 * - "pending": the new job has not reported anything yet;
 * - "unknown": only one of the two carries a portfolio, so sameness cannot be confirmed.
 * Nothing is inferred from the weights: only the ids the service gave are compared.
 */
export type PortfolioMatch = "same" | "different" | "legacy" | "pending" | "unknown";

export function portfolioMatch(older: InvestigationJob | undefined, newer: InvestigationJob | undefined): PortfolioMatch {
  if (!newer) return "pending";
  const before = older?.portfolio;
  const after = newer.portfolio;
  if (before && after) return before.portfolio_id === after.portfolio_id ? "same" : "different";
  if (!before && !after) return older ? "legacy" : "unknown";
  return "unknown";
}

/**
 * After a rule change: policy v(n) against v(n+1), and the result under each,
 * side by side. The earlier report is not altered and can still be opened.
 * Every figure is read from the two results; nothing is compared by
 * calculation here.
 */
export function RuleChangeComparison() {
  const { state, actions, derived } = useWorkflow();
  const comparison = state.comparison;
  if (!comparison) return null;
  const scenarioData = state.portfolio.data?.scenario ?? null;

  const older = state.investigations[comparison.olderId];
  const newer = state.investigations[comparison.newerId];
  const olderPolicy = older ? derived.policyFor(older) : null;
  const newerPolicy = newer ? derived.policyFor(newer) : derived.currentPolicy;
  const olderResult = older?.result ? assessResult(older.result) : null;
  const newerResult = newer?.result ? assessResult(newer.result) : null;
  const open = (id: string) => {
    actions.viewReport(id);
    goToStage("verdict");
  };
  const match = portfolioMatch(older, newer);
  const named = (portfolio: Portfolio) => (
    <span className="font-semibold text-ink">{portfolioCheckedLabel(portfolio, scenarioData?.portfolio ?? null, scenarioData?.persona.display_name ?? "This persona")}</span>
  );

  return (
    <div className="space-y-8" data-testid="rule-change-comparison">
      {olderPolicy && newerPolicy ? (
        <section aria-labelledby="comparison-policy-title">
          <h3 id="comparison-policy-title" className="text-lg font-semibold text-ink">
            {t("What changed in the policy")}</h3>
          <div className="mt-2">
            <PolicyDiffTable older={olderPolicy} newer={newerPolicy} />
          </div>
        </section>
      ) : null}

      <section aria-labelledby="comparison-reports-title">
        <h3 id="comparison-reports-title" className="text-lg font-semibold text-ink">
          The same purchase under each version
        </h3>
        {/* Said from the two jobs' own portfolio ids. Sameness is claimed only when both jobs carry the same id. */}
        {older?.portfolio || newer?.portfolio ? (
          <p className="mt-1 text-sm text-ink-muted" data-testid="comparison-portfolio" data-portfolio-match={match}>
            {match === "same" && older?.portfolio ? (
              <>Both reports were checked against the portfolio stored with the earlier one: {named(older.portfolio)}.</>
            ) : match === "different" && older?.portfolio && newer?.portfolio ? (
              <>
                The two reports were not checked against the same portfolio. The earlier report used: {named(older.portfolio)}. The new report used:{" "}
                {named(newer.portfolio)}.
              </>
            ) : match === "pending" && older?.portfolio ? (
              <>The earlier report was checked against: {named(older.portfolio)}. The new check has not reported its portfolio yet.</>
            ) : older?.portfolio ? (
              <>
                The earlier report was checked against: {named(older.portfolio)}. The service did not say which portfolio the new report was checked against,
                so this page cannot confirm that both used the same one.
              </>
            ) : newer?.portfolio ? (
              <>
                The new report was checked against: {named(newer.portfolio)}. The service did not say which portfolio the earlier report was checked
                against, so this page cannot confirm that both used the same one.
              </>
            ) : null}
          </p>
        ) : null}
        <div className="mt-3 grid gap-4 md:grid-cols-2">
          <ReportCard label={`Earlier report: policy version ${older?.policy_version ?? "unknown"}: unchanged`} job={older} onOpen={() => open(comparison.olderId)} />
          <ReportCard label={`New report: policy version ${newer?.policy_version ?? newerPolicy?.version ?? "unknown"}`} job={newer} onOpen={() => open(comparison.newerId)} />
        </div>
      </section>

      {olderResult?.kind === "ok" && newerResult?.kind === "ok" && olderPolicy && newerPolicy ? (
        <section aria-labelledby="comparison-rules-title" data-figures="true">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <h3 id="comparison-rules-title" className="text-lg font-semibold text-ink">
              {t("Each rule under the two versions")}</h3>
            <TestDataTag />
          </div>
          <table className="mt-2 w-full border-collapse text-left" data-testid="result-comparison">
            <caption className="pb-2 text-left text-sm text-ink-muted">{t("Each rule, after the purchase, as reported under the two policy versions.")}</caption>
            <thead>
              <tr className="border-b-2 border-line-strong text-sm text-ink-muted">
                <th scope="col" className="py-2 pr-3 font-semibold">
                  {t("Rule")}</th>
                <th scope="col" className="py-2 pl-3 text-right font-semibold">
                  {t("Version")} {olderPolicy.version}
                </th>
                <th scope="col" className="py-2 pl-3 text-right font-semibold">
                  {t("Version")} {newerPolicy.version}
                </th>
              </tr>
            </thead>
            <tbody>
              {pairRuleResults(olderPolicy, newerPolicy, olderResult.result, newerResult.result).map(({ diff, before, after }) => {
                const rule = diff.after ?? diff.before;
                if (!rule) return null;
                return (
                  <tr key={rule.rule_id} className="border-b border-line align-top" data-testid="result-comparison-row" data-change={diff.kind}>
                    <th scope="row" className="py-3 pr-3 font-semibold text-ink">
                      {ruleTypeLabel(rule.rule_type)}
                    </th>
                    <td className="py-3 pl-3 text-right">
                      <ResultCell ruleResult={before} />
                    </td>
                    <td className="py-3 pl-3 text-right">
                      <ResultCell ruleResult={after} />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </section>
      ) : null}

      <p className="text-sm text-ink-muted" data-testid="comparison-cause" data-portfolio-match={match}>
        {match === "same" || match === "legacy"
          ? "A different result under the new version comes from the rule that was changed, not from the data: both reports use the same portfolio, the same purchase and the same sources."
          : match === "different"
            ? "The two reports were not checked against the same portfolio, so a different result under the new version can come from the portfolio as well as from the rule that was changed."
            : match === "pending"
              ? "A different result under the new version comes from the rule that was changed only if the two reports were checked against one portfolio. That is known once the new check reports its portfolio."
              : "A different result under the new version comes from the rule that was changed only if the two reports were checked against one portfolio, which this page cannot confirm for these two."}
      </p>
    </div>
  );
}
