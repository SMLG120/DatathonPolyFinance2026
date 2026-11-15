#!/usr/bin/env node
/**
 * WCAG 2.x contrast of the colour pairs this interface actually uses.
 *
 * The colours are read from the `@theme` block of `src/app/globals.css`, so
 * the report cannot drift from the stylesheet. `npm run contrast` prints the
 * table (and exits 1 if a pair is under its minimum);
 * `src/lib/design-tokens.test.ts` imports the same list and asserts it.
 *
 * Minimums: 4.5:1 for text (WCAG 1.4.3), 3:1 for control boundaries, focus
 * indicators and chart marks (WCAG 1.4.11).
 */
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
export const TOKENS_FILE = path.resolve(here, "..", "src", "app", "globals.css");

const TEXT = 4.5;
const GRAPHIC = 3;

/** [foreground token, background token, minimum ratio, where it is used] */
export const PAIRS = [
  // Primary and secondary text on every background it sits on.
  ["ink", "canvas", TEXT, "body text on the page"],
  ["ink", "surface", TEXT, "body text on cards"],
  ["ink", "sunken", TEXT, "text on inset panels"],
  ["ink", "accent-soft", TEXT, "text on the selected row / info notice"],
  ["ink", "pass-soft", TEXT, "text on a pass headline"],
  ["ink", "fail-soft", TEXT, "text on a fail headline / error notice"],
  ["ink", "unknown-soft", TEXT, "text on an unknown headline / caution notice"],
  ["ink-muted", "canvas", TEXT, "secondary text on the page"],
  ["ink-muted", "surface", TEXT, "secondary text on cards"],
  ["ink-muted", "sunken", TEXT, "secondary text on inset panels"],
  ["ink-muted", "accent-soft", TEXT, "secondary text on the selected row"],
  ["ink-muted", "pass-soft", TEXT, "secondary text on a pass headline"],
  ["ink-muted", "fail-soft", TEXT, "secondary text on a fail headline"],
  ["ink-muted", "unknown-soft", TEXT, "secondary text on an unknown block"],
  // Accent: links, buttons, the current step.
  ["accent", "surface", TEXT, "links and secondary buttons on cards"],
  ["accent", "canvas", TEXT, "links on the page"],
  ["accent", "sunken", TEXT, "links on inset panels"],
  ["accent", "accent-soft", TEXT, "link text on a hovered button / info notice"],
  ["accent-strong", "accent-soft", TEXT, "current step, confirmed badge"],
  ["on-accent", "accent", TEXT, "primary button"],
  ["on-accent", "accent-strong", TEXT, "primary button, hovered"],
  // Status words (always next to an icon and a shape).
  ["pass", "pass-soft", TEXT, "Pass badge"],
  ["pass", "surface", TEXT, "pass icon on a card"],
  ["fail", "fail-soft", TEXT, "Fail badge"],
  ["fail", "surface", TEXT, "error message under a field"],
  ["fail", "canvas", TEXT, "error message on the page"],
  ["fail", "sunken", TEXT, "error icon on an inset panel"],
  ["unknown", "unknown-soft", TEXT, "Unknown badge, fixtures label"],
  ["unknown", "surface", TEXT, "unknown icon on a card"],
  // Banner.
  ["on-banner", "banner", TEXT, "simulation label"],
  ["on-banner-muted", "banner", TEXT, "valuation date label"],
  // Non-text: control boundaries, focus ring, chart marks.
  ["line-strong", "surface", GRAPHIC, "input and control borders on cards"],
  ["line-strong", "canvas", GRAPHIC, "dashed borders on the page"],
  ["line-strong", "sunken", GRAPHIC, "borders on inset panels"],
  ["accent", "surface", GRAPHIC, "focus ring on cards"],
  ["accent", "canvas", GRAPHIC, "focus ring on the page"],
  ["on-banner", "banner", GRAPHIC, "focus ring on the banner"],
  ["chart-direct", "surface", GRAPHIC, "chart: direct segment against the gaps and card"],
  ["chart-direct", "chart-track", GRAPHIC, "chart: direct segment against the track"],
  ["chart-indirect", "surface", GRAPHIC, "chart: through-funds segment against the gaps and card"],
  ["chart-indirect", "chart-track", GRAPHIC, "chart: through-funds segment against the track"],
  ["ink", "surface", GRAPHIC, "chart: limit marker against its surface ring"],
];

/** Reads `--color-name: #rrggbb;` declarations from the stylesheet's @theme block. */
export function readTokens(css = readFileSync(TOKENS_FILE, "utf8")) {
  const theme = css.match(/@theme\s*\{([\s\S]*?)\n\}/);
  if (!theme) throw new Error("No @theme block found in globals.css");
  const tokens = {};
  for (const match of theme[1].matchAll(/--color-([a-z0-9-]+):\s*(#[0-9a-fA-F]{6})\s*;/g)) tokens[match[1]] = match[2].toLowerCase();
  return tokens;
}

function channel(value) {
  const c = value / 255;
  return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
}

/** WCAG relative luminance of `#rrggbb`. */
export function luminance(hex) {
  const n = Number.parseInt(hex.slice(1), 16);
  return 0.2126 * channel((n >> 16) & 255) + 0.7152 * channel((n >> 8) & 255) + 0.0722 * channel(n & 255);
}

/** WCAG contrast ratio of two `#rrggbb` colours, from 1 to 21. */
export function contrastRatio(a, b) {
  const [light, dark] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (light + 0.05) / (dark + 0.05);
}

/** Every declared pair with its measured ratio. */
export function evaluatePairs(tokens = readTokens()) {
  return PAIRS.map(([foreground, background, minimum, use]) => {
    const fg = tokens[foreground];
    const bg = tokens[background];
    if (!fg || !bg) throw new Error(`Unknown colour token in pair: ${foreground} on ${background}`);
    const ratio = contrastRatio(fg, bg);
    return { foreground, background, fg, bg, minimum, ratio, pass: ratio >= minimum, use };
  });
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const rows = evaluatePairs();
  const pad = (text, width) => String(text).padEnd(width);
  console.log(`${pad("foreground", 17)}${pad("background", 15)}${pad("ratio", 9)}${pad("min", 6)}${pad("ok", 6)}use`);
  for (const row of rows) {
    console.log(
      `${pad(row.foreground, 17)}${pad(row.background, 15)}${pad(`${row.ratio.toFixed(2)}:1`, 9)}${pad(row.minimum, 6)}${pad(row.pass ? "yes" : "NO", 6)}${row.use}`,
    );
  }
  const failed = rows.filter((row) => !row.pass);
  console.log(`\n${rows.length} pairs checked, ${failed.length} below their minimum.`);
  process.exit(failed.length > 0 ? 1 : 0);
}
