"use client";

import { useId, useState, type FormEvent } from "react";
import { ClarificationCard } from "@/components/rules/ClarificationCard";
import { DraftOutcome, OptionOutcome, ruleName } from "@/components/rules/DraftOutcome";
import { Button, LinkButton } from "@/components/ui/Button";
import { describedBy, Field, Select, TextArea } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";
import type { DemoChallenge, InvestigationJob, Objective } from "@/lib/contracts";
import { stageHref } from "@/state/stage";
import { clarificationKey, useWorkflow } from "@/state/workflow";
import { t } from "@/lib/i18n";

/**
 * Path 2: clarify a preference. The text goes back through the interpreter.
 * It may be recorded as an objective, raise a question or lead to a PROPOSED
 * rule — it never changes a confirmed rule or a report by itself.
 */
export function ClarifyPreferenceForm({ job, objectives, example }: { job: InvestigationJob; objectives: Objective[]; example: DemoChallenge | null }) {
  const { state, actions } = useWorkflow();
  const textId = useId();
  const objectiveFieldId = useId();
  const [text, setText] = useState("");
  const [objectiveId, setObjectiveId] = useState("");
  const [attempted, setAttempted] = useState(false);
  const error = attempted && text.trim() === "" ? "Write what should be understood differently." : null;
  const busy = state.challenge.status === "loading";
  const response = state.preferenceResponse;
  const exampleText = example?.type === "CLARIFY_PREFERENCE" && typeof example.payload.text === "string" ? example.payload.text : null;

  function fillExample() {
    if (!example || exampleText === null) return;
    const exampleObjective = example.payload.objective_id;
    setText(exampleText);
    setObjectiveId(typeof exampleObjective === "string" && objectives.some((objective) => objective.objective_id === exampleObjective) ? exampleObjective : "");
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setAttempted(true);
    if (text.trim() === "") {
      document.getElementById(textId)?.focus();
      return;
    }
    const answer = await actions.submitChallenge(job.id, {
      type: "CLARIFY_PREFERENCE",
      payload: { text: text.trim(), objective_id: objectiveId === "" ? null : objectiveId },
    });
    if (answer) {
      setText("");
      setAttempted(false);
    }
  }

  return (
    <div className="space-y-6">
      <h3 className="text-lg font-semibold text-ink">{t("Clarify a preference")}</h3>
      <p className="max-w-prose text-ink">
        {t("If the result does not reflect what you meant, say it in your own words. Your text is read again. Nothing becomes a rule unless you confirm it, so the confirmed policy and this report do not change here.")}</p>

      {example && exampleText !== null ? (
        <p>
          <Button size="sm" onClick={fillExample} data-testid="fill-example-preference">
            {t("Fill in the scenario&apos;s example:")} {example.label}
          </Button>
        </p>
      ) : null}

      <form onSubmit={onSubmit} noValidate className="space-y-5" data-testid="clarify-preference-form">
        <Field htmlFor={textId} label={t("What did you mean?")} hint={t("For example what a word in your objective should cover.")} error={error}>
          <TextArea
            id={textId}
            rows={3}
            value={text}
            onChange={(event) => setText(event.target.value)}
            aria-invalid={error ? true : undefined}
            aria-describedby={describedBy(textId, { hint: true, error: Boolean(error) })}
          />
        </Field>
        {objectives.length > 0 ? (
          <Field htmlFor={objectiveFieldId} label={t("Which objective is this about? (optional)")} hint={t("Kept with your words as context.")}>
            <Select id={objectiveFieldId} value={objectiveId} onChange={(event) => setObjectiveId(event.target.value)} aria-describedby={describedBy(objectiveFieldId, { hint: true })}>
              <option value="">{t("No particular objective")}</option>
              {objectives.map((objective) => (
                <option key={objective.objective_id} value={objective.objective_id}>
                  {objective.original_words}
                </option>
              ))}
            </Select>
          </Field>
        ) : null}
        <Button type="submit" variant="primary" busy={busy} busyLabel="Reading your text…" data-testid="submit-preference">
          {t("Record this clarification")}</Button>
      </form>

      {response ? (
        <div className="space-y-4" data-testid="preference-response">
          <div role="status">
            <Notice
              tone="info"
              title={t("Your clarification was read. No rule was changed.")}
              action={
                <LinkButton href={stageHref("goals")} size="sm">
                  {t("Review it in Goals &amp; rules")}</LinkButton>
              }
            >
              <p>
                {t("Read from: &ldquo;")}{response.original_words}{t("&rdquo; Everything below is a draft. The confirmed policy and the report are exactly as they were.")}</p>
            </Notice>
          </div>

          {response.unsupported.length > 0 ? (
            <div>
              <h4 className="font-semibold text-ink">{t("Not turned into a rule")}</h4>
              <ul className="mt-1 space-y-2">
                {response.unsupported.map((item) => (
                  <li key={`${item.code}-${item.words}`} className="rounded-md border border-dashed border-line-strong bg-canvas p-3 text-ink" data-testid="unsupported-request">
                    <span className="block font-semibold">{t("&ldquo;")}{item.words}{t("&rdquo;")}</span>
                    <span className="block text-sm">{item.reason}</span>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          {response.clarifications.length > 0 ? (
            <div>
              <h4 className="font-semibold text-ink">
                {response.clarifications.length === 1 ? "One question needs your answer" : `${response.clarifications.length} questions need your answer`}{" "}
                {t("before a rule can be written")}</h4>
              <ul className="mt-2 space-y-4">
                {response.clarifications.map((clarification) => {
                  // Named by this answer as well as by its id: the question asked in Goals & rules can have the same id.
                  const key = clarificationKey(response.interpretation_id, clarification.clarification_id);
                  const chosen = state.chosenOptions[key] ?? null;
                  return (
                    <ClarificationCard
                      key={key}
                      clarification={clarification}
                      chosenOptionId={chosen}
                      onChoose={(optionId) => actions.chooseOption(response.interpretation_id, clarification.clarification_id, optionId)}
                      outcome={<OptionOutcome option={clarification.options.find((option) => option.option_id === chosen)} place="elsewhere" />}
                    />
                  );
                })}
              </ul>
            </div>
          ) : null}

          {response.proposed_rules.length > 0 ? (
            <div>
              <h4 className="font-semibold text-ink">Rules drafted from your words: inactive until you confirm them</h4>
              <ul className="mt-1 space-y-2">
                {response.proposed_rules.map((draft) => (
                  <li key={draft.rule_id} className="rounded-md border border-line bg-canvas p-3" data-testid="drafted-rule">
                    <span className="block text-ink">{ruleName(draft)}</span>
                    <span className="block text-sm text-ink">
                      <DraftOutcome draft={draft} place="elsewhere" />
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          {response.objectives.length > 0 ? (
            <div>
              <h4 className="font-semibold text-ink">{t("Kept as an objective, word for word")}</h4>
              <ul className="mt-1 list-disc pl-5 text-ink">
                {response.objectives.map((objective) => (
                  <li key={objective.objective_id}>{t("&ldquo;")}{objective.original_words}{t("&rdquo;")}</li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
