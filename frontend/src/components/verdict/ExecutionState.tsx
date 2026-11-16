import { Notice } from "@/components/ui/Notice";
import type { Execution } from "@/lib/contracts";
import { t } from "@/lib/i18n";
import { tn } from "@/lib/i18n-nodes";

const TITLES: Record<Execution["status"], string> = {
  OK: "The check ran",
  INVALID_REQUEST: "This request cannot be evaluated",
  ERROR: "The check could not be run",
};

/**
 * The execution state of a check that did not run (`execution.status` is not
 * OK). It is shown instead of a verdict: no rule was evaluated, so nothing
 * here is styled or worded as pass, fail or unknown.
 */
export function ExecutionState({ execution, context }: { execution: Execution; context: "preview" | "report" }) {
  return (
    <Notice tone={execution.status === "INVALID_REQUEST" ? "info" : "caution"} title={t(TITLES[execution.status])}>
      <div data-testid="execution-state" data-execution-status={execution.status} className="space-y-2">
        <p data-testid="execution-message" lang={execution.message ? "en" : undefined}>
          {execution.message ?? t("The service gave no reason.")}
        </p>
        {execution.code ? (
          <p className="text-sm text-ink-muted">
            {tn("Reported by the service as {code}.", { code: <span className="font-mono text-[0.8125rem] text-ink">{execution.code}</span> })}
          </p>
        ) : null}
        <p>
          {context === "preview"
            ? t("No rule was evaluated, so there is no preview to show. Nothing was assumed in its place.")
            : t("No rule was evaluated, so there is no verdict to show. Nothing was assumed in its place.")}
        </p>
      </div>
    </Notice>
  );
}
