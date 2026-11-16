import { Badge } from "@/components/ui/Badge";
import type { Portfolio } from "@/lib/contracts";
import { CUSTOMIZED_LABEL, isCustomizedPortfolio } from "@/lib/customize";
import { t, tf } from "@/lib/i18n";
import type { InstrumentRegistry } from "@/lib/portfolio";
import { PortfolioTable } from "./PortfolioTable";

/** The same wording as `portfolioCheckedLabel` (lib/customize), in the reader's language. */
function checkedLabel(portfolio: Portfolio, scenario: Portfolio | null, personaName: string): string {
  if (scenario === null) return t("Fictional portfolio stored with this report");
  return isCustomizedPortfolio(portfolio, scenario) ? t(CUSTOMIZED_LABEL) : tf("{name}’s original fictional portfolio", { name: personaName });
}

export interface PortfolioCheckedProps {
  /** The portfolio stored with the job: the exact one it was checked against. */
  portfolio: Portfolio;
  /** The persona's scenario portfolio, to say whether the stored one is the original or a customized one. */
  scenarioPortfolio: Portfolio | null;
  instruments: InstrumentRegistry;
  personaName: string;
}

/**
 * The name of the portfolio a job was checked against, for a place that shows a job without its report: a
 * job that is running, failed or stopped to ask a question, or one line of a list of reports. Read from
 * the job and from nowhere else, exactly as `PortfolioChecked` does; the caller shows nothing for a job
 * stored without a portfolio.
 */
export function PortfolioUsedLabel({ portfolio, scenarioPortfolio, personaName, testId }: Omit<PortfolioCheckedProps, "instruments"> & { testId: string }) {
  const customized = isCustomizedPortfolio(portfolio, scenarioPortfolio);
  return (
    <span data-testid={testId} data-portfolio-id={portfolio.portfolio_id} data-customized={customized ? "true" : "false"}>
      <Badge tone={customized ? "accent" : "neutral"} dashed>
        {checkedLabel(portfolio, scenarioPortfolio, personaName)}
      </Badge>
    </span>
  );
}

/**
 * "Portfolio checked": the portfolio a report was made on, read from the job and from nowhere else.
 * It does not follow the customization applied now, so an earlier report keeps showing its own weights
 * after the user edits the portfolio again. Closed until asked for; its name stays visible.
 */
export function PortfolioChecked({ portfolio, scenarioPortfolio, instruments, personaName }: PortfolioCheckedProps) {
  const customized = isCustomizedPortfolio(portfolio, scenarioPortfolio);
  return (
    <details
      className="rounded-md border border-line bg-surface p-3 sm:p-4"
      data-testid="report-portfolio"
      data-portfolio-id={portfolio.portfolio_id}
      data-customized={customized ? "true" : "false"}
      data-figures="true"
    >
      <summary className="flex min-h-6 cursor-pointer flex-wrap items-center gap-x-3 gap-y-1 text-ink">
        <span className="font-semibold">{t("Portfolio checked")}</span>
        <span data-testid="report-portfolio-label">
          <Badge tone={customized ? "accent" : "neutral"} dashed>
            {checkedLabel(portfolio, scenarioPortfolio, personaName)}
          </Badge>
        </span>
      </summary>
      <div className="mt-3 space-y-2">
        <p className="text-sm text-ink-muted">
          {t("The weights this report was checked against, as the service stored them with the investigation. They do not change when the portfolio is customized or reset afterwards.")}
        </p>
        <PortfolioTable portfolio={portfolio} instruments={instruments} personaName={personaName} customized={customized} />
      </div>
    </details>
  );
}
