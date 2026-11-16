import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { App } from "@/components/App";
import { renderApp } from "@/test/app";
import { BRAND_TAGLINE } from "./BrandHero";

describe("BrandHero", () => {
  it("titles the page ETHOS in the HTML the build writes, before any script runs", () => {
    // The static export is rendered on the server: this is the title a crawler, a link preview and a slow connection see.
    const html = renderToStaticMarkup(<App />);
    expect(html).toContain("<title>ETHOS: fictional simulation</title>");
    expect(html).toContain(">ETHOS</h1>");
    expect(html).not.toContain("Before You Buy");
  });

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

  it("has one call to action that starts at step 1 and never jumps ahead", async () => {
    renderApp();
    await screen.findByTestId("portfolio-table");
    const hero = screen.getByTestId("brand-hero");
    // No link out of the first step: a jump to a later step would skip the profile and the limits.
    expect(hero.querySelectorAll("a")).toHaveLength(0);
    expect(screen.queryByText("Explore 3D Portfolio")).toBeNull();
    expect(screen.queryByText("Analyze My Portfolio")).toBeNull();
    expect(screen.getByRole("button", { name: "Start with a profile" })).toBeInTheDocument();
  });

  it("the call to action moves focus to the persona chooser on the same step", async () => {
    const user = userEvent.setup();
    renderApp();
    await screen.findByTestId("portfolio-table");
    const before = window.location.hash;
    await user.click(screen.getByRole("button", { name: "Start with a profile" }));
    expect(screen.getByRole("heading", { name: "Who would you like to try?" })).toHaveFocus();
    expect(window.location.hash).toBe(before);
  });
});
