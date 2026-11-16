"use client";

import { EvidenceButton } from "@/components/evidence/EvidenceProvider";
import { Badge } from "@/components/ui/Badge";
import type { CheckResult, ExplanationStatement } from "@/lib/contracts";
import { t } from "@/lib/i18n";

interface Origin {
  label: string;
  meaning: string;
}

const TEMPLATE_ORIGIN: Origin = { label: "Template sentence", meaning: "Built by the service from the figures of the result." };
const OTHER_ORIGIN: Origin = { label: "Sentence from the service", meaning: "Shown as plain text, exactly as the service sent it." };

/**
 * What is said under a sentence about where its words come from.
 *
 * The service writes every sentence itself and marks it `TEMPLATE`; where a model picked what to
 * point out, the service still wrote the sentence from the evidence record. It returns no sentence
 * written by a model, so nothing on this page says that one was. The contract's other marker is not
 * relied on: a sentence carrying it (only recorded test data does), or a marker this page does not
 * know, gets the neutral wording, which claims nothing about who worded it.
 */
export function originOf(renderedBy: string): Origin {
  return renderedBy === "TEMPLATE" ? TEMPLATE_ORIGIN : OTHER_ORIGIN;
}

/**
 * The result in sentences.
 *
 * Every sentence is shown as plain text: it is placed in the page as a text
 * node, so markup, links or scripts inside a sentence are displayed as the
 * characters they are and never interpreted, whatever produced the sentence.
 * Nothing here decides or restates a verdict.
 */
export function ExplanationList({ result, statements }: { result: CheckResult; statements: ExplanationStatement[] }) {
  return (
    <ul className="space-y-4" data-testid="explanation">
      {statements.map((statement) => {
        const origin = originOf(statement.rendered_by);
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
              <Badge tone="neutral">{origin.label}</Badge>
              <span className="text-sm text-ink-muted">{origin.meaning}</span>
            </div>
            {statement.evidence_ids.length > 0 ? <EvidenceButton label={t("this sentence")} result={result} evidenceIds={statement.evidence_ids} /> : null}
          </li>
        );
      })}
    </ul>
  );
}
