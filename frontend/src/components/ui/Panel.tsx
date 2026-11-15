import { useId, type ReactNode } from "react";
import { cn } from "@/lib/cn";

export interface PanelProps {
  title: ReactNode;
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
}

/** A titled region: a card with a real heading, exposed as a named landmark region. */
export function Panel({ title, eyebrow, description, aside, children, className, level = 2, tone = "surface", id, focusableHeading = false }: PanelProps) {
  const generated = useId();
  const headingId = `${id ?? generated}-title`;
  const Heading = level === 2 ? "h2" : "h3";
  return (
    <section
      id={id}
      aria-labelledby={headingId}
      className={cn(
        "rounded-lg border border-line p-4 sm:p-6",
        tone === "surface" ? "bg-surface" : "bg-sunken",
        className,
      )}
    >
      <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
        <div className="min-w-0 space-y-1">
          {eyebrow ? <p className="text-sm font-semibold text-ink-muted">{eyebrow}</p> : null}
          <Heading
            id={headingId}
            tabIndex={focusableHeading ? -1 : undefined}
            className={cn("font-semibold text-ink", level === 2 ? "text-xl" : "text-lg")}
          >
            {title}
          </Heading>
        </div>
        {aside ? <div className="flex-none">{aside}</div> : null}
      </div>
      {description ? <div className="mt-2 max-w-prose text-ink-muted">{description}</div> : null}
      <div className="mt-4">{children}</div>
    </section>
  );
}

/** Label / value pairs. */
export function Facts({ children, className }: { children: ReactNode; className?: string }) {
  return <dl className={cn("grid grid-cols-1 gap-x-6 gap-y-3 sm:grid-cols-2", className)}>{children}</dl>;
}

export function Fact({ label, children, wide = false }: { label: ReactNode; children: ReactNode; wide?: boolean }) {
  return (
    <div className={cn("min-w-0", wide && "sm:col-span-2")}>
      <dt className="text-sm font-semibold text-ink-muted">{label}</dt>
      <dd className="mt-0.5 text-ink">{children}</dd>
    </div>
  );
}
