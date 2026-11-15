"use client";

import { StageFrame } from "@/components/shell/StageFrame";
import { EmptyBlock, ErrorBlock, LoadingBlock, UnknownBlock } from "@/components/ui/AsyncStates";
import { Badge } from "@/components/ui/Badge";
import { Button, LinkButton } from "@/components/ui/Button";
import { Notice } from "@/components/ui/Notice";
import { Panel } from "@/components/ui/Panel";
import { Report } from "@/components/verdict/Report";
import type { Investigation } from "@/lib/contracts";
import { formatTime } from "@/lib/format";
import { countResult, isTerminalJobStatus, verdictHeadline } from "@/lib/verdict";
import { stageHref } from "@/state/stage";
import { useWorkflow } from "@/state/workflow";

const LEAD = "What the checks found, rule by rule, with the evidence behind every figure. An unknown is reported as unknown, never as a pass.";

function ReportList({ reports, viewedId, onOpen }: { reports: Investigation[]; viewedId: string | null; onOpen: (id: string) => void }) {
  return (
    <Panel title="Reports of this session" tone="sunken" description="A report never changes after it is produced. Earlier ones stay available.">
      <ol className="space-y-2" data-testid="report-list">
        {reports.map((report, index) => {
          const viewing = report.investigation_id === viewedId;
          const headline = report.result ? verdictHeadline(countResult(report.result)).title : "No result";
          return (
            <li
              key={report.investigation_id}
              className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 rounded-md border border-line bg-surface p-3"
              data-testid="report-entry"
              data-viewing={viewing ? "true" : undefined}
            >
              <p className="min-w-0 text-ink">
                <span className="font-semibold">
                  Report <span className="tabular">{index + 1}</span> · policy version <span className="tabular">{report.policy_version}</span>
                </span>
                <span className="block text-sm text-ink-muted">
                  Started <span className="tabular">{formatTime(report.created_at)}</span> · {headline}
                </span>
              </p>
              {viewing ? (
                <Badge tone="accent">Shown below</Badge>
              ) : (
                <Button size="sm" onClick={() => onOpen(report.investigation_id)}>
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
  const investigation = derived.viewedInvestigation;
  const reports = state.investigationIds.map((reportId) => state.investigations[reportId]).filter((i): i is Investigation => Boolean(i?.result));
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

  const result = investigation?.result ?? null;
  const running = !investigation || !isTerminalJobStatus(investigation.status);
  const pollProblem = running && state.activeInvestigationId === id && (derived.polling.phase === "timed_out" || derived.polling.phase === "failed");

  return (
    <StageFrame stage="verdict" lead={LEAD}>
      {reports.length > 1 ? <ReportList reports={reports} viewedId={id} onOpen={actions.viewReport} /> : null}

      {!isLatest && result ? (
        <Notice
          tone="info"
          role="status"
          title={`You are reading an earlier report, checked against policy version ${investigation?.policy_version}`}
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
            investigation
              ? `The investigation is still running: ${investigation.steps.length} ${investigation.steps.length === 1 ? "step" : "steps"} reported so far. No verdict exists yet.`
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

      {investigation?.status === "FAILED" ? (
        <ErrorBlock
          title="This investigation failed, so there is no verdict"
          message={investigation.error?.message ?? "The job ended without a result and gave no reason."}
        >
          <p>A failed run is not a pass and not a fail. Start the investigation again from Proposed purchase.</p>
        </ErrorBlock>
      ) : null}

      {investigation?.status === "SUCCEEDED" && !result ? (
        <UnknownBlock title="The investigation finished without a result">
          <p>The job reported success but returned no report. Nothing can be concluded from it.</p>
        </UnknownBlock>
      ) : null}

      {result && investigation ? (
        <>
          <Report result={result} policy={derived.policyByVersion(investigation.policy_version)} />
          <Notice
            tone="info"
            title="Something looks wrong, or you would decide differently?"
            action={
              <LinkButton href={stageHref("challenge")} size="sm">
                Challenge this result
              </LinkButton>
            }
          >
            <p>You can propose a correction to a fact, clarify a preference, or change a rule. This report stays as it is.</p>
          </Notice>
        </>
      ) : null}
    </StageFrame>
  );
}
