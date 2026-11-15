import { describe, expect, it } from "vitest";
import type { Policy, Rule, VerdictStatus } from "@/lib/contracts";
import { countStatuses, diffPolicies, verdictHeadline } from "./verdict";

const headlineFor = (...statuses: VerdictStatus[]) => verdictHeadline(countStatuses(statuses));
const FAVOURABLE = /respected|all \d+ confirmed rules are|\bpass(es|ed)?\b(?!.*not a pass)/i;

describe("countStatuses", () => {
  it("counts pass, fail and unknown separately", () => {
    expect(countStatuses(["PASS", "FAIL", "UNKNOWN", "UNKNOWN"])).toEqual({ pass: 1, fail: 1, unknown: 2, total: 4 });
    expect(countStatuses([])).toEqual({ pass: 0, fail: 0, unknown: 0, total: 0 });
  });
});

describe("verdictHeadline", () => {
  it("says all rules are respected only when every one passed", () => {
    const headline = headlineFor("PASS", "PASS");
    expect(headline.tone).toBe("pass");
    expect(headline.title).toBe("All 2 confirmed rules are respected");
  });

  it("words a single passing rule without a plural", () => {
    expect(headlineFor("PASS").title).toBe("The one confirmed rule is respected");
  });

  it("never reports a pass when any check is unknown", () => {
    for (const statuses of [
      ["PASS", "UNKNOWN"],
      ["UNKNOWN"],
      ["PASS", "PASS", "PASS", "UNKNOWN"],
    ] as VerdictStatus[][]) {
      const headline = headlineFor(...statuses);
      expect(headline.tone).toBe("unknown");
      expect(headline.title).toMatch(/^Not determined/);
      expect(headline.title).not.toMatch(/respected/i);
      expect(headline.title).not.toMatch(/\ball\b/i);
      expect(headline.detail).toMatch(/not a pass/i);
    }
  });

  it("states how many checks are unknown", () => {
    expect(headlineFor("PASS", "UNKNOWN", "UNKNOWN").title).toBe("Not determined: 2 of 3 confirmed rules could not be checked");
  });

  it("states a failure even when other checks are unknown, and still counts the unknowns", () => {
    const headline = headlineFor("FAIL", "UNKNOWN", "PASS");
    expect(headline.tone).toBe("fail");
    expect(headline.title).toBe("1 of 3 confirmed rules is not respected");
    expect(headline.detail).toMatch(/1 more could not be determined/);
    expect(headline.detail).toMatch(/not counted as passed/);
  });

  it("states the number of failures", () => {
    const headline = headlineFor("FAIL", "FAIL");
    expect(headline.title).toBe("2 of 2 confirmed rules are not respected");
    expect(headline.detail).toBe("0 passed and none are unknown.");
  });

  it("does not present an empty check as a pass", () => {
    const headline = headlineFor();
    expect(headline.tone).toBe("none");
    expect(headline.title).not.toMatch(FAVOURABLE);
  });

  it("is favourable for exactly one combination: no failure, no unknown, at least one rule", () => {
    const all: VerdictStatus[] = ["PASS", "FAIL", "UNKNOWN"];
    for (const a of all) {
      for (const b of all) {
        for (const c of all) {
          const headline = headlineFor(a, b, c);
          const everyPass = [a, b, c].every((s) => s === "PASS");
          expect(headline.tone === "pass").toBe(everyPass);
          expect(/respected$/.test(headline.title) && !/not respected$/.test(headline.title)).toBe(everyPass);
        }
      }
    }
  });
});

function rule(id: string, status: Rule["status"], max: number, supersedes: string | null = null): Rule {
  return {
    rule_id: id,
    rule_type: "max_issuer_exposure",
    status,
    origin: "FICTIONAL_SCENARIO",
    original_words: "",
    scope_description: "",
    objective_id: null,
    supersedes_rule_id: supersedes,
    issuer_scope: "any",
    max_fraction: max,
  };
}

function policy(version: number, rules: Rule[]): Policy {
  return {
    policy_id: "p",
    policy_version: version,
    previous_version: version > 1 ? version - 1 : null,
    persona_id: "robert",
    created_at: "2026-11-14T15:00:00Z",
    objectives: [],
    rules,
  };
}

describe("diffPolicies", () => {
  it("pairs a rule with the one it superseded and lists changes first", () => {
    const v1 = policy(1, [rule("cap", "CONFIRMED", 0.1), rule("other", "CONFIRMED", 0.2)]);
    const v2 = policy(2, [rule("other", "CONFIRMED", 0.2), rule("cap-v2", "CONFIRMED", 0.3, "cap"), rule("cap", "SUPERSEDED", 0.1)]);

    const rows = diffPolicies(v1, v2);
    expect(rows.map((r) => [r.kind, r.before?.rule_id ?? null, r.after?.rule_id ?? null])).toEqual([
      ["CHANGED", "cap", "cap-v2"],
      ["UNCHANGED", "other", "other"],
    ]);
  });

  it("reports rules that were added or removed", () => {
    const v1 = policy(1, [rule("a", "CONFIRMED", 0.1)]);
    const v2 = policy(2, [rule("b", "CONFIRMED", 0.2)]);
    expect(diffPolicies(v1, v2).map((r) => r.kind)).toEqual(["ADDED", "REMOVED"]);
  });

  it("ignores superseded rules of the older version", () => {
    const v1 = policy(1, [rule("a", "CONFIRMED", 0.1), rule("old", "SUPERSEDED", 0.05)]);
    const v2 = policy(2, [rule("a", "CONFIRMED", 0.1)]);
    expect(diffPolicies(v1, v2).map((r) => r.kind)).toEqual(["UNCHANGED"]);
  });
});
