import type { Portfolio } from "@/lib/contracts";
import { formatDate, formatFraction } from "@/lib/format";
import { portfolioRows, type InstrumentRegistry } from "@/lib/portfolio";
import { t } from "@/lib/i18n";

/**
 * The holdings of a portfolio as a plain table: name, type and weight, in the
 * order the service lists them, then cash. Weights arrive as fractions and are
 * shown as percentages; nothing is added up here.
 */
export function PortfolioTable({ portfolio, instruments, personaName }: { portfolio: Portfolio; instruments: InstrumentRegistry; personaName: string }) {
  const rows = portfolioRows(portfolio, instruments);
  return (
    <table className="w-full border-collapse text-left" data-testid="portfolio-table">
      <caption className="pb-3 text-left text-sm text-ink-muted">
        {personaName}{t("&rsquo;s fictional portfolio. Each weight is a share of the whole portfolio in")} {portfolio.base_currency}{t(", valued on")}{" "}
        <span className="tabular">{formatDate(portfolio.valuation_date)}</span>.
      </caption>
      <thead>
        <tr className="border-b-2 border-line-strong text-sm text-ink-muted">
          <th scope="col" className="py-2 pr-3 font-semibold">
            {t("Holding")}</th>
          <th scope="col" className="hidden py-2 pr-3 font-semibold sm:table-cell">
            {t("Type")}</th>
          <th scope="col" className="py-2 text-right font-semibold">
            {t("Weight")}</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.key} className="border-b border-line" data-testid="portfolio-row">
            <th scope="row" className="py-2.5 pr-3 font-normal">
              <span className="block font-semibold text-ink">{row.name}</span>
              <span className="block text-sm text-ink-muted">
                {row.instrument_id ? <span className="tabular">{row.instrument_id}</span> : t("Uninvested")}
                <span className="sm:hidden"> · {t(row.kind)}</span>
              </span>
            </th>
            <td className="hidden py-2.5 pr-3 text-ink-muted sm:table-cell">{t(row.kind)}</td>
            <td className="tabular py-2.5 text-right text-lg font-semibold text-ink">{formatFraction(row.weight)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
