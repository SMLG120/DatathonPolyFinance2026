"use client";

import { VerdictExposureExplorerSlot } from "@/components/exposure3d/ExposureExplorerSlots";
import { UnknownBlock } from "@/components/ui/AsyncStates";
import type { CheckResult, Rule } from "@/lib/contracts";
import { EPS, formatFraction } from "@/lib/format";
import { ISSUER_SCOPE_ANY } from "@/lib/contracts";
import { ExposureChart } from "./ExposureChart";
import type { RuleLookup } from "./RuleResults";
import { t } from "@/lib/i18n";

/**
 * The limit the chart may draw: the threshold of an evaluated limit on ANY
 * single company. A limit on one named company, or no such rule at all, draws
 * no marker, because it would not apply to every row.
 */
export function chartLimit(result: CheckResult, lookup: RuleLookup): { limit: number; rule: Rule } | null {
  for (const ruleResult of result.rule_results) {
    if (ruleResult.rule_type !== "max_issuer_exposure") continue;
    const rule = lookup(ruleResult.rule_id);
    if (rule?.rule_type === "max_issuer_exposure" && rule.parameters.issuer_scope === ISSUER_SCOPE_ANY) return { limit: ruleResult.limit, rule };
  }
  return null;
}

/**
 * Exposure to single companies: the chart, the note on how its rows were
 * chosen, and the explanation of the part that cannot be measured.
 *
 * When the result carries no exposure rows, that is said in words. An empty
 * chart would read as "no exposure", which is a different statement.
 */
export function ExposurePanel({ result, lookup, openIssuerId = null }: { result: CheckResult; lookup: RuleLookup; openIssuerId?: string | null }) {
  const exposure = result.exposure;
  if (exposure === null || exposure.issuers.length === 0) {
    return (
      <UnknownBlock title={t("No exposure data")}>
        <p data-testid="no-exposure">
          {t("This result carries no company exposure rows, so there is nothing to draw. This is not the same as an exposure of zero: the exposure was not reported.")}</p>
      </UnknownBlock>
    );
  }
  const drawn = chartLimit(result, lookup);
  const extra = exposure.possible_extra.proposed;
  return (
    <div className="space-y-4" data-testid="exposure-panel">
      <div className="grid gap-6" data-testid="exposure-views">
        <ExposureChart
          exposure={exposure}
          limit={drawn ? drawn.limit : null}
          limitLabel={result.preview ? "Draft limit" : "Confirmed limit"}
          openIssuerId={openIssuerId}
        />
        {/* The 3D exposure explorer mounts here, beside the 2D chart. It renders nothing until it is wired in. */}
        <VerdictExposureExplorerSlot result={result} />
      </div>
      <p className="text-sm text-ink-muted" data-testid="exposure-selection-note">
        {exposure.selection_note}
      </p>
      {extra > EPS ? (
        <p className="text-ink" data-testid="possible-extra-note">
          <span className="font-semibold">{formatFraction(extra)} {t("of the portfolio")}</span> {t("is fund weight that the holdings files do not attribute to any company. It could belong to any of them, so every company&apos;s exposure is shown as a range from what is proven to what is possible. Missing holdings are never counted as zero, and reported holdings are never rescaled to 100%.")}</p>
      ) : null}
      <p className="text-sm text-ink-muted">
        {t("Whether a rule is respected is decided on the rule itself, in the list of confirmed rules above. The chart shows where the exposure comes from.")}</p>
    </div>
  );
}
