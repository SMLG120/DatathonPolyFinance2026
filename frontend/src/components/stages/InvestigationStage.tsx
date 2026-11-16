"use client";

import { PortfolioUsedLabel } from "@/components/portfolio/PortfolioChecked";
import { StageFrame } from "@/components/shell/StageFrame";
import { StepTimeline } from "@/components/timeline/StepTimeline";
import { EmptyBlock, ErrorBlock, LoadingBlock } from "@/components/ui/AsyncStates";
import { JobStatusBadge } from "@/components/ui/Badge";
import { Button, LinkButton } from "@/components/ui/Button";
import { ArrowRightIcon } from "@/components/ui/icons";
import { Notice } from "@/components/ui/Notice";
import { Fact, Facts, Panel } from "@/components/ui/Panel";
import type { InvestigationJob } from "@/lib/contracts";
import { customPortfolioOfReport } from "@/lib/customize";
import { formatDateTime, formatTime } from "@/lib/format";
import { describePurchase } from "@/lib/portfolio";
import { isTerminalJobStatus } from "@/lib/verdict";
import { useRuntime } from "@/state/runtime";
import { goToStage, stageHref } from "@/state/stage";
import { useWorkflow } from "@/state/workflow";
import { t, tf } from "@/lib/i18n";

const LEAD = "Each step below is one the investigation actually completed. Steps appear as the job reports them; nothing is scripted in advance.";

/** The request a job was asked to check: the structured one once resolved, else the user's words. */
export function describeJobRequest(job: InvestigationJob): string {
  if (job.resolved_request) return describePurchase(job.resolved_request);
  if (job.request.instrument_id !== null && job.request.target_direct_weight !== null) return describePurchase(job.request);
  return tf("“{words}” (free text, not resolved into a request yet)", { words: job.request.original_words });
}

function HowItIsRun({ job }: { job: InvestigationJob }) {
  const { agent } = job;
  return (
    <>
      {agent.mode === "MODEL"
        ? t("A model chooses which tool to call next; the final checks are always run by the service.")
        : t("The model was unavailable or its output was rejected, so the service ran its fixed sequence of tools.")}{" "}
      {t("Either way, every number comes from the deterministic engine and every sentence of the report is written by the service.")}<span className="mt-0.5 block text-sm text-ink-muted" data-testid="agent-mode" data-agent-mode={agent.mode}>
        {agent.mode === "MODEL" ? tf("Model: {model}", { model: agent.model_id ?? t("not reported") }) : t("Deterministic fallback")} {t("· tool rounds:")}{" "}
        <span className="tabular">{agent.tool_rounds}</span>
        {agent.note ? ` · ${agent.note}` : ""}
      </span>
    </>
  );
}

/** Stage 4: the real steps of the running or finished job. */
export function InvestigationStage() {
  const { state, actions, derived } = useWorkflow();
  const { timing } = useRuntime();
  const id = derived.latestInvestigationId;
  const investigation = derived.latestInvestigation;
  const { phase, error } = derived.polling;

  if (!id) {
    return (
      <StageFrame stage="investigation" lead={t(LEAD)}>
        <EmptyBlock
          title={t("No investigation has been started")}
          action={
            <LinkButton href={stageHref("purchase")} size="sm">
              {t("Go to Test an idea")}
            </LinkButton>
          }
        >
          <p>{t("Describe a purchase and start the investigation to see its steps here.")}</p>
        </EmptyBlock>
      </StageFrame>
    );
  }

  const isActive = state.activeInvestigationId === id;
  const terminal = investigation ? isTerminalJobStatus(investigation.status) : false;
  const waiting = !terminal && isActive && phase === "polling";
  const deadlineSeconds = Math.round(timing.pollDeadlineMs / 1000);
  const retryRequest = investigation?.resolved_request ?? null;
  // "The same request" is the same purchase on the same portfolio: the one stored with the failed job, whatever
  // customization was applied or reset since. A job stored without a portfolio was checked against the scenario's.
  const scenario = state.portfolio.data?.scenario ?? null;
  const retryPortfolio = customPortfolioOfReport(investigation?.portfolio, scenario?.portfolio ?? null);

  return (
    <StageFrame stage="investigation" lead={t(LEAD)}>
      <Panel
        title={t("Investigation")}
        eyebrow={<span className="font-mono text-[0.8125rem]">{id}</span>}
        aside={investigation ? <JobStatusBadge status={investigation.status} /> : undefined}
        figures={investigation !== null}
      >
        {investigation ? (
          <Facts className="sm:grid-cols-3">
            <Fact label={t("Request")}>
              <span className="tabular">{describeJobRequest(investigation)}</span>
            </Fact>
            <Fact label={t("Checked against")}>{tf("Confirmed policy: version {version}", { version: investigation.policy_version })}</Fact>
            {/* The job's own stored portfolio, whatever its status and whatever is customized now. A job stored without one says nothing. */}
            {investigation.portfolio ? (
              <Fact label={t("Portfolio checked")}>
                <PortfolioUsedLabel
                  portfolio={investigation.portfolio}
                  scenarioPortfolio={scenario?.portfolio ?? null}
                  personaName={scenario?.persona.display_name ?? t("This persona")}
                  testId="job-portfolio-label"
                />
              </Fact>
            ) : null}
            <Fact label={t("Started")}>
              <span className="tabular">{formatDateTime(investigation.created_at)}</span>
            </Fact>
            <Fact label={t("Steps reported")}>
              <span className="tabular" data-testid="step-count">
                {investigation.steps.length}
              </span>
            </Fact>
            <Fact label={t("Last update")}>
              <span className="tabular">{formatTime(investigation.updated_at)}</span>
              <span className="block text-sm text-ink-muted">
                {t("The service stops the job at")} <span className="tabular">{formatTime(investigation.deadline_at)}</span> {t("at the latest.")}</span>
            </Fact>
            <Fact label={t("How it is run")}>
              <HowItIsRun job={investigation} />
            </Fact>
          </Facts>
        ) : (
          <LoadingBlock label={t("Investigation accepted. Waiting for its first status…")} />
        )}
      </Panel>

      {investigation ? (
        <Panel title={t("Steps")} figures description={t("A completed job means the checks ran. It does not mean the rules are respected: read the verdict.")}>
          {investigation.steps.length === 0 && terminal ? (
            <EmptyBlock title={t("The job reported no steps")} />
          ) : (
            <StepTimeline steps={investigation.steps} waiting={waiting} />
          )}
        </Panel>
      ) : null}

      {/* Final states and failures of the poll itself. */}
      {investigation?.status === "SUCCEEDED" ? (
        <Notice
          tone="info"
          role="status"
          title={
            investigation.steps.length === 1
              ? t("The investigation is complete: 1 step reported")
              : tf("The investigation is complete: {count} steps reported", { count: investigation.steps.length })
          }
          action={
            <Button variant="primary" iconAfter={<ArrowRightIcon />} onClick={() => goToStage("verdict")} data-testid="see-verdict">
              {investigation.result ? t("See the verdict and evidence") : t("See what the investigation needs")}
            </Button>
          }
        >
          <p>
            {investigation.result
              ? t("Completion says the checks ran, not how they came out.")
              : t("The request was ambiguous, so nothing was checked: the investigation asks a question instead of guessing.")}
          </p>
        </Notice>
      ) : null}

      {investigation?.status === "FAILED" ? (
        <ErrorBlock
          title={t("The investigation failed")}
          message={investigation.failure?.message ?? t("The job ended without a result and gave no reason.")}
          onRetry={
            // A new investigation needs a policy in force (there is none after a policy version conflict).
            investigation.failure?.retryable !== false && retryRequest && derived.currentPolicy ? () => void actions.startInvestigation(retryRequest, null, retryPortfolio) : undefined
          }
          retryLabel={t("Run the same request again")}
        >
          {investigation.failure?.code ? (
            <p>
              {t("Error code:")} <span className="font-mono text-[0.8125rem]">{investigation.failure.code}</span>
            </p>
          ) : null}
          <p>{t("No verdict was produced, so none is shown. The steps above are the ones that ran before the failure.")}</p>
        </ErrorBlock>
      ) : null}

      {waiting && error ? (
        // A failed status request is retried until the time limit (contracts/api.md section 7), and said while it lasts.
        <Notice tone="caution" role="status" title={t("The latest request for the status failed")}>
          <div data-testid="polling-retrying">
            <p>{error}</p>
            <p>
              {t("It is asked again every")} <span className="tabular">{timing.pollIntervalMs / 1000}</span> {t("seconds until the time limit of")}{" "}
              <span className="tabular">{deadlineSeconds}</span> {t("seconds. The investigation itself may be unaffected.")}</p>
          </div>
        </Notice>
      ) : null}

      {!terminal && isActive && phase === "timed_out" ? (
        <ErrorBlock
          title={tf("No final answer within {seconds} seconds", { seconds: deadlineSeconds })}
          message={
            error
              ? t("No final status was received within the time limit, so checking was stopped. The investigation may still be running.")
              : t("The investigation did not finish within the time limit, so checking was stopped. It may still be running.")
          }
          onRetry={actions.retryPolling}
          retryLabel={t("Keep waiting")}
        >
          {error ? <p data-testid="polling-last-error">{t("The last request for its status failed:")} {error}</p> : null}
          <p>{t("No verdict is shown, because none was received.")}</p>
        </ErrorBlock>
      ) : null}

      {!terminal && isActive && phase === "failed" ? (
        <ErrorBlock
          title={t("The status of the investigation could not be fetched")}
          message={error ?? t("The request for its status failed.")}
          onRetry={actions.retryPolling}
          retryLabel={t("Check again")}
        >
          <p>{t("The investigation itself may be unaffected. No verdict is shown until its status is known.")}</p>
        </ErrorBlock>
      ) : null}

      {state.start.status === "error" ? (
        <ErrorBlock title={t("A new investigation could not be started")} message={state.start.error ?? t("The request failed.")} />
      ) : null}
    </StageFrame>
  );
}
