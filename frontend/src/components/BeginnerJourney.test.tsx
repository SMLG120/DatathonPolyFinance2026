import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { AppShell } from "@/components/shell/AppShell";
import { Button } from "@/components/ui/Button";
import { Report } from "@/components/verdict/Report";
import { WhatNext } from "@/components/verdict/WhatNext";
import type { CheckResult } from "@/lib/contracts";
import { summaryCounts } from "@/lib/verdict";
import { confirmScenarioRules, go, renderApp, stageHeading } from "@/test/app";
import { recorded } from "@/test/probes";
import { FIXTURES_CONFIG, renderWithApp } from "@/test/render";

/** What a first-time user needs: what the tool does, four visible steps, a plain reading of the result, and no lost work. */
describe("a first-time user's journey", () => {
  it("says on the first screen what the tool does and the four steps, before the profiles", async () => {
    renderApp();
    const intro = await screen.findByTestId("how-it-works");
    expect(within(intro).getByRole("heading", { name: "What this tool does" })).toBeInTheDocument();
    expect(intro).toHaveTextContent("gives no advice and places no trade");
    expect(within(intro).getAllByRole("listitem").map((item) => item.querySelector(".block")?.textContent)).toEqual([
      "Choose a profile", "Set your limits", "Test an idea", "Understand the result",
    ]);
    const profiles = screen.getByRole("heading", { name: "Who would you like to try?" });
    expect(intro.compareDocumentPosition(profiles) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("shows setting the limits as a step of its own, and the first screen continues to it", async () => {
    renderApp();
    await screen.findByTestId("how-it-works");
    const nav = screen.getByRole("navigation", { name: "Stages of the simulation" });
    expect(within(nav).getByRole("link", { name: "Step 2 of 4: Set your limits" })).toHaveAttribute("href", "#/goals");
    const next = screen.getByTestId("continue-link");
    expect(next).toHaveAccessibleName("Set your limits");
    expect(next).toHaveAttribute("href", "#/goals");
  });

  it("goes back from the idea to the limits, and keeps the confirmed limits on the way", async () => {
    const user = userEvent.setup();
    renderApp();
    await screen.findByTestId("how-it-works");
    await confirmScenarioRules(user);
    await go("purchase");
    expect(stageHeading()).toHaveTextContent("Step 3 of 4: Test an idea");
    const back = screen.getByRole("link", { name: "Back to your limits" });
    expect(back).toHaveAttribute("href", "#/goals");
    await go("goals");
    expect(screen.getAllByTestId("policy-rule-card").length).toBeGreaterThan(0);
    expect(within(screen.getByRole("navigation", { name: "Stages of the simulation" })).getByRole("link", { name: "Step 2 of 4: Set your limits" })).toHaveAttribute("aria-current", "step");
  });

  it("explains an empty result screen (after a reload) and links to the idea", async () => {
    renderApp();
    await screen.findByTestId("how-it-works");
    await go("verdict");
    expect(screen.getByText("There is no result to show yet")).toBeInTheDocument();
    expect(screen.getByTestId("empty-result-reload-note")).toHaveTextContent("reloading the page");
    expect(screen.getByTestId("empty-result-action")).toHaveAttribute("href", "#/purchase");
  });
});

describe("the Evidence Investigator link", () => {
  it("keeps the test-data mode when it was asked for, and opens in a new tab", () => {
    renderWithApp(<AppShell>content</AppShell>, { config: { ...FIXTURES_CONFIG, fixturesReason: "requested" } });
    const link = screen.getByRole("link", { name: /^Evidence Investigator/ });
    expect(link).toHaveAttribute("href", "/evidence/?fixtures=1");
    expect(link).toHaveAttribute("target", "_blank");
  });
});

describe("What this means and what you can do next", () => {
  const robert = () => recorded.robertJob().result as CheckResult;
  /** The recorded result with other counts: a copy of the engine's own object, only its numbers changed. */
  const withCounts = (pass: number, fail: number, unknown: number): CheckResult => {
    const copy = structuredClone(robert());
    Object.assign(copy.summary.counts, { pass, fail, unknown });
    copy.summary.rules_evaluated = pass + fail + unknown;
    return copy;
  };

  it("reads the engine's own counts in plain words, says it is not advice, and offers the next actions", () => {
    const result = robert();
    const counts = summaryCounts(result.summary);
    renderWithApp(<Report job={recorded.robertJob()} result={result} policy={recorded.robertPolicyV1()} objectives={[]} instruments={recorded.robertPortfolio().instruments} />);
    const box = screen.getByTestId("what-next");
    expect(screen.getByTestId("what-next-meaning")).toHaveTextContent(`This idea goes over ${counts.fail} of the ${counts.total} limits you confirmed.`);
    expect(box).toHaveTextContent("not advice");
    const actions = within(box).getAllByRole("link").map((link) => link.textContent);
    expect(actions).toContain("Modify my idea");
    expect(actions).toContain("Review or dispute this result");
    expect(actions).toContain("Sources and missing data");
    expect(actions.includes("Largest share that fits my limits")).toBe(result.max_compliant?.status === "SUPPORTED");
  });

  it("never claims a limit is broken when none failed, and says what is undecided", () => {
    const result = withCounts(1, 0, 1);
    renderWithApp(<WhatNext result={result} />);
    const meaning = screen.getByTestId("what-next-meaning");
    expect(meaning).toHaveTextContent("No confirmed limit is shown to be broken, but 1 limit cannot be decided with the data held.");
    expect(meaning).not.toHaveTextContent("goes over");
  });

  it("when every limit passes, says it is no judgment of the investment", () => {
    const result = withCounts(2, 0, 0);
    renderWithApp(<WhatNext result={result} />);
    expect(screen.getByTestId("what-next-meaning")).toHaveTextContent("All 2 limits you confirmed are respected by this idea, on the data held. That says nothing about whether the investment itself is a good one.");
  });
});

describe("an unavailable primary button", () => {
  it("drops the primary gradient so its grey label stays readable", () => {
    renderWithApp(<Button variant="primary" softDisabled>Check my idea</Button>);
    expect(screen.getByRole("button", { name: "Check my idea" }).className).toMatch(/\bbg-none\b/);
  });
});
