"use client";

// Temporary review route for the exposure explorer; remove or replace at integration.
//
// It renders `ExposureExplorer` for a few CONTRACT FIXTURES so the component can be
// measured and screenshotted in a real production build. Everything on this page is
// test data. It calls no service.
import { useState } from "react";
import type { CheckResult } from "@/components/explorer/contract-types";
import { ExposureExplorer } from "@/components/explorer/ExposureExplorer";
import { buildExplorerModel } from "@/components/explorer/model";
import invalidRequest from "@/generated/contracts/fixtures/api/check_invalid_request.json";
import robertPreview from "@/generated/contracts/fixtures/api/check_robert_preview.json";
import robertAfterChallenge from "@/generated/contracts/fixtures/api/investigation_robert_after_challenge_succeeded.json";
import robertSucceeded from "@/generated/contracts/fixtures/api/investigation_robert_succeeded.json";

// The fixtures are JSON, so their literal types are wider than the contract unions; the contract's own tests validate them.
const CASES = [
  { id: "robert", label: "Robert: purchase checked against policy version 1", result: robertSucceeded.response_body.result as unknown as CheckResult },
  { id: "after-challenge", label: "Robert: after the rule change", result: robertAfterChallenge.response_body.result as unknown as CheckResult },
  { id: "preview", label: "Robert: draft preview", result: robertPreview.response_body as unknown as CheckResult },
  { id: "unavailable", label: "Invalid request: no exposure returned", result: invalidRequest.response_body as unknown as CheckResult },
] as const;

type CaseId = (typeof CASES)[number]["id"];

const MODELS = Object.fromEntries(CASES.map((item) => [item.id, buildExplorerModel(item.result, { dataOrigin: "FIXTURE" })])) as Record<
  CaseId,
  ReturnType<typeof buildExplorerModel>
>;

export default function ExplorerPreviewPage() {
  const [caseId, setCaseId] = useState<CaseId>("robert");
  const [opened, setOpened] = useState<string | null>(null);

  return (
    <main className="mx-auto max-w-5xl space-y-6 p-4 sm:p-6">
      <header className="space-y-2">
        <p className="inline-block rounded-md border border-dashed border-unknown bg-unknown-soft px-2 py-0.5 text-sm font-semibold text-unknown">
          Temporary review page — test data only
        </p>
        <h1 className="text-2xl font-bold text-ink">Exposure explorer preview</h1>
        <p className="text-ink-muted">
          Fictional simulation, not advice. Every figure below comes from a recorded contract fixture; none is a live result.
        </p>
      </header>

      <fieldset className="space-y-2">
        <legend className="font-semibold text-ink">Fixture</legend>
        <div className="flex flex-wrap gap-2">
          {CASES.map((item) => (
            <button
              key={item.id}
              type="button"
              aria-pressed={item.id === caseId}
              onClick={() => {
                setCaseId(item.id);
                setOpened(null);
              }}
              className={
                item.id === caseId
                  ? "min-h-11 rounded-md border-2 border-accent bg-accent-soft px-3 py-1.5 font-semibold text-ink"
                  : "min-h-11 rounded-md border border-line-strong bg-surface px-3 py-1.5 text-ink hover:bg-accent-soft"
              }
              data-testid="preview-case"
              data-case={item.id}
            >
              {item.label}
            </button>
          ))}
        </div>
      </fieldset>

      <div className="rounded-lg border border-line bg-surface p-4 sm:p-6">
        <ExposureExplorer
          model={MODELS[caseId]}
          headingLevel={2}
          onOpenEvidence={setOpened}
          fallback={
            <p className="rounded-md border border-dashed border-line-strong bg-sunken p-3 text-ink" data-testid="preview-fallback">
              Fallback slot. In the application the existing 2D exposure chart is passed here. The table next to this box carries every value.
            </p>
          }
        />
      </div>

      <p role="status" className="text-ink" data-testid="preview-opened">
        {opened ? (
          <>
            Evidence record requested: <span className="font-mono">{opened}</span> (the application opens its evidence drawer here).
          </>
        ) : (
          "No evidence record requested yet."
        )}
      </p>
    </main>
  );
}
