import { Badge } from "@/components/ui/Badge";
import { formatChange, formatFraction } from "@/lib/format";
import type { BeforeAfterRow } from "@/lib/portfolio";

/**
 * The portfolio before and after the purchase, side by side. The rows the
 * purchase changes are marked with the word "Changed" and their change in
 * percentage points — not by colour alone.
 */
export function BeforeAfterTable({ rows }: { rows: BeforeAfterRow[] }) {
  const totalBefore = rows.reduce((sum, row) => sum + row.before, 0);
  const totalAfter = rows.reduce((sum, row) => sum + row.after, 0);
  return (
    <table className="w-full border-collapse text-left" data-testid="before-after-table">
      <caption className="pb-3 text-left text-sm text-ink-muted">
        Direct weights as a share of the whole portfolio. Only the purchased position and cash change.
      </caption>
      <thead>
        <tr className="border-b-2 border-line-strong text-sm text-ink-muted">
          <th scope="col" className="py-2 pr-2 font-semibold">
            Holding
          </th>
          <th scope="col" className="py-2 pl-2 text-right font-semibold">
            Before
          </th>
          <th scope="col" className="py-2 pl-2 text-right font-semibold">
            After
          </th>
          <th scope="col" className="hidden py-2 pl-2 text-right font-semibold sm:table-cell">
            Change
          </th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.key} className={row.changed ? "border-b border-line bg-accent-soft" : "border-b border-line"} data-changed={row.changed ? "true" : undefined}>
            <th scope="row" className="py-2.5 pl-2 pr-2 font-normal">
              <span className="block font-semibold text-ink">{row.name}</span>
              <span className="flex flex-wrap items-center gap-x-2 text-sm text-ink-muted">
                {row.instrument_id ? <span className="tabular">{row.instrument_id}</span> : <span>Uninvested</span>}
                {row.changed ? (
                  <Badge tone="accent" className="py-0 leading-5">
                    Changed
                  </Badge>
                ) : null}
                <span className="tabular sm:hidden">{formatChange(row.after - row.before)}</span>
              </span>
            </th>
            <td className="tabular py-2.5 pl-2 text-right text-ink">{formatFraction(row.before)}</td>
            <td className={row.changed ? "tabular py-2.5 pl-2 text-right text-lg font-bold text-ink" : "tabular py-2.5 pl-2 text-right text-ink"}>
              {formatFraction(row.after)}
            </td>
            <td className="tabular hidden py-2.5 pl-2 pr-2 text-right text-ink-muted sm:table-cell">{formatChange(row.after - row.before)}</td>
          </tr>
        ))}
      </tbody>
      <tfoot>
        <tr>
          <th scope="row" className="py-2.5 pl-2 pr-2 font-semibold text-ink">
            Total
          </th>
          <td className="tabular py-2.5 pl-2 text-right font-semibold text-ink">{formatFraction(totalBefore)}</td>
          <td className="tabular py-2.5 pl-2 text-right font-semibold text-ink">{formatFraction(totalAfter)}</td>
          <td className="hidden sm:table-cell" />
        </tr>
      </tfoot>
    </table>
  );
}
