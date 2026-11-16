"use client";

import { Button } from "@/components/ui/Button";
import { ArrowRightIcon } from "@/components/ui/icons";

export const BRAND_NAME = "ETHOS";
export const BRAND_HEADLINE = ["Invest with conviction.", "Not contradiction."] as const;
export const BRAND_SUBTITLE =
  "Your AI-powered investment decision investigator. Uncover hidden exposure, verify your financial rules, and understand every trade before you commit.";
export const BRAND_TAGLINE = "ETHOS — The AI Agent That Challenges Your Investments Before the Market Does.";

/** The persona chooser on the same screen (PersonaStage's "Who would you like to try?" panel). */
export const PERSONA_CHOICE = "persona-choice";

/** Brings the persona chooser into view and moves focus to its heading, so keyboard and screen-reader users land there too. */
function startWithAProfile(): void {
  const heading = document.getElementById(`${PERSONA_CHOICE}-title`);
  if (!heading) return;
  heading.scrollIntoView?.({ behavior: "smooth", block: "start" });
  heading.focus({ preventScroll: true });
}

/**
 * The brand message at the top of the first screen.
 *
 * The headline is a paragraph, not a heading: each stage keeps exactly one h1
 * (see StageFrame), which is what receives focus when the stage changes.
 *
 * Its one call to action starts the journey where it begins: it stays on step 1
 * and moves to the persona chooser. It never jumps ahead to a later step, which
 * would skip choosing a profile and confirming limits and then send the reader
 * back. The 3D exposure view lives where it has data to draw: under the purchase
 * preview and in the result.
 */
export function BrandHero() {
  return (
    <section aria-label={BRAND_NAME} data-testid="brand-hero" className="space-y-5 border-b border-line pb-8">
      <p className="text-4xl font-bold leading-tight tracking-tight text-ink sm:text-5xl" data-testid="brand-headline">
        <span className="block">{BRAND_HEADLINE[0]}</span>
        <span className="block text-accent-strong">{BRAND_HEADLINE[1]}</span>
      </p>
      <p className="max-w-prose text-lg text-ink-muted" data-testid="brand-subtitle">
        {BRAND_SUBTITLE}
      </p>
      <Button variant="primary" iconAfter={<ArrowRightIcon className="rotate-90" />} onClick={startWithAProfile} data-testid="brand-cta-start">
        Start with a profile
      </Button>
    </section>
  );
}
