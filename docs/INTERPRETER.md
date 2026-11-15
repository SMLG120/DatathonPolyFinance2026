# Rule interpreter: behaviour and limitations

Code: `backend/agents/interpreter.py`. Routes: `POST /rules/interpret` and the
`CLARIFY_PREFERENCE` challenge (`contracts/api.md` §3 and the challenge section).
Tests: `backend/tests/service/test_service_interpreter.py` (in01–in36) and
`backend/tests/service/test_service_interpreter_agent.py` (ia01–ia14, the agent features).
Server vocabulary: `backend/agents/themes.py`. Prompt version: `interpreter-2`.

## The interpretation agent (interpreter-2)

The interpreter is a small bounded agent, not a single keyword parse:

- **Lookups before answering.** The model may call two read-only tools that the
  server answers from the data snapshot: `find_companies` (common names,
  misspellings, partial names, for words the investor wrote) and
  `describe_sector` (example companies under a sector label). It then submits
  with `submit_interpretation`. Bounds: 2 lookup rounds, 6 calls per round, then
  the model is told to submit; a third request for lookups is rejected. A model
  call starts only when 13 s of the 20 s budget remain, so a lookup round is
  only possible when the model answers fast; the rest of the time the
  deterministic matching below already covers it.
- **Broader vocabulary.** Two new topics:
  - `THEME` (`ENVIRONMENTAL`, `ESG`, `SOCIAL`; polarity `ONLY`, `AVOID`,
    `PREFER`). "I want only environmental investments", "nothing that hurts the
    planet", "keep it ethical" become a question whose options are the
    definitions the data can check: leave out the fund-reported Energy label
    (environmental only), leave out companies with a recorded controversy, name
    sectors, name companies. The definitions it cannot check (green rating, ESG
    score, social classification) are shown as unsupported, next to "keep it
    qualitative".
  - `SECTOR_FOCUS`. "Only tech stocks", "just banks and utilities" draft one
    exclusion (no number) per *other* sector label in the snapshot. Each kept
    sector must be written in the investor's words, as the label or an everyday
    word for it (`SECTOR_ALIASES`); otherwise the request is listed as
    unsupported with the labels the data has. At most 14 exclusions.
- **Common company names** ("Google", "RBC", "Exxon", "P&G") resolve
  deterministically through `COMPANY_ALIASES`, only to companies in the snapshot.
- **Theme safety net.** If the model gives no code to a theme word that follows
  an "only", "avoid" or "prefer" cue in the same sentence, the server asks the
  theme question anyway. It can only add a question, never a rule, and it never
  replaces the oil question or a code the model gave. "ESG matters to me"
  (no cue) stays an objective only.

None of this changes the guarantees below: the model still writes no text that
is shown, cannot supply a number, and every draft is `PROPOSED`.

## What it does

The interpreter turns the investor's words into a **draft**. A draft is never
stored and never active: every rule in it is `PROPOSED` until the investor
confirms it through `POST /rules/confirm`. It never calls the calculation
engine and never produces PASS, FAIL or UNKNOWN.

- **The model only extracts.** Through its submission tool it marks spans of the
  investor's text and chooses from closed lists (objective kind, rule type,
  clarification topic, theme, polarity, unsupported reason, controversy nature,
  a sector label from the data snapshot, a company id among those the server
  found in the text or returned by `find_companies`). No tool has a numeric
  member.
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
- **Company nicknames are matched only from a fixed list.** Companies are
  matched by id, cleaned legal name, upper-case ticker and the aliases in
  `themes.COMPANY_ALIASES`. Any other nickname needs the agent's
  `find_companies` lookup (close spellings and name prefixes), which only runs
  when there is time for a second model call.
- **Themes are never classified.** No sourced environmental, ESG or social data
  exists in the snapshot, so a theme always becomes a question. The Energy
  option is a stand-in and says so.
- **A model span covering a catalog term and something else is dropped
  whole.** For "oil and tobacco" marked as one span, only the oil question is
  asked.
- **A wrong "instruction" label can sit beside the right question.** If the
  model flags words about oil as an instruction to the system, that entry is
  still listed as unsupported next to the correct oil question.
- **Fixed set of clarification topics:** exclusion definition, theme,
  diversification, loss limit, plus the missing-number question. A sector
  focus drafts rules directly.
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

- Verified with a scripted fake model: every case in in01–in36 and ia01–ia14, including
  prompt-injection text, invented companies, unknown rule types, truncated and
  non-JSON answers, throttling, the deadline, and that nothing is stored.
- Mateo's flow was verified **only in process, on synthetic data**: the live
  check's interpretation steps were run against the handlers with three model
  behaviours (correct answer, a guessed Energy rule, oil ignored).
- **Not verified:** the real Bedrock model has not been called. Prompt
  quality, latency against the 12-second read timeout and the model's
  tool-use behaviour are unknown until the stack is deployed.
