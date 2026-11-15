import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { InvestigationStep } from "@/lib/contracts";
import { StepTimeline, toolLabel } from "./StepTimeline";

function step(seq: number, tool: string, overrides: Partial<InvestigationStep> = {}): InvestigationStep {
  return {
    seq,
    tool,
    initiated_by: "SERVER",
    status: "OK",
    started_at: `2026-11-14T15:02:0${seq}Z`,
    finished_at: `2026-11-14T15:02:1${seq}Z`,
    input_summary: `input ${seq}`,
    result_summary: `result ${seq}`,
    ...overrides,
  };
}

describe("StepTimeline", () => {
  it("shows exactly the steps the job reported — no more — in sequence order", () => {
    render(<StepTimeline steps={[step(2, "get_policy"), step(1, "get_portfolio")]} waiting={false} />);
    const rows = screen.getAllByTestId("timeline-step");
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent("Step 1 · Read the portfolio");
    expect(rows[1]).toHaveTextContent("Step 2 · Read the confirmed policy");
    expect(screen.queryByTestId("timeline-waiting")).toBeNull();
  });

  it("shows the tool name, who ran it, the time, and the input and result summaries", () => {
    render(<StepTimeline steps={[step(1, "compute_exposure", { initiated_by: "MODEL" })]} waiting={false} />);
    const row = screen.getByTestId("timeline-step");
    expect(row).toHaveTextContent("compute_exposure");
    expect(row).toHaveTextContent("requested by the model");
    expect(row).toHaveTextContent("finished 15:02:11 UTC");
    expect(within(row).getByText("input 1")).toBeInTheDocument();
    expect(within(row).getByText("result 1")).toBeInTheDocument();
    expect(within(row).getByText("Completed")).toBeInTheDocument();
  });

  it("puts a plain waiting line after the real steps while the job is running, and invents no step", () => {
    render(<StepTimeline steps={[step(1, "get_portfolio")]} waiting />);
    expect(screen.getAllByTestId("timeline-step")).toHaveLength(1);
    expect(screen.getByTestId("timeline-waiting")).toHaveTextContent("Waiting for the next step");
  });

  it("shows only the waiting line when no step has been reported yet", () => {
    render(<StepTimeline steps={[]} waiting />);
    expect(screen.queryAllByTestId("timeline-step")).toHaveLength(0);
    expect(screen.getByTestId("timeline-waiting")).toBeInTheDocument();
  });

  it("shows a step as in progress only when the job reports it as running", () => {
    render(<StepTimeline steps={[step(1, "get_portfolio"), step(2, "replay_period", { status: "RUNNING", finished_at: null, result_summary: null })]} waiting />);
    const running = screen.getAllByTestId("timeline-step")[1];
    expect(running).toHaveAttribute("data-step-status", "RUNNING");
    expect(running).toHaveTextContent("In progress");
    expect(running).toHaveTextContent("started 15:02:02 UTC");
    expect(running).toHaveTextContent("Not available yet");
    // The job already says what it is doing: no extra "waiting" line.
    expect(screen.queryByTestId("timeline-waiting")).toBeNull();
  });

  it("marks a failed step in words", () => {
    render(<StepTimeline steps={[step(1, "get_holdings", { status: "ERROR", result_summary: "holdings file missing" })]} waiting={false} />);
    expect(screen.getByTestId("timeline-step")).toHaveTextContent("Failed");
  });

  it("shows an unknown tool by its raw name instead of guessing a description", () => {
    expect(toolLabel("some_new_tool")).toBeNull();
    render(<StepTimeline steps={[step(1, "some_new_tool")]} waiting={false} />);
    const row = screen.getByTestId("timeline-step");
    expect(row).toHaveTextContent("some_new_tool");
    expect(row).not.toHaveTextContent("·  ·");
  });

  it("is a polite log, so new steps are announced as they arrive", () => {
    render(<StepTimeline steps={[]} waiting />);
    const log = screen.getByRole("log");
    expect(log).toHaveAttribute("aria-live", "polite");
  });
});
