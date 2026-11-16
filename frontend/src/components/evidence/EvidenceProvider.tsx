"use client";

import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from "react";
import { Drawer } from "@/components/ui/Drawer";
import { EvidenceIcon } from "@/components/ui/icons";
import type { CheckResult } from "@/lib/contracts";
import { cn } from "@/lib/cn";
import { EvidenceContent } from "./EvidenceContent";
import { t } from "@/lib/i18n";

export interface EvidenceRequest {
  /** What the figure is, in words: "NVDA exposure after the purchase". */
  title: string;
  /** The report the figure belongs to. Evidence is always read from that report, never from a newer one. */
  result: CheckResult;
  evidenceIds: string[];
}

interface EvidenceContextValue {
  open: (request: EvidenceRequest, opener: HTMLElement | null) => void;
  close: () => void;
  /** An evidence record the user chose to challenge from the drawer. */
  challengeEvidenceId: string | null;
  setChallengeEvidenceId: (evidenceId: string | null) => void;
}

const EvidenceContext = createContext<EvidenceContextValue | null>(null);

/**
 * One evidence drawer for the whole app. Any figure can open it; closing it
 * returns focus to the control that opened it.
 */
export function EvidenceProvider({ children }: { children: ReactNode }) {
  const [request, setRequest] = useState<EvidenceRequest | null>(null);
  const [isOpen, setIsOpen] = useState(false);
  const [challengeEvidenceId, setChallengeEvidenceId] = useState<string | null>(null);
  const opener = useRef<HTMLElement | null>(null);

  const open = useCallback((next: EvidenceRequest, element: HTMLElement | null) => {
    opener.current = element;
    setRequest(next);
    setIsOpen(true);
  }, []);

  const close = useCallback(() => setIsOpen(false), []);

  const value = useMemo(
    () => ({ open, close, challengeEvidenceId, setChallengeEvidenceId }),
    [open, close, challengeEvidenceId],
  );

  return (
    <EvidenceContext.Provider value={value}>
      {children}
      <Drawer
        open={isOpen}
        onOpenChange={setIsOpen}
        title={request ? `Evidence: ${request.title}` : "Evidence"}
        description={t("Where this figure comes from: dates, sources, coverage, assumptions and how it was calculated.")}
        closeLabel="Close evidence"
        returnFocusTo={() => opener.current}
      >
        {request ? (
          <EvidenceContent
            request={request}
            onChallenge={(evidenceId) => {
              // Going to another stage: focus moves to that stage's heading, not back to the opener.
              opener.current = null;
              setChallengeEvidenceId(evidenceId);
              setIsOpen(false);
            }}
          />
        ) : null}
      </Drawer>
    </EvidenceContext.Provider>
  );
}

export function useEvidence(): EvidenceContextValue {
  const value = useContext(EvidenceContext);
  if (!value) throw new Error("useEvidence must be used inside <EvidenceProvider>");
  return value;
}

export interface EvidenceButtonProps {
  /** Completes the accessible name: "Evidence for {label}". */
  label: string;
  result: CheckResult;
  evidenceIds: string[];
  className?: string;
}

/**
 * The control next to a figure that opens its evidence. Visible text
 * "Evidence"; accessible name "Evidence for …" so a list of them is
 * distinguishable out of context.
 */
export function EvidenceButton({ label, result, evidenceIds, className }: EvidenceButtonProps) {
  const { open } = useEvidence();
  if (evidenceIds.length === 0) {
    return <span className={cn("text-sm text-ink-muted", className)}>{t("No evidence record")}</span>;
  }
  return (
    <button
      type="button"
      aria-label={`Evidence for ${label}`}
      onClick={(event) => open({ title: label, result, evidenceIds }, event.currentTarget)}
      className={cn(
        "inline-flex min-h-9 items-center gap-1.5 rounded-md px-1.5 text-sm font-semibold text-accent underline decoration-1 underline-offset-4 hover:text-accent-strong hover:decoration-2",
        className,
      )}
    >
      <EvidenceIcon size={16} />
      <span>{t("Evidence")}</span>
    </button>
  );
}
