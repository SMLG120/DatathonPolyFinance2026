import { Badge } from "@/components/ui/Badge";
import type { Feasibility, PurchaseRequest } from "@/lib/contracts";
import { formatChange, formatFraction } from "@/lib/format";

/**
 * What the purchase does to the position bought and to cash, exactly as the
 * service reports it (`CheckResult.feasibility`). Every figure in this table
 * is the service's: nothing is subtracted or added here.
 */
export function FeasibilityTable({ feasibility, purchase, instrumentName }: { feasibility: Feasibility; purchase: PurchaseRequest; instrumentName: string }) {
  return (
    <table className="w-full border-collapse text-left" data-testid="feasibility-table">
      <caption className="pb-3 text-left text-sm text-ink-muted">
        Direct weights as a share of the whole portfolio, as computed by the service. Only the purchased position and cash change; every other
        position is unchanged.
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
        </tr>
      </thead>
      <tbody>
        <tr className="border-b border-line bg-accent-soft" data-row="purchase">
          <th scope="row" className="py-2.5 pl-2 pr-2 font-normal">
            <span className="block font-semibold text-ink">{instrumentName}</span>
            <span className="flex flex-wrap items-center gap-x-2 text-sm text-ink-muted">
              <span className="tabular">{purchase.instrument_id}</span>
              <Badge tone="accent" className="py-0 leading-5">
                Purchased
              </Badge>
              <span className="tabular" data-testid="additional-purchase">
                {formatChange(feasibility.additional_purchase)}
              </span>
            </span>
          </th>
          <td className="tabular py-2.5 pl-2 text-right text-ink">{formatFraction(feasibility.starting_direct_weight)}</td>
          <td className="tabular py-2.5 pl-2 pr-2 text-right text-lg font-bold text-ink">{formatFraction(feasibility.target_direct_weight)}</td>
        </tr>
        <tr className="border-b border-line bg-accent-soft" data-row="cash">
          <th scope="row" className="py-2.5 pl-2 pr-2 font-normal">
            <span className="block font-semibold text-ink">Cash</span>
            <span className="block text-sm text-ink-muted">Funds the purchase</span>
          </th>
          <td className="tabular py-2.5 pl-2 text-right text-ink">{formatFraction(feasibility.cash_before)}</td>
          <td className="tabular py-2.5 pl-2 pr-2 text-right text-lg font-bold text-ink" data-testid="cash-after">
            {formatFraction(feasibility.cash_after)}
          </td>
        </tr>
      </tbody>
    </table>
  );
}
