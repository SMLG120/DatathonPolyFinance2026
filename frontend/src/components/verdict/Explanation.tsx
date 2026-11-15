"use client";

import { EvidenceButton } from "@/components/evidence/EvidenceProvider";
import { Badge } from "@/components/ui/Badge";
import type { CheckResult, ExplanationStatement, RenderedBy } from "@/lib/contracts";

const RENDERED_BY: Record<RenderedBy, { label: string; meaning: string }> = {
  TEMPLATE: { label: "Template sentence", meaning: "Built by the service from the figures of the result." },
  MODEL_VALIDATED: {
    label: "Written by the model",
    meaning: "Worded by a model. The service checked every figure in it against the evidence before showing it.",
  },
};

/**
 * The result in sentences.
 *
 * Every sentence is shown as plain text: it is placed in the page as a text
 * node, so markup, links or scripts inside a sentence are displayed as the
 * characters they are and never interpreted. This matters most for the
 * sentences a model wrote. Nothing here decides or restates a verdict.
 */
export function ExplanationList({ result, statements }: { result: CheckResult; statements: ExplanationStatement[] }) {
  return (
    <ul className="space-y-4" data-testid="explanation">
      {statements.map((statement) => {
        const origin = RENDERED_BY[statement.rendered_by];
        return (
          <li
            key={statement.statement_id}
            className="space-y-1 border-b border-line pb-4 last:border-b-0 last:pb-0"
            data-testid="explanation-statement"
            data-rendered-by={statement.rendered_by}
          >
            <p className="whitespace-pre-line text-ink" data-testid="explanation-text">
              {statement.text}
            </p>
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
              <Badge tone="neutral" dashed={statement.rendered_by === "MODEL_VALIDATED"}>
                {origin.label}
              </Badge>
              <span className="text-sm text-ink-muted">{origin.meaning}</span>
            </div>
            {statement.evidence_ids.length > 0 ? <EvidenceButton label="this sentence" result={result} evidenceIds={statement.evidence_ids} /> : null}
          </li>
        );
      })}
    </ul>
  );
}
