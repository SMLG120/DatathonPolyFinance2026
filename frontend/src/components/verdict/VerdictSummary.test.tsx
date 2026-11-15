import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { Summary } from "@/lib/contracts";
import { probe, recorded } from "@/test/probes";
import { LIVE_CONFIG, renderWithApp } from "@/test/render";
import { VerdictSummary } from "./VerdictSummary";

function renderSummary(summary: Summary, options: Parameters<typeof renderWithApp>[1] = {}) {
  const view = renderWithApp(<VerdictSummary summary={summary} scope="After the purchase" />, options);
  return { ...view, card: screen.getByTestId("verdict-summary"), headline: screen.getByTestId("verdict-headline").textContent ?? "" };
}

const SAYS_RESPECTED = /\b(all|every)\b.*\brespected\b|\brule is respected\b|\brules are respected\b/i;

describe("VerdictSummary, on recorded summaries", () => {
  it("states Robert's two failures in the fail tone, with the engine's three counts", () => {
    const summary = recorded.robertResult().summary;
    const { headline, card } = renderSummary(summary);
    expect(headline).toBe("2 of 2 confirmed rules are not respected");
    expect(card).toHaveAttribute("data-tone", "fail");
    expect(card).toHaveAttribute("data-headline", "HAS_FAIL");
    expect(screen.getByTestId("count-fail")).toHaveAttribute("data-count", String(summary.counts.fail));
    expect(screen.getByTestId("count-unknown")).toHaveAttribute("data-count", String(summary.counts.unknown));
    expect(screen.getByTestId("count-pass")).toHaveAttribute("data-count", String(summary.counts.pass));
  });

  it("does not report a pass for Mateo's preview: one rule is unknown", () => {
    const { headline, card } = renderSummary(recorded.mateoPreviewUnknown().summary);
    expect(headline).toBe("Not determined: 1 of 1 confirmed rule could not be checked");
    expect(headline).not.toMatch(SAYS_RESPECTED);
    expect(card).toHaveAttribute("data-tone", "unknown");
    expect(card).toHaveTextContent("this is not a pass");
  });

  it("gives a request that was not evaluated no verdict tone", () => {
    const { headline, card } = renderSummary(recorded.invalidRequest().summary);
    expect(headline).toBe("This request cannot be evaluated");
    expect(card).toHaveAttribute("data-tone", "none");
  });

  it("always shows all three counts, zeros included, each as a number with a word and an icon", () => {
    renderSummary(recorded.robertResult().summary);
    for (const [kind, word, shape] of [
      ["fail", "Fail", "octagon"],
      ["unknown", "Unknown", "diamond"],
      ["pass", "Pass", "circle"],
    ] as const) {
      const chip = screen.getByTestId(`count-${kind}`);
      expect(chip).toHaveTextContent(word);
      expect(chip.querySelector(`svg[data-shape="${shape}"]`)).not.toBeNull();
      expect(within(chip).getByText(chip.getAttribute("data-count") as string)).toBeInTheDocument();
    }
  });
});

describe("VerdictSummary, test data marker", () => {
  it("carries the “Test data” tag on the card itself in fixtures mode", () => {
    const { card } = renderSummary(recorded.robertResult().summary);
    expect(card).toHaveAttribute("data-figures", "true");
    expect(within(card).getByTestId("test-data-tag")).toHaveTextContent("Test data");
  });

  it("carries no such tag on the live service", () => {
    const { card } = renderSummary(recorded.robertResult().summary, { config: LIVE_CONFIG });
    expect(within(card).queryByTestId("test-data-tag")).toBeNull();
  });
});

describe("VerdictSummary, wording no recording exercises", () => {
  it("says the rules are respected only when the engine says so and its counts agree", () => {
    const { headline, card } = renderSummary(probe.summaryWith("ALL_PASS", { pass: 3, fail: 0, unknown: 0, evaluated: 3 }));
    expect(headline).toBe("All 3 confirmed rules are respected");
    expect(card).toHaveAttribute("data-tone", "pass");
  });

  it("states a fail and still mentions the unknowns", () => {
    const { headline, card } = renderSummary(probe.summaryWith("HAS_FAIL", { pass: 1, fail: 1, unknown: 1, evaluated: 3 }));
    expect(headline).toBe("1 of 3 confirmed rules is not respected");
    expect(card).toHaveAttribute("data-tone", "fail");
    expect(card).toHaveTextContent("1 more could not be determined");
  });

  it("never says 'respected' and never uses the pass tone when anything failed or is unknown (all small combinations)", () => {
    for (let pass = 0; pass <= 2; pass += 1) {
      for (let fail = 0; fail <= 2; fail += 1) {
        for (let unknown = 0; unknown <= 2; unknown += 1) {
          if (fail === 0 && unknown === 0) continue;
          for (const headlineCode of ["ALL_PASS", "HAS_FAIL", "NO_FAIL_BUT_UNKNOWN"] as const) {
            const { headline, card, unmount } = renderSummary(probe.summaryWith(headlineCode, { pass, fail, unknown, evaluated: pass + fail + unknown }));
            expect(headline, `${headlineCode} ${pass}/${fail}/${unknown}`).not.toMatch(SAYS_RESPECTED);
            expect(card.getAttribute("data-tone"), `${headlineCode} ${pass}/${fail}/${unknown}`).not.toBe("pass");
            unmount();
          }
        }
      }
    }
  });

  it("shows the counts the engine sent even when its headline contradicts them, and makes no overall statement", () => {
    const { headline, card } = renderSummary(probe.summaryWith("ALL_PASS", { pass: 1, fail: 1, unknown: 0, evaluated: 2 }));
    expect(headline).toBe("The summary of this result is inconsistent");
    expect(card).toHaveAttribute("data-tone", "none");
    expect(screen.getByTestId("count-fail")).toHaveAttribute("data-count", "1");
  });

  it("says that nothing was checked instead of implying a pass when there are no rules", () => {
    const { headline, card } = renderSummary(probe.summaryWith("NO_RULES_EVALUATED", { pass: 0, fail: 0, unknown: 0, evaluated: 0 }));
    expect(headline).toBe("No confirmed rule was checked");
    expect(card).toHaveAttribute("data-tone", "none");
  });
});

describe("VerdictSummary, in-page links", () => {
  it("moves focus to the section's heading without changing the stage in the address", async () => {
    const user = userEvent.setup();
    window.location.hash = "#/verdict";
    renderWithApp(
      <>
        <VerdictSummary summary={recorded.robertResult().summary} scope="After the purchase" links={[{ id: "a-panel", label: "A panel" }, { id: "a-section", label: "A closed section" }]} />
        <section id="a-panel">
          <h2 id="a-panel-title" tabIndex={-1}>
            Panel
          </h2>
        </section>
        <details id="a-section">
          <summary>Closed section</summary>
          <p>Inside</p>
        </details>
      </>,
    );
    const links = within(screen.getByRole("navigation", { name: "Sections of this report" }));

    await user.click(links.getByRole("link", { name: "A panel" }));
    expect(screen.getByRole("heading", { name: "Panel" })).toHaveFocus();
    expect(window.location.hash).toBe("#/verdict");

    const closed = document.getElementById("a-section") as HTMLDetailsElement;
    expect(closed.open).toBe(false);
    await user.click(links.getByRole("link", { name: "A closed section" }));
    expect(closed.open).toBe(true);
    expect(closed.querySelector("summary")).toHaveFocus();
    expect(window.location.hash).toBe("#/verdict");
  });
});
