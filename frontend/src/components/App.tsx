"use client";

import { useEffect, useRef, useSyncExternalStore } from "react";
import { EvidenceProvider } from "@/components/evidence/EvidenceProvider";
import { AccessCodeForm } from "@/components/shell/AccessCodeForm";
import { AppShell, SIMULATION_LABEL } from "@/components/shell/AppShell";
import { ChallengeStage } from "@/components/stages/ChallengeStage";
import { GoalsStage } from "@/components/stages/GoalsStage";
import { InvestigationStage } from "@/components/stages/InvestigationStage";
import { PersonaStage } from "@/components/stages/PersonaStage";
import { PurchaseStage } from "@/components/stages/PurchaseStage";
import { VerdictStage } from "@/components/stages/VerdictStage";
import { AnnouncerProvider } from "@/components/ui/Announcer";
import { DEFAULT_PERSONA } from "@/content/personas";
import { t, useLocale } from "@/lib/i18n";
import { RuntimeProvider, useRuntime } from "@/state/runtime";
import { SCREEN_TITLES, useStage, type StageId } from "@/state/stage";
import { useWorkflow, WorkflowProvider } from "@/state/workflow";

const APP_NAME = "ETHOS: fictional simulation";

const subscribeToNothing = () => () => {};

/** False while the page is the static HTML from the build, true once it runs in a browser. */
function useIsBrowser(): boolean {
  return useSyncExternalStore(
    subscribeToNothing,
    () => true,
    () => false,
  );
}

function StageView({ stage }: { stage: StageId }) {
  switch (stage) {
    case "persona":
      return <PersonaStage />;
    case "goals":
      return <GoalsStage />;
    case "purchase":
      return <PurchaseStage />;
    case "investigation":
      return <InvestigationStage />;
    case "verdict":
      return <VerdictStage />;
    case "challenge":
      return <ChallengeStage />;
  }
}

/**
 * The document title. It is rendered as an element, which React places in
 * <head>, and it is the only <title> the page has: the layout sets none.
 * Assigning `document.title` instead does not hold, because the framework
 * writes its own title element again when it finishes hydrating the page.
 */
function PageTitle({ children }: { children: string }) {
  return <title>{children}</title>;
}

/** Shows the current stage with its page title; on a stage change moves focus to the new heading. */
function StageRouter() {
  const [locale] = useLocale();
  void locale;
  const stage = useStage();
  const { state, actions } = useWorkflow();
  const shownStage = useRef(stage);

  useEffect(() => {
    if (shownStage.current === stage) return;
    shownStage.current = stage;
    // A stage change is a page change: start at the top, with focus on the
    // heading so assistive technology announces where the user now is.
    window.scrollTo(0, 0);
    document.querySelector<HTMLElement>("[data-stage-heading]")?.focus({ preventScroll: true });
  }, [stage]);

  // The primary demonstration is loaded on arrival, so the first screen is never empty.
  const hasPersona = state.personaId !== null;
  const selectPersona = actions.selectPersona;
  useEffect(() => {
    if (!hasPersona) selectPersona(DEFAULT_PERSONA);
  }, [hasPersona, selectPersona]);

  return (
    <>
      <PageTitle>{`${SCREEN_TITLES[stage]}: ${APP_NAME}`}</PageTitle>
      <StageView stage={stage} />
    </>
  );
}

function Gate() {
  const { needsAccessCode } = useRuntime();
  return (
    <AppShell>
      {needsAccessCode ? (
        <>
          <PageTitle>{`Access code: ${APP_NAME}`}</PageTitle>
          <AccessCodeForm />
        </>
      ) : (
        <StageRouter />
      )}
    </AppShell>
  );
}

/** Everything below the runtime: announcer, workflow state, evidence drawer and the shell. Tests render this with an injected runtime. */
export function AppContent() {
  // Subscribe here so locale changes refresh every stage without resetting the
  // in-memory workflow or its form state.
  const [locale] = useLocale();
  void locale;
  return (
    <AnnouncerProvider>
      <WorkflowProvider>
        <EvidenceProvider>
          <Gate />
        </EvidenceProvider>
      </WorkflowProvider>
    </AnnouncerProvider>
  );
}

/**
 * The whole application. It is one static page: the stage lives in the URL
 * hash, so moving between stages never reloads the page and never loses the
 * workflow state held in memory.
 */
export function App() {
  const isBrowser = useIsBrowser();

  if (!isBrowser) {
    // The prerendered HTML: the notice is already there before any script runs.
    return (
      <div className="flex min-h-screen flex-col">
        <PageTitle>{APP_NAME}</PageTitle>
        <div className="bg-banner px-4 py-2 text-sm font-semibold text-on-banner sm:px-6">{t(SIMULATION_LABEL)}</div>
        <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-8 sm:px-6">
          <h1 className="text-3xl font-bold tracking-tight text-ink">ETHOS</h1>
          <p className="mt-2 text-lg text-ink-muted" role="status">
            {t("Loading the simulation…")}
          </p>
        </main>
      </div>
    );
  }

  return (
    <RuntimeProvider>
      <AppContent />
    </RuntimeProvider>
  );
}
