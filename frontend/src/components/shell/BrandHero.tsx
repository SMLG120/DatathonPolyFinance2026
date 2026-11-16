import { LinkButton } from "@/components/ui/Button";
import { ArrowRightIcon } from "@/components/ui/icons";
import { stageHref } from "@/state/stage";

export const BRAND_NAME = "ETHOS";
export const BRAND_HEADLINE = ["Invest with conviction.", "Not contradiction."] as const;
export const BRAND_SUBTITLE =
  "Your AI-powered investment decision investigator. Uncover hidden exposure, verify your financial rules, and understand every trade before you commit.";
export const BRAND_TAGLINE = "ETHOS — The AI Agent That Challenges Your Investments Before the Market Does.";

/**
 * The brand message at the top of the first screen.
 *
 * The headline is a paragraph, not a heading: each stage keeps exactly one h1
 * (see StageFrame), which is what receives focus when the stage changes.
 *
 * Both links go to stages that already exist. The purchase stage is where a
 * portfolio change is checked; the verdict stage is where the 3D exposure
 * explorer is shown beside the flat chart once a check has run.
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
      <div className="flex flex-wrap gap-3">
        <LinkButton href={stageHref("purchase")} variant="primary" iconAfter={<ArrowRightIcon />} data-testid="brand-cta-primary">
          Analyze My Portfolio
        </LinkButton>
        <LinkButton href={stageHref("verdict")} data-testid="brand-cta-secondary">
          Explore 3D Portfolio
        </LinkButton>
      </div>
    </section>
  );
}
