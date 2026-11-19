"use client";

import { createPortal } from "react-dom";
import { PortfolioUsedLabel } from "@/components/portfolio/PortfolioChecked";
import { StageFrame } from "@/components/shell/StageFrame";
import { EmptyBlock, ErrorBlock, LoadingBlock, UnknownBlock } from "@/components/ui/AsyncStates";
import { Badge } from "@/components/ui/Badge";
import { Button, LinkButton } from "@/components/ui/Button";
import { Notice } from "@/components/ui/Notice";
import { Panel } from "@/components/ui/Panel";
import { ExecutionState } from "@/components/verdict/ExecutionState";
import { PrintReport, printDocumentTitle, useReportPrint } from "@/components/verdict/PrintReport";
import { Report } from "@/components/verdict/Report";
import type { InvestigationJob, Portfolio } from "@/lib/contracts";
import { formatTime } from "@/lib/format";
import { assessResult } from "@/lib/result";
import { isTerminalJobStatus, verdictHeadline } from "@/lib/verdict";
import { stageHref } from "@/state/stage";
import { useRuntime } from "@/state/runtime";
import { useWorkflow } from "@/state/workflow";
import { t, tf } from "@/lib/i18n";
import { tn } from "@/lib/i18n-nodes";

const LEAD = "See whether your idea fits your limits. Open any figure to see its evidence.";

/** One line for a report in the list: the engine's headline when the check ran, the execution state otherwise. */
function reportLine(job: InvestigationJob): string {
  const assessment = assessResult(job.result);
  if (assessment.kind === "ok") return verdictHeadline(assessment.result.summary).title;
  if (assessment.kind === "not_executed") return t("The check did not run");
  return t("No readable result");
}

interface ReportListProps {
  reports: InvestigationJob[];
  viewedId: string | null;
  onOpen: (id: string) => void;
  /** The persona's scenario portfolio and name, to say which portfolio each report was checked against. */
  scenarioPortfolio: Portfolio | null;
  personaName: string;
}

function ReportList({ reports, viewedId, onOpen, scenarioPortfolio, personaName }: ReportListProps) {
  return (
    <Panel title={t("Reports of this session")} tone="sunken" figures description={t("A report never changes after it is produced. Earlier ones stay available.")}>
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
                  {tn("Report {number} · policy version {version}", {
                    number: <span className="tabular">{index + 1}</span>,
                    version: <span className="tabular">{report.policy_version}</span>,
                  })}
                </span>
                <span className="block text-sm text-ink-muted">
                  {tn("Started {time}", { time: <span className="tabular">{formatTime(report.created_at)}</span> })} · {reportLine(report)}
                </span>
                {/* Two reports under one policy version can differ by portfolio alone: each entry names its job's own. */}
                {report.portfolio ? (
                  <span className="mt-1 block">
                    <PortfolioUsedLabel portfolio={report.portfolio} scenarioPortfolio={scenarioPortfolio} personaName={personaName} testId="report-entry-portfolio" />
                  </span>
                ) : null}
              </p>
              {viewing ? (
                <Badge tone="accent">{t("Shown above")}</Badge>
              ) : (
                <Button size="sm" onClick={() => onOpen(report.id)}>
                  {tf("Open report {number}", { number: index + 1 })}
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
  const { config } = useRuntime();
  // The print document exists only while the browser prints, and only for a report that can be read.
  const { printing, print } = useReportPrint(job ? printDocumentTitle(job) : null);

  if (!id) {
    return (
      <StageFrame stage="verdict" lead={t(LEAD)}>
        <EmptyBlock
          title={t("There is no result to show yet")}
          action={
            <LinkButton href={stageHref("purchase")} size="sm" data-testid="empty-result-action">
              {t("Go to Test an idea")}
            </LinkButton>
          }
        >
          <p>{t("A result exists only after you check an idea. Nothing is shown in its place.")}</p>
          <p data-testid="empty-result-reload-note">
            {t("Results are kept only while this tab stays open: reloading the page or opening it from a saved link starts a new session. Choose a profile, confirm your limits, then check your idea again.")}
          </p>
        </EmptyBlock>
      </StageFrame>
    );
  }

  const running = !job || !isTerminalJobStatus(job.status);
  const pollProblem = running && state.activeInvestigationId === id && (derived.polling.phase === "timed_out" || derived.polling.phase === "failed");
  const assessment = job?.status === "SUCCEEDED" && job.result !== null ? assessResult(job.result) : null;

  return (
    <StageFrame stage="verdict" lead={t(LEAD)}>
      {!isLatest && assessment ? (
        <Notice
          tone="info"
          role="status"
          title={tf("You are reading an earlier report, checked against policy version {version}", { version: String(job?.policy_version) })}
          action={
            <Button size="sm" onClick={() => actions.viewReport(null)}>
              {t("Back to the latest")}</Button>
          }
        >
          <p>{t("It is shown exactly as it was produced. Later rule changes do not alter it.")}</p>
        </Notice>
      ) : null}

      {running && !pollProblem ? (
        <LoadingBlock
          label={
            job
              ? tf(
                  job.steps.length === 1
                    ? "The investigation is still running: {count} step reported so far. No verdict exists yet."
                    : "The investigation is still running: {count} steps reported so far. No verdict exists yet.",
                  { count: job.steps.length },
                )
              : t("The investigation was accepted. No verdict exists yet.")
          }
        />
      ) : null}
      {running ? (
        <p>
          <LinkButton href={stageHref("investigation")} size="sm">
            {t("See the investigation steps")}</LinkButton>
        </p>
      ) : null}
      {pollProblem ? (
        <ErrorBlock
          title={derived.polling.phase === "timed_out" ? t("No final answer within the time limit") : t("The status of the investigation could not be fetched")}
          message={derived.polling.error ?? t("The investigation did not report a final status. It may still be running.")}
          onRetry={actions.retryPolling}
          retryLabel={t("Check again")}
        >
          <p>{t("No verdict is shown, because none was received.")}</p>
        </ErrorBlock>
      ) : null}

      {job?.status === "FAILED" ? (
        <ErrorBlock title={t("This investigation failed, so there is no verdict")} message={job.failure?.message ?? t("The job ended without a result and gave no reason.")}>
          <p data-testid="failure-code">
            {job.failure ? (
              <>
                {tn("Reported by the service as {code}.", { code: <span className="font-mono text-[0.8125rem]">{job.failure.code}</span> })}{" "}
              </>
            ) : null}
            {t("A failed run is not a pass and not a fail.")}{" "}
            {job.failure?.retryable === false ? t("Starting it again is not expected to help.") : t("You can start the investigation again from Proposed purchase.")}
          </p>
        </ErrorBlock>
      ) : null}

      {job?.status === "SUCCEEDED" && job.result === null && job.clarification ? (
        <UnknownBlock title={t("The investigation stopped to ask a question")}>
          <div className="space-y-2" data-testid="job-clarification">
            <p>
              {tn("About “{words}”:", { words: <span lang="en">{job.clarification.about_words}</span> })} <span lang="en">{job.clarification.question}</span>
            </p>
            <ul className="list-disc space-y-1 pl-5">
              {job.clarification.options.map((option) => (
                <li key={option.option_id}>
                  <span className="font-semibold" lang="en">
                    {option.label}
                  </span>
                  {option.supported ? "" : ` ${t("(not supported)")}`}: <span lang="en">{option.description}</span>
                </li>
              ))}
            </ul>
            <p>{t("Nothing was checked, so there is no verdict. State the request as an instrument and a final weight in Proposed purchase.")}</p>
          </div>
        </UnknownBlock>
      ) : null}

      {job?.status === "SUCCEEDED" && job.result === null && !job.clarification ? (
        <UnknownBlock title={t("The investigation finished without a result")}>
          <p>{t("The job reported success but returned no report. Nothing can be concluded from it.")}</p>
        </UnknownBlock>
      ) : null}

      {job && assessment?.kind === "unreadable" ? (
        <UnknownBlock title={t("The result could not be read")}>
          <p data-testid="result-unreadable">
            {t("The service answered, but not in the agreed format. No part of it is shown, because a partly read result could be mistaken for a verdict.")}</p>
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
            scenarioPortfolio={state.portfolio.data?.scenario.portfolio ?? null}
            personaName={state.portfolio.data?.scenario.persona.display_name}
            onPrint={print}
          />
          {/* A child of <body>, so the print style sheet can hide the whole application around it. */}
          {printing
            ? createPortal(
                <PrintReport
                  job={job}
                  result={assessment.result}
                  policy={derived.policyFor(assessment.result)}
                  objectives={state.objectives}
                  instruments={state.portfolio.data?.instruments ?? {}}
                  scenarioPortfolio={state.portfolio.data?.scenario.portfolio ?? null}
                  personaName={state.portfolio.data?.scenario.persona.display_name ?? null}
                  testData={config.mode === "fixtures"}
                />,
                document.body,
              )
            : null}

        </>
      ) : null}

      {reports.length > 1 ? (
        <ReportList
          reports={reports}
          viewedId={id}
          onOpen={actions.viewReport}
          scenarioPortfolio={state.portfolio.data?.scenario.portfolio ?? null}
          personaName={state.portfolio.data?.scenario.persona.display_name ?? t("This persona")}
        />
      ) : null}
    </StageFrame>
  );
}
