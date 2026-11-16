"use client";

import { useId, useRef, useState, useLayoutEffect } from "react";
import { ObjectivePendingNote } from "@/components/portfolio/CustomizePanel";
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
import { clarificationKey, useWorkflow } from "@/state/workflow";
import { t, tf } from "@/lib/i18n";

const OBJECTIVE_SOURCE: Record<Objective["source"], string> = {
  USER_STATED: "Stated by you",
  FICTIONAL_SCENARIO: "From the fictional scenario",
};

const OBJECTIVE_KIND: Record<Objective["kind"], string> = {
  goal: "goal",
  preference: "preference",
  constraint: "constraint",
};

/** `edited` is the scenario's own objective when the one listed under its id carries the user's wording instead. */
function ObjectiveList({ objectives, edited }: { objectives: Objective[]; edited: Objective | null }) {
  return (
    <ul className="space-y-3">
      {objectives.map((objective) => (
        <li key={objective.objective_id} className="rounded-md border border-line bg-canvas p-3" data-testid="objective" data-objective-source={objective.source}>
          {edited && edited.objective_id === objective.objective_id ? (
            <p className="mb-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-ink" data-testid="objective-edited-note">
              <Badge tone="accent" dashed>
                {t("Your wording")}
              </Badge>
              <span>
                {t("You edited this objective in step 1. The scenario said:")} &ldquo;{edited.original_words}&rdquo;{" "}
                {t("It is context only: editing it created, changed and confirmed no rule.")}
              </span>
            </p>
          ) : null}
          <blockquote className="text-ink" lang={objective.source === "FICTIONAL_SCENARIO" ? "en" : undefined}>&ldquo;{objective.original_words}&rdquo;</blockquote>
          <p className="mt-1 text-sm text-ink-muted">
            {t(OBJECTIVE_SOURCE[objective.source])} · {t(OBJECTIVE_KIND[objective.kind])} {t("· recorded word for word · not scored")}{objective.case_reference ? ` · ${objective.case_reference}` : ""}
          </p>
        </li>
      ))}
    </ul>
  );
}

function PolicyPanel({ policy, earlier }: { policy: Policy | null; earlier: Policy[] }) {
  if (!policy) {
    return (
      <Panel id="confirmed-policy" title={t("Confirmed policy")} focusableHeading>
        <EmptyBlock title={t("No confirmed rule yet")}>
          <p>{t("Checks use confirmed rules only. A proposed rule stays inactive until you confirm it with a threshold.")}</p>
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
      title={t("Your confirmed limits")}
      eyebrow={t("In force")}
      aside={
        <Badge tone="accent" icon={<CheckIcon size={16} />}>
          {active.length === 1 ? t("1 active rule") : tf("{count} active rules", { count: active.length })}
        </Badge>
      }
      description={t("These limits will be used to check your idea.")}
    >
      <div className="space-y-5">
        <details><summary className="cursor-pointer text-sm font-medium text-ink-muted">{t("History and source")}</summary><Facts className="mt-3 sm:grid-cols-3">
          <Fact label={t("Version")}>
            <span className="tabular">{policy.version}</span>
          </Fact>
          <Fact label={t("Created")}>
            <span className="tabular">{formatDateTime(policy.created_at)}</span>
          </Fact>
          <Fact label={t("Replaces")}>{policy.parent_version === null ? t("Nothing: first version") : tf("Version {version}", { version: policy.parent_version })}</Fact>
          <Fact label={t("Change note")} wide>
            {policy.change_note}
          </Fact>
        </Facts></details>
        <ul className="space-y-4">
          {active.map((rule) => (
            <PolicyRuleCard key={rule.rule_id} rule={rule} objective={objectiveOf(rule.objective_id)} />
          ))}
        </ul>
        {superseded.length > 0 ? (
          <details className="rounded-md border border-line bg-canvas p-3">
            <summary className="min-h-6 cursor-pointer font-semibold text-ink">
              {tf("Superseded rules ({count}): kept for the record, not checked", { count: superseded.length })}
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
            <summary className="min-h-6 cursor-pointer font-semibold text-ink">{t("Earlier versions (")}{earlier.length})</summary>
            <ul className="mt-3 space-y-3">
              {earlier
                .slice()
                .reverse()
                .map((version) => (
                  <li key={version.version}>
                    <p className="font-semibold text-ink">
                      {t("Version")} <span className="tabular">{version.version}</span>{" "}
                      <span className="font-normal text-ink-muted">
                        {t("· created")} <span className="tabular">{formatDateTime(version.created_at)}</span>
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

  const [confirmationFocus, setConfirmationFocus] = useState(0);
  useLayoutEffect(() => {
    if (confirmationFocus > 0) document.getElementById("confirmed-policy-title")?.focus();
  }, [confirmationFocus]);

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
      setConfirmationFocus((count) => count + 1);
    }
  }

  function interpret() {
    if (state.goalText.trim() === "") {
      setGoalError(t("Write what you want in a sentence first."));
      goalRef.current?.focus();
      return;
    }
    setGoalError(null);
    void actions.interpretGoal();
  }

  return (
    <StageFrame
      stage="goals"
      lead={t("Review these limits and confirm the ones you want to use.")}
      continueNote={policy ? null : t("You can continue, but a purchase can only be checked once at least one rule is confirmed.")}
    >
      {state.proposedRules.length > 0 || !policy ? (
      <Panel
        title={t("Your limits")}
        eyebrow={t("Inactive until confirmed")}
        aside={
          <Badge tone="neutral" dashed>
            {state.proposedRules.length} {t("proposed")}</Badge>
        }
        description={t("Offered by the fictional scenario or drafted from your words. Each one shows exactly what it would check. Change a number, clear it to leave the rule out, then confirm.")}
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
                  customPortfolio={derived.customPortfolio}
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
                busyLabel={t("Confirming…")}
                icon={<CheckIcon />}
                data-testid="confirm-rules"
                onClick={() => void confirmAll()}
              >
                {confirmable.length === 0
                  ? t("Confirm the rules")
                  : confirmable.length === 1
                    ? t("Confirm this 1 rule with its number")
                    : tf("Confirm these {count} rules with their numbers", { count: confirmable.length })}
              </Button>
              <p className="text-sm text-ink-muted" data-testid="confirm-hint">
                {t("Only the limits you confirm will be checked.")}{leftOut > 0 ? ` ${leftOut === 1 ? t("1 rule has no valid number and stays proposed.") : tf("{count} rules have no valid number and stay proposed.", { count: leftOut })}` : ""}
              </p>
              {attempted && confirmable.length === 0 ? (
                <p role="alert" className="text-sm font-semibold text-fail">
                  {t("No proposed rule has a valid number yet. Enter a number in a rule above first.")}</p>
              ) : null}
            </div>
          </div>
        ) : (
          <EmptyBlock title={policy ? t("No rule is waiting for confirmation") : t("No rule is proposed")}>
            <p>
              {policy
                ? t("Everything proposed so far has been confirmed. A confirmed number is changed in the Challenge stage, which creates a new policy version.")
                : t("The scenario offers no rule for this persona. Write one in your own words above.")}
            </p>
          </EmptyBlock>
        )}
        {state.confirm.status === "error" ? (
          state.confirm.code === "POLICY_VERSION_CONFLICT" ? (
            // No "Try again": the same request would be refused again. The stage has started again instead.
            <ErrorBlock className="mt-4" title={t("The rules could not be confirmed")} message={state.confirm.error ?? t("The policy has a newer version than the one this page held.")}>
              <div className="space-y-1" data-testid="policy-conflict">
                <p>
                  {t("The policy was changed after this page last received it: from another tab or session, or by a request whose answer never arrived. The service cannot send this page the newer version.")}</p>
                <p>
                  {t("So this page has set its copy of the policy aside, and this stage starts again: every rule above is a proposal, with the number shown in it. Confirming them creates a new policy, starting at version 1. Nothing is checked until then. Reports already made keep the version they were checked against.")}</p>
              </div>
            </ErrorBlock>
          ) : (
            <ErrorBlock className="mt-4" title={t("The rules could not be confirmed")} message={state.confirm.error ?? t("The request failed.")} onRetry={() => void confirmAll()}>
              <p>{t("They are still proposed and inactive. The confirmed policy is unchanged.")}</p>
            </ErrorBlock>
          )
        ) : null}
      </Panel>

      ) : null}
      {policy ? <PolicyPanel policy={policy} earlier={state.policies.slice(0, -1)} /> : null}
      <Panel
        title={t("Why these limits?")}
        // An edited objective is stored with the next rule confirmation, if there is one, so it stays on screen while the user confirms.
        collapsible={!state.objectiveEdited}
        eyebrow={t("Context, not rules")}
        description={t("An objective is kept word for word to give results their context. It is never marked pass or fail, and it never implies a number.")}
      >
        {state.portfolio.status !== "ready" ? (
          <Notice tone="caution" title={t("No portfolio is loaded")}>
            <p>{t("The objective and the offered rules come with the persona. Load one in stage 1.")}</p>
          </Notice>
        ) : state.objectives.length > 0 ? (
          <div className="space-y-3">
            <ObjectiveList objectives={state.objectives} edited={state.objectiveEdited ? (scenario?.objectives[0] ?? null) : null} />
            <ObjectivePendingNote policy={policy} objective={scenario?.objectives[0] ? objectiveOf(scenario.objectives[0].objective_id) : undefined} />
          </div>
        ) : (
          <EmptyBlock title={t("No objective is recorded")}>
            <p>{t("The scenario carries no objective for this persona.")}</p>
          </EmptyBlock>
        )}
      </Panel>

      <Panel
        title={t("Add a limit in your own words")}
        collapsible
        eyebrow={t("Optional")}
        description={t("Write a limit or an exclusion in a sentence. The service drafts the kind of rule from it and asks when a word has more than one meaning. It never invents a number.")}
      >
        <div className="space-y-4">
          <Field htmlFor={goalId} label={t("What should the portfolio respect?")} hint={t("For example a maximum share in one company, or holdings to avoid.")} error={goalError}>
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
            <Button softDisabled={state.goalText.trim() === ""} busy={interpreting} busyLabel={t("Reading your words…")} onClick={interpret} data-testid="interpret-words">
              {state.interpretation ? t("Interpret these words again") : t("Interpret these words")}
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
                {t("Use the scenario’s sentence")}</Button>
            ) : null}
          </div>

          {interpreting && !state.interpretation ? <LoadingBlock label={t("Reading your words and drafting rules…")} /> : null}
          {state.interpret.status === "error" ? (
            state.interpret.kind === "no_fixture" ? (
              <Notice tone="info" role="status" title={t("The test data holds no interpretation of these words")}>
                <p data-testid="interpret-not-recorded">{state.interpret.error}</p>
              </Notice>
            ) : (
              <ErrorBlock title={t("Your words could not be read")} message={state.interpret.error ?? t("The request failed.")} onRetry={interpret}>
                <p>{t("No rule was created or changed. The rules offered below can still be confirmed by hand.")}</p>
              </ErrorBlock>
            )
          ) : null}

          {state.interpretation ? (
            <div className="space-y-4 border-t border-line pt-4" data-testid="interpretation">
              <p className="text-ink">
                <span className="font-semibold">{t("Draft read from:")}</span> &ldquo;{state.interpretation.original_words}&rdquo;{" "}
                <span className="text-sm text-ink-muted">{t("Nothing in a draft is active, and no stored rule was changed.")}</span>
              </p>

              {state.interpretation.clarifications.length > 0 ? (
                <ul className="space-y-4">
                  {state.interpretation.clarifications.map((clarification) => {
                    // Named by the answer as well as by its id: a later answer numbers its questions from 1 again.
                    const interpretationId = state.interpretation?.interpretation_id ?? "";
                    const key = clarificationKey(interpretationId, clarification.clarification_id);
                    const chosen = state.chosenOptions[key] ?? null;
                    return (
                      <ClarificationCard
                        key={key}
                        clarification={clarification}
                        chosenOptionId={chosen}
                        onChoose={(optionId) => actions.chooseOption(interpretationId, clarification.clarification_id, optionId)}
                        outcome={<OptionOutcome option={clarification.options.find((option) => option.option_id === chosen)} />}
                      />
                    );
                  })}
                </ul>
              ) : null}

              {state.interpretation.proposed_rules.length > 0 ? (
                <div>
                  <p className="font-semibold text-ink">{t("Rules drafted from your words")}</p>
                  <ul className="mt-1 space-y-2">
                    {state.interpretation.proposed_rules.map((draft) => (
                      <li key={draft.rule_id} className="rounded-md border border-line bg-canvas p-3" data-testid="drafted-rule">
                        <span className="block text-ink">
                          {ruleName(draft)} <span className="text-sm text-ink-muted">{t("· from")} &ldquo;{draft.original_words}&rdquo;</span>
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
                  <p className="font-semibold text-ink">{t("Not turned into a rule")}</p>
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
                <EmptyBlock title={t("Nothing in these words was read as a rule")}>
                  <p>{t("Try wording that names a limit, for example a maximum share in one company.")}</p>
                </EmptyBlock>
              ) : null}
            </div>
          ) : null}
        </div>
      </Panel>


    </StageFrame>
  );
}
