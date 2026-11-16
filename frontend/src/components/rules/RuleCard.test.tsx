import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { createFixturesClient } from "@/lib/api/fixtures-client";
import type { PersonaId, PurchaseRequest, Rule } from "@/lib/contracts";
import { FIXTURES } from "@/lib/fixtures";
import { fractionToPercentInput } from "@/lib/format";
import { draftRule, getRuleThreshold, previewRuleSet } from "@/lib/rules";
import { recorded } from "@/test/probes";
import { LIVE_CONFIG, renderWithApp } from "@/test/render";
import { PREVIEW_LABEL } from "./DraftPreview";
import { PolicyRuleCard, ProposedRuleCard, thresholdProblem } from "./RuleCard";

/** Recorded rules only: the scenario's proposals for Robert, the interpreter's draft for Mateo, the stored policy. */
function scenarioRule(ruleType: Rule["rule_type"]): Rule {
  const rule = FIXTURES.scenarios.robert?.scenario_rules.find((candidate) => candidate.rule_type === ruleType);
  if (!rule) throw new Error(`Robert's scenario has no ${ruleType} rule.`);
  return structuredClone(rule);
}

function systemDraft(): Rule {
  const rule = FIXTURES.interpret.mateo.response.proposed_rules[0];
  if (!rule) throw new Error("The recorded interpretation drafts no rule.");
  return structuredClone(rule);
}

function scenarioPurchase(): PurchaseRequest {
  const request = FIXTURES.scenarios.robert?.demo_requests[0]?.purchase_request;
  if (!request) throw new Error("Robert's scenario has no scripted request.");
  return structuredClone(request);
}

interface HarnessProps {
  rule: Rule;
  /** The other proposed rules, which stand beside this one in a preview at their own numbers. */
  others?: Rule[];
  personaId: PersonaId;
  purchase?: PurchaseRequest | null;
  attempted?: boolean;
}

function Harness({ rule, others = [], personaId, purchase = null, attempted = false }: HarnessProps) {
  // Same initial text as the workflow store: a rule without a number starts with an empty field.
  const [text, setText] = useState(fractionToPercentInput(getRuleThreshold(rule)));
  return (
    <ul>
      <ProposedRuleCard
        rule={rule}
        objective={undefined}
        personaId={personaId}
        policy={null}
        purchase={purchase}
        customPortfolio={null}
        thresholdText={text}
        onThresholdChange={setText}
        buildPreviewRules={(threshold) => previewRuleSet([], [draftRule(rule, threshold), ...others.flatMap((other) => (other.threshold === null ? [] : [draftRule(other, other.threshold)]))])}
        attempted={attempted}
      />
    </ul>
  );
}

function setup(props: HarnessProps, options: Parameters<typeof renderWithApp>[1] = {}) {
  const fixtures = createFixturesClient({ latencyMs: 0 });
  const check = vi.fn(fixtures.check);
  renderWithApp(<Harness {...props} />, { api: { ...fixtures, check }, ...options });
  const card = screen.getByTestId("rule-card");
  return { card, check, field: within(card).getByRole("textbox"), slider: within(card).getByRole("slider"), user: userEvent.setup() };
}

describe("ProposedRuleCard — a rule proposed by the system (the recorded interpretation of Mateo's words)", () => {
  it("arrives with an empty threshold: no number the user did not choose", () => {
    const rule = systemDraft();
    const { card, field, slider } = setup({ rule, personaId: "mateo" });
    expect(rule.origin).toBe("SYSTEM_PROPOSED");
    expect(getRuleThreshold(rule)).toBeNull();
    expect(field).toHaveValue("");
    expect(slider).toHaveAttribute("aria-valuetext", "Not set");
    expect(slider).toHaveAttribute("data-unset", "true");
    expect(within(card).getByTestId("threshold-empty-note")).toHaveTextContent("No threshold has been set");
    expect(within(card).getByTestId("threshold-empty-note")).toHaveTextContent("never the number");
  });

  it("shows the user's words, the plain-language type, the scope, the origin and the inactive status", () => {
    const rule = systemDraft();
    const { card } = setup({ rule, personaId: "mateo" });
    expect(within(card).getByRole("heading", { level: 3 })).toHaveTextContent("Exclusion of companies with a controversy record");
    expect(within(card).getByTestId("rule-original-words")).toHaveTextContent(rule.original_words);
    expect(within(card).getByTestId("rule-scope")).toHaveTextContent(rule.scope_description);
    expect(within(card).getAllByText("Proposed by the system").length).toBeGreaterThan(0);
    expect(within(card).getByText("Proposed: inactive")).toBeInTheDocument();
    expect(card).toHaveAttribute("data-rule-origin", "SYSTEM_PROPOSED");
  });

  it("says nothing about an empty field until the user tries to confirm, then explains", () => {
    const quiet = setup({ rule: systemDraft(), personaId: "mateo" });
    expect(quiet.field).not.toHaveAttribute("aria-invalid");
    quiet.card.remove();

    const { field } = setup({ rule: systemDraft(), personaId: "mateo", attempted: true });
    expect(field).toHaveAttribute("aria-invalid", "true");
    expect(field).toHaveAccessibleDescription(expect.stringContaining(thresholdProblem("") as string));
  });

  it("takes the number the user enters, on the field and on the slider", async () => {
    const { card, field, slider, user } = setup({ rule: systemDraft(), personaId: "mateo" });
    await user.type(field, "5");
    expect(slider).toHaveAttribute("aria-valuetext", "5 percent");
    expect(slider).not.toHaveAttribute("data-unset");
    expect(within(card).queryByTestId("threshold-empty-note")).toBeNull();

    fireEvent.change(slider, { target: { value: "7.5" } });
    expect(field).toHaveValue("7.5");
  });

  it("treats zero as a number the user chose, not as 'not set'", async () => {
    const { card, field, slider, user } = setup({ rule: systemDraft(), personaId: "mateo" });
    await user.type(field, "0");
    expect(thresholdProblem("0")).toBeNull();
    expect(slider).toHaveAttribute("aria-valuetext", "0 percent");
    expect(within(card).queryByTestId("threshold-empty-note")).toBeNull();
    expect(field).not.toHaveAttribute("aria-invalid");
  });

  it.each([
    ["abc", "Enter a number such as 10 or 12.5."],
    ["150", "The threshold cannot be more than 100% of the portfolio."],
  ])("refuses %s and says why, as soon as it is typed", async (typed, message) => {
    const { card, field, user } = setup({ rule: systemDraft(), personaId: "mateo" });
    await user.type(field, typed);
    expect(thresholdProblem(typed)).toBe(message);
    expect(within(card).getByText(message)).toBeInTheDocument();
    expect(field).toHaveAttribute("aria-invalid", "true");
  });
});

describe("ProposedRuleCard — a rule from the fictional scenario", () => {
  it("shows the scenario's number, labelled as coming from the fictional scenario, and is still inactive", () => {
    const { card, field } = setup({ rule: scenarioRule("max_issuer_exposure"), personaId: "robert" });
    expect(field).toHaveValue("10");
    expect(within(card).getAllByText("From the fictional scenario").length).toBeGreaterThan(0);
    expect(within(card).getByText("Proposed: inactive")).toBeInTheDocument();
    expect(within(card).queryByTestId("threshold-empty-note")).toBeNull();
    expect(card).toHaveAttribute("data-rule-origin", "FICTIONAL_SCENARIO");
  });
});

describe("ProposedRuleCard — draft preview", () => {
  const cap = () => scenarioRule("max_issuer_exposure");
  const budget = () => scenarioRule("scenario_loss_budget");
  const withPurchase = () => ({ rule: cap(), others: [budget()], personaId: "robert" as const, purchase: scenarioPurchase() });

  it("is labelled as a preview of a draft, never as the confirmed policy", () => {
    const { card } = setup(withPurchase());
    expect(within(card).getByTestId("draft-preview")).toHaveTextContent(PREVIEW_LABEL);
    expect(PREVIEW_LABEL).toBe("Preview with draft threshold: not your confirmed policy");
  });

  it("previews nothing without a purchase to try the number on, and says so", () => {
    const { card, check, field } = setup({ rule: cap(), personaId: "robert", purchase: null });
    fireEvent.change(field, { target: { value: "20" } });
    expect(within(card).getByTestId("draft-preview")).toHaveTextContent("Enter a purchase in stage 3 first");
    expect(check).not.toHaveBeenCalled();
  });

  it("debounces: two quick changes send one request, for the latest draft only, and show the service's recorded answer", async () => {
    const { card, check, field } = setup(withPurchase());
    fireEvent.change(field, { target: { value: "2" } });
    fireEvent.change(field, { target: { value: "20" } });

    const shown = await within(card).findByTestId("draft-preview-result");
    expect(check).toHaveBeenCalledTimes(1);
    const request = check.mock.calls[0]?.[0];
    // The request the recording holds: the same purchase, the cap as a draft at 20%, the loss budget beside it.
    expect(request?.persona_id).toBe("robert");
    expect(request?.purchase_request).toEqual(scenarioPurchase());
    expect(request?.draft_rules?.map((rule) => [rule.rule_id, rule.threshold, rule.status])).toEqual([
      ["robert-issuer-cap-1", 0.2, "PROPOSED"],
      ["robert-loss-budget-1", 0.1, "PROPOSED"],
    ]);

    const answer = recorded.robertPreview().rule_results.find((result) => result.rule_id === "robert-issuer-cap-1");
    expect(answer?.status).toBe("FAIL");
    expect(shown).toHaveTextContent("Preview: Fail");
    expect(shown).toHaveTextContent("draft limit 20.0%");
    expect(within(shown).getByTestId("rule-measured")).toHaveTextContent("26.2% to 26.4%");
    expect(within(shown).getByTestId("rule-limit")).toHaveTextContent("20.0%");
    expect(within(shown).getByTestId("rule-gap")).toHaveTextContent("6.2 points over the limit");
    expect(shown).toHaveTextContent(answer?.reason as string);
  });

  it("marks a finished preview as test data in fixtures mode, and not on the live service", async () => {
    const fixtures = setup(withPurchase());
    fireEvent.change(fixtures.field, { target: { value: "20" } });
    await within(fixtures.card).findByTestId("draft-preview-result");
    const preview = within(fixtures.card).getByTestId("draft-preview");
    expect(preview).toHaveAttribute("data-figures", "true");
    expect(within(preview).getByTestId("test-data-tag")).toBeInTheDocument();
    fixtures.card.remove();

    const live = setup(withPurchase(), { config: LIVE_CONFIG });
    fireEvent.change(live.field, { target: { value: "20" } });
    await within(live.card).findByTestId("draft-preview-result");
    expect(within(live.card).queryByTestId("test-data-tag")).toBeNull();
  });

  it("says calmly that the test data holds no preview for another draft value, and shows no figure in its place", async () => {
    const { card, field } = setup(withPurchase());
    fireEvent.change(field, { target: { value: "12" } });
    const note = await within(card).findByTestId("draft-preview-not-recorded");
    expect(note).toHaveTextContent("No preview for this draft value in the test data");
    expect(note).toHaveTextContent("Your confirmed rules and reports are unchanged");
    expect(within(card).queryByTestId("draft-preview-result")).toBeNull();
    expect(within(card).queryByTestId("draft-preview-error")).toBeNull();
    // No pass, fail or unknown badge is drawn without an answer from the service.
    expect(card.querySelector("[data-status]")).toBeNull();
  });

  it("removes the preview as soon as the draft is no longer a valid number", async () => {
    const { card, field } = setup(withPurchase());
    fireEvent.change(field, { target: { value: "20" } });
    await within(card).findByTestId("draft-preview-result");

    fireEvent.change(field, { target: { value: "" } });
    await waitFor(() => expect(within(card).queryByTestId("draft-preview-result")).toBeNull());
  });

  it("does not confirm anything by previewing: the rule stays proposed and inactive", async () => {
    const { card, field } = setup(withPurchase());
    fireEvent.change(field, { target: { value: "20" } });
    await within(card).findByTestId("draft-preview-result");
    expect(within(card).getByText("Proposed: inactive")).toBeInTheDocument();
    expect(screen.queryByTestId("policy-rule-card")).toBeNull();
  });
});

describe("PolicyRuleCard, on the recorded policies", () => {
  it("shows a confirmed rule as active with its threshold, read-only", () => {
    const rule = recorded.robertPolicyV1().rules.find((candidate) => candidate.rule_id === "robert-issuer-cap-1");
    if (!rule) throw new Error("The recorded policy has no issuer cap.");
    renderWithApp(
      <ul>
        <PolicyRuleCard rule={rule} objective={undefined} />
      </ul>,
    );
    const card = screen.getByTestId("policy-rule-card");
    expect(rule.status).toBe("CONFIRMED");
    expect(within(card).getByText("Confirmed: active")).toBeInTheDocument();
    expect(within(card).getByTestId("policy-rule-threshold")).toHaveTextContent("10.0%");
    expect(within(card).queryByRole("textbox")).toBeNull();
    expect(within(card).queryByRole("slider")).toBeNull();
  });

  it("shows a superseded rule as no longer in force (version 2 of the recorded rule change)", () => {
    const rule = FIXTURES.challenges.changeRule.response.policy?.rules.find((candidate) => candidate.status === "SUPERSEDED");
    if (!rule) throw new Error("The recorded rule change supersedes no rule.");
    renderWithApp(
      <ul>
        <PolicyRuleCard rule={structuredClone(rule)} objective={undefined} />
      </ul>,
    );
    const card = screen.getByTestId("policy-rule-card");
    expect(within(card).getByText("Superseded")).toBeInTheDocument();
    expect(card).toHaveTextContent("no longer in force");
    expect(within(card).getByTestId("policy-rule-threshold")).toHaveTextContent("10.0%");
  });
});
