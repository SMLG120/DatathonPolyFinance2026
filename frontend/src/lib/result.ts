import type { CheckResult } from "@/lib/contracts";

/**
 * What a result body is, decided before anything is drawn.
 *
 * Only `ok` may be shown as a verdict (pass / fail / unknown styling, counts,
 * a headline about the rules). Everything else is shown as what it is:
 * - `not_executed`: the engine refused or failed to run the request
 *   (`execution.status` is not OK). The execution state is shown, never a
 *   verdict, whatever else the body contains.
 * - `unreadable`: the body is not the shape the shared contract describes.
 */
export type ResultAssessment = { kind: "ok"; result: CheckResult } | { kind: "not_executed"; result: CheckResult } | { kind: "unreadable" };

const isObject = (value: unknown): value is Record<string, unknown> => typeof value === "object" && value !== null && !Array.isArray(value);

const LISTS = ["rule_results", "rules_not_evaluated", "starting_portfolio_findings", "data_coverage", "goal_context", "evidence", "disclosures"] as const;

/** The members every screen reads without checking. Deeper validation belongs to the service. */
export function isReadableResult(value: unknown): value is CheckResult {
  if (!isObject(value)) return false;
  if (!isObject(value.execution) || typeof value.execution.status !== "string") return false;
  if (!isObject(value.summary) || typeof value.summary.headline !== "string" || !isObject(value.summary.counts)) return false;
  if (!isObject(value.purchase_request) || !isObject(value.policy_consistency)) return false;
  const counts = value.summary.counts;
  if (typeof counts.pass !== "number" || typeof counts.fail !== "number" || typeof counts.unknown !== "number") return false;
  if (typeof value.summary.rules_evaluated !== "number") return false;
  return LISTS.every((name) => Array.isArray(value[name]));
}

export function assessResult(value: unknown): ResultAssessment {
  if (!isReadableResult(value)) return { kind: "unreadable" };
  if (value.execution.status !== "OK") return { kind: "not_executed", result: value };
  return { kind: "ok", result: value };
}
