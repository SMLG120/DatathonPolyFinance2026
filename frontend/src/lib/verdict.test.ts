import { describe, expect, it } from "vitest";
import type { Headline } from "@/lib/contracts";
import { FIXTURES } from "@/lib/fixtures";
import { probe, recorded } from "@/test/probes";
import {
  activeRules,
  bindingConstraintText,
  coverageText,
  diffPolicies,
  findEvidence,
  isTerminalJobStatus,
  issuerName,
  pairRuleResults,
  summaryCounts,
  unknownCauseText,
  verdictHeadline,
} from "./verdict";

const policyV1 = FIXTURES.confirmRobertV1.response.policy;
const policyV2 = FIXTURES.challenges.changeRule.response.policy;
if (!policyV2) throw new Error("The recorded rule change carries no policy.");

describe("summaryCounts", () => {
  it("is the engine's own counts: nothing is counted from the list of results", () => {
    const summary = recorded.robertResult().summary;
    expect(summaryCounts(summary)).toEqual({ pass: summary.counts.pass, fail: summary.counts.fail, unknown: summary.counts.unknown, total: summary.rules_evaluated });
    // Counts that contradict the two rule results listed are still the ones reported.
    const job = probe.sentinelFigures();
    expect(job.result?.rule_results).toHaveLength(2);
    expect(summaryCounts(job.result!.summary)).toEqual({ pass: 7, fail: 8, unknown: 9, total: 24 });
  });
});

describe("verdictHeadline, on recorded summaries", () => {
  it("states Robert's two failures", () => {
    expect(verdictHeadline(recorded.robertResult().summary)).toMatchObject({ tone: "fail", title: "2 of 2 confirmed rules are not respected" });
  });

  it("states that Mateo's preview is not determined, and that this is not a pass", () => {
    const headline = verdictHeadline(recorded.mateoPreviewUnknown().summary);
    expect(headline.tone).toBe("unknown");
    expect(headline.title).toBe("Not determined: 1 of 1 confirmed rule could not be checked");
    expect(headline.detail).toMatch(/not a pass/);
  });

  it("states one failure of two after Robert's rule change", () => {
    const summary = recorded.robertAfterChangeJob().result!.summary;
    expect(verdictHeadline(summary)).toMatchObject({ tone: "fail", title: `${summary.counts.fail} of ${summary.rules_evaluated} confirmed rules ${summary.counts.fail === 1 ? "is" : "are"} not respected` });
  });

  it("gives a request that was not evaluated no verdict tone", () => {
    expect(verdictHeadline(recorded.invalidRequest().summary)).toMatchObject({ tone: "none", title: "This request cannot be evaluated" });
  });
});

describe("verdictHeadline, on summaries no recording holds", () => {
  it("says all rules are respected only when the engine says so and its counts agree", () => {
    expect(verdictHeadline(probe.summaryWith("ALL_PASS", { pass: 3, fail: 0, unknown: 0, evaluated: 3 }))).toMatchObject({ tone: "pass", title: "All 3 confirmed rules are respected" });
    expect(verdictHeadline(probe.summaryWith("ALL_PASS", { pass: 1, fail: 0, unknown: 0, evaluated: 1 })).title).toBe("The one confirmed rule is respected");
  });

  it("states a failure even when other checks are unknown, and still mentions the unknowns", () => {
    const headline = verdictHeadline(probe.summaryWith("HAS_FAIL", { pass: 1, fail: 1, unknown: 2, evaluated: 4 }));
    expect(headline.tone).toBe("fail");
    expect(headline.title).toBe("1 of 4 confirmed rules is not respected");
    expect(headline.detail).toMatch(/2 more could not be determined/);
    expect(headline.detail).toMatch(/not counted as passed/);
  });

  it("does not present an empty check as a pass", () => {
    expect(verdictHeadline(probe.summaryWith("ALL_PASS", { pass: 0, fail: 0, unknown: 0, evaluated: 0 }))).toMatchObject({ tone: "none", title: "No confirmed rule was checked" });
    expect(verdictHeadline(probe.summaryWith("NO_RULES_EVALUATED", { pass: 0, fail: 0, unknown: 0, evaluated: 0 })).tone).toBe("none");
  });

  it("is favourable for exactly one combination: ALL_PASS with no failure, no unknown and at least one rule", () => {
    const headlines: Headline[] = ["ALL_PASS", "HAS_FAIL", "NO_FAIL_BUT_UNKNOWN", "POLICY_CONFLICT", "NO_RULES_EVALUATED", "INVALID_REQUEST", "EXECUTION_ERROR"];
    for (const headline of headlines) {
      for (let pass = 0; pass <= 2; pass += 1) {
        for (let fail = 0; fail <= 2; fail += 1) {
          for (let unknown = 0; unknown <= 2; unknown += 1) {
            const worded = verdictHeadline(probe.summaryWith(headline, { pass, fail, unknown, evaluated: pass + fail + unknown }));
            const favourable = headline === "ALL_PASS" && fail === 0 && unknown === 0 && pass > 0;
            expect(worded.tone === "pass", `${headline} ${pass}/${fail}/${unknown}`).toBe(favourable);
            if (!favourable) expect(worded.title, `${headline} ${pass}/${fail}/${unknown}`).not.toMatch(/rule is respected|rules are respected/);
          }
        }
      }
    }
  });

  it("shows no overall statement when the headline and the counts disagree", () => {
    for (const summary of [
      probe.summaryWith("ALL_PASS", { pass: 1, fail: 1, unknown: 0, evaluated: 2 }),
      probe.summaryWith("ALL_PASS", { pass: 1, fail: 0, unknown: 1, evaluated: 2 }),
      probe.summaryWith("HAS_FAIL", { pass: 2, fail: 0, unknown: 0, evaluated: 2 }),
      probe.summaryWith("NO_FAIL_BUT_UNKNOWN", { pass: 1, fail: 1, unknown: 1, evaluated: 3 }),
      probe.summaryWith("NO_FAIL_BUT_UNKNOWN", { pass: 2, fail: 0, unknown: 0, evaluated: 2 }),
    ]) {
      expect(verdictHeadline(summary)).toMatchObject({ tone: "none", title: "The summary of this result is inconsistent" });
    }
  });
});

describe("wording", () => {
  it("reads coverage statuses and causes of an unknown in words", () => {
    expect(coverageText("COVERED")).toBe("Complete");
    expect(coverageText("PARTIAL")).toBe("Partial");
    expect(coverageText("MISSING")).toBe("Missing");
    expect(unknownCauseText("MISSING_HOLDINGS")).toBe("a fund has no holdings file");
    expect(unknownCauseText("PARTIAL_HOLDINGS")).toBe("a fund's holdings file reports only part of the fund");
  });

  it("names what stops a larger purchase", () => {
    const max = recorded.robertResult().max_compliant;
    if (max?.status !== "SUPPORTED") throw new Error("The recording changed.");
    expect(bindingConstraintText(max.binding_constraint, (ruleId) => `rule ${ruleId}`)).toBe("the rule “rule robert-issuer-cap-1”");
  });

  it("names a company from the exposure rows of the result, and falls back to its id", () => {
    const result = recorded.robertResult();
    expect(issuerName(result, "ROYAL_BANK_OF_CANADA")).toBe("Royal Bank of Canada");
    expect(issuerName(result, "NOT_LISTED")).toBe("NOT_LISTED");
    expect(issuerName(recorded.invalidRequest(), "NVIDIA")).toBe("NVIDIA");
  });

  it("finds an evidence record by id, and none for an id the result does not hold", () => {
    const result = recorded.robertResult();
    expect(findEvidence(result, "ev-cash-after")?.formula).toBe("0.30 - (0.25 - 0.00) = 0.05");
    expect(findEvidence(result, "nope")).toBeUndefined();
  });

  it("knows which job statuses are final", () => {
    expect(["QUEUED", "RUNNING", "SUCCEEDED", "FAILED"].map((status) => isTerminalJobStatus(status as never))).toEqual([false, false, true, true]);
  });
});

describe("diffPolicies, on the recorded versions 1 and 2", () => {
  it("pairs the raised limit with the rule it superseded and lists the change first", () => {
    const rows = diffPolicies(policyV1, policyV2);
    expect(rows.map((row) => [row.kind, row.before?.rule_id ?? null, row.after?.rule_id ?? null])).toEqual([
      ["CHANGED", "robert-issuer-cap-1", "robert-issuer-cap-2"],
      ["UNCHANGED", "robert-loss-budget-1", "robert-loss-budget-1"],
    ]);
    expect([rows[0]?.before?.threshold, rows[0]?.after?.threshold]).toEqual([0.1, 0.3]);
  });

  it("counts only the rules in force: the superseded rule of version 2 is not a third rule", () => {
    expect(activeRules(policyV2).map((rule) => rule.rule_id)).toEqual(["robert-issuer-cap-2", "robert-loss-budget-1"]);
    expect(activeRules(null)).toEqual([]);
  });

  it("reports a rule that exists in only one version as added or removed", () => {
    const rows = diffPolicies(policyV2, policyV1);
    // Read backwards, version 1 has neither the superseding id nor a rule superseded by it.
    expect(rows.map((row) => row.kind).sort()).toEqual(["ADDED", "REMOVED", "UNCHANGED"]);
  });

  it("pairs the rule results of the two recorded reports", () => {
    const older = recorded.robertResult();
    const newer = recorded.robertAfterChangeJob().result!;
    const pairs = pairRuleResults(policyV1, policyV2, older, newer);
    expect(pairs.map((pair) => [pair.before?.rule_id, pair.before?.status, pair.after?.rule_id, pair.after?.status])).toEqual([
      ["robert-issuer-cap-1", "FAIL", "robert-issuer-cap-2", newer.rule_results.find((item) => item.rule_id === "robert-issuer-cap-2")?.status],
      ["robert-loss-budget-1", "FAIL", "robert-loss-budget-1", "FAIL"],
    ]);
  });
});
