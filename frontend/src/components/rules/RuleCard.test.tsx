import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { createFixturesClient } from "@/lib/api/fixtures-client";
import type { PersonaId, Rule } from "@/lib/contracts";
import { FIXTURE_SCENARIOS } from "@/lib/fixtures";
import { fractionToPercentInput } from "@/lib/format";
import { getRuleThreshold } from "@/lib/rules";
import { renderWithApp } from "@/test/render";
import { PREVIEW_LABEL } from "./DraftPreview";
import { PolicyRuleCard, ProposedRuleCard } from "./RuleCard";

function proposedRule(persona: "robert" | "mateo", origin: Rule["origin"]): Rule {
  const rule = FIXTURE_SCENARIOS[persona]?.interpretation.proposed_rules.find((candidate) => candidate.origin === origin);
  if (!rule) throw new Error(`fixture has no ${origin} rule for ${persona}`);
  return rule;
}

function Harness({ rule, personaId, onConfirm }: { rule: Rule; personaId: PersonaId; onConfirm: () => void }) {
  // Same initial text as the workflow store: a rule without a number starts with an empty field.
  const [text, setText] = useState(fractionToPercentInput(getRuleThreshold(rule)));
  return (
    <ul>
      <ProposedRuleCard rule={rule} objective={undefined} personaId={personaId} thresholdText={text} onThresholdChange={setText} onConfirm={onConfirm} confirming={false} />
    </ul>
  );
}

function setup(rule: Rule, personaId: PersonaId) {
  const fixtures = createFixturesClient({ latencyMs: 0 });
  const check = vi.fn(fixtures.check);
  const onConfirm = vi.fn();
  renderWithApp(<Harness rule={rule} personaId={personaId} onConfirm={onConfirm} />, { api: { ...fixtures, check } });
  const card = screen.getByTestId("rule-card");
  return {
    card,
    check,
    onConfirm,
    field: within(card).getByRole("textbox"),
    slider: within(card).getByRole("slider"),
    confirm: within(card).getByTestId("confirm-rule"),
    user: userEvent.setup(),
  };
}

describe("ProposedRuleCard — a rule proposed by the system", () => {
  const rule = proposedRule("mateo", "SYSTEM_PROPOSED");

  it("arrives with an empty threshold: no number the user did not choose", () => {
    const { card, field, slider } = setup(rule, "mateo");
    expect(getRuleThreshold(rule)).toBeNull();
    expect(field).toHaveValue("");
    expect(slider).toHaveAttribute("aria-valuetext", "Not set");
    expect(slider).toHaveAttribute("data-unset", "true");
    expect(within(card).getByTestId("threshold-empty-note")).toHaveTextContent("No threshold has been set");
  });

  it("shows the user's words, the plain-language type, the scope, the origin and the inactive status", () => {
    const { card } = setup(rule, "mateo");
    expect(within(card).getByRole("heading", { level: 3 })).toHaveTextContent("Exclusion of companies with a controversy record");
    expect(within(card).getByTestId("rule-original-words")).toHaveTextContent(rule.original_words);
    expect(within(card).getByTestId("rule-scope")).toHaveTextContent(rule.scope_description);
    expect(within(card).getAllByText("Proposed by the system").length).toBeGreaterThan(0);
    expect(within(card).getByText("Proposed — inactive")).toBeInTheDocument();
    expect(card).toHaveAttribute("data-rule-origin", "SYSTEM_PROPOSED");
  });

  it("cannot be confirmed without a threshold: the button explains instead of acting", async () => {
    const { card, confirm, field, onConfirm, user } = setup(rule, "mateo");
    expect(confirm).toHaveAttribute("aria-disabled", "true");
    // Still a real, focusable button: a keyboard user can reach it and learn why.
    expect(confirm).not.toBeDisabled();

    await user.click(confirm);

    expect(onConfirm).not.toHaveBeenCalled();
    expect(within(card).getByText("Enter a number before confirming. This rule has no threshold yet.")).toBeInTheDocument();
    expect(field).toHaveFocus();
    expect(field).toHaveAttribute("aria-invalid", "true");
  });

  it("can be confirmed once the user has entered a number", async () => {
    const { confirm, field, onConfirm, slider, user } = setup(rule, "mateo");
    await user.type(field, "5");
    expect(slider).toHaveAttribute("aria-valuetext", "5 percent");
    expect(slider).not.toHaveAttribute("data-unset");
    expect(confirm).not.toHaveAttribute("aria-disabled");

    await user.click(confirm);
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it("treats zero as a number the user chose, not as 'not set'", async () => {
    const { confirm, field, user } = setup(rule, "mateo");
    await user.type(field, "0");
    expect(confirm).not.toHaveAttribute("aria-disabled");
  });

  it.each([
    ["abc", "Enter a number such as 10 or 12.5."],
    ["150", "The threshold cannot be more than 100% of the portfolio."],
  ])("refuses %s and says why", async (typed, message) => {
    const { card, confirm, field, onConfirm, user } = setup(rule, "mateo");
    await user.type(field, typed);
    expect(within(card).getByText(message)).toBeInTheDocument();
    expect(confirm).toHaveAttribute("aria-disabled", "true");
    await user.click(confirm);
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("moves the number field when the slider moves", () => {
    const { field, slider } = setup(rule, "mateo");
    fireEvent.change(slider, { target: { value: "7.5" } });
    expect(field).toHaveValue("7.5");
  });
});

describe("ProposedRuleCard — a rule from the fictional scenario", () => {
  const rule = proposedRule("robert", "FICTIONAL_SCENARIO");

  it("shows the scenario's number, labelled as coming from the fictional scenario, and is still inactive", () => {
    const { card, confirm, field } = setup(rule, "robert");
    expect(field).toHaveValue("10");
    expect(within(card).getAllByText("From the fictional scenario").length).toBeGreaterThan(0);
    expect(within(card).getByText("Proposed — inactive")).toBeInTheDocument();
    expect(within(card).queryByTestId("threshold-empty-note")).toBeNull();
    expect(confirm).not.toHaveAttribute("aria-disabled");
  });
});

describe("ProposedRuleCard — draft preview", () => {
  const rule = proposedRule("robert", "FICTIONAL_SCENARIO");

  it("is labelled as a preview of a draft, never as the confirmed policy", () => {
    const { card } = setup(rule, "robert");
    expect(within(card).getByTestId("draft-preview")).toHaveTextContent(PREVIEW_LABEL);
    expect(PREVIEW_LABEL).toBe("Preview with draft threshold — not your confirmed policy");
  });

  it("debounces: two quick changes send one preview request, for the latest draft only", async () => {
    const { card, check, field } = setup(rule, "robert");
    fireEvent.change(field, { target: { value: "1" } });
    fireEvent.change(field, { target: { value: "12" } });

    const result = await within(card).findByTestId("draft-preview-result");
    expect(check).toHaveBeenCalledTimes(1);
    const request = check.mock.calls[0]?.[0];
    expect(request?.is_draft_preview).toBe(true);
    expect(request?.purchase).toBeNull();
    expect(request?.rules.map(getRuleThreshold)).toEqual([0.12]);
    expect(result).toHaveTextContent("Preview: Pass");
    expect(result).toHaveTextContent("12.0%");
  });

  it("removes the preview as soon as the draft is no longer a valid number", async () => {
    const { card, field } = setup(rule, "robert");
    fireEvent.change(field, { target: { value: "12" } });
    await within(card).findByTestId("draft-preview-result");

    fireEvent.change(field, { target: { value: "" } });
    await waitFor(() => expect(within(card).queryByTestId("draft-preview-result")).toBeNull());
  });

  it("does not confirm anything by previewing", async () => {
    const { card, field, onConfirm } = setup(rule, "robert");
    fireEvent.change(field, { target: { value: "30" } });
    await within(card).findByTestId("draft-preview-result");
    expect(onConfirm).not.toHaveBeenCalled();
    expect(within(card).getByText("Proposed — inactive")).toBeInTheDocument();
  });
});

describe("PolicyRuleCard", () => {
  it("shows a confirmed rule as active with its threshold", () => {
    const rule: Rule = { ...proposedRule("robert", "FICTIONAL_SCENARIO"), status: "CONFIRMED" };
    renderWithApp(
      <ul>
        <PolicyRuleCard rule={rule} objective={undefined} />
      </ul>,
    );
    const card = screen.getByTestId("policy-rule-card");
    expect(within(card).getByText("Confirmed — active")).toBeInTheDocument();
    expect(card).toHaveTextContent("10.0%");
    expect(within(card).queryByRole("textbox")).toBeNull();
  });

  it("shows a superseded rule as no longer in force", () => {
    const rule: Rule = { ...proposedRule("robert", "FICTIONAL_SCENARIO"), status: "SUPERSEDED" };
    renderWithApp(
      <ul>
        <PolicyRuleCard rule={rule} objective={undefined} />
      </ul>,
    );
    const card = screen.getByTestId("policy-rule-card");
    expect(within(card).getByText("Superseded")).toBeInTheDocument();
    expect(card).toHaveTextContent("no longer in force");
  });
});
