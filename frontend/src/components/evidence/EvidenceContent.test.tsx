import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { CheckResult, EvidenceRecord } from "@/lib/contracts";
import { FIXTURES } from "@/lib/fixtures";
import { probe, recorded } from "@/test/probes";
import { LIVE_CONFIG, renderWithApp, type AppRenderOptions } from "@/test/render";
import { EvidenceContent, SOURCE_DETAILS_NOTE } from "./EvidenceContent";

function renderEvidence(result: CheckResult, evidenceIds: string[], options: AppRenderOptions = {}) {
  const onChallenge = vi.fn();
  renderWithApp(<EvidenceContent request={{ title: "a figure", result, evidenceIds }} onChallenge={onChallenge} />, options);
  return { onChallenge, records: screen.queryAllByTestId("evidence-record") };
}

function recordOf(result: CheckResult, evidenceId: string): EvidenceRecord {
  const record = result.evidence.find((candidate) => candidate.evidence_id === evidenceId);
  if (!record) throw new Error(`The recording has no evidence record ${evidenceId}.`);
  return record;
}

describe("Evidence drawer, how a figure was calculated", () => {
  it("shows the formula as the engine recorded it, apart from the values it was computed from", () => {
    const result = recorded.robertResult();
    const record = recordOf(result, "ev-cash-after");
    const { records } = renderEvidence(result, ["ev-cash-after"]);
    const card = records[0] as HTMLElement;
    const calculation = within(card).getByTestId("evidence-calculation");

    // Two headed blocks: the formula text, then the list of substituted values.
    expect(within(calculation).getByRole("heading", { name: "How it was calculated" })).toBeInTheDocument();
    expect(within(calculation).getAllByRole("heading", { level: 5 }).map((heading) => heading.textContent)).toEqual([
      "Formula, as recorded by the engine",
      "Values it was computed from",
    ]);
    const formula = within(calculation).getByTestId("evidence-formula");
    const inputs = within(calculation).getByTestId("evidence-inputs");
    expect(formula.textContent).toBe(record.formula);
    expect(formula.textContent).toBe("0.30 - (0.25 - 0.00) = 0.05");
    expect(formula.childElementCount).toBe(0);
    expect(formula.contains(inputs)).toBe(false);
    expect(inputs.contains(formula)).toBe(false);
    expect(formula.compareDocumentPosition(inputs) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();

    // Each value is one of the records the service names in derived_from, in its order, with what it is and whose it is.
    const rows = within(inputs).getAllByTestId("evidence-input");
    expect(record.derived_from).toEqual(["ev-cash-start", "ev-w-nvda-start", "ev-w-nvda-target"]);
    expect(rows).toHaveLength(record.derived_from.length);
    expect(rows[0]).toHaveTextContent("Cash weight");
    expect(rows[0]).toHaveTextContent("ev-cash-start");
    expect(rows[0]).toHaveTextContent("30.00% (as a fraction: 0.3)");
    expect(rows[1]).toHaveTextContent("Instrument NVDA, before the purchase");
    expect(rows[1]).toHaveTextContent("0.00% (as a fraction: 0)");
    expect(rows[2]).toHaveTextContent("Instrument NVDA, after the purchase");
    expect(rows[2]).toHaveTextContent("25.00% (as a fraction: 0.25)");
  });

  it("renders a formula that contains the character ≈ exactly as it is", () => {
    const formula = "0.262 + 0.002 ≈ 0.264";
    const { records } = renderEvidence(probe.withFormula("ev-nvda-upper", formula), ["ev-nvda-upper"]);
    const shown = within(records[0] as HTMLElement).getByTestId("evidence-formula");
    expect(shown.textContent).toBe(formula);
    expect(shown.textContent).toContain("≈");
    expect(shown.childElementCount).toBe(0);
  });

  it("shows a formula written in words as it is, with no list when the service names no input", () => {
    const result = recorded.robertResult();
    const record = recordOf(result, "ev-scn-prop-dd");
    expect(record.derived_from).toEqual([]);
    const { records } = renderEvidence(result, ["ev-scn-prop-dd"]);
    const card = records[0] as HTMLElement;
    expect(within(card).getByTestId("evidence-formula").textContent).toBe("lowest value 0.7765 on 2022-06-30 against a running maximum of 1.0000");
    expect(within(card).queryByTestId("evidence-inputs")).toBeNull();
  });

  it("says that a recorded value has no calculation instead of leaving the block empty", () => {
    const { records } = renderEvidence(recorded.robertResult(), ["ev-cap-threshold"]);
    const card = records[0] as HTMLElement;
    expect(within(card).getByTestId("evidence-no-calculation")).toHaveTextContent("No calculation: this value is taken as recorded.");
    expect(within(card).queryByTestId("evidence-formula")).toBeNull();
    expect(within(card).queryByTestId("evidence-inputs")).toBeNull();
  });

  it("names an input the result does not hold instead of dropping it", () => {
    const { records } = renderEvidence(probe.withoutEvidenceRecord("ev-cash-start"), ["ev-cash-after"]);
    const card = records[0] as HTMLElement;
    expect(within(card).getAllByTestId("evidence-input")).toHaveLength(2);
    expect(within(card).getByTestId("evidence-input-missing")).toHaveTextContent("ev-cash-start");
  });
});

describe("Evidence drawer, sources, dates and assumptions", () => {
  it("shows the source ids, the date and the assumptions recorded with the figure", () => {
    const result = recorded.robertResult();
    const record = recordOf(result, "ev-ret-nvda");
    const { records } = renderEvidence(result, ["ev-ret-nvda"]);
    const card = records[0] as HTMLElement;

    expect(record.source_ids).toEqual(["SYNTHETIC_FIXTURE"]);
    expect(within(within(card).getByTestId("evidence-sources")).getAllByRole("listitem").map((item) => item.textContent)).toEqual(record.source_ids);
    expect(within(card).getByTestId("evidence-period")).toHaveTextContent("31 Dec 2021 to 30 Dec 2022");
    expect(record.assumptions.length).toBeGreaterThan(0);
    expect(within(within(card).getByTestId("evidence-assumptions")).getAllByRole("listitem").map((item) => item.textContent)).toEqual(record.assumptions);
    expect(within(card).getByTestId("evidence-value")).toHaveTextContent("−35.00%");
    expect(within(card).getByTestId("evidence-label")).toHaveTextContent("Calculation");
  });

  it("shows a single date as a date", () => {
    const { records } = renderEvidence(recorded.robertResult(), ["ev-spy-nvda-weight"]);
    const card = records[0] as HTMLElement;
    expect(within(card).getByTestId("evidence-period")).toHaveTextContent("As of 12 Nov 2026");
    expect(within(card).getByTestId("evidence-label")).toHaveTextContent("Fact");
    expect(within(card).getByTestId("evidence-sources")).toHaveTextContent("SYNTHETIC_FIXTURE");
  });

  it.each([
    ["on test data", {}],
    ["on the live service", { config: LIVE_CONFIG }],
  ] as const)("says plainly that only source ids are available and promises nothing more, %s (finding F-07)", (_mode, options) => {
    renderEvidence(recorded.robertResult(), ["ev-spy-nvda-weight"], options);
    const note = screen.getByTestId("source-details-note");
    expect(note).toHaveTextContent(SOURCE_DETAILS_NOTE);
    expect(SOURCE_DETAILS_NOTE).toContain("Only the ids of a figure’s sources are available here");
    expect(SOURCE_DETAILS_NOTE).toContain("are not shown");
    // No route delivers the registry, so the note must not announce that its details will load.
    expect(note.textContent).not.toMatch(/live API|once it delivers|until then|\bload/i);
    expect(screen.getByTestId("evidence-sources")).toHaveTextContent("SYNTHETIC_FIXTURE");

    // No route delivers the source registry, so its title, publisher and terms are not on the page.
    const source = FIXTURES.registries.robert_synthetic_universe?.sources.SYNTHETIC_FIXTURE;
    if (!source) throw new Error("The copied registry changed.");
    for (const detail of [source.title, source.publisher, source.terms, source.sha256]) {
      expect(document.body).not.toHaveTextContent(detail);
    }
  });

  it("says where a calculated value's sources are when it has none of its own", () => {
    const { records } = renderEvidence(recorded.robertResult(), ["ev-nvda-lower"]);
    const card = records[0] as HTMLElement;
    expect(within(card).queryByTestId("evidence-sources")).toBeNull();
    expect(within(card).getByTestId("evidence-no-source")).toHaveTextContent("rests on the sources of the values listed above");
    expect(within(card).getByText("None recorded.")).toBeInTheDocument();
  });

  it("says so when a figure refers to a record the result does not hold", () => {
    const { records } = renderEvidence(recorded.robertResult(), ["ev-does-not-exist"]);
    expect(records).toHaveLength(0);
    expect(screen.getByText("Evidence record not found")).toBeInTheDocument();
    expect(screen.getByText(/Treat the figure as\s+unverified/)).toBeInTheDocument();
  });
});

describe("Evidence drawer, marking and challenge", () => {
  it("marks every record as test data in fixtures mode, and none on the live service", () => {
    const ids = ["ev-nvda-lower", "ev-nvda-upper", "ev-cap-threshold"];
    const fixtures = renderEvidence(recorded.robertResult(), ids);
    expect(fixtures.records).toHaveLength(ids.length);
    for (const card of fixtures.records) {
      expect(card).toHaveAttribute("data-figures", "true");
      expect(within(card).getByTestId("test-data-tag")).toHaveTextContent("Test data");
    }
    for (const card of fixtures.records) card.remove();

    const live = renderEvidence(recorded.robertResult(), ids, { config: LIVE_CONFIG });
    for (const card of live.records) expect(within(card).queryByTestId("test-data-tag")).toBeNull();
  });

  it("offers to challenge a figure of a report, and passes the record on", async () => {
    const user = userEvent.setup();
    const { onChallenge, records } = renderEvidence(recorded.robertResult(), ["ev-spy-nvda-weight"]);
    await user.click(within(records[0] as HTMLElement).getByRole("link", { name: "Challenge this figure" }));
    expect(onChallenge).toHaveBeenCalledWith("ev-spy-nvda-weight");
  });

  it("labels the records of a preview as a preview and offers no challenge on them", () => {
    const preview = recorded.robertPreview();
    const [first] = preview.evidence;
    if (!first) throw new Error("The recorded preview has no evidence.");
    const { records } = renderEvidence(preview, [first.evidence_id]);
    expect(screen.getByText("Preview with draft rules — not a confirmed policy")).toBeInTheDocument();
    expect(within(records[0] as HTMLElement).queryByRole("link", { name: "Challenge this figure" })).toBeNull();
  });
});
