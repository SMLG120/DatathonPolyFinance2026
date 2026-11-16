"use client";

import { useId, useState, type ReactNode } from "react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { CheckIcon, ErrorIcon, InfoIcon } from "@/components/ui/icons";
import type { Clarification } from "@/lib/contracts";
import { t } from "@/lib/i18n";

export interface ClarificationCardProps {
  clarification: Clarification;
  /** The option already chosen for this question, if any. */
  chosenOptionId: string | null;
  /** Records the chosen definition. No request is sent: a supported option already carries the draft it leads to. */
  onChoose: (optionId: string) => void;
  /** What the chosen definition led to, in words (a listed draft, a rule already listed, nothing yet). */
  outcome?: ReactNode;
  /** Label of the action button. */
  chooseLabel?: string;
}

/**
 * Wording that has more than one meaning. Instead of guessing and writing a
 * rule, the interface asks. Only definitions that can actually be checked are
 * offered as choices; the others are listed with the reason they are not.
 */
export function ClarificationCard({ clarification, chosenOptionId, onChoose, outcome, chooseLabel = "Use this definition" }: ClarificationCardProps) {
  const headingId = useId();
  const groupName = useId();
  const errorId = useId();
  const [selected, setSelected] = useState<string | null>(chosenOptionId);
  const [attempted, setAttempted] = useState(false);
  const supported = clarification.options.filter((option) => option.supported);
  const unsupported = clarification.options.filter((option) => !option.supported);
  const showError = attempted && selected === null;

  return (
    <li>
      <article aria-labelledby={headingId} className="space-y-4 rounded-lg border border-unknown bg-surface p-4 sm:p-5" data-testid="clarification-card">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <h3 id={headingId} className="text-lg font-semibold text-ink">
            {clarification.question}
          </h3>
          {chosenOptionId ? (
            <Badge tone="accent" icon={<CheckIcon size={16} />}>
              {t("Definition chosen")}</Badge>
          ) : (
            <Badge tone="unknown" dashed icon={<InfoIcon size={16} />}>
              {t("No rule written yet")}</Badge>
          )}
        </div>
        <figure>
          <figcaption className="text-sm font-semibold text-ink-muted">{t("The words in question")}</figcaption>
          <blockquote className="mt-1 border-l-4 border-line-strong pl-3 text-ink">{t("&ldquo;")}{clarification.about_words}{t("&rdquo;")}</blockquote>
        </figure>

        {supported.length > 0 ? (
          <fieldset aria-describedby={showError ? errorId : undefined}>
            <legend className="font-semibold text-ink">{t("Which definition do you mean?")}</legend>
            <div className="mt-2 space-y-2">
              {supported.map((option) => {
                const optionId = `${groupName}-${option.option_id}`;
                return (
                  <label
                    key={option.option_id}
                    htmlFor={optionId}
                    className="flex min-h-11 cursor-pointer items-start gap-3 rounded-md border border-line-strong bg-surface p-3 has-[:checked]:border-2 has-[:checked]:border-accent has-[:checked]:bg-accent-soft"
                  >
                    <input
                      id={optionId}
                      type="radio"
                      name={groupName}
                      value={option.option_id}
                      checked={selected === option.option_id}
                      onChange={() => setSelected(option.option_id)}
                      className="mt-1 size-5 flex-none accent-accent"
                    />
                    <span>
                      <span className="block font-semibold text-ink">{option.label}</span>
                      <span className="block text-sm text-ink-muted">{option.description}</span>
                    </span>
                  </label>
                );
              })}
            </div>
            {showError ? (
              <p id={errorId} className="mt-2 flex items-start gap-1.5 text-sm font-semibold text-fail">
                <ErrorIcon size={16} className="mt-0.5 flex-none" />
                <span>{t("Choose one of the definitions above first.")}</span>
              </p>
            ) : null}
          </fieldset>
        ) : null}

        {unsupported.length > 0 ? (
          <div>
            <p className="font-semibold text-ink">{t("Readings that cannot be checked here")}</p>
            <ul className="mt-1 space-y-2">
              {unsupported.map((option) => (
                <li key={option.option_id} className="rounded-md border border-dashed border-line-strong bg-canvas p-3" data-testid="unsupported-option">
                  <span className="block font-semibold text-ink">{option.label}</span>
                  <span className="block text-sm text-ink-muted">{option.description}</span>
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        {supported.length > 0 ? (
          <Button
            softDisabled={selected === null}
            onClick={() => {
              if (selected === null) {
                setAttempted(true);
                return;
              }
              onChoose(selected);
            }}
            data-testid="choose-definition"
          >
            {chooseLabel}
          </Button>
        ) : null}

        <div role="status" aria-live="polite">
          {chosenOptionId && outcome ? (
            <div className="rounded-md bg-accent-soft px-3 py-2 text-ink" data-testid="clarification-outcome">
              {outcome}
            </div>
          ) : null}
        </div>
      </article>
    </li>
  );
}
