/**
 * The only place where data becomes display text.
 *
 * Data stays in portfolio fractions everywhere else (10% = 0.10). These
 * functions decide how a fraction, a range, a gap, a date and an UNKNOWN are
 * worded, so the wording is identical on every screen and is unit-tested once.
 */

/** Same tolerance as the engine (LEAD_DECISIONS D2). Used for wording only, never for a verdict. */
export const EPS = 1e-9;

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

/**
 * Formats a portfolio fraction as a percentage: 0.265 -> "26.5%".
 * Anything that is not a finite number is worded "Unknown", never "0.0%".
 */
export function formatFraction(value: number | null | undefined, options: FormatFractionOptions = {}): string {
  if (!isFiniteNumber(value)) return UNKNOWN_TEXT;
  const decimals = options.decimals ?? 1;
  const shifted = shiftDecimal(value, 2 + decimals);
  const scaled =
    options.rounding === "down"
      ? Math.sign(shifted) * Math.floor(Math.abs(shifted) + 1e-7)
      : roundHalfAwayFromZero(shifted);
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
  return `${formatFraction(lower, { ...options, decimals })} to ${formatFraction(upper, { ...options, decimals })}`;
}

/** True when a measured interval is a real range rather than one number. */
export function isRange(lower: number | null | undefined, upper: number | null | undefined): boolean {
  return isFiniteNumber(lower) && isFiniteNumber(upper) && Math.abs(upper - lower) > EPS;
}

const MAX_DECIMALS = 4;

/**
 * Smallest number of decimals (from `start`, at most 4) at which two different
 * values are displayed differently. Without this a measured 10.04% against a
 * 10.0% limit would read "10.0% vs 10.0% — FAIL".
 */
export function decimalsToDistinguish(a: number, b: number, start = 1): number {
  if (Math.abs(a - b) <= EPS) return start;
  for (let decimals = start; decimals < MAX_DECIMALS; decimals += 1) {
    if (formatFraction(a, { decimals }) !== formatFraction(b, { decimals })) return decimals;
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

export type LimitDirection = "max" | "min";

/**
 * Words the gap between a measured value and its limit.
 * `gap` is measured minus limit, as a fraction; null means it cannot be determined.
 */
export function formatGap(gap: number | null | undefined, direction: LimitDirection = "max"): string {
  if (!isFiniteNumber(gap)) return "Cannot be determined";
  if (Math.abs(gap) <= EPS) return direction === "max" ? "Exactly at the limit" : "Exactly at the minimum";
  let decimals = 1;
  while (decimals < MAX_DECIMALS && Number(formatPoints(gap, decimals).split(" ")[0]) === 0) decimals += 1;
  const points = formatPoints(gap, decimals);
  if (direction === "max") return gap > 0 ? `${points} over the limit` : `${points} under the limit`;
  return gap > 0 ? `${points} above the minimum` : `${points} below the minimum`;
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
