# Interpreter improvement report (2026-11-15)

Branch `feat/interpreter-multiclause`, from `origin/main` 1f582bf. Code commit `fa47744`. Not pushed, not deployed.

## Previous weaknesses
- "below 10%", "under 10%", "less than 10%" were not maximum cues, so "Keep any single company below 10%" got no number and a question.
- "more than 10%" / "above 10%" were not minimum cues, so a cap drafted from them was not refused by direction ("At most 10% more than today").
- One request holding a minimum above a maximum (or a minimum for a company it also excludes) produced two drafts that no portfolio can meet together; the conflict appeared only at check time.

## Improvements (`backend/agents/interpreter.py`)
- Everyday comparatives count as direction cues, only when written right before the number, after the existing cue phrases are removed (so "don't want more than" stays a maximum, "lose 10% over a year" holds no minimum).
- `_Builder.hold_back_conflicts`: the conflict the engine can prove (`MIN_EXCEEDS_MAX_SAME_ISSUER`, contracts/SEMANTICS.md) is detected among drafts with user-stated numbers, plus minimum vs named exclusion. Both drafts are withdrawn and one question offers "keep only" either one, or neither. Equal limits are not a conflict. Nothing is confirmed by the interpreter.
- Unchanged: the model extracts spans and codes only; numbers come only from the investor's characters; one number per sentence; schema validation; bounded calls.

## Tried and reverted
Clause-level number scoping ("less than 10% in X, but at least 5% in Y" in one sentence). It contradicts validation F-23 (`validation/tests/test_v36_interpreter.py`: a draft carries a number only when the text holds one percentage) and let "At most 20% but at least 10% in NVIDIA" through. Such sentences still get one draft per limit with no number and a question.

## Tests
- New `backend/tests/service/test_service_interpreter_clauses.py`: 17 cases, all pass.
- `validation/tests backend/tests contracts/python/tests` with the real data present: 3257 passed, 6 skipped, 21 xfailed, 1 failed. The failure, `test_v36_the_model_is_offered_one_tool_without_any_numeric_member_and_is_not_forced`, is about the lookup tools added in PR #17; this change does not touch tools.
- Frontend: not changed, not run.

## Real-model evaluation
`scripts/try_interpreter.py`, `us.anthropic.claude-sonnet-5-5`, synthetic snapshot, 10 sentences, 1.3–3.3 s each:
sector caps (technology, energy) and the Canadian minimum → UNSUPPORTED_RULE_TYPE; oil → Energy-label question; tobacco → definition question with no supported sourced option; "too much in risky assets" → question, no number; "Keep any single company below 10%" → max_issuer_exposure 0.10 quoted from "10%"; "Limit tech to 15% and exclude tobacco" → both clauses kept (unsupported + question); "At most 5% in any company. At least 10% in Exxon Mobil." → conflict question; prompt injection → INSTRUCTION_IGNORED, no rule. No invented number.

## Remaining limitations
- Two limits in one sentence get no numbers (by the F-23 rule); the investor enters them.
- "less than" and "more than" are treated as inclusive limits.
- No sector-cap or country rule type exists in schema version 1.
- The deployed Lambda still runs the previous interpreter.
