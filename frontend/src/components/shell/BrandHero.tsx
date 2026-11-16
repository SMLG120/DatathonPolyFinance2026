"use client";

import { useId } from "react";
import { LinkButton } from "@/components/ui/Button";
import { ArrowRightIcon } from "@/components/ui/icons";
import { goToSection } from "@/components/verdict/VerdictSummary";
import { stageHref } from "@/state/stage";
import { useWorkflow } from "@/state/workflow";

export const BRAND_NAME = "ETHOS";
export const BRAND_HEADLINE = ["Invest with conviction.", "Not contradiction."] as const;
export const BRAND_SUBTITLE =
  "Your AI-powered investment decision investigator. Uncover hidden exposure, verify your financial rules, and understand every trade before you commit.";
export const BRAND_TAGLINE = "ETHOS — The AI Agent That Challenges Your Investments Before the Market Does.";

/** The report section that holds the 2D exposure chart and the 3D exposure explorer (see verdict/Report.tsx). */
const EXPOSURE_SECTION = "report-exposure";

/**
 * Opens the exposure section once the verdict stage is on screen.
 *
 * The link's own hash changes the stage; the stage then scrolls to the top and
 * focuses its heading (see App.tsx). The section is opened one tick after it
 * first exists, so that this runs after that reset and not before it. A report
 * with no exposure section (a check that did not run) leaves the reader on the
 * verdict stage, which says what happened.
 */
function openExposureSectionWhenReady(): void {
  let tries = 0;
  const attempt = (found: boolean) => {
    const present = document.getElementById(EXPOSURE_SECTION) !== null;
    if (present && found) {
      // Opens the section and moves focus to its summary; the explorer is below the flat chart, so it is brought into view itself.
      goToSection(EXPOSURE_SECTION);
      document.querySelector(`#${EXPOSURE_SECTION} [data-testid="exposure-explorer"]`)?.scrollIntoView?.({ block: "start" });
      return;
    }
    tries += 1;
    if (tries < 40) window.setTimeout(() => attempt(present), 50);
  };
  window.setTimeout(() => attempt(false), 0);
}

/**
 * The brand message at the top of the first screen.
 *
 * The headline is a paragraph, not a heading: each stage keeps exactly one h1
 * (see StageFrame), which is what receives focus when the stage changes.
 *
 * Both links go to stages that already exist. The 3D exposure explorer is
 * drawn from a result, never from invented data: with a report in this
 * session, the second link opens it in that report; with none, it leads to
 * the purchase step, where the explorer appears under the preview of an
 * entered purchase, and says so.
 */
export function BrandHero() {
  const { derived } = useWorkflow();
  const noteId = useId();
  const hasReport = derived.latestReport !== null;

  return (
    <section aria-label={BRAND_NAME} data-testid="brand-hero" className="space-y-5 border-b border-line pb-8">
      <p className="text-4xl font-bold leading-tight tracking-tight text-ink sm:text-5xl" data-testid="brand-headline">
        <span className="block">{BRAND_HEADLINE[0]}</span>
        <span className="block text-accent-strong">{BRAND_HEADLINE[1]}</span>
      </p>
      <p className="max-w-prose text-lg text-ink-muted" data-testid="brand-subtitle">
        {BRAND_SUBTITLE}
      </p>
      <div className="flex flex-wrap gap-3">
        <LinkButton href={stageHref("purchase")} variant="primary" iconAfter={<ArrowRightIcon />} data-testid="brand-cta-primary">
          Analyze My Portfolio
        </LinkButton>
        <LinkButton
          href={stageHref(hasReport ? "verdict" : "purchase")}
          onClick={hasReport ? openExposureSectionWhenReady : undefined}
          aria-describedby={noteId}
          data-testid="brand-cta-secondary"
          data-has-report={hasReport ? "true" : "false"}
        >
          Explore 3D Portfolio
        </LinkButton>
      </div>
      <p id={noteId} className="max-w-prose text-sm text-ink-muted" data-testid="brand-cta-note">
        {hasReport
          ? "Opens the 3D exposure view of the latest result in this session."
          : "The 3D exposure view is drawn from a checked purchase, and none has been checked in this session yet. This opens the purchase step: the view appears there under the preview of your purchase, and again in the result."}
      </p>
    </section>
  );
}
