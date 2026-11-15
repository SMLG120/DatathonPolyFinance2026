import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { createFixturesClient } from "@/lib/api/fixtures-client";
import type { InvestigationJob, Policy } from "@/lib/contracts";
import type { InstrumentRegistry } from "@/lib/portfolio";
import { unknownCauseText } from "@/lib/verdict";
import { probe, recorded, SENTINEL } from "@/test/probes";
import { LIVE_CONFIG, renderWithApp, type AppRenderOptions } from "@/test/render";
import { coverageSentence, CoverageBlock } from "./ContextPanels";
import { ExplanationList } from "./Explanation";
import { Report } from "./Report";
import { ruleLookup, RuleResultsList } from "./RuleResults";

const robertInstruments = () => recorded.robertPortfolio().instruments;

function renderReport(job: InvestigationJob, context: { policy: Policy | null; instruments: InstrumentRegistry }, options: AppRenderOptions = {}) {
  if (!job.result) throw new Error("This recorded job has no result.");
  renderWithApp(<Report job={job} result={job.result} policy={context.policy} objectives={[]} instruments={context.instruments} />, options);
  return screen.getByTestId("report");
}

const renderRobert = (job: InvestigationJob = recorded.robertJob(), options: AppRenderOptions = {}) =>
  renderReport(job, { policy: recorded.robertPolicyV1(), instruments: robertInstruments() }, options);

async function renderMateo() {
  const portfolio = await createFixturesClient({ latencyMs: 0 }).getPortfolio("mateo");
  // The policy version of Mateo's recorded job is not itself a recording: the report is read without it.
  return renderReport(recorded.mateoJob(), { policy: null, instruments: portfolio.instruments });
}

describe("Report, page order", () => {
  it("puts the headline, the per-rule results and the exposure chart first, in that order", () => {
    const report = renderRobert();
    const blocks = [...report.children];
    expect(blocks[0]).toHaveAttribute("data-testid", "verdict-summary");
    expect(blocks[1]).toHaveAttribute("id", "report-rules");
    expect(blocks[2]).toHaveAttribute("id", "report-exposure");
    expect(within(blocks[1] as HTMLElement).getAllByTestId("rule-result")).toHaveLength(2);
    expect(within(blocks[2] as HTMLElement).getByTestId("exposure-chart")).toBeInTheDocument();
  });

  it("keeps coverage, the sentences and the notes about the report in closed native disclosures, after everything else", () => {
    const report = renderRobert();
    const ids = [...report.children].map((block) => block.id).filter((id) => id !== "");
    expect(ids).toEqual(["report-rules", "report-exposure", "report-cash", "report-replay", "report-max", "report-objectives", "report-coverage", "report-sentences", "report-about"]);
    for (const id of ["report-coverage", "report-sentences", "report-about"]) {
      const section = document.getElementById(id) as HTMLDetailsElement;
      expect(section.tagName).toBe("DETAILS");
      expect(section.open).toBe(false);
      // The summary is what the keyboard and a tap operate; the title stays a heading in the page outline.
      const summary = section.querySelector(":scope > summary") as HTMLElement;
      expect(summary).not.toBeNull();
      expect(within(summary).getByRole("heading", { level: 2 })).toBeInTheDocument();
    }
    // What matters about coverage stays visible while the section is closed.
    expect(document.getElementById("report-coverage")?.querySelector("summary")).toHaveTextContent("SPY complete · XIU.TO partial (98.0%)");
    expect(document.getElementById("report-sentences")?.querySelector("summary")).toHaveTextContent("5 sentences, each linked to its evidence");
  });

  it("links from the headline card to every section, in page order", () => {
    const report = renderRobert();
    const links = within(within(report).getByRole("navigation", { name: "Sections of this report" })).getAllByRole("link");
    const targets = links.map((link) => link.getAttribute("data-section"));
    expect(targets).toEqual([...report.children].map((block) => block.id).filter((id) => id !== ""));
    for (const target of targets) expect(document.getElementById(target as string)).not.toBeNull();
    expect(links.map((link) => link.textContent)).toEqual([
      "Confirmed rules",
      "Exposure",
      "Cash",
      "Historical replay",
      "Largest compliant purchase",
      "Objectives",
      "Data coverage",
      "In sentences",
      "About this report",
    ]);
  });

  it("opens a closed section from its link and moves focus to it; a panel link moves focus to the panel's heading", async () => {
    const user = userEvent.setup();
    window.location.hash = "#/verdict";
    const report = renderRobert();
    const links = within(within(report).getByRole("navigation", { name: "Sections of this report" }));

    await user.click(links.getByRole("link", { name: "Data coverage" }));
    const coverage = document.getElementById("report-coverage") as HTMLDetailsElement;
    expect(coverage.open).toBe(true);
    expect(coverage.querySelector("summary")).toHaveFocus();
    expect(within(coverage).getAllByTestId("fund-coverage")).toHaveLength(2);

    await user.click(links.getByRole("link", { name: "Exposure" }));
    expect(screen.getByRole("heading", { level: 2, name: "Exposure: held directly and through funds" })).toHaveFocus();
    // The address still names the stage: an in-page link never leaves it.
    expect(window.location.hash).toBe("#/verdict");
  });

  it("lists only the sections a result has (Mateo: findings before the purchase, no replay)", async () => {
    const report = await renderMateo();
    const targets = within(within(report).getByRole("navigation", { name: "Sections of this report" }))
      .getAllByRole("link")
      .map((link) => link.getAttribute("data-section"));
    expect(targets).toEqual(["report-rules", "report-exposure", "report-starting", "report-cash", "report-max", "report-objectives", "report-coverage", "report-sentences", "report-about"]);
    expect(document.getElementById("report-replay")).toBeNull();
  });
});

describe("Report, no financial arithmetic in the browser", () => {
  it("shows the recorded figures of Robert's result where the service put them", () => {
    const report = renderRobert();
    const result = recorded.robertResult();
    expect([result.feasibility?.cash_before, result.feasibility?.cash_after, result.feasibility?.additional_purchase]).toEqual([0.3, 0.05, 0.25]);
    expect(within(report).getByTestId("feasibility")).toHaveTextContent("Cash goes from 30.0% to 5.0% of the portfolio.");
    const table = within(report).getByTestId("feasibility-table");
    expect(within(table).getByTestId("additional-purchase")).toHaveTextContent("+25.0 points");
    expect(within(table).getByTestId("cash-after")).toHaveTextContent("5.0%");
    expect(within(report).getByTestId("max-final-weight")).toHaveTextContent("8.6%");
    expect(within(report).getByTestId("max-additional")).toHaveTextContent("8.6%");
    expect(within(report).getByTestId("starting-breaches")).toHaveAttribute("data-count", "0");
  });

  it("reads cash, the amount added, the counts, the headline and the maximum from the response: figures no arithmetic gives are shown as sent", () => {
    // Cash before minus the purchase is not cash after; the counts are not the number of rule results listed.
    const report = renderRobert(probe.sentinelFigures());
    expect(SENTINEL.cashBefore - SENTINEL.additionalPurchase).not.toBeCloseTo(SENTINEL.cashAfter);

    expect(within(report).getByTestId("feasibility")).toHaveTextContent("Cash goes from 66.6% to 55.5% of the portfolio.");
    const table = within(report).getByTestId("feasibility-table");
    expect(within(table).getByTestId("additional-purchase")).toHaveTextContent("+77.7 points");
    expect(within(table).getByTestId("cash-after")).toHaveTextContent("55.5%");
    const [purchaseBefore, purchaseAfter] = [...(table.querySelector('tr[data-row="purchase"]')?.querySelectorAll("td") ?? [])].map((cell) => cell.textContent);
    expect(purchaseBefore).toBe("1.1%");
    expect(purchaseAfter).toBe("25.0%");
    const [cashBefore] = [...(table.querySelector('tr[data-row="cash"]')?.querySelectorAll("td") ?? [])].map((cell) => cell.textContent);
    expect(cashBefore).toBe("66.6%");

    // Two rule results are listed; the headline and the counts say what the summary says.
    expect(within(report).getAllByTestId("rule-result")).toHaveLength(2);
    expect(within(report).getByTestId("verdict-headline")).toHaveTextContent("8 of 24 confirmed rules are not respected");
    expect(within(report).getByTestId("count-fail")).toHaveAttribute("data-count", "8");
    expect(within(report).getByTestId("count-unknown")).toHaveAttribute("data-count", "9");
    expect(within(report).getByTestId("count-pass")).toHaveAttribute("data-count", "7");
    expect(within(report).getByTestId("starting-breaches")).toHaveAttribute("data-count", "5");
    expect(within(report).getByTestId("starting-breaches")).toHaveTextContent("5 confirmed rules were already not respected");

    // The maximum is the service's, shown rounded down and never recomputed from the limits.
    expect(within(report).getByTestId("max-final-weight")).toHaveTextContent("43.2%");
    expect(within(report).getByTestId("max-additional")).toHaveTextContent("12.3%");
  });

  it("shows the gap the service sent, not the difference between the measured value and the limit", () => {
    const job = recorded.robertJob();
    const cap = job.result?.rule_results.find((ruleResult) => ruleResult.rule_id === "robert-issuer-cap-1");
    if (!cap) throw new Error("The recording changed.");
    expect(cap.gap).toBe(0.162);
    const report = renderRobert(job);
    const row = within(report)
      .getAllByTestId("rule-result")
      .find((item) => item.getAttribute("data-rule-id") === "robert-issuer-cap-1") as HTMLElement;
    expect(within(row).getByTestId("rule-measured")).toHaveTextContent("26.2% to 26.4%");
    expect(within(row).getByTestId("rule-limit")).toHaveTextContent("10.0%");
    expect(within(row).getByTestId("rule-gap")).toHaveTextContent("16.2 points over the limit");
    expect(within(row).getByTestId("rule-reason")).toHaveTextContent(cap.reason);
  });
});

describe("Report, the “Test data” marker", () => {
  it("is on the verdict summary card itself and on every block of figures in fixtures mode", () => {
    const report = renderRobert();
    expect(within(within(report).getByTestId("verdict-summary")).getByTestId("test-data-tag")).toHaveTextContent("Test data");
    const blocks = [...report.querySelectorAll('[data-figures="true"]')];
    // Headline card, six panels and the two closed sections that hold figures.
    expect(blocks.map((block) => block.id || block.getAttribute("data-testid"))).toEqual([
      "verdict-summary",
      "report-rules",
      "report-exposure",
      "report-cash",
      "report-replay",
      "report-max",
      "report-objectives",
      "report-coverage",
      "report-sentences",
    ]);
    for (const block of blocks) {
      expect(within(block as HTMLElement).getAllByTestId("test-data-tag").length, block.id || "verdict-summary").toBeGreaterThan(0);
    }
    // A closed section keeps its tag where it can be seen: on its summary line.
    for (const id of ["report-coverage", "report-sentences"]) {
      expect(within(document.getElementById(id)?.querySelector("summary") as HTMLElement).getByTestId("test-data-tag")).toBeInTheDocument();
    }
  });

  it("leaves no figure outside a marked block", () => {
    const report = renderRobert();
    for (const testId of ["rule-measured", "rule-limit", "rule-gap", "exposure-after", "exposure-before", "cash-after", "additional-purchase", "max-final-weight", "scenario-table", "goal-context-item", "coverage-sentence", "explanation-text", "count-fail", "feasibility"]) {
      const figures = within(report).getAllByTestId(testId);
      expect(figures.length, testId).toBeGreaterThan(0);
      for (const figure of figures) expect(figure.closest('[data-figures="true"]'), testId).not.toBeNull();
    }
  });

  it("shows no such marker on the live service", () => {
    const report = renderRobert(recorded.robertJob(), { config: LIVE_CONFIG });
    expect(within(report).queryAllByTestId("test-data-tag")).toHaveLength(0);
  });
});

describe("Report, Mateo's recorded result", () => {
  it("states both failures plainly and keeps what was already failing apart from what the purchase adds", async () => {
    const report = await renderMateo();
    const result = recorded.mateoResult();
    expect(within(report).getByTestId("verdict-headline")).toHaveTextContent("2 of 2 confirmed rules are not respected");
    expect(within(report).getByTestId("verdict-summary")).toHaveAttribute("data-tone", "fail");
    expect(within(report).getByTestId("starting-breaches")).toHaveAttribute("data-count", "2");
    expect(within(report).getByTestId("starting-breaches")).toHaveTextContent("2 confirmed rules were already not respected");

    const rows = within(report).getAllByTestId("rule-result");
    expect(rows.map((row) => [row.getAttribute("data-rule-id"), row.getAttribute("data-status")])).toEqual([
      ["mateo-excl-energy-1", "FAIL"],
      ["mateo-controversy-1", "FAIL"],
    ]);
    // A failure whose upper end is unproven still says what is unknown, and why.
    const energy = rows[0] as HTMLElement;
    expect(within(energy).getByTestId("rule-measured")).toHaveTextContent("1.4% to 31.8%");
    expect(within(energy).getByTestId("rule-starting")).toHaveAttribute("data-starting-status", "FAIL");
    const energyCauses = result.rule_results[0]?.unknown_causes ?? [];
    expect(energyCauses.length).toBeGreaterThan(0);
    for (const cause of energyCauses) expect(within(energy).getByTestId("unknown-causes")).toHaveTextContent(unknownCauseText(cause));
    expect(within(energy).getByTestId("unknown-causes")).toHaveTextContent("What is still unknown");

    // The findings that exist without the purchase have their own panel, after the exposure and before the cash.
    const starting = document.getElementById("report-starting") as HTMLElement;
    expect(within(starting).getByRole("heading", { level: 2 })).toHaveTextContent("Already not respected before the purchase");
    const findings = within(starting).getAllByTestId("starting-finding");
    expect(findings).toHaveLength(result.starting_portfolio_findings.length);
    expect(findings).toHaveLength(2);
    expect(within(findings[0] as HTMLElement).getByTestId("rule-measured")).toHaveTextContent("1.4% to 16.8%");

    // What the purchase adds is the engine's range, shown as unresolved: proven 0.0, possibly 15.0.
    const effects = within(starting).getAllByTestId("purchase-effect");
    expect(effects.map((effect) => effect.getAttribute("data-resolved"))).toEqual(["false", "false"]);
    expect(effects[0]).toHaveTextContent("Unresolved");
    expect(effects[0]).toHaveTextContent("0.0% to +15.0% of the portfolio");
    expect(effects[1]).toHaveTextContent("+0.3% to +15.0% of the portfolio");
  });

  it("offers no maximum and no replay figure, and shows the missing holdings file as missing", async () => {
    const report = await renderMateo();
    const max = within(report).getByTestId("max-compliant");
    expect(max).toHaveAttribute("data-status", "NO_FEASIBLE_PURCHASE");
    expect(within(max).getByTestId("max-reason")).toHaveTextContent(recorded.mateoResult().max_compliant?.reason as string);
    expect(within(report).queryByTestId("max-final-weight")).toBeNull();
    expect(within(report).queryByTestId("scenario-table")).toBeNull();

    const coverage = document.getElementById("report-coverage") as HTMLElement;
    expect(coverage.querySelector("summary")).toHaveTextContent("ESGV missing");
    const funds = within(coverage).getAllByTestId("fund-coverage");
    const esgv = funds.find((fund) => fund.getAttribute("data-fund-id") === "ESGV") as HTMLElement;
    expect(esgv).toHaveAttribute("data-coverage-status", "MISSING");
    expect(within(esgv).getByTestId("coverage-sentence")).toHaveTextContent("No holdings file");
    // The part of the portfolio that cannot be measured is drawn, not left out.
    expect(report.querySelector('[data-seg="possible"]')).not.toBeNull();
  });
});

describe("An UNKNOWN rule result (Mateo's recorded preview)", () => {
  it("shows the range, no gap, the cause from unknown_causes, and that unknown is not a pass", () => {
    const preview = recorded.mateoPreviewUnknown();
    const [ruleResult] = preview.rule_results;
    if (!ruleResult) throw new Error("The recording changed.");
    expect(ruleResult.status).toBe("UNKNOWN");
    expect(ruleResult.unknown_causes).toEqual(["MISSING_HOLDINGS", "PARTIAL_HOLDINGS"]);

    renderWithApp(<RuleResultsList result={preview} lookup={ruleLookup(null, recorded.mateoPreviewUnknownRequest().draft_rules ?? [])} />);
    const row = screen.getByTestId("rule-result");
    expect(row).toHaveAttribute("data-status", "UNKNOWN");
    expect(within(row).getByTestId("rule-measured")).toHaveTextContent("5.9% to 21.3%");
    expect(within(row).getByTestId("rule-limit")).toHaveTextContent("20.0%");
    expect(within(row).getByTestId("rule-gap")).toHaveTextContent("Cannot be determined");
    const causes = within(row).getByTestId("unknown-causes");
    expect(causes).toHaveTextContent("Why this is unknown");
    expect(causes).toHaveTextContent("a fund has no holdings file");
    expect(causes).toHaveTextContent("a fund's holdings file reports only part of the fund");
    expect(causes).toHaveTextContent("Missing data is never counted as zero");
    expect(within(row).getByTestId("unknown-note")).toHaveTextContent("Unknown is not a pass.");
    // The row carries no pass and no fail badge.
    expect(row.querySelectorAll('[data-status="PASS"], [data-status="FAIL"]')).toHaveLength(0);
  });
});

describe("Fund coverage wording", () => {
  it("reads the recorded funds as complete and as partial with the reported percentage", () => {
    const result = recorded.robertResult();
    renderWithApp(<CoverageBlock funds={result.data_coverage} instrumentName={(fundId) => fundId} />);
    const sentence = (fundId: string) =>
      within(screen.getAllByTestId("fund-coverage").find((fund) => fund.getAttribute("data-fund-id") === fundId) as HTMLElement).getByTestId("coverage-sentence").textContent;
    expect(sentence("SPY")).toBe("Complete — 100.0% of the fund reported");
    expect(sentence("XIU.TO")).toBe("Partial — 98.0% of the fund reported");
  });

  it("truncates the percentage of a fund below full coverage, so it never reads 100.0% beside the word Partial", () => {
    const result = probe.withCoverage("XIU.TO", 0.9996);
    renderWithApp(<CoverageBlock funds={result.data_coverage} instrumentName={(fundId) => fundId} />);
    const fund = screen.getAllByTestId("fund-coverage").find((item) => item.getAttribute("data-fund-id") === "XIU.TO") as HTMLElement;
    expect(fund).toHaveAttribute("data-coverage-status", "PARTIAL");
    expect(within(fund).getByTestId("coverage-sentence")).toHaveTextContent("Partial — 99.9% of the fund reported");
    expect(within(fund).getByTestId("coverage-sentence")).not.toHaveTextContent("100");
    const xiu = (fraction: number) => probe.withCoverage("XIU.TO", fraction).data_coverage.find((item) => item.fund_id === "XIU.TO");
    for (const [fraction, sentence] of [
      [0.99999, "Partial — 99.9% of the fund reported"],
      [0.9987, "Partial — 99.8% of the fund reported"],
    ] as const) {
      const partial = xiu(fraction);
      if (!partial) throw new Error("The recording changed.");
      expect(coverageSentence(partial)).toBe(sentence);
    }
  });

  it("keeps the truncated percentage on the closed section's summary line too", () => {
    renderRobert(probe.robertJobWith(probe.withCoverage("XIU.TO", 0.9996)));
    expect(document.getElementById("report-coverage")?.querySelector("summary")).toHaveTextContent("SPY complete · XIU.TO partial (99.9%)");
  });
});

describe("The result in sentences", () => {
  it("shows every recorded sentence word for word and says which were written by the model", () => {
    const job = recorded.robertJob();
    renderWithApp(<ExplanationList result={recorded.robertResult()} statements={job.explanation} />);
    const statements = screen.getAllByTestId("explanation-statement");
    expect(statements).toHaveLength(job.explanation.length);
    job.explanation.forEach((statement, index) => {
      const item = statements[index] as HTMLElement;
      expect(within(item).getByTestId("explanation-text").textContent).toBe(statement.text);
      expect(item).toHaveAttribute("data-rendered-by", statement.rendered_by);
      expect(item).toHaveTextContent(statement.rendered_by === "MODEL_VALIDATED" ? "Written by the model" : "Template sentence");
    });
    expect(statements.filter((item) => item.getAttribute("data-rendered-by") === "MODEL_VALIDATED")).toHaveLength(1);
  });

  it("renders model-written text as plain text only: markup in a sentence is shown as characters, never interpreted", () => {
    const hostile = '<img src=x onerror="window.__pwned = true"> <a href="javascript:alert(1)">click</a> <script>window.__pwned = true</script> **bold** [link](https://example.test)';
    const job = probe.withStatementText("st-4", hostile);
    renderWithApp(<ExplanationList result={recorded.robertResult()} statements={job.explanation} />);
    const list = screen.getByTestId("explanation");
    const item = screen.getAllByTestId("explanation-statement").find((statement) => statement.getAttribute("data-rendered-by") === "MODEL_VALIDATED") as HTMLElement;
    const text = within(item).getByTestId("explanation-text");

    expect(text.textContent).toBe(hostile);
    // One text node and nothing else: no element was created from the sentence.
    expect(text.childElementCount).toBe(0);
    expect(list.querySelectorAll("img, script, a, strong, b, em, iframe")).toHaveLength(0);
    expect((window as unknown as { __pwned?: boolean }).__pwned).toBeUndefined();
  });
});
