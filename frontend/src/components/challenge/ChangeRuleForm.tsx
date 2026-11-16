"use client";

import { useId, useRef, useState } from "react";
import { DraftPreviewPanel, useDraftPreview } from "@/components/rules/DraftPreview";
import { ThresholdInput } from "@/components/rules/ThresholdInput";
import { Button } from "@/components/ui/Button";
import { describedBy, Field, Select, TextInput } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";
import type { CheckResult, DemoChallenge, InvestigationJob, Policy } from "@/lib/contracts";
import { customPortfolioOfReport } from "@/lib/customize";
import { EPS, fractionToPercentInput, percentInputToFraction } from "@/lib/format";
import { draftRule, getRuleThreshold, previewRuleSet, ruleParametersText, ruleTypeLabel, thresholdHint, thresholdLabel, thresholdText, validateThreshold } from "@/lib/rules";
import { activeRules } from "@/lib/verdict";
import { useWorkflow } from "@/state/workflow";
import { t, tf } from "@/lib/i18n";

export interface ChangeRuleFormProps {
  job: InvestigationJob;
  result: CheckResult;
  /** The policy version the report was checked against. It is the one in force. */
  policy: Policy;
  example: DemoChallenge | null;
}

/**
 * Path 3: change a rule. A new threshold creates the NEXT policy version and
 * re-checks the same purchase under it. The version the report was checked
 * against, and the report itself, are left exactly as they were. The outcome
 * is shown in its own section of the stage, under its own heading, so the form
 * and the comparison are never read as one thing.
 */
export function ChangeRuleForm({ job, result, policy, example }: ChangeRuleFormProps) {
  const { state, actions } = useWorkflow();
  const ruleFieldId = useId();
  const thresholdId = useId();
  const noteId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const rules = activeRules(policy);
  const [ruleId, setRuleId] = useState(rules[0]?.rule_id ?? "");
  const [text, setText] = useState("");
  const [note, setNote] = useState("");
  const [attempted, setAttempted] = useState(false);

  const rule = rules.find((candidate) => candidate.rule_id === ruleId);
  const current = rule ? getRuleThreshold(rule) : null;
  const threshold = percentInputToFraction(text);
  const problem =
    text.trim() !== "" && threshold === null
      ? t("Enter a number such as 10 or 12.5.")
      : (validateThreshold(threshold) ??
        (threshold !== null && current !== null && Math.abs(threshold - current) <= EPS
          ? t("This is the number already confirmed. Enter a different value to change the rule.")
          : null));
  const canSubmit = rule !== undefined && problem === null;
  const shownError = problem !== null && (attempted || text.trim() !== "") ? problem : null;
  const busy = state.challenge.status === "loading";

  const { preview, onDraftChange } = useDraftPreview({
    personaId: state.personaId,
    policy,
    purchase: result.purchase_request,
    // A rule change re-checks the portfolio stored with this report (contracts/api.md section 2a), so the
    // preview is asked for that portfolio, not for whatever customization is applied now.
    customPortfolio: customPortfolioOfReport(job.portfolio, state.portfolio.data?.scenario.portfolio ?? null),
    // The rules in force, with the edited rule standing in as a draft at the new number.
    buildRules: (draft) => (rule ? previewRuleSet(policy.rules, [draftRule(rule, draft)]) : policy.rules),
  });

  const exampleRuleId = example?.type === "CHANGE_RULE" && typeof example.payload.rule_id === "string" ? example.payload.rule_id : null;
  const exampleThreshold = example?.type === "CHANGE_RULE" && typeof example.payload.new_threshold === "number" ? example.payload.new_threshold : null;
  const hasExample = exampleRuleId !== null && exampleThreshold !== null && rules.some((candidate) => candidate.rule_id === exampleRuleId);

  if (rules.length === 0 || !rule) {
    return <p className="text-ink-muted">{t("This policy version has no rule in force to change.")}</p>;
  }

  function fillExample() {
    if (!example || exampleRuleId === null || exampleThreshold === null) return;
    const exampleText = fractionToPercentInput(exampleThreshold);
    setRuleId(exampleRuleId);
    setText(exampleText);
    setNote(typeof example.payload.user_note === "string" ? example.payload.user_note : "");
    setAttempted(false);
    onDraftChange(exampleText);
  }

  async function submit() {
    if (!canSubmit || threshold === null) {
      setAttempted(true);
      inputRef.current?.focus();
      return;
    }
    const response = await actions.submitChallenge(job.id, {
      type: "CHANGE_RULE",
      payload: { rule_id: ruleId, new_threshold: threshold, user_note: note.trim() === "" ? null : note.trim() },
    });
    if (response) {
      setText("");
      setNote("");
      setAttempted(false);
      preview.clear();
    }
  }

  return (
    <div className="space-y-5" data-testid="change-rule-form">
      <h3 className="text-lg font-semibold text-ink">{t("Change a rule")}</h3>
      <p className="max-w-prose text-ink">
        {t("A rule is yours to change. Changing it does not edit the past: it creates the next policy version, checks the same purchase again under it, and keeps the report made under version")}<span className="tabular">{policy.version}</span>.
      </p>

      {hasExample && example ? (
        <p>
          <Button size="sm" onClick={fillExample} data-testid="fill-example-rule">
            {t("Fill in the scenario&apos;s example:")} {example.label}
          </Button>
        </p>
      ) : null}

      <Field htmlFor={ruleFieldId} label={t("Rule to change")} hint={tf("The rules in force in policy version {version}.", { version: policy.version })}>
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
              {tf("{rule}: now {threshold}", { rule: ruleTypeLabel(candidate.rule_type), threshold: thresholdText(candidate) })}
            </option>
          ))}
        </Select>
      </Field>

      <p className="text-ink" data-testid="current-threshold">
        {t("Confirmed now:")} <span className="tabular text-lg font-bold">{thresholdText(rule)}</span>{" "}
        <span className="text-ink-muted">
          ({ruleParametersText(rule)} {t("· policy version")} {policy.version})
        </span>
      </p>

      <ThresholdInput
        id={thresholdId}
        inputRef={inputRef}
        label={tf("New value: {label}", { label: thresholdLabel(rule.rule_type).toLowerCase() })}
        hint={thresholdHint(rule.rule_type)}
        value={text}
        error={shownError}
        onChange={(next) => {
          setText(next);
          onDraftChange(next);
        }}
      />

      <DraftPreviewPanel preview={preview} ruleId={rule.rule_id} ruleType={rule.rule_type} purchase={result.purchase_request} />

      <Field htmlFor={noteId} label={t("Note for the record (optional)")} hint={t("Kept with the change, word for word.")}>
        <TextInput id={noteId} value={note} onChange={(event) => setNote(event.target.value)} autoComplete="off" aria-describedby={describedBy(noteId, { hint: true })} />
      </Field>

      <Notice tone="info" title={t("What confirming this change does")}>
        <ul className="list-disc space-y-1 pl-5">
          <li>
            {t("Creates the next policy version with the new number. Version")} <span className="tabular">{policy.version}</span> {t("is kept, unchanged.")}</li>
          <li>{t("Runs a new investigation of the same purchase under the new version.")}</li>
          <li>{t("Shows both results in a separate section below this form. The earlier report stays openable.")}</li>
        </ul>
      </Notice>

      <Button variant="primary" softDisabled={!canSubmit} busy={busy} busyLabel={t("Creating the new version…")} onClick={() => void submit()} data-testid="submit-rule-change">
        {t("Confirm the change and check again under a new version")}</Button>
    </div>
  );
}
