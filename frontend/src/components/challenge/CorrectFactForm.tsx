"use client";

import { useId, useRef, useState, type FormEvent } from "react";
import { EvidenceButton, useEvidence } from "@/components/evidence/EvidenceProvider";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { describedBy, Field, Select, TextArea, TextInput } from "@/components/ui/Field";
import { UnknownIcon } from "@/components/ui/icons";
import { TestDataTag } from "@/components/ui/TestDataTag";
import type { CheckResult, DemoChallenge, EvidenceRecord, EvidenceUnit, InvestigationJob, ProposedCorrection } from "@/lib/contracts";
import { formatEvidenceValue, formatValueInUnit, metricLabel, subjectText } from "@/lib/evidence";
import { formatDateTime, fractionToPercentInput, percentInputToFraction } from "@/lib/format";
import { findEvidence } from "@/lib/verdict";
import { useWorkflow } from "@/state/workflow";
import { t } from "@/lib/i18n";

/** How the asserted value is typed for each unit, and how the text is read. A share is typed as a percentage and stored as a fraction. */
const VALUE_FIELD: Record<EvidenceUnit, { label: string; hint: string; error: string }> = {
  fraction: {
    label: "The value you believe is right, in percent",
    hint: "For example 8 for 8%. It is stored as a share of 1: 8% is stored as 0.08.",
    error: "Enter a percentage such as 8 or 8.5.",
  },
  price: { label: "The price you believe is right", hint: "A number, in the currency of the record.", error: "Enter a number such as 123.45." },
  fx_rate: { label: "The exchange rate you believe is right", hint: "A number, for example 1.3625.", error: "Enter a number such as 1.3625." },
  days: { label: "The number of days you believe is right", hint: "A whole number.", error: "Enter a whole number." },
  count: { label: "The count you believe is right", hint: "A whole number.", error: "Enter a whole number." },
  date: { label: "The date you believe is right", hint: "As year-month-day, for example 2026-11-12.", error: "Enter a date as year-month-day, for example 2026-11-12." },
  text: { label: "The value you believe is right", hint: "In words, as it should be recorded.", error: "Enter the value you believe is right." },
};

/** Reads the typed value in the unit of the record. Null means it cannot be read; it is never read as zero. */
export function readAssertedValue(text: string, unit: EvidenceUnit): number | string | null {
  const trimmed = text.trim();
  if (trimmed === "") return null;
  switch (unit) {
    case "fraction":
      return percentInputToFraction(trimmed);
    case "price":
    case "fx_rate":
      return /^-?\d+(\.\d+)?$/.test(trimmed) ? Number(trimmed) : null;
    case "days":
    case "count":
      return /^\d+$/.test(trimmed) ? Number(trimmed) : null;
    case "date":
      return /^\d{4}-\d{2}-\d{2}$/.test(trimmed) ? trimmed : null;
    case "text":
      return trimmed;
  }
}

function recordName(record: EvidenceRecord): string {
  return `${metricLabel(record.metric_id)} — ${subjectText(record.subject)}`;
}

function CorrectionCard({ correction, result }: { correction: ProposedCorrection; result: CheckResult }) {
  const original = findEvidence(result, correction.evidence_id);
  return (
    <li className="rounded-md border border-dashed border-unknown bg-unknown-soft p-3 sm:p-4" data-testid="correction-card" data-figures="true">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <Badge tone="unknown" dashed icon={<UnknownIcon size={16} />}>
          {t("Proposed correction — unverified")}</Badge>
        <TestDataTag />
      </div>
      <dl className="mt-3 grid gap-x-6 gap-y-3 sm:grid-cols-2">
        <div>
          <dt className="text-sm font-semibold text-ink-muted">{t("Recorded in the report — unchanged")}</dt>
          <dd className="text-ink" data-testid="correction-original">
            {original ? (
              <>
                {recordName(original)}: <span className="tabular font-semibold">{formatEvidenceValue(original)}</span>
              </>
            ) : (
              <>
                {t("Evidence")} <span className="font-mono text-sm">{correction.evidence_id}</span>:{" "}
                <span className="tabular font-semibold">{formatValueInUnit(correction.original_value, correction.original_unit)}</span>
              </>
            )}
          </dd>
          {original ? (
            <dd>
              <EvidenceButton label={`the recorded value of ${recordName(original)}`} result={result} evidenceIds={[original.evidence_id]} />
            </dd>
          ) : null}
        </div>
        <div>
          <dt className="text-sm font-semibold text-ink-muted">{t("Value proposed")}</dt>
          <dd className="tabular font-semibold text-ink" data-testid="correction-proposed">
            {formatValueInUnit(correction.asserted_value, correction.asserted_unit)}
          </dd>
        </div>
        <div className="sm:col-span-2">
          <dt className="text-sm font-semibold text-ink-muted">{t("Reason given")}</dt>
          <dd className="whitespace-pre-line text-ink">{correction.provenance.user_note}</dd>
        </div>
        <div className="sm:col-span-2">
          <dt className="text-sm font-semibold text-ink-muted">{t("Source named")}</dt>
          <dd className="whitespace-pre-line text-ink">{correction.provenance.user_source ?? "None"}</dd>
        </div>
        <div className="sm:col-span-2">
          <dt className="text-sm font-semibold text-ink-muted">{t("Provenance")}</dt>
          <dd className="text-ink">
            {t("Asserted by the user on")} <span className="tabular">{formatDateTime(correction.provenance.asserted_at)}</span>{t(". No source has confirmed it.")}</dd>
        </div>
      </dl>
      <p className="mt-3 text-sm font-semibold text-ink">{t("Not used in any calculation. Every figure of the report is still based on the recorded value.")}</p>
    </li>
  );
}

/**
 * Path 1: correct a fact. The user's value is recorded as a proposed,
 * unverified correction with the user as its source. It never replaces the
 * recorded evidence, and the original stays visible next to it.
 */
export function CorrectFactForm({ job, result, example }: { job: InvestigationJob; result: CheckResult; example: DemoChallenge | null }) {
  const { state, actions, derived } = useWorkflow();
  const { challengeEvidenceId } = useEvidence();
  const evidenceFieldId = useId();
  const valueId = useId();
  const noteId = useId();
  const sourceId = useId();
  const listHeadingRef = useRef<HTMLHeadingElement>(null);

  const preselected = challengeEvidenceId && findEvidence(result, challengeEvidenceId) ? challengeEvidenceId : "";
  const [evidenceId, setEvidenceId] = useState(preselected);
  const [value, setValue] = useState("");
  const [note, setNote] = useState("");
  const [source, setSource] = useState("");
  const [attempted, setAttempted] = useState(false);

  const selected = evidenceId ? findEvidence(result, evidenceId) : undefined;
  const field = VALUE_FIELD[selected?.unit ?? "text"];
  const asserted = selected ? readAssertedValue(value, selected.unit) : null;
  const errors = {
    evidence: selected ? null : "Choose the figure you want to correct.",
    value: asserted === null ? (value.trim() === "" ? "Enter the value you believe is right." : field.error) : null,
    note: note.trim() === "" ? "Say why. It is stored with the correction." : null,
  };
  const show = (message: string | null) => (attempted ? message : null);
  const busy = state.challenge.status === "loading";
  const corrections = derived.correctionsFor(job.id);

  const exampleEvidenceId = example?.type === "CORRECT_FACT" && typeof example.payload.evidence_id === "string" ? example.payload.evidence_id : null;
  const exampleRecord = exampleEvidenceId ? findEvidence(result, exampleEvidenceId) : undefined;

  function fillExample() {
    if (!example || !exampleRecord) return;
    const { asserted_value: exampleValue, user_note: exampleNote, user_source: exampleSource } = example.payload;
    setEvidenceId(exampleRecord.evidence_id);
    setValue(typeof exampleValue === "number" ? (exampleRecord.unit === "fraction" ? fractionToPercentInput(exampleValue) : String(exampleValue)) : typeof exampleValue === "string" ? exampleValue : "");
    setNote(typeof exampleNote === "string" ? exampleNote : "");
    setSource(typeof exampleSource === "string" ? exampleSource : "");
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setAttempted(true);
    if (!selected || asserted === null || errors.note) {
      const firstInvalid = errors.evidence ? evidenceFieldId : errors.value ? valueId : noteId;
      document.getElementById(firstInvalid)?.focus();
      return;
    }
    const response = await actions.submitChallenge(job.id, {
      type: "CORRECT_FACT",
      payload: {
        evidence_id: selected.evidence_id,
        asserted_value: asserted,
        asserted_unit: selected.unit,
        user_note: note.trim(),
        user_source: source.trim() === "" ? null : source.trim(),
      },
    });
    if (response) {
      setValue("");
      setNote("");
      setSource("");
      setAttempted(false);
      listHeadingRef.current?.focus();
    }
  }

  return (
    <div className="space-y-6">
      <h3 className="text-lg font-semibold text-ink">{t("Correct a fact")}</h3>
      <p className="max-w-prose text-ink">
        {t("If a figure looks wrong, say what you believe it should be. Your value is stored as a claim from you. It is not checked against a source, it is not used in any calculation, and the recorded evidence stays as it is.")}</p>

      {exampleRecord && example ? (
        <p>
          <Button size="sm" onClick={fillExample} data-testid="fill-example-fact">
            {t("Fill in the scenario&apos;s example:")} {example.label}
          </Button>
        </p>
      ) : null}

      <form onSubmit={onSubmit} noValidate className="space-y-5" data-testid="correct-fact-form">
        <Field htmlFor={evidenceFieldId} label={t("Which figure?")} hint={t("Every figure of this report, by its evidence record.")} error={show(errors.evidence)}>
          <Select
            id={evidenceFieldId}
            value={evidenceId}
            onChange={(event) => {
              setEvidenceId(event.target.value);
              setValue("");
            }}
            aria-invalid={show(errors.evidence) ? true : undefined}
            aria-describedby={describedBy(evidenceFieldId, { hint: true, error: Boolean(show(errors.evidence)) })}
          >
            <option value="">{t("Choose a figure")}</option>
            {result.evidence.map((record) => (
              <option key={record.evidence_id} value={record.evidence_id}>
                {recordName(record)} — {formatEvidenceValue(record)}
              </option>
            ))}
          </Select>
        </Field>

        {selected ? (
          <div className="rounded-md border border-line bg-canvas p-3 sm:p-4" data-testid="original-evidence" data-figures="true">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <p className="text-sm font-semibold text-ink-muted">{t("Recorded in the report")}</p>
              <TestDataTag />
            </div>
            <p className="text-ink">
              {metricLabel(selected.metric_id)}: <span className="tabular text-lg font-bold">{formatEvidenceValue(selected)}</span>
            </p>
            <p className="text-sm text-ink-muted">{subjectText(selected.subject)}</p>
            <EvidenceButton label={`the recorded value of ${recordName(selected)}`} result={result} evidenceIds={[selected.evidence_id]} />
          </div>
        ) : null}

        <div className="grid gap-5 md:grid-cols-2">
          <Field htmlFor={valueId} label={field.label} hint={field.hint} error={show(errors.value)}>
            <TextInput
              id={valueId}
              value={value}
              onChange={(event) => setValue(event.target.value)}
              autoComplete="off"
              inputMode={selected && selected.unit !== "text" && selected.unit !== "date" ? "decimal" : undefined}
              aria-invalid={show(errors.value) ? true : undefined}
              aria-describedby={describedBy(valueId, { hint: true, error: Boolean(show(errors.value)) })}
            />
          </Field>
          <Field htmlFor={sourceId} label={t("Where your value comes from (optional)")} hint={t("For example a document and its date. It is recorded as named by you, not retrieved.")}>
            <TextInput
              id={sourceId}
              value={source}
              onChange={(event) => setSource(event.target.value)}
              autoComplete="off"
              aria-describedby={describedBy(sourceId, { hint: true })}
            />
          </Field>
        </div>
        <Field htmlFor={noteId} label={t("Why you believe the recorded value is wrong")} hint={t("Stored word for word with the correction.")} error={show(errors.note)}>
          <TextArea
            id={noteId}
            rows={2}
            value={note}
            onChange={(event) => setNote(event.target.value)}
            aria-invalid={show(errors.note) ? true : undefined}
            aria-describedby={describedBy(noteId, { hint: true, error: Boolean(show(errors.note)) })}
          />
        </Field>

        <Button type="submit" variant="primary" busy={busy} busyLabel="Recording…" data-testid="submit-correction">
          {t("Record my correction as unverified")}</Button>
      </form>

      <div>
        <h3 ref={listHeadingRef} tabIndex={-1} className="text-lg font-semibold text-ink">
          {t("Proposed corrections to this report (")}{corrections.length})
        </h3>
        {corrections.length > 0 ? (
          <ul className="mt-3 space-y-3">
            {corrections.map((correction) => (
              <CorrectionCard key={correction.correction_id} correction={correction} result={result} />
            ))}
          </ul>
        ) : (
          <p className="mt-1 text-ink-muted">{t("None yet.")}</p>
        )}
      </div>
    </div>
  );
}
