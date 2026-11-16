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

const LEAD = "Each step below is one the investigation actually completed. Steps appear as the job reports them; nothing is scripted in advance.";

/** The request a job was asked to check: the structured one once resolved, else the user's words. */
export function describeJobRequest(job: InvestigationJob): string {
  if (job.resolved_request) return describePurchase(job.resolved_request);
  if (job.request.instrument_id !== null && job.request.target_direct_weight !== null) return describePurchase(job.request);
  return `“${job.request.original_words}” (free text, not resolved into a request yet)`;
}

function HowItIsRun({ job }: { job: InvestigationJob }) {
  const { agent } = job;
  return (
    <>
      {agent.mode === "MODEL"
        ? "A model chooses which tool to call next; the final checks are always run by the service."
        : "The model was unavailable or its output was rejected, so the service ran its fixed sequence of tools."}{" "}
      Either way, every number comes from the deterministic engine and every sentence of the report is written by the service.
      <span className="mt-0.5 block text-sm text-ink-muted" data-testid="agent-mode" data-agent-mode={agent.mode}>
        {agent.mode === "MODEL" ? `Model: ${agent.model_id ?? "not reported"}` : "Deterministic fallback"} · tool rounds:{" "}
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
      <StageFrame stage="investigation" lead={LEAD}>
        <EmptyBlock
          title="No investigation has been started"
          action={
            <LinkButton href={stageHref("purchase")} size="sm">
              Go to Proposed purchase
            </LinkButton>
          }
        >
          <p>Describe a purchase and start the investigation to see its steps here.</p>
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
    <StageFrame stage="investigation" lead={LEAD}>
      <Panel
        title="Investigation"
        eyebrow={<span className="font-mono text-[0.8125rem]">{id}</span>}
        aside={investigation ? <JobStatusBadge status={investigation.status} /> : undefined}
        figures={investigation !== null}
      >
        {investigation ? (
          <Facts className="sm:grid-cols-3">
            <Fact label="Request">
              <span className="tabular">{describeJobRequest(investigation)}</span>
            </Fact>
            <Fact label="Checked against">Confirmed policy: version {investigation.policy_version}</Fact>
            {/* The job's own stored portfolio, whatever its status and whatever is customized now. A job stored without one says nothing. */}
            {investigation.portfolio ? (
              <Fact label="Portfolio checked">
                <PortfolioUsedLabel
                  portfolio={investigation.portfolio}
                  scenarioPortfolio={scenario?.portfolio ?? null}
                  personaName={scenario?.persona.display_name ?? "This persona"}
                  testId="job-portfolio-label"
                />
              </Fact>
            ) : null}
            <Fact label="Started">
              <span className="tabular">{formatDateTime(investigation.created_at)}</span>
            </Fact>
            <Fact label="Steps reported">
              <span className="tabular" data-testid="step-count">
                {investigation.steps.length}
              </span>
            </Fact>
            <Fact label="Last update">
              <span className="tabular">{formatTime(investigation.updated_at)}</span>
              <span className="block text-sm text-ink-muted">
                The service stops the job at <span className="tabular">{formatTime(investigation.deadline_at)}</span> at the latest.
              </span>
            </Fact>
            <Fact label="How it is run">
              <HowItIsRun job={investigation} />
            </Fact>
          </Facts>
        ) : (
          <LoadingBlock label="Investigation accepted. Waiting for its first status…" />
        )}
      </Panel>

      {investigation ? (
        <Panel title="Steps" figures description="A completed job means the checks ran. It does not mean the rules are respected: read the verdict.">
          {investigation.steps.length === 0 && terminal ? (
            <EmptyBlock title="The job reported no steps" />
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
          title={`The investigation is complete: ${investigation.steps.length} ${investigation.steps.length === 1 ? "step" : "steps"} reported`}
          action={
            <Button variant="primary" iconAfter={<ArrowRightIcon />} onClick={() => goToStage("verdict")} data-testid="see-verdict">
              {investigation.result ? "See the verdict and evidence" : "See what the investigation needs"}
            </Button>
          }
        >
          <p>
            {investigation.result
              ? "Completion says the checks ran, not how they came out."
              : "The request was ambiguous, so nothing was checked: the investigation asks a question instead of guessing."}
          </p>
        </Notice>
      ) : null}

      {investigation?.status === "FAILED" ? (
        <ErrorBlock
          title="The investigation failed"
          message={investigation.failure?.message ?? "The job ended without a result and gave no reason."}
          onRetry={
            // A new investigation needs a policy in force (there is none after a policy version conflict).
            investigation.failure?.retryable !== false && retryRequest && derived.currentPolicy ? () => void actions.startInvestigation(retryRequest, null, retryPortfolio) : undefined
          }
          retryLabel="Run the same request again"
        >
          {investigation.failure?.code ? (
            <p>
              Error code: <span className="font-mono text-[0.8125rem]">{investigation.failure.code}</span>
            </p>
          ) : null}
          <p>No verdict was produced, so none is shown. The steps above are the ones that ran before the failure.</p>
        </ErrorBlock>
      ) : null}

      {waiting && error ? (
        // A failed status request is retried until the time limit (contracts/api.md section 7), and said while it lasts.
        <Notice tone="caution" role="status" title="The latest request for the status failed">
          <div data-testid="polling-retrying">
            <p>{error}</p>
            <p>
              It is asked again every <span className="tabular">{timing.pollIntervalMs / 1000}</span> seconds until the time limit of{" "}
              <span className="tabular">{deadlineSeconds}</span> seconds. The investigation itself may be unaffected.
            </p>
          </div>
        </Notice>
      ) : null}

      {!terminal && isActive && phase === "timed_out" ? (
        <ErrorBlock
          title={`No final answer within ${deadlineSeconds} seconds`}
          message={
            error
              ? "No final status was received within the time limit, so checking was stopped. The investigation may still be running."
              : "The investigation did not finish within the time limit, so checking was stopped. It may still be running."
          }
          onRetry={actions.retryPolling}
          retryLabel="Keep waiting"
        >
          {error ? <p data-testid="polling-last-error">The last request for its status failed: {error}</p> : null}
          <p>No verdict is shown, because none was received.</p>
        </ErrorBlock>
      ) : null}

      {!terminal && isActive && phase === "failed" ? (
        <ErrorBlock
          title="The status of the investigation could not be fetched"
          message={error ?? "The request for its status failed."}
          onRetry={actions.retryPolling}
          retryLabel="Check again"
        >
          <p>The investigation itself may be unaffected. No verdict is shown until its status is known.</p>
        </ErrorBlock>
      ) : null}

      {state.start.status === "error" ? (
        <ErrorBlock title="A new investigation could not be started" message={state.start.error ?? "The request failed."} />
      ) : null}
    </StageFrame>
  );
}
