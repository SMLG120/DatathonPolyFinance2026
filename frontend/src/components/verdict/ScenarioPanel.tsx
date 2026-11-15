"use client";

import { EvidenceButton } from "@/components/evidence/EvidenceProvider";
import { StatusBadge } from "@/components/ui/Badge";
import { Notice } from "@/components/ui/Notice";
import type { CheckResult, ScenarioMeasurement, ScenarioResult } from "@/lib/contracts";
import { formatDate, formatFraction, formatGap, UNKNOWN_TEXT } from "@/lib/format";

const SCENARIO_NOTES: Record<string, string> = {
  replay_2022: "Replay of an assumed allocation through 2022 — not a forecast",
};

/** The label every scenario figure carries. */
export function scenarioNote(scenario: Pick<ScenarioResult, "scenario_id" | "period_start" | "period_end">): string {
  return (
    SCENARIO_NOTES[scenario.scenario_id] ??
    `Replay of an assumed allocation from ${formatDate(scenario.period_start)} to ${formatDate(scenario.period_end)} — not a forecast`
  );
}

/** A terminal return worded as a loss: -0.178 -> "17.8% loss"; a gain is said to be no loss. */
export function lossText(terminalReturn: number | null): string {
  if (terminalReturn === null || !Number.isFinite(terminalReturn)) return UNKNOWN_TEXT;
  if (terminalReturn < 0) return `${formatFraction(-terminalReturn)} loss`;
  return `No loss (${formatFraction(terminalReturn, { signed: true })})`;
}

function measurementCells(measurement: ScenarioMeasurement | null) {
  return {
    loss: measurement ? lossText(measurement.scenario_terminal_return) : "Not evaluated",
    endReturn: measurement ? formatFraction(measurement.scenario_terminal_return, { signed: true }) : "Not evaluated",
    drawdown: measurement ? formatFraction(measurement.scenario_max_drawdown) : "Not evaluated",
  };
}

/**
 * The scenario risk budget, kept apart from the exposure rules. It answers one
 * narrow question — would this allocation, held through a past period, have
 * lost more than the budget the user chose — and says so on every figure.
 */
export function ScenarioPanel({ result, scenario }: { result: CheckResult; scenario: ScenarioResult }) {
  const decisive = scenario.proposed ?? scenario.starting;
  const before = measurementCells(scenario.starting);
  const after = measurementCells(scenario.proposed);
  const note = scenarioNote(scenario);

  return (
    <div className="space-y-5" data-testid="scenario-panel">
      <Notice tone="caution" title={note}>
        <p data-testid="scenario-note">
          The allocation is assumed to have been bought once and held from <span className="tabular">{formatDate(scenario.period_start)}</span> to{" "}
          <span className="tabular">{formatDate(scenario.period_end)}</span>. It says what would have happened in that period only. It predicts
          nothing and guarantees nothing.
        </p>
      </Notice>

      <dl className="grid gap-x-6 gap-y-4 sm:grid-cols-3">
        <div>
          <dt className="text-sm font-semibold text-ink-muted">Measured scenario loss{scenario.proposed ? ", after the purchase" : ""}</dt>
          <dd className="tabular text-2xl font-bold text-ink" data-testid="scenario-loss">
            {lossText(decisive.scenario_terminal_return)}
          </dd>
          <dd className="text-sm text-ink-muted">at the end of the period</dd>
        </div>
        <div>
          <dt className="text-sm font-semibold text-ink-muted">Loss budget you confirmed</dt>
          <dd className="tabular text-2xl font-bold text-ink" data-testid="scenario-budget">
            {scenario.budget === null ? "None confirmed" : formatFraction(scenario.budget)}
          </dd>
        </div>
        <div>
          <dt className="text-sm font-semibold text-ink-muted">Gap</dt>
          <dd className="tabular text-lg font-semibold text-ink" data-testid="scenario-gap">
            {scenario.budget === null ? "No budget to compare with" : formatGap(scenario.gap).replace("the limit", "the budget")}
          </dd>
          {scenario.status ? (
            <dd className="mt-1">
              <StatusBadge status={scenario.status} />
            </dd>
          ) : null}
        </div>
      </dl>

      <table className="w-full border-collapse text-left" data-testid="scenario-table">
        <caption className="pb-2 text-left text-sm text-ink-muted">{note}. Values in CAD.</caption>
        <thead>
          <tr className="border-b-2 border-line-strong text-sm text-ink-muted">
            <td className="py-2 pr-3" />
            <th scope="col" className="py-2 pl-3 text-right font-semibold">
              Before the purchase
            </th>
            <th scope="col" className="py-2 pl-3 text-right font-semibold">
              After the purchase
            </th>
          </tr>
        </thead>
        <tbody>
          <tr className="border-b border-line">
            <th scope="row" className="py-2 pr-3 text-sm font-semibold text-ink-muted">
              Loss at the end of the period — compared with the budget
            </th>
            <td className="tabular py-2 pl-3 text-right font-semibold text-ink">{before.loss}</td>
            <td className="tabular py-2 pl-3 text-right text-lg font-bold text-ink">{after.loss}</td>
          </tr>
          <tr className="border-b border-line">
            <th scope="row" className="py-2 pr-3 text-sm font-semibold text-ink-muted">
              Return over the period
            </th>
            <td className="tabular py-2 pl-3 text-right text-ink">{before.endReturn}</td>
            <td className="tabular py-2 pl-3 text-right text-ink">{after.endReturn}</td>
          </tr>
          <tr className="border-b border-line">
            <th scope="row" className="py-2 pr-3 text-sm font-semibold text-ink-muted">
              Deepest fall during the period — context only, not compared with the budget
            </th>
            <td className="tabular py-2 pl-3 text-right text-ink">{before.drawdown}</td>
            <td className="tabular py-2 pl-3 text-right text-ink">{after.drawdown}</td>
          </tr>
        </tbody>
      </table>

      <div>
        <h3 className="font-semibold text-ink">Assumptions of the replay</h3>
        {scenario.assumptions.length > 0 ? (
          <ul className="mt-1 list-disc space-y-1 pl-5 text-ink">
            {scenario.assumptions.map((assumption) => (
              <li key={assumption}>{assumption}</li>
            ))}
          </ul>
        ) : (
          <p className="mt-1 text-ink-muted">None recorded.</p>
        )}
      </div>

      <EvidenceButton label="the scenario loss" result={result} evidenceIds={scenario.evidence_ids} />
    </div>
  );
}
