"use client";

import { useId } from "react";
import { EvidenceButton } from "@/components/evidence/EvidenceProvider";
import { UnknownBlock } from "@/components/ui/AsyncStates";
import { Notice } from "@/components/ui/Notice";
import { cn } from "@/lib/cn";
import type { CheckResult, InstrumentReturn, ScenarioMeasures, ScenarioResult } from "@/lib/contracts";
import { formatDate, formatReturn } from "@/lib/format";
import { t } from "@/lib/i18n";

const NOT_COMPUTED = "Not computed";

function ageText(days: number | null): string {
  if (days === null) return "";
  return days === 0 ? " (same day)" : ` (${days} ${days === 1 ? "day" : "days"} earlier)`;
}

function MeasureRow({ label, hint, values, testId }: { label: string; hint?: string; values: string[]; testId: string }) {
  return (
    <tr className="border-b border-line" data-testid={testId}>
      <th scope="row" className="py-2 pr-3 font-semibold text-ink">
        {label}
        {hint ? <span className="block text-sm font-normal text-ink-muted">{hint}</span> : null}
      </th>
      {values.map((value, index) => (
        <td key={index} className="tabular py-2 pl-3 text-right text-lg font-semibold text-ink">
          {value}
        </td>
      ))}
    </tr>
  );
}

/** One date a price or an exchange rate was taken from, kept on one line, with how much older it is than the date that was wanted. */
function UsedDate({ date, ageDays }: { date: string; ageDays: number | null }) {
  return (
    <>
      <span className="whitespace-nowrap">{formatDate(date)}</span>
      {ageText(ageDays)}
    </>
  );
}

/** On a phone a row is a small grid: the instrument and its return on one line, the dates on the full width below. From the sm width up it is a table row again. */
const RETURNS_ROW = "grid grid-cols-[minmax(0,1fr)_auto] gap-x-3 sm:table-row";

/**
 * Return and dates used, per instrument. Three columns from the sm width up.
 * On a phone three columns leave the dates a few words per line, so each row
 * is laid out as a grid instead and nothing has to scroll sideways. A browser
 * may stop treating a table as one when its layout is changed, so the table
 * roles are written out and the caption is tied to it by id.
 */
function InstrumentReturns({ rows }: { rows: InstrumentReturn[] }) {
  const captionId = useId();
  return (
    <table className="block w-full border-collapse text-left text-sm sm:table" role="table" aria-labelledby={captionId} data-testid="instrument-returns">
      <caption id={captionId} className="sr-only">
        {t("Return of each instrument over the replayed period, with the dates of the prices and exchange rates used")}</caption>
      <thead className="block sm:table-header-group" role="rowgroup">
        <tr className={cn(RETURNS_ROW, "border-b-2 border-line-strong text-ink-muted")} role="row">
          <th scope="col" role="columnheader" className="pt-1.5 font-semibold sm:py-1.5 sm:pr-3 sm:align-bottom">
            {t("Instrument")}</th>
          <th scope="col" role="columnheader" className="pt-1.5 text-right font-semibold sm:py-1.5 sm:pl-3 sm:align-bottom">
            {t("Return in CAD")}</th>
          <th scope="col" role="columnheader" className="col-span-2 pb-1.5 font-semibold sm:py-1.5 sm:pl-3 sm:align-bottom">
            {t("Dates of the prices and exchange rates used")}</th>
        </tr>
      </thead>
      <tbody className="block sm:table-row-group" role="rowgroup">
        {rows.map((row) => (
          <tr key={row.instrument_id} className={cn(RETURNS_ROW, "border-b border-line text-ink")} role="row" data-testid="instrument-return" data-instrument-id={row.instrument_id}>
            <th scope="row" role="rowheader" className="pt-1.5 font-semibold sm:py-1.5 sm:pr-3 sm:align-top">
              {row.instrument_id} <span className="font-normal text-ink-muted">({row.currency})</span>
            </th>
            <td role="cell" className="tabular pt-1.5 text-right sm:py-1.5 sm:pl-3 sm:align-top">
              {formatReturn(row.return_cad)}
            </td>
            <td role="cell" className="tabular col-span-2 pb-1.5 sm:py-1.5 sm:pl-3 sm:align-top">
              <span className="block" data-testid="price-dates">
                <span className="text-ink-muted">{t("Prices:")}</span> <UsedDate date={row.base_price_date} ageDays={row.base_price_age_days} /> {t("and")}{" "}
                <UsedDate date={row.end_price_date} ageDays={row.end_price_age_days} />
              </span>
              <span className="block" data-testid="fx-dates">
                <span className="text-ink-muted">{t("Exchange rates:")}</span>{" "}
                {row.base_fx_date && row.end_fx_date ? (
                  <>
                    <UsedDate date={row.base_fx_date} ageDays={row.base_fx_age_days} /> {t("and")} <UsedDate date={row.end_fx_date} ageDays={row.end_fx_age_days} />
                  </>
                ) : (
                  "none needed"
                )}
              </span>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function measureCells(measures: ScenarioMeasures | null) {
  return {
    terminal: measures ? formatReturn(measures.scenario_terminal_return) : NOT_COMPUTED,
    drawdown: measures ? formatReturn(measures.scenario_max_drawdown) : NOT_COMPUTED,
    drawdownDate: measures?.max_drawdown_date ? formatDate(measures.max_drawdown_date) : NOT_COMPUTED,
  };
}

/**
 * The historical replay, kept apart from the exposure rules. It answers one
 * narrow question — what would this allocation, bought once and held, have
 * done over a past period — and says on every figure that it is not a
 * forecast. Whether the loss budget is respected is decided by the engine on
 * the rule itself; nothing is compared or recomputed here.
 */
export function ScenarioPanel({ result, scenario }: { result: CheckResult; scenario: ScenarioResult }) {
  const before = measureCells(scenario.starting);
  const after = measureCells(scenario.proposed);
  const target = result.purchase_request.instrument_id;
  return (
    <div className="space-y-5" data-testid="scenario-panel" data-scenario-status={scenario.status}>
      <Notice tone="caution" title="A replay of the past: not a forecast">
        <p data-testid="scenario-note">
          {scenario.label}{t(". The allocation is assumed to have been bought once on")} <span className="tabular">{formatDate(scenario.base_date)}</span>{" "}
          {t("and held to")} <span className="tabular">{formatDate(scenario.end_date)}</span>{t(". It says what would have happened in that period only. It predicts nothing and guarantees nothing.")}</p>
      </Notice>

      {scenario.status === "INSUFFICIENT_HISTORY" ? (
        <UnknownBlock title={t("Not enough price history to replay this allocation")}>
          <p data-testid="scenario-insufficient">
            {scenario.missing_instruments.length > 0
              ? `No usable price history for: ${scenario.missing_instruments.join(", ")}.`
              : "A price or an exchange rate needed for the period is missing."}{" "}
            {t("No figure is shown in its place.")}</p>
        </UnknownBlock>
      ) : null}

      <table className="w-full border-collapse text-left" data-testid="scenario-table">
        <caption className="sr-only">{t("Replay results before and after the purchase. Historical replay, not a forecast.")}</caption>
        <thead>
          <tr className="border-b-2 border-line-strong text-sm text-ink-muted">
            <td className="py-2 pr-3" />
            <th scope="col" className="py-2 pl-3 text-right font-semibold">
              {t("Before the purchase")}</th>
            <th scope="col" className="py-2 pl-3 text-right font-semibold">
              {t("After the purchase")}</th>
          </tr>
        </thead>
        <tbody>
          <MeasureRow
            testId="scenario-terminal"
            label={t("Change over the whole period")}
            hint={t("value at the end compared with the start")}
            values={[before.terminal, after.terminal]}
          />
          <MeasureRow
            testId="scenario-drawdown"
            label={t("Deepest fall inside the period")}
            hint={t("from the highest value reached to the lowest after it")}
            values={[before.drawdown, after.drawdown]}
          />
          <MeasureRow testId="scenario-drawdown-date" label={t("Date of the lowest point")} values={[before.drawdownDate, after.drawdownDate]} />
        </tbody>
      </table>

      {scenario.target_instrument_return !== null ? (
        <p className="text-ink" data-testid="scenario-target-return">
          {target} {t("alone over the same period:")} <span className="tabular font-semibold">{formatReturn(scenario.target_instrument_return)}</span>{t(", in Canadian dollars.")}</p>
      ) : null}
      {scenario.status === "COMPUTED" && scenario.missing_instruments.length > 0 ? (
        <p className="text-ink" data-testid="scenario-missing">
          {t("No usable price history for:")} {scenario.missing_instruments.join(", ")}.
        </p>
      ) : null}

      <p className="text-sm text-ink-muted">
        {t("Whether the loss budget is respected is decided on the rule itself, in the list of confirmed rules above. The deepest fall is context: it is not one of the rules.")}</p>

      {scenario.assumptions.length > 0 ? (
        <details>
          <summary className="min-h-6 font-semibold text-ink">{t("Assumptions of the replay (")}{scenario.assumptions.length})</summary>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-ink" data-testid="scenario-assumptions">
            {scenario.assumptions.map((assumption) => (
              <li key={assumption}>{assumption}</li>
            ))}
          </ul>
        </details>
      ) : null}
      {scenario.instrument_returns.length > 0 ? (
        <details>
          <summary className="min-h-6 font-semibold text-ink">{t("Return of each instrument and the dates of the prices used (")}{scenario.instrument_returns.length})</summary>
          <div className="mt-2">
            <InstrumentReturns rows={scenario.instrument_returns} />
          </div>
        </details>
      ) : null}

      <EvidenceButton label={t("the historical replay")} result={result} evidenceIds={scenario.evidence_ids} />
    </div>
  );
}
