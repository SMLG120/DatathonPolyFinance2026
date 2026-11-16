import { Badge } from "@/components/ui/Badge";
import { CheckIcon, ClockIcon, ErrorIcon } from "@/components/ui/icons";
import type { InvestigationStep, StepStatus } from "@/lib/contracts";
import { cn } from "@/lib/cn";
import { formatTime } from "@/lib/format";
import { t } from "@/lib/i18n";

const TOOL_LABELS: Record<string, string> = {
  get_portfolio: "Read the portfolio",
  get_policy: "Read the confirmed policy",
  simulate_change: "Apply the purchase to a copy of the portfolio",
  get_holdings: "Read the holdings of the funds",
  compute_exposure: "Compute exposure, direct and through funds",
  lookup_controversy_evidence: "Look up controversy records",
  replay_period: "Replay the historical period",
  check_rules: "Compare the measured values with the confirmed rules",
  max_compliant_amount: "Find the largest purchase that respects the rules",
};

/** Plain-language name of a tool, or null for a tool this interface does not know. */
export function toolLabel(tool: string): string | null {
  const label = TOOL_LABELS[tool];
  return label ? t(label) : null;
}

const STEP_STATUS: Record<StepStatus, { text: string; tone: "accent" | "fail" | "neutral"; dashed: boolean }> = {
  OK: { text: "Completed", tone: "accent", dashed: false },
  ERROR: { text: "Failed", tone: "fail", dashed: false },
  RUNNING: { text: "In progress", tone: "neutral", dashed: true },
};

function StepIcon({ status }: { status: StepStatus }) {
  if (status === "OK") return <CheckIcon size={16} />;
  if (status === "ERROR") return <ErrorIcon size={16} />;
  return <ClockIcon size={16} />;
}

export interface StepTimelineProps {
  steps: InvestigationStep[];
  /** True while the job has not reached a final status. */
  waiting: boolean;
}

/**
 * The steps a job has actually reported, in order, and nothing else.
 *
 * There is no scripted or animated sequence: a row exists only because the
 * job returned it. While the job is still running, a plain "Waiting for the
 * next step" line stands where the next real step will appear.
 */
export function StepTimeline({ steps, waiting }: StepTimelineProps) {
  const ordered = steps.slice().sort((a, b) => a.seq - b.seq);
  const reportedRunning = ordered.some((step) => step.status === "RUNNING");
  return (
    <div role="log" aria-label={t("Steps reported by the investigation")} aria-live="polite" data-testid="step-timeline">
      <ol className="space-y-3">
        {ordered.map((step) => {
          const label = toolLabel(step.tool);
          const status = STEP_STATUS[step.status];
          return (
            <li
              key={step.seq}
              className={cn("rounded-md border bg-surface p-3 sm:p-4", step.status === "ERROR" ? "border-fail" : "border-line", step.status === "RUNNING" && "border-dashed border-line-strong")}
              data-testid="timeline-step"
              data-step-status={step.status}
            >
              <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-1">
                <p className="font-semibold text-ink">
                  <span className="tabular">{t("Step")} {step.seq}</span>
                  {label ? <span> · {label}</span> : null}
                </p>
                <Badge tone={status.tone} dashed={status.dashed} icon={<StepIcon status={step.status} />}>
                  {t(status.text)}
                </Badge>
              </div>
              <p className="mt-0.5 text-sm text-ink-muted">
                {t("Tool")} <span className="font-mono text-[0.8125rem] text-ink">{step.tool}</span> ·{" "}
                {step.initiated_by === "MODEL" ? t("requested by the model") : t("run by the server")} ·{" "}
                <span className="tabular">
                  {step.finished_at ? `${t("finished")} ${formatTime(step.finished_at)}` : `${t("started")} ${formatTime(step.started_at)}`}
                </span>
              </p>
              <dl className="mt-2 grid gap-x-6 gap-y-2 sm:grid-cols-2">
                <div>
                  <dt className="text-sm font-semibold text-ink-muted">{t("Input")}</dt>
                  <dd className="tabular text-ink">{step.input_summary}</dd>
                </div>
                <div>
                  <dt className="text-sm font-semibold text-ink-muted">{t("Result")}</dt>
                  <dd className="tabular text-ink">{step.result_summary ?? t("Not available yet")}</dd>
                </div>
              </dl>
            </li>
          );
        })}
        {waiting && !reportedRunning ? (
          <li className="flex items-center gap-3 rounded-md border border-dashed border-line-strong bg-canvas p-3 text-ink-muted sm:p-4" data-testid="timeline-waiting">
            <ClockIcon className="flex-none" />
            <span>{t("Waiting for the next step")}</span>
          </li>
        ) : null}
      </ol>
    </div>
  );
}
