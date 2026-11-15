import type { Portfolio } from "@/lib/contracts";
import { formatDate, formatFraction } from "@/lib/format";
import { portfolioRows, totalWeight } from "@/lib/portfolio";

/**
 * The holdings of a portfolio as a plain table: name, type and weight.
 * Weights arrive as fractions and are shown as percentages.
 */
export function PortfolioTable({ portfolio, personaName }: { portfolio: Portfolio; personaName: string }) {
  const rows = portfolioRows(portfolio);
  return (
    <table className="w-full border-collapse text-left" data-testid="portfolio-table">
      <caption className="pb-3 text-left text-sm text-ink-muted">
        {personaName}&rsquo;s fictional portfolio. Each weight is a share of the whole portfolio in {portfolio.reporting_currency}, valued on{" "}
        <span className="tabular">{formatDate(portfolio.valuation_date)}</span>.
      </caption>
      <thead>
        <tr className="border-b-2 border-line-strong text-sm text-ink-muted">
          <th scope="col" className="py-2 pr-3 font-semibold">
            Holding
          </th>
          <th scope="col" className="hidden py-2 pr-3 font-semibold sm:table-cell">
            Type
          </th>
          <th scope="col" className="py-2 text-right font-semibold">
            Weight
          </th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.key} className="border-b border-line">
            <th scope="row" className="py-2.5 pr-3 font-normal">
              <span className="block font-semibold text-ink">{row.name}</span>
              <span className="block text-sm text-ink-muted">
                {row.instrument_id ? <span className="tabular">{row.instrument_id}</span> : "Uninvested"}
                <span className="sm:hidden"> · {row.kind}</span>
              </span>
            </th>
            <td className="hidden py-2.5 pr-3 text-ink-muted sm:table-cell">{row.kind}</td>
            <td className="tabular py-2.5 text-right text-lg font-semibold text-ink">{formatFraction(row.weight)}</td>
          </tr>
        ))}
      </tbody>
      <tfoot>
        <tr>
          <th scope="row" className="py-2.5 pr-3 font-semibold text-ink">
            Total
          </th>
          <td className="hidden sm:table-cell" />
          <td className="tabular py-2.5 text-right text-lg font-bold text-ink">{formatFraction(totalWeight(portfolio))}</td>
        </tr>
      </tfoot>
    </table>
  );
}
