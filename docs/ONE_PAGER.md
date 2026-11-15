# Before You Buy

*PolyFinances AlphaForge AI Datathon 2026. Fictional simulation: no advice, no
recommendation, no forecast, no trade.*

**The promise.** Before you change your portfolio, our agent investigates
whether the decision respects your own rules, and shows evidence you can
challenge.

**Problem.** A self-directed investor states goals in words ("preserve my
capital", "avoid oil") and then places an order that may contradict them. The
contradiction is often invisible: a fund already holds the company, a file is
missing, or a limit was never written down as a number. Robert, 59, wants
NVIDIA at 25% of his portfolio; Mateo, 41, wants to buy a broad fund while
avoiding oil and controversies.

**Approach.** The investor confirms rules with explicit numbers. The system
checks one proposed purchase against those rules and returns PASS, FAIL or
UNKNOWN for each rule, with the evidence behind every figure. The investor can
then dispute a fact, clarify a preference, or change a rule. The split of
work, by design:

| Deterministic (Python engine) | Agentic (Claude Sonnet on Amazon Bedrock) |
| --- | --- |
| Exposure through funds, rule statuses, the 2022 replay, the largest weight that passes every rule | Turns the investor's words into *proposed* rules and asks when wording is ambiguous |
| The same inputs always give the same result | Chooses which allowlisted tools to call during an investigation |
| Runs every applicable check whatever the model did | Words the explanation; never produces or changes a number, a status or a policy |

**Why the result can be trusted.**

- *Unknown is not a pass.* When a fund's holdings are missing or partial, the
  result is a range. A rule is UNKNOWN when its limit falls inside the range;
  missing data is never counted as zero.
- *Policies are immutable versions.* Changing a rule creates a new version;
  the earlier version and its report stay unchanged. Raising a limit changes
  the status, not the measured exposure.
- *The server enforces the calculation.* The model cannot skip an unfavourable
  rule by not calling a tool, and it never writes the verdict.
- *Evidence records.* Each figure has a source, a date, a unit, a formula and
  the records it was derived from. "PASS" means consistent with the
  investor's own confirmed rules, not "a good investment".

**Data.** Organizer price and FX files; holdings from the issuers' own files
for SPY (State Street) and XIU (BlackRock Canada), one snapshot dated
2026-11-12, used only for today's look-through; three controversy records from
official pages. Absence from the registry means "not assessed".

**AWS.** API Gateway, three Lambda functions, Amazon Bedrock, a private S3
bucket used as the job store, CloudWatch Logs, one SAM template.

**Current state (commit `d36e41f`, 2026-11-15 UTC).** Built and tested: the
contracts, the data pipeline and the engine (1083 automated tests pass, 3
skipped). Deployed on AWS: the investigation pipeline from the API to Bedrock
and S3, proven with real requests, **with a placeholder calculation**. In
progress, not finished: the engine inside the deployed worker, the remaining
API routes, the interface on the final data shapes, independent validation.
The interface runs on test fixtures and is not hosted.

**Limits.** Two funds with holdings; two others deliberately unknown. No
sector labels for SPY's constituents. Three issuers researched for
controversies. One shared demonstration access code, not user identity. The
2022 replay tests an assumed allocation against one past year; it is not a
prediction. The AWS account is deleted at the end of 2026-11-16.

**Why it is not advice.** The system never proposes what to buy, never
forecasts a return and never says a purchase is good or safe. It measures a
decision the investor already made against rules the investor wrote, says what
it could not determine, and leaves the decision with the investor. A CIRO news
release dated 2026-03-12 announces guidance that, in its words, "broadens the
range of decision-making supports that OEO dealers can offer to clients
without violating the rule that prohibits them from making recommendations";
we did not read the guidance itself and claim no regulatory approval.

**User benefit.** A second look before acting, in the investor's own terms,
that is honest about what it does not know.
