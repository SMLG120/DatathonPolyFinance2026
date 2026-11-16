"use client";

import { useEffect, useRef, useState } from "react";
import { ChangeRuleForm } from "@/components/challenge/ChangeRuleForm";
import { ClarifyPreferenceForm } from "@/components/challenge/ClarifyPreferenceForm";
import { RuleChangeComparison } from "@/components/challenge/Comparison";
import { CorrectFactForm } from "@/components/challenge/CorrectFactForm";
import { useEvidence } from "@/components/evidence/EvidenceProvider";
import { StageFrame } from "@/components/shell/StageFrame";
import { EmptyBlock, ErrorBlock } from "@/components/ui/AsyncStates";
import { Button, LinkButton } from "@/components/ui/Button";
import { Notice } from "@/components/ui/Notice";
import { Fact, Facts, Panel } from "@/components/ui/Panel";
import { Tabs } from "@/components/ui/Tabs";
import type { ChallengeType } from "@/lib/contracts";
import { portfolioCheckedLabel } from "@/lib/customize";
import { describePurchase } from "@/lib/portfolio";
import { assessResult } from "@/lib/result";
import { verdictHeadline } from "@/lib/verdict";
import { stageHref } from "@/state/stage";
import { useWorkflow } from "@/state/workflow";

const LEAD = "Disagree with a figure, with how your preference was read, or with one of your own rules? Each path keeps the earlier report exactly as it was.";

const TAB_OF: Record<ChallengeType, string> = { CORRECT_FACT: "fact", CLARIFY_PREFERENCE: "preference", CHANGE_RULE: "rule" };

/** Stage 6: three ways to challenge a report, then — in its own section — the old and the new side by side. */
export function ChallengeStage() {
  const { state, actions, derived } = useWorkflow();
  const { challengeEvidenceId } = useEvidence();
  const example = state.portfolio.data?.scenario.demo_challenge ?? null;

  // The tab the user chose stands until a figure is sent here from the evidence drawer: that always opens "Correct a fact".
  const [choice, setChoice] = useState<{ tab: string; forEvidenceId: string | null }>({
    tab: challengeEvidenceId ? "fact" : example ? TAB_OF[example.type] : "fact",
    forEvidenceId: challengeEvidenceId,
  });
  const tab = choice.forEvidenceId === challengeEvidenceId ? choice.tab : "fact";

  // When a rule change produces a comparison, move focus to it: the form that had focus has been reset.
  const comparisonKey = state.comparison?.newerId ?? null;
  const shownComparison = useRef(comparisonKey);
  useEffect(() => {
    if (comparisonKey && shownComparison.current !== comparisonKey) document.getElementById("rule-change-comparison-title")?.focus();
    shownComparison.current = comparisonKey;
  }, [comparisonKey]);

  // The report being read if it has a result, otherwise the newest one that has.
  const job = derived.viewedInvestigation?.result ? derived.viewedInvestigation : derived.latestReport;
  const assessment = job?.result ? assessResult(job.result) : null;

  if (!job || assessment?.kind !== "ok") {
    return (
      <StageFrame stage="challenge" lead={LEAD}>
        <EmptyBlock
          title="There is no report to challenge yet"
          action={
            <LinkButton href={stageHref("purchase")} size="sm">
              Go to Test an idea
            </LinkButton>
          }
        >
          <p>A challenge is made against a report whose checks ran. Run an investigation first.</p>
        </EmptyBlock>
        {state.comparison ? <ComparisonPanel /> : null}
      </StageFrame>
    );
  }

  const result = assessment.result;
  const scenarioPortfolio = state.portfolio.data?.scenario.portfolio ?? null;
  const personaLabel = state.portfolio.data?.scenario.persona.display_name ?? "This persona";
  const policy = derived.policyFor(job);
  const current = derived.currentPolicy;
  const isCurrentPolicy = policy !== null && current !== null && policy.policy_id === current.policy_id && policy.version === current.version;
  const headline = verdictHeadline(result.summary);

  return (
    <StageFrame stage="challenge" lead={LEAD}>
      <Panel title="Report being challenged" tone="sunken" figures>
        <Facts className="sm:grid-cols-3">
          <Fact label="Result">
            <span data-testid="challenged-headline">{headline.title}</span>
          </Fact>
          <Fact label="Request">
            <span className="tabular">{describePurchase(result.purchase_request)}</span>
          </Fact>
          <Fact label="Checked against">
            Confirmed policy: version <span className="tabular">{job.policy_version}</span>
          </Fact>
          {job.portfolio ? (
            <Fact label="Portfolio checked" wide>
              <span data-testid="report-portfolio-label">{portfolioCheckedLabel(job.portfolio, scenarioPortfolio, personaLabel)}</span>
              <span className="block text-sm text-ink-muted">
                Stored with this report. A rule change re-checks this same portfolio, whatever customization is applied now.
              </span>
            </Fact>
          ) : null}
        </Facts>
        <div className="mt-4">
          <LinkButton href={stageHref("verdict")} size="sm">
            Open this report
          </LinkButton>
        </div>
      </Panel>

      <Panel id="challenge-forms" title="What do you want to challenge?" description="Choose one of three paths. Each has its own form.">
        <Tabs
          label="Ways to challenge this report"
          value={tab}
          onValueChange={(next) => {
            actions.clearChallengeError();
            setChoice({ tab: next, forEvidenceId: challengeEvidenceId });
          }}
          items={[
            {
              value: "fact",
              label: "Correct a fact",
              // Remount when a figure is chosen from the evidence drawer, so it arrives preselected.
              content: <CorrectFactForm key={`${job.id}|${challengeEvidenceId ?? "none"}`} job={job} result={result} example={example} />,
            },
            {
              value: "preference",
              label: "Clarify a preference",
              content: <ClarifyPreferenceForm job={job} objectives={policy?.objectives ?? state.objectives} example={example} />,
            },
            {
              value: "rule",
              label: "Change a rule",
              content:
                policy && isCurrentPolicy ? (
                  <ChangeRuleForm key={job.id} job={job} result={result} policy={policy} example={example} />
                ) : (
                  <Notice
                    tone="caution"
                    title={`This report was checked against policy version ${job.policy_version}, which is no longer the one in force`}
                    action={
                      <Button size="sm" onClick={() => actions.viewReport(null)}>
                        Use the latest report instead
                      </Button>
                    }
                  >
                    <p>A rule is changed starting from the version in force{current ? ` (version ${current.version})` : ""}.</p>
                  </Notice>
                ),
            },
          ]}
        />
        {state.challenge.status === "error" ? (
          state.challenge.kind === "no_fixture" ? (
            <Notice tone="info" role="status" title="The test data holds no answer to this challenge" className="mt-5">
              <p data-testid="challenge-not-recorded">{state.challenge.error}</p>
              <p>Nothing was changed: no correction, no rule and no report.</p>
            </Notice>
          ) : (
            <ErrorBlock className="mt-5" title="Your challenge could not be recorded" message={state.challenge.error ?? "The request failed."}>
              <p>Nothing was changed: no correction, no rule and no report.</p>
            </ErrorBlock>
          )
        ) : null}
      </Panel>

      {state.comparison ? <ComparisonPanel /> : null}
    </StageFrame>
  );
}

/**
 * The outcome of a rule change, as its own section: a rule above it, its own
 * heading and a heavier outline, so it is not read as part of the form.
 */
function ComparisonPanel() {
  return (
    <div className="border-t-2 border-line-strong pt-6" data-testid="comparison-section">
      <Panel
        id="rule-change-comparison"
        focusableHeading
        className="border-2 border-accent"
        eyebrow="Outcome of the rule change: separate from the form above"
        title="Version comparison: before and after the rule change"
        description="The earlier report was not edited. It still says what it said under the earlier policy version."
      >
        <RuleChangeComparison />
      </Panel>
    </div>
  );
}
