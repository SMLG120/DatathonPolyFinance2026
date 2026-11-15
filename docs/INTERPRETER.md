# Rule interpreter: behaviour and limitations

Code: `backend/agents/interpreter.py`. Routes: `POST /rules/interpret` and the
`CLARIFY_PREFERENCE` challenge (`contracts/api.md` §3 and the challenge section).
Tests: `backend/tests/service/test_service_interpreter.py` (in01–in31).

## What it does

The interpreter turns the investor's words into a **draft**. A draft is never
stored and never active: every rule in it is `PROPOSED` until the investor
confirms it through `POST /rules/confirm`. It never calls the calculation
engine and never produces PASS, FAIL or UNKNOWN.

- **The model only extracts.** Through one tool it marks spans of the
  investor's text and chooses from closed lists (objective kind, rule type,
  clarification topic, unsupported reason, controversy nature, a sector label
  from the data snapshot, a company id among those the server found in the
  text). The tool has no numeric member.
- **The server writes everything shown.** Questions, option labels,
  descriptions and reasons are server templates. The investor's words are
  echoed from the request, character for character. No sentence written by
  the model reaches the client.
- **Numbers come from the investor only.** A threshold is set only when the
  investor's own sentence about that rule contains exactly one percentage
  (`10%`, `10 %`, `10 percent`, `2,5 %`) between 0 and 100. The rule then
  carries the literal quote and origin `USER_STATED`. In every other case the
  threshold is null and the investor is asked for the number.
- **"Oil" is always a question.** The words "oil", "petroleum", "fossil" or
  "fossil fuel(s)" always produce a clarification offering the fund-reported
  Energy sector or named companies, and marking "oil producers" and "fossil
  fuels" as definitions we cannot check. The server's question wins: the
  model's own question, sector label or drafted rule about those words is
  dropped (a controversy rule is kept).
- **Out-of-scope requests** (recommend, forecast, trade, optimize) and text
  that reads as an instruction to the system are listed as unsupported; no
  rule is drafted from them.
- **Failures are visible.** A model error or an unusable answer gets one
  bounded retry, then `502 INTERPRETER_FAILED`. The 20-second deadline gives
  `504 INTERPRETER_TIMEOUT`. There is no canned or fallback draft.

## Limitations

- **Bare decimals and numbers in words get a question, not a threshold.**
  "0.10", "ten percent" or a bare "10" are not accepted as a number, because
  the unit is ambiguous without a percent sign. The investor is asked to enter
  it.
- **"I confirm a 10% limit" gets a question.** Sentences that appear to
  address the system (confirm, approve, set the threshold, ignore …) are
  refused as a source of numbers. The check is lexical, so some legitimate
  sentences are caught. It can only turn a number into a question, never the
  reverse.
- **Company nicknames are not matched.** Companies are matched by id, cleaned
  legal name and upper-case ticker. "Google" does not match Alphabet; the
  request is reported as unsupported for that company.
- **A model span covering a catalog term and something else is dropped
  whole.** For "oil and tobacco" marked as one span, only the oil question is
  asked.
- **A wrong "instruction" label can sit beside the right question.** If the
  model flags words about oil as an instruction to the system, that entry is
  still listed as unsupported next to the correct oil question.
- **Fixed set of clarification topics:** exclusion definition, diversification,
  loss limit, plus the missing-number question.
- **Controversy rules** always start with no date filter and a default set of
  record natures (regulatory finding, court ruling, settlement).
- **An empty extraction is a valid empty draft.** If the model finds nothing,
  the answer is 200 with empty lists.
- **A percentage the investor wrote in a plain sentence can be attached to a
  rule by the model.** It then appears as a `PROPOSED` draft with the
  investor's own quote, and stays inactive until confirmed.

## What has and has not been verified

- Verified with a scripted fake model: every case in in01–in31, including
  prompt-injection text, invented companies, unknown rule types, truncated and
  non-JSON answers, throttling, the deadline, and that nothing is stored.
- Mateo's flow was verified **only in process, on synthetic data**: the live
  check's interpretation steps were run against the handlers with three model
  behaviours (correct answer, a guessed Energy rule, oil ignored).
- **Not verified:** the real Bedrock model has not been called. Prompt
  quality, latency against the 12-second read timeout and the model's
  tool-use behaviour are unknown until the stack is deployed.
