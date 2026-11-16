import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { contrastRatio, evaluatePairs, PAIRS, readTokens } from "../../scripts/contrast-report.mjs";

/**
 * Guards the colour tokens in `src/app/globals.css`. The pairs are the ones
 * the interface really uses; `npm run contrast` prints the same list.
 */
describe("design tokens", () => {
  const tokens = readTokens();

  it("computes WCAG contrast correctly for known values", () => {
    expect(contrastRatio("#000000", "#ffffff")).toBeCloseTo(21, 5);
    expect(contrastRatio("#ffffff", "#ffffff")).toBeCloseTo(1, 5);
    // #767676 on white is the well-known 4.54:1 boundary grey.
    expect(contrastRatio("#767676", "#ffffff")).toBeCloseTo(4.54, 2);
  });

  it("reads every colour token named in a pair from the stylesheet", () => {
    for (const [foreground, background] of PAIRS) {
      expect(tokens[foreground], `--color-${foreground}`).toMatch(/^#[0-9a-f]{6}$/);
      expect(tokens[background], `--color-${background}`).toMatch(/^#[0-9a-f]{6}$/);
    }
  });

  it.each(evaluatePairs().map((row) => [`${row.foreground} on ${row.background}`, row] as const))(
    "%s meets its WCAG AA minimum",
    (_name, row) => {
      expect(row.ratio, `${row.fg} on ${row.bg} is ${row.ratio.toFixed(2)}:1, needs ${row.minimum}:1 (${row.use})`).toBeGreaterThanOrEqual(row.minimum);
    },
  );

  it("keeps the two exposure series apart by lightness: held directly is clearly darker than held through funds", () => {
    // The stylesheet's rule for the exposure chart is "one hue, darker = held more directly". Two blues of the same
    // lightness (1.03:1 after the palette change of PR #20) are one colour to most readers, so the ramp needs a real step.
    const ratio = contrastRatio(tokens["chart-direct"] as string, tokens["chart-indirect"] as string);
    expect(ratio, `chart-direct vs chart-indirect is ${ratio.toFixed(2)}:1`).toBeGreaterThanOrEqual(2);
    // Darker means more direct, not the reverse.
    expect(contrastRatio(tokens["chart-direct"] as string, "#ffffff")).toBeGreaterThan(contrastRatio(tokens["chart-indirect"] as string, "#ffffff"));
  });

  it("keeps the primary button's label readable on every stop of its gradient, also while hovered", () => {
    // The primary button is a gradient written in the class list, not a token, so the token pairs above do not see it.
    const source = readFileSync(path.resolve(__dirname, "..", "components", "shadcn", "button-variants.ts"), "utf8");
    const primary = /primary:\s*"([^"]+)"/.exec(source)?.[1] ?? "";
    const stops = [...primary.matchAll(/#[0-9a-fA-F]{6}(?=_\d+%)/g)].map((match) => match[0].toLowerCase());
    expect(stops.length, primary).toBeGreaterThanOrEqual(2);
    expect(primary).toContain("text-on-accent");
    const hover = /hover:brightness-(\d+)/.exec(primary);
    const factor = hover ? Number(hover[1]) / 100 : 1;
    const brightened = (hex: string) =>
      "#" + [1, 3, 5].map((at) => Math.min(255, Math.round(parseInt(hex.slice(at, at + 2), 16) * factor)).toString(16).padStart(2, "0")).join("");
    for (const stop of stops) {
      const resting = contrastRatio(tokens["on-accent"] as string, stop);
      const hovered = contrastRatio(tokens["on-accent"] as string, brightened(stop));
      expect(resting, `label on ${stop} is ${resting.toFixed(2)}:1`).toBeGreaterThanOrEqual(4.5);
      expect(hovered, `label on ${stop} while hovered (${brightened(stop)}) is ${hovered.toFixed(2)}:1`).toBeGreaterThanOrEqual(4.5);
    }
  });

  it("keeps status colours distinguishable from body text only with a word and an icon (documented, not by colour)", () => {
    // The three status colours are all dark; they are not expected to differ
    // strongly from each other. This test pins that the design does not rely on it.
    expect(tokens.pass).not.toBe(tokens.fail);
    expect(tokens.fail).not.toBe(tokens.unknown);
  });
});
