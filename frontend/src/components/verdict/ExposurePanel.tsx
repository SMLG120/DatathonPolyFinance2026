"use client";

import { EvidenceButton } from "@/components/evidence/EvidenceProvider";
import type { CheckResult, ExposureBreakdown, ExposureResult, FundPath } from "@/lib/contracts";
import { EPS, formatDate, formatFraction } from "@/lib/format";
import { limitNoun } from "@/lib/rules";
import { ExposureChart, type ExposureBar } from "./ExposureChart";

function toBar(key: string, label: string, breakdown: ExposureBreakdown): ExposureBar {
  return {
    key,
    label,
    direct: breakdown.direct,
    indirect: breakdown.indirect_known,
    possibleExtra: breakdown.possible_extra,
    lower: breakdown.lower,
    upper: breakdown.upper,
  };
}

/** Contract shape -> the chart's view model. The only place that knows both. */
export function toExposureBars(exposure: ExposureResult): ExposureBar[] {
  const bars = [toBar("starting", "Before the purchase", exposure.starting)];
  if (exposure.proposed) bars.push(toBar("proposed", "After the purchase", exposure.proposed));
  return bars;
}

function FundPathLine({ path }: { path: FundPath }) {
  if (path.subject_weight_in_fund === null) {
    return (
      <li className="tabular" data-testid="fund-path" data-measured="false">
        <span className="font-semibold">{path.fund_id}</span>: {formatFraction(path.fund_weight)} of the portfolio. No holdings file is available, so
        nothing is measured through this fund and up to {formatFraction(path.possible_extra)} is possible.
      </li>
    );
  }
  return (
    <li className="tabular" data-testid="fund-path" data-measured="true">
      <span className="font-semibold">{path.fund_id}</span>: {formatFraction(path.fund_weight)} of the portfolio ×{" "}
      {formatFraction(path.subject_weight_in_fund, { decimals: 2 })} of the fund = {formatFraction(path.known_exposure, { decimals: 2 })}. The
      holdings file covers {formatFraction(path.coverage)} of the fund
      {path.possible_extra > EPS ? `, so up to ${formatFraction(path.possible_extra, { decimals: 2 })} more is possible but not measured` : ""}
      {path.holdings_date ? `; holdings dated ${formatDate(path.holdings_date)}` : ""}.
    </li>
  );
}

/** One measured exposure: the chart, how the through-fund part is built, and its evidence. */
export function ExposurePanel({ result, exposure }: { result: CheckResult; exposure: ExposureResult }) {
  const ruleResult = result.rule_results.find((r) => r.rule_id === exposure.rule_id);
  const bars = toExposureBars(exposure);
  const noun = ruleResult ? limitNoun(ruleResult.rule_type).toLowerCase() : "limit";
  const limitLabel = `${result.is_draft_preview ? "Draft" : "Confirmed"} ${noun}`;
  const paths = (exposure.proposed ?? exposure.starting).paths;

  return (
    <div className="space-y-4" data-testid="exposure-panel">
      <ExposureChart subject={exposure.subject_label} bars={bars} limit={exposure.limit} limitLabel={limitLabel} />
      <p className="text-sm text-ink-muted">
        This shows one subject. Whether the rule is respected is decided on the rule itself, in the section on each confirmed rule above — for a
        limit on any single company, that is the company with the largest exposure, which can be a different one before and after the purchase.
      </p>
      {paths.length > 0 ? (
        <div>
          <h3 className="font-semibold text-ink">How the through-fund part is built{exposure.proposed ? " (after the purchase)" : ""}</h3>
          <ul className="mt-1 list-disc space-y-1 pl-5 text-ink">
            {paths.map((path) => (
              <FundPathLine key={path.fund_id} path={path} />
            ))}
          </ul>
          <p className="mt-2 text-sm text-ink-muted">
            Reported holdings are used as published and never rescaled to 100%. The part of a fund with no reported holdings is shown as a possible
            range, not as zero.
          </p>
        </div>
      ) : null}
      <EvidenceButton label={`${exposure.subject_label} exposure`} result={result} evidenceIds={exposure.evidence_ids} />
    </div>
  );
}
