import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

/**
 * Guards over the source tree itself.
 *
 * Results come from the service (or, in fixtures mode, from the recorded
 * bodies under `src/generated/`). No file may write one by hand: a result
 * typed into the interface could be shown as if the engine had produced it.
 */
const SRC = path.dirname(fileURLToPath(import.meta.url));
const FRONTEND = path.resolve(SRC, "..");
const SELF = "guard.test.ts";
/** The one file that may assign result fields: derived test inputs, each a recorded body with named fields replaced. */
const PROBES = path.join("test", "probes.ts");

function sourceFiles(directory: string = SRC): string[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const full = path.join(directory, entry.name);
    if (entry.isDirectory()) return entry.name === "generated" ? [] : sourceFiles(full);
    return /\.(ts|tsx)$/.test(entry.name) ? [full] : [];
  });
}

const relative = (file: string) => path.relative(SRC, file);

function offences(files: string[], pattern: RegExp): string[] {
  return files.flatMap((file) =>
    readFileSync(file, "utf8")
      .split("\n")
      .flatMap((line, index) => (pattern.test(line) ? [`${relative(file)}:${index + 1}: ${line.trim()}`] : [])),
  );
}

/** Fields that exist only inside an engine result. Written as an object key (`name:`), they mean a result is being authored. */
const RESULT_KEYS = [
  "rule_results",
  "rules_not_evaluated",
  "starting_portfolio_findings",
  "data_coverage",
  "goal_context",
  "max_compliant",
  "policy_consistency",
  "calculation_version",
  "breaching_subjects",
  "unknown_causes",
  "out_of_scope",
  "purchase_effect",
  "feasibility_status",
  "starting_portfolio_breaches",
  "rules_evaluated",
  "cash_before",
  "cash_after",
  "additional_purchase",
  "verified_by_rerun",
  "binding_constraint",
  "indirect_by_fund",
  "possible_extra",
  "coverage_fraction",
  "uncovered_portfolio_weight",
];
/** `name:` or `"name":` as a key. A read such as `result.rule_results` has a dot in front and does not match. */
const RESULT_KEY = new RegExp(`(?<![.\\w])["']?(${RESULT_KEYS.join("|")})["']?\\s*:`);

describe("source guards", () => {
  const files = sourceFiles();

  it("finds the source tree", () => {
    expect(files.length).toBeGreaterThan(60);
    expect(files.map(relative)).toContain(PROBES);
    expect(files.some((file) => relative(file).startsWith("generated"))).toBe(false);
  });

  it("has no hand-written result object outside src/generated", () => {
    const scanned = files.filter((file) => relative(file) !== SELF && relative(file) !== PROBES);
    expect(offences(scanned, RESULT_KEY)).toEqual([]);
  });

  it("recognises a hand-written result when it sees one", () => {
    expect(RESULT_KEY.test('const made = { rule_results: [], summary };')).toBe(true);
    expect(RESULT_KEY.test('  "max_compliant": null,')).toBe(true);
    expect(RESULT_KEY.test("const shown = result.rule_results.length;")).toBe(false);
    expect(RESULT_KEY.test("return fund.status === PARTIAL ? fund.coverage_fraction : null;")).toBe(false);
  });

  it("keeps the derived test inputs derived: the probes file never writes a whole result", () => {
    const probes = files.filter((file) => relative(file) === PROBES);
    // A complete result needs these; a probe only replaces fields of a recorded one.
    expect(offences(probes, /(?<![.\w])["']?(schema_version|rule_results|evidence|purchase_request|persona_id|portfolio_id|summary|execution)["']?\s*:/)).toEqual([]);
    expect(readFileSync(probes[0] as string, "utf8")).toContain('from "@/lib/fixtures"');
  });

  it("never injects text as markup", () => {
    const scanned = files.filter((file) => relative(file) !== SELF);
    expect(offences(scanned, /dangerouslySetInnerHTML|\.innerHTML\b|\.outerHTML\b|insertAdjacentHTML|document\.write/)).toEqual([]);
  });

  it("never makes an idempotency key, or anything else, from Math.random", () => {
    const scanned = files.filter((file) => relative(file) !== SELF);
    expect(offences(scanned, /Math\.random/)).toEqual([]);
  });

  it("checks the contract copies before the unit tests run", () => {
    const scripts = (JSON.parse(readFileSync(path.join(FRONTEND, "package.json"), "utf8")) as { scripts: Record<string, string> }).scripts;
    expect(scripts.test).toMatch(/^node scripts\/sync-contracts\.mjs --check && vitest run/);
  });

  it("does not depend on a 3D library yet, and ships no AWS SDK", () => {
    const manifest = JSON.parse(readFileSync(path.join(FRONTEND, "package.json"), "utf8")) as { dependencies?: Record<string, string>; devDependencies?: Record<string, string> };
    const names = [...Object.keys(manifest.dependencies ?? {}), ...Object.keys(manifest.devDependencies ?? {})];
    expect(names.filter((name) => name === "three" || name.startsWith("@react-three/") || name.startsWith("@aws-sdk/") || name === "aws-sdk")).toEqual([]);
  });
});
