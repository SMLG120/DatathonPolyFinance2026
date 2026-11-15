"use client";

import type { ReactNode } from "react";
import { cn } from "@/lib/cn";
import { ChevronIcon } from "./icons";
import { TestDataTag } from "./TestDataTag";

export interface DisclosureProps {
  id: string;
  title: string;
  /** One line that stays visible while the section is closed, so nothing important is hidden by collapsing it. */
  hint?: ReactNode;
  children: ReactNode;
  /** True when the section shows figures: in fixtures mode its summary line then carries the "Test data" tag. */
  figures?: boolean;
  className?: string;
}

/**
 * A section that is closed until asked for. It is a native <details>, so it
 * opens with Enter or Space, with a tap, and with find-in-page, and it needs
 * no script. The title is a real heading inside the summary, so the section
 * stays in the page outline whether it is open or closed.
 */
export function Disclosure({ id, title, hint, children, figures = false, className }: DisclosureProps) {
  return (
    <details
      id={id}
      className={cn("scroll-mt-16 rounded-lg border border-line bg-surface p-4 sm:p-6", className)}
      data-testid="disclosure"
      data-figures={figures ? "true" : undefined}
    >
      <summary className="byb-summary -m-1 flex min-h-11 cursor-pointer flex-wrap items-center gap-x-3 gap-y-1 rounded-md p-1">
        <ChevronIcon size={20} className="text-ink-muted" />
        <h2 id={`${id}-title`} className="text-xl font-semibold text-ink">
          {title}
        </h2>
        {figures ? <TestDataTag /> : null}
        {hint ? <span className="basis-full text-sm text-ink-muted sm:basis-auto">{hint}</span> : null}
      </summary>
      <div className="mt-4">{children}</div>
    </details>
  );
}
