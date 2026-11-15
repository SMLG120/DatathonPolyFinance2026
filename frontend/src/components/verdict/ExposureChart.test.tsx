import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { describeExposure, exposureAxis, ExposureChart, type ExposureBar } from "./ExposureChart";

const measured: ExposureBar[] = [
  { key: "starting", label: "Before the purchase", direct: 0, indirect: 0.015, possibleExtra: 0, lower: 0.015, upper: 0.015 },
  { key: "proposed", label: "After the purchase", direct: 0.25, indirect: 0.015, possibleExtra: 0, lower: 0.265, upper: 0.265 },
];

const partlyUnknown: ExposureBar[] = [
  { key: "starting", label: "Before the purchase", direct: 0, indirect: 0.034, possibleExtra: 0.15, lower: 0.034, upper: 0.184 },
  { key: "proposed", label: "After the purchase", direct: 0, indirect: 0.03895, possibleExtra: 0.15, lower: 0.03895, upper: 0.18895 },
];

describe("exposureAxis", () => {
  it("ends on a round value above the largest value and the limit", () => {
    expect(exposureAxis([0.265, 0.1])).toEqual({ max: 0.3, ticks: [0, 0.1, 0.2, 0.3] });
    expect(exposureAxis([0.18895, 0])).toEqual({ max: 0.25, ticks: [0, 0.05, 0.1, 0.15, 0.2, 0.25] });
  });

  it("never exceeds the whole portfolio and copes with nothing to draw", () => {
    expect(exposureAxis([0.99]).max).toBe(1);
    expect(exposureAxis([]).max).toBe(0.02);
    expect(exposureAxis([Number.NaN, 0.04]).max).toBe(0.05);
  });
});

describe("ExposureChart", () => {
  it("draws direct and through-fund segments and a limit marker on every bar", () => {
    render(<ExposureChart subject="NVIDIA Corporation" bars={measured} limit={0.1} />);
    const bars = screen.getAllByTestId("exposure-bar");
    expect(bars).toHaveLength(2);

    const [before, after] = bars;
    expect(before?.querySelector('[data-seg="direct"]')).toBeNull(); // nothing held directly before
    expect(before?.querySelector('[data-seg="indirect"]')).not.toBeNull();
    expect(after?.querySelector('[data-seg="direct"]')).not.toBeNull();
    expect(after?.querySelector('[data-seg="indirect"]')).not.toBeNull();

    const markers = screen.getAllByTestId("limit-marker");
    expect(markers).toHaveLength(2);
    // 10% on an axis that ends at 30%.
    expect(markers[0]?.style.left).toBe(`${(0.1 / 0.3) * 100}%`);
    expect(screen.getByText("Confirmed limit 10.0%")).toBeInTheDocument();
  });

  it("sizes segments in proportion to the axis", () => {
    render(<ExposureChart subject="NVIDIA Corporation" bars={measured} limit={0.1} />);
    const after = screen.getAllByTestId("exposure-bar")[1];
    const direct = after?.querySelector<HTMLElement>('[data-seg="direct"]');
    const indirect = after?.querySelector<HTMLElement>('[data-seg="indirect"]');
    expect(Number.parseFloat(direct?.style.width ?? "")).toBeCloseTo((0.25 / 0.3) * 100, 6);
    expect(Number.parseFloat(indirect?.style.width ?? "")).toBeCloseTo((0.015 / 0.3) * 100, 6);
  });

  it("draws exposure that cannot be measured as its own hollow segment, and says so in the legend and the table", () => {
    render(<ExposureChart subject="Holdings labelled Energy" bars={partlyUnknown} limit={0} />);
    for (const bar of screen.getAllByTestId("exposure-bar")) {
      expect(bar.querySelector('[data-seg="possible"]')).not.toBeNull();
    }
    expect(screen.getByText("Possible extra, not measured (fund holdings not reported)")).toBeInTheDocument();

    const table = screen.getByTestId("exposure-table");
    const range = within(table).getByRole("row", { name: /Possible range/ });
    expect(range).toHaveTextContent("3.4% to 18.4%");
    expect(range).toHaveTextContent("3.9% to 18.9%");
    expect(within(table).getByRole("row", { name: /Possible extra, not measured/ })).toHaveTextContent("up to 15.0%");
    // The measured total stays the lower bound: the unknown part is never added to it.
    expect(within(table).getByRole("row", { name: /Measured total/ })).toHaveTextContent("3.4%");
  });

  it("has no possible-range segment or legend entry when everything is measured", () => {
    const { container } = render(<ExposureChart subject="NVIDIA Corporation" bars={measured} limit={0.1} />);
    expect(container.querySelector('[data-seg="possible"]')).toBeNull();
    expect(screen.queryByText(/Possible extra, not measured \(/)).toBeNull();
    expect(within(screen.getByTestId("exposure-table")).getByRole("row", { name: /Possible extra, not measured/ })).toHaveTextContent("None");
  });

  it("draws no limit marker when there is no limit", () => {
    render(<ExposureChart subject="NVIDIA Corporation" bars={measured} limit={null} />);
    expect(screen.queryByTestId("limit-marker")).toBeNull();
    expect(screen.getByRole("img")).toHaveAccessibleName(/No limit is drawn\./);
  });

  it("labels a draft limit as a draft", () => {
    render(<ExposureChart subject="NVIDIA Corporation" bars={measured} limit={0.3} limitLabel="Draft limit" />);
    expect(screen.getByText("Draft limit 30.0%")).toBeInTheDocument();
  });

  it("exposes the drawing as one image whose name states every value, and repeats the values in a table", () => {
    render(<ExposureChart subject="NVIDIA Corporation" bars={measured} limit={0.1} />);
    expect(screen.getByRole("img")).toHaveAccessibleName(
      "NVIDIA Corporation exposure as a share of the portfolio. Before the purchase: 1.5% (direct 0.0%, through funds 1.5%). After the purchase: 26.5% (direct 25.0%, through funds 1.5%). Confirmed limit: 10.0%.",
    );
    const table = screen.getByTestId("exposure-table");
    expect(within(table).getAllByRole("columnheader").map((cell) => cell.textContent)).toEqual(["Before the purchase", "After the purchase"]);
    expect(within(table).getByRole("row", { name: /Direct holding/ })).toHaveTextContent("0.0%25.0%");
  });

  it("describes a range in words", () => {
    expect(describeExposure({ subject: "Energy", bars: [partlyUnknown[0] as ExposureBar], limit: 0 })).toBe(
      "Energy exposure as a share of the portfolio. Before the purchase: between 3.4% and 18.4% (direct 0.0%, through funds 3.4%, plus up to 15.0% that cannot be measured). Confirmed limit: 0.0%.",
    );
  });
});
