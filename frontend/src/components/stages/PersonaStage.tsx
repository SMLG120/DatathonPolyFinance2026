"use client";

import { PortfolioTable } from "@/components/portfolio/PortfolioTable";
import { StageFrame } from "@/components/shell/StageFrame";
import { ErrorBlock, LoadingBlock } from "@/components/ui/AsyncStates";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { CheckIcon, PersonIcon } from "@/components/ui/icons";
import { Notice } from "@/components/ui/Notice";
import { Fact, Facts, Panel } from "@/components/ui/Panel";
import { PERSONAS, personaName, type PersonaCard } from "@/content/personas";
import { cn } from "@/lib/cn";
import type { Persona } from "@/lib/contracts";
import { formatDate, formatFraction } from "@/lib/format";
import { useWorkflow } from "@/state/workflow";
import { t } from "@/lib/i18n";

function PersonaOption({ persona, selected, onSelect }: { persona: PersonaCard; selected: boolean; onSelect: () => void }) {
  const headingId = `persona-${persona.persona_id}`;
  return (
    <li
      className={cn(
        "flex flex-col gap-4 rounded-xl border p-5 transition-shadow",
        !persona.available && "border-dashed border-line-strong bg-canvas",
        persona.available && selected && "border-accent bg-surface ring-1 ring-accent shadow-sm",
        persona.available && !selected && "border-line bg-surface hover:shadow-sm",
      )}
      data-testid={`persona-${persona.persona_id}`}
    >
      <div className="space-y-2">
        <h3 id={headingId} className="flex items-center gap-2 text-lg font-semibold text-ink">
          <PersonIcon className="flex-none text-ink-muted" />
          {persona.name}
        </h3>

      </div>
      <p className="text-ink-muted">{persona.objective}</p>
      <details className="text-sm"><summary className="cursor-pointer font-medium text-ink-muted">{t("Full profile")}</summary>
      {/* Each group is a direct child of the list: a <dl> may hold <div> groups, but not groups nested in a layout wrapper. */}
      <dl className="flex flex-wrap gap-x-6 gap-y-2 text-sm">
        <div className="basis-full">
          <dt className="font-semibold text-ink-muted">{t("Objective in the case")}</dt>
          <dd className="text-ink">{persona.objective}</dd>
        </div>
        <div>
          <dt className="font-semibold text-ink-muted">{t("Horizon")}</dt>
          <dd className="text-ink">{persona.horizon}</dd>
        </div>
        <div>
          <dt className="font-semibold text-ink-muted">{t("Risk profile")}</dt>
          <dd className="text-ink">{persona.risk_profile}</dd>
        </div>
        <div className="basis-full">
          <dt className="font-semibold text-ink-muted">{t("What it demonstrates")}</dt>
          <dd className="text-ink">{persona.demonstrates}</dd>
        </div>
      </dl>
      </details>
      <div className="mt-auto pt-1">
        {persona.available ? (
          selected ? (
            <p className="flex min-h-11 items-center gap-2 font-semibold text-accent-strong" data-testid="persona-selected">
              <CheckIcon />
              {t("Selected")}</p>
          ) : (
            <Button onClick={onSelect} aria-describedby={headingId}>
              {t("Use")} {persona.name}{t("&rsquo;s portfolio")}</Button>
          )
        ) : (
          <p className="text-sm text-ink-muted">{t("Not available in this build. It is added once the two demonstrations above work end to end.")}</p>
        )}
      </div>
    </li>
  );
}

/** The persona as the service describes it: facts quoted from the case, each with its page reference. */
function CaseFacts({ persona }: { persona: Persona }) {
  return (
    <details className="rounded-md border border-line bg-canvas p-3" data-testid="case-facts">
      <summary className="min-h-6 cursor-pointer font-semibold text-ink">
        {t("What the case says about")} {persona.display_name} ({persona.case_reference})
      </summary>
      <dl className="mt-3 grid gap-3 sm:grid-cols-2">
        {persona.facts.map((fact) => (
          <div key={fact.fact_id}>
            <dt className="text-sm font-semibold text-ink-muted">{fact.label}</dt>
            <dd className="text-ink">
              {fact.text} <span className="text-sm text-ink-muted">({fact.case_reference})</span>
            </dd>
          </div>
        ))}
        <div className="sm:col-span-2">
          <dt className="text-sm font-semibold text-ink-muted">{t("What this persona tests")}</dt>
          <dd className="text-ink">
            {persona.what_this_persona_tests.text} <span className="text-sm text-ink-muted">({persona.what_this_persona_tests.case_reference})</span>
          </dd>
        </div>
      </dl>
    </details>
  );
}

/** Stage 1: choose a persona and read its fictional portfolio. */
export function PersonaStage() {
  const { state, actions } = useWorkflow();
  const { portfolio, personaId } = state;
  const hasWork = state.policies.length > 0 || state.investigationIds.length > 0;
  const scenario = portfolio.data?.scenario ?? null;

  return (
    <StageFrame
      stage="persona"
      lead={t("Pick a fictional investor to try a portfolio decision.")}
    >
      <Panel title={t("Who would you like to try?")}>
        <ul className="grid gap-4 md:grid-cols-2">
          {PERSONAS.filter((persona) => persona.available).map((persona) => (
            <PersonaOption
              key={persona.persona_id}
              persona={persona}
              selected={persona.persona_id === personaId}
              onSelect={() => actions.selectPersona(persona.persona_id)}
            />
          ))}
        </ul>
        {hasWork ? (
          <p className="mt-4 text-sm text-ink-muted">
            {t("Choosing another persona starts a new session: the rules and reports of the current one are cleared from this page.")}</p>
        ) : null}
      </Panel>

      <Panel
        title={t("View the fictional portfolio")}
        collapsible={portfolio.status === "ready"}
        eyebrow="Fictional simulation"
        figures
        aside={
          <Badge tone="neutral" dashed>
            {t("Invented holdings")}</Badge>
        }
      >
        {portfolio.status === "idle" ? <LoadingBlock label={t("Preparing the portfolio…")} /> : null}
        {portfolio.status === "loading" ? <LoadingBlock label={`Loading ${personaName(personaId)}’s portfolio…`} /> : null}
        {portfolio.status === "error" ? (
          <ErrorBlock title={t("The portfolio could not be loaded")} message={portfolio.error ?? "The request failed."} onRetry={actions.retryPortfolio}>
            <p>{t("Nothing was changed. No figure is shown rather than a guessed one.")}</p>
          </ErrorBlock>
        ) : null}
        {portfolio.status === "ready" && portfolio.data && scenario ? (
          <div className="space-y-5">
            <Notice tone="info" title={t("These holdings are invented")}>
              <p data-testid="fiction-notice">{scenario.fiction_notice}</p>
            </Notice>
            <Facts className="sm:grid-cols-3">
              <Fact label={t("Valuation date")}>
                <span className="tabular">{formatDate(scenario.portfolio.valuation_date)}</span>
              </Fact>
              <Fact label={t("Reporting currency")}>{scenario.portfolio.base_currency}</Fact>
              <Fact label={t("Cash")}>
                <span className="tabular">{formatFraction(scenario.portfolio.cash_weight)}</span> {t("of the portfolio")}</Fact>
            </Facts>
            <PortfolioTable portfolio={scenario.portfolio} instruments={portfolio.data.instruments} personaName={scenario.persona.display_name} />
            <CaseFacts persona={scenario.persona} />
          </div>
        ) : null}
      </Panel>
    </StageFrame>
  );
}
