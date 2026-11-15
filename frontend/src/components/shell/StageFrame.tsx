"use client";

import type { ReactNode } from "react";
import { LinkButton } from "@/components/ui/Button";
import { ArrowLeftIcon, ArrowRightIcon } from "@/components/ui/icons";
import { nextStage, previousStage, stageById, stageHref, STAGES, type StageId } from "@/state/stage";

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
  const current = stageById(stage);
  const previous = previousStage(stage);
  const next = nextStage(stage);

  return (
    <article aria-labelledby="stage-title" className="space-y-6">
      <header className="space-y-2">
        <h1 id="stage-title" data-stage-heading tabIndex={-1} className="text-ink">
          <span className="block text-sm font-semibold text-ink-muted">
            Step {current.number} of {STAGES.length}
            <span className="sr-only">: </span>
          </span>
          <span className="mt-1 block text-3xl font-bold tracking-tight sm:text-4xl">{current.title}</span>
        </h1>
        <div className="max-w-prose text-lg text-ink-muted">{lead}</div>
      </header>

      {children}

      <nav aria-label="Previous and next stage" className="space-y-3 border-t border-line pt-5">
        {continueNote ? <div className="text-ink-muted">{continueNote}</div> : null}
        <div className="flex flex-wrap items-center justify-between gap-3">
          {previous ? (
            <LinkButton href={stageHref(previous.id)} icon={<ArrowLeftIcon />}>
              Back to {previous.title}
            </LinkButton>
          ) : (
            <span />
          )}
          {next ? (
            <LinkButton href={stageHref(next.id)} variant="primary" iconAfter={<ArrowRightIcon />} data-testid="continue-link">
              Continue to {next.title}
            </LinkButton>
          ) : null}
        </div>
      </nav>
    </article>
  );
}
