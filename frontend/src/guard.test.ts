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

// ---------------------------------------------------------------------------
// Imports. `three` is large, so it may be named only inside the exposure
// explorer, and the pages must reach it through `import()` alone: a module
// that is imported statically is part of the JavaScript every visitor loads.
// ---------------------------------------------------------------------------

/** The only directory that may import `three`. */
const EXPLORER = path.join("components", "explorer") + path.sep;
/** The pages and layouts: where the JavaScript every visitor loads starts. */
const APP = "app" + path.sep;

type ImportKind = "static" | "type" | "dynamic";

/**
 * Every module a source text names, and how it loads it. `import type` (and
 * `export type`) is erased by the compiler and loads nothing; `import()` loads
 * on demand; everything else loads with the file itself.
 */
function importsOf(source: string): { specifier: string; kind: ImportKind }[] {
  const found: { specifier: string; kind: ImportKind }[] = [];
  for (const match of source.matchAll(/^[ \t]*(?:import|export)\s+(type\s+)?(?:[\w*${},\s]+?\s+from\s+)?["']([^"']+)["']/gm)) {
    found.push({ specifier: match[2] as string, kind: match[1] ? "type" : "static" });
  }
  for (const match of source.matchAll(/\bimport\s*\(\s*["']([^"']+)["']\s*\)/g)) found.push({ specifier: match[1] as string, kind: "dynamic" });
  for (const match of source.matchAll(/\brequire\s*\(\s*["']([^"']+)["']\s*\)/g)) found.push({ specifier: match[1] as string, kind: "static" });
  return found;
}

const isThree = (specifier: string) => specifier === "three" || specifier.startsWith("three/");

/** The source file a relative or `@/` specifier points at; undefined for a package, a stylesheet or a generated file. */
function resolveSource(from: string, specifier: string, files: Set<string>): string | undefined {
  const base = specifier.startsWith("@/") ? path.join(SRC, specifier.slice(2)) : specifier.startsWith(".") ? path.resolve(path.dirname(from), specifier) : null;
  if (base === null) return undefined;
  return [base, `${base}.ts`, `${base}.tsx`, path.join(base, "index.ts"), path.join(base, "index.tsx")].find((candidate) => files.has(candidate));
}

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

  it("ships no AWS SDK and no React wrapper around three; three itself is the one 3D dependency", () => {
    const manifest = JSON.parse(readFileSync(path.join(FRONTEND, "package.json"), "utf8")) as { dependencies?: Record<string, string>; devDependencies?: Record<string, string> };
    const names = [...Object.keys(manifest.dependencies ?? {}), ...Object.keys(manifest.devDependencies ?? {})];
    expect(names.filter((name) => name.startsWith("@react-three/") || name.startsWith("@aws-sdk/") || name === "aws-sdk")).toEqual([]);
    expect(manifest.dependencies).toHaveProperty("three");
  });

  describe("three", () => {
    const sources = new Map(files.filter((file) => relative(file) !== SELF).map((file) => [file, importsOf(readFileSync(file, "utf8"))]));
    const known = new Set(files);
    /** Files that load three together with themselves. */
    const carriers = [...sources].filter(([, imports]) => imports.some((item) => item.kind === "static" && isThree(item.specifier))).map(([file]) => file);

    it("tells a static import from a type-only one and from one made on demand", () => {
      const kinds = (source: string) => importsOf(source).map((item) => `${item.kind} ${item.specifier}`);
      expect(kinds('import { Mesh } from "three";')).toEqual(["static three"]);
      expect(kinds('import {\n  Mesh,\n  type Material,\n} from "three";')).toEqual(["static three"]);
      expect(kinds('import * as THREE from "three";')).toEqual(["static three"]);
      expect(kinds('import "three/addons/controls/OrbitControls.js";')).toEqual(["static three/addons/controls/OrbitControls.js"]);
      expect(kinds('export { Scene } from "three";')).toEqual(["static three"]);
      expect(kinds('const three = require("three");')).toEqual(["static three"]);
      expect(kinds('import type { ExposureSceneHandle } from "./ExposureScene";')).toEqual(["type ./ExposureScene"]);
      expect(kinds('export type * from "@/lib/contracts";')).toEqual(["type @/lib/contracts"]);
      expect(kinds('const ExposureScene = lazy(() => import("./ExposureScene"));')).toEqual(["dynamic ./ExposureScene"]);
      expect(isThree("three")).toBe(true);
      expect(isThree("three/webgpu")).toBe(true);
      expect(isThree("three-stdlib")).toBe(false);
    });

    it("is named only inside the exposure explorer", () => {
      const naming = [...sources].filter(([, imports]) => imports.some((item) => isThree(item.specifier))).map(([file]) => relative(file));
      expect(naming.length).toBeGreaterThan(0);
      expect(naming.filter((name) => !name.startsWith(EXPLORER))).toEqual([]);
    });

    it("is never reached from a page through static imports, so it stays out of the JavaScript every visitor loads", () => {
      const pages = [...sources.keys()].filter((file) => relative(file).startsWith(APP));
      expect(pages.length).toBeGreaterThan(0);
      // Everything a page loads up front: follow the static imports only.
      const loadedUpFront = new Set<string>(pages);
      const queue = [...pages];
      while (queue.length > 0) {
        const file = queue.pop() as string;
        for (const item of sources.get(file) ?? []) {
          if (item.kind !== "static") continue;
          const target = resolveSource(file, item.specifier, known);
          if (target && !loadedUpFront.has(target)) {
            loadedUpFront.add(target);
            queue.push(target);
          }
        }
      }
      // The walk is real: it reaches the explorer card, which is on the pages.
      expect([...loadedUpFront].map(relative)).toContain(path.join("components", "explorer", "ExposureExplorer.tsx"));
      expect(carriers.filter((file) => loadedUpFront.has(file)).map(relative)).toEqual([]);
    });

    it("is loaded on demand: each file that imports it is itself brought in by import() from a file the pages load", () => {
      expect(carriers.length).toBeGreaterThan(0);
      for (const carrier of carriers) {
        const onDemand = [...sources].filter(([file, imports]) => imports.some((item) => item.kind === "dynamic" && resolveSource(file, item.specifier, known) === carrier));
        expect(onDemand.map(([file]) => relative(file)), `${relative(carrier)} is not loaded by any import()`).not.toEqual([]);
        const statically = [...sources].filter(
          ([file, imports]) => !/\.test\.tsx?$/.test(file) && imports.some((item) => item.kind === "static" && resolveSource(file, item.specifier, known) === carrier),
        );
        expect(statically.map(([file]) => relative(file)), `${relative(carrier)} is also imported statically`).toEqual([]);
      }
    });
  });
});
