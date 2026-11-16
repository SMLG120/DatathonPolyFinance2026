import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { go, renderApp, toVerdict } from "@/test/app";
import { BRAND_TAGLINE } from "./BrandHero";

describe("BrandHero", () => {
  it("shows the exact headline, subtitle and tagline on the first screen", async () => {
    renderApp();
    await screen.findByTestId("portfolio-table");
    expect(screen.getByTestId("brand-headline")).toHaveTextContent("Invest with conviction.Not contradiction.");
    expect(screen.getByTestId("brand-subtitle")).toHaveTextContent(
      "Your AI-powered investment decision investigator. Uncover hidden exposure, verify your financial rules, and understand every trade before you commit.",
    );
    expect(BRAND_TAGLINE).toBe("ETHOS — The AI Agent That Challenges Your Investments Before the Market Does.");
    expect(screen.getByTestId("brand-tagline")).toHaveTextContent(BRAND_TAGLINE);
  });

  it("adds no heading, so the stage keeps its single h1", async () => {
    renderApp();
    await screen.findByTestId("portfolio-table");
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getByTestId("brand-hero").querySelector("h1, h2, h3, h4")).toBeNull();
  });

  it("with no result, both calls to action lead to the purchase step and the 3D one says why", async () => {
    renderApp();
    await screen.findByTestId("portfolio-table");
    expect(screen.getByRole("link", { name: "Analyze My Portfolio" })).toHaveAttribute("href", "#/purchase");
    const explore = screen.getByRole("link", { name: "Explore 3D Portfolio" });
    expect(explore).toHaveAttribute("href", "#/purchase");
    expect(explore).toHaveAccessibleDescription(/none has been checked in this session yet/);
  });

  it("with a result, the 3D call to action opens the exposure section of the report", async () => {
    const user = await toVerdict();
    await screen.findByTestId("report");
    expect(document.getElementById("report-exposure")).not.toHaveAttribute("open");

    await go("persona");
    const explore = screen.getByRole("link", { name: "Explore 3D Portfolio" });
    expect(explore).toHaveAttribute("href", "#/verdict");
    expect(explore).toHaveAccessibleDescription("Opens the 3D exposure view of the latest result in this session.");

    await user.click(explore);
    // jsdom does not follow a link's hash, so the navigation the href performs in a browser is made here.
    await go("verdict");
    await waitFor(() => expect(document.getElementById("report-exposure")).toHaveAttribute("open"));
    expect(screen.getByTestId("exposure-explorer")).toBeInTheDocument();
  });
});
