import type { CustomPortfolio, InstrumentId, Objective, Portfolio } from "@/lib/contracts";
import { shiftDecimal } from "@/lib/format";

/**
 * The customized fictional portfolio: reading the editor's form and carrying
 * the applied weights to the screen and to the service.
 *
 * Nothing here is a financial calculation. The form's weights are added up
 * only to check that the form is complete (they must total 100%), and that is
 * done on whole hundredths of a percent, never on floating-point fractions.
 * Every exposure, verdict, cash figure and maximum stays the service's answer.
 *
 * One value, `CustomPortfolio | null`, is the applied customization. It feeds
 * both what is shown (`applyCustomPortfolio`) and what is sent
 * (`withCustomPortfolio`), so the two cannot disagree.
 */

/** Contract limits (contracts/api.md section 2a, and the objective length of the interpret request). */
export const MAX_CUSTOM_POSITIONS = 40;
export const MAX_OBJECTIVE_LENGTH = 2000;

/** 100% in hundredths of a percent. */
export const FULL_HUNDREDTHS = 10_000;

/** The label of an edited portfolio, wherever it is shown. */
export const CUSTOMIZED_LABEL = "Customized fictional portfolio";

export const TOTAL_MESSAGE = "Weights must total 100%. Leverage is not supported and weights are never rescaled.";

export type WeightProblemCode = "EMPTY" | "MALFORMED" | "NEGATIVE" | "TOO_PRECISE" | "ZERO_POSITION" | "ABOVE_FULL";

export type WeightReading = { ok: true; hundredths: number } | { ok: false; code: WeightProblemCode; message: string };

const WEIGHT_MESSAGES: Record<WeightProblemCode, string> = {
  EMPTY: "Enter a weight as a percentage, for example 12.5.",
  MALFORMED: "Enter a number such as 25 or 12.5.",
  NEGATIVE: "Shorting is not supported: a weight cannot be negative.",
  TOO_PRECISE: "Use at most 2 decimals, for example 12.25.",
  ZERO_POSITION: "A position's weight must be above 0%. Remove the row to hold none of it.",
  ABOVE_FULL: "A weight cannot be above 100%. Leverage is not supported.",
};

const refuse = (code: WeightProblemCode): WeightReading => ({ ok: false, code, message: WEIGHT_MESSAGES[code] });

/**
 * Reads a typed percentage into whole hundredths of a percent, from its digits: "12.5" is 1250.
 * No floating-point number is involved, so "0.1" and "0.2" add up to exactly "0.3".
 */
export function readWeight(text: string, kind: "position" | "cash"): WeightReading {
  const trimmed = text.trim().replace(/%$/, "").trim();
  if (trimmed === "") return refuse("EMPTY");
  const match = /^([+-]?)(\d*)(?:\.(\d*))?$/.exec(trimmed);
  if (!match || ((match[2] ?? "") === "" && (match[3] ?? "") === "")) return refuse("MALFORMED");
  const whole = (match[2] ?? "").replace(/^0+(?=\d)/, "");
  const decimals = (match[3] ?? "").replace(/0+$/, "");
  const isZero = /^0*$/.test(whole) && decimals === "";
  if (match[1] === "-" && !isZero) return refuse("NEGATIVE");
  if (decimals.length > 2) return refuse("TOO_PRECISE");
  // More than 100% whatever follows: refused before any number is built from the digits.
  if (whole.length > 3) return refuse("ABOVE_FULL");
  const hundredths = Number(whole === "" ? "0" : whole) * 100 + Number(decimals.padEnd(2, "0"));
  if (hundredths > FULL_HUNDREDTHS) return refuse("ABOVE_FULL");
  if (kind === "position" && hundredths === 0) return refuse("ZERO_POSITION");
  return { ok: true, hundredths };
}

/** Whole hundredths of a percent as text with two decimals: 9550 is "95.50". */
export function hundredthsToText(hundredths: number): string {
  const whole = Math.trunc(hundredths / 100);
  return `${whole}.${String(hundredths - whole * 100).padStart(2, "0")}`;
}

/** Whole hundredths of a percent as a portfolio fraction: 1250 is 0.125 (the same number the JSON text `0.125` is). */
export function hundredthsToFraction(hundredths: number): number {
  return Number(`${hundredths}e-4`);
}

/**
 * A stored weight as text for a percentage field: 0.3 is "30", 0.125 is "12.5".
 * A weight finer than a hundredth of a percent is written out in full, and the field then says so.
 */
export function fractionToWeightText(weight: number): string {
  if (!Number.isFinite(weight)) return "";
  const scaled = shiftDecimal(weight, 4);
  if (!Number.isInteger(scaled)) return String(shiftDecimal(weight, 2));
  const text = hundredthsToText(scaled);
  return text.replace(/\.?0+$/, "");
}

export interface CustomizeRow {
  instrumentId: InstrumentId;
  text: string;
}

export interface CustomizeFormInput {
  rows: CustomizeRow[];
  cashText: string;
  /** Null when the scenario has no objective to edit. */
  objectiveText: string | null;
}

export interface CustomizeFormReading {
  /** The message for each row, by instrument id. */
  rowErrors: Record<InstrumentId, string>;
  cashError: string | null;
  /** The form's total in hundredths of a percent, or null while a weight cannot be read. */
  totalHundredths: number | null;
  totalError: string | null;
  objectiveError: string | null;
  /** A problem with the list itself (an asset that cannot be held, an asset listed twice, too many rows). */
  listError: string | null;
  /** The weights as they would be sent, or null while the form cannot be applied. */
  portfolio: CustomPortfolio | null;
  valid: boolean;
}

/** Reads the editor's form. Only the form is checked here; the service checks the portfolio again and is the authority. */
export function readCustomizeForm(input: CustomizeFormInput, purchasableIds: readonly InstrumentId[]): CustomizeFormReading {
  const rowErrors: Record<InstrumentId, string> = {};
  const readings = input.rows.map((row) => ({ row, reading: readWeight(row.text, "position") }));
  for (const { row, reading } of readings) if (!reading.ok) rowErrors[row.instrumentId] = reading.message;
  const cash = readWeight(input.cashText, "cash");
  const cashError = cash.ok ? null : cash.message;

  const ids = input.rows.map((row) => row.instrumentId);
  const unsupported = ids.find((id) => !purchasableIds.includes(id));
  const listError =
    unsupported !== undefined
      ? `${unsupported} cannot be held in this simulation. Remove its row.`
      : new Set(ids).size !== ids.length
        ? "An asset can be listed only once."
        : ids.length > MAX_CUSTOM_POSITIONS
          ? `A portfolio can hold at most ${MAX_CUSTOM_POSITIONS} positions.`
          : null;

  // The total of the form, in whole hundredths of a percent. This is form validation, not a portfolio figure.
  let totalHundredths: number | null = cash.ok ? cash.hundredths : null;
  for (const { reading } of readings) totalHundredths = totalHundredths !== null && reading.ok ? totalHundredths + reading.hundredths : null;
  const totalError = totalHundredths !== null && totalHundredths !== FULL_HUNDREDTHS ? TOTAL_MESSAGE : null;

  const objectiveError =
    input.objectiveText === null
      ? null
      : input.objectiveText.trim() === ""
        ? "Write the objective in a sentence. It cannot be empty."
        : input.objectiveText.length > MAX_OBJECTIVE_LENGTH
          ? `The objective can have at most ${MAX_OBJECTIVE_LENGTH} characters. It has ${input.objectiveText.length}.`
          : null;

  const valid = Object.keys(rowErrors).length === 0 && cashError === null && listError === null && totalHundredths === FULL_HUNDREDTHS && objectiveError === null;
  const portfolio: CustomPortfolio | null =
    valid && cash.ok
      ? {
          cash_weight: hundredthsToFraction(cash.hundredths),
          positions: readings.flatMap(({ row, reading }) => (reading.ok ? [{ instrument_id: row.instrumentId, weight: hundredthsToFraction(reading.hundredths) }] : [])),
        }
      : null;
  return { rowErrors, cashError, totalHundredths, totalError, objectiveError, listError, portfolio, valid };
}

/**
 * True when the weights are the scenario portfolio's own: the same instruments at the same weights, in any
 * order. The service then checks the scenario portfolio (contracts/api.md section 2a, rule 5), so the
 * page does not call it customized and sends no `custom_portfolio`.
 */
export function isScenarioPortfolio(custom: CustomPortfolio, scenario: Portfolio): boolean {
  return (
    custom.cash_weight === scenario.cash_weight &&
    custom.positions.length === scenario.positions.length &&
    scenario.positions.every((position) => custom.positions.some((candidate) => candidate.instrument_id === position.instrument_id && candidate.weight === position.weight))
  );
}

/**
 * The portfolio the next check starts from: the scenario's, with cash and positions replaced when a
 * customization is applied. The id stays the scenario's here: only the service names a customized
 * portfolio, and it reports that id in its results and jobs.
 */
export function applyCustomPortfolio(scenario: Portfolio, custom: CustomPortfolio | null): Portfolio {
  return custom === null ? scenario : { ...scenario, cash_weight: custom.cash_weight, positions: custom.positions };
}

/**
 * Adds the applied customization to a request body. Without one the member is left out altogether, so a
 * request on the scenario portfolio is exactly what it was before customization existed.
 */
export function withCustomPortfolio<T extends object>(body: T, custom: CustomPortfolio | null): T & { custom_portfolio?: CustomPortfolio } {
  return custom === null ? body : { ...body, custom_portfolio: custom };
}

/** The weights of a stored portfolio document, as a request carries them. */
export function customPortfolioOf(portfolio: Portfolio): CustomPortfolio {
  return { cash_weight: portfolio.cash_weight, positions: portfolio.positions.map((position) => ({ instrument_id: position.instrument_id, weight: position.weight })) };
}

/** True when a stored portfolio document is not the scenario's own: the service gave it another id. */
export function isCustomizedPortfolio(portfolio: Portfolio, scenario: Portfolio | null): boolean {
  return scenario !== null && portfolio.portfolio_id !== scenario.portfolio_id;
}

/**
 * The `custom_portfolio` that reproduces the portfolio a report was checked against, or null when that
 * was the scenario portfolio (or the report was stored before jobs kept their portfolio: it was then
 * checked against the scenario's). A preview about a report uses this, never the current customization.
 */
export function customPortfolioOfReport(portfolio: Portfolio | undefined, scenario: Portfolio | null): CustomPortfolio | null {
  return portfolio && isCustomizedPortfolio(portfolio, scenario) ? customPortfolioOf(portfolio) : null;
}

/** What a stored portfolio is called wherever a report names it. */
export function portfolioCheckedLabel(portfolio: Portfolio, scenario: Portfolio | null, personaName: string): string {
  if (scenario === null) return "Fictional portfolio stored with this report";
  return isCustomizedPortfolio(portfolio, scenario) ? CUSTOMIZED_LABEL : `${personaName}’s original fictional portfolio`;
}

/** The scenario objective with the user's wording: same id and kind, the words verbatim, stated by the user. */
export function restatedObjective(objective: Objective, words: string): Objective {
  return { ...objective, original_words: words, source: "USER_STATED", case_reference: null };
}
