"use client";

import { StageFrame } from "@/components/shell/StageFrame";
import { StepTimeline } from "@/components/timeline/StepTimeline";
import { EmptyBlock, ErrorBlock, LoadingBlock } from "@/components/ui/AsyncStates";
import { JobStatusBadge } from "@/components/ui/Badge";
import { Button, LinkButton } from "@/components/ui/Button";
import { ArrowRightIcon } from "@/components/ui/icons";
import { Notice } from "@/components/ui/Notice";
import { Fact, Facts, Panel } from "@/components/ui/Panel";
import { formatDateTime, formatTime } from "@/lib/format";
import { describePurchase } from "@/lib/portfolio";
import { isTerminalJobStatus } from "@/lib/verdict";
import { useRuntime } from "@/state/runtime";
import { goToStage, stageHref } from "@/state/stage";
import { useWorkflow } from "@/state/workflow";

const LEAD = "Each step below is one the investigation actually completed. Steps appear as the job reports them; nothing is scripted in advance.";

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

  return (
    <StageFrame stage="investigation" lead={LEAD}>
      <Panel
        title="Investigation"
        eyebrow={<span className="font-mono text-[0.8125rem]">{id}</span>}
        aside={investigation ? <JobStatusBadge status={investigation.status} /> : undefined}
      >
        {investigation ? (
          <Facts className="sm:grid-cols-3">
            <Fact label="Request">
              <span className="tabular">{describePurchase(investigation.purchase)}</span>
            </Fact>
            <Fact label="Checked against">Confirmed policy — version {investigation.policy_version}</Fact>
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
            </Fact>
            <Fact label="How it is run">
              {investigation.agent
                ? investigation.agent.mode === "MODEL"
                  ? "A model chooses which tool to call next; every number comes from the deterministic engine."
                  : "A fixed sequence of tools run by the server; no model is involved."
                : "Not reported yet"}
              {investigation.agent?.note ? <span className="block text-sm text-ink-muted">{investigation.agent.note}</span> : null}
            </Fact>
          </Facts>
        ) : (
          <LoadingBlock label="Investigation accepted. Waiting for its first status…" />
        )}
      </Panel>

      {investigation ? (
        <Panel title="Steps" description="A completed job means the checks ran. It does not mean the rules are respected: read the verdict.">
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
              See the verdict and evidence
            </Button>
          }
        >
          <p>Completion says the checks ran, not how they came out.</p>
        </Notice>
      ) : null}

      {investigation?.status === "FAILED" ? (
        <ErrorBlock
          title="The investigation failed"
          message={investigation.error?.message ?? "The job ended without a result and gave no reason."}
          onRetry={() => void actions.startInvestigation(investigation.purchase)}
          retryLabel="Run the same request again"
        >
          {investigation.error?.code ? (
            <p>
              Error code: <span className="font-mono text-[0.8125rem]">{investigation.error.code}</span>
            </p>
          ) : null}
          <p>No verdict was produced, so none is shown. The steps above are the ones that completed before the failure.</p>
        </ErrorBlock>
      ) : null}

      {!terminal && isActive && phase === "timed_out" ? (
        <ErrorBlock
          title={`No final answer within ${deadlineSeconds} seconds`}
          message="The investigation did not finish within the time limit, so checking was stopped. It may still be running."
          onRetry={actions.retryPolling}
          retryLabel="Keep waiting"
        >
          <p>No verdict is shown, because none was received.</p>
        </ErrorBlock>
      ) : null}

      {!terminal && isActive && phase === "failed" ? (
        <ErrorBlock
          title="The status of the investigation could not be fetched"
          message={error ?? "Several requests in a row failed."}
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
