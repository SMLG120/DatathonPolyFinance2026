"use client";

import { LinkButton } from "@/components/ui/Button";
import { UnknownBlock } from "@/components/ui/AsyncStates";
import { Badge } from "@/components/ui/Badge";
import { UnknownIcon } from "@/components/ui/icons";
import { Fact, Facts } from "@/components/ui/Panel";
import { TestDataTag } from "@/components/ui/TestDataTag";
import type { CheckResult, EvidenceRecord, ProposedCorrection } from "@/lib/contracts";
import {
  derivedRecords,
  evidenceLabelMeaning,
  evidenceLabelText,
  formatEvidenceValue,
  formatValueInUnit,
  metricLabel,
  periodText,
  subjectText,
  unitText,
} from "@/lib/evidence";
import { formatDateTime } from "@/lib/format";
import { findEvidence } from "@/lib/verdict";
import { stageHref } from "@/state/stage";
import { useWorkflow } from "@/state/workflow";
import type { EvidenceRequest } from "./EvidenceProvider";

/**
 * What the drawer says about sources, on test data and on the live service alike. No route of the
 * contract delivers the source registry, so nothing is promised: only the ids are there to show.
 */
export const SOURCE_DETAILS_NOTE =
  "Only the ids of a figure’s sources are available here, as they were recorded with the figure. The source registry is not delivered to this page, so the title, publisher, retrieval date and terms of use of a source are not shown.";

function CorrectionNote({ correction }: { correction: ProposedCorrection }) {
  return (
    <li className="rounded-md border border-dashed border-unknown bg-unknown-soft p-3" data-testid="proposed-correction">
      <Badge tone="unknown" dashed icon={<UnknownIcon size={16} />}>
        Proposed correction: unverified
      </Badge>
      <dl className="mt-2 space-y-2 text-sm">
        <div>
          <dt className="font-semibold text-ink-muted">Value proposed</dt>
          <dd className="tabular text-ink" data-testid="correction-asserted">
            {formatValueInUnit(correction.asserted_value, correction.asserted_unit)}
          </dd>
        </div>
        <div>
          <dt className="font-semibold text-ink-muted">Value on record when it was proposed</dt>
          <dd className="tabular text-ink">{formatValueInUnit(correction.original_value, correction.original_unit)}</dd>
        </div>
        <div>
          <dt className="font-semibold text-ink-muted">Reason given</dt>
          <dd className="whitespace-pre-line text-ink">{correction.provenance.user_note}</dd>
        </div>
        <div>
          <dt className="font-semibold text-ink-muted">Source named by the user</dt>
          <dd className="whitespace-pre-line text-ink">{correction.provenance.user_source ?? "None"}</dd>
        </div>
        <div>
          <dt className="font-semibold text-ink-muted">Provenance</dt>
          <dd className="text-ink">Asserted by the user on {formatDateTime(correction.provenance.asserted_at)}. Not verified against any source.</dd>
        </div>
      </dl>
      <p className="mt-2 text-sm font-semibold text-ink">Not used in any calculation. The recorded value above is unchanged.</p>
    </li>
  );
}

/** One value a calculation was computed from: what it is, whose it is, and the value in its own unit. */
function InputValue({ record }: { record: EvidenceRecord }) {
  return (
    <li className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-0.5 border-b border-line py-1.5 last:border-b-0" data-testid="evidence-input">
      <span className="min-w-0 text-ink">
        {metricLabel(record.metric_id)}
        <span className="block text-sm text-ink-muted">
          {subjectText(record.subject)} · <span className="font-mono text-[0.8125rem]">{record.evidence_id}</span>
        </span>
      </span>
      <span className="tabular font-semibold text-ink">
        {formatEvidenceValue(record)}
        {typeof record.value === "number" && record.unit === "fraction" ? <span className="font-normal text-ink-muted"> (as a fraction: {record.value})</span> : null}
      </span>
    </li>
  );
}

function EvidenceCard({ record, result, corrections, onChallenge }: { record: EvidenceRecord; result: CheckResult; corrections: ProposedCorrection[]; onChallenge: (evidenceId: string) => void }) {
  const inputs = derivedRecords(result, record);
  const hasInputs = inputs.found.length > 0 || inputs.missing.length > 0;
  const headingId = `evidence-${record.evidence_id}`;

  return (
    <section aria-labelledby={headingId} className="space-y-4 border-b border-line pb-6 last:border-b-0" data-testid="evidence-record" data-evidence-id={record.evidence_id} data-figures="true">
      <div>
        <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-1">
          <h3 id={headingId} className="text-lg font-semibold text-ink">
            {metricLabel(record.metric_id)}
          </h3>
          <TestDataTag />
        </div>
        <p className="tabular mt-1 text-2xl font-bold text-ink" data-testid="evidence-value">
          {formatEvidenceValue(record)}
        </p>
        <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-ink-muted">
          <Badge tone="neutral" dashed={record.label !== "FACT" && record.label !== "CALCULATION"}>
            <span data-testid="evidence-label">{evidenceLabelText(record.label)}</span>
          </Badge>
          <span>{evidenceLabelMeaning(record.label)}</span>
        </p>
      </div>

      <Facts>
        <Fact label="Subject">{subjectText(record.subject)}</Fact>
        <Fact label="Date or period">
          <span className="tabular" data-testid="evidence-period">
            {periodText(record.period)}
          </span>
        </Fact>
        <Fact label="Unit">{unitText(record.unit)}</Fact>
        <Fact label="Policy version">{record.policy_version === null ? "None: a preview, not tied to a confirmed policy" : `Version ${record.policy_version}`}</Fact>
        <Fact label="Calculation version">
          <span className="break-all font-mono text-sm">{record.calculation_version}</span>
        </Fact>
        <Fact label="Record">
          <span className="break-all font-mono text-sm">{record.evidence_id}</span>
        </Fact>
      </Facts>

      <div data-testid="evidence-calculation">
        <h4 className="font-semibold text-ink">How it was calculated</h4>
        {record.formula === null && !hasInputs ? (
          <p className="mt-1 text-ink-muted" data-testid="evidence-no-calculation">
            No calculation: this value is taken as recorded.
          </p>
        ) : null}
        {record.formula !== null ? (
          <div className="mt-2">
            <h5 className="text-sm font-semibold text-ink-muted">Formula, as recorded by the engine</h5>
            <p className="tabular mt-1 whitespace-pre-wrap break-words rounded-md border border-line bg-canvas px-3 py-2 font-mono text-[0.9375rem] text-ink" data-testid="evidence-formula">
              {record.formula}
            </p>
          </div>
        ) : null}
        {hasInputs ? (
          <div className="mt-3">
            <h5 className="text-sm font-semibold text-ink-muted">Values it was computed from</h5>
            <ul className="mt-1" data-testid="evidence-inputs">
              {inputs.found.map((input) => (
                <InputValue key={input.evidence_id} record={input} />
              ))}
              {inputs.missing.map((evidenceId) => (
                <li key={evidenceId} className="py-1.5 text-ink" data-testid="evidence-input-missing">
                  Record <span className="font-mono text-[0.8125rem]">{evidenceId}</span> is named as an input but is not in this result.
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </div>

      <div>
        <h4 className="font-semibold text-ink">Assumptions</h4>
        {record.assumptions.length > 0 ? (
          <ul className="mt-1 list-disc space-y-1 pl-5 text-ink" data-testid="evidence-assumptions">
            {record.assumptions.map((assumption) => (
              <li key={assumption}>{assumption}</li>
            ))}
          </ul>
        ) : (
          <p className="mt-1 text-ink-muted">None recorded.</p>
        )}
      </div>

      <div>
        <h4 className="font-semibold text-ink">Sources</h4>
        {record.source_ids.length > 0 ? (
          <ul className="mt-1 flex flex-wrap gap-2" data-testid="evidence-sources">
            {record.source_ids.map((sourceId) => (
              <li key={sourceId} className="break-all rounded-md border border-line bg-canvas px-2 py-0.5 font-mono text-sm text-ink">
                {sourceId}
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-1 text-ink-muted" data-testid="evidence-no-source">
            {record.label === "CALCULATION" ? "None of its own: a calculated value rests on the sources of the values listed above." : "No source id is recorded with this figure."}
          </p>
        )}
      </div>

      {corrections.length > 0 ? (
        <div>
          <h4 className="font-semibold text-ink">Proposed corrections</h4>
          <ul className="mt-2 space-y-2">
            {corrections.map((correction) => (
              <CorrectionNote key={correction.correction_id} correction={correction} />
            ))}
          </ul>
        </div>
      ) : null}

      {result.preview ? null : (
        <LinkButton href={stageHref("challenge")} size="sm" onClick={() => onChallenge(record.evidence_id)}>
          Challenge this figure
        </LinkButton>
      )}
    </section>
  );
}

/** The body of the evidence drawer: one card per evidence record behind the figure. */
export function EvidenceContent({ request, onChallenge }: { request: EvidenceRequest; onChallenge: (evidenceId: string) => void }) {
  const { state, derived } = useWorkflow();
  // Corrections are filed against a job. The job is the one whose result this figure was read from.
  const jobId = state.investigationIds.find((id) => state.investigations[id]?.result === request.result) ?? null;
  const corrections = jobId ? derived.correctionsFor(jobId) : [];

  return (
    <div className="space-y-6">
      {request.result.preview ? (
        <UnknownBlock title="Preview with draft rules: not a confirmed policy">
          <p>These records belong to a preview. They are not part of any stored report.</p>
        </UnknownBlock>
      ) : null}
      <p className="rounded-md border border-line bg-sunken px-3 py-2 text-sm text-ink" data-testid="source-details-note">
        {SOURCE_DETAILS_NOTE}
      </p>
      {request.evidenceIds.map((evidenceId) => {
        const record = findEvidence(request.result, evidenceId);
        return record ? (
          <EvidenceCard
            key={evidenceId}
            record={record}
            result={request.result}
            corrections={corrections.filter((correction) => correction.evidence_id === evidenceId)}
            onChallenge={onChallenge}
          />
        ) : (
          <UnknownBlock key={evidenceId} title="Evidence record not found">
            <p>
              This figure refers to evidence <span className="font-mono">{evidenceId}</span>, which is not in this result. Treat the figure as
              unverified.
            </p>
          </UnknownBlock>
        );
      })}
    </div>
  );
}
