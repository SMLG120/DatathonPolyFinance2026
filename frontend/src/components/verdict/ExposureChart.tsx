import { useId } from "react";
import { cn } from "@/lib/cn";
import { EPS, formatFraction, formatFractionRange } from "@/lib/format";

/**
 * One bar of the chart. All values are portfolio fractions.
 *
 * The component takes this view model, not a contract object, so the shared
 * contract can change without touching the drawing.
 */
export interface ExposureBar {
  key: string;
  /** "Before the purchase" / "After the purchase". */
  label: string;
  /** Held directly. */
  direct: number;
  /** Reached through funds, from reported holdings. */
  indirect: number;
  /** Fund weight with no reported holdings: could be this subject, could be nothing. Unmeasured. */
  possibleExtra: number;
  /** direct + indirect: the least the exposure can be. */
  lower: number;
  /** lower + possibleExtra: the most it can be. */
  upper: number;
}

export interface ExposureChartProps {
  /** What is measured, e.g. "NVDA" or "Energy sector". */
  subject: string;
  bars: ExposureBar[];
  /** The threshold drawn as a marker, or null when there is none. */
  limit: number | null;
  /** "Confirmed limit", "Confirmed minimum" or "Draft limit". */
  limitLabel?: string;
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

/** A round axis end that leaves headroom above the largest value, and the tick step that goes with it. */
export function exposureAxis(values: number[]): { max: number; ticks: number[] } {
  const largest = Math.max(0, ...values.filter((value) => Number.isFinite(value)));
  const [max, step] = AXIS_STEPS.find(([candidate]) => candidate + EPS >= largest * 1.1) ?? [1, 0.25];
  const ticks: number[] = [];
  for (let index = 0; index * step <= max + EPS; index += 1) ticks.push(Number((index * step).toFixed(6)));
  return { max, ticks };
}

/** The whole chart as one sentence, for assistive technology and for tests. */
export function describeExposure({ subject, bars, limit, limitLabel = "Confirmed limit" }: ExposureChartProps): string {
  const parts = bars.map((bar) => {
    const total = formatFractionRange(bar.lower, bar.upper);
    const range = bar.possibleExtra > EPS ? `between ${total.replace(" to ", " and ")}` : total;
    const extra = bar.possibleExtra > EPS ? `, plus up to ${formatFraction(bar.possibleExtra)} that cannot be measured` : "";
    return `${bar.label}: ${range} (direct ${formatFraction(bar.direct)}, through funds ${formatFraction(bar.indirect)}${extra}).`;
  });
  const limitText = limit === null ? "No limit is drawn." : `${limitLabel}: ${formatFraction(limit)}.`;
  return `${subject} exposure as a share of the portfolio. ${parts.join(" ")} ${limitText}`;
}

const percent = (value: number, max: number) => `${Math.min(100, Math.max(0, (value / max) * 100))}%`;

function tickText(tick: number, step: number): string {
  return formatFraction(tick, { decimals: step < 0.01 - EPS ? 1 : 0 });
}

/**
 * Direct and through-fund exposure as stacked horizontal bars against a limit.
 *
 * - Two solid segments in one hue: direct (dark) and through funds (lighter).
 * - Exposure that may exist but cannot be measured is drawn hollow and dashed,
 *   so a possible range is never mistaken for a measured amount.
 * - The limit is a marker across each bar with its value written next to it.
 * - The same numbers are always on screen as a table under the drawing, so the
 *   chart never depends on colour, hover or eyesight alone.
 */
export function ExposureChart(props: ExposureChartProps) {
  const { subject, bars, limit, limitLabel = "Confirmed limit" } = props;
  const captionId = useId();
  const axis = exposureAxis([...bars.map((bar) => bar.upper), limit ?? 0]);
  const step = axis.ticks[1] ?? axis.max;
  const hasPossible = bars.some((bar) => bar.possibleExtra > EPS);
  const limitNearEnd = limit !== null && limit / axis.max > 0.7;

  return (
    <figure className="byb-chart" aria-labelledby={captionId} data-testid="exposure-chart">
      <figcaption id={captionId} className="font-semibold text-ink">
        {subject}: exposure as a share of the portfolio
      </figcaption>

      {/* The drawing. It is one image to assistive technology; the table below carries every value. */}
      <div role="img" aria-label={describeExposure(props)} className="mt-4" data-testid="exposure-drawing">
        <div className="grid grid-cols-1 gap-x-4 sm:grid-cols-[10rem_minmax(0,1fr)]">
          {/* Limit label, positioned over the marker. */}
          <div className="hidden sm:block" />
          <div className="relative h-6 text-sm">
            {limit !== null ? (
              <span
                className={cn("tabular absolute bottom-0.5 whitespace-nowrap font-semibold text-ink", limitNearEnd ? "-translate-x-full pr-1.5" : "pl-1.5")}
                style={{ left: percent(limit, axis.max) }}
                data-key="limit"
              >
                {limitLabel} {formatFraction(limit)}
              </span>
            ) : null}
          </div>

          {bars.map((bar) => (
            <div key={bar.key} className="contents" data-testid="exposure-bar" data-bar={bar.key}>
              <div className="flex items-baseline justify-between gap-3 pt-3 sm:block sm:pt-0">
                <span className="block text-sm font-semibold text-ink">{bar.label}</span>
                <span className="tabular block text-sm text-ink-muted">{formatFractionRange(bar.lower, bar.upper)}</span>
              </div>
              <div className="flex items-center py-2">
                <div className="byb-bar w-full">
                  <div className="byb-bar-track">
                    {bar.direct > EPS ? (
                      <span
                        className="byb-seg"
                        data-seg="direct"
                        style={{ width: percent(bar.direct, axis.max), minWidth: 4 }}
                        title={`${bar.label} — direct holding: ${formatFraction(bar.direct)}`}
                      />
                    ) : null}
                    {bar.indirect > EPS ? (
                      <span
                        className="byb-seg"
                        data-seg="indirect"
                        style={{ width: percent(bar.indirect, axis.max), minWidth: 4 }}
                        title={`${bar.label} — through funds: ${formatFraction(bar.indirect)}`}
                      />
                    ) : null}
                    {bar.possibleExtra > EPS ? (
                      <span
                        className="byb-seg"
                        data-seg="possible"
                        style={{ width: percent(bar.possibleExtra, axis.max), minWidth: 6 }}
                        title={`${bar.label} — possible extra, not measured: up to ${formatFraction(bar.possibleExtra)}`}
                      />
                    ) : null}
                  </div>
                  {limit !== null ? (
                    <span className="byb-limit" style={{ left: percent(limit, axis.max) }} title={`${limitLabel}: ${formatFraction(limit)}`} data-testid="limit-marker" />
                  ) : null}
                </div>
              </div>
            </div>
          ))}

          {/* Axis. */}
          <div className="hidden sm:block" />
          <div className="relative mt-1 h-5 border-t border-line-strong text-sm text-ink-muted">
            {axis.ticks.map((tick, index) => (
              <span
                key={tick}
                className={cn(
                  "tabular absolute top-0.5",
                  index === 0 ? "" : index === axis.ticks.length - 1 ? "-translate-x-full" : "-translate-x-1/2",
                )}
                style={{ left: percent(tick, axis.max) }}
              >
                {tickText(tick, step)}
              </span>
            ))}
          </div>
        </div>
      </div>

      <ul className="mt-4 flex flex-wrap gap-x-5 gap-y-2 text-sm text-ink" aria-label="Legend">
        <li className="flex items-center gap-2" data-key="direct">
          <span className="byb-swatch" data-seg="direct" aria-hidden="true" />
          Direct holding
        </li>
        <li className="flex items-center gap-2" data-key="indirect">
          <span className="byb-swatch" data-seg="indirect" aria-hidden="true" />
          Through funds, from reported holdings
        </li>
        {hasPossible ? (
          <li className="flex items-center gap-2" data-key="possible">
            <span className="byb-swatch" data-seg="possible" aria-hidden="true" />
            Possible extra, not measured (fund holdings not reported)
          </li>
        ) : null}
        {limit !== null ? (
          <li className="flex items-center gap-2" data-key="limit">
            <span className="byb-swatch" data-seg="limit" aria-hidden="true" />
            {limitLabel}
          </li>
        ) : null}
      </ul>

      <table className="mt-5 w-full border-collapse text-left" data-testid="exposure-table">
        <caption className="sr-only">{subject} exposure: the values drawn above</caption>
        <thead>
          <tr className="border-b-2 border-line-strong text-sm text-ink-muted">
            <td className="py-2 pr-3" />
            {bars.map((bar) => (
              <th key={bar.key} scope="col" className="py-2 pl-3 text-right font-semibold">
                {bar.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          <ValueRow label="Direct holding" values={bars.map((bar) => formatFraction(bar.direct))} />
          <ValueRow label="Through funds, from reported holdings" values={bars.map((bar) => formatFraction(bar.indirect))} />
          <ValueRow label="Measured total" strong values={bars.map((bar) => formatFraction(bar.lower))} />
          <ValueRow
            label="Possible extra, not measured"
            values={bars.map((bar) => (bar.possibleExtra > EPS ? `up to ${formatFraction(bar.possibleExtra)}` : "None"))}
          />
          <ValueRow label="Possible range" strong values={bars.map((bar) => formatFractionRange(bar.lower, bar.upper))} />
          {limit !== null ? <ValueRow label={limitLabel} values={bars.map(() => formatFraction(limit))} /> : null}
        </tbody>
      </table>
    </figure>
  );
}

function ValueRow({ label, values, strong = false }: { label: string; values: string[]; strong?: boolean }) {
  return (
    <tr className="border-b border-line">
      <th scope="row" className="py-2 pr-3 text-sm font-semibold text-ink-muted">
        {label}
      </th>
      {values.map((value, index) => (
        <td key={index} className={cn("tabular py-2 pl-3 text-right text-ink", strong && "text-lg font-bold")}>
          {value}
        </td>
      ))}
    </tr>
  );
}
