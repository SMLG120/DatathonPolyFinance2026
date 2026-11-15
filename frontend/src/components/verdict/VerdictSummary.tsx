"use client";

import type { ReactNode } from "react";
import { FailIcon, InfoIcon, PassIcon, UnknownIcon } from "@/components/ui/icons";
import { TestDataTag } from "@/components/ui/TestDataTag";
import { cn } from "@/lib/cn";
import type { Summary } from "@/lib/contracts";
import { summaryCounts, verdictHeadline, type HeadlineTone } from "@/lib/verdict";
import { stageHref } from "@/state/stage";

const TONE: Record<HeadlineTone, { box: string; icon: ReactNode }> = {
  fail: { box: "border-fail bg-fail-soft", icon: <FailIcon size={28} className="text-fail" /> },
  unknown: { box: "border-dashed border-unknown bg-unknown-soft", icon: <UnknownIcon size={28} className="text-unknown" /> },
  pass: { box: "border-pass bg-pass-soft", icon: <PassIcon size={28} className="text-pass" /> },
  none: { box: "border-line-strong bg-sunken", icon: <InfoIcon size={28} className="text-ink-muted" /> },
};

export interface SummaryLink {
  /** id of the section on this page. */
  id: string;
  label: string;
}

/**
 * Moves to a section of the page. The URL hash carries the stage, so the link
 * moves focus itself: a closed section is opened first, then its heading (or
 * its summary) receives focus and is scrolled into view.
 */
export function goToSection(id: string): void {
  const section = document.getElementById(id);
  if (!section) return;
  // A deep evidence link also reveals its enclosing optional sections.
  let parent = section.parentElement;
  while (parent) {
    if (parent instanceof HTMLDetailsElement) parent.open = true;
    parent = parent.parentElement;
  }
  let target: HTMLElement | null;
  if (section instanceof HTMLDetailsElement) {
    section.open = true;
    target = section.querySelector("summary");
  } else {
    target = document.getElementById(`${id}-title`);
  }
  (target ?? section).focus({ preventScroll: true });
  section.scrollIntoView?.({ block: "start" });
}

export interface VerdictSummaryProps {
  /** The engine's own summary. The headline and the counts are worded from it, never recomputed. */
  summary: Summary;
  /** What was checked, e.g. "After the purchase of NVDA at a final direct weight of 25.0%". */
  scope: ReactNode;
  /** In-page links to the sections of the report, in page order. */
  links?: SummaryLink[];
  headingId?: string;
  children?: ReactNode;
}

/**
 * The headline of a result.
 *
 * The three counts — fail, unknown, pass — are always all shown, zeros
 * included, so an UNKNOWN can never be folded into a pass. They are the
 * engine's counts. The card carries the "Test data" tag itself in fixtures
 * mode, so a cropped picture of it still says what its figures are.
 */
export function VerdictSummary({ summary, scope, links = [], headingId = "verdict-headline", children }: VerdictSummaryProps) {
  const headline = verdictHeadline(summary);
  const counts = summaryCounts(summary);
  const tone = TONE[headline.tone];
  return (
    <section
      aria-labelledby={headingId}
      className={cn("rounded-lg border-2 p-4 sm:p-6", tone.box)}
      data-testid="verdict-summary"
      data-tone={headline.tone}
      data-headline={summary.headline}
      data-figures="true"
    >
      <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-1">
        <p className="min-w-0 text-sm font-semibold text-ink-muted">{scope}</p>
        <TestDataTag />
      </div>
      <div className="mt-2 flex items-start gap-3">
        <span className="mt-1 flex-none">{tone.icon}</span>
        <div className="min-w-0">
          <h2 id={headingId} className="text-2xl font-bold tracking-tight text-ink sm:text-3xl" data-testid="verdict-headline">
            {headline.title}
          </h2>
          <p className="mt-1 text-lg text-ink">{headline.detail}</p>
        </div>
      </div>
      <ul className="mt-4 flex flex-wrap gap-3" aria-label="Number of confirmed rules by result">
        <CountChip kind="fail" count={counts.fail} label="Fail" icon={<FailIcon size={18} className="text-fail" />} />
        <CountChip kind="unknown" count={counts.unknown} label="Unknown" icon={<UnknownIcon size={18} className="text-unknown" />} dashed />
        <CountChip kind="pass" count={counts.pass} label="Pass" icon={<PassIcon size={18} className="text-pass" />} />
      </ul>
      {children ? <div className="mt-4 space-y-2 border-t border-line-strong pt-4">{children}</div> : null}
      {links.length > 0 ? (
        <nav aria-label="Sections of this report" className="mt-4 border-t border-line-strong pt-3" data-testid="summary-links">
          <ul className="flex flex-wrap gap-x-5 gap-y-1">
            {links.map((link) => (
              <li key={link.id}>
                <a
                  href={stageHref("verdict")}
                  onClick={(event) => {
                    event.preventDefault();
                    goToSection(link.id);
                  }}
                  className="inline-flex min-h-9 items-center font-semibold text-accent underline decoration-1 underline-offset-4 hover:text-accent-strong hover:decoration-2"
                  data-section={link.id}
                >
                  {link.label}
                </a>
              </li>
            ))}
          </ul>
        </nav>
      ) : null}
    </section>
  );
}

function CountChip({ kind, count, label, icon, dashed = false }: { kind: string; count: number; label: string; icon: ReactNode; dashed?: boolean }) {
  return (
    <li
      className={cn("flex min-w-28 items-center gap-2 rounded-md border border-line-strong bg-surface px-3 py-2", dashed && "border-dashed")}
      data-testid={`count-${kind}`}
      data-count={count}
    >
      {icon}
      <span className="tabular text-2xl font-bold text-ink">{count}</span>
      <span className="font-semibold text-ink">{label}</span>
    </li>
  );
}
