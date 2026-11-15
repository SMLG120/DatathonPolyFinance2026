import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { CheckResult, IssuerExposure } from "@/lib/contracts";
import { explorerFlatChart } from "@/test/exposure";
import { probe, recorded } from "@/test/probes";
import { LIVE_CONFIG, renderWithApp } from "@/test/render";
import { PurchaseExposureExplorerSlot, VerdictExposureExplorerSlot } from "./ExposureExplorerSlots";

/** The first company the engine lists: the one the explorer shows. */
function firstCompany(result: CheckResult): IssuerExposure {
  const issuer = result.exposure?.issuers[0];
  if (!issuer) throw new Error("This recorded result lists no company.");
  return issuer;
}

function cell(rowKey: string, state: "starting" | "proposed"): string {
  const found = screen.getByTestId("explorer-table").querySelector(`tr[data-row="${rowKey}"] td[data-state="${state}"]`);
  if (!found) throw new Error(`The explorer's table has no cell ${rowKey}/${state}.`);
  return found.textContent ?? "";
}

describe("exposure explorer in the verdict stage, on Robert's recorded result", () => {
  it("shows the first company the engine lists, with the engine's figures", () => {
    const result = recorded.robertResult();
    const company = firstCompany(result);
    renderWithApp(<VerdictExposureExplorerSlot result={result} />);

    const explorer = screen.getByTestId("exposure-explorer");
    expect(explorer).toHaveAttribute("data-status", "READY");
    expect(within(explorer).getByRole("heading", { level: 3 })).toHaveTextContent(`${company.name}: current and proposed exposure`);
    expect(screen.getByTestId("explorer-context")).toHaveTextContent("Confirmed policy version 1");

    // As recorded: nothing held directly before, 25% after; 1.2% through SPY; up to 0.2% not attributed.
    expect([cell("direct", "starting"), cell("direct", "proposed")]).toEqual(["0.0%", "25.0%"]);
    expect([cell("fund:SPY", "starting"), cell("fund:SPY", "proposed")]).toEqual(["1.2%", "1.2%"]);
    expect([cell("unresolved", "starting"), cell("unresolved", "proposed")]).toEqual(["up to 0.2%", "up to 0.2%"]);
    expect([cell("known", "starting"), cell("known", "proposed")]).toEqual(["1.2%", "26.2%"]);
    expect([cell("upper", "starting"), cell("upper", "proposed")]).toEqual(["1.4%", "26.4%"]);
    expect([cell("limit", "starting"), cell("limit", "proposed")]).toEqual(["10.0%", "10.0%"]);
  });

  it("reads the totals from the result instead of adding up the parts", () => {
    // Totals that no sum of the recorded parts gives.
    renderWithApp(<VerdictExposureExplorerSlot result={probe.withIssuerTotals("NVIDIA", 0.3141, 0.5926)} />);
    expect(cell("direct", "proposed")).toBe("25.0%");
    expect(cell("fund:SPY", "proposed")).toBe("1.2%");
    expect(cell("known", "proposed")).toBe("31.4%");
    expect(cell("upper", "proposed")).toBe("59.3%");
    expect(screen.getByTestId("explorer-totals")).toHaveTextContent("Proposed: between 31.4% and 59.3% of the portfolio");
    expect(within(explorerFlatChart()).getByTestId("exposure-after")).toHaveTextContent("After 31.4% to 59.3%");
  });

  it("uses the flat chart of the same company where the 3D drawing cannot be shown, and reports no error", () => {
    // A test DOM has no WebGL: the path of every browser that cannot draw the scene.
    const result = recorded.robertResult();
    const company = firstCompany(result);
    const { container } = renderWithApp(<VerdictExposureExplorerSlot result={result} />);

    const explorer = screen.getByTestId("exposure-explorer");
    expect(explorer).toHaveAttribute("data-mode", "FALLBACK");
    expect(explorer).toHaveAttribute("data-fallback-reason", "NO_WEBGL");
    expect(container.querySelector("canvas")).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByTestId("explorer-fallback")).toHaveTextContent("The 3D view is not available in this browser, so the flat chart and the table are shown instead.");

    const flat = explorerFlatChart();
    expect(flat).toHaveTextContent(`${company.name}: exposure as a share of the portfolio, flat view`);
    const rows = within(flat).getAllByTestId("exposure-row");
    expect(rows.map((row) => row.getAttribute("data-issuer-id"))).toEqual([company.issuer_id]);
    expect(within(flat).getByTestId("exposure-after")).toHaveTextContent("After 26.2% to 26.4%");
    expect(within(flat).getByTestId("exposure-before")).toHaveTextContent("Before 1.2% to 1.4%");
    expect(flat).toHaveTextContent("Confirmed limit 10.0%");
  });

  it("marks its figures as test data on the fixtures client, and not on the live service", () => {
    const fixtures = renderWithApp(<VerdictExposureExplorerSlot result={recorded.robertResult()} />);
    expect(screen.getByTestId("explorer-origin")).toHaveTextContent("Test data");
    fixtures.unmount();

    renderWithApp(<VerdictExposureExplorerSlot result={recorded.robertResult()} />, { config: LIVE_CONFIG });
    expect(screen.getByTestId("exposure-explorer")).toBeInTheDocument();
    expect(screen.queryByTestId("explorer-origin")).toBeNull();
  });

  it("opens the app's evidence drawer on the calculation of a fund's share, read from the same result", async () => {
    const user = userEvent.setup();
    const result = recorded.robertResult();
    const company = firstCompany(result);
    const record = result.evidence.find(
      (candidate) =>
        candidate.metric_id === "issuer_exposure_via_fund" &&
        candidate.subject.kind === "ISSUER" &&
        candidate.subject.id === company.issuer_id &&
        candidate.subject.via_fund_id === "SPY" &&
        candidate.subject.portfolio_state === "PROPOSED",
    );
    if (!record) throw new Error("The recording changed: a record for the share through SPY after the purchase is expected.");
    renderWithApp(<VerdictExposureExplorerSlot result={result} />);

    const part = screen.getAllByTestId("explorer-segment").find((button) => button.getAttribute("data-segment") === "proposed:FUND:SPY");
    if (!part) throw new Error("The explorer lists no part through SPY after the purchase.");
    await user.click(part);
    const open = within(screen.getByTestId("explorer-details")).getByRole("button", { name: "Open the calculation" });
    await user.click(open);

    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveAccessibleName(`Evidence: exposure to ${company.name} through SPY, after the purchase`);
    const shown = within(dialog).getAllByTestId("evidence-record");
    expect(shown.map((item) => item.getAttribute("data-evidence-id"))).toEqual([record.evidence_id]);
    expect(within(dialog).getAllByTestId("evidence-formula")[0]).toHaveTextContent(record.formula as string);

    // Closing the drawer gives focus back to the button that opened it.
    await user.click(within(dialog).getByRole("button", { name: "Close evidence" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(open).toHaveFocus();
  });

  it("says what is not known for Mateo: no limit on a single company was evaluated, and the total is a range", () => {
    const result = recorded.mateoResult();
    const company = firstCompany(result);
    renderWithApp(<VerdictExposureExplorerSlot result={result} />);
    expect(within(screen.getByTestId("exposure-explorer")).getByRole("heading", { level: 3 })).toHaveTextContent(company.name);
    expect(screen.getByTestId("explorer-limit")).toHaveTextContent("No limit is drawn: this check evaluated no rule that limits exposure to a single company.");
    expect([cell("limit", "starting"), cell("limit", "proposed")]).toEqual(["Not available", "Not available"]);
    expect(within(explorerFlatChart()).queryAllByTestId("limit-marker")).toHaveLength(0);
  });
});

describe("exposure explorer in the purchase stage", () => {
  it("renders nothing while there is no result", () => {
    const { container } = renderWithApp(<PurchaseExposureExplorerSlot result={null} />);
    expect(screen.queryByTestId("exposure-explorer")).toBeNull();
    expect(container.querySelector('[data-testid="exposure-chart"]')).toBeNull();
  });

  it("shows the explorer for a preview and marks it as a draft", () => {
    const preview = recorded.robertPreview();
    expect(preview.preview).toBe(true);
    renderWithApp(<PurchaseExposureExplorerSlot result={preview} />);
    const origin = screen.getByTestId("explorer-origin");
    expect(origin).toHaveTextContent("Test data");
    expect(origin).toHaveTextContent("Draft preview");
    expect(screen.getByTestId("explorer-context")).toHaveTextContent("Draft rules, not a confirmed policy");
    expect([cell("limit", "starting"), cell("limit", "proposed")]).toEqual(["20.0%", "20.0%"]);
    expect(explorerFlatChart()).toHaveTextContent("Draft limit 20.0%");
  });

  it("says that the exposure cannot be shown for a request the service did not evaluate, and draws nothing", () => {
    renderWithApp(<PurchaseExposureExplorerSlot result={recorded.invalidRequest()} />);
    const explorer = screen.getByTestId("exposure-explorer");
    expect(explorer).toHaveAttribute("data-status", "UNAVAILABLE");
    expect(screen.getByTestId("explorer-unavailable")).toHaveTextContent("Exposure cannot be shown");
    expect(screen.queryByTestId("exposure-chart")).toBeNull();
    expect(screen.queryByTestId("explorer-table")).toBeNull();
  });
});
