#!/usr/bin/env bash
# End-to-end smoke test against the deployed HTTP API (curl + jq, no AWS CLI).
#
#   scripts/e2e_smoke.sh https://<api-id>.execute-api.us-east-1.amazonaws.com /path/to/access-code-file
#
# The access code is read from a file (mode 600, outside the repository) so it
# never appears in the command line, the shell history or this script's
# output. Nothing printed here contains the code or an Authorization header.
set -euo pipefail

API="${1:?usage: e2e_smoke.sh API_BASE_URL ACCESS_CODE_FILE}"
CODE_FILE="${2:?usage: e2e_smoke.sh API_BASE_URL ACCESS_CODE_FILE}"
[ -r "$CODE_FILE" ] || { echo "cannot read the access code file" >&2; exit 2; }
WORK="$(mktemp -d)"
trap 'rm -r "$WORK"' EXIT
HEADER_FILE="$WORK/auth-header"
( umask 077; printf 'Authorization: Bearer %s' "$(tr -d '\r\n' < "$CODE_FILE")" > "$HEADER_FILE" )
KEY="e2e-$(date -u +%Y%m%dT%H%M%SZ)-$RANDOM"
BODY='{"persona_id":"robert","purchase":{"instrument_id":"NVDA","target_direct_weight":0.25},"question":"What is my exposure to NVDA after this purchase?","idempotency_key":"'"$KEY"'"}'
FAILURES=0

call() { # call LABEL EXPECTED_STATUS curl-args... ; prints status, time and body
  local label="$1" expected="$2"; shift 2
  local status
  status="$(curl -sS -o "$WORK/body" -D "$WORK/headers" -w '%{http_code} %{time_total}' "$@")"
  local code="${status%% *}" seconds="${status##* }"
  if [ "$code" = "$expected" ]; then echo "PASS  $label -> HTTP $code in ${seconds}s"; else echo "FAIL  $label -> HTTP $code (expected $expected) in ${seconds}s"; FAILURES=$((FAILURES + 1)); fi
  if [ -s "$WORK/body" ]; then (jq -c . "$WORK/body" 2>/dev/null || head -c 400 "$WORK/body") | cut -c1-700 | sed 's/^/      /'; fi
}

echo "== API $API   idempotency key $KEY"
echo "== 1. authentication"
call "POST without a token" 401 -X POST "$API/investigations" -H 'content-type: application/json' -d "$BODY"
call "GET without a token" 401 "$API/investigations/inv_00000000000000000000000000000000"
call "POST with a wrong token" 403 -X POST "$API/investigations" -H 'content-type: application/json' -H 'Authorization: Bearer this-is-not-the-access-code-0000' -d "$BODY"

echo "== 2. CORS preflight (no token)"
call "OPTIONS /investigations" 204 -X OPTIONS "$API/investigations" -H 'Origin: https://example.org' -H 'Access-Control-Request-Method: POST' -H 'Access-Control-Request-Headers: authorization,content-type,idempotency-key'
grep -i '^access-control-' "$WORK/headers" | tr -d '\r' | sed 's/^/      /'
curl -sS -o /dev/null -D "$WORK/headers" "$API/investigations/inv_00000000000000000000000000000000" -H 'Origin: https://example.org'
echo "      CORS headers on the 401: $(grep -i -c '^access-control-allow-origin' "$WORK/headers" || true) access-control-allow-origin header(s)"

echo "== 3. validation"
call "POST with an invalid body" 400 -X POST "$API/investigations" -H @"$HEADER_FILE" -H 'content-type: application/json' -d '{"persona_id":"robert","purchase":{"instrument_id":"NVDA","target_direct_weight":25},"idempotency_key":"'"$KEY"'-bad"}'
call "GET an unknown investigation" 404 "$API/investigations/inv_00000000000000000000000000000000" -H @"$HEADER_FILE"

echo "== 4. create (202 only after the worker invocation was accepted)"
call "POST /investigations" 202 -X POST "$API/investigations" -H @"$HEADER_FILE" -H 'content-type: application/json' -d "$BODY"
ID="$(jq -r '.investigation_id // empty' "$WORK/body")"
grep -i '^location:' "$WORK/headers" | tr -d '\r' | sed 's/^/      /' || true
[ -n "$ID" ] || { echo "no investigation id returned; stopping"; exit 1; }
STARTED=$(date +%s)

echo "== 5. idempotency"
call "duplicate POST (same key, same body)" 202 -X POST "$API/investigations" -H @"$HEADER_FILE" -H 'content-type: application/json' -d "$BODY"
[ "$(jq -r '.investigation_id' "$WORK/body")" = "$ID" ] && echo "PASS  same investigation id returned ($ID)" || { echo "FAIL  a different id was returned"; FAILURES=$((FAILURES + 1)); }
call "same key, different body" 409 -X POST "$API/investigations" -H @"$HEADER_FILE" -H 'content-type: application/json' -d "${BODY/0.25/0.30}"

echo "== 6. poll until terminal"
STATUS=""
for attempt in $(seq 1 90); do
  curl -sS -o "$WORK/job" "$API/investigations/$ID" -H @"$HEADER_FILE"
  NEW="$(jq -r '.status' "$WORK/job")"
  if [ "$NEW" != "$STATUS" ]; then STATUS="$NEW"; echo "      t+$(( $(date +%s) - STARTED ))s status=$STATUS steps=$(jq '.steps | length' "$WORK/job")"; fi
  case "$STATUS" in SUCCEEDED|FAILED) break ;; esac
  sleep 1
done
[ "$STATUS" = "SUCCEEDED" ] && echo "PASS  investigation SUCCEEDED" || { echo "FAIL  investigation ended as '$STATUS'"; FAILURES=$((FAILURES + 1)); }

echo "== 7. final job document"
jq '{investigation_id, status, created_at, started_at, finished_at, deadline_at, request, steps, error,
     result: (.result | if . == null then null else {placeholder, exposure, exposure_source, explanation, usage, trace_key} end)}' "$WORK/job"
call "GET the finished investigation" 200 "$API/investigations/$ID" -H @"$HEADER_FILE" > "$WORK/last"; head -1 "$WORK/last"

echo "== $FAILURES check(s) failed"
[ "$FAILURES" -eq 0 ]
