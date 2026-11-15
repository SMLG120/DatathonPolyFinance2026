/** Types for `contrast-report.mjs`, so the unit test can import the same pair list the report prints. */
export declare const TOKENS_FILE: string;
export declare const PAIRS: [foreground: string, background: string, minimum: number, use: string][];
export declare function readTokens(css?: string): Record<string, string>;
export declare function luminance(hex: string): number;
export declare function contrastRatio(a: string, b: string): number;
export interface ContrastRow {
  foreground: string;
  background: string;
  fg: string;
  bg: string;
  minimum: number;
  ratio: number;
  pass: boolean;
  use: string;
}
export declare function evaluatePairs(tokens?: Record<string, string>): ContrastRow[];
