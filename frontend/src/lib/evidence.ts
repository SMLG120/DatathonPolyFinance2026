import type { CheckResult, EvidenceLabel, EvidencePeriod, EvidenceRecord, EvidenceSubject, EvidenceUnit, MetricId } from "@/lib/contracts";
import { formatDate, formatFraction } from "@/lib/format";

/**
 * Wording for evidence records. A record is shown exactly as the service sent
 * it: the value in its own unit, the subject, the period, the label.
 */

const METRIC_LABELS: Record<MetricId, string> = {
  position_weight: "Position weight",
  cash_weight: "Cash weight",
  cash_after_purchase: "Cash after the purchase",
  fund_constituent_weight: "Weight of a holding inside a fund",
  fund_coverage_fraction: "Share of a fund reported in its holdings file",
  unattributed_fund_weight: "Fund weight not attributed to any company",
  issuer_direct_exposure: "Direct exposure to a company",
  issuer_exposure_via_fund: "Exposure to a company through a fund",
  exposure_lower: "Measured exposure (lower bound)",
  exposure_upper: "Possible exposure (upper bound)",
  rule_threshold: "Rule threshold",
  gap_to_limit: "Gap to the limit",
  scenario_instrument_return: "Return of an instrument over the replayed period",
  scenario_terminal_return: "Return of the allocation over the replayed period",
  scenario_max_drawdown: "Deepest fall inside the replayed period",
  scenario_loss: "Loss over the replayed period",
  price_adj_close: "Adjusted closing price",
  fx_usdcad: "Exchange rate (CAD per USD)",
  fx_rate_age_days: "Age of the exchange rate",
  price_age_days: "Age of the price",
  max_compliant_final_weight: "Largest final direct weight that passes every rule",
  max_compliant_additional_purchase: "Largest additional purchase that passes every rule",
  sector_label: "Sector label",
  controversy_record: "Controversy registry record",
  holdings_date: "Date of the holdings file",
};

export function metricLabel(metricId: MetricId): string {
  return METRIC_LABELS[metricId] ?? metricId;
}

const LABEL_TEXT: Record<EvidenceLabel, string> = {
  FACT: "Fact",
  ASSUMPTION: "Assumption",
  FICTIONAL_SCENARIO: "Fictional scenario",
  CALCULATION: "Calculation",
};

const LABEL_MEANING: Record<EvidenceLabel, string> = {
  FACT: "Taken unchanged from a cited source, or a threshold you stated and confirmed.",
  ASSUMPTION: "A modelling choice, or a draft value in a preview.",
  FICTIONAL_SCENARIO: "Invented for the simulation: persona weights, scenario thresholds, the hypothetical purchase.",
  CALCULATION: "Computed by the engine from the values listed below.",
};

export function evidenceLabelText(label: EvidenceLabel): string {
  return LABEL_TEXT[label] ?? label;
}

export function evidenceLabelMeaning(label: EvidenceLabel): string {
  return LABEL_MEANING[label] ?? "";
}

const UNIT_TEXT: Record<EvidenceUnit, string> = {
  fraction: "share (fraction of the portfolio or of a fund)",
  price: "price",
  fx_rate: "exchange rate",
  days: "days",
  count: "count",
  date: "date",
  text: "text",
};

export function unitText(unit: EvidenceUnit): string {
  return UNIT_TEXT[unit] ?? unit;
}

/** A value in the unit the record declares. Fractions are shown as percentages to two decimals; nothing is ever shown as 0 when it is missing. */
export function formatValueInUnit(value: number | string | null, unit: EvidenceUnit, currency: string | null = null): string {
  if (value === null) return "Not available";
  if (typeof value === "string") return unit === "date" ? formatDate(value) : value;
  switch (unit) {
    case "fraction":
      return formatFraction(value, { decimals: 2 });
    case "price":
      return `${value.toFixed(2)}${currency ? ` ${currency}` : ""}`;
    case "fx_rate":
      return value.toFixed(4);
    case "days":
      return `${value} ${value === 1 ? "day" : "days"}`;
    case "count":
    case "date":
    case "text":
      return String(value);
  }
}

export function formatEvidenceValue(record: EvidenceRecord): string {
  return formatValueInUnit(record.value, record.unit, record.currency);
}

const STATE_TEXT: Record<EvidenceSubject["portfolio_state"], string> = {
  STARTING: "before the purchase",
  PROPOSED: "after the purchase",
  NOT_APPLICABLE: "",
};

const KIND_TEXT: Record<EvidenceSubject["kind"], string> = {
  INSTRUMENT: "Instrument",
  ISSUER: "Company",
  FUND: "Fund",
  PORTFOLIO: "Portfolio",
  RULE: "Rule",
  FX: "Exchange rate",
};

/** "Company NVIDIA, through SPY, after the purchase" */
export function subjectText(subject: EvidenceSubject): string {
  const parts = [`${KIND_TEXT[subject.kind] ?? subject.kind} ${subject.id}`];
  if (subject.via_fund_id) parts.push(`through ${subject.via_fund_id}`);
  const state = STATE_TEXT[subject.portfolio_state];
  if (state) parts.push(state);
  return parts.join(", ");
}

export function periodText(period: EvidencePeriod): string {
  return period.type === "AS_OF" ? `As of ${formatDate(period.date)}` : `${formatDate(period.start_date)} to ${formatDate(period.end_date)}`;
}

/** The records a calculated value was computed from, in the order the service lists them. Missing ids are reported, not dropped. */
export function derivedRecords(result: CheckResult, record: EvidenceRecord): { found: EvidenceRecord[]; missing: string[] } {
  const found: EvidenceRecord[] = [];
  const missing: string[] = [];
  for (const id of record.derived_from) {
    const source = result.evidence.find((item) => item.evidence_id === id);
    if (source) found.push(source);
    else missing.push(id);
  }
  return { found, missing };
}
