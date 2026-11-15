#!/bin/bash
# One command: build the frontend in live mode against the local API, start the local stack, run the browser specs.
#
#   acceptance/fullstack/run.sh                 build + run everything
#   acceptance/fullstack/run.sh --no-build      reuse acceptance/fullstack/.site from the previous run
#   acceptance/fullstack/run.sh -g "Robert"     extra arguments go to `playwright test`
#
# Loopback only. The access code is a made-up value generated here for this run; no real one is read.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
FRONTEND="$ROOT/frontend"
export BYB_LOCAL_API_PORT="${BYB_LOCAL_API_PORT:-4184}"
export BYB_LOCAL_SITE_PORT="${BYB_LOCAL_SITE_PORT:-4185}"
export BYB_LOCAL_CONTROL_PORT="${BYB_LOCAL_CONTROL_PORT:-4186}"

BUILD=1
if [ "${1:-}" = "--no-build" ]; then BUILD=0; shift; fi

for name in holdings instruments market_data controversies sources; do
  [ -f "$ROOT/data/processed/$name.json" ] || { echo "run.sh: data/processed/$name.json is missing (git-ignored real data)"; exit 2; }
done
[ -d "$FRONTEND/node_modules/@playwright/test" ] || (cd "$FRONTEND" && npm ci)

if [ "$BUILD" = 1 ] || [ ! -f "$HERE/.site/index.html" ]; then
  # `next build` always writes frontend/out (git-ignored). An existing out/ is set aside and put back,
  # so no live-mode build pointing at a local address is left where a deployment would look for it.
  KEEP=""
  if [ -d "$FRONTEND/out" ]; then KEEP="$FRONTEND/.out-kept-by-fullstack.$$"; mv "$FRONTEND/out" "$KEEP"; fi
  restore() { rm -rf "$FRONTEND/out"; if [ -n "$KEEP" ] && [ -d "$KEEP" ]; then mv "$KEEP" "$FRONTEND/out"; fi; }
  trap restore EXIT
  (cd "$FRONTEND" && NEXT_TELEMETRY_DISABLED=1 NEXT_PUBLIC_API_BASE_URL="http://127.0.0.1:$BYB_LOCAL_API_PORT" \
      node node_modules/next/dist/bin/next build) > "$HERE/.run-build.log" 2>&1 || { tail -40 "$HERE/.run-build.log"; exit 1; }
  rm -rf "$HERE/.site"
  mv "$FRONTEND/out" "$HERE/.site"
  restore
  trap - EXIT
  rm -f "$HERE/.run-build.log"
  echo "run.sh: live-mode site built into acceptance/fullstack/.site (API http://127.0.0.1:$BYB_LOCAL_API_PORT)"
fi

# A made-up code for this run only (the authorizer requires at least 16 characters).
export BYB_LOCAL_ACCESS_CODE="local-run-$(node -e 'console.log(require("crypto").randomBytes(12).toString("hex"))')"
mkdir -p "$HERE/.run"
cd "$HERE"
NODE_PATH="$FRONTEND/node_modules" exec node "$FRONTEND/node_modules/@playwright/test/cli.js" test -c playwright.config.ts "$@"
