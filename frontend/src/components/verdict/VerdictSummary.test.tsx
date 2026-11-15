import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { countStatuses } from "@/lib/verdict";
import type { VerdictStatus } from "@/lib/contracts";
import { VerdictSummary } from "./VerdictSummary";

function statuses(pass: number, fail: number, unknown: number): VerdictStatus[] {
  return [...Array<VerdictStatus>(pass).fill("PASS"), ...Array<VerdictStatus>(fail).fill("FAIL"), ...Array<VerdictStatus>(unknown).fill("UNKNOWN")];
}

function renderSummary(pass: number, fail: number, unknown: number) {
  const view = render(<VerdictSummary counts={countStatuses(statuses(pass, fail, unknown))} scope="After the purchase" />);
  return { ...view, summary: screen.getByTestId("verdict-summary"), headline: screen.getByTestId("verdict-headline").textContent ?? "" };
}

const SAYS_RESPECTED = /\b(all|every)\b.*\brespected\b|\bis respected\b|\bare respected\b/i;

describe("VerdictSummary", () => {
  it("says the rules are respected only when every rule passed", () => {
    const { headline, summary } = renderSummary(3, 0, 0);
    expect(headline).toBe("All 3 confirmed rules are respected");
    expect(summary).toHaveAttribute("data-tone", "pass");
  });

  it("does not report a pass when one rule is unknown and the rest pass", () => {
    const { headline, summary } = renderSummary(2, 0, 1);
    expect(headline).toBe("Not determined: 1 of 3 confirmed rules could not be checked");
    expect(headline).not.toMatch(SAYS_RESPECTED);
    expect(summary).toHaveAttribute("data-tone", "unknown");
    expect(summary).toHaveTextContent("this is not a pass");
  });

  it("states a fail and still mentions the unknowns", () => {
    const { headline, summary } = renderSummary(1, 1, 1);
    expect(headline).toBe("1 of 3 confirmed rules is not respected");
    expect(summary).toHaveAttribute("data-tone", "fail");
    expect(summary).toHaveTextContent("1 more could not be determined");
  });

  it("never says 'respected' and never uses the pass tone when anything failed or is unknown (all small combinations)", () => {
    for (let pass = 0; pass <= 3; pass += 1) {
      for (let fail = 0; fail <= 3; fail += 1) {
        for (let unknown = 0; unknown <= 3; unknown += 1) {
          if (fail === 0 && unknown === 0) continue;
          const { headline, summary, unmount } = renderSummary(pass, fail, unknown);
          expect(headline, `pass=${pass} fail=${fail} unknown=${unknown}`).not.toMatch(SAYS_RESPECTED);
          expect(summary.getAttribute("data-tone")).not.toBe("pass");
          unmount();
        }
      }
    }
  });

  it("always shows all three counts, zeros included, each as a number with a word and an icon", () => {
    const { summary } = renderSummary(2, 0, 1);
    for (const [kind, count, word] of [
      ["fail", "0", "Fail"],
      ["unknown", "1", "Unknown"],
      ["pass", "2", "Pass"],
    ] as const) {
      const chip = within(summary).getByTestId(`count-${kind}`);
      expect(chip).toHaveAttribute("data-count", count);
      expect(chip).toHaveTextContent(`${count}${word}`);
      expect(chip.querySelector("svg")).not.toBeNull();
    }
  });

  it("says that nothing was checked instead of implying a pass when there are no rules", () => {
    const { headline, summary } = renderSummary(0, 0, 0);
    expect(headline).toBe("No confirmed rule was checked");
    expect(summary).toHaveAttribute("data-tone", "none");
  });
});
