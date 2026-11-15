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
- **Numbers come from the investor only, and the model cannot choose among
  them.** A threshold is set only when all of this holds; otherwise it is null
  and the investor is asked for the number:
  - the number lies inside the rule's own words, and it is the only number in
    that sentence (no second percentage, range or alternative; a calendar
    year such as 2022 does not count);
  - it is one plain unsigned percentage (`10%`, `10 %`, `10 percent`,
    `2,5 %`) between 0 and 100, with at most two decimals;
  - the sentence has no hedge ("about", "roughly", "maybe", "or so");
  - the sentence carries a direction cue that agrees with the rule type
    ("at most", "no more than", "do not want to lose more than", "maximum",
    "cap", "limit" for a maximum; "at least", "minimum" for a minimum) and
    none for the other direction; an exclusion needs no cue but must not
    carry a minimum cue;
  - no negation remains once those cue phrases are removed ("I do not want a
    10% limit" gives a question).
  The rule then carries the literal quote and origin `USER_STATED`.
- **Which company is meant is not left to the model.** When a sentence names
  several companies and the model's rule targets only some of them, a cap or
  minimum is reported as unsupported and an exclusion becomes a question.
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

- **Direction, negation and company checks are lexical.** They look for fixed
  English phrases in the investor's sentence. They can only remove a number or
  turn a draft into a question. They do not understand meaning: a maximum
  written without one of the cue phrases ("10% per company is my ceiling for
  tech" works, "I'd stop at 10%" does not) gets a question; a sentence with
  one company where the model picks the wrong rule type but a matching cue is
  present is not caught beyond the cue check; for an exclusion of a single
  named company, whether the investor wants to avoid or keep it rests on the
  model's code. Every draft stays `PROPOSED` and shows the investor's own
  words, so the investor sees and must confirm what was understood.
- **Any other number in the sentence blocks the threshold**, including a
  horizon ("over 5 years, at most 10% per company" gets a question). Only a
  four-digit calendar year is ignored.
- **Throttling:** `POST /rules/interpret` is limited to 2 requests per second
  (burst 5); the clarify-preference challenge shares the challenge route's
  limit (5 per second, burst 10).

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
