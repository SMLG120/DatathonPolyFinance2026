import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { InvestigationStep, ToolName } from "@/lib/contracts";
import { FIXTURES } from "@/lib/fixtures";
import { recorded } from "@/test/probes";
import { StepTimeline, toolLabel } from "./StepTimeline";

/** The steps of the recorded jobs. Every row a test expects is a row a recording holds. */
const finished = () => recorded.robertJob().steps;
const running = () => structuredClone(FIXTURES.jobs.robertRunning.response.steps);
const queued = () => structuredClone(FIXTURES.jobs.robertQueued.response.steps);
const failed = () => recorded.failedJob().steps;

function stepOf(steps: InvestigationStep[], seq: number): InvestigationStep {
  const step = steps.find((candidate) => candidate.seq === seq);
  if (!step) throw new Error(`The recording has no step ${seq}.`);
  return step;
}

describe("StepTimeline, on the recorded steps", () => {
  it("shows exactly the steps the job reported — no more — in sequence order", () => {
    const steps = finished();
    render(<StepTimeline steps={steps.slice().reverse()} waiting={false} />);
    const rows = screen.getAllByTestId("timeline-step");
    expect(rows).toHaveLength(steps.length);
    expect(rows[0]).toHaveTextContent("Step 1 · Read the portfolio");
    expect(rows[1]).toHaveTextContent("Step 2 · Read the confirmed policy");
    expect(rows[7]).toHaveTextContent("Step 8 · Find the largest purchase that respects the rules");
    expect(screen.queryByTestId("timeline-waiting")).toBeNull();
  });

  it("shows the tool name, who ran it, the time, and the input and result summaries as the job wrote them", () => {
    const steps = finished();
    render(<StepTimeline steps={steps} waiting={false} />);
    const rows = screen.getAllByTestId("timeline-step");

    const exposure = stepOf(steps, 5);
    const exposureRow = rows[4] as HTMLElement;
    expect(exposure.initiated_by).toBe("MODEL");
    expect(exposureRow).toHaveTextContent("compute_exposure");
    expect(exposureRow).toHaveTextContent("requested by the model");
    expect(exposureRow).toHaveTextContent("finished 15:02:17 UTC");
    expect(within(exposureRow).getByText(exposure.input_summary)).toBeInTheDocument();
    expect(within(exposureRow).getByText(exposure.result_summary as string)).toBeInTheDocument();
    expect(within(exposureRow).getByText("Completed")).toBeInTheDocument();

    // The rule check itself is run by the service whatever the model did.
    const check = stepOf(steps, 7);
    expect(check.initiated_by).toBe("SERVER");
    expect(rows[6]).toHaveTextContent("check_rules");
    expect(rows[6]).toHaveTextContent("run by the server");
    expect(within(rows[6] as HTMLElement).getByText(check.result_summary as string)).toBeInTheDocument();
  });

  it("puts a plain waiting line after the real steps while the job is running, and invents no step", () => {
    // The first four recorded steps are finished; the job has not reported the next one yet.
    const done = running().filter((step) => step.status === "OK");
    render(<StepTimeline steps={done} waiting />);
    expect(screen.getAllByTestId("timeline-step")).toHaveLength(done.length);
    expect(screen.getByTestId("timeline-waiting")).toHaveTextContent("Waiting for the next step");
  });

  it("shows only the waiting line when no step has been reported yet (the recorded queued job)", () => {
    expect(queued()).toHaveLength(0);
    render(<StepTimeline steps={queued()} waiting />);
    expect(screen.queryAllByTestId("timeline-step")).toHaveLength(0);
    expect(screen.getByTestId("timeline-waiting")).toBeInTheDocument();
  });

  it("shows a step as in progress only when the job reports it as running", () => {
    const steps = running();
    render(<StepTimeline steps={steps} waiting />);
    const rows = screen.getAllByTestId("timeline-step");
    expect(rows).toHaveLength(steps.length);
    const last = rows[rows.length - 1] as HTMLElement;
    expect(last).toHaveAttribute("data-step-status", "RUNNING");
    expect(last).toHaveTextContent("In progress");
    expect(last).toHaveTextContent("started 15:02:15 UTC");
    expect(last).toHaveTextContent("Not available yet");
    // The job already says what it is doing: no extra "waiting" line.
    expect(screen.queryByTestId("timeline-waiting")).toBeNull();
  });

  it("marks a failed step in words (the recorded failed job)", () => {
    const steps = failed();
    render(<StepTimeline steps={steps} waiting={false} />);
    const row = screen.getAllByTestId("timeline-step")[1] as HTMLElement;
    expect(row).toHaveAttribute("data-step-status", "ERROR");
    expect(row).toHaveTextContent("Failed");
    expect(within(row).getByText(stepOf(steps, 2).result_summary as string)).toBeInTheDocument();
  });

  it("shows a tool it does not know by its raw name instead of guessing a description", () => {
    expect(toolLabel("some_new_tool")).toBeNull();
    // A recorded step whose tool name a later service version might send.
    const step = { ...stepOf(finished(), 1), tool: "some_new_tool" as ToolName };
    render(<StepTimeline steps={[step]} waiting={false} />);
    const row = screen.getByTestId("timeline-step");
    expect(row).toHaveTextContent("some_new_tool");
    expect(row).not.toHaveTextContent("Step 1 ·");
  });

  it("is a polite log, so new steps are announced as they arrive", () => {
    render(<StepTimeline steps={[]} waiting />);
    const log = screen.getByRole("log");
    expect(log).toHaveAttribute("aria-live", "polite");
  });
});
