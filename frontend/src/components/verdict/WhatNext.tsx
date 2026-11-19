"use client";

import { Button, LinkButton } from "@/components/ui/Button";
import type { CheckResult } from "@/lib/contracts";
import { t, tf } from "@/lib/i18n";
import { summaryCounts } from "@/lib/verdict";
import { stageHref } from "@/state/stage";
import { PRINT_REPORT_LABEL } from "./PrintReport";
import { goToSection } from "./VerdictSummary";

/**
 * The practical reading of the result, in plain words, and the actions available from here. Every number is one of the
 * engine's own counts (summaryCounts); nothing is recomputed, and nothing here recommends a purchase.
 */
export function WhatNext({ result, onPrint }: { result: CheckResult; onPrint?: () => void }) {
  const counts = summaryCounts(result.summary);
  // Prints this report, or saves it as PDF, through the browser. Offered only when the caller can print it.
  const printButton = onPrint ? (
    <Button onClick={onPrint} data-testid="print-report-button" title={t("Opens the browser's print dialog, where the report can be printed or saved as a PDF file")}>
      {t(PRINT_REPORT_LABEL)}
    </Button>
  ) : null;
  // A report with no evaluated rule has no reading to give, but it can still be printed.
  if (counts.total === 0) return printButton ? <div className="flex flex-wrap gap-3" data-testid="result-actions">{printButton}</div> : null;
  // Offered only when the engine supports a figure; the section itself says why when it does not.
  const hasMax = result.max_compliant?.status === "SUPPORTED";
  let meaning: string;
  if (counts.fail > 0) {
    meaning = tf(counts.total === 1 ? "This idea goes over {fail} of the {total} limit you confirmed." : "This idea goes over {fail} of the {total} limits you confirmed.", { fail: counts.fail, total: counts.total });
    if (counts.unknown > 0) meaning += ` ${tf(counts.unknown === 1 ? "{n} other limit cannot be decided with the data held." : "{n} other limits cannot be decided with the data held.", { n: counts.unknown })}`;
  } else if (counts.unknown > 0) {
    meaning = tf(
      counts.unknown === 1
        ? "No confirmed limit is shown to be broken, but {n} limit cannot be decided with the data held. A missing figure is never counted as zero."
        : "No confirmed limit is shown to be broken, but {n} limits cannot be decided with the data held. A missing figure is never counted as zero.",
      { n: counts.unknown },
    );
  } else {
    meaning =
      counts.total === 1
        ? t("The limit you confirmed is respected by this idea, on the data held. That says nothing about whether the investment itself is a good one.")
        : tf("All {total} limits you confirmed are respected by this idea, on the data held. That says nothing about whether the investment itself is a good one.", { total: counts.total });
  }
  return (
    <section aria-labelledby="what-next-title" className="rounded-xl border border-line bg-surface p-5" data-testid="what-next">
      <h2 id="what-next-title" className="text-lg font-semibold text-ink">
        {t("What this means and what you can do next")}
      </h2>
      <p className="mt-1 max-w-prose text-ink" data-testid="what-next-meaning">
        {meaning} {t("This is a check against your own limits, not advice.")}
      </p>
      <ul className="mt-3 list-disc space-y-1 pl-5 text-ink-muted">
        <li>{t("Change the investment or the share it would have, then check again.")}</li>
        {counts.unknown > 0 ? <li>{t("See which data is missing and why it leaves a limit undecided.")}</li> : null}
        <li>{t("Read the evidence behind each figure, or dispute a figure or a limit you disagree with.")}</li>
      </ul>
      <div className="mt-4 flex flex-wrap gap-3" data-testid="result-actions">
        <LinkButton href={stageHref("purchase")} variant="primary">
          {t("Modify my idea")}
        </LinkButton>
        {hasMax ? (
          <LinkButton href="#report-max" onClick={(event) => { event.preventDefault(); goToSection("report-max"); }}>
            {t("Largest share that fits my limits")}
          </LinkButton>
        ) : null}
        <LinkButton href="#report-coverage" onClick={(event) => { event.preventDefault(); goToSection("report-coverage"); }}>
          {t("Sources and missing data")}
        </LinkButton>
        <LinkButton href={stageHref("challenge")}>{t("Review or dispute this result")}</LinkButton>
        {printButton}
      </div>
    </section>
  );
}
