#!/usr/bin/env node
/**
 * Copies the shared contract into the frontend, so the app can be built from a
 * checkout of `frontend/` alone:
 *
 *   ../contracts/typescript/contracts.ts  -> src/generated/contracts/contracts.ts
 *   ../contracts/fixtures/api/*.json      -> src/generated/contracts/fixtures/api/
 *   ../contracts/scenarios/*.json         -> src/generated/contracts/scenarios/
 *
 * Every copied TypeScript file gets a "GENERATED — DO NOT EDIT" header, and
 * each copied directory gets a GENERATED_DO_NOT_EDIT.txt listing its sources
 * and their SHA-256 (JSON cannot carry a comment).
 *
 * The copies are meant to be committed. Edit the originals in `contracts/`
 * (owned by the contracts agent), then run `npm run sync:contracts` again.
 *
 *   node scripts/sync-contracts.mjs            copy what exists, report the rest
 *   node scripts/sync-contracts.mjs --check    exit 1 if a copy is missing or stale (for CI)
 */
import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const frontend = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const contracts = path.resolve(frontend, "..", "contracts");
const target = path.join(frontend, "src", "generated", "contracts");
const check = process.argv.includes("--check");

const HEADER = (source) =>
  `// GENERATED — DO NOT EDIT.\n// Copied from ${source} by \`npm run sync:contracts\`.\n// Change the original in contracts/ and run the script again.\n\n`;

const sha256 = (text) => createHash("sha256").update(text).digest("hex");
const relative = (file) => path.relative(path.resolve(frontend, ".."), file).split(path.sep).join("/");

/** [source directory, file filter, destination directory, add a header?] */
const JOBS = [
  { from: path.join(contracts, "typescript"), match: /\.ts$/, to: target, header: true },
  { from: path.join(contracts, "fixtures", "api"), match: /\.json$/, to: path.join(target, "fixtures", "api"), header: false },
  { from: path.join(contracts, "scenarios"), match: /\.json$/, to: path.join(target, "scenarios"), header: false },
];

let copied = 0;
let stale = 0;
const missing = [];

for (const job of JOBS) {
  const files = existsSync(job.from) ? readdirSync(job.from).filter((name) => job.match.test(name)).sort() : [];
  if (files.length === 0) {
    missing.push(relative(job.from));
    continue;
  }
  const manifest = [`GENERATED — DO NOT EDIT. Copied by \`npm run sync:contracts\` from ${relative(job.from)}/.`, ""];
  if (!check) mkdirSync(job.to, { recursive: true });
  for (const name of files) {
    const source = readFileSync(path.join(job.from, name), "utf8");
    const output = job.header ? HEADER(`${relative(job.from)}/${name}`) + source : source;
    const destination = path.join(job.to, name);
    manifest.push(`${name}  sha256:${sha256(source)}`);
    if (check) {
      if (!existsSync(destination) || readFileSync(destination, "utf8") !== output) {
        stale += 1;
        console.error(`stale or missing: ${relative(destination)}`);
      }
      continue;
    }
    writeFileSync(destination, output);
    copied += 1;
  }
  if (!check) {
    // Remove copies whose original is gone, so the frontend never keeps a contract that no longer exists.
    for (const name of readdirSync(job.to)) {
      if (job.match.test(name) && !files.includes(name)) rmSync(path.join(job.to, name));
    }
    writeFileSync(path.join(job.to, "GENERATED_DO_NOT_EDIT.txt"), `${manifest.join("\n")}\n`);
  }
}

for (const directory of missing) console.warn(`not found yet (nothing copied): ${directory}/`);

if (check) {
  if (stale > 0 || missing.length > 0) {
    console.error(`sync:contracts --check failed: ${stale} stale, ${missing.length} source ${missing.length === 1 ? "directory" : "directories"} empty or missing.`);
    process.exit(1);
  }
  console.log("sync:contracts --check: copies are up to date.");
} else {
  console.log(`sync:contracts: ${copied} ${copied === 1 ? "file" : "files"} copied into ${relative(target)}/.`);
  if (missing.length > 0) {
    console.log("The interface keeps using its provisional types and fixtures (src/lib/provisional-*.ts) until the contract exists.");
  }
}
