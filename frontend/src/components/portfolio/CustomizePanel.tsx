"use client";

import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { Button } from "@/components/ui/Button";
import { describedBy, errorId, Field, Select, TextArea } from "@/components/ui/Field";
import { ErrorIcon } from "@/components/ui/icons";
import { Notice } from "@/components/ui/Notice";
import { Panel } from "@/components/ui/Panel";
import { cn } from "@/lib/cn";
import type { InstrumentId, Objective, Policy, Portfolio, PortfolioResponse } from "@/lib/contracts";
import {
  CUSTOMIZED_LABEL,
  fractionToWeightText,
  hundredthsToText,
  MAX_CUSTOM_POSITIONS,
  MAX_OBJECTIVE_LENGTH,
  readCustomizeForm,
  type CustomizeFormInput,
  type CustomizeRow,
} from "@/lib/customize";
import { assetClassLabel, instrumentName } from "@/lib/portfolio";
import { useRuntime } from "@/state/runtime";
import { useWorkflow } from "@/state/workflow";

const WEIGHT_INPUT =
  "tabular min-h-11 w-28 rounded-md border border-line-strong bg-surface px-3 text-right text-lg font-semibold text-ink aria-invalid:border-2 aria-invalid:border-fail";

function FieldError({ id, children }: { id: string; children: string }) {
  return (
    <p id={id} className="flex items-start gap-1.5 text-sm font-semibold text-fail">
      <ErrorIcon size={16} className="mt-0.5 flex-none" />
      <span>{children}</span>
    </p>
  );
}

/**
 * Says when the wording shown for the scenario objective is not the wording the policy in force was
 * confirmed with. A stored policy version is immutable, and the only request that stores objectives is the
 * confirmation of a rule: so the wording is stored when, and only when, another rule is confirmed. A rule
 * changed by challenging a result copies the stored objectives (contracts/api.md section 8).
 */
export function ObjectivePendingNote({ policy, objective }: { policy: Policy | null; objective: Objective | undefined }) {
  if (!policy || !objective) return null;
  const stored = policy.objectives.find((candidate) => candidate.objective_id === objective.objective_id);
  if (!stored || stored.original_words === objective.original_words) return null;
  return (
    <Notice tone="info" title="This wording is not in your stored policy">
      <p data-testid="objective-pending-note">
        Policy version <span className="tabular">{policy.version}</span> is stored exactly as it was confirmed and keeps the wording it had then, so reports
        made under it show that earlier wording. The new wording is stored only if you confirm another rule, which creates a new policy version. Changing
        the number of a rule from a result keeps the stored wording. No rule was created, changed or confirmed by editing the objective.
      </p>
    </Notice>
  );
}

/** The form as it opens: the weights of the portfolio every check starts from now, and the objective as it is worded now. */
function openingDraft(starting: Portfolio, objective: Objective | undefined): CustomizeFormInput {
  return {
    rows: starting.positions.map((position) => ({ instrumentId: position.instrument_id, text: fractionToWeightText(position.weight) })),
    cashText: fractionToWeightText(starting.cash_weight),
    objectiveText: objective?.original_words ?? null,
  };
}

interface EditorProps {
  data: PortfolioResponse;
  /** The currency the cash is held in. */
  baseCurrency: string;
  /**
   * The text of the form. It is held by the session, not by this component, so that it is still there
   * when the user comes back to this stage without having chosen Apply or Cancel.
   */
  draft: CustomizeFormInput;
  onDraft: (draft: CustomizeFormInput) => void;
  customized: boolean;
  onApply: (portfolio: NonNullable<ReturnType<typeof readCustomizeForm>["portfolio"]>, objectiveWords: string | null) => void;
  onCancel: () => void;
  onReset: () => void;
}

/**
 * The form of a customization. It holds text only: nothing is applied, shown elsewhere or sent until
 * Apply, and Apply needs every weight to be readable and the weights to total exactly 100%.
 */
function CustomizeEditor({ data, baseCurrency, draft, onDraft, customized, onApply, onCancel, onReset }: EditorProps) {
  const baseId = useId();
  const headingId = `${baseId}-title`;
  const cashId = `${baseId}-cash`;
  const addId = `${baseId}-add`;
  const objectiveId = `${baseId}-objective`;
  const totalId = `${baseId}-total`;
  const weightId = (instrumentId: InstrumentId) => `${baseId}-w-${instrumentId}`;

  const { rows, cashText, objectiveText } = draft;
  const setRows = (change: (current: CustomizeRow[]) => CustomizeRow[]) => onDraft({ ...draft, rows: change(rows) });
  const setCashText = (text: string) => onDraft({ ...draft, cashText: text });
  const setObjectiveText = (text: string) => onDraft({ ...draft, objectiveText: text });
  const [toAdd, setToAdd] = useState("");
  const [attempted, setAttempted] = useState(false);

  // Focus follows what the user just did: the new row after adding, the "add" list after removing.
  const pendingFocus = useRef<string | null>(null);
  useEffect(() => {
    if (pendingFocus.current === null) return;
    document.getElementById(pendingFocus.current)?.focus();
    pendingFocus.current = null;
  });

  const purchasable = data.purchasable_instrument_ids;
  const held = new Set(rows.map((row) => row.instrumentId));
  // Only supported assets that are not already listed can be added: no unsupported asset, no duplicate row.
  const addable = purchasable.filter((id) => !held.has(id));
  const full = rows.length >= MAX_CUSTOM_POSITIONS;
  const reading = readCustomizeForm({ rows, cashText, objectiveText }, purchasable);

  const rowError = (row: CustomizeRow): string | null => (row.text.trim() === "" && !attempted ? null : (reading.rowErrors[row.instrumentId] ?? null));
  const cashError = cashText.trim() === "" && !attempted ? null : reading.cashError;
  const problems = [
    ...rows.flatMap((row) => (reading.rowErrors[row.instrumentId] ? [`${row.instrumentId}: ${reading.rowErrors[row.instrumentId]}`] : [])),
    ...(reading.cashError ? [`Cash: ${reading.cashError}`] : []),
    ...(reading.listError ? [reading.listError] : []),
    ...(reading.totalError ? [reading.totalError] : []),
    ...(reading.objectiveError ? [`Objective: ${reading.objectiveError}`] : []),
  ];

  function add() {
    if (toAdd === "" || !addable.includes(toAdd) || full) return;
    setRows((current) => (current.some((row) => row.instrumentId === toAdd) ? current : [...current, { instrumentId: toAdd, text: "" }]));
    pendingFocus.current = weightId(toAdd);
    setToAdd("");
  }

  function remove(instrumentId: InstrumentId) {
    setRows((current) => current.filter((row) => row.instrumentId !== instrumentId));
    pendingFocus.current = addId;
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!reading.valid || !reading.portfolio) {
      // Refuse and explain: the first field that is wrong takes focus, and the list of problems is announced.
      setAttempted(true);
      const firstRow = rows.find((row) => reading.rowErrors[row.instrumentId]);
      const target = firstRow ? weightId(firstRow.instrumentId) : reading.cashError || reading.totalError ? cashId : reading.objectiveError ? objectiveId : null;
      // The fields are already on the page, so focus moves now (a second refusal changes no state and would not render again).
      if (target !== null) document.getElementById(target)?.focus();
      return;
    }
    onApply(reading.portfolio, objectiveText);
  }

  return (
    <form noValidate onSubmit={submit} aria-labelledby={headingId} className="space-y-6 rounded-lg border border-dashed border-line-strong bg-canvas p-4 sm:p-5" data-testid="customize-editor">
      <div className="space-y-1">
        <h3 id={headingId} className="text-lg font-semibold text-ink">
          Edit the fictional portfolio and the objective
        </h3>
        <p className="text-sm text-ink-muted">
          Enter each weight as a percentage of the whole portfolio, with at most 2 decimals. Nothing is applied until you choose Apply, and no rule is
          created, changed or confirmed here.
        </p>
      </div>

      <fieldset className="space-y-3">
        <legend className="font-semibold text-ink">Positions</legend>
        {rows.length === 0 ? <p className="text-sm text-ink-muted">No position: the whole portfolio is cash.</p> : null}
        <ul className="space-y-3">
          {rows.map((row) => {
            const id = weightId(row.instrumentId);
            const error = rowError(row);
            return (
              <li key={row.instrumentId} className="space-y-1.5 border-b border-line pb-3" data-testid="customize-row" data-instrument-id={row.instrumentId}>
                <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
                  <label htmlFor={id} className="min-w-0 flex-1 basis-48">
                    <span className="block font-semibold text-ink">{instrumentName(data.instruments, row.instrumentId)}</span>
                    <span className="tabular block text-sm text-ink-muted">{row.instrumentId}</span>
                  </label>
                  <div className="flex items-center gap-2">
                    <input
                      id={id}
                      type="text"
                      inputMode="decimal"
                      autoComplete="off"
                      value={row.text}
                      onChange={(event) => setRows((current) => current.map((candidate) => (candidate.instrumentId === row.instrumentId ? { ...candidate, text: event.target.value } : candidate)))}
                      aria-invalid={error ? true : undefined}
                      aria-describedby={describedBy(id, { error: Boolean(error) })}
                      className={WEIGHT_INPUT}
                      data-testid={`customize-weight-${row.instrumentId}`}
                    />
                    <span className="text-lg font-semibold text-ink" aria-hidden="true">
                      %
                    </span>
                    <Button size="sm" variant="quiet" onClick={() => remove(row.instrumentId)} aria-label={`Remove ${row.instrumentId} from the portfolio`} data-testid={`customize-remove-${row.instrumentId}`}>
                      Remove
                    </Button>
                  </div>
                </div>
                {error ? <FieldError id={errorId(id)}>{error}</FieldError> : null}
              </li>
            );
          })}
        </ul>

        <div className="flex flex-wrap items-end gap-3">
          <Field
            htmlFor={addId}
            label="Add an asset"
            hint={
              full
                ? `A portfolio can hold at most ${MAX_CUSTOM_POSITIONS} positions.`
                : addable.length === 0
                  ? "Every supported asset is already in the portfolio."
                  : "Only supported assets that are not already held are listed."
            }
            className="min-w-0 flex-1 basis-64"
          >
            <Select id={addId} value={toAdd} onChange={(event) => setToAdd(event.target.value)} aria-describedby={describedBy(addId, { hint: true })} data-testid="customize-add-select">
              <option value="">Choose an asset</option>
              {full
                ? null
                : addable.map((id) => {
                    const instrument = data.instruments[id];
                    return (
                      <option key={id} value={id}>
                        {id}: {instrumentName(data.instruments, id)}
                        {instrument ? ` (${assetClassLabel(instrument.asset_class)})` : ""}
                      </option>
                    );
                  })}
            </Select>
          </Field>
          <Button softDisabled={toAdd === "" || full} onClick={add} data-testid="customize-add">
            Add this asset
          </Button>
        </div>
      </fieldset>

      <div className="space-y-1.5">
        <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
          <label htmlFor={cashId} className="min-w-0 flex-1 basis-48">
            <span className="block font-semibold text-ink">Cash ({baseCurrency})</span>
            <span className="block text-sm text-ink-muted">Uninvested. A purchase is funded from it.</span>
          </label>
          <div className="flex items-center gap-2">
            <input
              id={cashId}
              type="text"
              inputMode="decimal"
              autoComplete="off"
              value={cashText}
              onChange={(event) => setCashText(event.target.value)}
              aria-invalid={cashError || (attempted && reading.totalError) ? true : undefined}
              aria-describedby={[cashError ? errorId(cashId) : null, totalId].filter(Boolean).join(" ")}
              className={WEIGHT_INPUT}
              data-testid="customize-cash"
            />
            <span className="text-lg font-semibold text-ink" aria-hidden="true">
              %
            </span>
          </div>
        </div>
        {cashError ? <FieldError id={errorId(cashId)}>{cashError}</FieldError> : null}
      </div>

      <p
        id={totalId}
        role="status"
        aria-live="polite"
        className={cn("rounded-md border px-3 py-2 text-ink", reading.totalHundredths === null || reading.totalError ? "border-fail bg-fail-soft" : "border-line bg-surface")}
        data-testid="customize-total"
        data-total-valid={reading.totalHundredths !== null && !reading.totalError ? "true" : "false"}
      >
        <span className="font-semibold">
          Total:{" "}
          {reading.totalHundredths === null ? "not available until every weight is a valid number" : <span className="tabular">{hundredthsToText(reading.totalHundredths)}%</span>}
        </span>
        {reading.totalError ? <span className="block text-sm font-semibold text-fail">{reading.totalError}</span> : null}
        {reading.totalHundredths !== null && !reading.totalError ? <span className="block text-sm text-ink-muted">The weights you entered total exactly 100%.</span> : null}
      </p>

      {objectiveText !== null ? (
        <Field
          htmlFor={objectiveId}
          label="Objective, in plain language"
          hint={`Kept word for word as context for the results. It is never scored, and it never creates or changes a rule. At most ${MAX_OBJECTIVE_LENGTH} characters.`}
          error={reading.objectiveError}
        >
          <TextArea
            id={objectiveId}
            rows={3}
            value={objectiveText}
            onChange={(event) => setObjectiveText(event.target.value)}
            aria-invalid={reading.objectiveError ? true : undefined}
            aria-describedby={describedBy(objectiveId, { hint: true, error: Boolean(reading.objectiveError) })}
            data-testid="customize-objective"
          />
        </Field>
      ) : null}

      {problems.length > 0 ? (
        <div role={attempted ? "alert" : undefined} className="rounded-md border-l-4 border-fail bg-fail-soft px-4 py-3 text-ink" data-testid="customize-error">
          <p className="font-semibold">This customization cannot be applied yet</p>
          <ul className="mt-1 list-disc space-y-1 pl-5 text-[0.9375rem]">
            {problems.map((problem) => (
              <li key={problem}>{problem}</li>
            ))}
          </ul>
        </div>
      ) : null}

      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" variant="primary" softDisabled={!reading.valid} data-testid="customize-apply">
          Apply
        </Button>
        <Button onClick={onCancel} data-testid="customize-cancel">
          Cancel
        </Button>
        <Button variant="quiet" softDisabled={!customized} onClick={() => (customized ? onReset() : undefined)} data-testid="customize-reset">
          Reset to the original scenario
        </Button>
      </div>
      <p className="text-sm text-ink-muted">
        The service checks the portfolio again with every request and is the authority: it refuses a portfolio it cannot accept, and says why.
      </p>
    </form>
  );
}

/**
 * Stage 1, optional: "Customize this profile". Applies an edited fictional portfolio and the user's
 * wording of the objective to the session. It sends nothing: the applied weights travel with the next
 * checks. Confirmed policies and reports are kept as they are.
 */
export function CustomizePanel() {
  const { state, actions, derived } = useWorkflow();
  const { api } = useRuntime();
  const openRef = useRef<HTMLButtonElement>(null);
  const hintId = useId();
  const [returnFocus, setReturnFocus] = useState(0);
  useEffect(() => {
    if (returnFocus > 0) openRef.current?.focus();
  }, [returnFocus]);

  const data = state.portfolio.data;
  const starting = derived.effectivePortfolio;
  if (state.portfolio.status !== "ready" || !data || !starting) return null;

  const scenarioObjective = data.scenario.objectives[0];
  const objective = scenarioObjective ? state.objectives.find((candidate) => candidate.objective_id === scenarioObjective.objective_id) : undefined;
  const customized = derived.customPortfolio !== null || state.objectiveEdited;
  // The test data only replays recorded answers for the original portfolio; it cannot calculate another one.
  const unavailable = api.mode === "fixtures";
  const hasWork = state.policies.length > 0 || state.investigationIds.length > 0;

  // Open while the session holds the text of the form. Leaving this stage keeps it; Apply, Cancel, Reset and
  // choosing another persona end it.
  const draft = state.customizeDraft;

  function close() {
    actions.setCustomizeDraft(null);
    setReturnFocus((count) => count + 1);
  }

  return (
    <Panel
      title="Customize this profile"
      eyebrow="Optional"
      description={`Change the invented weights of ${data.scenario.persona.display_name}’s fictional portfolio and the wording of the objective, then test ideas against your version. It stays a fictional simulation.`}
    >
      <div className="space-y-4">
        {customized ? (
          <Notice tone="info" role="status" title={derived.customPortfolio ? `${CUSTOMIZED_LABEL}: applied` : "Objective edited: the portfolio is the original one"}>
            <ul className="list-disc space-y-1 pl-5" data-testid="customize-summary">
              {derived.customPortfolio ? <li>The portfolio above shows the weights you entered. Every check from now on is asked for exactly these weights.</li> : null}
              {state.objectiveEdited ? <li data-testid="objective-edited-summary">The objective carries your wording. Your limits are unchanged: no rule was created, changed or confirmed.</li> : null}
              {hasWork ? <li>Confirmed limits and earlier reports are kept. Each report keeps the portfolio it was checked against.</li> : null}
            </ul>
          </Notice>
        ) : null}
        {state.objectiveEdited ? <ObjectivePendingNote policy={derived.currentPolicy} objective={objective} /> : null}

        {draft ? (
          <CustomizeEditor
            data={data}
            baseCurrency={starting.base_currency}
            draft={draft}
            onDraft={actions.setCustomizeDraft}
            customized={customized}
            onApply={(portfolio, words) => {
              actions.applyCustomization(portfolio, words);
              close();
            }}
            onCancel={close}
            onReset={() => {
              actions.resetCustomization();
              close();
            }}
          />
        ) : (
          <div className="space-y-2">
            <div className="flex flex-wrap items-center gap-3">
              {/* Unavailable in fixtures mode, but still reachable by keyboard, so the reason below is read out. */}
              <Button
                ref={openRef}
                softDisabled={unavailable}
                aria-describedby={unavailable ? hintId : undefined}
                onClick={() => (unavailable ? undefined : actions.setCustomizeDraft(openingDraft(starting, objective)))}
                data-testid="customize-open"
              >
                Customize this profile
              </Button>
              {customized ? (
                <Button variant="quiet" onClick={actions.resetCustomization} data-testid="customize-reset">
                  Reset to the original scenario
                </Button>
              ) : null}
            </div>
            {unavailable ? (
              <p id={hintId} className="text-sm text-ink-muted" data-testid="customize-unavailable">
                Customization needs the live service: the test data only replays results recorded for the original portfolio.
              </p>
            ) : null}
          </div>
        )}
      </div>
    </Panel>
  );
}
