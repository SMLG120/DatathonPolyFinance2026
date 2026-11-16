import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SOURCE_DETAILS_NOTE } from "@/components/evidence/EvidenceContent";
import { FIXTURES_LABEL, SIMULATION_LABEL } from "@/components/shell/AppShell";
import type { CheckResult, InvestigationJob, Portfolio } from "@/lib/contracts";
import { CUSTOMIZED_LABEL } from "@/lib/customize";
import { formatDate, formatFraction, formatGap } from "@/lib/format";
import { limitNoun, ruleDirection } from "@/lib/rules";
import { recorded } from "@/test/probes";
import { renderWithApp } from "@/test/render";
import { PRINT_NOT_ADVICE, PRINT_REPORT_LABEL, PrintReport, printDocumentTitle, useReportPrint, type PrintReportProps } from "./PrintReport";
import { Report } from "./Report";
import { measureDecimals, measuredText } from "./RuleMeasure";

function resultOf(job: InvestigationJob): CheckResult {
  if (!job.result) throw new Error("This recorded job has no result.");
  return job.result;
}

function renderPrint(job: InvestigationJob, overrides: Partial<PrintReportProps> = {}) {
  const portfolio = recorded.robertPortfolio();
  render(
    <PrintReport
      job={job}
      result={resultOf(job)}
      policy={null}
      objectives={[]}
      instruments={portfolio.instruments}
      scenarioPortfolio={portfolio.scenario.portfolio}
      personaName={portfolio.scenario.persona.display_name}
      testData={false}
      {...overrides}
    />,
  );
  return screen.getByTestId("print-report");
}

const robertPrint = (overrides: Partial<PrintReportProps> = {}, job: InvestigationJob = recorded.robertJob()) =>
  renderPrint(job, { policy: recorded.robertPolicyV1(), ...overrides });

/**
 * Mateo's recorded job carrying the recorded result in which rules are UNKNOWN. That result is recorded as a
 * preview; only the three members that say so are set to the job's. No figure is written here.
 */
function mateoUnknownJob(): InvestigationJob {
  const job = recorded.mateoJob();
  const unknown = recorded.mateoPreviewUnknown();
  unknown.preview = false;
  unknown.policy_id = job.policy_id;
  unknown.policy_version = job.policy_version;
  job.result = unknown;
  return job;
}

afterEach(() => vi.restoreAllMocks());

describe("PrintReport, what the document says it is", () => {
  it("opens with the simulation label and says it is a simulation report, not personalized financial advice", () => {
    const doc = robertPrint();
    expect(within(doc).getByTestId("print-simulation-label")).toHaveTextContent(SIMULATION_LABEL);
    expect(within(doc).getByRole("heading", { level: 1 })).toHaveTextContent("simulation report");
    expect(within(doc).getByTestId("print-not-advice")).toHaveTextContent(PRINT_NOT_ADVICE);
    expect(PRINT_NOT_ADVICE).toMatch(/not personalized financial advice/);
    expect(within(doc).queryByTestId("print-test-data")).toBeNull();
  });

  it("says so when the figures are recorded test data", () => {
    const doc = robertPrint({ testData: true });
    expect(within(doc).getByTestId("print-simulation-label")).toHaveTextContent(FIXTURES_LABEL);
    expect(within(doc).getByTestId("print-test-data")).toHaveTextContent("recorded test data");
  });

  it("identifies the report: persona, valuation date of the result, investigation, policy version and purchase", () => {
    const job = recorded.robertJob();
    const result = resultOf(job);
    const doc = robertPrint({}, job);
    expect(within(doc).getByTestId("print-persona")).toHaveTextContent(recorded.robertPortfolio().scenario.persona.display_name);
    expect(within(doc).getByTestId("print-valuation-date")).toHaveTextContent(formatDate(result.valuation_date));
    expect(within(doc).getByTestId("print-investigation-id")).toHaveTextContent(job.id);
    expect(within(doc).getByTestId("print-policy")).toHaveTextContent(`Version ${result.policy_version}`);
    expect(within(doc).getByTestId("print-purchase")).toHaveTextContent(result.purchase_request.instrument_id);
  });

  it("has no control, link or drawing: it is a document, not a screen", () => {
    const doc = robertPrint();
    expect(doc.querySelectorAll("button, a, input, select, textarea, summary, details, svg, canvas, [role=button]")).toHaveLength(0);
  });
});

describe("PrintReport, the verdict and the rules", () => {
  it("prints the engine's headline and counts", () => {
    const result = recorded.robertResult();
    const doc = robertPrint();
    expect(within(doc).getByTestId("print-verdict")).toHaveAttribute("data-headline", result.summary.headline);
    expect(within(doc).getByTestId("print-headline")).toHaveTextContent("2 of 2 confirmed rules are not respected");
    expect(within(doc).getByTestId("print-counts")).toHaveTextContent(
      `Confirmed rules evaluated: ${result.summary.rules_evaluated}. Pass: ${result.summary.counts.pass}. Fail: ${result.summary.counts.fail}. Unknown: ${result.summary.counts.unknown}.`,
    );
  });

  it("prints every evaluated rule with its status, measured value, limit and gap as the screen words them", () => {
    const result = recorded.robertResult();
    const doc = robertPrint();
    const blocks = within(doc).getAllByTestId("print-rule");
    expect(blocks).toHaveLength(result.rule_results.length);
    result.rule_results.forEach((ruleResult, index) => {
      const block = blocks[index] as HTMLElement;
      expect(block).toHaveAttribute("data-rule-id", ruleResult.rule_id);
      expect(block).toHaveAttribute("data-status", ruleResult.status);
      expect(within(block).getByTestId("print-rule-measured")).toHaveTextContent(measuredText(ruleResult.rule_type, ruleResult.measured));
      expect(within(block).getByTestId("print-rule-limit")).toHaveTextContent(formatFraction(ruleResult.limit));
      const noun = limitNoun(ruleResult.rule_type).toLowerCase();
      expect(within(block).getByTestId("print-rule-gap")).toHaveTextContent(formatGap(ruleResult.gap, ruleDirection(ruleResult.rule_type), noun, measureDecimals(ruleResult.rule_type)));
      expect(block).toHaveTextContent(ruleResult.reason);
    });
  });

  it("shows figures it was sent, not figures it worked out: a changed limit and gap are printed as they are", () => {
    const job = recorded.robertJob();
    const result = resultOf(job);
    const first = result.rule_results[0] as (typeof result.rule_results)[number];
    first.limit = 0.4321;
    first.gap = 0.1234;
    const doc = robertPrint({}, job);
    const block = within(doc).getAllByTestId("print-rule")[0] as HTMLElement;
    expect(within(block).getByTestId("print-rule-limit")).toHaveTextContent("43.2%");
    expect(within(block).getByTestId("print-rule-gap")).toHaveTextContent("12.3 points over the limit");
  });
});

describe("PrintReport, unknown outcomes and limitations", () => {
  it("keeps UNKNOWN as UNKNOWN: in the headline, on the rule, and listed directly under the verdict", () => {
    const job = mateoUnknownJob();
    const result = resultOf(job);
    const unknownRules = result.rule_results.filter((ruleResult) => ruleResult.status === "UNKNOWN");
    expect(unknownRules.length).toBeGreaterThan(0);
    const doc = renderPrint(job);

    expect(within(doc).getByTestId("print-counts")).toHaveTextContent(`Unknown: ${result.summary.counts.unknown}.`);
    const unknownBlocks = within(doc)
      .getAllByTestId("print-rule")
      .filter((block) => block.getAttribute("data-status") === "UNKNOWN");
    expect(unknownBlocks).toHaveLength(unknownRules.length);
    for (const block of unknownBlocks) {
      expect(block).toHaveTextContent("UNKNOWN");
      expect(within(block).getByTestId("print-unknown-note")).toHaveTextContent("Unknown is not a pass.");
      expect(within(block).getByTestId("print-unknown-causes")).toHaveTextContent("Why this is unknown");
    }

    const limitations = within(doc).getByTestId("print-limitations");
    expect(Number(limitations.getAttribute("data-count"))).toBeGreaterThanOrEqual(unknownRules.length);
    expect(limitations).toHaveTextContent("UNKNOWN");
    expect(limitations).toHaveTextContent("an unknown result is never counted as a pass");
    // The limitations come before the rule list, straight after the verdict.
    const sections = [...doc.children].map((child) => child.getAttribute("data-testid"));
    expect(sections).toContain("print-verdict");
    expect(sections.indexOf("print-limitations")).toBe(sections.indexOf("print-verdict") + 1);
  });

  it("lists a fund without holdings and a partly reported fund as limitations, and in the coverage table", () => {
    const job = recorded.mateoJob();
    const result = resultOf(job);
    const doc = renderPrint(job);
    const limitations = within(doc).getByTestId("print-limitations");
    for (const fund of result.data_coverage.filter((candidate) => candidate.status !== "COVERED")) {
      expect(limitations).toHaveTextContent(fund.fund_id);
    }
    expect(limitations).toHaveTextContent("no holdings file");
    const rows = within(doc).getAllByTestId("print-coverage-row");
    expect(rows.map((row) => row.getAttribute("data-coverage-status"))).toEqual(result.data_coverage.map((fund) => fund.status));
  });

  it("writes out a rule that passes or fails while part of its range is unproven", () => {
    const doc = robertPrint();
    expect(within(doc).getByTestId("print-limitations")).toHaveTextContent("with part of the measured range unproven");
  });

  it("says in words when no maximum is shown instead of printing a number", () => {
    const job = mateoUnknownJob();
    const maximum = resultOf(job).max_compliant;
    if (maximum?.status !== "WITHHELD") throw new Error("The recording changed: a withheld maximum is expected.");
    const doc = renderPrint(job);
    expect(within(doc).getByTestId("print-max-withheld")).toHaveTextContent("No maximum is shown.");
    expect(within(doc).getByTestId("print-max-withheld")).toHaveTextContent(maximum.reason);
    expect(within(doc).getByTestId("print-limitations")).toHaveTextContent(maximum.reason);
    expect(within(doc).queryByTestId("print-max-supported")).toBeNull();
  });
});

describe("PrintReport, portfolio, sources and the closed sections of the screen", () => {
  it("names the persona's original portfolio, or a customized one, from the portfolio stored with the job", () => {
    const scenario = recorded.robertPortfolio().scenario.portfolio;
    const original: InvestigationJob = { ...recorded.robertJob(), portfolio: scenario };
    const first = robertPrint({}, original);
    expect(within(first).getByTestId("print-portfolio-label")).toHaveAttribute("data-customized", "false");
    expect(within(first).getByTestId("print-portfolio-label")).toHaveTextContent("original fictional portfolio");
    expect(within(first).getAllByTestId("print-portfolio-row")).toHaveLength(scenario.positions.length + 1);
  });

  it("prints the customized weights the job stored, not the scenario's", () => {
    const scenario = recorded.robertPortfolio().scenario.portfolio;
    const [firstPosition, ...rest] = scenario.positions as [Portfolio["positions"][number], ...Portfolio["positions"]];
    const custom: Portfolio = {
      ...scenario,
      portfolio_id: "pf-robert-custom-test",
      cash_weight: scenario.cash_weight + firstPosition.weight - 0.0123,
      positions: [{ ...firstPosition, weight: 0.0123 }, ...rest],
    };
    const doc = robertPrint({}, { ...recorded.robertJob(), portfolio: custom });
    const label = within(doc).getByTestId("print-portfolio-label");
    expect(label).toHaveAttribute("data-customized", "true");
    expect(label).toHaveTextContent(CUSTOMIZED_LABEL);
    expect(within(doc).getAllByTestId("print-portfolio-row")[0] as HTMLElement).toHaveTextContent("1.2%");
  });

  it("lists the source ids recorded with the figures and says what is not available, without inventing a citation", () => {
    const result = recorded.robertResult();
    const doc = robertPrint();
    const expected = new Set([...result.evidence.flatMap((record) => record.source_ids), ...result.data_coverage.flatMap((fund) => (fund.source_id ? [fund.source_id] : []))]);
    const printed = within(doc)
      .getAllByTestId("print-source")
      .map((item) => item.querySelector(".pr-id")?.textContent);
    expect(new Set(printed)).toEqual(expected);
    expect(printed).toHaveLength(expected.size);
    expect(within(doc).getByTestId("print-source-note")).toHaveTextContent(SOURCE_DETAILS_NOTE);
    expect(within(doc).getByTestId("print-sources")).not.toHaveTextContent(/https?:\/\//);
  });

  it("writes out what the screen keeps closed: coverage, assumptions, replay assumptions, sentences and disclosures", () => {
    const job = recorded.robertJob();
    const result = resultOf(job);
    const doc = robertPrint({}, job);
    expect(within(doc).getAllByTestId("print-coverage-row")).toHaveLength(result.data_coverage.length);
    // Every assumption recorded with a figure is printed once: with the replay when it is the replay's, in the list otherwise.
    const replay = result.scenario?.assumptions ?? [];
    expect(replay.length).toBeGreaterThan(0);
    const others = [...new Set(result.evidence.flatMap((record) => record.assumptions))].filter((assumption) => !replay.includes(assumption));
    expect(others.length).toBeGreaterThan(0);
    expect(within(within(doc).getByTestId("print-assumptions")).getAllByRole("listitem")).toHaveLength(others.length);
    for (const assumption of others) expect(within(doc).getByTestId("print-assumptions")).toHaveTextContent(assumption);
    expect(within(within(doc).getByTestId("print-scenario-assumptions")).getAllByRole("listitem")).toHaveLength(replay.length);
    for (const assumption of replay) expect(within(doc).getByTestId("print-scenario-assumptions")).toHaveTextContent(assumption);
    for (const statement of job.explanation) expect(within(doc).getByTestId("print-sentences")).toHaveTextContent(statement.text);
    for (const disclosure of result.disclosures) expect(within(doc).getByTestId("print-disclosures")).toHaveTextContent(disclosure);
    expect(within(doc).getAllByTestId("print-exposure-row")).toHaveLength(result.exposure?.issuers.length ?? 0);
  });
});

describe("the export button on a report", () => {
  it("is shown, clearly labelled, only when the report can be printed, and calls the print action", () => {
    const job = recorded.robertJob();
    const onPrint = vi.fn();
    const props = { job, result: resultOf(job), policy: recorded.robertPolicyV1(), objectives: [], instruments: recorded.robertPortfolio().instruments };
    const first = renderWithApp(<Report {...props} />);
    expect(screen.queryByTestId("print-report-button")).toBeNull();
    first.unmount();
    renderWithApp(<Report {...props} onPrint={onPrint} />);
    const button = screen.getByRole("button", { name: PRINT_REPORT_LABEL });
    expect(button).toHaveAttribute("data-testid", "print-report-button");
    fireEvent.click(button);
    expect(onPrint).toHaveBeenCalledTimes(1);
  });
});

describe("useReportPrint", () => {
  function Harness({ title }: { title: string | null }) {
    const { printing, print } = useReportPrint(title);
    return (
      <div>
        <button onClick={print}>go</button>
        <span data-testid="printing">{printing ? "yes" : "no"}</span>
      </div>
    );
  }

  it("has the print document ready before the browser prints, names the PDF, and puts everything back afterwards", () => {
    const title = printDocumentTitle({ id: "inv-1", persona_id: "robert" });
    document.title = "Before You Buy";
    let titleAtPrint = "";
    let printingAtPrint = "";
    const printSpy = vi.fn(() => {
      titleAtPrint = document.title;
      printingAtPrint = screen.getByTestId("printing").textContent ?? "";
    });
    vi.stubGlobal("print", printSpy);
    render(<Harness title={title} />);
    expect(screen.getByTestId("printing")).toHaveTextContent("no");

    fireEvent.click(screen.getByRole("button", { name: "go" }));
    expect(printSpy).toHaveBeenCalledTimes(1);
    expect(printingAtPrint).toBe("yes");
    expect(titleAtPrint).toBe(title);
    expect(title).toContain("inv-1");

    act(() => {
      window.dispatchEvent(new Event("afterprint"));
    });
    expect(screen.getByTestId("printing")).toHaveTextContent("no");
    expect(document.title).toBe("Before You Buy");
    vi.unstubAllGlobals();
  });

  it("also prepares the document when printing is started from the browser's own Print command", () => {
    render(<Harness title={null} />);
    act(() => {
      window.dispatchEvent(new Event("beforeprint"));
    });
    expect(screen.getByTestId("printing")).toHaveTextContent("yes");
    act(() => {
      window.dispatchEvent(new Event("afterprint"));
    });
    expect(screen.getByTestId("printing")).toHaveTextContent("no");
  });
});
