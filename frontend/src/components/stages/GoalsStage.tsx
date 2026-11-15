"use client";

import { useId, useRef, useState } from "react";
import { ClarificationCard } from "@/components/rules/ClarificationCard";
import { DraftOutcome, OptionOutcome, ruleName } from "@/components/rules/DraftOutcome";
import { PolicyRuleCard, ProposedRuleCard, thresholdProblem } from "@/components/rules/RuleCard";
import { StageFrame } from "@/components/shell/StageFrame";
import { EmptyBlock, ErrorBlock, LoadingBlock } from "@/components/ui/AsyncStates";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { describedBy, Field, TextArea } from "@/components/ui/Field";
import { CheckIcon } from "@/components/ui/icons";
import { Notice } from "@/components/ui/Notice";
import { Fact, Facts, Panel } from "@/components/ui/Panel";
import type { Objective, Policy, Rule } from "@/lib/contracts";
import { formatDateTime, percentInputToFraction } from "@/lib/format";
import { draftRule, previewRuleSet, ruleSummary, validateThreshold } from "@/lib/rules";
import { activeRules } from "@/lib/verdict";
import { usePurchaseForm } from "@/state/purchase";
import { useWorkflow } from "@/state/workflow";

const OBJECTIVE_SOURCE: Record<Objective["source"], string> = {
  USER_STATED: "Stated by you",
  FICTIONAL_SCENARIO: "From the fictional scenario",
};

const OBJECTIVE_KIND: Record<Objective["kind"], string> = {
  goal: "goal",
  preference: "preference",
  constraint: "constraint",
};

function ObjectiveList({ objectives }: { objectives: Objective[] }) {
  return (
    <ul className="space-y-3">
      {objectives.map((objective) => (
        <li key={objective.objective_id} className="rounded-md border border-line bg-canvas p-3" data-testid="objective">
          <blockquote className="text-ink">&ldquo;{objective.original_words}&rdquo;</blockquote>
          <p className="mt-1 text-sm text-ink-muted">
            {OBJECTIVE_SOURCE[objective.source]} · {OBJECTIVE_KIND[objective.kind]} · recorded word for word · not scored
            {objective.case_reference ? ` · ${objective.case_reference}` : ""}
          </p>
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
  const objectiveOf = (id: string | null) => policy.objectives.find((objective) => objective.objective_id === id);
  return (
    <Panel
      id="confirmed-policy"
      focusableHeading
      figures
      title={`Confirmed policy — version ${policy.version}`}
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
            <span className="tabular">{policy.version}</span>
          </Fact>
          <Fact label="Created">
            <span className="tabular">{formatDateTime(policy.created_at)}</span>
          </Fact>
          <Fact label="Replaces">{policy.parent_version === null ? "Nothing — first version" : `Version ${policy.parent_version}`}</Fact>
          <Fact label="Change note" wide>
            {policy.change_note}
          </Fact>
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
                  <li key={version.version}>
                    <p className="font-semibold text-ink">
                      Version <span className="tabular">{version.version}</span>{" "}
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

/** Stage 2: objective → proposed rules → explicit confirmation. */
export function GoalsStage() {
  const { state, actions, derived } = useWorkflow();
  const goalId = useId();
  const goalRef = useRef<HTMLTextAreaElement>(null);
  const thresholdRefs = useRef(new Map<string, HTMLInputElement>());
  const [goalError, setGoalError] = useState<string | null>(null);
  const [attempted, setAttempted] = useState(false);

  const policy = derived.currentPolicy;
  const scenario = state.portfolio.data?.scenario ?? null;
  const purchase = usePurchaseForm().request;
  const interpreting = state.interpret.status === "loading";
  const confirming = state.confirm.status === "loading";
  const scenarioSentence = scenario?.demo_phrases[0]?.original_words ?? null;
  const objectiveOf = (id: string | null) => state.objectives.find((objective) => objective.objective_id === id);

  const numberOf = (rule: Rule): number | null => {
    const value = percentInputToFraction(state.thresholdText[rule.rule_id] ?? "");
    return value !== null && validateThreshold(value) === null ? value : null;
  };
  const confirmable = state.proposedRules.filter((rule) => numberOf(rule) !== null);
  const leftOut = state.proposedRules.length - confirmable.length;

  /** The rules a preview evaluates when one proposed rule carries a draft number: the rules in force, with every proposed rule that has a number standing in as a draft. */
  const previewRulesFor = (editedId: string) => (threshold: number) =>
    previewRuleSet(
      policy?.rules ?? [],
      state.proposedRules.flatMap((rule) => {
        const value = rule.rule_id === editedId ? threshold : numberOf(rule);
        return value === null ? [] : [draftRule(rule, value)];
      }),
    );

  async function confirmAll() {
    if (confirmable.length === 0) {
      // Explain instead of doing nothing: the button stays reachable.
      setAttempted(true);
      const first = state.proposedRules.find((rule) => thresholdProblem(state.thresholdText[rule.rule_id] ?? "") !== null);
      if (first) thresholdRefs.current.get(first.rule_id)?.focus();
      return;
    }
    const confirmed = await actions.confirmRules(confirmable.map((rule) => rule.rule_id));
    // The cards that held focus are gone: move to the policy they became part of.
    if (confirmed) {
      setAttempted(false);
      document.getElementById("confirmed-policy-title")?.focus();
    }
  }

  function interpret() {
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
      lead="A rule counts only after you confirm it, with a number you can see. Until then it is a proposal and nothing checks it."
      continueNote={policy ? null : "You can continue, but a purchase can only be checked once at least one rule is confirmed."}
    >
      <Panel
        title="Objective"
        eyebrow="Context, not rules"
        description="An objective is kept word for word to give results their context. It is never marked pass or fail, and it never implies a number."
      >
        {state.portfolio.status !== "ready" ? (
          <Notice tone="caution" title="No portfolio is loaded">
            <p>The objective and the offered rules come with the persona. Load one in stage 1.</p>
          </Notice>
        ) : state.objectives.length > 0 ? (
          <ObjectiveList objectives={state.objectives} />
        ) : (
          <EmptyBlock title="No objective is recorded">
            <p>The scenario carries no objective for this persona.</p>
          </EmptyBlock>
        )}
      </Panel>

      <Panel
        title="Rules in your own words"
        eyebrow="Optional"
        description="Write a limit or an exclusion in a sentence. The service drafts the kind of rule from it and asks when a word has more than one meaning. It never invents a number."
      >
        <div className="space-y-4">
          <Field htmlFor={goalId} label="What should the portfolio respect?" hint="For example a maximum share in one company, or holdings to avoid." error={goalError}>
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
          <div className="flex flex-wrap items-center gap-3">
            <Button softDisabled={state.goalText.trim() === ""} busy={interpreting} busyLabel="Reading your words…" onClick={interpret} data-testid="interpret-words">
              {state.interpretation ? "Interpret these words again" : "Interpret these words"}
            </Button>
            {scenarioSentence ? (
              <Button
                variant="quiet"
                onClick={() => {
                  actions.setGoalText(scenarioSentence);
                  setGoalError(null);
                  goalRef.current?.focus();
                }}
                data-testid="use-scenario-sentence"
              >
                Use the scenario&rsquo;s sentence
              </Button>
            ) : null}
          </div>

          {interpreting && !state.interpretation ? <LoadingBlock label="Reading your words and drafting rules…" /> : null}
          {state.interpret.status === "error" ? (
            state.interpret.kind === "no_fixture" ? (
              <Notice tone="info" role="status" title="The test data holds no interpretation of these words">
                <p data-testid="interpret-not-recorded">{state.interpret.error}</p>
              </Notice>
            ) : (
              <ErrorBlock title="Your words could not be read" message={state.interpret.error ?? "The request failed."} onRetry={interpret}>
                <p>No rule was created or changed. The rules offered below can still be confirmed by hand.</p>
              </ErrorBlock>
            )
          ) : null}

          {state.interpretation ? (
            <div className="space-y-4 border-t border-line pt-4" data-testid="interpretation">
              <p className="text-ink">
                <span className="font-semibold">Draft read from:</span> &ldquo;{state.interpretation.original_words}&rdquo;{" "}
                <span className="text-sm text-ink-muted">Nothing in a draft is active, and no stored rule was changed.</span>
              </p>

              {state.interpretation.clarifications.length > 0 ? (
                <ul className="space-y-4">
                  {state.interpretation.clarifications.map((clarification) => {
                    const chosen = state.chosenOptions[clarification.clarification_id] ?? null;
                    return (
                      <ClarificationCard
                        key={clarification.clarification_id}
                        clarification={clarification}
                        chosenOptionId={chosen}
                        onChoose={(optionId) => actions.chooseOption(clarification.clarification_id, optionId)}
                        outcome={<OptionOutcome option={clarification.options.find((option) => option.option_id === chosen)} />}
                      />
                    );
                  })}
                </ul>
              ) : null}

              {state.interpretation.proposed_rules.length > 0 ? (
                <div>
                  <p className="font-semibold text-ink">Rules drafted from your words</p>
                  <ul className="mt-1 space-y-2">
                    {state.interpretation.proposed_rules.map((draft) => (
                      <li key={draft.rule_id} className="rounded-md border border-line bg-canvas p-3" data-testid="drafted-rule">
                        <span className="block text-ink">
                          {ruleName(draft)} <span className="text-sm text-ink-muted">· from &ldquo;{draft.original_words}&rdquo;</span>
                        </span>
                        <span className="block text-sm text-ink">
                          <DraftOutcome draft={draft} />
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}

              {state.interpretation.unsupported.length > 0 ? (
                <div>
                  <p className="font-semibold text-ink">Not turned into a rule</p>
                  <ul className="mt-1 space-y-2">
                    {state.interpretation.unsupported.map((item) => (
                      <li key={`${item.code}-${item.words}`} className="rounded-md border border-dashed border-line-strong bg-canvas p-3" data-testid="unsupported-request">
                        <blockquote className="text-ink">&ldquo;{item.words}&rdquo;</blockquote>
                        <p className="mt-1 text-sm text-ink-muted">{item.reason}</p>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}

              {state.interpretation.clarifications.length === 0 &&
              state.interpretation.proposed_rules.length === 0 &&
              state.interpretation.unsupported.length === 0 ? (
                <EmptyBlock title="Nothing in these words was read as a rule">
                  <p>Try wording that names a limit, for example a maximum share in one company.</p>
                </EmptyBlock>
              ) : null}
            </div>
          ) : null}
        </div>
      </Panel>

      <Panel
        title="Proposed rules"
        eyebrow="Inactive until confirmed"
        aside={
          <Badge tone="neutral" dashed>
            {state.proposedRules.length} proposed
          </Badge>
        }
        description="Offered by the fictional scenario or drafted from your words. Each one shows exactly what it would check. Change a number, clear it to leave the rule out, then confirm."
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
                  policy={policy}
                  purchase={purchase}
                  thresholdText={state.thresholdText[rule.rule_id] ?? ""}
                  onThresholdChange={(text) => actions.setThresholdText(rule.rule_id, text)}
                  buildPreviewRules={previewRulesFor(rule.rule_id)}
                  attempted={attempted}
                  inputRef={(element) => {
                    if (element) thresholdRefs.current.set(rule.rule_id, element);
                    else thresholdRefs.current.delete(rule.rule_id);
                  }}
                />
              ))}
            </ul>
            <div className="space-y-2 border-t border-line pt-4">
              <Button
                variant="primary"
                softDisabled={confirmable.length === 0}
                busy={confirming}
                busyLabel="Confirming…"
                icon={<CheckIcon />}
                data-testid="confirm-rules"
                onClick={() => void confirmAll()}
              >
                {confirmable.length === 0
                  ? "Confirm the rules"
                  : `Confirm ${confirmable.length === 1 ? "this 1 rule" : `these ${confirmable.length} rules`} with ${confirmable.length === 1 ? "its number" : "their numbers"}`}
              </Button>
              <p className="text-sm text-ink-muted" data-testid="confirm-hint">
                Confirms them together in one new policy version.
                {leftOut > 0 ? ` ${leftOut} ${leftOut === 1 ? "rule has" : "rules have"} no valid number and ${leftOut === 1 ? "stays" : "stay"} proposed.` : ""}
              </p>
              {attempted && confirmable.length === 0 ? (
                <p role="alert" className="text-sm font-semibold text-fail">
                  No proposed rule has a valid number yet. Enter a number in a rule above first.
                </p>
              ) : null}
            </div>
          </div>
        ) : (
          <EmptyBlock title={policy ? "No rule is waiting for confirmation" : "No rule is proposed"}>
            <p>
              {policy
                ? "Everything proposed so far has been confirmed. A confirmed number is changed in the Challenge stage, which creates a new policy version."
                : "The scenario offers no rule for this persona. Write one in your own words above."}
            </p>
          </EmptyBlock>
        )}
        {state.confirm.status === "error" ? (
          <ErrorBlock className="mt-4" title="The rules could not be confirmed" message={state.confirm.error ?? "The request failed."} onRetry={() => void confirmAll()}>
            <p>They are still proposed and inactive. The confirmed policy is unchanged.</p>
          </ErrorBlock>
        ) : null}
      </Panel>

      <PolicyPanel policy={policy} earlier={state.policies.slice(0, -1)} />
    </StageFrame>
  );
}
