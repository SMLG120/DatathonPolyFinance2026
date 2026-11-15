"use client";

import { useId, useRef, useState } from "react";
import { ClarificationCard } from "@/components/rules/ClarificationCard";
import { PolicyRuleCard, ProposedRuleCard } from "@/components/rules/RuleCard";
import { StageFrame } from "@/components/shell/StageFrame";
import { EmptyBlock, ErrorBlock, LoadingBlock } from "@/components/ui/AsyncStates";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { describedBy, Field, TextArea } from "@/components/ui/Field";
import { CheckIcon } from "@/components/ui/icons";
import { Notice } from "@/components/ui/Notice";
import { Fact, Facts, Panel } from "@/components/ui/Panel";
import type { Objective, Policy } from "@/lib/contracts";
import { formatDateTime, percentInputToFraction } from "@/lib/format";
import { originLabel, ruleSummary, validateThreshold } from "@/lib/rules";
import { activeRules } from "@/lib/verdict";
import { useWorkflow } from "@/state/workflow";

function ObjectiveList({ objectives }: { objectives: Objective[] }) {
  return (
    <ul className="space-y-3">
      {objectives.map((objective) => (
        <li key={objective.objective_id} className="rounded-md border border-line bg-canvas p-3" data-testid="objective">
          <blockquote className="text-ink">&ldquo;{objective.original_words}&rdquo;</blockquote>
          <p className="mt-1 text-sm text-ink-muted">{originLabel(objective.origin)} · recorded word for word · not scored</p>
        </li>
      ))}
    </ul>
  );
}

function PolicyPanel({ policy, earlier }: { policy: Policy | null; earlier: Policy[] }) {
  if (!policy) {
    return (
      <Panel id="confirmed-policy" title="Confirmed policy" focusableHeading>
        <EmptyBlock title="No confirmed rule yet">
          <p>Checks use confirmed rules only. A proposed rule stays inactive until you confirm it with a threshold.</p>
        </EmptyBlock>
      </Panel>
    );
  }
  const active = activeRules(policy);
  const superseded = policy.rules.filter((rule) => rule.status === "SUPERSEDED");
  const objectiveOf = (id: string | null) => policy.objectives.find((o) => o.objective_id === id);
  return (
    <Panel
      id="confirmed-policy"
      focusableHeading
      title={`Confirmed policy — version ${policy.policy_version}`}
      eyebrow="In force"
      aside={
        <Badge tone="accent" icon={<CheckIcon size={16} />}>
          {active.length} active {active.length === 1 ? "rule" : "rules"}
        </Badge>
      }
      description="A policy version never changes. Confirming or changing a rule creates the next version, and earlier reports keep the version they were checked against."
    >
      <div className="space-y-5">
        <Facts className="sm:grid-cols-3">
          <Fact label="Version">
            <span className="tabular">{policy.policy_version}</span>
          </Fact>
          <Fact label="Created">
            <span className="tabular">{formatDateTime(policy.created_at)}</span>
          </Fact>
          <Fact label="Replaces">{policy.previous_version === null ? "Nothing — first version" : `Version ${policy.previous_version}`}</Fact>
        </Facts>
        <ul className="space-y-4">
          {active.map((rule) => (
            <PolicyRuleCard key={rule.rule_id} rule={rule} objective={objectiveOf(rule.objective_id)} />
          ))}
        </ul>
        {superseded.length > 0 ? (
          <details className="rounded-md border border-line bg-canvas p-3">
            <summary className="min-h-6 cursor-pointer font-semibold text-ink">
              Superseded rules ({superseded.length}) — kept for the record, not checked
            </summary>
            <ul className="mt-3 space-y-4">
              {superseded.map((rule) => (
                <PolicyRuleCard key={rule.rule_id} rule={rule} objective={objectiveOf(rule.objective_id)} />
              ))}
            </ul>
          </details>
        ) : null}
        {earlier.length > 0 ? (
          <details className="rounded-md border border-line bg-canvas p-3" data-testid="earlier-versions">
            <summary className="min-h-6 cursor-pointer font-semibold text-ink">Earlier versions ({earlier.length})</summary>
            <ul className="mt-3 space-y-3">
              {earlier
                .slice()
                .reverse()
                .map((version) => (
                  <li key={version.policy_version}>
                    <p className="font-semibold text-ink">
                      Version <span className="tabular">{version.policy_version}</span>{" "}
                      <span className="font-normal text-ink-muted">
                        · created <span className="tabular">{formatDateTime(version.created_at)}</span>
                      </span>
                    </p>
                    <ul className="list-disc pl-5 text-ink">
                      {activeRules(version).map((rule) => (
                        <li key={rule.rule_id} className="tabular">
                          {ruleSummary(rule)}
                        </li>
                      ))}
                    </ul>
                  </li>
                ))}
            </ul>
          </details>
        ) : null}
      </div>
    </Panel>
  );
}

/** Stage 2: goal text → proposed rules → explicit confirmation. */
export function GoalsStage() {
  const { state, actions, derived } = useWorkflow();
  const goalId = useId();
  const goalRef = useRef<HTMLTextAreaElement>(null);
  const [goalError, setGoalError] = useState<string | null>(null);
  const [confirmAllNote, setConfirmAllNote] = useState<string | null>(null);

  const interpreting = state.interpret.status === "loading";
  const confirming = state.confirm.status === "loading";
  const policy = derived.currentPolicy;
  const objectiveOf = (id: string | null) => state.objectives.find((o) => o.objective_id === id);

  const confirmable = state.proposedRules.filter((rule) => {
    const threshold = percentInputToFraction(state.thresholdText[rule.rule_id] ?? "");
    return threshold !== null && validateThreshold(threshold) === null;
  });

  async function confirm(ruleIds: string[]) {
    setConfirmAllNote(null);
    const confirmed = await actions.confirmRules(ruleIds);
    // The card that held focus is gone: move to the policy it became part of.
    if (confirmed) document.getElementById("confirmed-policy-title")?.focus();
  }

  function propose() {
    if (state.goalText.trim() === "") {
      setGoalError("Write what you want in a sentence first.");
      goalRef.current?.focus();
      return;
    }
    setGoalError(null);
    void actions.interpretGoal();
  }

  return (
    <StageFrame
      stage="goals"
      lead="Say what you want in your own words. The system proposes rules from them. A rule counts only after you confirm it, with a number you chose."
      continueNote={policy ? null : "You can continue, but a purchase can only be checked once at least one rule is confirmed."}
    >
      <Panel title="Your goal">
        <div className="space-y-4">
          <Field
            htmlFor={goalId}
            label="What do you want from this portfolio?"
            hint="Starts with the objective from the fictional scenario. Edit it or replace it with your own words."
            error={goalError}
          >
            <TextArea
              id={goalId}
              ref={goalRef}
              rows={3}
              value={state.goalText}
              onChange={(event) => {
                actions.setGoalText(event.target.value);
                if (goalError) setGoalError(null);
              }}
              aria-invalid={goalError ? true : undefined}
              aria-describedby={describedBy(goalId, { hint: true, error: Boolean(goalError) })}
            />
          </Field>
          <Button
            variant={state.hasInterpretation ? "secondary" : "primary"}
            softDisabled={state.goalText.trim() === ""}
            busy={interpreting}
            busyLabel="Reading your text…"
            onClick={propose}
            data-testid="propose-rules"
          >
            {state.hasInterpretation ? "Propose rules again from this text" : "Propose rules from this text"}
          </Button>
          {state.portfolio.status !== "ready" ? (
            <Notice tone="caution" title="No portfolio is loaded">
              <p>Rules can be written now, but previews need the portfolio from stage 1.</p>
            </Notice>
          ) : null}
        </div>
      </Panel>

      {interpreting && !state.hasInterpretation ? <LoadingBlock label="Reading your text and preparing proposed rules…" /> : null}
      {state.interpret.status === "error" ? (
        <ErrorBlock title="Your text could not be read" message={state.interpret.error ?? "The request failed."} onRetry={propose}>
          <p>No rule was created or changed.</p>
        </ErrorBlock>
      ) : null}

      {state.hasInterpretation ? (
        <>
          <Panel
            title="Objectives"
            eyebrow="Context, not rules"
            description="An objective is kept in your words to give results their context. It is never marked pass or fail, and it never implies a number."
          >
            {state.objectives.length > 0 ? (
              <ObjectiveList objectives={state.objectives} />
            ) : (
              <EmptyBlock title="No objective was recorded">
                <p>Nothing in the text was read as a qualitative objective.</p>
              </EmptyBlock>
            )}
          </Panel>

          {state.clarifications.length > 0 ? (
            <Panel
              title="Questions before a rule can be written"
              description="Some wording has more than one meaning. No rule is written from it until you choose a definition."
            >
              <ul className="space-y-4">
                {state.clarifications.map((clarification) => (
                  <ClarificationCard
                    key={clarification.clarification_id}
                    clarification={clarification}
                    busy={interpreting}
                    onAnswer={(optionId) => void actions.interpretGoal({ clarification_id: clarification.clarification_id, option_id: optionId })}
                  />
                ))}
              </ul>
            </Panel>
          ) : null}

          <Panel
            title="Proposed rules"
            eyebrow="Inactive until confirmed"
            aside={
              <Badge tone="neutral" dashed>
                {state.proposedRules.length} proposed
              </Badge>
            }
          >
            {state.proposedRules.length > 0 ? (
              <div className="space-y-5">
                <ul className="space-y-4">
                  {state.proposedRules.map((rule) => (
                    <ProposedRuleCard
                      key={rule.rule_id}
                      rule={rule}
                      objective={objectiveOf(rule.objective_id)}
                      personaId={state.personaId}
                      thresholdText={state.thresholdText[rule.rule_id] ?? ""}
                      onThresholdChange={(text) => actions.setThresholdText(rule.rule_id, text)}
                      onConfirm={() => void confirm([rule.rule_id])}
                      confirming={confirming && state.confirm.ruleIds.includes(rule.rule_id)}
                    />
                  ))}
                </ul>
                {state.proposedRules.length > 1 ? (
                  <div className="space-y-2 border-t border-line pt-4">
                    <Button
                      variant="primary"
                      softDisabled={confirmable.length === 0}
                      busy={confirming}
                      busyLabel="Confirming…"
                      icon={<CheckIcon />}
                      data-testid="confirm-all"
                      onClick={() => {
                        if (confirmable.length === 0) {
                          setConfirmAllNote("No proposed rule has a valid threshold yet. Enter a number in a rule above first.");
                          return;
                        }
                        void confirm(confirmable.map((rule) => rule.rule_id));
                      }}
                    >
                      Confirm {confirmable.length === state.proposedRules.length ? "all" : "the"} {confirmable.length}{" "}
                      {confirmable.length === 1 ? "rule" : "rules"} that {confirmable.length === 1 ? "has" : "have"} a threshold
                    </Button>
                    <p className="text-sm text-ink-muted">Confirms them together in one new policy version. Rules without a threshold stay proposed.</p>
                    {confirmAllNote ? (
                      <p role="alert" className="text-sm font-semibold text-fail">
                        {confirmAllNote}
                      </p>
                    ) : null}
                  </div>
                ) : null}
              </div>
            ) : (
              <EmptyBlock title={policy ? "No rule is waiting for confirmation" : "No rule was proposed from this text"}>
                <p>
                  {state.clarifications.length > 0
                    ? "Answer the question above to get a proposed rule."
                    : policy
                      ? "Everything proposed so far has been confirmed."
                      : "Try wording that names a limit, for example a maximum share in one company."}
                </p>
              </EmptyBlock>
            )}
            {state.confirm.status === "error" ? (
              <ErrorBlock
                className="mt-4"
                title="The rules could not be confirmed"
                message={state.confirm.error ?? "The request failed."}
                onRetry={() => void confirm(state.confirm.ruleIds)}
              >
                <p>They are still proposed and inactive. The confirmed policy is unchanged.</p>
              </ErrorBlock>
            ) : null}
          </Panel>

          {state.unsupported.length > 0 || state.notes.length > 0 ? (
            <Panel title="Not turned into a rule" description="Shown so that nothing you wrote is silently dropped.">
              <ul className="space-y-3">
                {state.unsupported.map((item) => (
                  <li key={item.original_words} className="rounded-md border border-dashed border-line-strong bg-canvas p-3" data-testid="unsupported-request">
                    <blockquote className="text-ink">&ldquo;{item.original_words}&rdquo;</blockquote>
                    <p className="mt-1 text-sm text-ink-muted">{item.reason}</p>
                  </li>
                ))}
                {state.notes.map((note) => (
                  <li key={note} className="text-ink-muted">
                    {note}
                  </li>
                ))}
              </ul>
            </Panel>
          ) : null}
        </>
      ) : null}

      <PolicyPanel policy={policy} earlier={state.policies.slice(0, -1)} />
    </StageFrame>
  );
}
