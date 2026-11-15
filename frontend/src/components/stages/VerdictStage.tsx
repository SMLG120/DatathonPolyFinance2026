"use client";

import { StageFrame } from "@/components/shell/StageFrame";
import { EmptyBlock, ErrorBlock, LoadingBlock, UnknownBlock } from "@/components/ui/AsyncStates";
import { Badge } from "@/components/ui/Badge";
import { Button, LinkButton } from "@/components/ui/Button";
import { Notice } from "@/components/ui/Notice";
import { Panel } from "@/components/ui/Panel";
import { ExecutionState } from "@/components/verdict/ExecutionState";
import { Report } from "@/components/verdict/Report";
import type { InvestigationJob } from "@/lib/contracts";
import { formatTime } from "@/lib/format";
import { assessResult } from "@/lib/result";
import { isTerminalJobStatus, verdictHeadline } from "@/lib/verdict";
import { stageHref } from "@/state/stage";
import { useWorkflow } from "@/state/workflow";

const LEAD = "See whether your idea fits your limits. Open any figure to see its evidence.";

/** One line for a report in the list: the engine's headline when the check ran, the execution state otherwise. */
function reportLine(job: InvestigationJob): string {
  const assessment = assessResult(job.result);
  if (assessment.kind === "ok") return verdictHeadline(assessment.result.summary).title;
  if (assessment.kind === "not_executed") return "The check did not run";
  return "No readable result";
}

function ReportList({ reports, viewedId, onOpen }: { reports: InvestigationJob[]; viewedId: string | null; onOpen: (id: string) => void }) {
  return (
    <Panel title="Reports of this session" tone="sunken" figures description="A report never changes after it is produced. Earlier ones stay available.">
      <ol className="space-y-2" data-testid="report-list">
        {reports.map((report, index) => {
          const viewing = report.id === viewedId;
          return (
            <li
              key={report.id}
              className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 rounded-md border border-line bg-surface p-3"
              data-testid="report-entry"
              data-viewing={viewing ? "true" : undefined}
            >
              <p className="min-w-0 text-ink">
                <span className="font-semibold">
                  Report <span className="tabular">{index + 1}</span> · policy version <span className="tabular">{report.policy_version}</span>
                </span>
                <span className="block text-sm text-ink-muted">
                  Started <span className="tabular">{formatTime(report.created_at)}</span> · {reportLine(report)}
                </span>
              </p>
              {viewing ? (
                <Badge tone="accent">Shown above</Badge>
              ) : (
                <Button size="sm" onClick={() => onOpen(report.id)}>
                  Open report {index + 1}
                </Button>
              )}
            </li>
          );
        })}
      </ol>
    </Panel>
  );
}

/** Stage 5: the report of the investigation being viewed. */
export function VerdictStage() {
  const { state, actions, derived } = useWorkflow();
  const id = derived.viewedInvestigationId;
  const job = derived.viewedInvestigation;
  const reports = state.investigationIds.map((reportId) => state.investigations[reportId]).filter((candidate): candidate is InvestigationJob => Boolean(candidate?.result));
  const isLatest = id === derived.latestInvestigationId;

  if (!id) {
    return (
      <StageFrame stage="verdict" lead={LEAD}>
        <EmptyBlock
          title="There is no result yet"
          action={
            <LinkButton href={stageHref("purchase")} size="sm">
              Go to Proposed purchase
            </LinkButton>
          }
        >
          <p>A verdict exists only after an investigation has run. Nothing is shown in its place.</p>
        </EmptyBlock>
      </StageFrame>
    );
  }

  const running = !job || !isTerminalJobStatus(job.status);
  const pollProblem = running && state.activeInvestigationId === id && (derived.polling.phase === "timed_out" || derived.polling.phase === "failed");
  const assessment = job?.status === "SUCCEEDED" && job.result !== null ? assessResult(job.result) : null;

  return (
    <StageFrame stage="verdict" lead={LEAD}>
      {!isLatest && assessment ? (
        <Notice
          tone="info"
          role="status"
          title={`You are reading an earlier report, checked against policy version ${job?.policy_version}`}
          action={
            <Button size="sm" onClick={() => actions.viewReport(null)}>
              Back to the latest
            </Button>
          }
        >
          <p>It is shown exactly as it was produced. Later rule changes do not alter it.</p>
        </Notice>
      ) : null}

      {running && !pollProblem ? (
        <LoadingBlock
          label={
            job
              ? `The investigation is still running: ${job.steps.length} ${job.steps.length === 1 ? "step" : "steps"} reported so far. No verdict exists yet.`
              : "The investigation was accepted. No verdict exists yet."
          }
        />
      ) : null}
      {running ? (
        <p>
          <LinkButton href={stageHref("investigation")} size="sm">
            See the investigation steps
          </LinkButton>
        </p>
      ) : null}
      {pollProblem ? (
        <ErrorBlock
          title={derived.polling.phase === "timed_out" ? "No final answer within the time limit" : "The status of the investigation could not be fetched"}
          message={derived.polling.error ?? "The investigation did not report a final status. It may still be running."}
          onRetry={actions.retryPolling}
          retryLabel="Check again"
        >
          <p>No verdict is shown, because none was received.</p>
        </ErrorBlock>
      ) : null}

      {job?.status === "FAILED" ? (
        <ErrorBlock title="This investigation failed, so there is no verdict" message={job.failure?.message ?? "The job ended without a result and gave no reason."}>
          <p data-testid="failure-code">
            {job.failure ? (
              <>
                Reported by the service as <span className="font-mono text-[0.8125rem]">{job.failure.code}</span>.{" "}
              </>
            ) : null}
            A failed run is not a pass and not a fail.{" "}
            {job.failure?.retryable === false ? "Starting it again is not expected to help." : "You can start the investigation again from Proposed purchase."}
          </p>
        </ErrorBlock>
      ) : null}

      {job?.status === "SUCCEEDED" && job.result === null && job.clarification ? (
        <UnknownBlock title="The investigation stopped to ask a question">
          <div className="space-y-2" data-testid="job-clarification">
            <p>
              About &ldquo;{job.clarification.about_words}&rdquo;: {job.clarification.question}
            </p>
            <ul className="list-disc space-y-1 pl-5">
              {job.clarification.options.map((option) => (
                <li key={option.option_id}>
                  <span className="font-semibold">{option.label}</span>
                  {option.supported ? "" : " (not supported)"} — {option.description}
                </li>
              ))}
            </ul>
            <p>Nothing was checked, so there is no verdict. State the request as an instrument and a final weight in Proposed purchase.</p>
          </div>
        </UnknownBlock>
      ) : null}

      {job?.status === "SUCCEEDED" && job.result === null && !job.clarification ? (
        <UnknownBlock title="The investigation finished without a result">
          <p>The job reported success but returned no report. Nothing can be concluded from it.</p>
        </UnknownBlock>
      ) : null}

      {job && assessment?.kind === "unreadable" ? (
        <UnknownBlock title="The result could not be read">
          <p data-testid="result-unreadable">
            The service answered, but not in the agreed format. No part of it is shown, because a partly read result could be mistaken for a verdict.
          </p>
        </UnknownBlock>
      ) : null}

      {job && assessment?.kind === "not_executed" ? (
        <div data-testid="report-not-executed">
          <ExecutionState execution={assessment.result.execution} context="report" />
        </div>
      ) : null}

      {job && assessment?.kind === "ok" ? (
        <>
          <Report
            job={job}
            result={assessment.result}
            policy={derived.policyFor(assessment.result)}
            objectives={state.objectives}
            instruments={state.portfolio.data?.instruments ?? {}}
          />

        </>
      ) : null}

      {reports.length > 1 ? <ReportList reports={reports} viewedId={id} onOpen={actions.viewReport} /> : null}
    </StageFrame>
  );
}
