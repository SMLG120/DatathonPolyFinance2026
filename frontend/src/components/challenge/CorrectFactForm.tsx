"use client";

import { useId, useRef, useState, type FormEvent } from "react";
import { formatEvidenceValue } from "@/components/evidence/EvidenceContent";
import { EvidenceButton, useEvidence } from "@/components/evidence/EvidenceProvider";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { describedBy, Field, Select, TextArea, TextInput } from "@/components/ui/Field";
import { UnknownIcon } from "@/components/ui/icons";
import type { CheckResult, Investigation, ProposedCorrection } from "@/lib/contracts";
import { formatDateTime } from "@/lib/format";
import { findEvidence } from "@/lib/verdict";
import { useWorkflow } from "@/state/workflow";

function CorrectionCard({ correction, result }: { correction: ProposedCorrection; result: CheckResult }) {
  const original = findEvidence(result, correction.evidence_id);
  return (
    <li className="rounded-md border border-dashed border-unknown bg-unknown-soft p-3 sm:p-4" data-testid="correction-card">
      <Badge tone="unknown" dashed icon={<UnknownIcon size={16} />}>
        Proposed correction — unverified
      </Badge>
      <dl className="mt-3 grid gap-x-6 gap-y-3 sm:grid-cols-2">
        <div>
          <dt className="text-sm font-semibold text-ink-muted">Recorded in the report — unchanged</dt>
          <dd className="text-ink" data-testid="correction-original">
            {original ? (
              <>
                {original.label}: <span className="tabular font-semibold">{formatEvidenceValue(original)}</span>
              </>
            ) : (
              <>
                Evidence <span className="font-mono text-sm">{correction.evidence_id}</span> (from another report)
              </>
            )}
          </dd>
          {original ? (
            <dd>
              <EvidenceButton label={`the recorded value of ${original.label}`} result={result} evidenceIds={[original.evidence_id]} />
            </dd>
          ) : null}
        </div>
        <div>
          <dt className="text-sm font-semibold text-ink-muted">Value you proposed</dt>
          <dd className="font-semibold text-ink" data-testid="correction-proposed">
            {correction.proposed_value_text}
          </dd>
        </div>
        <div className="sm:col-span-2">
          <dt className="text-sm font-semibold text-ink-muted">Your reason</dt>
          <dd className="text-ink">{correction.reason_text}</dd>
        </div>
        <div className="sm:col-span-2">
          <dt className="text-sm font-semibold text-ink-muted">Provenance</dt>
          <dd className="text-ink">
            Asserted by you on <span className="tabular">{formatDateTime(correction.provenance.asserted_at)}</span>. No source has confirmed it.
          </dd>
        </div>
      </dl>
      <p className="mt-3 text-sm font-semibold text-ink">Not used in any calculation. Every figure of the report is still based on the recorded value.</p>
    </li>
  );
}

/**
 * Path 1: correct a fact. The user's value is recorded as a proposed,
 * unverified correction with the user as its source. It never replaces the
 * recorded evidence, and the original stays visible next to it.
 */
export function CorrectFactForm({ investigation, result }: { investigation: Investigation; result: CheckResult }) {
  const { state, actions } = useWorkflow();
  const { challengeEvidenceId } = useEvidence();
  const evidenceFieldId = useId();
  const valueId = useId();
  const reasonId = useId();
  const listHeadingRef = useRef<HTMLHeadingElement>(null);

  const preselected = challengeEvidenceId && findEvidence(result, challengeEvidenceId) ? challengeEvidenceId : "";
  const [evidenceId, setEvidenceId] = useState(preselected);
  const [value, setValue] = useState("");
  const [reason, setReason] = useState("");
  const [attempted, setAttempted] = useState(false);

  const selected = evidenceId ? findEvidence(result, evidenceId) : undefined;
  const errors = {
    evidence: evidenceId === "" ? "Choose the figure you want to correct." : null,
    value: value.trim() === "" ? "Enter the value you believe is right." : null,
    reason: reason.trim() === "" ? "Say why, or where your value comes from. It is stored with the correction." : null,
  };
  const show = (message: string | null) => (attempted ? message : null);
  const busy = state.challenge.status === "loading";

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setAttempted(true);
    if (errors.evidence || errors.value || errors.reason) {
      const firstInvalid = errors.evidence ? evidenceFieldId : errors.value ? valueId : reasonId;
      document.getElementById(firstInvalid)?.focus();
      return;
    }
    const response = await actions.submitChallenge(investigation.investigation_id, {
      kind: "CORRECT_FACT",
      evidence_id: evidenceId,
      proposed_value_text: value.trim(),
      reason_text: reason.trim(),
    });
    if (response) {
      setValue("");
      setReason("");
      setAttempted(false);
      listHeadingRef.current?.focus();
    }
  }

  return (
    <div className="space-y-6">
      <p className="max-w-prose text-ink">
        If a figure looks wrong, say what you believe it should be. Your value is stored as a claim from you. It is not checked against a source, it
        is not used in any calculation, and the recorded evidence stays as it is.
      </p>

      <form onSubmit={onSubmit} noValidate className="space-y-5" data-testid="correct-fact-form">
        <Field htmlFor={evidenceFieldId} label="Which figure?" hint="Every figure of this report, by its evidence record." error={show(errors.evidence)}>
          <Select
            id={evidenceFieldId}
            value={evidenceId}
            onChange={(event) => setEvidenceId(event.target.value)}
            aria-invalid={show(errors.evidence) ? true : undefined}
            aria-describedby={describedBy(evidenceFieldId, { hint: true, error: Boolean(show(errors.evidence)) })}
          >
            <option value="">Choose a figure</option>
            {result.evidence.map((record) => (
              <option key={record.evidence_id} value={record.evidence_id}>
                {record.label} — {formatEvidenceValue(record)}
              </option>
            ))}
          </Select>
        </Field>

        {selected ? (
          <div className="rounded-md border border-line bg-canvas p-3 sm:p-4" data-testid="original-evidence">
            <p className="text-sm font-semibold text-ink-muted">Recorded in the report</p>
            <p className="text-ink">
              {selected.label}: <span className="tabular text-lg font-bold">{formatEvidenceValue(selected)}</span>
            </p>
            <p className="text-sm text-ink-muted">{selected.subject}</p>
            <EvidenceButton label={`the recorded value of ${selected.label}`} result={result} evidenceIds={[selected.evidence_id]} />
          </div>
        ) : null}

        <div className="grid gap-5 md:grid-cols-2">
          <Field htmlFor={valueId} label="The value you believe is right" hint="Write it as you would say it, for example 8.1%." error={show(errors.value)}>
            <TextInput
              id={valueId}
              value={value}
              onChange={(event) => setValue(event.target.value)}
              autoComplete="off"
              aria-invalid={show(errors.value) ? true : undefined}
              aria-describedby={describedBy(valueId, { hint: true, error: Boolean(show(errors.value)) })}
            />
          </Field>
          <Field htmlFor={reasonId} label="Why, or where it comes from" hint="For example a document and its date." error={show(errors.reason)}>
            <TextArea
              id={reasonId}
              rows={2}
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              aria-invalid={show(errors.reason) ? true : undefined}
              aria-describedby={describedBy(reasonId, { hint: true, error: Boolean(show(errors.reason)) })}
            />
          </Field>
        </div>

        <Button type="submit" variant="primary" busy={busy} busyLabel="Recording…" data-testid="submit-correction">
          Record my correction as unverified
        </Button>
      </form>

      <div>
        <h3 ref={listHeadingRef} tabIndex={-1} className="text-lg font-semibold text-ink">
          Your proposed corrections ({state.corrections.length})
        </h3>
        {state.corrections.length > 0 ? (
          <ul className="mt-3 space-y-3">
            {state.corrections.map((correction) => (
              <CorrectionCard key={correction.correction_id} correction={correction} result={result} />
            ))}
          </ul>
        ) : (
          <p className="mt-1 text-ink-muted">None yet.</p>
        )}
      </div>
    </div>
  );
}
