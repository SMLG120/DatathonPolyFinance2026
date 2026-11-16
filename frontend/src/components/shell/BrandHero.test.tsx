import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { isStageId } from "@/state/stage";
import { BrandHero, BRAND_TAGLINE } from "./BrandHero";

describe("BrandHero", () => {
  it("shows the exact headline and subtitle", () => {
    render(<BrandHero />);
    expect(screen.getByTestId("brand-headline")).toHaveTextContent("Invest with conviction.Not contradiction.");
    expect(screen.getByTestId("brand-subtitle")).toHaveTextContent(
      "Your AI-powered investment decision investigator. Uncover hidden exposure, verify your financial rules, and understand every trade before you commit.",
    );
    expect(BRAND_TAGLINE).toBe("ETHOS — The AI Agent That Challenges Your Investments Before the Market Does.");
  });

  it("links both calls to action to stages that exist", () => {
    render(<BrandHero />);
    const primary = screen.getByRole("link", { name: "Analyze My Portfolio" });
    const secondary = screen.getByRole("link", { name: "Explore 3D Portfolio" });
    for (const link of [primary, secondary]) {
      const href = link.getAttribute("href") ?? "";
      expect(href.startsWith("#/")).toBe(true);
      expect(isStageId(href.slice(2))).toBe(true);
    }
    expect(primary).toHaveAttribute("href", "#/purchase");
    expect(secondary).toHaveAttribute("href", "#/verdict");
  });

  it("adds no heading, so each stage keeps its single h1", () => {
    render(<BrandHero />);
    expect(screen.queryAllByRole("heading")).toHaveLength(0);
  });
});
