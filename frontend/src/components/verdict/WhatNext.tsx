"use client";

import { LinkButton } from "@/components/ui/Button";
import type { CheckResult } from "@/lib/contracts";
import { summaryCounts } from "@/lib/verdict";
import { stageHref } from "@/state/stage";
import { goToSection } from "./VerdictSummary";

const plural = (count: number, one: string, many: string) => `${count} ${count === 1 ? one : many}`;

/**
 * The practical reading of the result, in plain words, and the actions available from here. Every number is one of the
 * engine's own counts (summaryCounts); nothing is recomputed, and nothing here recommends a purchase.
 */
export function WhatNext({ result }: { result: CheckResult }) {
  const counts = summaryCounts(result.summary);
  if (counts.total === 0) return null;
  // Offered only when the engine supports a figure; the section itself says why when it does not.
  const hasMax = result.max_compliant?.status === "SUPPORTED";
  let meaning: string;
  if (counts.fail > 0) {
    meaning = `This idea goes over ${counts.fail} of the ${plural(counts.total, "limit", "limits")} you confirmed.`;
    if (counts.unknown > 0) meaning += ` ${plural(counts.unknown, "other limit cannot", "other limits cannot")} be decided with the data held.`;
  } else if (counts.unknown > 0) {
    meaning = `No confirmed limit is shown to be broken, but ${plural(counts.unknown, "limit cannot", "limits cannot")} be decided with the data held. A missing figure is never counted as zero.`;
  } else {
    meaning = `${counts.total === 1 ? "The limit" : `All ${counts.total} limits`} you confirmed ${counts.total === 1 ? "is" : "are"} respected by this idea, on the data held. That says nothing about whether the investment itself is a good one.`;
  }
  return (
    <section aria-labelledby="what-next-title" className="rounded-xl border border-line bg-surface p-5" data-testid="what-next">
      <h2 id="what-next-title" className="text-lg font-semibold text-ink">
        What this means and what you can do next
      </h2>
      <p className="mt-1 max-w-prose text-ink" data-testid="what-next-meaning">
        {meaning} This is a check against your own limits, not advice.
      </p>
      <ul className="mt-3 list-disc space-y-1 pl-5 text-ink-muted">
        <li>Change the investment or the share it would have, then check again.</li>
        {counts.unknown > 0 ? <li>See which data is missing and why it leaves a limit undecided.</li> : null}
        <li>Read the evidence behind each figure, or dispute a figure or a limit you disagree with.</li>
      </ul>
      <div className="mt-4 flex flex-wrap gap-3" data-testid="result-actions">
        <LinkButton href={stageHref("purchase")} variant="primary">
          Modify my idea
        </LinkButton>
        {hasMax ? (
          <LinkButton href="#report-max" onClick={(event) => { event.preventDefault(); goToSection("report-max"); }}>
            Largest share that fits my limits
          </LinkButton>
        ) : null}
        <LinkButton href="#report-coverage" onClick={(event) => { event.preventDefault(); goToSection("report-coverage"); }}>
          Sources and missing data
        </LinkButton>
        <LinkButton href={stageHref("challenge")}>Review or dispute this result</LinkButton>
      </div>
    </section>
  );
}
