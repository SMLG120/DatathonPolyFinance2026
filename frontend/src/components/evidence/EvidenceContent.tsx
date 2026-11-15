"use client";

import { LinkButton } from "@/components/ui/Button";
import { UnknownBlock } from "@/components/ui/AsyncStates";
import { Badge } from "@/components/ui/Badge";
import { UnknownIcon } from "@/components/ui/icons";
import { Fact, Facts } from "@/components/ui/Panel";
import type { EvidenceRecord, ProposedCorrection, SourceRecord } from "@/lib/contracts";
import { formatDate, formatDateTime, formatFraction, UNKNOWN_TEXT } from "@/lib/format";
import { findEvidence, findSource } from "@/lib/verdict";
import { stageHref } from "@/state/stage";
import { useWorkflow } from "@/state/workflow";
import type { EvidenceRequest } from "./EvidenceProvider";

/** The value of an evidence record in its own unit. Fractions get two decimals so they can be recomputed. */
export function formatEvidenceValue(record: Pick<EvidenceRecord, "value" | "unit">): string {
  if (record.value === null || !Number.isFinite(record.value)) return UNKNOWN_TEXT;
  if (record.unit === "fraction") return formatFraction(record.value, { decimals: 2 });
  if (record.unit === "days") return `${record.value} ${record.value === 1 ? "day" : "days"}`;
  return String(record.value);
}

function periodText(record: EvidenceRecord): string {
  if (record.period_start && record.period_end) return `${formatDate(record.period_start)} to ${formatDate(record.period_end)}`;
  if (record.period_end) return `As of ${formatDate(record.period_end)}`;
  if (record.period_start) return `From ${formatDate(record.period_start)}`;
  return "No date recorded";
}

function SourceCard({ source }: { source: SourceRecord }) {
  return (
    <li className="rounded-md border border-line bg-canvas p-3">
      <p className="font-semibold text-ink">{source.title}</p>
      <p className="text-sm text-ink-muted">{source.publisher}</p>
      <dl className="mt-2 grid grid-cols-1 gap-x-4 gap-y-2 text-sm sm:grid-cols-2">
        <div>
          <dt className="font-semibold text-ink-muted">Data date</dt>
          <dd className="tabular">{formatDate(source.relevant_date)}</dd>
        </div>
        <div>
          <dt className="font-semibold text-ink-muted">Retrieved</dt>
          <dd className="tabular">{formatDate(source.retrieval_date)}</dd>
        </div>
        <div className="sm:col-span-2">
          <dt className="font-semibold text-ink-muted">Processing</dt>
          <dd>{source.processing}</dd>
        </div>
        <div className="sm:col-span-2">
          <dt className="font-semibold text-ink-muted">Terms of use</dt>
          <dd>{source.terms}</dd>
        </div>
        <div className="sm:col-span-2">
          <dt className="font-semibold text-ink-muted">Known limitations</dt>
          <dd>
            {source.known_limitations.length > 0 ? (
              <ul className="list-disc space-y-1 pl-5">
                {source.known_limitations.map((limitation) => (
                  <li key={limitation}>{limitation}</li>
                ))}
              </ul>
            ) : (
              "None recorded"
            )}
          </dd>
        </div>
        <div className="sm:col-span-2">
          <dt className="font-semibold text-ink-muted">File hash (SHA-256)</dt>
          <dd className="break-all font-mono text-[0.8125rem]">{source.sha256 ?? "Not recorded"}</dd>
        </div>
        {source.url ? (
          <div className="sm:col-span-2">
            <dt className="font-semibold text-ink-muted">Address</dt>
            <dd className="break-all">
              <a href={source.url} target="_blank" rel="noreferrer noopener" className="text-accent underline underline-offset-4">
                {source.url}
                <span className="sr-only"> (opens in a new tab)</span>
              </a>
            </dd>
          </div>
        ) : null}
      </dl>
    </li>
  );
}

function CorrectionNote({ correction }: { correction: ProposedCorrection }) {
  return (
    <li className="rounded-md border border-dashed border-unknown bg-unknown-soft p-3" data-testid="proposed-correction">
      <Badge tone="unknown" dashed icon={<UnknownIcon size={16} />}>
        Proposed correction — unverified
      </Badge>
      <dl className="mt-2 space-y-2 text-sm">
        <div>
          <dt className="font-semibold text-ink-muted">Value you proposed</dt>
          <dd className="text-ink">{correction.proposed_value_text}</dd>
        </div>
        <div>
          <dt className="font-semibold text-ink-muted">Your reason</dt>
          <dd className="text-ink">{correction.reason_text}</dd>
        </div>
        <div>
          <dt className="font-semibold text-ink-muted">Provenance</dt>
          <dd className="text-ink">Asserted by you on {formatDateTime(correction.provenance.asserted_at)}. Not verified by any source.</dd>
        </div>
      </dl>
      <p className="mt-2 text-sm font-semibold text-ink">Not used in any calculation. The recorded value above is unchanged.</p>
    </li>
  );
}

function EvidenceCard({ record, request, onChallenge }: { record: EvidenceRecord; request: EvidenceRequest; onChallenge: (evidenceId: string) => void }) {
  const { state } = useWorkflow();
  const corrections = state.corrections.filter((correction) => correction.evidence_id === record.evidence_id);
  const sources = record.source_ids.map((sourceId) => ({ sourceId, source: findSource(request.result, sourceId) }));

  return (
    <section aria-labelledby={`evidence-${record.evidence_id}`} className="space-y-4 border-b border-line pb-6 last:border-b-0" data-testid="evidence-record">
      <div>
        <h3 id={`evidence-${record.evidence_id}`} className="text-lg font-semibold text-ink">
          {record.label}
        </h3>
        <p className="tabular mt-1 text-2xl font-bold text-ink" data-testid="evidence-value">
          {formatEvidenceValue(record)}
        </p>
        <p className="text-sm text-ink-muted">Recorded value. A fraction of the whole portfolio unless stated otherwise.</p>
      </div>

      <Facts>
        <Fact label="Subject">{record.subject}</Fact>
        <Fact label="Period">
          <span className="tabular">{periodText(record)}</span>
        </Fact>
        <Fact label="Data coverage">
          {record.coverage === null ? "Not applicable to this figure" : <span className="tabular">{formatFraction(record.coverage)} of the underlying data</span>}
        </Fact>
        <Fact label="Policy version">{record.policy_version === null ? "None — not tied to a confirmed policy" : `Version ${record.policy_version}`}</Fact>
        <Fact label="Calculation version">
          <span className="break-all font-mono text-sm">{record.calculation_version}</span>
        </Fact>
        <Fact label="Metric">
          <span className="break-all font-mono text-sm">{record.metric_id}</span>
        </Fact>
      </Facts>

      <div>
        <h4 className="font-semibold text-ink">Calculation path</h4>
        {record.calculation_path.length > 0 ? (
          <ol className="mt-1 list-decimal space-y-1 pl-5 text-ink">
            {record.calculation_path.map((step) => (
              <li key={step} className="tabular break-words">
                {step}
              </li>
            ))}
          </ol>
        ) : (
          <p className="mt-1 text-ink-muted">No calculation: this value is read directly from its source.</p>
        )}
      </div>

      <div>
        <h4 className="font-semibold text-ink">Assumptions</h4>
        {record.assumptions.length > 0 ? (
          <ul className="mt-1 list-disc space-y-1 pl-5 text-ink">
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
        {sources.length > 0 ? (
          <ul className="mt-2 space-y-2">
            {sources.map(({ sourceId, source }) =>
              source ? (
                <SourceCard key={sourceId} source={source} />
              ) : (
                <li key={sourceId}>
                  <UnknownBlock title="Source record not found">
                    <p>
                      This report names source <span className="font-mono">{sourceId}</span> but does not contain its record.
                    </p>
                  </UnknownBlock>
                </li>
              ),
            )}
          </ul>
        ) : (
          <UnknownBlock title="No source recorded" className="mt-2">
            <p>This figure names no source. Treat it as unverified.</p>
          </UnknownBlock>
        )}
      </div>

      {corrections.length > 0 ? (
        <div>
          <h4 className="font-semibold text-ink">Your proposed corrections</h4>
          <ul className="mt-2 space-y-2">
            {corrections.map((correction) => (
              <CorrectionNote key={correction.correction_id} correction={correction} />
            ))}
          </ul>
        </div>
      ) : null}

      <LinkButton href={stageHref("challenge")} size="sm" onClick={() => onChallenge(record.evidence_id)}>
        Challenge this figure
      </LinkButton>
    </section>
  );
}

/** The body of the evidence drawer: one card per evidence record behind the figure. */
export function EvidenceContent({ request, onChallenge }: { request: EvidenceRequest; onChallenge: (evidenceId: string) => void }) {
  return (
    <div className="space-y-6">
      {request.result.is_draft_preview ? (
        <UnknownBlock title="Preview with draft threshold — not your confirmed policy">
          <p>These records belong to a preview. They are not part of any stored report.</p>
        </UnknownBlock>
      ) : null}
      {request.evidenceIds.map((evidenceId) => {
        const record = findEvidence(request.result, evidenceId);
        return record ? (
          <EvidenceCard key={evidenceId} record={record} request={request} onChallenge={onChallenge} />
        ) : (
          <UnknownBlock key={evidenceId} title="Evidence record not found">
            <p>
              This figure refers to evidence <span className="font-mono">{evidenceId}</span>, which is not in this report. Treat the figure as
              unverified.
            </p>
          </UnknownBlock>
        );
      })}
    </div>
  );
}
