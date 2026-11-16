#!/bin/bash
# One command: build the frontend in live mode against the local API, start the local stack, run the browser specs.
#
#   acceptance/fullstack/run.sh                 build + run everything
#   acceptance/fullstack/run.sh --no-build      reuse acceptance/fullstack/.site from the previous run
#   acceptance/fullstack/run.sh -g "Robert"     extra arguments go to `playwright test`
#
# Optional environment:
#   BYB_PYTHON=/path/to/python   interpreter that has boto3 and jsonschema (for a machine without `uv`); default: `uv run`
#   BYB_SITE_DIR=/some/dir       where the live-mode site is built and served from; default: acceptance/fullstack/.site
#   BYB_FULLSTACK_SHOTS=/dir     where specs 01 to 05 write screenshots; default: acceptance/fullstack/screenshots-2026-11-15
#
# Loopback only. The access code is a made-up value generated here for this run; no real one is read.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
FRONTEND="$ROOT/frontend"
export BYB_LOCAL_API_PORT="${BYB_LOCAL_API_PORT:-4184}"
export BYB_LOCAL_SITE_PORT="${BYB_LOCAL_SITE_PORT:-4185}"
export BYB_LOCAL_CONTROL_PORT="${BYB_LOCAL_CONTROL_PORT:-4186}"
export BYB_SITE_DIR="${BYB_SITE_DIR:-$HERE/.site}"
if [ -n "${BYB_PYTHON:-}" ]; then
  [ -x "$BYB_PYTHON" ] || { echo "run.sh: BYB_PYTHON ($BYB_PYTHON) is not an interpreter"; exit 2; }
  export BYB_PYTHON
elif ! command -v uv >/dev/null 2>&1; then
  echo "run.sh: \`uv\` is not installed; set BYB_PYTHON to a Python that has boto3 and jsonschema"; exit 2
fi
# Only one `next build` may run in frontend/ at a time (it writes frontend/.next and frontend/out).
BUILD_LOCK="${BYB_BUILD_LOCK:-/tmp/byb-next-build.lock}"

BUILD=1
if [ "${1:-}" = "--no-build" ]; then BUILD=0; shift; fi

for name in holdings instruments market_data controversies sources; do
  [ -f "$ROOT/data/processed/$name.json" ] || { echo "run.sh: data/processed/$name.json is missing (git-ignored real data)"; exit 2; }
done
[ -d "$FRONTEND/node_modules/@playwright/test" ] || (cd "$FRONTEND" && npm ci)

if [ "$BUILD" = 1 ] || [ ! -f "$BYB_SITE_DIR/index.html" ]; then
  # `next build` always writes frontend/out (git-ignored). An existing out/ is set aside and put back,
  # so no live-mode build pointing at a local address is left where a deployment would look for it.
  until mkdir "$BUILD_LOCK" 2>/dev/null; do echo "run.sh: waiting for another build ($BUILD_LOCK)"; sleep 5; done
  KEEP=""
  restore() {
    if [ -n "$KEEP" ]; then rm -rf "$FRONTEND/out"; if [ -d "$KEEP" ]; then mv "$KEEP" "$FRONTEND/out"; fi; KEEP=""; fi
    rmdir "$BUILD_LOCK" 2>/dev/null || true
  }
  trap restore EXIT
  if [ -d "$FRONTEND/out" ]; then KEEP="$FRONTEND/.out-kept-by-fullstack.$$"; mv "$FRONTEND/out" "$KEEP"; else KEEP="-"; fi
  (cd "$FRONTEND" && NEXT_TELEMETRY_DISABLED=1 NEXT_PUBLIC_API_BASE_URL="http://127.0.0.1:$BYB_LOCAL_API_PORT" \
      node node_modules/next/dist/bin/next build) > "$HERE/.run-build.log" 2>&1 || { tail -40 "$HERE/.run-build.log"; exit 1; }
  rm -rf "$BYB_SITE_DIR"
  mv "$FRONTEND/out" "$BYB_SITE_DIR"
  restore
  trap - EXIT
  rm -f "$HERE/.run-build.log"
  echo "run.sh: live-mode site built into $BYB_SITE_DIR (API http://127.0.0.1:$BYB_LOCAL_API_PORT)"
fi

# A made-up code for this run only (the authorizer requires at least 16 characters).
export BYB_LOCAL_ACCESS_CODE="local-run-$(node -e 'console.log(require("crypto").randomBytes(12).toString("hex"))')"
mkdir -p "$HERE/.run"
cd "$HERE"
NODE_PATH="$FRONTEND/node_modules" exec node "$FRONTEND/node_modules/@playwright/test/cli.js" test -c playwright.config.ts "$@"
