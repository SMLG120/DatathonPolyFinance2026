import type { CheckResult } from "@/lib/contracts";

/**
 * Integration slots for the 3D exposure explorer.
 *
 * The explorer is built in another session. Until it is wired in, each slot
 * renders nothing, so the stages look and behave exactly as they do without
 * it. A slot receives the engine's `CheckResult` and nothing else: the
 * explorer reads `result.exposure` (and whatever else it needs) from it and
 * must not compute figures of its own.
 */

/** Verdict stage, beside the 2D exposure chart. `result` is the report on screen; its execution status is OK. */
export interface VerdictExposureExplorerSlotProps {
  result: CheckResult;
}

export function VerdictExposureExplorerSlot({ result }: VerdictExposureExplorerSlotProps) {
  void result;
  return null;
}

/**
 * Purchase stage, under the preview of the entered purchase. `result` is the
 * service's answer to POST /check for the request in the form, or null while
 * there is none (form incomplete, no confirmed policy, request in flight,
 * request not executable, or no recorded answer in fixtures mode).
 */
export interface PurchaseExposureExplorerSlotProps {
  result: CheckResult | null;
}

export function PurchaseExposureExplorerSlot({ result }: PurchaseExposureExplorerSlotProps) {
  void result;
  return null;
}
