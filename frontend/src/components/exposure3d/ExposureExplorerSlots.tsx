"use client";

import { useMemo } from "react";
import { useEvidence } from "@/components/evidence/EvidenceProvider";
import { ExposureExplorer } from "@/components/explorer/ExposureExplorer";
import { buildExplorerModel, type ExplorerModel, type ExplorerReady } from "@/components/explorer/model";
import { useIsTestData } from "@/components/ui/TestDataTag";
import { ExposureChart } from "@/components/verdict/ExposureChart";
import type { CheckResult, Exposure } from "@/lib/contracts";
import { t, tf } from "@/lib/i18n";

/**
 * Where the exposure explorer is mounted: one company's exposure before and
 * after the purchase, as a 3D drawing with its values in a table.
 *
 * The explorer is an enhancement. Its drawing needs WebGL, a wide screen, no
 * forced colours and no request for reduced motion, and its code is loaded
 * only when it is about to be shown. Whenever it cannot be drawn, or fails
 * while loading or running, the flat chart of the same company stands in its
 * place and nothing is reported as an error.
 *
 * A slot receives the engine's `CheckResult` and nothing else. Every figure
 * the explorer shows is a field of that result; nothing is computed here.
 */

/** The flat chart of the one company the explorer shows, so that the drawing and its replacement carry the same values. */
function FlatChart({ exposure, model }: { exposure: Exposure; model: ExplorerReady }) {
  const company = exposure.issuers.filter((issuer) => issuer.issuer_id === model.issuerId);
  return (
    <ExposureChart
      exposure={{ ...exposure, issuers: company }}
      limit={model.limit ? model.limit.value : null}
      limitLabel={model.limit?.isDraft ? t("Draft limit") : t("Confirmed limit")}
      caption={tf("{company}: exposure as a share of the portfolio, flat view", { company: model.issuerName })}
    />
  );
}

/** What a calculation record is about, in words, for the title of the evidence drawer. */
function evidenceTitle(model: ExplorerModel, evidenceId: string): string {
  if (model.status !== "READY") return t("the exposure shown");
  const segment = [...model.current.segments, ...model.proposed.segments].find((candidate) => candidate.evidenceId === evidenceId);
  if (!segment) return tf("exposure to {company}", { company: model.issuerName });
  if (segment.fundId) {
    const template = segment.state === "starting" ? "exposure to {company} through {fund}, before the purchase" : "exposure to {company} through {fund}, after the purchase";
    return tf(template, { company: model.issuerName, fund: segment.fundId });
  }
  const template = segment.state === "starting" ? "exposure to {company}, before the purchase" : "exposure to {company}, after the purchase";
  return tf(template, { company: model.issuerName });
}

function Explorer({ result }: { result: CheckResult }) {
  const isTestData = useIsTestData();
  const { open } = useEvidence();
  // One model per result: the drawing is rebuilt only when the result on screen changes.
  const model = useMemo(() => buildExplorerModel(result, { dataOrigin: isTestData ? "FIXTURE" : "LIVE" }), [result, isTestData]);

  return (
    <ExposureExplorer
      model={model}
      fallback={model.status === "READY" && result.exposure ? <FlatChart exposure={result.exposure} model={model} /> : null}
      onOpenEvidence={(evidenceId) =>
        // The evidence is read from the same result the explorer shows; focus returns to the button that asked for it.
        open({ title: evidenceTitle(model, evidenceId), result, evidenceIds: [evidenceId] }, document.activeElement instanceof HTMLElement ? document.activeElement : null)
      }
      headingLevel={3}
    />
  );
}

/** Verdict stage, beside the 2D exposure chart, which stays on screen. `result` is the report on screen; its execution status is OK. */
export interface VerdictExposureExplorerSlotProps {
  result: CheckResult;
}

export function VerdictExposureExplorerSlot({ result }: VerdictExposureExplorerSlotProps) {
  return <Explorer result={result} />;
}

/**
 * Purchase stage, under the preview of the entered purchase. `result` is the
 * service's answer to POST /check for the request in the form, or null while
 * there is none (form incomplete, no confirmed policy, request in flight,
 * request not executable, or no recorded answer in fixtures mode). With no
 * result there is nothing to show, and nothing is rendered.
 */
export interface PurchaseExposureExplorerSlotProps {
  result: CheckResult | null;
}

export function PurchaseExposureExplorerSlot({ result }: PurchaseExposureExplorerSlotProps) {
  if (result === null) return null;
  return <Explorer result={result} />;
}
