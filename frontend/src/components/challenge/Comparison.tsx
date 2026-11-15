"use client";

import { ErrorBlock, LoadingBlock, UnknownBlock } from "@/components/ui/AsyncStates";
import { Badge, StatusBadge } from "@/components/ui/Badge";
import { Button, LinkButton } from "@/components/ui/Button";
import type { Investigation, Policy, RuleResult } from "@/lib/contracts";
import { cn } from "@/lib/cn";
import { formatFraction } from "@/lib/format";
import { ruleTypeLabel, thresholdText } from "@/lib/rules";
import { measuredText } from "@/components/verdict/RuleResults";
import { countResult, diffPolicies, isTerminalJobStatus, pairRuleResults, verdictHeadline, type RuleChangeKind } from "@/lib/verdict";
import { goToStage, stageHref } from "@/state/stage";
import { useWorkflow } from "@/state/workflow";

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
        Active rules of policy version {older.policy_version} and version {newer.policy_version}.
      </caption>
      <thead>
        <tr className="border-b-2 border-line-strong text-sm text-ink-muted">
          <th scope="col" className="py-2 pr-3 font-semibold">
            Rule
          </th>
          <th scope="col" className="py-2 pl-3 text-right font-semibold">
            Version {older.policy_version}
          </th>
          <th scope="col" className="py-2 pl-3 text-right font-semibold">
            Version {newer.policy_version}
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
                  {CHANGE_TEXT[row.kind]}
                </Badge>
              </th>
              <td className="tabular py-2.5 pl-3 text-right text-lg text-ink">{row.before ? thresholdText(row.before) : "Not in this version"}</td>
              <td className={cn("tabular py-2.5 pl-3 pr-2 text-right text-lg text-ink", row.kind === "CHANGED" && "font-bold")}>
                {row.after ? thresholdText(row.after) : "Not in this version"}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function ResultCell({ ruleResult }: { ruleResult: RuleResult | null }) {
  if (!ruleResult) return <span className="text-ink-muted">Not checked in this version</span>;
  const evaluation = ruleResult.proposed ?? ruleResult.starting;
  return (
    <span className="flex flex-col items-end gap-1">
      <StatusBadge status={evaluation.status} />
      <span className="tabular text-sm text-ink">
        measured {measuredText(evaluation).toLowerCase()} · limit {formatFraction(evaluation.limit)}
      </span>
    </span>
  );
}

function ReportCard({ label, investigation, onOpen }: { label: string; investigation: Investigation | undefined; onOpen: () => void }) {
  const result = investigation?.result ?? null;
  const headline = result ? verdictHeadline(countResult(result)) : null;
  const counts = result ? countResult(result) : null;
  return (
    <div className="flex flex-col gap-3 rounded-lg border border-line bg-surface p-4" data-testid="comparison-report">
      <p className="text-sm font-semibold text-ink-muted">{label}</p>
      {headline && counts ? (
        <>
          <p className="text-lg font-bold text-ink" data-testid="comparison-headline">
            {headline.title}
          </p>
          <p className="tabular text-ink">
            {counts.fail} fail · {counts.unknown} unknown · {counts.pass} pass
          </p>
          <div className="mt-auto">
            <Button size="sm" onClick={onOpen}>
              Open this report
            </Button>
          </div>
        </>
      ) : investigation?.status === "FAILED" ? (
        <ErrorBlock title="This investigation failed" message={investigation.error?.message ?? "No result was produced."} />
      ) : investigation && isTerminalJobStatus(investigation.status) ? (
        <UnknownBlock title="No result was returned" />
      ) : (
        <>
          <LoadingBlock
            label={
              investigation
                ? `Checking again: ${investigation.steps.length} ${investigation.steps.length === 1 ? "step" : "steps"} reported so far.`
                : "Checking again: waiting for the first status."
            }
          />
          <div>
            <LinkButton href={stageHref("investigation")} size="sm">
              See the investigation steps
            </LinkButton>
          </div>
        </>
      )}
    </div>
  );
}

/**
 * After a rule change: policy v(n) against v(n+1), and the result under each,
 * side by side. The earlier report is not altered and can still be opened.
 */
export function RuleChangeComparison() {
  const { state, actions, derived } = useWorkflow();
  const comparison = state.comparison;
  if (!comparison) return null;

  const older = state.investigations[comparison.olderId];
  const newer = state.investigations[comparison.newerId];
  const olderPolicy = older ? derived.policyByVersion(older.policy_version) : null;
  const newerPolicy = newer ? derived.policyByVersion(newer.policy_version) : derived.currentPolicy;
  const open = (id: string) => {
    actions.viewReport(id);
    goToStage("verdict");
  };

  return (
    <div className="space-y-6" data-testid="rule-change-comparison">
      {olderPolicy && newerPolicy ? (
        <div>
          <h3 className="text-lg font-semibold text-ink">What changed in the policy</h3>
          <div className="mt-2">
            <PolicyDiffTable older={olderPolicy} newer={newerPolicy} />
          </div>
        </div>
      ) : null}

      <div>
        <h3 className="text-lg font-semibold text-ink">The same purchase under each version</h3>
        <div className="mt-3 grid gap-4 md:grid-cols-2">
          <ReportCard
            label={`Earlier report — policy version ${older?.policy_version ?? "unknown"} — unchanged`}
            investigation={older}
            onOpen={() => open(comparison.olderId)}
          />
          <ReportCard
            label={`New report — policy version ${newer?.policy_version ?? newerPolicy?.policy_version ?? "unknown"}`}
            investigation={newer}
            onOpen={() => open(comparison.newerId)}
          />
        </div>
      </div>

      {older?.result && newer?.result && olderPolicy && newerPolicy ? (
        <table className="w-full border-collapse text-left" data-testid="result-comparison">
          <caption className="pb-2 text-left text-sm text-ink-muted">Each rule, after the purchase, under the two policy versions.</caption>
          <thead>
            <tr className="border-b-2 border-line-strong text-sm text-ink-muted">
              <th scope="col" className="py-2 pr-3 font-semibold">
                Rule
              </th>
              <th scope="col" className="py-2 pl-3 text-right font-semibold">
                Version {olderPolicy.policy_version}
              </th>
              <th scope="col" className="py-2 pl-3 text-right font-semibold">
                Version {newerPolicy.policy_version}
              </th>
            </tr>
          </thead>
          <tbody>
            {pairRuleResults(olderPolicy, newerPolicy, older.result, newer.result).map(({ diff, before, after }) => {
              const rule = diff.after ?? diff.before;
              if (!rule) return null;
              return (
                <tr key={rule.rule_id} className="border-b border-line align-top" data-testid="result-comparison-row">
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
      ) : null}

      <p className="text-sm text-ink-muted">
        A different result under the new version comes from the rule you changed, not from the data: both reports use the same portfolio, the same
        purchase and the same sources.
      </p>
    </div>
  );
}
