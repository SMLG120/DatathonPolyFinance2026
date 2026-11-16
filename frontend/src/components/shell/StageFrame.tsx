"use client";

import type { ReactNode } from "react";
import { ProgressBar } from "@/components/tremor/ProgressBar";
import { LinkButton } from "@/components/ui/Button";
import { ArrowLeftIcon, ArrowRightIcon } from "@/components/ui/icons";
import { t } from "@/lib/i18n";
import { journeyFor, SCREEN_TITLES, stageHref, JOURNEY, type StageId } from "@/state/stage";

export interface StageFrameProps {
  stage: StageId;
  /** One or two sentences under the title that say what this stage is for. */
  lead: ReactNode;
  children: ReactNode;
  /** Shown above the Continue link, e.g. what is still missing before the next stage is useful. */
  continueNote?: ReactNode;
}

/**
 * The common frame of a stage: its one h1 (which receives focus when the stage
 * changes, so a screen reader announces "Step 3 of 6, Proposed purchase"), a
 * lead paragraph, the content, and Back / Continue links.
 *
 * Back and Continue are links because they navigate. No stage is locked: a
 * stage whose inputs are missing explains what it needs.
 */
export function StageFrame({ stage, lead, children, continueNote }: StageFrameProps) {
  const current = journeyFor(stage);
  const previous =
    stage === "goals" ? { id: "persona" as const, title: "profiles" }
    : stage === "purchase" ? { id: "goals" as const, title: "your limits" }
    : stage === "verdict" || stage === "investigation" || stage === "challenge" ? { id: "purchase" as const, title: "your idea" }
    : null;
  const next = stage === "persona" ? { id: "goals" as const, title: "Set your limits" } : stage === "goals" ? { id: "purchase" as const, title: "Test an idea" } : null;

  return (
    <article aria-labelledby="stage-title" className="space-y-6">
      <header className="space-y-2">
        <h1 id="stage-title" data-stage-heading tabIndex={-1} className="text-ink">
          <span className="block text-sm font-semibold text-ink-muted">
            {t("Step")} {current.number} {t("of")} {JOURNEY.length}
            <span className="sr-only">: </span>
          </span>
          <span className="mt-1 block text-3xl font-bold tracking-tight sm:text-4xl">{t(SCREEN_TITLES[stage])}</span>
        </h1>
        <div className="max-w-prose text-lg text-ink-muted">{lead}</div>
      </header>

      <ProgressBar value={current.number} max={JOURNEY.length} aria-label={t("Current step")} aria-valuetext={`${t("Step")} ${current.number} ${t("of")} ${JOURNEY.length}`} />
      {children}

      <nav aria-label={t("Previous and next stage")} className="space-y-3 border-t border-line pt-5">
        {continueNote ? <div className="text-ink-muted">{continueNote}</div> : null}
        <div className="flex flex-wrap items-center justify-between gap-3">
          {previous ? (
            <LinkButton href={stageHref(previous.id)} icon={<ArrowLeftIcon />}>
              {t("Back to")} {t(previous.title)}
            </LinkButton>
          ) : (
            <span />
          )}
          {next ? (
            <LinkButton href={stageHref(next.id)} variant="primary" iconAfter={<ArrowRightIcon />} data-testid="continue-link">
              {t(next.title)}
            </LinkButton>
          ) : null}
        </div>
      </nav>
    </article>
  );
}
