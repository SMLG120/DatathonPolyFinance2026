import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { VerdictStatus } from "@/lib/contracts";
import { CoverageBadge, JobStatusBadge, RuleStatusBadge, StatusBadge } from "./Badge";

describe("StatusBadge", () => {
  const cases: [VerdictStatus, string, string][] = [
    ["PASS", "Pass", "circle"],
    ["FAIL", "Fail", "octagon"],
    ["UNKNOWN", "Unknown", "diamond"],
  ];

  it.each(cases)("%s is a word plus an icon with its own shape, not colour alone", (status, word, shape) => {
    const { container } = render(<StatusBadge status={status} />);
    // The word is real text.
    expect(screen.getByText(word)).toBeInTheDocument();
    // The icon exists, has the status's shape, and is decorative (the word carries the meaning).
    const icon = container.querySelector("svg");
    expect(icon).not.toBeNull();
    expect(icon).toHaveAttribute("data-shape", shape);
    expect(icon).toHaveAttribute("aria-hidden", "true");
    expect(container.querySelector(`[data-status="${status}"]`)).not.toBeNull();
  });

  it("gives the three statuses three different shapes", () => {
    const shapes = cases.map(([status]) => render(<StatusBadge status={status} />).container.querySelector("svg")?.getAttribute("data-shape"));
    expect(new Set(shapes).size).toBe(3);
  });

  it("draws UNKNOWN with a dashed outline, a third non-colour cue", () => {
    const unknown = render(<StatusBadge status="UNKNOWN" />).container.querySelector("[data-status] > span");
    const pass = render(<StatusBadge status="PASS" />).container.querySelector("[data-status] > span");
    expect(unknown?.className).toContain("border-dashed");
    expect(pass?.className).not.toContain("border-dashed");
  });

  it("can be prefixed so a preview is never read as a confirmed status", () => {
    render(<StatusBadge status="PASS" prefix="Preview:" />);
    expect(screen.getByText("Preview: Pass")).toBeInTheDocument();
  });
});

describe("other status badges", () => {
  it("words the rule lifecycle so that 'proposed' reads as inactive", () => {
    render(
      <>
        <RuleStatusBadge status="PROPOSED" />
        <RuleStatusBadge status="CONFIRMED" />
        <RuleStatusBadge status="SUPERSEDED" />
      </>,
    );
    expect(screen.getByText("Proposed: inactive")).toBeInTheDocument();
    expect(screen.getByText("Confirmed: active")).toBeInTheDocument();
    expect(screen.getByText("Superseded")).toBeInTheDocument();
  });

  it("never words a finished job as a pass", () => {
    render(<JobStatusBadge status="SUCCEEDED" />);
    expect(screen.getByText("Completed")).toBeInTheDocument();
    expect(screen.queryByText(/pass/i)).toBeNull();
  });

  it("shows missing coverage as words with an icon", () => {
    const { container } = render(<CoverageBadge status="MISSING" />);
    expect(screen.getByText("Missing")).toBeInTheDocument();
    expect(container.querySelector("svg")).not.toBeNull();
  });
});
