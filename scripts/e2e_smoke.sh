#!/usr/bin/env bash
# End-to-end smoke test against the deployed HTTP API (curl + jq, no AWS CLI). Milestone-5 request shapes
# (contracts/api.md): portfolio, confirm, check, investigation, poll, challenge. One real investigation per run.
# Not yet run against AWS; exercised locally against the handlers behind a loopback HTTP server.
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
PERSONA="${PERSONA:-robert}"
UNKNOWN_ID="inv-00000000000000000000000000000000"
FAILURES=0

call() { # call LABEL EXPECTED_STATUS curl-args... ; prints status, time and the start of the body
  local label="$1" expected="$2"; shift 2
  local status
  status="$(curl -sS -o "$WORK/body" -D "$WORK/headers" -w '%{http_code} %{time_total}' "$@")"
  local code="${status%% *}" seconds="${status##* }"
  if [ "$code" = "$expected" ]; then echo "PASS  $label -> HTTP $code in ${seconds}s"; else echo "FAIL  $label -> HTTP $code (expected $expected) in ${seconds}s"; FAILURES=$((FAILURES + 1)); fi
  if [ -s "$WORK/body" ]; then (jq -c . "$WORK/body" 2>/dev/null || head -c 400 "$WORK/body") | cut -c1-400 | sed 's/^/      /'; fi
}
check() { # check LABEL jq-filter FILE ; the filter must print true
  if [ "$(jq -r "$2" "$3" 2>/dev/null)" = "true" ]; then echo "PASS  $1"; else echo "FAIL  $1"; FAILURES=$((FAILURES + 1)); fi
}
JSON=(-H @"$HEADER_FILE" -H 'content-type: application/json')

echo "== API $API   persona $PERSONA   idempotency key $KEY"
echo "== 1. authentication"
call "GET portfolio without a token" 401 "$API/portfolios/$PERSONA"
call "POST /investigations without a token" 401 -X POST "$API/investigations" -H 'content-type: application/json' -d '{}'
call "GET with a wrong token" 403 "$API/portfolios/$PERSONA" -H 'Authorization: Bearer this-is-not-the-access-code-0000'

echo "== 2. CORS preflight (no token)"
call "OPTIONS /investigations" 204 -X OPTIONS "$API/investigations" -H 'Origin: https://example.org' -H 'Access-Control-Request-Method: POST' -H 'Access-Control-Request-Headers: authorization,content-type,idempotency-key'
grep -i '^access-control-' "$WORK/headers" | tr -d '\r' | sed 's/^/      /' || true

echo "== 3. portfolio (GET /portfolios/{persona_id})"
call "GET /portfolios/$PERSONA" 200 "$API/portfolios/$PERSONA" -H @"$HEADER_FILE"
cp "$WORK/body" "$WORK/portfolio"
check "the scenario is fictional and offers rules and a demo request" '.scenario.fictional == true and (.scenario.scenario_rules | length) > 0 and (.scenario.demo_requests | length) > 0' "$WORK/portfolio"
call "GET an unknown persona" 404 "$API/portfolios/nobody" -H @"$HEADER_FILE"
REQUEST="$(jq -c '.scenario.demo_requests[0].purchase_request' "$WORK/portfolio")"

echo "== 4. confirm the scenario rules (POST /rules/confirm)"
jq -c '{persona_id: .scenario.persona.persona_id, policy_id: null, base_version: null, objectives: .scenario.objectives,
        confirmations: [.scenario.scenario_rules[] | {rule: ., threshold: .threshold}], withdraw_rule_ids: [], change_note: null}' "$WORK/portfolio" > "$WORK/confirm"
call "POST /rules/confirm" 201 -X POST "$API/rules/confirm" "${JSON[@]}" -d @"$WORK/confirm"
POLICY_ID="$(jq -r '.policy.policy_id // empty' "$WORK/body")"; VERSION="$(jq -r '.policy.version // empty' "$WORK/body")"
[ -n "$POLICY_ID" ] || { echo "no policy id returned; stopping"; exit 1; }
check "every stored rule is CONFIRMED" '[.policy.rules[].status] | all(. == "CONFIRMED")' "$WORK/body"
call "POST /rules/confirm with an invalid body" 400 -X POST "$API/rules/confirm" "${JSON[@]}" -d '{"persona_id":"robert"}'

echo "== 5. deterministic check (POST /check)"
jq -cn --arg p "$PERSONA" --arg id "$POLICY_ID" --argjson v "$VERSION" --argjson r "$REQUEST" \
  '{persona_id: $p, policy_id: $id, policy_version: $v, purchase_request: $r, draft_rules: null}' > "$WORK/check"
call "POST /check" 200 -X POST "$API/check" "${JSON[@]}" -d @"$WORK/check"
cp "$WORK/body" "$WORK/check_result"
jq -c '{headline: .summary.headline, calculation_version, rules: [.rule_results[] | {rule_id, status, measured, limit}], max_compliant: (.max_compliant | {status, final_direct_weight, binding_constraint})}' "$WORK/check_result" | sed 's/^/      /'
call "POST /check a second time" 200 -X POST "$API/check" "${JSON[@]}" -d @"$WORK/check"
if [ "$(jq -cS . "$WORK/body")" = "$(jq -cS . "$WORK/check_result")" ]; then echo "PASS  two /check calls return the same document"; else echo "FAIL  two /check calls differ"; FAILURES=$((FAILURES + 1)); fi
call "POST /check with NaN as the target" 400 -X POST "$API/check" "${JSON[@]}" -d "$(sed 's/"target_direct_weight":[0-9.]*/"target_direct_weight":NaN/' "$WORK/check")"
call "POST /rules/interpret (not implemented: documented 502)" 502 -X POST "$API/rules/interpret" "${JSON[@]}" \
  -d "$(jq -cn --arg p "$PERSONA" '{persona_id: $p, text: "No more than 10% in one company.", policy_id: null, policy_version: null}')"

echo "== 6. investigation: validation, create, idempotency"
jq -cn --arg p "$PERSONA" --arg id "$POLICY_ID" --argjson v "$VERSION" --argjson r "$REQUEST" \
  '{persona_id: $p, policy_id: $id, policy_version: $v, request: $r, parent_investigation_id: null}' > "$WORK/create"
call "POST /investigations with an invalid body" 400 -X POST "$API/investigations" "${JSON[@]}" -H "Idempotency-Key: $KEY-bad" -d '{"persona_id":"robert"}'
call "POST /investigations without an idempotency key" 400 -X POST "$API/investigations" "${JSON[@]}" -d @"$WORK/create"
call "GET an unknown investigation" 404 "$API/investigations/$UNKNOWN_ID" -H @"$HEADER_FILE"
call "POST /investigations (202 only after the worker invocation was accepted)" 202 -X POST "$API/investigations" "${JSON[@]}" -H "Idempotency-Key: $KEY" -d @"$WORK/create"
ID="$(jq -r '.id // empty' "$WORK/body")"; POLL_PATH="$(jq -r '.poll.path // empty' "$WORK/body")"
[ -n "$ID" ] && [ -n "$POLL_PATH" ] || { echo "no investigation id or poll path returned; stopping"; exit 1; }
STARTED=$(date +%s)
call "duplicate POST (same key, same body)" 202 -X POST "$API/investigations" "${JSON[@]}" -H "Idempotency-Key: $KEY" -d @"$WORK/create"
[ "$(jq -r '.id' "$WORK/body")" = "$ID" ] && echo "PASS  same investigation id returned ($ID)" || { echo "FAIL  a different id was returned"; FAILURES=$((FAILURES + 1)); }
call "same key, different body" 409 -X POST "$API/investigations" "${JSON[@]}" -H "Idempotency-Key: $KEY" -d "$(jq -c '.request.original_words = "another request"' "$WORK/create")"

echo "== 7. poll until terminal (poll.path is relative to the base URL)"
STATUS=""
for attempt in $(seq 1 120); do
  curl -sS -o "$WORK/job" "$API$POLL_PATH" -H @"$HEADER_FILE"
  NEW="$(jq -r '.status' "$WORK/job")"
  if [ "$NEW" != "$STATUS" ]; then STATUS="$NEW"; echo "      t+$(( $(date +%s) - STARTED ))s status=$STATUS steps=$(jq '.steps | length' "$WORK/job")"; fi
  case "$STATUS" in SUCCEEDED|FAILED) break ;; esac
  sleep 1.5
done
[ "$STATUS" = "SUCCEEDED" ] && echo "PASS  investigation SUCCEEDED" || { echo "FAIL  investigation ended as '$STATUS'"; jq -c '.failure' "$WORK/job"; FAILURES=$((FAILURES + 1)); }

echo "== 8. final job document"
jq '{id, status, agent, policy_id, policy_version, clarification, failure,
     steps: [.steps[] | {seq, tool, initiated_by, status}],
     explanation: [.explanation[] | {rendered_by, text: (.text | .[0:160])}],
     result: (.result | if . == null then null else {headline: .summary.headline, calculation_version, max_compliant: (.max_compliant | {status, final_direct_weight})} end)}' "$WORK/job"
check "agent.mode is MODEL or DETERMINISTIC_FALLBACK" '.agent.mode == "MODEL" or .agent.mode == "DETERMINISTIC_FALLBACK"' "$WORK/job"
check "the server ran check_rules itself" '[.steps[] | select(.tool == "check_rules" and .initiated_by == "SERVER" and .status == "OK")] | length == 1' "$WORK/job"
check "every explanation statement cites only evidence of the result" '. as $j | [$j.result.evidence[].evidence_id] as $known | [$j.explanation[].evidence_ids[]] | all(. as $i | $known | index($i) != null)' "$WORK/job"
if [ "$(jq -cS '.result' "$WORK/job")" = "$(jq -cS . "$WORK/check_result")" ]; then echo "PASS  the investigation result equals the /check document"; else echo "FAIL  the investigation result differs from /check"; FAILURES=$((FAILURES + 1)); fi

echo "== 9. challenge"
call "POST challenge with an unsupported body" 400 -X POST "$API/investigations/$ID/challenge" "${JSON[@]}" -H "Idempotency-Key: $KEY-ch" -d '{"type":"NOT_A_TYPE"}'

echo "== $FAILURES check(s) failed"
[ "$FAILURES" -eq 0 ]
