"use client";

import { CheckIcon } from "@/components/ui/icons";
import { cn } from "@/lib/cn";
import { STAGES, stageHref, type StageId } from "@/state/stage";

export interface StepperProps {
  current: StageId;
  /** Stages whose task is done. Shown with a check mark and the word "completed". */
  completed: ReadonlySet<StageId>;
}

/**
 * The six stages as an ordered list of links.
 *
 * - Links, not buttons: each stage has its own URL (`#/verdict`), so Enter
 *   activates them, Back/Forward work and they can be opened directly.
 * - The current stage carries `aria-current="step"`, a filled marker, a heavier
 *   label and a bar — it is never marked by colour alone.
 * - Every stage stays reachable. A stage whose prerequisites are missing
 *   explains what is needed instead of being locked.
 * - Below 640px only the numbered markers are shown; the stage heading right
 *   below names the current stage, and the links keep their full accessible names.
 */
export function Stepper({ current, completed }: StepperProps) {
  return (
    <nav aria-label="Stages of the simulation">
      <ol className="flex gap-1 sm:gap-2">
        {STAGES.map((stage) => {
          const isCurrent = stage.id === current;
          const isDone = completed.has(stage.id) && !isCurrent;
          return (
            <li key={stage.id} className="min-w-0 flex-1">
              <a
                href={stageHref(stage.id)}
                aria-current={isCurrent ? "step" : undefined}
                className={cn(
                  "group flex min-h-11 flex-col items-center justify-center gap-1 rounded-t-md border-b-4 px-1 py-2 text-center",
                  "lg:flex-row lg:gap-2 lg:text-left",
                  isCurrent ? "border-accent bg-accent-soft" : "border-transparent hover:bg-sunken",
                )}
              >
                <span
                  aria-hidden="true"
                  className={cn(
                    "tabular flex size-7 flex-none items-center justify-center rounded-full border-2 text-sm font-bold",
                    isCurrent && "border-accent bg-accent text-on-accent",
                    isDone && "border-accent bg-surface text-accent",
                    !isCurrent && !isDone && "border-line-strong bg-surface text-ink-muted",
                  )}
                >
                  {isDone ? <CheckIcon size={16} /> : stage.number}
                </span>
                <span
                  className={cn(
                    "text-sm leading-tight",
                    isCurrent ? "font-bold text-accent-strong" : "font-semibold text-ink-muted group-hover:text-ink",
                  )}
                >
                  {/* One accessible name at every width; the visible labels are decorative copies of it. */}
                  <span className="sr-only">
                    Step {stage.number} of {STAGES.length}: {stage.title}
                    {isDone ? " (completed)" : ""}
                  </span>
                  <span aria-hidden="true" className="hidden sm:inline lg:hidden">
                    {stage.short}
                  </span>
                  <span aria-hidden="true" className="hidden lg:inline">
                    {stage.title}
                  </span>
                </span>
              </a>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
