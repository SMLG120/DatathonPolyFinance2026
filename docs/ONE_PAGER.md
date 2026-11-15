# Before You Buy

*PolyFinances AlphaForge AI Datathon 2026. Fictional simulation: no advice, no
recommendation, no forecast, no trade.*

**The promise.** Before you change your portfolio, our agent investigates
whether the decision respects your own rules, and shows evidence you can
challenge.

**Problem.** A self-directed investor states goals in words ("preserve my
capital", "avoid oil") and then places an order that may contradict them. The
contradiction is often invisible: a fund already holds the company, or a limit
was never written down as a number. Robert, 59, wants
NVIDIA at 25% of his portfolio; Mateo, 41, wants to buy a broad fund while
avoiding oil and controversies.

**Approach.** The investor confirms rules with explicit numbers. The system
checks one proposed purchase against those rules and returns PASS, FAIL or
UNKNOWN for each rule, with the evidence behind every figure. The investor can
then dispute a fact, clarify a preference, or change a rule. The split of
work, by design:

| Deterministic (Python engine) | Agentic (Claude Sonnet on Amazon Bedrock) |
| --- | --- |
| Exposure through funds, rule statuses, the 2022 replay, the largest weight that passes every rule | Reads the investor's words into *proposed* rules and asks when wording is ambiguous; it cannot supply a number |
| The same inputs always give the same result | Chooses which allowlisted tools to call during an investigation |
| Runs every check whatever the model did, and writes every sentence shown | Selects which evidence to highlight; never produces or changes a number, a status, a policy or a displayed sentence |

**Why the result can be trusted.**

- *Unknown is not a pass.* When a fund's holdings are missing or partial, the
  result is a range. A rule is UNKNOWN when its limit falls inside the range;
  missing data is never counted as zero.
- *Policies are immutable versions.* Changing a rule creates a new version;
  the earlier version and its report stay unchanged. Raising a limit changes
  the status, not the measured exposure.
- *The server enforces the calculation.* The model cannot skip an unfavourable
  rule, and if the model is unavailable the same checks still run.
- *Evidence records.* Each figure has a source, a date, a unit, a formula and
  the records it was derived from. "PASS" means consistent with the
  investor's own confirmed rules, not "a good investment".

**Data and AWS.** Organizer price and FX files; holdings from the issuers' own
files for SPY (State Street) and XIU (BlackRock Canada), one snapshot dated
2026-11-12, used only for today's look-through; controversy records from
official pages. API Gateway, three Lambda functions, Amazon Bedrock, a private
S3 bucket as the only store, one SAM template.

**Current state.** Candidate: local branch `integration/rc` at `deec650`, plus fixes in progress.
Working locally on the real data: engine, seven-route backend, interpreter,
interface with a 3D exposure view, and both scenarios in a browser against the
real handlers. On real data Robert's request fails both of his rules (NVIDIA
26.23% to 26.28% against 10%; 2022 replay loss 17.78% against 10%), and
raising his cap to 30% leaves the loss rule failing. **Not yet verified: any
deployment of this candidate, the real model with the current prompts, and
hosting.** AWS today runs an earlier slice with a placeholder calculation. An
independent validation gave "go with disclosed limits", conditional on one fix
in progress.

**Disclosed limits.** One shared access code, no user identity. Model text is
never shown: explanations are server templates. The interpreter depends on a
model call never yet made live. The 5 s check budget is measured, not
pre-emptive. Policies and results do not expire. ESGV and QQQ holdings are
missing; SPY has no sector labels; the controversy registry holds three
records. The 2022 replay tests one past year and predicts nothing. The AWS
account is deleted at the end of 2026-11-16.

**Why it is not advice.** The system never proposes what to buy, never
forecasts a return and never says a purchase is good or safe. It measures a
decision the investor already made against rules the investor wrote, and says
what it could not determine: a second look before acting. A CIRO news
release dated 2026-03-12 announces guidance that, in its words, "broadens the
range of decision-making supports that OEO dealers can offer to clients
without violating the rule that prohibits them from making recommendations";
we did not read the guidance itself and claim no regulatory approval.
