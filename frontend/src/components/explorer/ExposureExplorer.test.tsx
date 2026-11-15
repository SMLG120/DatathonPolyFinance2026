import { readFileSync } from "node:fs";
import path from "node:path";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { formatDate, formatFraction } from "@/lib/format";
import { MIN_3D_VIEWPORT_WIDTH } from "./capability";
import type { CheckResult } from "./contract-types";
import { ExposureExplorer } from "./ExposureExplorer";
import { buildExplorerModel, type ExplorerReady } from "./model";

/**
 * Expected text is always built from the contract fixture being shown (through
 * the same formatter the application uses), never typed here. jsdom has no
 * WebGL, so these tests exercise the fallback path, which is the path every
 * reader without WebGL gets.
 */
const FIXTURES = path.resolve(import.meta.dirname, "../../../../contracts/fixtures/api");

function fixtureResult(name: string): CheckResult {
  const body = (JSON.parse(readFileSync(path.join(FIXTURES, name), "utf8")) as { response_body: Record<string, unknown> }).response_body;
  return structuredClone(("result" in body ? body.result : body) as CheckResult);
}

function ready(result: CheckResult, dataOrigin: "FIXTURE" | "LIVE" = "FIXTURE"): ExplorerReady {
  const model = buildExplorerModel(result, { dataOrigin });
  if (model.status !== "READY") throw new Error(`expected READY, got ${model.reason}`);
  return model;
}

const FALLBACK = <p data-testid="test-fallback">2D chart stands here</p>;

function cell(rowKey: string, state: "starting" | "proposed"): string {
  const table = screen.getByTestId("explorer-table");
  const found = table.querySelector(`tr[data-row="${rowKey}"] td[data-state="${state}"]`);
  if (!found) throw new Error(`no cell ${rowKey}/${state}`);
  return found.textContent ?? "";
}

describe("ExposureExplorer: unavailable", () => {
  it("names the reason and the engine's message, and draws nothing", () => {
    const result = fixtureResult("check_invalid_request.json");
    const model = buildExplorerModel(result, { dataOrigin: "FIXTURE" });
    expect(model.status).toBe("UNAVAILABLE");
    render(<ExposureExplorer model={model} fallback={FALLBACK} />);

    const box = screen.getByTestId("explorer-unavailable");
    expect(box).toHaveTextContent("Exposure cannot be shown");
    expect(box).toHaveTextContent("did not run to the end");
    expect(result.execution.message).toBeTruthy();
    expect(box).toHaveTextContent(result.execution.message as string);
    expect(screen.queryByTestId("explorer-table")).not.toBeInTheDocument();
    expect(screen.queryByTestId("test-fallback")).not.toBeInTheDocument();
    expect(screen.getByTestId("explorer-origin")).toHaveTextContent("Test data");
  });
});

describe("ExposureExplorer: origin markers", () => {
  it("marks fixture data, with the policy version, valuation date and calculation version", () => {
    const result = fixtureResult("investigation_robert_succeeded.json");
    render(<ExposureExplorer model={ready(result)} fallback={FALLBACK} />);
    const origin = screen.getByTestId("explorer-origin");
    expect(origin).toHaveTextContent("Test data");
    expect(origin).not.toHaveTextContent("Draft preview");
    const context = screen.getByTestId("explorer-context");
    expect(context).toHaveTextContent(`Confirmed policy version ${result.policy_version}`);
    expect(context).toHaveTextContent(formatDate(result.valuation_date));
    expect(context).toHaveTextContent(result.calculation_version);
  });

  it("marks a draft preview as a draft, and its limit as not confirmed", () => {
    const result = fixtureResult("check_robert_preview.json");
    expect(result.preview).toBe(true);
    const model = ready(result);
    render(<ExposureExplorer model={model} fallback={FALLBACK} />);
    const origin = screen.getByTestId("explorer-origin");
    expect(origin).toHaveTextContent("Test data");
    expect(origin).toHaveTextContent("Draft preview");
    expect(screen.getByTestId("explorer-context")).toHaveTextContent("Draft rules, not a confirmed policy");
    if (model.limit) {
      expect(screen.getByTestId("explorer-limit")).toHaveTextContent("Draft limit (not confirmed)");
      expect(screen.getByTestId("explorer-table").querySelector('tr[data-row="limit"] th')).toHaveTextContent("Draft limit (not confirmed)");
    }
  });

  it("shows no marker for a live, confirmed result", () => {
    render(<ExposureExplorer model={ready(fixtureResult("investigation_robert_succeeded.json"), "LIVE")} fallback={FALLBACK} />);
    expect(screen.queryByTestId("explorer-origin")).not.toBeInTheDocument();
  });
});

describe("ExposureExplorer: values", () => {
  it("shows exactly the fixture's values in the table", () => {
    const result = fixtureResult("investigation_robert_succeeded.json");
    const issuer = result.exposure?.issuers[0];
    if (!result.exposure || !issuer) throw new Error("fixture has no exposure");
    const model = ready(result);
    render(<ExposureExplorer model={model} fallback={FALLBACK} />);

    expect(screen.getByRole("heading", { name: new RegExp(issuer.name) })).toBeInTheDocument();

    for (const state of ["starting", "proposed"] as const) {
      const breakdown = issuer[state];
      expect(cell("direct", state)).toBe(formatFraction(breakdown.direct));
      for (const fund of breakdown.indirect_by_fund) {
        expect(cell(`fund:${fund.fund_id}`, state)).toBe(formatFraction(fund.known));
      }
      expect(cell("known", state)).toBe(formatFraction(breakdown.lower));
      const extra = result.exposure.possible_extra[state];
      if (extra > 0) expect(cell("unresolved", state)).toBe(`up to ${formatFraction(extra)}`);
      if (breakdown.upper !== breakdown.lower) expect(cell("upper", state)).toBe(formatFraction(breakdown.upper));
    }

    const cap = result.rule_results.find((rule) => rule.rule_type === "max_issuer_exposure");
    if (!cap) throw new Error("fixture has no issuer cap");
    expect(cell("limit", "starting")).toBe(formatFraction(cap.limit));
    expect(cell("limit", "proposed")).toBe(formatFraction(cap.limit));
    expect(screen.getByTestId("explorer-limit")).toHaveTextContent("Confirmed limit");
    expect(screen.getByTestId("explorer-limit")).toHaveTextContent("Rule result from the check:");
    expect(screen.getByTestId("explorer-limit").querySelector("[data-status]")).toHaveAttribute("data-status", cap.status);
  });

  it("words a range as a range and never as one total", () => {
    const result = fixtureResult("investigation_robert_succeeded.json");
    const issuer = result.exposure?.issuers[0];
    if (!issuer) throw new Error("fixture has no exposure");
    expect(issuer.proposed.upper, "this fixture is expected to hold a range").not.toBe(issuer.proposed.lower);
    render(<ExposureExplorer model={ready(result)} fallback={FALLBACK} />);

    const sentence = screen.getByTestId("explorer-totals").querySelector('[data-state="proposed"]');
    expect(sentence).toHaveTextContent(`between ${formatFraction(issuer.proposed.lower)} and ${formatFraction(issuer.proposed.upper)} of the portfolio`);
    expect(sentence).toHaveTextContent("shown hollow");
    expect(screen.getByTestId("explorer-table").querySelector('tr[data-row="upper"]')).not.toBeNull();
    const causes = screen.getByTestId("explorer-unknown-causes");
    expect(within(causes).getAllByRole("listitem").length).toBeGreaterThan(0);
  });

  it("has no possible-total row, no hollow part and no range wording when nothing is unresolved", () => {
    const result = fixtureResult("investigation_robert_succeeded.json");
    if (!result.exposure) throw new Error("fixture has no exposure");
    // The same response with nothing unattributed: bounds coincide, as the engine reports for fully covered funds.
    result.exposure.possible_extra = { starting: 0, proposed: 0 };
    for (const issuer of result.exposure.issuers) {
      issuer.starting.upper = issuer.starting.lower;
      issuer.proposed.upper = issuer.proposed.lower;
    }
    const issuer = result.exposure.issuers[0];
    if (!issuer) throw new Error("fixture has no issuer");
    render(<ExposureExplorer model={ready(result)} fallback={FALLBACK} />);

    const table = screen.getByTestId("explorer-table");
    expect(table.querySelector('tr[data-row="upper"]')).toBeNull();
    expect(table.querySelector('tr[data-row="unresolved"]')).toBeNull();
    expect(table).not.toHaveTextContent("Possible total");
    const sentence = screen.getByTestId("explorer-totals").querySelector('[data-state="proposed"]');
    expect(sentence).toHaveTextContent(`${formatFraction(issuer.proposed.lower)} of the portfolio.`);
    expect(sentence).not.toHaveTextContent("between");
    expect(screen.queryByTestId("explorer-unknown-causes")).not.toBeInTheDocument();
  });

  it("says why no limit is drawn when the result has no single-company limit", () => {
    const result = fixtureResult("investigation_robert_succeeded.json");
    result.rule_results = result.rule_results.filter((rule) => rule.rule_type !== "max_issuer_exposure");
    render(<ExposureExplorer model={ready(result)} fallback={FALLBACK} />);
    expect(screen.getByTestId("explorer-limit")).toHaveTextContent("No limit is drawn");
    expect(cell("limit", "proposed")).toBe("Not available");
    expect(screen.getByTestId("explorer-limit").querySelector("[data-status]")).toBeNull();
  });
});

describe("ExposureExplorer: selecting a part", () => {
  it("shows the fund's details and opens its calculation record", async () => {
    const user = userEvent.setup();
    const result = fixtureResult("investigation_robert_succeeded.json");
    const model = ready(result);
    const fund = model.proposed.segments.find((segment) => segment.kind === "FUND" && segment.evidenceId !== null);
    if (!fund?.fundId || !fund.evidenceId) throw new Error("fixture has no fund contribution with a calculation record");
    const record = result.evidence.find((item) => item.evidence_id === fund.evidenceId);
    const coverage = result.data_coverage.find((row) => row.fund_id === fund.fundId);
    if (!record?.formula || !coverage?.holdings_date || !coverage.source_id) throw new Error("fixture lacks the fund's record or coverage");
    const onOpenEvidence = vi.fn();
    render(<ExposureExplorer model={model} fallback={FALLBACK} onOpenEvidence={onOpenEvidence} />);

    expect(screen.queryByTestId("explorer-details")).not.toBeInTheDocument();
    const button = screen.getAllByTestId("explorer-segment").find((item) => item.getAttribute("data-segment") === fund.id);
    if (!button) throw new Error("no button for the fund part");
    expect(button).toHaveAttribute("aria-pressed", "false");
    await user.click(button);
    expect(button).toHaveAttribute("aria-pressed", "true");

    const details = screen.getByTestId("explorer-details");
    expect(details).toHaveTextContent(`Through ${fund.fundId}`);
    expect(details).toHaveTextContent("Proposed portfolio");
    expect(details).toHaveTextContent(formatFraction(fund.value));
    expect(details).toHaveTextContent(formatDate(coverage.holdings_date));
    expect(details).toHaveTextContent(coverage.source_id);
    expect(details).toHaveTextContent(record.formula);

    await user.click(within(details).getByRole("button", { name: "Open the calculation" }));
    expect(onOpenEvidence).toHaveBeenCalledExactlyOnceWith(record.evidence_id);

    // Selecting again clears it.
    await user.click(button);
    expect(screen.queryByTestId("explorer-details")).not.toBeInTheDocument();
  });

  it("works from the keyboard alone", async () => {
    const user = userEvent.setup();
    render(<ExposureExplorer model={ready(fixtureResult("investigation_robert_succeeded.json"))} fallback={FALLBACK} />);
    const first = screen.getAllByTestId("explorer-segment")[0];
    if (!first) throw new Error("no segment button");
    first.focus();
    await user.keyboard("{Enter}");
    expect(screen.getByTestId("explorer-details")).toHaveAttribute("data-segment", first.getAttribute("data-segment"));
  });

  it("says so when the response holds no calculation record for a part", async () => {
    const user = userEvent.setup();
    const model = ready(fixtureResult("investigation_robert_succeeded.json"));
    const direct = model.proposed.segments.find((segment) => segment.kind === "DIRECT");
    if (!direct) throw new Error("no direct part");
    expect(direct.evidenceId).toBeNull();
    render(<ExposureExplorer model={model} fallback={FALLBACK} onOpenEvidence={vi.fn()} />);
    await user.click(screen.getAllByTestId("explorer-segment").find((item) => item.getAttribute("data-segment") === direct.id) as HTMLElement);
    expect(screen.getByTestId("explorer-no-evidence")).toHaveTextContent("The response contains no calculation record for this part.");
    expect(screen.queryByRole("button", { name: "Open the calculation" })).not.toBeInTheDocument();
  });

  it('says "no holdings file" for a fund without one', async () => {
    const user = userEvent.setup();
    const model = ready(fixtureResult("investigation_robert_succeeded.json"));
    const fund = model.proposed.segments.find((segment) => segment.kind === "FUND");
    if (!fund) throw new Error("no fund part");
    // The model as the adapter builds it for a fund that has no holdings entry.
    fund.holdingsDate = null;
    fund.sourceId = null;
    fund.coverageStatus = "MISSING";
    render(<ExposureExplorer model={model} fallback={FALLBACK} />);
    await user.click(screen.getAllByTestId("explorer-segment").find((item) => item.getAttribute("data-segment") === fund.id) as HTMLElement);
    const details = screen.getByTestId("explorer-details");
    expect(details).toHaveTextContent("No holdings file");
    expect(details).toHaveTextContent("No source recorded");
  });

  it("drops a selection that the next result does not contain", async () => {
    const user = userEvent.setup();
    const model = ready(fixtureResult("investigation_robert_succeeded.json"));
    const view = render(<ExposureExplorer model={model} fallback={FALLBACK} />);
    await user.click(screen.getAllByTestId("explorer-segment")[0] as HTMLElement);
    expect(screen.getByTestId("explorer-details")).toBeInTheDocument();
    view.rerender(<ExposureExplorer model={buildExplorerModel(fixtureResult("check_invalid_request.json"), { dataOrigin: "FIXTURE" })} fallback={FALLBACK} />);
    expect(screen.queryByTestId("explorer-details")).not.toBeInTheDocument();
    expect(screen.getByTestId("explorer-unavailable")).toBeInTheDocument();
  });
});

describe("ExposureExplorer: fallback", () => {
  it("renders the caller's fallback, the table and no canvas when WebGL is absent", () => {
    // A wide, ordinary screen: the only thing missing is WebGL.
    vi.stubGlobal("matchMedia", (query: string) => ({
      matches: query.includes("min-width") ? window.innerWidth >= MIN_3D_VIEWPORT_WIDTH : false,
      media: query,
      addEventListener: () => {},
      removeEventListener: () => {},
    }));
    const { container } = render(<ExposureExplorer model={ready(fixtureResult("investigation_robert_succeeded.json"))} fallback={FALLBACK} />);
    const explorer = screen.getByTestId("exposure-explorer");
    expect(explorer).toHaveAttribute("data-mode", "FALLBACK");
    expect(explorer).toHaveAttribute("data-fallback-reason", "NO_WEBGL");
    expect(within(screen.getByTestId("explorer-fallback")).getByTestId("test-fallback")).toBeInTheDocument();
    expect(screen.getByTestId("explorer-fallback")).toHaveTextContent("not available in this browser");
    expect(container.querySelector("canvas")).toBeNull();
    expect(screen.queryByRole("button", { name: "Reset view" })).not.toBeInTheDocument();
    expect(screen.getByTestId("explorer-table")).toBeInTheDocument();
  });

  it("uses the fallback on a narrow screen", () => {
    render(<ExposureExplorer model={ready(fixtureResult("investigation_robert_succeeded.json"))} fallback={FALLBACK} />);
    expect(screen.getByTestId("explorer-fallback")).toBeInTheDocument();
    expect(screen.getByTestId("exposure-explorer")).toHaveAttribute("data-mode", "FALLBACK");
  });

  it("explains how to read the drawing", () => {
    render(<ExposureExplorer model={ready(fixtureResult("investigation_robert_succeeded.json"))} fallback={FALLBACK} />);
    const help = screen.getByTestId("explorer-how-to-read");
    expect(help.tagName).toBe("DETAILS");
    expect(help).toHaveTextContent("Indirect exposure means owning a company through a fund.");
    expect(help).toHaveTextContent("Depth and width mean nothing");
  });
});
