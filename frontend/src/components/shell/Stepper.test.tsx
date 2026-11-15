import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { JOURNEY, type StageId } from "@/state/stage";
import { Stepper } from "./Stepper";

describe("Stepper", () => {
  it("is a navigation landmark with one link per stage, in order, each naming its position", () => {
    render(<Stepper current="persona" completed={new Set()} />);
    const nav = screen.getByRole("navigation", { name: "Stages of the simulation" });
    expect(nav).toBeInTheDocument();
    const links = screen.getAllByRole("link");
    expect(links.map((link) => link.getAttribute("href"))).toEqual(["#/persona", "#/purchase", "#/verdict"]);
    expect(links.map((link) => link.textContent?.replace(/\s+/g, " ").trim())).toEqual(
      JOURNEY.map((stage) => expect.stringContaining(`Step ${stage.number} of 3: ${stage.title}`)),
    );
  });

  it("marks exactly the current stage with aria-current=step", () => {
    render(<Stepper current="purchase" completed={new Set<StageId>(["persona", "goals"])} />);
    const current = screen.getAllByRole("link").filter((link) => link.getAttribute("aria-current") === "step");
    expect(current).toHaveLength(1);
    expect(current[0]).toHaveAccessibleName("Step 2 of 3: Test an idea");
  });

  it("says in words which stages are completed", () => {
    render(<Stepper current="purchase" completed={new Set<StageId>(["persona", "goals", "purchase"])} />);
    expect(screen.getByRole("link", { name: "Step 1 of 3: Choose a profile (completed)" })).toBeInTheDocument();

    // The current stage is announced as current, not as completed.
    expect(screen.getByRole("link", { name: "Step 2 of 3: Test an idea" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Step 3 of 3: Understand the result" })).toBeInTheDocument();
  });

  it("keeps every visible short label inside the accessible name (WCAG 2.5.3)", () => {
    for (const stage of JOURNEY) {
      expect(`Step ${stage.number} of 3: ${stage.title}`.toLowerCase()).toContain(stage.short.toLowerCase());
    }
  });
});
