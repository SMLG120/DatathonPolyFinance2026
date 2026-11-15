"use client";

import { useId, useState, type FormEvent } from "react";
import { Button, LinkButton } from "@/components/ui/Button";
import { describedBy, Field, TextArea } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";
import type { Investigation } from "@/lib/contracts";
import { ruleTypeLabel } from "@/lib/rules";
import { stageHref } from "@/state/stage";
import { useWorkflow } from "@/state/workflow";

/**
 * Path 2: clarify a preference. The text goes back through the interpreter.
 * It may be recorded as an objective, raise a question or lead to a PROPOSED
 * rule — it never changes a confirmed rule or a report by itself.
 */
export function ClarifyPreferenceForm({ investigation }: { investigation: Investigation }) {
  const { state, actions } = useWorkflow();
  const textId = useId();
  const [text, setText] = useState("");
  const [attempted, setAttempted] = useState(false);
  const error = attempted && text.trim() === "" ? "Write what should be understood differently." : null;
  const busy = state.challenge.status === "loading";
  const response = state.preferenceResponse;

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setAttempted(true);
    if (text.trim() === "") {
      document.getElementById(textId)?.focus();
      return;
    }
    const answer = await actions.submitChallenge(investigation.investigation_id, { kind: "CLARIFY_PREFERENCE", text: text.trim() });
    if (answer) {
      setText("");
      setAttempted(false);
    }
  }

  return (
    <div className="space-y-6">
      <p className="max-w-prose text-ink">
        If the result does not reflect what you meant, say it in your own words. Your text is read again. Nothing becomes a rule unless you confirm
        it, so the confirmed policy and this report do not change here.
      </p>

      <form onSubmit={onSubmit} noValidate className="space-y-5" data-testid="clarify-preference-form">
        <Field htmlFor={textId} label="What did you mean?" hint="For example what a word in your goal should cover." error={error}>
          <TextArea
            id={textId}
            rows={3}
            value={text}
            onChange={(event) => setText(event.target.value)}
            aria-invalid={error ? true : undefined}
            aria-describedby={describedBy(textId, { hint: true, error: Boolean(error) })}
          />
        </Field>
        <Button type="submit" variant="primary" busy={busy} busyLabel="Reading your text…" data-testid="submit-preference">
          Record this clarification
        </Button>
      </form>

      {response ? (
        <div role="status" data-testid="preference-response">
          <Notice
            tone="info"
            title="Your clarification was recorded. No rule was changed."
            action={
              <LinkButton href={stageHref("goals")} size="sm">
                Review it in Goals &amp; rules
              </LinkButton>
            }
          >
            {response.objectives.length > 0 ? (
              <div>
                <p className="font-semibold">Kept as an objective, in your words:</p>
                <ul className="list-disc pl-5">
                  {response.objectives.map((objective) => (
                    <li key={objective.objective_id}>&ldquo;{objective.original_words}&rdquo;</li>
                  ))}
                </ul>
              </div>
            ) : null}
            {response.proposed_rules.length > 0 ? (
              <div>
                <p className="font-semibold">Proposed, inactive until you confirm:</p>
                <ul className="list-disc pl-5">
                  {response.proposed_rules.map((rule) => (
                    <li key={rule.rule_id}>{ruleTypeLabel(rule.rule_type)}</li>
                  ))}
                </ul>
              </div>
            ) : null}
            {response.clarifications.length > 0 ? (
              <p>
                {response.clarifications.length === 1 ? "One question needs" : `${response.clarifications.length} questions need`} your answer before a rule
                can be written.
              </p>
            ) : null}
            {response.unsupported.map((item) => (
              <p key={item.original_words}>
                Not turned into a rule: &ldquo;{item.original_words}&rdquo; — {item.reason}
              </p>
            ))}
            {response.notes.map((note) => (
              <p key={note}>{note}</p>
            ))}
          </Notice>
        </div>
      ) : null}
    </div>
  );
}
