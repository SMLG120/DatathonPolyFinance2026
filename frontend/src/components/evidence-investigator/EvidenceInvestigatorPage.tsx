"use client";

import { useId, useState, useSyncExternalStore } from "react";
import { AccessCodeForm } from "@/components/shell/AccessCodeForm";
import { FIXTURES_LABEL, SIMULATION_LABEL } from "@/components/shell/AppShell";
import { LinkButton } from "@/components/ui/Button";
import { Field, Select } from "@/components/ui/Field";
import { DEFAULT_PERSONA, PERSONAS } from "@/content/personas";
import { t, tf, useLocale } from "@/lib/i18n";
import { RuntimeProvider, useRuntime } from "@/state/runtime";
import { EvidenceInvestigatorChat, TITLE } from "./EvidenceInvestigatorChat";

const subscribeToNothing = () => () => {};

function Content() {
  // Reads the stored language choice of the main page and re-renders this page when it changes.
  const [locale] = useLocale();
  void locale;
  const { needsAccessCode, config } = useRuntime();
  const personaSelectId = useId();
  const [personaId, setPersonaId] = useState<string>(DEFAULT_PERSONA);
  return (
    <div className="mx-auto w-full max-w-4xl space-y-5 px-4 py-6 sm:px-6">
      <title>{tf("{title}: ETHOS (fictional simulation)", { title: t(TITLE) })}</title>
      <p className="rounded-md bg-sunken px-3 py-2 text-sm font-semibold text-ink">
        {t(SIMULATION_LABEL)}
        {config.mode === "fixtures" ? ` · ${t(FIXTURES_LABEL)}` : ""}
      </p>
      <LinkButton href={`../${config.mode === "fixtures" && config.fixturesReason === "requested" ? "?fixtures=1" : ""}`} variant="quiet" size="sm">
        {t("Back to the purchase check")}
      </LinkButton>
      {needsAccessCode ? (
        <AccessCodeForm />
      ) : (
        <main id="main-content" className="space-y-5">
          <Field htmlFor={personaSelectId} label={t("Fictional investor")}>
            <Select id={personaSelectId} value={personaId} onChange={(event) => setPersonaId(event.target.value)}>
              {PERSONAS.filter((persona) => persona.available).map((persona) => (
                <option key={persona.persona_id} value={persona.persona_id}>
                  {persona.name}
                </option>
              ))}
            </Select>
          </Field>
          <EvidenceInvestigatorChat key={personaId} personaId={personaId} />
        </main>
      )}
    </div>
  );
}

/** The standalone `/evidence/` page: the investigator on its own, with the app's runtime and access-code gate. */
export function EvidenceInvestigatorPage() {
  const inBrowser = useSyncExternalStore(subscribeToNothing, () => true, () => false);
  if (!inBrowser) return null;
  return (
    <RuntimeProvider>
      <Content />
    </RuntimeProvider>
  );
}
