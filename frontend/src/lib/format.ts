/**
 * The only place where data becomes display text.
 *
 * Data stays in portfolio fractions everywhere else (10% = 0.10). These
 * functions decide how a fraction, a range, a gap, a date and an UNKNOWN are
 * worded, so the wording is identical on every screen and is unit-tested once.
 */

import { EPS } from "@/lib/contracts";

/** The contract's tolerance. Used here for wording only, never for a verdict. */
export { EPS };

export const UNKNOWN_TEXT = "Unknown";
export const NOT_SET_TEXT = "Not set";

/** A real minus sign: read as "minus" by screen readers, unlike a hyphen. */
const MINUS = "−";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"] as const;

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

/**
 * Moves the decimal point without binary floating-point drift:
 * 0.265 shifted by 3 is exactly 265, where 0.265 * 1000 is 264.99999999999994.
 */
export function shiftDecimal(value: number, places: number): number {
  if (value === 0) return 0;
  const [mantissa, exponent] = value.toExponential().split("e");
  return Number(`${mantissa}e${Number(exponent) + places}`);
}

function roundHalfAwayFromZero(value: number): number {
  return Math.sign(value) * Math.round(Math.abs(value));
}

function scaledToText(scaled: number, decimals: number): string {
  const digits = String(Math.abs(scaled)).padStart(decimals + 1, "0");
  const whole = digits.slice(0, digits.length - decimals);
  const fractional = digits.slice(digits.length - decimals);
  return decimals > 0 ? `${whole}.${fractional}` : whole;
}

export interface FormatFractionOptions {
  /** Decimal places of the percentage. Default 1 ("26.5%"). */
  decimals?: number;
  /** Prefix positive values with "+" (used for changes and returns). */
  signed?: boolean;
  /**
   * "down" truncates toward zero instead of rounding to nearest. Used for a
   * maximum, so the displayed figure is never larger than the real boundary.
   */
  rounding?: "nearest" | "down";
}

/** The fraction as a whole number of units of the last decimal shown: 0.265 at one decimal is 265. */
function scaleFraction(value: number, decimals: number, rounding: FormatFractionOptions["rounding"] = "nearest"): number {
  const shifted = shiftDecimal(value, 2 + decimals);
  return rounding === "down" ? Math.sign(shifted) * Math.floor(Math.abs(shifted) + 1e-7) : roundHalfAwayFromZero(shifted);
}

/**
 * Formats a portfolio fraction as a percentage: 0.265 -> "26.5%".
 * Anything that is not a finite number is worded "Unknown", never "0.0%".
 *
 * A value that is not zero is never printed as zero. One too small for the
 * decimals shown is printed as a bound at the last decimal instead:
 * 0.00048735 -> "< 0.1%", -0.0004 -> "> −0.1%". "Not zero" means further from
 * zero than the contract's tolerance, so the noise of a sum of floats still
 * reads "0.0%". This is wording only: the value itself is never changed.
 */
export function formatFraction(value: number | null | undefined, options: FormatFractionOptions = {}): string {
  if (!isFiniteNumber(value)) return UNKNOWN_TEXT;
  const decimals = options.decimals ?? 1;
  const scaled = scaleFraction(value, decimals, options.rounding);
  if (scaled === 0 && Math.abs(value) > EPS) {
    const smallestShown = `${scaledToText(1, decimals)}%`;
    return value < 0 ? `> ${MINUS}${smallestShown}` : `< ${options.signed ? "+" : ""}${smallestShown}`;
  }
  const sign = scaled < 0 ? MINUS : options.signed && scaled > 0 ? "+" : "";
  return `${sign}${scaledToText(scaled, decimals)}%`;
}

/**
 * Formats a possible range (LEAD_DECISIONS D4): "3.9% to 18.9%".
 * A range whose bounds are the same number is a single value: "26.5%".
 * A missing bound makes the whole range "Unknown".
 */
export function formatFractionRange(
  lower: number | null | undefined,
  upper: number | null | undefined,
  options: FormatFractionOptions = {},
): string {
  if (!isFiniteNumber(lower) || !isFiniteNumber(upper)) return UNKNOWN_TEXT;
  if (Math.abs(upper - lower) <= EPS) return formatFraction(lower, options);
  const decimals = decimalsToDistinguish(lower, upper, options.decimals ?? 1);
  const from = formatFraction(lower, { ...options, decimals });
  const to = formatFraction(upper, { ...options, decimals });
  // Two bounds that read the same even at the most decimals shown are worded once, not as "X to X".
  return from === to ? from : `${from} to ${to}`;
}

/** True when a measured interval is a real range rather than one number. */
export function isRange(lower: number | null | undefined, upper: number | null | undefined): boolean {
  return isFiniteNumber(lower) && isFiniteNumber(upper) && Math.abs(upper - lower) > EPS;
}

const MAX_DECIMALS = 4;

/**
 * Smallest number of decimals (from `start`, at most 4) at which two different
 * values round to different figures. Without this a measured 10.04% against a
 * 10.0% limit would read "10.0% vs 10.0% — FAIL". The rounded figures are
 * compared, not the texts, so 0 and 0.0003 read "0.00%" and "0.03%" rather
 * than "0.0%" and "< 0.1%".
 */
export function decimalsToDistinguish(a: number, b: number, start = 1): number {
  if (Math.abs(a - b) <= EPS) return start;
  for (let decimals = start; decimals < MAX_DECIMALS; decimals += 1) {
    if (scaleFraction(a, decimals) !== scaleFraction(b, decimals)) return decimals;
  }
  return MAX_DECIMALS;
}

/**
 * Formats a difference between two fractions in percentage points:
 * 0.165 -> "16.5 points". Always unsigned; the caller words the direction.
 */
export function formatPoints(value: number | null | undefined, decimals = 1): string {
  if (!isFiniteNumber(value)) return UNKNOWN_TEXT;
  const scaled = Math.abs(roundHalfAwayFromZero(shiftDecimal(value, 2 + decimals)));
  const text = scaledToText(scaled, decimals);
  return `${text} ${Number(text) === 1 ? "point" : "points"}`;
}

/**
 * Words a change between two weights in percentage points, with its direction:
 * 0.25 -> "+25.0 points", -0.25 -> "−25.0 points", 0 -> "No change".
 */
export function formatChange(delta: number | null | undefined, decimals = 1): string {
  if (!isFiniteNumber(delta)) return UNKNOWN_TEXT;
  if (Math.abs(delta) <= EPS) return "No change";
  return `${delta > 0 ? "+" : MINUS}${formatPoints(delta, decimals)}`;
}

/**
 * How much of a fund its holdings file reports: 0.998 -> "99.8%".
 * Truncated, never rounded up, so a fund that reports 99.96% of its weight is
 * not displayed as "100.0%" next to the word "Partial".
 */
export function formatCoverage(value: number | null | undefined): string {
  return formatFraction(value, { rounding: "down" });
}

/** A return over a period, signed, to two decimals: -0.1525 -> "−15.25%". */
export function formatReturn(value: number | null | undefined): string {
  return formatFraction(value, { decimals: 2, signed: true });
}

export type LimitDirection = "max" | "min";

/**
 * Words the gap the service reports between a measured value and its limit.
 * `gap` is the contract's: positive is the size of the breach, zero or
 * negative is headroom, null means it cannot be determined. It is worded,
 * never recomputed.
 */
export function formatGap(
  gap: number | null | undefined,
  direction: LimitDirection = "max",
  noun: string = direction === "max" ? "limit" : "minimum",
  startDecimals = 1,
): string {
  if (!isFiniteNumber(gap)) return "Cannot be determined";
  if (Math.abs(gap) <= EPS) return `Exactly at the ${noun}`;
  let decimals = startDecimals;
  while (decimals < MAX_DECIMALS && Number(formatPoints(gap, decimals).split(" ")[0]) === 0) decimals += 1;
  const points = formatPoints(gap, decimals);
  if (direction === "max") return gap > 0 ? `${points} over the ${noun}` : `${points} under the ${noun}`;
  return gap > 0 ? `${points} below the ${noun}` : `${points} above the ${noun}`;
}

/** "12 Nov 2026" from "2026-11-12". Parsed as text so no time zone can shift the day. */
export function formatDate(iso: string | null | undefined): string {
  if (typeof iso !== "string") return UNKNOWN_TEXT;
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!match) return UNKNOWN_TEXT;
  const [, year, month, day] = match;
  const monthName = MONTHS[Number(month) - 1];
  const dayNumber = Number(day);
  if (!monthName || dayNumber < 1 || dayNumber > 31) return UNKNOWN_TEXT;
  return `${dayNumber} ${monthName} ${year}`;
}

/** "14 Nov 2026, 15:02:11 UTC" from an ISO timestamp. */
export function formatDateTime(iso: string | null | undefined): string {
  const time = formatTime(iso);
  const date = formatDate(iso);
  if (time === UNKNOWN_TEXT || date === UNKNOWN_TEXT) return UNKNOWN_TEXT;
  return `${date}, ${time}`;
}

/** "15:02:11 UTC" from an ISO timestamp. Always UTC so a recording reads the same everywhere. */
export function formatTime(iso: string | null | undefined): string {
  if (typeof iso !== "string") return UNKNOWN_TEXT;
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime()) || !/T\d{2}:\d{2}/.test(iso)) return UNKNOWN_TEXT;
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${pad(parsed.getUTCHours())}:${pad(parsed.getUTCMinutes())}:${pad(parsed.getUTCSeconds())} UTC`;
}

/** Text for a percentage form field: 0.1 -> "10", 0.125 -> "12.5", null -> "". */
export function fractionToPercentInput(value: number | null | undefined): string {
  if (!isFiniteNumber(value)) return "";
  return String(shiftDecimal(roundHalfAwayFromZero(shiftDecimal(value, 6)), -4));
}

/**
 * Reads a percentage typed by the user back into a fraction: "12.5" -> 0.125.
 * Empty or malformed text is null — it is never read as zero.
 */
export function percentInputToFraction(text: string): number | null {
  const trimmed = text.trim().replace(/%$/, "").trim();
  if (!/^\d+(\.\d+)?$|^\.\d+$/.test(trimmed)) return null;
  const parsed = Number(trimmed);
  if (!Number.isFinite(parsed)) return null;
  return shiftDecimal(parsed, -2);
}
