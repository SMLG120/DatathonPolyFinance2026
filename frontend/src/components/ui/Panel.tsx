"use client";

import { useId, type ReactNode } from "react";
import { cn } from "@/lib/cn";
import { Card } from "@/components/tremor/Card";
import { TestDataTag } from "./TestDataTag";

export interface PanelProps {
  title: ReactNode;
  collapsible?: boolean;
  /** Small label above the title that says what kind of thing this panel is. */
  eyebrow?: ReactNode;
  description?: ReactNode;
  /** Shown at the right of the heading row (a badge, a version). */
  aside?: ReactNode;
  children: ReactNode;
  className?: string;
  /** Heading level. Panels inside a stage are h2; panels nested in a panel are h3. */
  level?: 2 | 3;
  tone?: "surface" | "sunken";
  id?: string;
  /** Lets code move focus to the heading (`#<id>-title`) after an action replaces the control that had focus. */
  focusableHeading?: boolean;
  /** True when the panel shows figures: in fixtures mode it then carries the "Test data" tag. */
  figures?: boolean;
}

/** A titled region: a card with a real heading, exposed as a named landmark region. */
export function Panel({ title, eyebrow, description, aside, children, className, level = 2, tone = "surface", id, focusableHeading = false, figures = false, collapsible = false }: PanelProps) {
  const generated = useId();
  const headingId = `${id ?? generated}-title`;
  const Heading = level === 2 ? "h2" : "h3";
  const Container = collapsible ? "details" : "section";
  const Header = collapsible ? "summary" : "div";
  return (
    <Card asChild>
    <Container
      id={id}
      aria-labelledby={headingId}
      data-figures={figures ? "true" : undefined}
      className={cn(
        "rounded-xl border border-line p-5 shadow-xs sm:p-7",
        tone === "surface" ? "bg-surface" : "bg-sunken",
        className,
      )}
    >
      <Header className={cn("flex flex-wrap items-start justify-between gap-x-4 gap-y-2", collapsible && "cursor-pointer list-none [&::-webkit-details-marker]:hidden")}>
        <div className="min-w-0 space-y-1">
          {eyebrow ? <p className="text-xs font-semibold uppercase tracking-wider text-ink-muted">{eyebrow}</p> : null}
          <Heading
            id={headingId}
            tabIndex={focusableHeading ? -1 : undefined}
            className={cn("font-semibold text-ink", level === 2 ? "text-xl" : "text-lg")}
          >
            {collapsible ? <span aria-hidden="true" className="mr-2 text-ink-muted">＋</span> : null}{title}
          </Heading>
        </div>
        {aside || figures ? (
          <div className="flex flex-none flex-wrap items-center gap-2">
            {figures ? <TestDataTag /> : null}
            {aside}
          </div>
        ) : null}
      </Header>
      {description ? <div className="mt-2 max-w-prose text-ink-muted">{description}</div> : null}
      <div className="mt-4">{children}</div>
    </Container>
    </Card>
  );
}

/** Label / value pairs. */
export function Facts({ children, className }: { children: ReactNode; className?: string }) {
  return <dl className={cn("grid grid-cols-1 gap-x-6 gap-y-3 sm:grid-cols-2", className)}>{children}</dl>;
}

export function Fact({ label, children, wide = false }: { label: ReactNode; children: ReactNode; wide?: boolean }) {
  return (
    <div className={cn("min-w-0", wide && "sm:col-span-2")}>
      <dt className="text-xs font-semibold uppercase tracking-wider text-ink-muted">{label}</dt>
      <dd className="mt-0.5 text-ink">{children}</dd>
    </div>
  );
}
