"use client";

import { useId } from "react";
import { ChevronIcon } from "@/components/ui/icons";
import type { Exposure, ExposureBreakdown, IssuerExposure } from "@/lib/contracts";
import { cn } from "@/lib/cn";
import { EPS, formatFraction, formatFractionRange } from "@/lib/format";

export interface ExposureChartProps {
  /** The engine's chart rows: at most ten companies, in the engine's order. Every value drawn is one of its fields. */
  exposure: Exposure;
  /** The threshold drawn as a marker, or null when no limit on any single company was evaluated. */
  limit: number | null;
  /** "Confirmed limit" or "Draft limit". */
  limitLabel?: string;
  /** The company whose breakdown is open at first, when it is among the rows (the one being bought). */
  openIssuerId?: string | null;
  /** The chart's caption. The default names the chart of every company the engine sent. */
  caption?: string;
}

const AXIS_STEPS: [max: number, step: number][] = [
  [0.02, 0.005],
  [0.05, 0.01],
  [0.1, 0.02],
  [0.15, 0.05],
  [0.2, 0.05],
  [0.25, 0.05],
  [0.3, 0.1],
  [0.4, 0.1],
  [0.5, 0.1],
  [0.6, 0.2],
  [0.75, 0.25],
  [1, 0.25],
];

/** A round axis end that leaves headroom above the largest value, and the tick step that goes with it. Geometry only. */
export function exposureAxis(values: number[]): { max: number; ticks: number[] } {
  const largest = Math.max(0, ...values.filter((value) => Number.isFinite(value)));
  const [max, step] = AXIS_STEPS.find(([candidate]) => candidate + EPS >= largest * 1.1) ?? [1, 0.25];
  const ticks: number[] = [];
  for (let index = 0; index * step <= max + EPS; index += 1) ticks.push(Number((index * step).toFixed(6)));
  return { max, ticks };
}

const percent = (value: number, max: number) => `${Math.min(100, Math.max(0, (value / max) * 100))}%`;

function tickText(tick: number, step: number): string {
  return formatFraction(tick, { decimals: step < 0.01 - EPS ? 1 : 0 });
}

/** The fund ids of a row, in the order the engine lists them: after the purchase first, then any only listed before it. */
function fundIds(issuer: IssuerExposure): string[] {
  const ids = issuer.proposed.indirect_by_fund.map((part) => part.fund_id);
  for (const part of issuer.starting.indirect_by_fund) if (!ids.includes(part.fund_id)) ids.push(part.fund_id);
  return ids;
}

const GRID = "grid grid-cols-[9.5rem_minmax(0,1fr)] gap-x-2 sm:grid-cols-[minmax(7rem,10rem)_10rem_minmax(0,1fr)] sm:gap-x-3";

/** One state of one company as a bar: direct, one segment per fund, then the part that cannot be measured. */
function StateBar({ state, possibleExtra, axisMax, limit, thin = false }: { state: ExposureBreakdown; possibleExtra: number; axisMax: number; limit: number | null; thin?: boolean }) {
  return (
    <span className="byb-bar block w-full" data-size={thin ? "thin" : undefined} aria-hidden="true">
      <span className="byb-bar-track">
        {state.direct > EPS ? <span className="byb-seg" data-seg="direct" style={{ width: percent(state.direct, axisMax), minWidth: 4 }} /> : null}
        {state.indirect_by_fund.map((part) =>
          part.known > EPS ? (
            <span key={part.fund_id} className="byb-seg" data-seg="indirect" data-fund={part.fund_id} style={{ width: percent(part.known, axisMax), minWidth: 4 }} />
          ) : null,
        )}
        {possibleExtra > EPS ? <span className="byb-seg" data-seg="possible" style={{ width: percent(possibleExtra, axisMax), minWidth: 6 }} /> : null}
      </span>
      {limit !== null ? <span className="byb-limit" style={{ left: percent(limit, axisMax) }} data-testid="limit-marker" /> : null}
    </span>
  );
}

function StateText({ label, state, testId }: { label: string; state: ExposureBreakdown; testId: string }) {
  return (
    <span className="tabular text-sm text-ink" data-testid={testId}>
      <span className="text-ink-muted">{label}</span> <span className="font-semibold">{formatFractionRange(state.lower, state.upper)}</span>
    </span>
  );
}

/** The breakdown shows two decimals, so its parts can be added up by hand against the totals. */
const DETAIL = { decimals: 2 } as const;

function BreakdownTable({ issuer, exposure, limit, limitLabel }: { issuer: IssuerExposure; exposure: Exposure; limit: number | null; limitLabel: string }) {
  const states = [issuer.starting, issuer.proposed];
  const extras = [exposure.possible_extra.starting, exposure.possible_extra.proposed];
  return (
    <table className="w-full max-w-2xl border-collapse text-left" data-testid="exposure-breakdown">
      <caption className="sr-only">{issuer.name}: the values drawn in the bars, as a share of the portfolio</caption>
      <thead>
        <tr className="border-b-2 border-line-strong text-sm text-ink-muted">
          <td className="py-1.5 pr-3" />
          <th scope="col" className="py-1.5 pl-3 text-right font-semibold">
            Before the purchase
          </th>
          <th scope="col" className="py-1.5 pl-3 text-right font-semibold">
            After the purchase
          </th>
        </tr>
      </thead>
      <tbody>
        <ValueRow label="Direct holding" rowKey="direct" values={states.map((state) => formatFraction(state.direct, DETAIL))} />
        {fundIds(issuer).map((fundId) => (
          <ValueRow
            key={fundId}
            rowKey={`fund-${fundId}`}
            label={`Through ${fundId}, from its reported holdings`}
            values={states.map((state) => {
              const part = state.indirect_by_fund.find((candidate) => candidate.fund_id === fundId);
              return part ? formatFraction(part.known, DETAIL) : "Not listed";
            })}
          />
        ))}
        <ValueRow label="Proven total" rowKey="lower" strong values={states.map((state) => formatFraction(state.lower, DETAIL))} />
        <ValueRow
          label="Possible extra, not measured"
          rowKey="possible"
          values={extras.map((extra) => (extra > EPS ? `up to ${formatFraction(extra, DETAIL)}` : "None"))}
        />
        <ValueRow label="Possible range" rowKey="range" strong values={states.map((state) => formatFractionRange(state.lower, state.upper, DETAIL))} />
        {limit !== null ? <ValueRow label={limitLabel} rowKey="limit" values={states.map(() => formatFraction(limit, DETAIL))} /> : null}
      </tbody>
    </table>
  );
}

function ValueRow({ label, rowKey, values, strong = false }: { label: string; rowKey: string; values: string[]; strong?: boolean }) {
  return (
    <tr className="border-b border-line" data-row={rowKey}>
      <th scope="row" className="py-1.5 pr-3 text-sm font-semibold text-ink-muted">
        {label}
      </th>
      {values.map((value, index) => (
        <td key={index} className={cn("tabular py-1.5 pl-3 text-right text-ink", strong && "font-bold")}>
          {value}
        </td>
      ))}
    </tr>
  );
}

/**
 * Exposure to single companies, before and after the purchase, as stacked
 * horizontal bars against a limit.
 *
 * - Solid segments in one hue: the direct holding (dark), then one lighter
 *   segment per fund, from its reported holdings.
 * - Fund weight that is not attributed to any company is drawn hollow and
 *   dashed, so a possible range is never mistaken for a measured amount.
 * - Each row is a native <details>: Enter, Space, a click or a tap on the row
 *   opens a table with the value of every segment. Nothing depends on hover,
 *   and the bars themselves are decoration next to the same numbers as text.
 * - Every value is a field of the engine's result. The only arithmetic here is
 *   the geometry of the drawing.
 */
export function ExposureChart({
  exposure,
  limit,
  limitLabel = "Confirmed limit",
  openIssuerId = null,
  caption = "Exposure to single companies, as a share of the portfolio",
}: ExposureChartProps) {
  const captionId = useId();
  const axis = exposureAxis([...exposure.issuers.flatMap((issuer) => [issuer.starting.upper, issuer.proposed.upper]), limit ?? 0]);
  const step = axis.ticks[1] ?? axis.max;
  const extras = exposure.possible_extra;
  const hasPossible = extras.starting > EPS || extras.proposed > EPS;
  /** The label goes on the side of the marker that has more room. Geometry only. */
  const limitNearEnd = limit !== null && limit / axis.max > 0.5;

  return (
    <figure className="byb-chart" aria-labelledby={captionId} data-testid="exposure-chart">
      <figcaption id={captionId} className="font-semibold text-ink">
        {caption}
      </figcaption>
      <p className="mt-1 text-sm text-ink-muted">Select a company to see the value of each part of its bars.</p>

      {/*
        Limit label. From the md width up it sits at the marker, on the side with more room, and the spacer beside it
        gives way before the label could leave the track. Below that the track is too narrow for it, so the label is a
        line of its own, led by the marker's glyph, and the marker itself is found on the bars below.
      */}
      <div className={cn(GRID, "mt-3")} aria-hidden="true">
        <span className="hidden md:block" />
        <span className="hidden md:block" />
        <span
          className={cn("col-span-2 flex min-h-6 items-end justify-end text-sm sm:col-span-3 md:col-span-1", !limitNearEnd && "md:justify-start")}
          data-testid="limit-label-row"
        >
          {limit !== null ? (
            <>
              {limitNearEnd ? null : <span className="hidden shrink md:block" style={{ flexBasis: percent(limit, axis.max) }} />}
              <span
                className={cn("tabular inline-flex shrink-0 items-center whitespace-nowrap pb-0.5 font-semibold text-ink", limitNearEnd ? "md:pr-1.5" : "md:pl-1.5")}
                data-key="limit"
                data-testid="limit-label"
              >
                <span className="inline-flex md:hidden">
                  <span className="byb-swatch" data-seg="limit" />
                </span>
                {limitLabel} {formatFraction(limit)}
              </span>
              {limitNearEnd ? <span className="hidden shrink md:block" style={{ flexBasis: `calc(100% - ${percent(limit, axis.max)})` }} /> : null}
            </>
          ) : null}
        </span>
      </div>

      <ul data-testid="exposure-rows">
        {exposure.issuers.map((issuer) => (
          <li key={issuer.issuer_id} className="border-t border-line" data-testid="exposure-row" data-issuer-id={issuer.issuer_id}>
            <details open={issuer.issuer_id === openIssuerId ? true : undefined}>
              <summary className="byb-summary block rounded-md py-2">
                <span className={cn(GRID, "items-center gap-y-1")}>
                  <span className="col-span-2 flex min-w-0 items-start gap-1.5 sm:col-span-1 sm:row-span-2 sm:self-start">
                    <ChevronIcon size={16} className="mt-1 text-ink-muted" />
                    <span className="min-w-0 font-semibold text-ink">
                      {issuer.name}
                      <span className="sr-only">, breakdown.</span>
                    </span>
                  </span>
                  <StateText label="After" state={issuer.proposed} testId="exposure-after" />
                  <StateBar state={issuer.proposed} possibleExtra={extras.proposed} axisMax={axis.max} limit={limit} />
                  <StateText label="Before" state={issuer.starting} testId="exposure-before" />
                  <StateBar state={issuer.starting} possibleExtra={extras.starting} axisMax={axis.max} limit={limit} thin />
                </span>
              </summary>
              <div className="pb-4 pt-1 sm:pl-6">
                <BreakdownTable issuer={issuer} exposure={exposure} limit={limit} limitLabel={limitLabel} />
              </div>
            </details>
          </li>
        ))}
      </ul>

      {/* Axis. */}
      <div className={cn(GRID, "border-t border-line")} aria-hidden="true">
        <span className="hidden sm:block" />
        <span />
        <span className="relative mt-1 block h-5 border-t border-line-strong text-sm text-ink-muted">
          {axis.ticks.map((tick, index) => (
            <span
              key={tick}
              className={cn("tabular absolute top-0.5", index === 0 ? "" : index === axis.ticks.length - 1 ? "-translate-x-full" : "-translate-x-1/2")}
              style={{ left: percent(tick, axis.max) }}
            >
              {tickText(tick, step)}
            </span>
          ))}
        </span>
      </div>

      <ul className="mt-4 flex flex-wrap gap-x-5 gap-y-2 text-sm text-ink" aria-label="Legend">
        <li className="flex items-center gap-2" data-key="direct">
          <span className="byb-swatch" data-seg="direct" aria-hidden="true" />
          Direct holding
        </li>
        <li className="flex items-center gap-2" data-key="indirect">
          <span className="byb-swatch" data-seg="indirect" aria-hidden="true" />
          Through a fund, from its reported holdings (one segment per fund)
        </li>
        {hasPossible ? (
          <li className="flex items-center gap-2" data-key="possible">
            <span className="byb-swatch" data-seg="possible" aria-hidden="true" />
            Possible extra, not measured (fund weight not attributed to any company)
          </li>
        ) : null}
        {limit !== null ? (
          <li className="flex items-center gap-2" data-key="limit">
            <span className="byb-swatch" data-seg="limit" aria-hidden="true" />
            {limitLabel}
          </li>
        ) : null}
        <li className="flex items-center gap-2">
          <span className="byb-bar inline-block w-6" data-size="thin" aria-hidden="true">
            <span className="byb-bar-track">
              <span className="byb-seg" data-seg="direct" style={{ width: "100%" }} />
            </span>
          </span>
          Thin bar: before the purchase
        </li>
      </ul>
    </figure>
  );
}
