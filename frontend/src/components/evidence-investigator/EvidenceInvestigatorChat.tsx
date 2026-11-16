"use client";

import { useCallback, useEffect, useId, useMemo, useRef, useState, type FormEvent } from "react";
import { ProgressBar } from "@/components/tremor/ProgressBar";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Field, Select, TextInput } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";
import { Fact, Facts, Panel } from "@/components/ui/Panel";
import { describeError, isAbortError, isApiError } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { useRuntime } from "@/state/runtime";
import { createEvidenceClient, type EvidenceClient } from "./client";
import { MAX_QUESTION_CHARS, OVERVIEW_QUESTION, SUGGESTED_QUESTIONS, type EvidenceResponse, type EvidenceStatement, type EvidenceStatus } from "./types";

export const TITLE = "Evidence Investigator";
export const SUBTITLE = "Understand missing portfolio data and its impact on your investment rules.";
export const SCOPE_NOTE =
  "A limited evidence tool, not a research agent: it reads the holdings files, instrument registry and source registry held by this service, and answers with calculated figures and fixed wording. It does not search the web or fetch new data.";
export const UNCONFIRMED_RULES_NOTE =
  "Limits mentioned here are this fictional scenario's suggested rules. They have not been confirmed by the investor and are not an active policy.";
export const UNKNOWN = "Unknown";
const WHOLE_PORTFOLIO = "";

const STATUS: Record<EvidenceStatus, { label: string; tone: "pass" | "unknown" | "fail" }> = {
  sufficient_evidence: { label: "Sufficient evidence", tone: "pass" },
  partial_evidence: { label: "Partial evidence", tone: "unknown" },
  insufficient_evidence: { label: "Insufficient evidence", tone: "fail" },
};

/** A percentage the service calculated, or "Unknown". A missing value is never shown as 0%. */
export function percentText(value: number | null | undefined): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return UNKNOWN;
  return `${Number(value.toFixed(value >= 99 && value < 100 ? 3 : 2))}%`;
}

export interface EvidenceInvestigatorChatProps {
  personaId: string;
  /** A confirmed policy version of this persona. Without one the service compares with the scenario's offered rules and says so. */
  policyId?: string | null;
  policyVersion?: number | null;
  /** Test seam. The app passes none: the client follows the runtime (live service or recorded test data). */
  client?: EvidenceClient;
}

interface FundOption {
  id: string;
  name: string;
}

type MessageBody = { role: "user"; text: string } | { role: "assistant"; answer: EvidenceResponse; scopeNote: string | null } | { role: "error"; text: string };
type Message = MessageBody & { id: number };

function Coverage({ label, value }: { label: string; value: number | null }) {
  const known = typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 100;
  return (
    <Fact label={label}>
      <span className="font-semibold tabular-nums" data-testid={`evidence-${label.toLowerCase().split(" ")[0]}`}>
        {percentText(value)}
      </span>
      {/* A bar only for a percentage that was actually measured. */}
      {known ? <ProgressBar value={value} aria-label={label} className="mt-1" /> : <p className="text-sm text-ink-muted">Not measurable from the evidence held.</p>}
    </Fact>
  );
}

function StatementList({ title, items, empty, hypothetical = false }: { title: string; items: EvidenceStatement[]; empty: string; hypothetical?: boolean }) {
  return (
    <section className="space-y-1">
      <h4 className="flex flex-wrap items-center gap-2 text-sm font-semibold text-ink">
        {title}
        {hypothetical ? (
          <Badge tone="unknown" dashed>
            Hypothetical: not measured
          </Badge>
        ) : null}
      </h4>
      {items.length === 0 ? (
        <p className="text-sm text-ink-muted">{empty}</p>
      ) : (
        <ul className="list-disc space-y-1 pl-5 text-[0.9375rem]">
          {items.map((item, index) => (
            <li key={index} className={hypothetical ? "italic" : undefined}>
              {item.text}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function Answer({ answer, scopeNote }: { answer: EvidenceResponse; scopeNote: string | null }) {
  if (!answer.question.supported) return <Notice tone="info" title="Outside what this assistant does">{answer.headline}</Notice>;
  const empty = answer.explanation.trim() === "" && answer.headline.trim() === "";
  const modelWorded = answer.explanation_source === "model";
  return (
    <div className="space-y-3">
      {scopeNote ? <p className="text-sm text-ink-muted">{scopeNote}</p> : null}
      {answer.question.fund_recognised ? (
        <p className="text-sm text-ink-muted">
          The question names {answer.question.fund_recognised}, so this answer is about that fund.
        </p>
      ) : null}
      {empty ? (
        <Notice tone="caution" title="The service sent an empty answer">Nothing is shown in its place. The structured evidence below is what was calculated.</Notice>
      ) : (
        <p className="font-semibold text-ink">{answer.headline}</p>
      )}
      {modelWorded ? (
        <div className="rounded-md border border-line bg-sunken p-3">
          <p className="text-xs font-semibold uppercase tracking-wider text-ink-muted">Explanation worded by the model from the evidence below</p>
          <p className="mt-1 whitespace-pre-line text-[0.9375rem]">{answer.explanation}</p>
        </div>
      ) : null}
      {!modelWorded && answer.model_status !== "not_configured" ? (
        <p className="text-sm text-ink-muted">The model explanation was not available, so this answer uses the service&rsquo;s own wording. The figures are the same.</p>
      ) : null}
      <StatementList title="1. What we know" items={answer.verified_findings} empty="Nothing is verified for this question." />
      <StatementList title="2. What is missing" items={answer.missing_evidence} empty="No gap was found for this question." />
      <StatementList title="3. What could happen under an assumption" items={answer.hypothetical_scenarios} empty="No hypothetical scenario applies." hypothetical />
      <StatementList title="4. What needs to be verified next" items={answer.next_evidence} empty="Nothing further is needed for the checks made here." />
      {answer.retrieval.message ? <p className="text-sm font-medium text-ink">{answer.retrieval.message}</p> : null}
      <details className="rounded-md border border-line p-3 text-sm">
        <summary className="byb-summary cursor-pointer font-semibold">Sources and calculation basis</summary>
        <div className="mt-2 space-y-3">
          {answer.sources.length === 0 ? (
            <p>No source record was found.</p>
          ) : (
            <ul className="space-y-2">
              {answer.sources.map((source, index) => (
                <li key={index}>
                  <span className="font-medium">{source.title ?? source.source_id ?? "Unregistered source"}</span>
                  {source.publisher ? ` — ${source.publisher}` : ""} · subject {source.subject} · as of {source.as_of_date ? formatDate(source.as_of_date) : UNKNOWN} · retrieved{" "}
                  {source.retrieval_date ? formatDate(source.retrieval_date) : UNKNOWN}{" "}
                  <Badge tone={source.verification === "verified" ? "pass" : "unknown"} dashed={source.verification !== "verified"}>
                    {source.verification === "verified" ? "Verified source" : "Provisional"}
                  </Badge>
                </li>
              ))}
            </ul>
          )}
          <div>
            <p className="font-semibold">Calculation basis</p>
            <ul className="list-disc space-y-1 pl-5">
              {answer.fund?.calculation_basis ? <li>{answer.fund.calculation_basis}</li> : null}
              {answer.fund === null ? <li>{answer.portfolio.basis}</li> : null}
              {answer.exposure_bounds.map((item, index) => (
                <li key={index}>
                  {item.category}, {item.unit}: {item.basis}
                </li>
              ))}
            </ul>
          </div>
          <div>
            <p className="font-semibold">Limitations</p>
            <ul className="list-disc space-y-1 pl-5">
              {answer.limitations.map((text, index) => (
                <li key={index}>{text}</li>
              ))}
            </ul>
          </div>
        </div>
      </details>
    </div>
  );
}

/**
 * The evidence-investigation assistant. It only reads: every figure comes from the service's structured answer,
 * and nothing here changes the portfolio, the rules or a verdict.
 */
export function EvidenceInvestigatorChat(props: EvidenceInvestigatorChatProps) {
  // A different investor is a different conversation: the fund selection and the messages start again.
  return <Investigator key={props.personaId} {...props} />;
}

function Investigator({ personaId, policyId = null, policyVersion = null, client: clientOverride }: EvidenceInvestigatorChatProps) {
  const { api, config } = useRuntime();
  const client = useMemo(() => clientOverride ?? createEvidenceClient(config), [clientOverride, config]);
  const fundSelectId = useId();
  const questionId = useId();
  const [funds, setFunds] = useState<FundOption[] | null>(null);
  const [fundsError, setFundsError] = useState<string | null>(null);
  const [fundId, setFundId] = useState<string>(WHOLE_PORTFOLIO);
  // The summary is kept with the scope it was calculated for, so a stale one is never shown for another scope.
  const [loaded, setLoaded] = useState<{ scope: string; answer: EvidenceResponse | null; error: string | null } | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [question, setQuestion] = useState("");
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const nextId = useRef(1);
  const logRef = useRef<HTMLDivElement>(null);

  // The funds this persona holds, from the same portfolio route the rest of the app uses.
  useEffect(() => {
    const controller = new AbortController();
    api.getPortfolio(personaId, { signal: controller.signal }).then(
      (portfolio) => {
        const held = portfolio.scenario.portfolio.positions.map((position) => portfolio.instruments[position.instrument_id]).filter((instrument) => instrument?.is_fund);
        setFunds(held.map((instrument) => ({ id: instrument!.instrument_id, name: instrument!.name })));
      },
      (error: unknown) => {
        if (!isAbortError(error)) setFundsError(describeError(error));
      },
    );
    return () => controller.abort();
  }, [api, personaId]);

  const request = useCallback(
    (text: string, signal?: AbortSignal) =>
      client.investigate({ persona_id: personaId, fund_id: fundId === WHOLE_PORTFOLIO ? null : fundId, question: text, policy_id: policyId, policy_version: policyVersion }, { signal }),
    [client, personaId, fundId, policyId, policyVersion],
  );

  // The evidence summary of the selected scope.
  const scope = `${fundId}|${policyId ?? ""}|${policyVersion ?? ""}`;
  useEffect(() => {
    const controller = new AbortController();
    request(OVERVIEW_QUESTION, controller.signal).then(
      (answer) => setLoaded({ scope, answer, error: null }),
      (error: unknown) => {
        if (!isAbortError(error)) setLoaded({ scope, answer: null, error: describeError(error) });
      },
    );
    return () => controller.abort();
  }, [request, scope]);
  const summary = loaded?.scope === scope ? loaded.answer : null;
  const summaryError = loaded?.scope === scope ? loaded.error : null;

  useEffect(() => {
    const log = logRef.current;
    if (log && typeof log.scrollTo === "function") log.scrollTo({ top: log.scrollHeight });
  }, [messages]);

  const push = (message: MessageBody) => {
    const id = nextId.current++;
    setMessages((current) => [...current, { ...message, id }]);
  };

  async function ask(text: string) {
    const trimmed = text.trim();
    if (busy) return;
    if (trimmed === "") {
      setFieldError("Type a question, or pick one of the suggested questions.");
      return;
    }
    if (trimmed.length > MAX_QUESTION_CHARS) {
      setFieldError(`Keep the question under ${MAX_QUESTION_CHARS} characters.`);
      return;
    }
    setFieldError(null);
    setQuestion("");
    setBusy(true);
    push({ role: "user", text: trimmed });
    try {
      const answer = await request(trimmed);
      const scopeNote =
        fundId === WHOLE_PORTFOLIO && /\bthis (etf|fund)\b/i.test(trimmed) ? "No fund is selected, so this answer covers the whole portfolio. Pick a fund above to ask about one ETF." : null;
      push({ role: "assistant", answer, scopeNote });
    } catch (error) {
      const routeMissing = isApiError(error) && error.kind === "not_found" && error.code === null;
      push({ role: "error", text: routeMissing ? "The evidence investigator is not available on this service yet. Nothing was calculated." : describeError(error) });
    } finally {
      setBusy(false);
    }
  }

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void ask(question);
  }

  const status = summary ? STATUS[summary.summary.data_quality_status] : null;
  return (
    <Panel title={TITLE} description={SUBTITLE} eyebrow="Read-only assistant" figures aside={status ? <Badge tone={status.tone} dashed={status.tone !== "pass"}>{status.label}</Badge> : null}>
      <div className="space-y-5">
        <p className="text-sm text-ink-muted" data-testid="evidence-scope-note">
          {SCOPE_NOTE}
        </p>
        {policyId === null ? (
          <Notice tone="caution" title="Suggested rules only: not confirmed">
            {UNCONFIRMED_RULES_NOTE}
          </Notice>
        ) : (
          <p className="text-sm text-ink-muted">
            Limits come from confirmed policy version <span className="tabular-nums">{policyVersion}</span>.
          </p>
        )}
        <Field htmlFor={fundSelectId} label="What to investigate" hint="The whole portfolio, or one fund held in it.">
          <Select id={fundSelectId} value={fundId} onChange={(event) => setFundId(event.target.value)} disabled={funds === null}>
            <option value={WHOLE_PORTFOLIO}>Whole portfolio</option>
            {(funds ?? []).map((fund) => (
              <option key={fund.id} value={fund.id}>
                {fund.id} — {fund.name}
              </option>
            ))}
          </Select>
        </Field>
        {fundsError ? <Notice tone="error" role="alert" title="The portfolio could not be loaded">{fundsError} Only the whole portfolio can be selected.</Notice> : null}
        {funds !== null && funds.length === 0 ? <Notice tone="info" title="No funds in this portfolio">There are no fund holdings to investigate; direct holdings need no look-through.</Notice> : null}

        <section aria-label="Evidence summary" className="rounded-lg border border-line bg-sunken p-4">
          <h3 className="text-lg font-semibold text-ink">Evidence summary</h3>
          {summaryError ? (
            <Notice tone="error" role="alert" title="The evidence summary could not be loaded" className="mt-2">
              {summaryError}
            </Notice>
          ) : summary === null ? (
            <p role="status" className="mt-2 text-ink-muted">Loading the evidence summary…</p>
          ) : (
            <>
              <p className="mt-1 text-sm text-ink-muted">
                For {summary.summary.scope_label}. Basis: {summary.summary.coverage_basis_label}.
              </p>
              <Facts className="mt-3">
                <Coverage label="Verified holdings" value={summary.summary.verified_weight_pct} />
                <Coverage label="Unresolved holdings" value={summary.summary.unresolved_weight_pct} />
                <Fact label="Data quality status">{STATUS[summary.summary.data_quality_status].label}</Fact>
                <Fact label="Last verified holdings date">{summary.summary.last_verified_holdings_date ? formatDate(summary.summary.last_verified_holdings_date) : UNKNOWN}</Fact>
                <Fact label="Sources investigated">{summary.summary.sources_investigated} (data snapshot only; no external provider)</Fact>
              </Facts>
              {(summary.fund?.data_quality_issues ?? []).some((issue) => issue.severity === "blocking") ? (
                <Notice tone="caution" title="The holdings file is not consistent" className="mt-3">
                  <ul className="list-disc pl-5">
                    {summary.fund!.data_quality_issues.filter((issue) => issue.severity === "blocking").map((issue) => (
                      <li key={issue.code}>{issue.detail}</li>
                    ))}
                  </ul>
                  <p>No percentage is shown for this fund.</p>
                </Notice>
              ) : null}
            </>
          )}
        </section>

        <section aria-label="Conversation" className="space-y-3">
          <div ref={logRef} role="log" aria-live="polite" aria-label="Messages" className="max-h-[36rem] space-y-3 overflow-y-auto">
            {messages.length === 0 ? <p className="text-ink-muted">Ask about missing holdings data, or start with a suggested question.</p> : null}
            {messages.map((message) =>
              message.role === "user" ? (
                <div key={message.id} className="ml-auto w-fit max-w-[85%] rounded-lg bg-accent-soft px-4 py-2 text-ink" data-testid="chat-user">
                  <span className="sr-only">You asked: </span>
                  {message.text}
                </div>
              ) : message.role === "error" ? (
                <Notice key={message.id} tone="error" role="alert" title="This question could not be answered">
                  {message.text}
                </Notice>
              ) : (
                <div key={message.id} className="rounded-lg border border-line bg-surface p-4" data-testid="chat-assistant">
                  <span className="sr-only">Evidence Investigator answered: </span>
                  <Answer answer={message.answer} scopeNote={message.scopeNote} />
                </div>
              ),
            )}
            {busy ? <p role="status" className="text-ink-muted">Investigating the evidence…</p> : null}
          </div>
          <div className="flex flex-wrap gap-2" aria-label="Suggested questions" role="group">
            {SUGGESTED_QUESTIONS.map((text) => (
              <Button key={text} size="sm" variant="quiet" softDisabled={busy} onClick={() => void ask(text)}>
                {text}
              </Button>
            ))}
          </div>
          <form onSubmit={onSubmit} className="flex flex-wrap items-end gap-2" noValidate>
            <Field htmlFor={questionId} label="Your question" error={fieldError} className="min-w-0 flex-1">
              <TextInput id={questionId} value={question} maxLength={MAX_QUESTION_CHARS} aria-invalid={fieldError ? true : undefined} onChange={(event) => setQuestion(event.target.value)} placeholder="For example: which holdings have no sector?" autoComplete="off" />
            </Field>
            <Button type="submit" variant="primary" busy={busy} busyLabel="Investigating…">
              Ask
            </Button>
          </form>
          <p className="text-sm text-ink-muted">This assistant explains evidence only. It cannot change your portfolio, your rules or a verdict.</p>
        </section>
      </div>
    </Panel>
  );
}
