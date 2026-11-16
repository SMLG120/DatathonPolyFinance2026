/**
 * Shapes of `POST /evidence/investigate` (backend/api/holdings_evidence). Additive to the shared contract: these
 * types are read-only views of what the service calculated. Percentages are percentage points; `null` means the
 * value is unknown and must be shown as "Unknown", never as 0.
 */
export type EvidenceStatus = "sufficient_evidence" | "partial_evidence" | "insufficient_evidence";
export type StatementKind = "VERIFIED" | "UNRESOLVED" | "HYPOTHETICAL" | "NEXT_EVIDENCE";

export interface EvidenceStatement {
  kind: StatementKind;
  text: string;
  source_ids: string[];
}

export interface EvidenceSummary {
  scope: "fund" | "portfolio";
  scope_label: string;
  verified_weight_pct: number | null;
  unresolved_weight_pct: number | null;
  coverage_basis: string;
  coverage_basis_label: string;
  data_quality_status: EvidenceStatus;
  last_verified_holdings_date: string | null;
  source_confidence: string | null;
  sources_investigated: number;
}

export interface EvidenceSource {
  source_id: string | null;
  publisher: string | null;
  title: string | null;
  url: string | null;
  as_of_date: string | null;
  retrieval_date: string | null;
  subject: string;
  verification: "verified" | "provisional";
}

export interface ExposureBounds {
  level: "fund" | "portfolio";
  category: string;
  unit: string;
  verified_exposure_pct: number | null;
  conditional_min_pct: number | null;
  conditional_max_pct: number | null;
  basis: string;
}

export interface FundEvidence {
  fund: string;
  calculation_basis: string | null;
  data_quality_issues: { code: string; severity: string; detail: string }[];
  limitations: string[];
}

export interface EvidenceResponse {
  schema_version: string;
  status: EvidenceStatus;
  persona_id: string;
  fund_id: string | null;
  question: { topic: string; supported: boolean; sectors_recognised: string[] };
  summary: EvidenceSummary;
  fund: FundEvidence | null;
  portfolio: { basis: string };
  verified_findings: EvidenceStatement[];
  missing_evidence: EvidenceStatement[];
  hypothetical_scenarios: EvidenceStatement[];
  next_evidence: EvidenceStatement[];
  exposure_bounds: ExposureBounds[];
  headline: string;
  explanation: string;
  explanation_source: "model" | "template";
  model_status: string;
  sources: EvidenceSource[];
  retrieval: { external_retrieval: string; message: string | null };
  limitations: string[];
}

export interface EvidenceRequest {
  persona_id: string;
  fund_id: string | null;
  question: string;
  policy_id: string | null;
  policy_version: number | null;
}

/** Asked when a scope is opened, to fill the evidence summary. Same text as the service's OVERVIEW_QUESTION. */
export const OVERVIEW_QUESTION = "Give me an overview of the evidence.";

/** The questions offered as buttons. Same list as the service's SUGGESTED_QUESTIONS (checked by a test). */
export const SUGGESTED_QUESTIONS = [
  "What data is missing from this ETF?",
  "How much of my portfolio is verified?",
  "Could missing holdings violate my technology limit?",
  "Which sources were checked?",
  "What evidence should I retrieve next?",
] as const;

export const MAX_QUESTION_CHARS = 500;
