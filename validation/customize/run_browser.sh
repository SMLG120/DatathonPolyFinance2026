#!/bin/bash
# Independent validation of "Customize this profile" in a real browser, against the real handlers.
# The equivalent of acceptance/fullstack/run.sh for a machine without `uv`; that script is not modified.
#
#   validation/customize/run_browser.sh                 build the live-mode site, run specs/06-customize.spec.ts
#   validation/customize/run_browser.sh --no-build      reuse the site built by the previous run
#   BYB_SPECS='specs/.*\.spec\.ts' validation/customize/run_browser.sh --no-build     every full-stack spec
#   further arguments go to `playwright test` (for example -g Mateo)
#
# Loopback only, no AWS. The access code is made up here for this run.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
FRONTEND="$ROOT/frontend"
FULLSTACK="$ROOT/acceptance/fullstack"
export BYB_PYTHON="${BYB_PYTHON:-/tmp/byb-test-venv/bin/python}"
export BYB_SITE_DIR="${BYB_SITE_DIR:-/tmp/byb-validation-site}"
export BYB_LOCAL_API_PORT="${BYB_LOCAL_API_PORT:-4184}"
export BYB_LOCAL_SITE_PORT="${BYB_LOCAL_SITE_PORT:-4185}"
export BYB_LOCAL_CONTROL_PORT="${BYB_LOCAL_CONTROL_PORT:-4186}"
export BYB_SCREENSHOT_DIR="${BYB_SCREENSHOT_DIR:-$HERE/screenshots}"
export BYB_OUTPUT_DIR="${BYB_OUTPUT_DIR:-/tmp/byb-validation-test-results}"

BUILD=1
if [ "${1:-}" = "--no-build" ]; then BUILD=0; shift; fi
[ -x "$BYB_PYTHON" ] || { echo "run_browser.sh: BYB_PYTHON ($BYB_PYTHON) is not an interpreter"; exit 2; }
[ -f "$ROOT/data/processed/holdings.json" ] || { echo "run_browser.sh: data/processed is missing (git-ignored real data)"; exit 2; }

if [ "$BUILD" = 1 ] || [ ! -f "$BYB_SITE_DIR/index.html" ]; then
  # `next build` always writes frontend/out: the existing one is set aside and put back, as run.sh does.
  KEEP=""
  if [ -d "$FRONTEND/out" ]; then KEEP="$FRONTEND/.out-kept-by-validation.$$"; mv "$FRONTEND/out" "$KEEP"; fi
  restore() { rm -rf "$FRONTEND/out"; if [ -n "$KEEP" ] && [ -d "$KEEP" ]; then mv "$KEEP" "$FRONTEND/out"; fi; }
  trap restore EXIT
  LOG="$(mktemp)"
  (cd "$FRONTEND" && NEXT_TELEMETRY_DISABLED=1 NEXT_PUBLIC_API_BASE_URL="http://127.0.0.1:$BYB_LOCAL_API_PORT" \
      node node_modules/next/dist/bin/next build) > "$LOG" 2>&1 || { tail -40 "$LOG"; exit 1; }
  rm -rf "$BYB_SITE_DIR"
  mv "$FRONTEND/out" "$BYB_SITE_DIR"
  restore
  trap - EXIT
  echo "run_browser.sh: live-mode site built into $BYB_SITE_DIR (API http://127.0.0.1:$BYB_LOCAL_API_PORT)"
fi

export BYB_LOCAL_ACCESS_CODE="local-run-$(node -e 'console.log(require("crypto").randomBytes(12).toString("hex"))')"
mkdir -p "$BYB_SCREENSHOT_DIR"
cd "$FULLSTACK"
NODE_PATH="$FRONTEND/node_modules" exec node "$FRONTEND/node_modules/@playwright/test/cli.js" test -c playwright.customize.config.ts "$@"
