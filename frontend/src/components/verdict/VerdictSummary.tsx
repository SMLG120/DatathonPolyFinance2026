import type { ReactNode } from "react";
import { FailIcon, InfoIcon, PassIcon, UnknownIcon } from "@/components/ui/icons";
import { cn } from "@/lib/cn";
import { verdictHeadline, type HeadlineTone, type VerdictCounts } from "@/lib/verdict";

const TONE: Record<HeadlineTone, { box: string; icon: ReactNode }> = {
  fail: { box: "border-fail bg-fail-soft", icon: <FailIcon size={28} className="text-fail" /> },
  unknown: { box: "border-dashed border-unknown bg-unknown-soft", icon: <UnknownIcon size={28} className="text-unknown" /> },
  pass: { box: "border-pass bg-pass-soft", icon: <PassIcon size={28} className="text-pass" /> },
  none: { box: "border-line-strong bg-sunken", icon: <InfoIcon size={28} className="text-ink-muted" /> },
};

export interface VerdictSummaryProps {
  counts: VerdictCounts;
  /** What was checked, e.g. "After the purchase of NVDA at a final direct weight of 25.0%". */
  scope: ReactNode;
  headingId?: string;
  children?: ReactNode;
}

/**
 * The headline of a result.
 *
 * The three counts — fail, unknown, pass — are always all shown, zeros
 * included, so an UNKNOWN can never be folded into a pass. The headline text
 * comes from `verdictHeadline`, which only says "respected" when every checked
 * rule passed.
 */
export function VerdictSummary({ counts, scope, headingId = "verdict-headline", children }: VerdictSummaryProps) {
  const headline = verdictHeadline(counts);
  const tone = TONE[headline.tone];
  return (
    <section aria-labelledby={headingId} className={cn("rounded-lg border-2 p-4 sm:p-6", tone.box)} data-testid="verdict-summary" data-tone={headline.tone}>
      <p className="text-sm font-semibold text-ink-muted">{scope}</p>
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
