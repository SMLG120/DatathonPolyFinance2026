/**
 * Contract -> exposure-explorer view model.
 *
 * This file RESHAPES values that the deterministic engine already returned in
 * a `CheckResult`. It performs no financial arithmetic: every percentage in
 * the model is a number copied from the response (`direct`, `known`, `lower`,
 * `upper`, `possible_extra`, `limit`). Nothing is summed, subtracted, rescaled
 * or rounded here. The only number this file computes is `axisMax`, the top of
 * the drawing scale. It is presentation: it appears only as the labels of the
 * scale lines of the drawing, never as a figure of the result.
 *
 * When the response does not supply something, the model says so
 * (`unavailable`, `limit: null`, `evidenceId: null`, `holdingsDate: null`)
 * instead of filling the gap.
 */
import type { CheckResult, EvidenceRecord, FundCoverage, IssuerExposure, RuleResult } from "./contract-types";

/** Where the result came from. The response body carries no such flag, so the caller states it. */
export type DataOrigin = "LIVE" | "FIXTURE";

export type PortfolioStateKey = "starting" | "proposed";

export type SegmentKind = "DIRECT" | "FUND" | "UNRESOLVED";

export interface ExplorerSegment {
  /** Stable id, unique within the model: `starting:DIRECT`, `proposed:FUND:SPY`, `proposed:UNRESOLVED`. */
  id: string;
  kind: SegmentKind;
  state: PortfolioStateKey;
  /** Portfolio fraction, copied from the response. */
  value: number;
  /** Set for FUND segments only. The response has no fund display name, so the id is the label. */
  fundId: string | null;
  /** Holdings date of the fund's file; null when the fund has no file or the segment is not a fund. */
  holdingsDate: string | null;
  sourceId: string | null;
  coverageStatus: FundCoverage["status"] | null;
  /** The `issuer_exposure_via_fund` record for this issuer, fund and state; null when the response has none. */
  evidenceId: string | null;
  /** The record's own formula text, e.g. "0.20 x 0.06 = 0.012"; null when there is no record. */
  formula: string | null;
}

export interface ExplorerColumn {
  state: PortfolioStateKey;
  /** DIRECT first, then one FUND segment per fund in response order, then UNRESOLVED when the API reports a non-zero bound. */
  segments: ExplorerSegment[];
  /** `lower` from the response: what is proven. */
  known: number;
  /** `upper` from the response: known plus what could not be attributed. */
  upper: number;
  /** True when `upper` and `known` differ in the response: the total is a range, not a number. */
  isRange: boolean;
}

export type LimitUnavailableReason = "NO_ISSUER_CAP_RULE" | "SEVERAL_ISSUER_CAP_RULES";

export interface ExplorerLimit {
  ruleId: string;
  /** The confirmed (or, in a preview, draft) maximum, copied from the rule result. */
  value: number;
  /** The engine's verdict for that rule on the proposed portfolio. It concerns the rule's own subject, which may be another issuer. */
  ruleStatus: RuleResult["status"];
  /** True when the result is a preview of draft rules: the limit is not a confirmed policy. */
  isDraft: boolean;
}

export type UnavailableReason = "EXECUTION_NOT_OK" | "NO_EXPOSURE_SECTION" | "NO_ISSUER_ROWS" | "ISSUER_NOT_IN_RESULT";

export interface ExplorerUnavailable {
  status: "UNAVAILABLE";
  reason: UnavailableReason;
  /** The engine's own message when execution failed; null otherwise. */
  message: string | null;
  dataOrigin: DataOrigin;
}

export interface ExplorerReady {
  status: "READY";
  issuerId: string;
  issuerName: string;
  /** Other issuers the response lists, for a selector. */
  availableIssuers: { issuerId: string; name: string }[];
  current: ExplorerColumn;
  proposed: ExplorerColumn;
  limit: ExplorerLimit | null;
  limitUnavailableReason: LimitUnavailableReason | null;
  /** Top of the shared drawing scale. Presentation only. */
  axisMax: number;
  policyVersion: number | null;
  preview: boolean;
  calculationVersion: string;
  valuationDate: string;
  dataOrigin: DataOrigin;
  /** Why the unresolved part exists, from the rule results; empty when nothing is unresolved. */
  unknownCauses: string[];
}

export type ExplorerModel = ExplorerReady | ExplorerUnavailable;

export interface BuildOptions {
  dataOrigin: DataOrigin;
  /** Defaults to the first issuer row, which the contract orders by largest proposed exposure. */
  issuerId?: string;
}

const STATE_NAME = { starting: "STARTING", proposed: "PROPOSED" } as const;

function viaFundEvidence(evidence: EvidenceRecord[], issuerId: string, fundId: string, state: PortfolioStateKey): EvidenceRecord | null {
  return (
    evidence.find(
      (record) =>
        record.metric_id === "issuer_exposure_via_fund" &&
        record.subject.kind === "ISSUER" &&
        record.subject.id === issuerId &&
        record.subject.via_fund_id === fundId &&
        record.subject.portfolio_state === STATE_NAME[state],
    ) ?? null
  );
}

function column(result: CheckResult, issuer: IssuerExposure, state: PortfolioStateKey, possibleExtra: number): ExplorerColumn {
  const breakdown = issuer[state];
  const coverage = new Map(result.data_coverage.map((row) => [row.fund_id, row]));
  const blank = { fundId: null, holdingsDate: null, sourceId: null, coverageStatus: null, evidenceId: null, formula: null };

  const segments: ExplorerSegment[] = [{ ...blank, id: `${state}:DIRECT`, kind: "DIRECT", state, value: breakdown.direct }];
  for (const path of breakdown.indirect_by_fund) {
    const fund = coverage.get(path.fund_id);
    const record = viaFundEvidence(result.evidence, issuer.issuer_id, path.fund_id, state);
    segments.push({
      id: `${state}:FUND:${path.fund_id}`,
      kind: "FUND",
      state,
      value: path.known,
      fundId: path.fund_id,
      holdingsDate: fund?.holdings_date ?? null,
      sourceId: fund?.source_id ?? null,
      coverageStatus: fund?.status ?? null,
      evidenceId: record?.evidence_id ?? null,
      formula: record?.formula ?? null,
    });
  }
  // The unresolved part is drawn only when the API itself reports a non-zero bound. It is the
  // API's `possible_extra` for this portfolio state, never a difference computed here.
  if (possibleExtra > 0) {
    segments.push({ ...blank, id: `${state}:UNRESOLVED`, kind: "UNRESOLVED", state, value: possibleExtra });
  }
  return { state, segments, known: breakdown.lower, upper: breakdown.upper, isRange: breakdown.upper !== breakdown.lower };
}

/** A round scale top just above the largest thing drawn. Presentation only. */
function axisTop(values: number[]): number {
  const largest = Math.max(0, ...values);
  const step = largest <= 0.1 ? 0.02 : largest <= 0.5 ? 0.05 : 0.1;
  return Math.min(1, Math.max(step, Math.ceil((largest * 1.08) / step) * step));
}

export function buildExplorerModel(result: CheckResult, options: BuildOptions): ExplorerModel {
  const unavailable = (reason: UnavailableReason, message: string | null = null): ExplorerUnavailable => ({
    status: "UNAVAILABLE",
    reason,
    message,
    dataOrigin: options.dataOrigin,
  });

  if (result.execution.status !== "OK") return unavailable("EXECUTION_NOT_OK", result.execution.message);
  if (result.exposure === null) return unavailable("NO_EXPOSURE_SECTION");
  if (result.exposure.issuers.length === 0) return unavailable("NO_ISSUER_ROWS");

  const issuer = options.issuerId
    ? result.exposure.issuers.find((row) => row.issuer_id === options.issuerId)
    : result.exposure.issuers[0];
  if (!issuer) return unavailable("ISSUER_NOT_IN_RESULT");

  const current = column(result, issuer, "starting", result.exposure.possible_extra.starting);
  const proposed = column(result, issuer, "proposed", result.exposure.possible_extra.proposed);

  // The result does not say which issuer a cap rule is scoped to, so a limit is shown only when
  // exactly one issuer-cap rule was evaluated. Otherwise it is reported as unavailable.
  const caps = result.rule_results.filter((rule) => rule.rule_type === "max_issuer_exposure");
  const cap = caps.length === 1 ? caps[0] : null;
  const limit: ExplorerLimit | null = cap
    ? { ruleId: cap.rule_id, value: cap.limit, ruleStatus: cap.status, isDraft: result.preview }
    : null;

  const hasUnresolved = current.isRange || proposed.isRange;
  const unknownCauses = hasUnresolved ? [...new Set(caps.flatMap((rule) => rule.unknown_causes))] : [];

  return {
    status: "READY",
    issuerId: issuer.issuer_id,
    issuerName: issuer.name,
    availableIssuers: result.exposure.issuers.map((row) => ({ issuerId: row.issuer_id, name: row.name })),
    current,
    proposed,
    limit,
    limitUnavailableReason: cap ? null : caps.length === 0 ? "NO_ISSUER_CAP_RULE" : "SEVERAL_ISSUER_CAP_RULES",
    axisMax: axisTop([current.upper, proposed.upper, limit?.value ?? 0]),
    policyVersion: result.policy_version,
    preview: result.preview,
    calculationVersion: result.calculation_version,
    valuationDate: result.valuation_date,
    dataOrigin: options.dataOrigin,
    unknownCauses,
  };
}
