import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { Exposure } from "@/lib/contracts";
import { formatFraction, formatFractionRange } from "@/lib/format";
import { overviewChart } from "@/test/exposure";
import { probe, recorded } from "@/test/probes";
import { LIVE_CONFIG, renderWithApp } from "@/test/render";
import { ExposureChart, exposureAxis } from "./ExposureChart";
import { chartLimit, ExposurePanel } from "./ExposurePanel";
import { ruleLookup } from "./RuleResults";

function exposureOf(result: { exposure: Exposure | null }): Exposure {
  if (!result.exposure) throw new Error("This recorded result has no exposure block.");
  return result.exposure;
}

const robert = () => exposureOf(recorded.robertResult());
const mateo = () => exposureOf(recorded.mateoResult());
const row = (issuerId: string) => screen.getAllByTestId("exposure-row").find((item) => item.getAttribute("data-issuer-id") === issuerId) as HTMLElement;
const width = (element: Element | null) => (element as HTMLElement | null)?.style.width;

describe("exposureAxis", () => {
  it("ends on a round value above the largest one and starts at zero", () => {
    expect(exposureAxis([0.264, 0.1])).toEqual({ max: 0.3, ticks: [0, 0.1, 0.2, 0.3] });
    expect(exposureAxis([0.014])).toEqual({ max: 0.02, ticks: [0, 0.005, 0.01, 0.015, 0.02] });
    expect(exposureAxis([]).max).toBeGreaterThan(0);
  });
});

describe("ExposureChart, on Robert's recorded exposure", () => {
  it("lists every company the engine sent, in the engine's order, with its range after and before the purchase as text", () => {
    const exposure = robert();
    renderWithApp(<ExposureChart exposure={exposure} limit={0.1} />);
    const rows = screen.getAllByTestId("exposure-row");
    expect(rows.map((item) => item.getAttribute("data-issuer-id"))).toEqual(exposure.issuers.map((issuer) => issuer.issuer_id));
    for (const issuer of exposure.issuers) {
      const item = row(issuer.issuer_id);
      expect(item).toHaveTextContent(issuer.name);
      expect(within(item).getByTestId("exposure-after")).toHaveTextContent(`After ${formatFractionRange(issuer.proposed.lower, issuer.proposed.upper)}`);
      expect(within(item).getByTestId("exposure-before")).toHaveTextContent(`Before ${formatFractionRange(issuer.starting.lower, issuer.starting.upper)}`);
    }
    expect(within(row("NVIDIA")).getByTestId("exposure-after")).toHaveTextContent("After 26.2% to 26.4%");
    expect(within(row("NVIDIA")).getByTestId("exposure-before")).toHaveTextContent("Before 1.2% to 1.4%");
  });

  it("draws the direct holding, one segment per fund and the part that cannot be measured, each sized from its own field", () => {
    const exposure = robert();
    renderWithApp(<ExposureChart exposure={exposure} limit={0.1} />);
    const bars = row("NVIDIA").querySelectorAll(".byb-bar");
    expect(bars).toHaveLength(2);
    const [after, before] = [bars[0] as Element, bars[1] as Element];
    // Axis 0 to 30%: 25.0% direct, 1.2% through SPY, 0.2% not attributed.
    expect(width(after.querySelector('[data-seg="direct"]'))).toBe(`${(0.25 / 0.3) * 100}%`);
    expect(width(after.querySelector('[data-seg="indirect"][data-fund="SPY"]'))).toBe(`${(0.012 / 0.3) * 100}%`);
    expect(width(after.querySelector('[data-seg="possible"]'))).toBe(`${(exposure.possible_extra.proposed / 0.3) * 100}%`);
    // Before the purchase nothing is held directly: no direct segment at all, not a zero-width one.
    expect(before.querySelector('[data-seg="direct"]')).toBeNull();
    expect(before.querySelector('[data-seg="indirect"][data-fund="SPY"]')).not.toBeNull();
    expect(before).toHaveAttribute("data-size", "thin");
  });

  it("marks the limit on every bar and writes its value", () => {
    renderWithApp(<ExposureChart exposure={robert()} limit={0.1} />);
    const markers = screen.getAllByTestId("limit-marker");
    expect(markers).toHaveLength(robert().issuers.length * 2);
    for (const marker of markers) expect(marker.style.left).toBe(`${(0.1 / 0.3) * 100}%`);
    expect(screen.getByTestId("exposure-chart")).toHaveTextContent("Confirmed limit 10.0%");
  });

  it("draws no limit marker when there is no limit, and labels a draft limit as a draft", () => {
    const { unmount } = renderWithApp(<ExposureChart exposure={robert()} limit={null} />);
    expect(screen.queryAllByTestId("limit-marker")).toHaveLength(0);
    expect(screen.getByTestId("exposure-chart")).not.toHaveTextContent("Confirmed limit");
    unmount();
    renderWithApp(<ExposureChart exposure={robert()} limit={0.2} limitLabel="Draft limit" />);
    expect(screen.getByTestId("exposure-chart")).toHaveTextContent("Draft limit 20.0%");
  });

  it("does not depend on hover: no segment carries a title, and the bars are decoration beside the same numbers as text", () => {
    renderWithApp(<ExposureChart exposure={robert()} limit={0.1} />);
    const chart = screen.getByTestId("exposure-chart");
    expect(chart.querySelectorAll("[title]")).toHaveLength(0);
    for (const bar of chart.querySelectorAll("ul[data-testid='exposure-rows'] .byb-bar")) expect(bar).toHaveAttribute("aria-hidden", "true");
  });

  it("puts every segment's value in a table inside a native disclosure, one per company", () => {
    const exposure = robert();
    renderWithApp(<ExposureChart exposure={exposure} limit={0.1} openIssuerId="NVIDIA" />);
    for (const issuer of exposure.issuers) {
      const details = row(issuer.issuer_id).querySelector("details") as HTMLDetailsElement;
      expect(details).not.toBeNull();
      // A <summary> is focusable and toggles with Enter, Space, click and tap in every browser.
      expect(details.querySelector("summary")).not.toBeNull();
      expect(details.open).toBe(issuer.issuer_id === "NVIDIA");
    }
    const table = within(row("NVIDIA")).getByTestId("exposure-breakdown");
    const cells = (key: string) => [...(table.querySelector(`tr[data-row="${key}"]`)?.querySelectorAll("td") ?? [])].map((cell) => cell.textContent);
    expect(cells("direct")).toEqual(["0.00%", "25.00%"]);
    expect(cells("fund-SPY")).toEqual(["1.20%", "1.20%"]);
    expect(cells("lower")).toEqual(["1.20%", "26.20%"]);
    expect(cells("possible")).toEqual(["up to 0.20%", "up to 0.20%"]);
    expect(cells("range")).toEqual(["1.20% to 1.40%", "26.20% to 26.40%"]);
    expect(cells("limit")).toEqual(["10.00%", "10.00%"]);
  });

  it("shows the engine's proven total and range, not a sum of the parts it draws", () => {
    // Totals that no sum of the parts gives.
    renderWithApp(<ExposureChart exposure={exposureOf(probe.withIssuerTotals("NVIDIA", 0.111, 0.222))} limit={null} openIssuerId="NVIDIA" />);
    expect(within(row("NVIDIA")).getByTestId("exposure-after")).toHaveTextContent("After 11.1% to 22.2%");
    const table = within(row("NVIDIA")).getByTestId("exposure-breakdown");
    expect(table.querySelector('tr[data-row="lower"]')?.querySelectorAll("td")[1]).toHaveTextContent("11.10%");
    expect(table.querySelector('tr[data-row="range"]')?.querySelectorAll("td")[1]).toHaveTextContent("11.10% to 22.20%");
  });
});

describe("ExposureChart, on Mateo's recorded exposure", () => {
  it("draws the large part that cannot be measured as its own hollow segment and names it in the legend", () => {
    const exposure = mateo();
    renderWithApp(<ExposureChart exposure={exposure} limit={null} />);
    const after = row("MICROSOFT").querySelector(".byb-bar") as Element;
    const axis = exposureAxis(exposure.issuers.flatMap((issuer) => [issuer.starting.upper, issuer.proposed.upper]));
    expect(width(after.querySelector('[data-seg="possible"]'))).toBe(`${(exposure.possible_extra.proposed / axis.max) * 100}%`);
    expect(within(screen.getByRole("list", { name: "Legend" })).getByText(/Possible extra, not measured/)).toBeInTheDocument();
    expect(within(row("MICROSOFT")).getByTestId("exposure-after")).toHaveTextContent(`After ${formatFractionRange(0.059, 0.213)}`);
  });

  it("says a fund is not listed for a state rather than showing a zero", () => {
    renderWithApp(<ExposureChart exposure={mateo()} limit={null} openIssuerId="MICROSOFT" />);
    const table = within(row("MICROSOFT")).getByTestId("exposure-breakdown");
    const cells = [...(table.querySelector('tr[data-row="fund-SPY"]')?.querySelectorAll("td") ?? [])].map((cell) => cell.textContent);
    expect(cells).toEqual(["Not listed", formatFraction(0.009, { decimals: 2 })]);
  });
});

describe("ExposurePanel", () => {
  it("draws the confirmed limit on any single company from the rule result, and no limit when no such rule was evaluated", () => {
    const robertResult = recorded.robertResult();
    expect(chartLimit(robertResult, ruleLookup(recorded.robertPolicyV1()))?.limit).toBe(0.1);
    // Mateo's rules are exclusions: no limit applies to every company.
    expect(chartLimit(recorded.mateoResult(), ruleLookup(null))).toBeNull();
    // Without the policy the scope of the rule is not known, so nothing is drawn.
    expect(chartLimit(robertResult, ruleLookup(null))).toBeNull();
  });

  it("shows the chart, the engine's note on how the rows were chosen and what the unattributed fund weight means", () => {
    const result = recorded.robertResult();
    renderWithApp(<ExposurePanel result={result} lookup={ruleLookup(recorded.robertPolicyV1())} openIssuerId="NVIDIA" />);
    expect(overviewChart()).toHaveTextContent("Confirmed limit 10.0%");
    expect(screen.getByTestId("exposure-selection-note")).toHaveTextContent(result.exposure?.selection_note as string);
    expect(screen.getByTestId("possible-extra-note")).toHaveTextContent("0.2% of the portfolio");
    expect(screen.getByTestId("possible-extra-note")).toHaveTextContent("never counted as zero");
  });

  it("labels the limit of a preview as a draft", () => {
    const preview = recorded.robertPreview();
    renderWithApp(<ExposurePanel result={preview} lookup={ruleLookup(null, recorded.robertPreviewRequest().draft_rules ?? [])} />);
    expect(overviewChart()).toHaveTextContent("Draft limit 20.0%");
  });

  it("says “No exposure data” when the result has no exposure block (the recorded request that was not evaluated)", () => {
    const result = recorded.invalidRequest();
    expect(result.exposure).toBeNull();
    renderWithApp(<ExposurePanel result={result} lookup={ruleLookup(null)} />);
    expect(screen.getByText("No exposure data")).toBeInTheDocument();
    expect(screen.getByTestId("no-exposure")).toHaveTextContent("not the same as an exposure of zero");
    expect(screen.queryByTestId("exposure-chart")).toBeNull();
    expect(screen.queryByTestId("exposure-explorer")).toBeNull();
  });

  it.each(["null", "empty"] as const)("says “No exposure data” instead of drawing an empty chart when exposure is %s", (kind) => {
    renderWithApp(<ExposurePanel result={probe.withoutExposure(kind)} lookup={ruleLookup(recorded.robertPolicyV1())} />);
    expect(screen.getByText("No exposure data")).toBeInTheDocument();
    expect(screen.queryByTestId("exposure-chart")).toBeNull();
    expect(screen.queryAllByTestId("exposure-row")).toHaveLength(0);
    expect(screen.queryByTestId("exposure-explorer")).toBeNull();
  });

  it("keeps the chart of every company first and mounts the explorer of one company beside it", () => {
    const result = recorded.robertResult();
    renderWithApp(<ExposurePanel result={result} lookup={ruleLookup(recorded.robertPolicyV1())} />, { config: LIVE_CONFIG });
    const views = screen.getByTestId("exposure-views");
    expect(views.children).toHaveLength(2);
    expect(views.firstElementChild).toBe(overviewChart());
    expect(views.lastElementChild).toBe(screen.getByTestId("exposure-explorer"));
    // The chart of every company is unchanged by the explorer: all the engine's rows, in its order.
    expect(within(overviewChart()).getAllByTestId("exposure-row").map((item) => item.getAttribute("data-issuer-id"))).toEqual(
      exposureOf(result).issuers.map((issuer) => issuer.issuer_id),
    );
    expect(overviewChart()).toHaveTextContent("Exposure to single companies, as a share of the portfolio");
  });
});
