"use client";

/**
 * Current versus proposed exposure to one company: direct, through each fund,
 * and the part that cannot be attributed, against the limit.
 *
 * Everything a reader needs is HTML and is always rendered: the origin marker,
 * the table, the legend, the segment buttons and the details panel. The 3D
 * drawing is an enhancement next to it, loaded lazily, and replaced by the
 * caller's `fallback` whenever it cannot or should not be shown.
 *
 * No financial arithmetic happens here. Each number is a value of the model
 * (itself a copy of the API response) turned into text by `@/lib/format`.
 * In particular this component never decides whether a rule passes: it shows
 * the rule status the check returned.
 */
import { Component, lazy, Suspense, useCallback, useId, useMemo, useRef, useState, useSyncExternalStore, type ReactNode } from "react";
import { Badge, StatusBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EvidenceIcon, InfoIcon, UnknownIcon, WarningIcon } from "@/components/ui/icons";
import { cn } from "@/lib/cn";
import { decimalsToDistinguish, formatDate, formatFraction } from "@/lib/format";
import {
  browserSupportsWebGL,
  decideRenderMode,
  fallbackReasonText,
  FORCED_COLORS_QUERY,
  MIN_3D_VIEWPORT_WIDTH,
  REDUCED_MOTION_QUERY,
  WIDE_VIEWPORT_QUERY,
  type SceneFailure,
} from "./capability";
import type { ExposureSceneHandle, SceneLabels } from "./ExposureScene";
import type { ExplorerColumn, ExplorerModel, ExplorerReady, ExplorerSegment, ExplorerUnavailable, LimitUnavailableReason, UnavailableReason } from "./model";
import { t } from "@/lib/i18n";

const ExposureScene = lazy(() => import("./ExposureScene"));

export interface ExposureExplorerProps {
  model: ExplorerModel;
  /** Shown instead of the 3D drawing whenever that cannot be used, and while it loads. Normally the 2D exposure chart. */
  fallback: ReactNode;
  /** Opens the evidence record of a fund contribution. Without it the record id is shown as text. */
  onOpenEvidence?: (evidenceId: string) => void;
  /** Heading level of the card title. Default 3 (inside a panel). */
  headingLevel?: 2 | 3;
  className?: string;
}

// ---------------------------------------------------------------------------
// Wording
// ---------------------------------------------------------------------------

const UNAVAILABLE_TEXT: Record<UnavailableReason, string> = {
  EXECUTION_NOT_OK: "The check did not run to the end, so it returned no exposure figures.",
  NO_EXPOSURE_SECTION: "The check returned no exposure section.",
  NO_ISSUER_ROWS: "The check returned an exposure section that lists no company.",
  ISSUER_NOT_IN_RESULT: "The check returned no exposure figures for this company.",
};

const LIMIT_UNAVAILABLE_TEXT: Record<LimitUnavailableReason, string> = {
  NO_ISSUER_CAP_RULE: "No limit is drawn: this check evaluated no rule that limits exposure to a single company.",
  SEVERAL_ISSUER_CAP_RULES:
    "No limit is drawn: this check evaluated several single-company limits and the result does not say which one applies to this company.",
};

const UNKNOWN_CAUSE_TEXT: Record<string, string> = {
  PARTIAL_HOLDINGS: "A fund's holdings file does not cover the whole fund.",
  MISSING_HOLDINGS: "A fund in the portfolio has no holdings file.",
  UNCLASSIFIED_SECTOR: "Some holdings carry no sector label.",
  REGISTRY_ABSENCE: "Some companies have no record in the registry that was consulted.",
  INSUFFICIENT_HISTORY: "There is not enough price history.",
};

const COVERAGE_TEXT: Record<string, string> = {
  COVERED: "Complete: the holdings file covers the whole fund",
  PARTIAL: "Partial: the holdings file does not cover the whole fund",
  MISSING: "Missing: the fund has no holdings file",
};

const STATE_TEXT = { starting: "Current", proposed: "Proposed" } as const;
const STATE_LONG_TEXT = { starting: "Current portfolio", proposed: "Proposed portfolio (after the purchase)" } as const;

const UNRESOLVED_LABEL = "Not attributed (could be this company)";

function segmentLabel(segment: ExplorerSegment): string {
  if (segment.kind === "DIRECT") return "Held directly";
  if (segment.kind === "FUND") return `Through ${segment.fundId ?? "a fund"}`;
  return UNRESOLVED_LABEL;
}

/**
 * "1.2%", or "up to 0.2%" for the part that is a bound and not a measurement. A bound too small for
 * one decimal is given the decimals that show it is not zero: "up to 0.05%", never "up to 0.0%".
 */
function segmentValueText(segment: ExplorerSegment): string {
  if (segment.kind !== "UNRESOLVED") return formatFraction(segment.value);
  return `up to ${formatFraction(segment.value, { decimals: decimalsToDistinguish(0, segment.value) })}`;
}

function limitNoun(model: ExplorerReady): string {
  return model.limit?.isDraft ? "Draft limit (not confirmed)" : "Confirmed limit";
}

/** A percentage on the drawing scale: whole percent when it is one, otherwise one decimal. Presentation only. */
function scaleText(value: number): string {
  const whole = formatFraction(value, { decimals: 0 });
  const fine = formatFraction(value, { decimals: 1 });
  return fine === whole.replace("%", ".0%") ? whole : fine;
}

// ---------------------------------------------------------------------------
// Browser environment (WebGL, forced colours, reduced motion, width) as an external store
// ---------------------------------------------------------------------------

function subscribeEnvironment(onChange: () => void): () => void {
  const queries = [window.matchMedia(WIDE_VIEWPORT_QUERY), window.matchMedia(FORCED_COLORS_QUERY), window.matchMedia(REDUCED_MOTION_QUERY)];
  queries.forEach((query) => query.addEventListener("change", onChange));
  return () => queries.forEach((query) => query.removeEventListener("change", onChange));
}

/** A string, so the snapshot is stable between calls: "<webgl><forcedColors><wide><reducedMotion>". */
function environmentSnapshot(): string {
  const flag = (value: boolean) => (value ? "1" : "0");
  const matches = (query: string) => flag(window.matchMedia(query).matches);
  return flag(browserSupportsWebGL()) + matches(FORCED_COLORS_QUERY) + matches(WIDE_VIEWPORT_QUERY) + matches(REDUCED_MOTION_QUERY);
}

const serverEnvironmentSnapshot = () => "server";

/** Catches a failed chunk load and any error thrown while the scene renders. */
class SceneBoundary extends Component<{ onError: () => void; children: ReactNode }, { failed: boolean }> {
  override state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  override componentDidCatch() {
    this.props.onError();
  }

  override render() {
    return this.state.failed ? null : this.props.children;
  }
}

// ---------------------------------------------------------------------------
// Pieces
// ---------------------------------------------------------------------------

function OriginMarker({ model }: { model: ExplorerModel }) {
  const preview = model.status === "READY" && model.preview;
  if (model.dataOrigin !== "FIXTURE" && !preview) return null;
  return (
    <p className="flex flex-wrap items-center gap-2" data-testid="explorer-origin">
      {model.dataOrigin === "FIXTURE" ? (
        <Badge tone="unknown" dashed icon={<WarningIcon size={16} />}>
          {t("Test data")}</Badge>
      ) : null}
      {preview ? (
        <Badge tone="neutral" dashed icon={<InfoIcon size={16} />}>
          {t("Draft preview")}</Badge>
      ) : null}
    </p>
  );
}

function Unavailable({ model, className }: { model: ExplorerUnavailable; className?: string }) {
  return (
    <section
      aria-label={t("Exposure explorer")}
      className={cn("space-y-3 rounded-md border border-dashed border-line-strong bg-sunken p-4", className)}
      data-testid="exposure-explorer"
      data-status="UNAVAILABLE"
    >
      <OriginMarker model={model} />
      <div className="flex items-start gap-2" data-testid="explorer-unavailable">
        <UnknownIcon size={20} className="mt-0.5 flex-none text-unknown" />
        <div className="space-y-1">
          <p className="font-semibold text-ink">{t("Exposure cannot be shown")}</p>
          <p className="text-ink">{UNAVAILABLE_TEXT[model.reason]}</p>
          {model.message ? (
            <p className="text-ink">
              <span className="font-semibold">{t("Message from the check:")}</span> {model.message}
            </p>
          ) : null}
          <p className="text-sm text-ink-muted">{t("Nothing is drawn, because an empty chart would read as zero exposure.")}</p>
        </div>
      </div>
    </section>
  );
}

function Legend({ model }: { model: ExplorerReady }) {
  const hasUnresolved = [model.current, model.proposed].some((column) => column.segments.some((segment) => segment.kind === "UNRESOLVED"));
  return (
    <ul className="flex flex-wrap gap-x-5 gap-y-2 text-sm text-ink" aria-label={t("Legend")}>
      <li className="flex items-center gap-2">
        <span className="byb-swatch" data-seg="direct" aria-hidden="true" />
        {t("Held directly (dark blue)")}</li>
      <li className="flex items-center gap-2">
        <span className="byb-swatch border border-ink" data-seg="indirect" aria-hidden="true" />
        {t("Through a fund (light blue)")}</li>
      {hasUnresolved ? (
        <li className="flex items-center gap-2">
          <span className="byb-swatch" data-seg="possible" aria-hidden="true" />
          {t("Not attributed (amber in network; dashed in chart)")}</li>
      ) : null}
      {model.limit ? (
        <li className="flex items-center gap-2">
          <span className="byb-swatch" data-seg="limit" aria-hidden="true" />
          {limitNoun(model)}
        </li>
      ) : null}
    </ul>
  );
}

function ValuesTable({ model }: { model: ExplorerReady }) {
  const columns = [model.current, model.proposed] as const;
  const fundIds = [...new Set(columns.flatMap((column) => column.segments.flatMap((segment) => (segment.kind === "FUND" && segment.fundId ? [segment.fundId] : []))))];
  const hasUnresolved = columns.some((column) => column.segments.some((segment) => segment.kind === "UNRESOLVED"));
  const anyRange = columns.some((column) => column.isRange);
  const find = (column: ExplorerColumn, predicate: (segment: ExplorerSegment) => boolean) => column.segments.find(predicate);
  // Enough decimals that a proven total and a possible total which differ are never printed as the same figure.
  const totalDecimals = Math.max(...columns.map((column) => (column.isRange ? decimalsToDistinguish(column.known, column.upper) : 1)));

  const rows: { key: string; label: string; cells: [string, string]; strong?: boolean }[] = [
    {
      key: "direct",
      label: "Held directly",
      cells: columns.map((column) => formatFraction(find(column, (segment) => segment.kind === "DIRECT")?.value)) as [string, string],
    },
    ...fundIds.map((fundId) => ({
      key: `fund:${fundId}`,
      label: `Through ${fundId}`,
      cells: columns.map((column) => {
        const segment = find(column, (item) => item.kind === "FUND" && item.fundId === fundId);
        return segment ? formatFraction(segment.value) : "None reported";
      }) as [string, string],
    })),
  ];
  if (hasUnresolved) {
    rows.push({
      key: "unresolved",
      label: UNRESOLVED_LABEL,
      cells: columns.map((column) => {
        const segment = find(column, (item) => item.kind === "UNRESOLVED");
        return segment ? segmentValueText(segment) : "None";
      }) as [string, string],
    });
  }
  rows.push({
    key: "known",
    label: "Proven total",
    strong: true,
    cells: columns.map((column) => formatFraction(column.known, { decimals: totalDecimals })) as [string, string],
  });
  if (anyRange) {
    rows.push({
      key: "upper",
      label: "Possible total",
      strong: true,
      cells: columns.map((column) => formatFraction(column.upper, { decimals: totalDecimals })) as [string, string],
    });
  }
  rows.push({
    key: "limit",
    label: model.limit ? limitNoun(model) : "Limit",
    cells: columns.map(() => (model.limit ? formatFraction(model.limit.value) : "Not available")) as [string, string],
  });

  return (
    <table className="w-full border-collapse text-left" data-testid="explorer-table">
      <caption className="sr-only">{model.issuerName}{t(": exposure as a share of the portfolio, current and proposed")}</caption>
      <thead>
        <tr className="border-b-2 border-line-strong text-sm text-ink-muted">
          <td className="py-2 pr-3" />
          {columns.map((column) => (
            <th key={column.state} scope="col" className="py-2 pl-3 text-right font-semibold">
              {STATE_TEXT[column.state]}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.key} className="border-b border-line" data-row={row.key}>
            <th scope="row" className="py-2 pr-3 text-sm font-semibold text-ink-muted">
              {row.label}
            </th>
            {row.cells.map((cell, index) => (
              <td key={index} className={cn("tabular whitespace-nowrap py-2 pl-3 text-right text-ink", row.strong && "text-lg font-bold")} data-state={columns[index]?.state}>
                {cell}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function TotalsInWords({ model }: { model: ExplorerReady }) {
  const columns = [model.current, model.proposed];
  return (
    <div className="space-y-1 text-ink" data-testid="explorer-totals">
      {columns.map((column) => {
        const decimals = column.isRange ? decimalsToDistinguish(column.known, column.upper) : 1;
        return (
          <p key={column.state} data-state={column.state}>
            <span className="font-semibold">{STATE_TEXT[column.state]}:</span>{" "}
            {column.isRange ? (
              <span className="tabular">
                {t("between")} {formatFraction(column.known, { decimals })} {t("and")} {formatFraction(column.upper, { decimals })} {t("of the portfolio; the part that cannot be attributed is an uncertain upper bound.")}</span>
            ) : (
              <span className="tabular">{formatFraction(column.known)} {t("of the portfolio.")}</span>
            )}
          </p>
        );
      })}
      {model.unknownCauses.length > 0 ? (
        <div className="text-sm text-ink-muted" data-testid="explorer-unknown-causes">
          <p>{t("Why the total is a range and not one number:")}</p>
          <ul className="list-disc pl-5">
            {model.unknownCauses.map((cause) => (
              <li key={cause}>{UNKNOWN_CAUSE_TEXT[cause] ?? cause}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

function LimitLine({ model }: { model: ExplorerReady }) {
  if (!model.limit) {
    return (
      <p className="text-ink" data-testid="explorer-limit">
        {model.limitUnavailableReason ? LIMIT_UNAVAILABLE_TEXT[model.limitUnavailableReason] : "No limit is drawn."}
      </p>
    );
  }
  return (
    <div className="space-y-1" data-testid="explorer-limit">
      <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-ink">
        <span>
          <span className="font-semibold">{limitNoun(model)}:</span> <span className="tabular">{formatFraction(model.limit.value)}</span>
        </span>
        <span className="flex flex-wrap items-center gap-2">
          {t("Rule result from the check:")} <StatusBadge status={model.limit.ruleStatus} />
        </span>
      </p>
      <p className="text-sm text-ink-muted">
        {t("The rule is judged on its own subject, which may be another company than")} {model.issuerName}{t(". This card does not decide whether the rule is respected.")}</p>
    </div>
  );
}

function SegmentDetails({ segment, onOpenEvidence }: { segment: ExplorerSegment; onOpenEvidence?: (evidenceId: string) => void }) {
  return (
    <div className="rounded-md border border-line bg-sunken p-3 sm:p-4" data-testid="explorer-details" data-segment={segment.id}>
      <p className="font-semibold text-ink">
        {segmentLabel(segment)}: {STATE_LONG_TEXT[segment.state]}
      </p>
      <dl className="mt-2 grid grid-cols-1 gap-x-6 gap-y-2 text-ink sm:grid-cols-2">
        <div>
          <dt className="text-sm font-semibold text-ink-muted">{t("Share of the portfolio")}</dt>
          <dd className="tabular text-lg font-bold">{segmentValueText(segment)}</dd>
        </div>
        {segment.kind === "FUND" ? (
          <>
            <div>
              <dt className="text-sm font-semibold text-ink-muted">{t("Holdings date")}</dt>
              <dd className="tabular">{segment.holdingsDate ? formatDate(segment.holdingsDate) : "No holdings file"}</dd>
            </div>
            <div>
              <dt className="text-sm font-semibold text-ink-muted">{t("Source")}</dt>
              <dd className="break-all font-mono text-sm">{segment.sourceId ?? "No source recorded"}</dd>
            </div>
            <div>
              <dt className="text-sm font-semibold text-ink-muted">{t("Holdings coverage")}</dt>
              <dd>{segment.coverageStatus ? (COVERAGE_TEXT[segment.coverageStatus] ?? segment.coverageStatus) : "Not reported"}</dd>
            </div>
            {segment.formula ? (
              <div className="sm:col-span-2">
                <dt className="text-sm font-semibold text-ink-muted">{t("Calculation, as recorded (portfolio fractions)")}</dt>
                <dd className="tabular font-mono text-sm">{segment.formula}</dd>
              </div>
            ) : null}
          </>
        ) : null}
      </dl>
      {segment.kind === "UNRESOLVED" ? (
        <p className="mt-2 text-sm text-ink">
          {t("This share of the portfolio sits in funds whose holdings are not fully reported. It could be this company or any other. It is a possible maximum, not a measured amount, and it is never counted as zero.")}</p>
      ) : null}
      <div className="mt-3">
        {segment.evidenceId ? (
          onOpenEvidence ? (
            <Button size="sm" icon={<EvidenceIcon size={16} />} onClick={() => onOpenEvidence(segment.evidenceId as string)} data-testid="explorer-open-evidence">
              {t("Open the calculation")}</Button>
          ) : (
            <p className="text-sm text-ink">
              {t("Calculation record:")} <span className="font-mono">{segment.evidenceId}</span>
            </p>
          )
        ) : (
          <p className="text-sm text-ink-muted" data-testid="explorer-no-evidence">
            {t("The response contains no calculation record for this part.")}</p>
        )}
      </div>
    </div>
  );
}

function SegmentButtons({
  model,
  selectedId,
  onSelect,
}: {
  model: ExplorerReady;
  selectedId: string | null;
  onSelect: (segmentId: string | null) => void;
}) {
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      {[model.current, model.proposed].map((column) => (
        <div key={column.state} role="group" aria-label={`${STATE_TEXT[column.state]} portfolio: parts`}>
          <p className="text-sm font-semibold text-ink-muted">{STATE_TEXT[column.state]}</p>
          <ul className="mt-1 space-y-1.5">
            {column.segments.map((segment) => {
              const selected = segment.id === selectedId;
              return (
                <li key={segment.id}>
                  <button
                    type="button"
                    aria-pressed={selected}
                    onClick={() => onSelect(selected ? null : segment.id)}
                    className={cn(
                      "flex min-h-11 w-full items-center justify-between gap-3 rounded-md border px-3 py-1.5 text-left text-ink",
                      selected ? "border-2 border-accent bg-accent-soft font-semibold" : "border-line-strong bg-surface hover:bg-accent-soft",
                    )}
                    data-testid="explorer-segment"
                    data-segment={segment.id}
                  >
                    <span className="flex items-center gap-2">
                      <span
                        className={cn("byb-swatch", segment.kind === "FUND" && "border border-ink")}
                        data-seg={segment.kind === "DIRECT" ? "direct" : segment.kind === "FUND" ? "indirect" : "possible"}
                        aria-hidden="true"
                      />
                      {segmentLabel(segment)}
                    </span>
                    <span className="tabular">{segmentValueText(segment)}</span>
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </div>
  );
}

function HowToRead() {
  return (
    <details className="rounded-md border border-line bg-surface px-3 py-2 text-ink" data-testid="explorer-how-to-read">
      <summary className="cursor-pointer font-semibold text-accent">{t("How to read this")}</summary>
      <ul className="mt-2 list-disc space-y-1 pl-5">
        <li>{t("The network shows ownership paths, not a forecast or a risk score.")}</li>
        <li>{t("Current and proposed portfolios are separate branches. Compare their percentages in the table.")}</li>
        <li>{t("Node size, distance and link width do not represent amounts. The simple chart uses a shared percentage scale.")}</li>
        <li>{t("Not attributed means missing holdings: the possible amount is not connected to the company as a proven exposure. The simple chart shows this range hollow and dashed.")}</li>
        <li>{t("Indirect exposure means owning a company through a fund.")}</li>
        <li>{t("The numbers are in the table. The drawing never shows a value the table does not.")}</li>
      </ul>
    </details>
  );
}

// ---------------------------------------------------------------------------
// The card
// ---------------------------------------------------------------------------

function Ready({ model, fallback, onOpenEvidence, headingLevel = 3, className }: ExposureExplorerProps & { model: ExplorerReady }) {
  const headingId = useId();
  const Heading = headingLevel === 2 ? "h2" : "h3";
  const SubHeading = headingLevel === 2 ? "h3" : "h4";
  const sceneRef = useRef<ExposureSceneHandle>(null);
  const [simpleView, setSimpleView] = useState(false);
  const [selection, setSelection] = useState<string | null>(null);
  const [sceneFailure, setSceneFailure] = useState<SceneFailure | null>(null);

  const snapshot = useSyncExternalStore(subscribeEnvironment, environmentSnapshot, serverEnvironmentSnapshot);
  const decision = decideRenderMode({
    ready: snapshot !== "server",
    webgl: snapshot[0] === "1",
    forcedColors: snapshot[1] === "1",
    reducedMotion: snapshot[3] === "1",
    // Only "wide enough or not" is known from the media query; that is all the decision needs.
    viewportWidth: snapshot[2] === "1" ? MIN_3D_VIEWPORT_WIDTH : 0,
    sceneFailure,
  });

  const segments = [...model.current.segments, ...model.proposed.segments];
  // A selection made on an earlier result is dropped when the new result has no such part.
  const selected = segments.find((segment) => segment.id === selection) ?? null;

  const { axisMax, limit } = model;
  const labels = useMemo<SceneLabels>(
    () => ({
      ticks: [0, 0.5, 1].map((position) => ({ position, text: scaleText(axisMax * position) })),
      limit: limit ? `${limit.isDraft ? "Draft limit" : "Confirmed limit"} ${formatFraction(limit.value)}` : null,
      current: STATE_TEXT.starting,
      proposed: STATE_TEXT.proposed,
    }),
    [axisMax, limit],
  );

  const onSceneFailure = useCallback((reason: "INIT_FAILED" | "CONTEXT_LOST") => setSceneFailure(reason), []);
  const onBoundaryError = useCallback(() => setSceneFailure("LOAD_OR_RENDER_ERROR"), []);

  const fallbackNote = decision.mode === "FALLBACK" ? fallbackReasonText(decision.reason) : null;

  return (
    <section
      aria-labelledby={headingId}
      className={cn("space-y-4", className)}
      data-testid="exposure-explorer"
      data-status="READY"
      data-mode={decision.mode}
      data-fallback-reason={decision.mode === "FALLBACK" ? decision.reason : undefined}
    >
      <header className="space-y-2">
        <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
          <Heading id={headingId} className="text-lg font-semibold text-ink">
            {model.issuerName}{t(": current and proposed exposure")}</Heading>
          <OriginMarker model={model} />
        </div>
        <p className="text-sm text-ink-muted" data-testid="explorer-context">
          {model.policyVersion === null ? "Draft rules, not a confirmed policy" : `Confirmed policy version ${model.policyVersion}`}
          {" · "}{t("Valuation date")} <span className="tabular">{formatDate(model.valuationDate)}</span>
          {" · "}{t("Calculation")} <span className="break-all font-mono">{model.calculationVersion}</span>
        </p>
      </header>

      <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg bg-accent-soft p-4">
        <div>
          <p className="font-semibold text-ink">{t("See how you own")} {model.issuerName}</p>
          <p className="text-sm text-ink-muted">{t("Follow each connection from your portfolio. Select a holding to inspect its source.")}</p>
        </div>
        {decision.mode === "3D" ? <Button size="sm" aria-pressed={simpleView} onClick={() => setSimpleView(!simpleView)}>
          {simpleView ? "Show interactive network" : "Show simple chart"}
        </Button> : null}
      </div>
      <div className="grid min-w-0 grid-cols-1 gap-5">
        <div className="min-w-0 space-y-3">
          {decision.mode === "3D" && !simpleView ? (
            <SceneBoundary onError={onBoundaryError}>
              <Suspense fallback={<div data-testid="explorer-fallback">{fallback}</div>}>
                <ExposureScene ref={sceneRef} model={model} labels={labels} selectedId={selected?.id ?? null} onSelect={setSelection} onFailure={onSceneFailure} />
                <div className="flex flex-wrap items-center gap-2" role="group" aria-label={t("3D view controls")}>
                  <Button size="sm" onClick={() => sceneRef.current?.rotate(-1)}>
                    {t("Rotate left")}</Button>
                  <Button size="sm" onClick={() => sceneRef.current?.rotate(1)}>
                    {t("Rotate right")}</Button>
                  <Button size="sm" onClick={() => sceneRef.current?.zoom(1)}>
                    {t("Zoom in")}</Button>
                  <Button size="sm" onClick={() => sceneRef.current?.zoom(-1)}>
                    {t("Zoom out")}</Button>
                  <Button size="sm" onClick={() => sceneRef.current?.reset()} data-testid="explorer-reset-view">
                    {t("Reset view")}</Button>
                </div>
                <p className="text-sm text-ink-muted">
                  {t("Drag to rotate; scroll to zoom. Click a holding to see its evidence below, or use the selection buttons.")}</p>
              </Suspense>
            </SceneBoundary>
          ) : (
            <div className="space-y-2" data-testid="explorer-fallback">
              {fallback}
              {fallbackNote ? <p className="text-sm text-ink-muted">{fallbackNote}</p> : null}
            </div>
          )}
          <Legend model={model} />
          <HowToRead />
        </div>

        <div className="space-y-4">
          <TotalsInWords model={model} />
          <LimitLine model={model} />
          <ValuesTable model={model} />
        </div>
      </div>

      <div className="space-y-3">
        <SubHeading className="font-semibold text-ink">{t("Parts of the exposure")}</SubHeading>
        <p className="text-sm text-ink-muted">{t("Select a part to see where it comes from.")}</p>
        <SegmentButtons model={model} selectedId={selected?.id ?? null} onSelect={setSelection} />
        <div aria-live="polite">
          {selected ? <SegmentDetails segment={selected} onOpenEvidence={onOpenEvidence} /> : null}
        </div>
      </div>
    </section>
  );
}

export function ExposureExplorer(props: ExposureExplorerProps) {
  if (props.model.status === "UNAVAILABLE") return <Unavailable model={props.model} className={props.className} />;
  return <Ready {...props} model={props.model} />;
}
