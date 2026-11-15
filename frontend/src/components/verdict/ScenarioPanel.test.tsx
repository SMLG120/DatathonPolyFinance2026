import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { CheckResult, ScenarioResult } from "@/lib/contracts";
import { formatDate, formatReturn } from "@/lib/format";
import { probe, recorded } from "@/test/probes";
import { renderWithApp } from "@/test/render";
import { ScenarioPanel } from "./ScenarioPanel";

function scenarioOf(result: CheckResult): ScenarioResult {
  if (!result.scenario) throw new Error("This result has no replay.");
  return result.scenario;
}

function renderPanel(result: CheckResult = recorded.robertResult()) {
  const scenario = scenarioOf(result);
  renderWithApp(<ScenarioPanel result={result} scenario={scenario} />);
  return scenario;
}

const cells = (testId: string) => within(screen.getByTestId(testId)).getAllByRole("cell").map((cell) => cell.textContent);

describe("ScenarioPanel, on Robert's recorded replay", () => {
  it("says it is a replay of the past and not a forecast, with the recorded label and period", () => {
    const scenario = renderPanel();
    const note = screen.getByTestId("scenario-note");
    expect(note).toHaveTextContent(scenario.label);
    expect(note).toHaveTextContent("bought once on 31 Dec 2021 and held to 30 Dec 2022");
    expect(note).toHaveTextContent("It predicts nothing and guarantees nothing.");
    expect(screen.getByTestId("scenario-panel")).toHaveTextContent("A replay of the past — not a forecast");
    expect(screen.getByTestId("scenario-panel")).toHaveAttribute("data-scenario-status", "COMPUTED");
  });

  it("shows the measures before and after the purchase as sent", () => {
    renderPanel();
    expect(cells("scenario-terminal")).toEqual(["−6.50%", "−15.25%"]);
    expect(cells("scenario-drawdown")).toEqual(["−9.85%", "−22.35%"]);
    expect(cells("scenario-drawdown-date")).toEqual(["30 Jun 2022", "30 Jun 2022"]);
    expect(screen.getByTestId("scenario-target-return")).toHaveTextContent("NVDA alone over the same period: −35.00%, in Canadian dollars.");
    expect(screen.queryByTestId("scenario-insufficient")).toBeNull();
    expect(screen.queryByTestId("scenario-missing")).toBeNull();
  });

  it("lists every instrument in the order sent, with its return and the dates of the prices and exchange rates used", () => {
    const scenario = renderPanel();
    const table = screen.getByTestId("instrument-returns");
    expect(within(table).getAllByRole("columnheader").map((header) => header.textContent)).toEqual([
      "Instrument",
      "Return in CAD",
      "Dates of the prices and exchange rates used",
    ]);
    const rows = within(table).getAllByTestId("instrument-return");
    expect(rows.map((row) => row.getAttribute("data-instrument-id"))).toEqual(scenario.instrument_returns.map((item) => item.instrument_id));
    expect(rows).toHaveLength(6);
    for (const [index, item] of scenario.instrument_returns.entries()) {
      const row = rows[index] as HTMLElement;
      expect(within(row).getByRole("rowheader")).toHaveTextContent(`${item.instrument_id} (${item.currency})`);
      expect(within(row).getAllByRole("cell")[0]).toHaveTextContent(formatReturn(item.return_cad));
      expect(within(row).getByTestId("price-dates")).toHaveTextContent(`Prices: ${formatDate(item.base_price_date)} (same day) and ${formatDate(item.end_price_date)} (same day)`);
    }
    const row = (id: string) => rows.find((candidate) => candidate.getAttribute("data-instrument-id") === id) as HTMLElement;
    expect(within(row("NVDA")).getAllByRole("cell")[0]).toHaveTextContent("−35.00%");
    expect(within(row("JNJ")).getAllByRole("cell")[0]).toHaveTextContent("+4.00%");
    // A price in US dollars names the exchange rates it was converted with; a Canadian one needs none.
    expect(within(row("SPY")).getByTestId("fx-dates")).toHaveTextContent("Exchange rates: 31 Dec 2021 (same day) and 30 Dec 2022 (same day)");
    expect(within(row("XBB.TO")).getByTestId("fx-dates")).toHaveTextContent("Exchange rates: none needed");
  });

  it("lists the assumptions of the replay as sent", () => {
    const scenario = renderPanel();
    const items = within(screen.getByTestId("scenario-assumptions")).getAllByRole("listitem");
    expect(items.map((item) => item.textContent)).toEqual(scenario.assumptions);
    expect(items).toHaveLength(7);
  });

  it("offers the evidence of the replay", () => {
    renderPanel();
    expect(screen.getByRole("button", { name: "Evidence for the historical replay" })).toBeInTheDocument();
  });
});

describe("ScenarioPanel, when the replay could not be computed", () => {
  it("names what is missing and shows no figure in place of a measure", () => {
    renderPanel(probe.withoutReplayHistory(["NVDA"]));
    expect(screen.getByTestId("scenario-panel")).toHaveAttribute("data-scenario-status", "INSUFFICIENT_HISTORY");
    expect(screen.getByTestId("scenario-insufficient")).toHaveTextContent("No usable price history for: NVDA. No figure is shown in its place.");
    expect(cells("scenario-terminal")).toEqual(["Not computed", "Not computed"]);
    expect(cells("scenario-drawdown")).toEqual(["Not computed", "Not computed"]);
    expect(cells("scenario-drawdown-date")).toEqual(["Not computed", "Not computed"]);
    expect(screen.queryByTestId("scenario-target-return")).toBeNull();
    expect(screen.getByTestId("scenario-table")).not.toHaveTextContent("%");
  });

  it("says a price or a rate is missing when no instrument is named", () => {
    renderPanel(probe.withoutReplayHistory([]));
    expect(screen.getByTestId("scenario-insufficient")).toHaveTextContent("A price or an exchange rate needed for the period is missing. No figure is shown in its place.");
  });
});
