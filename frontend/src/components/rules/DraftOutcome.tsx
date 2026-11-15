"use client";

import type { ClarificationOption, Rule } from "@/lib/contracts";
import { measureKey, ruleParametersText, ruleTypeLabel } from "@/lib/rules";
import { activeRules } from "@/lib/verdict";
import { useWorkflow } from "@/state/workflow";

/** "Maximum exposure to a single company — any single company" */
export const ruleName = (rule: Rule) => `${ruleTypeLabel(rule.rule_type)} — ${ruleParametersText(rule)}`;

/**
 * Where a drafted rule ended up, in words: listed as proposed, already listed
 * under another wording, or already in force. Nothing is dropped silently.
 * `place` says where the reader is: on the Goals & rules stage itself, or
 * elsewhere.
 */
export function DraftOutcome({ draft, place = "here" }: { draft: Rule; place?: "here" | "elsewhere" }) {
  const { state, derived } = useWorkflow();
  const policy = derived.currentPolicy;
  const list = place === "here" ? "“Proposed rules” below" : "“Proposed rules” in Goals & rules";

  // The same rule is the same id and the same check: another answer can have given another rule this id.
  if (state.proposedRules.some((rule) => rule.rule_id === draft.rule_id && measureKey(rule) === measureKey(draft))) {
    return (
      <>
        <span className="font-semibold">Listed under {list}, without a number.</span> Enter the number you want there, then confirm.
      </>
    );
  }
  const same = state.proposedRules.find((rule) => measureKey(rule) === measureKey(draft));
  if (same) {
    return (
      <>
        <span className="font-semibold">Already listed under {list}:</span> {ruleName(same)}. Check its number there, then confirm.
      </>
    );
  }
  const inForce = activeRules(policy).find((rule) => measureKey(rule) === measureKey(draft));
  if (inForce) {
    return (
      <>
        <span className="font-semibold">Already in force</span> in policy version <span className="tabular">{policy?.version}</span>: {ruleName(inForce)}.
        {place === "here" ? " Change its number in the Challenge stage." : " Its number can be changed under “Change a rule”."}
      </>
    );
  }
  return <>This draft could not be listed.</>;
}

/** What choosing a definition led to. A supported option carries the draft rule it leads to, or none. */
export function OptionOutcome({ option, place = "here" }: { option: ClarificationOption | undefined; place?: "here" | "elsewhere" }) {
  if (!option) return null;
  if (!option.proposed_rule) return <>Recorded. {option.description}</>;
  return <DraftOutcome draft={option.proposed_rule} place={place} />;
}
