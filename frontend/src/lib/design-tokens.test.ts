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

  it("keeps status colours distinguishable from body text only with a word and an icon (documented, not by colour)", () => {
    // The three status colours are all dark; they are not expected to differ
    // strongly from each other. This test pins that the design does not rely on it.
    expect(tokens.pass).not.toBe(tokens.fail);
    expect(tokens.fail).not.toBe(tokens.unknown);
  });
});
