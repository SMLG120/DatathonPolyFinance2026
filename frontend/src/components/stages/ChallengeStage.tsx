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
import { describePurchase } from "@/lib/portfolio";
import { countResult, verdictHeadline } from "@/lib/verdict";
import { stageHref } from "@/state/stage";
import { useWorkflow } from "@/state/workflow";

const LEAD = "Disagree with a figure, with how your preference was read, or with one of your own rules? Each path keeps the earlier report exactly as it was.";

/** Stage 6: three ways to challenge a report, then the old and the new side by side. */
export function ChallengeStage() {
  const { state, actions, derived } = useWorkflow();
  const { challengeEvidenceId } = useEvidence();
  const [tab, setTab] = useState("fact");

  // When a rule change produces a comparison, move focus to it: the form that had focus has been reset.
  const comparisonKey = state.comparison?.newerId ?? null;
  const shownComparison = useRef(comparisonKey);
  useEffect(() => {
    if (comparisonKey && shownComparison.current !== comparisonKey) document.getElementById("rule-change-comparison-title")?.focus();
    shownComparison.current = comparisonKey;
  }, [comparisonKey]);

  // The report being read if it has a result, otherwise the newest one that has.
  const target = derived.viewedInvestigation?.result ? derived.viewedInvestigation : derived.latestReport;
  const result = target?.result ?? null;

  if (!target || !result) {
    return (
      <StageFrame stage="challenge" lead={LEAD}>
        <EmptyBlock
          title="There is no report to challenge yet"
          action={
            <LinkButton href={stageHref("purchase")} size="sm">
              Go to Proposed purchase
            </LinkButton>
          }
        >
          <p>A challenge is made against a report. Run an investigation first.</p>
        </EmptyBlock>
      </StageFrame>
    );
  }

  const policy = derived.policyByVersion(target.policy_version);
  const current = derived.currentPolicy;
  const isCurrentPolicy = policy !== null && current !== null && policy.policy_version === current.policy_version;
  const headline = verdictHeadline(countResult(result));

  return (
    <StageFrame stage="challenge" lead={LEAD}>
      <Panel title="Report being challenged" tone="sunken">
        <Facts className="sm:grid-cols-3">
          <Fact label="Result">{headline.title}</Fact>
          <Fact label="Request">
            <span className="tabular">{result.purchase ? describePurchase(result.purchase) : "No purchase — the portfolio as it is"}</span>
          </Fact>
          <Fact label="Checked against">Confirmed policy — version {target.policy_version}</Fact>
        </Facts>
        <div className="mt-4">
          <LinkButton href={stageHref("verdict")} size="sm">
            Open this report
          </LinkButton>
        </div>
      </Panel>

      <Panel title="What do you want to challenge?">
        <Tabs
          label="Ways to challenge this report"
          value={tab}
          onValueChange={(next) => {
            actions.clearChallengeError();
            setTab(next);
          }}
          items={[
            {
              value: "fact",
              label: "Correct a fact",
              // Remount when a figure is chosen from the evidence drawer, so it arrives preselected.
              content: <CorrectFactForm key={challengeEvidenceId ?? "none"} investigation={target} result={result} />,
            },
            { value: "preference", label: "Clarify a preference", content: <ClarifyPreferenceForm investigation={target} /> },
            {
              value: "rule",
              label: "Change a rule",
              content:
                policy && isCurrentPolicy ? (
                  <ChangeRuleForm key={target.investigation_id} investigation={target} result={result} policy={policy} />
                ) : (
                  <Notice
                    tone="caution"
                    title={`This report was checked against policy version ${target.policy_version}, which is no longer the one in force`}
                    action={
                      <Button size="sm" onClick={() => actions.viewReport(null)}>
                        Use the latest report instead
                      </Button>
                    }
                  >
                    <p>A rule is changed starting from the version in force{current ? ` (version ${current.policy_version})` : ""}.</p>
                  </Notice>
                ),
            },
          ]}
        />
        {state.challenge.status === "error" ? (
          <ErrorBlock className="mt-5" title="Your challenge could not be recorded" message={state.challenge.error ?? "The request failed."}>
            <p>Nothing was changed: no correction, no rule and no report.</p>
          </ErrorBlock>
        ) : null}
      </Panel>

      {state.comparison ? (
        <Panel
          id="rule-change-comparison"
          focusableHeading
          title="Before and after your rule change"
          description="The earlier report was not edited. It still says what it said under the earlier policy version."
        >
          <RuleChangeComparison />
        </Panel>
      ) : null}
    </StageFrame>
  );
}
