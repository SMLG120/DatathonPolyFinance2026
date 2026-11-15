#!/usr/bin/env node
/**
 * Serves the static build in `out/` on http://127.0.0.1:<port>.
 *
 * `next start` does not work with `output: "export"`, so this small server
 * stands in for the static host (S3 + CloudFront in the deployed setup). It is
 * used by `npm start` and by the Playwright tests. Standard library only.
 *
 *   node scripts/serve-out.mjs [--port 4173] [--dir out]
 *
 * `--dir` names a folder inside `frontend/` (the tests serve `out-live/`, a
 * second build made with an API address).
 */
import { createServer } from "node:http";
import { readFile, stat } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

const args = process.argv.slice(2);
const dirFlag = args.indexOf("--dir");
const dirName = dirFlag >= 0 ? (args[dirFlag + 1] ?? "") : "out";
const root = path.resolve(projectRoot, dirName);
if (dirName === "" || !root.startsWith(projectRoot + path.sep)) {
  console.error("serve-out: --dir must name a folder inside the frontend directory");
  process.exit(1);
}
const portFlag = args.indexOf("--port");
const port = Number(portFlag >= 0 ? args[portFlag + 1] : (process.env.PORT ?? 4173));
if (!Number.isInteger(port) || port <= 0) {
  console.error("serve-out: --port must be a positive integer");
  process.exit(1);
}

const TYPES = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".txt": "text/plain; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".ico": "image/x-icon",
  ".woff2": "font/woff2",
  ".map": "application/json; charset=utf-8",
};

async function isFile(file) {
  try {
    return (await stat(file)).isFile();
  } catch {
    return false;
  }
}

/** Maps a URL path to a file inside `out/`, or null. Never leaves the root. */
async function resolveFile(urlPath) {
  let decoded;
  try {
    decoded = decodeURIComponent(urlPath);
  } catch {
    return null;
  }
  const target = path.resolve(root, `.${path.posix.normalize(`/${decoded}`)}`);
  if (target !== root && !target.startsWith(root + path.sep)) return null;
  for (const candidate of [target, path.join(target, "index.html"), `${target}.html`]) {
    if (await isFile(candidate)) return candidate;
  }
  return null;
}

const server = createServer(async (request, response) => {
  if (request.method !== "GET" && request.method !== "HEAD") {
    response.writeHead(405, { Allow: "GET, HEAD" }).end();
    return;
  }
  const { pathname } = new URL(request.url ?? "/", "http://localhost");
  const file = await resolveFile(pathname);
  const found = file ?? path.join(root, "404.html");
  try {
    const body = await readFile(found);
    response.writeHead(file ? 200 : 404, {
      "Content-Type": TYPES[path.extname(found)] ?? "application/octet-stream",
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff",
    });
    response.end(request.method === "HEAD" ? undefined : body);
  } catch {
    response.writeHead(404, { "Content-Type": "text/plain; charset=utf-8" }).end("Not found. Run `npm run build` first.");
  }
});

if (!(await isFile(path.join(root, "index.html")))) {
  console.error(`serve-out: ${dirName}/index.html not found. Run \`npm run build\` first (or \`npm run test:e2e\`, which builds both folders).`);
  process.exit(1);
}

server.listen(port, "127.0.0.1", () => {
  console.log(`Serving ${root} on http://127.0.0.1:${port}`);
});
