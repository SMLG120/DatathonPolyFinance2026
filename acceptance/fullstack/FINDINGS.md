# Full-stack check: findings

Source: agent A7's run of the built frontend (live mode) in Chromium against the real API handler,
authorizer and worker behind `local_api.py`, on a snapshot of the real data, at commit `db9678c`.
Saved by the integration coordinator from A7's handoff. No backend response deviated from
`contracts/api.md`; every finding is on the frontend side. None is BLOCKER or HIGH.

| Id | Severity | Mismatch | What the user sees | Smallest fix | Test |
|---|---|---|---|---|---|
| F-01 | MEDIUM | The client reads `message` from API Gateway bodies (`403 {"message":"Forbidden"}`, `429 {"message":"Too Many Requests"}`); the contract says act on the status alone. | "The portfolio could not be loaded: Forbidden"; "The investigation could not be started: Too Many Requests". | `frontend/src/lib/api/http-client.ts` `readErrorBody`: return the empty body when `outer.error` is not an object, so the fallback message is used. | `test.fail` in `specs/01-access.spec.ts`, `specs/04-errors.spec.ts` |
| F-02 | MEDIUM | Polling stops after 3 consecutive failed polls; contract §7 polling rule 4 says retry until 180 s. | After about 4.5 s, "The status of the investigation could not be fetched" while the job succeeds on the server. "Check again" works. | `frontend/src/hooks/usePolling.ts`: stop only on an unrecoverable error; drop the consecutive-error limit. | `test.fail` in `specs/04-errors.spec.ts` (and a companion test asserting the current behaviour) |
| F-03 | MEDIUM | After `503 WORKER_INVOCATION_FAILED`, "Try again" reuses the same Idempotency-Key and the backend replays the 503; contract §6 rule 5 requires a new key. | A dead end until the form changes or the page reloads. | `frontend/src/state/workflow.tsx`, catch of `startInvestigation`: release the key on that code; same for the challenge key. Keep the key on 429 and network errors. | `test.fail` in `specs/04-errors.spec.ts` |
| F-04 | MEDIUM | After `409 POLICY_VERSION_CONFLICT` the stale policy stays and the retry sends the same `base_version`; contract §4 rule 8 says drop policy state and restart the rule stage. | The earlier version is still shown as in force; "Try again" is 409 every time. Needs two tabs or two users. | `workflow.tsx` `confirm/failed`: on that code, clear policy and draft. | `test.fail` in `specs/04-errors.spec.ts` |
| F-05 | LOW | After a mid-session 401/403 and a new valid code, the refused request is not repeated (contract silent). | One extra "Try again" click. | Re-run the refused action after re-entry. | observed |
| F-06 | LOW | Non-zero values print as 0.0% (API `possible_extra.proposed` 0.00048735). | "Not attributed up to 0.0%", while the overview chart shows 0.05%. | `frontend/src/lib/format.ts` `formatFraction`: print "< 0.1%" for non-zero values that round to 0.0. | observed |
| F-07 | LOW | The evidence drawer says source details "load with the live API, once it delivers the source registry"; no route delivers it. | A placeholder sentence in live mode. | Remove the sentence in live mode, or add the registry to the contract. | observed |
| F-08 | LOW | `422 INVALID_PURCHASE_REQUEST` gives a generic alert with a "Try again" that can only 422 again; the start button stays enabled although the preview already says INVALID_REQUEST. | "The purchase request cannot be evaluated." | Disable the start button when the preview's `execution.status` is INVALID_REQUEST, or show `details[0].issue`. | observed |

To check on the deployed stage, not a finding: if API Gateway omits CORS headers on authorizer
401/403 responses, a wrong access code is shown as "The code could not be checked", as if the service
were unreachable.

Not exercised here: real API Gateway, IAM, S3, Lambda, Bedrock and the hosted site; a successful
interpreter response (the interpreter did not exist at `db9678c`).
