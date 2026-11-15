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
import { formatDate, formatFraction } from "@/lib/format";
import { useWorkflow } from "@/state/workflow";

function PersonaOption({ persona, selected, onSelect }: { persona: PersonaCard; selected: boolean; onSelect: () => void }) {
  const headingId = `persona-${persona.persona_id}`;
  return (
    <li
      className={cn(
        "flex flex-col gap-3 rounded-lg border p-4",
        !persona.available && "border-dashed border-line-strong bg-canvas",
        persona.available && selected && "border-accent bg-accent-soft outline outline-2 -outline-offset-2 outline-accent",
        persona.available && !selected && "border-line bg-surface",
      )}
      data-testid={`persona-${persona.persona_id}`}
    >
      <div className="space-y-2">
        <h3 id={headingId} className="flex items-center gap-2 text-lg font-semibold text-ink">
          <PersonIcon className="flex-none text-ink-muted" />
          {persona.name}
        </h3>
        <Badge tone={persona.available ? "neutral" : "unknown"} dashed={!persona.available}>
          {persona.role_label}
        </Badge>
      </div>
      <p className="text-sm text-ink-muted">
        <span className="tabular">{persona.age}</span> years old · {persona.occupation}
      </p>
      {/* Each group is a direct child of the list: a <dl> may hold <div> groups, but not groups nested in a layout wrapper. */}
      <dl className="flex flex-wrap gap-x-6 gap-y-2 text-sm">
        <div className="basis-full">
          <dt className="font-semibold text-ink-muted">Objective in the case</dt>
          <dd className="text-ink">{persona.objective}</dd>
        </div>
        <div>
          <dt className="font-semibold text-ink-muted">Horizon</dt>
          <dd className="text-ink">{persona.horizon}</dd>
        </div>
        <div>
          <dt className="font-semibold text-ink-muted">Risk profile</dt>
          <dd className="text-ink">{persona.risk_profile}</dd>
        </div>
        <div className="basis-full">
          <dt className="font-semibold text-ink-muted">What it demonstrates</dt>
          <dd className="text-ink">{persona.demonstrates}</dd>
        </div>
      </dl>
      <div className="mt-auto pt-1">
        {persona.available ? (
          selected ? (
            <p className="flex min-h-11 items-center gap-2 font-semibold text-accent-strong" data-testid="persona-selected">
              <CheckIcon />
              Selected
            </p>
          ) : (
            <Button onClick={onSelect} aria-describedby={headingId}>
              Use {persona.name}&rsquo;s portfolio
            </Button>
          )
        ) : (
          <p className="text-sm text-ink-muted">Not available in this build. It is added once the two demonstrations above work end to end.</p>
        )}
      </div>
    </li>
  );
}

/** Stage 1: choose a persona and read its fictional portfolio. */
export function PersonaStage() {
  const { state, actions } = useWorkflow();
  const { portfolio, personaId } = state;
  const hasWork = state.policies.length > 0 || state.proposedRules.length > 0;

  return (
    <StageFrame
      stage="persona"
      lead="Choose whose fictional situation to explore. Each persona comes from the competition case; the portfolio is invented for this simulation."
    >
      <Panel title="Persona" description="The personas, their objectives and their risk profiles are the ones described in the case.">
        <ul className="grid gap-4 md:grid-cols-3">
          {PERSONAS.map((persona) => (
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
            Choosing another persona starts a new session: the rules and reports of the current one are cleared from this page.
          </p>
        ) : null}
      </Panel>

      <Panel
        title="Portfolio"
        eyebrow="Fictional simulation"
        aside={
          <Badge tone="neutral" dashed>
            Invented holdings
          </Badge>
        }
      >
        {portfolio.status === "idle" ? <LoadingBlock label="Preparing the portfolio…" /> : null}
        {portfolio.status === "loading" ? <LoadingBlock label={`Loading ${personaName(personaId)}’s portfolio…`} /> : null}
        {portfolio.status === "error" ? (
          <ErrorBlock title="The portfolio could not be loaded" message={portfolio.error ?? "The request failed."} onRetry={actions.retryPortfolio}>
            <p>Nothing was changed. No figure is shown rather than a guessed one.</p>
          </ErrorBlock>
        ) : null}
        {portfolio.status === "ready" && portfolio.data ? (
          <div className="space-y-5">
            <Notice tone="info" title="These holdings are invented">
              <p>
                The case gives its personas no portfolio. The weights below are a fictional scenario written for this simulation, so that a
                purchase can be checked against rules. They are not a recommendation and not a model portfolio.
              </p>
            </Notice>
            <Facts className="sm:grid-cols-3">
              <Fact label="Valuation date">
                <span className="tabular">{formatDate(portfolio.data.portfolio.valuation_date)}</span>
              </Fact>
              <Fact label="Reporting currency">{portfolio.data.portfolio.reporting_currency}</Fact>
              <Fact label="Cash">
                <span className="tabular">{formatFraction(portfolio.data.portfolio.cash_weight)}</span> of the portfolio
              </Fact>
            </Facts>
            <PortfolioTable portfolio={portfolio.data.portfolio} personaName={personaName(personaId)} />
          </div>
        ) : null}
      </Panel>
    </StageFrame>
  );
}
