"use client";

import { useId, useRef, useState } from "react";
import { DraftPreviewPanel, useDraftPreview } from "@/components/rules/DraftPreview";
import { ThresholdInput } from "@/components/rules/ThresholdInput";
import { Button } from "@/components/ui/Button";
import { describedBy, Field, Select } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";
import type { CheckResult, Investigation, Policy } from "@/lib/contracts";
import { EPS, percentInputToFraction } from "@/lib/format";
import { getRuleThreshold, ruleTypeLabel, thresholdHint, thresholdLabel, thresholdText, validateThreshold, withRuleThreshold } from "@/lib/rules";
import { activeRules } from "@/lib/verdict";
import { useWorkflow } from "@/state/workflow";

export interface ChangeRuleFormProps {
  investigation: Investigation;
  result: CheckResult;
  /** The policy version the report was checked against. */
  policy: Policy;
}

/**
 * Path 3: change a rule. A new threshold creates the NEXT policy version and
 * re-checks the same purchase under it. The version the report was checked
 * against, and the report itself, are left exactly as they were.
 */
export function ChangeRuleForm({ investigation, result, policy }: ChangeRuleFormProps) {
  const { state, actions } = useWorkflow();
  const ruleFieldId = useId();
  const thresholdId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const rules = activeRules(policy);
  const [ruleId, setRuleId] = useState(rules[0]?.rule_id ?? "");
  const [text, setText] = useState("");
  const [attempted, setAttempted] = useState(false);

  const rule = rules.find((candidate) => candidate.rule_id === ruleId);
  const current = rule ? getRuleThreshold(rule) : null;
  const threshold = percentInputToFraction(text);
  const problem =
    text.trim() !== "" && threshold === null
      ? "Enter a number such as 10 or 12.5."
      : (validateThreshold(threshold) ??
        (threshold !== null && current !== null && Math.abs(threshold - current) <= EPS
          ? "This is the threshold already confirmed. Enter a different value to change the rule."
          : null));
  const canSubmit = rule !== undefined && problem === null;
  const shownError = problem !== null && (attempted || text.trim() !== "") ? problem : null;
  const busy = state.challenge.status === "loading";
  const nextVersion = policy.policy_version + 1;

  const { preview, onDraftChange } = useDraftPreview({
    personaId: state.personaId,
    purchase: result.purchase,
    buildRules: (draft) => rules.map((candidate) => (candidate.rule_id === ruleId ? withRuleThreshold(candidate, draft) : candidate)),
  });

  if (rules.length === 0 || !rule) {
    return <p className="text-ink-muted">This policy version has no active rule to change.</p>;
  }

  async function submit() {
    if (!canSubmit || threshold === null) {
      setAttempted(true);
      inputRef.current?.focus();
      return;
    }
    const response = await actions.submitChallenge(investigation.investigation_id, { kind: "CHANGE_RULE", rule_id: ruleId, new_threshold: threshold });
    if (response) {
      setText("");
      setAttempted(false);
      preview.clear();
    }
  }

  return (
    <div className="space-y-5" data-testid="change-rule-form">
      <p className="max-w-prose text-ink">
        A rule is yours to change. Changing it does not edit the past: it creates policy version {nextVersion}, checks the same purchase again under
        it, and keeps the report made under version {policy.policy_version}.
      </p>

      <Field htmlFor={ruleFieldId} label="Rule to change" hint={`The active rules of policy version ${policy.policy_version}.`}>
        <Select
          id={ruleFieldId}
          value={ruleId}
          onChange={(event) => {
            setRuleId(event.target.value);
            setText("");
            setAttempted(false);
            preview.clear();
          }}
          aria-describedby={describedBy(ruleFieldId, { hint: true })}
        >
          {rules.map((candidate) => (
            <option key={candidate.rule_id} value={candidate.rule_id}>
              {ruleTypeLabel(candidate.rule_type)} — now {thresholdText(candidate)}
            </option>
          ))}
        </Select>
      </Field>

      <p className="text-ink">
        Confirmed now: <span className="tabular text-lg font-bold">{thresholdText(rule)}</span>{" "}
        <span className="text-ink-muted">(policy version {policy.policy_version})</span>
      </p>

      <ThresholdInput
        id={thresholdId}
        inputRef={inputRef}
        label={`New value — ${thresholdLabel(rule.rule_type).toLowerCase()}`}
        hint={thresholdHint(rule.rule_type)}
        value={text}
        error={shownError}
        onChange={(next) => {
          setText(next);
          onDraftChange(next);
        }}
      />

      <DraftPreviewPanel
        preview={preview}
        ruleId={rule.rule_id}
        ruleType={rule.rule_type}
        subject={result.purchase ? "the portfolio after the same purchase" : "the current portfolio"}
      />

      <Notice tone="info" title="What confirming this change does">
        <ul className="list-disc space-y-1 pl-5">
          <li>Creates policy version {nextVersion} with the new threshold. Version {policy.policy_version} is kept, unchanged.</li>
          <li>Runs a new investigation of the same purchase under version {nextVersion}.</li>
          <li>Shows both results side by side. The earlier report stays openable.</li>
        </ul>
      </Notice>

      <Button variant="primary" softDisabled={!canSubmit} busy={busy} busyLabel="Creating the new version…" onClick={() => void submit()} data-testid="submit-rule-change">
        Confirm the change and check again under version {nextVersion}
      </Button>
    </div>
  );
}
