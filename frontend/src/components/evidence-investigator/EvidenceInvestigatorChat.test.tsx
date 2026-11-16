import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api";
import { LIVE_CONFIG, renderWithApp } from "@/test/render";
import { asEvidenceResponse, createHttpEvidenceClient, createRecordedEvidenceClient, NO_RECORDED_ANSWER, type EvidenceClient } from "./client";
import { EvidenceInvestigatorChat, percentText, SUBTITLE, TITLE, UNKNOWN } from "./EvidenceInvestigatorChat";
import recorded from "./recorded-answers.json";
import { OVERVIEW_QUESTION, SUGGESTED_QUESTIONS, type EvidenceRequest, type EvidenceResponse } from "./types";

// Answers recorded from the service code on the synthetic universes; tests only replace named members of them.
const recordedClient = createRecordedEvidenceClient();
const answerFor = (persona: string, fund: string | null, question: string) => recordedClient.investigate({ persona_id: persona, fund_id: fund, question, policy_id: null, policy_version: null });

function clientReturning(make: (request: EvidenceRequest) => Promise<EvidenceResponse>): EvidenceClient & { requests: EvidenceRequest[] } {
  const requests: EvidenceRequest[] = [];
  return { requests, investigate: (request) => (requests.push(request), make(request)) };
}

const summaryRegion = () => screen.getByRole("region", { name: "Evidence summary" });

describe("EvidenceInvestigatorChat", () => {
  it("shows the title, the subtitle and the evidence summary of the whole portfolio", async () => {
    renderWithApp(<EvidenceInvestigatorChat personaId="robert" />);
    expect(screen.getByRole("heading", { name: TITLE })).toBeInTheDocument();
    expect(screen.getByText(SUBTITLE)).toBeInTheDocument();
    const summary = summaryRegion();
    await within(summary).findByText("Verified holdings");
    for (const label of ["Unresolved holdings", "Data quality status", "Last verified holdings date", "Sources investigated"]) expect(within(summary).getByText(label)).toBeInTheDocument();
    // measured percentages get a bar
    expect(within(summary).getAllByRole("progressbar").length).toBe(2);
    expect(await screen.findByRole("option", { name: /^SPY/ })).toBeInTheDocument();
  });

  it("shows Unknown, not 0%, and no progress bar when a fund has no holdings", async () => {
    const user = userEvent.setup();
    renderWithApp(<EvidenceInvestigatorChat personaId="mateo" />);
    await user.selectOptions(await screen.findByLabelText("What to investigate"), await screen.findByRole("option", { name: /^ESGV/ }));
    const summary = summaryRegion();
    await waitFor(() => expect(within(summary).getByTestId("evidence-verified")).toHaveTextContent(UNKNOWN));
    expect(within(summary).getByTestId("evidence-verified")).not.toHaveTextContent("0%");
    expect(within(summary).getByText("Insufficient evidence")).toBeInTheDocument();
    expect(within(summary).getByText("Last verified holdings date").nextElementSibling).toHaveTextContent(UNKNOWN);
    // only the unresolved share (the whole fund) is a measured number
    expect(within(summary).getAllByRole("progressbar").length).toBe(1);
  });

  it("answers a suggested question in four labelled parts and marks hypothetical values", async () => {
    const user = userEvent.setup();
    renderWithApp(<EvidenceInvestigatorChat personaId="mateo" />);
    await within(summaryRegion()).findByText("Verified holdings");
    await user.click(screen.getByRole("button", { name: "Could missing holdings violate my technology limit?" }));
    const answer = await screen.findByTestId("chat-assistant");
    expect(screen.getByTestId("chat-user")).toHaveTextContent("Could missing holdings violate my technology limit?");
    for (const title of ["1. What we know", "2. What is missing", "3. What could happen under an assumption", "4. What needs to be verified next"]) {
      expect(within(answer).getByRole("heading", { name: new RegExp(title) })).toBeInTheDocument();
    }
    expect(within(answer).getByText("Hypothetical — not measured")).toBeInTheDocument();
    expect(within(answer).getByText("Sources and calculation basis")).toBeInTheDocument();
    expect(within(answer).getByText("Calculation basis")).toBeInTheDocument();
    expect(within(answer).getAllByText(/Provisional|Verified source/).length).toBeGreaterThan(0);
  });

  it("says so when 'this ETF' is asked without a fund selected", async () => {
    const user = userEvent.setup();
    renderWithApp(<EvidenceInvestigatorChat personaId="robert" />);
    await within(summaryRegion()).findByText("Verified holdings");
    await user.click(screen.getByRole("button", { name: "What data is missing from this ETF?" }));
    expect(await screen.findByText(/No fund is selected, so this answer covers the whole portfolio/)).toBeInTheDocument();
  });

  it("sends the persona, the fund, the question and the policy version, and nothing calculated", async () => {
    const user = userEvent.setup();
    const client = clientReturning((request) => answerFor("robert", request.fund_id, OVERVIEW_QUESTION));
    renderWithApp(<EvidenceInvestigatorChat personaId="robert" policyId="pol-robert-1" policyVersion={2} client={client} />);
    await within(summaryRegion()).findByText("Verified holdings");
    await user.type(screen.getByLabelText("Your question"), "Which holdings have no sector?");
    await user.click(screen.getByRole("button", { name: "Ask" }));
    await screen.findByTestId("chat-assistant");
    expect(client.requests.at(-1)).toEqual({ persona_id: "robert", fund_id: null, question: "Which holdings have no sector?", policy_id: "pol-robert-1", policy_version: 2 });
  });

  it("shows an API error as an alert and keeps the conversation usable", async () => {
    const user = userEvent.setup();
    let fail = false;
    const client = clientReturning((request) => (fail ? Promise.reject(new ApiError("server", "The service reported an internal error. Nothing was changed.")) : answerFor("robert", request.fund_id, OVERVIEW_QUESTION)));
    renderWithApp(<EvidenceInvestigatorChat personaId="robert" client={client} />);
    await within(summaryRegion()).findByText("Verified holdings");
    fail = true;
    await user.click(screen.getByRole("button", { name: "Which sources were checked?" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The service reported an internal error");
    fail = false;
    await user.click(screen.getByRole("button", { name: "Which sources were checked?" }));
    expect(await screen.findByTestId("chat-assistant")).toBeInTheDocument();
  });

  it("explains a service that does not have the route yet, and a summary that cannot load", async () => {
    const user = userEvent.setup();
    const client = clientReturning(() => Promise.reject(new ApiError("not_found", "The service has no record of this item.", { status: 404 })));
    renderWithApp(<EvidenceInvestigatorChat personaId="robert" client={client} />);
    expect(await within(summaryRegion()).findByRole("alert")).toHaveTextContent("The evidence summary could not be loaded");
    await user.click(screen.getByRole("button", { name: "Which sources were checked?" }));
    expect(await screen.findByText(/not available on this service yet/)).toBeInTheDocument();
  });

  it("labels model wording, and says when the model was unavailable", async () => {
    const user = userEvent.setup();
    const base = await answerFor("robert", null, "How much of my portfolio is verified?");
    const answers: EvidenceResponse[] = [
      { ...base, explanation: "Most of the portfolio is verified.", explanation_source: "model", model_status: "used" },
      { ...base, explanation_source: "template", model_status: "unavailable (ThrottlingException)" },
    ];
    const client = clientReturning((request) => Promise.resolve(request.question === OVERVIEW_QUESTION ? base : (answers.shift() as EvidenceResponse)));
    renderWithApp(<EvidenceInvestigatorChat personaId="robert" client={client} />);
    await within(summaryRegion()).findByText("Verified holdings");
    await user.click(screen.getByRole("button", { name: "How much of my portfolio is verified?" }));
    expect(await screen.findByText("Explanation worded by the model from the evidence below")).toBeInTheDocument();
    expect(screen.getByText("Most of the portfolio is verified.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "How much of my portfolio is verified?" }));
    expect(await screen.findByText(/The model explanation was not available/)).toBeInTheDocument();
  });

  it("handles an empty answer, an unsupported question and an empty input", async () => {
    const user = userEvent.setup();
    const base = await answerFor("robert", null, OVERVIEW_QUESTION);
    const answers: EvidenceResponse[] = [
      { ...base, explanation: "", headline: "" },
      { ...base, question: { ...base.question, supported: false }, headline: "This assistant only investigates holdings evidence." },
    ];
    const client = clientReturning((request) => Promise.resolve(request.question === OVERVIEW_QUESTION ? base : (answers.shift() as EvidenceResponse)));
    renderWithApp(<EvidenceInvestigatorChat personaId="robert" client={client} />);
    await within(summaryRegion()).findByText("Verified holdings");
    await user.click(screen.getByRole("button", { name: "Ask" }));
    expect(screen.getByText("Type a question, or pick one of the suggested questions.")).toBeInTheDocument();
    await user.type(screen.getByLabelText("Your question"), "anything");
    await user.click(screen.getByRole("button", { name: "Ask" }));
    expect(await screen.findByText("The service sent an empty answer")).toBeInTheDocument();
    await user.type(screen.getByLabelText("Your question"), "Should I buy?");
    await user.click(screen.getByRole("button", { name: "Ask" }));
    expect(await screen.findByText("Outside what this assistant does")).toBeInTheDocument();
  });

  it("warns when the holdings weights do not reconcile and shows no percentage", async () => {
    const base = await answerFor("robert", "SPY", OVERVIEW_QUESTION);
    const broken: EvidenceResponse = {
      ...base,
      summary: { ...base.summary, verified_weight_pct: null, unresolved_weight_pct: null, data_quality_status: "insufficient_evidence" },
      fund: { ...base.fund!, data_quality_issues: [{ code: "WEIGHTS_EXCEED_FUND", severity: "blocking", detail: "The printed weights add up to more than the fund itself." }] },
    };
    renderWithApp(<EvidenceInvestigatorChat personaId="robert" client={clientReturning(() => Promise.resolve(broken))} />);
    const summary = summaryRegion();
    expect(await within(summary).findByText("The holdings file is not consistent")).toBeInTheDocument();
    expect(within(summary).queryByRole("progressbar")).toBeNull();
    expect(within(summary).getAllByText(UNKNOWN).length).toBeGreaterThanOrEqual(2);
  });
});

describe("evidence clients", () => {
  it("formats unknown values as Unknown and never as 0%", () => {
    expect([percentText(null), percentText(undefined), percentText(Number.NaN)]).toEqual([UNKNOWN, UNKNOWN, UNKNOWN]);
    expect([percentText(0), percentText(82), percentText(99.871325), percentText(12.3456)]).toEqual(["0%", "82%", "99.871%", "12.35%"]);
  });

  it("offers the same questions the service recorded", () => {
    expect([...SUGGESTED_QUESTIONS]).toEqual(recorded.questions);
    expect(OVERVIEW_QUESTION).toBe(recorded.overview_question);
    expect(recorded.synthetic).toBe(true);
  });

  it("test data: answers the suggested questions and refuses free-form ones and unknown scopes", async () => {
    const answer = await answerFor("mateo", "XIU.TO", SUGGESTED_QUESTIONS[0]);
    expect(answer.fund_id).toBe("XIU.TO");
    expect(answer.question.topic).toBe("missing_data");
    await expect(answerFor("mateo", "XIU.TO", "free text")).rejects.toMatchObject({ kind: "no_fixture", message: NO_RECORDED_ANSWER });
    await expect(answerFor("amira", null, OVERVIEW_QUESTION)).rejects.toMatchObject({ kind: "no_fixture" });
  });

  it("live: posts to /evidence/investigate with the bearer code and reads contract errors", async () => {
    const good = await answerFor("robert", null, OVERVIEW_QUESTION);
    const fetchImpl = vi.fn(async () => new Response(JSON.stringify(good), { status: 200 }));
    const client = createHttpEvidenceClient(LIVE_CONFIG.apiBaseUrl as string, () => "code-123", fetchImpl as unknown as typeof fetch);
    const request = { persona_id: "robert", fund_id: "SPY", question: "q", policy_id: null, policy_version: null };
    await expect(client.investigate(request)).resolves.toMatchObject({ schema_version: "evidence-investigator/1" });
    const [url, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("https://api.example.test/evidence/investigate");
    expect(init.method).toBe("POST");
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer code-123");
    expect(JSON.parse(init.body as string)).toEqual(request);

    const refuse = (status: number, body: unknown) => createHttpEvidenceClient("https://x.test", () => null, (async () => new Response(JSON.stringify(body), { status })) as unknown as typeof fetch).investigate(request);
    await expect(refuse(404, { error: { code: "NOT_FOUND", message: "The service has no record of this fund.", details: [], request_id: null } })).rejects.toMatchObject({ kind: "not_found", code: "NOT_FOUND", message: "The service has no record of this fund." });
    await expect(refuse(404, { message: "Not Found" })).rejects.toMatchObject({ kind: "not_found", code: null });
    await expect(refuse(403, { message: "Forbidden" })).rejects.toMatchObject({ kind: "unauthorized" });
    await expect(refuse(200, { anything: true })).rejects.toMatchObject({ kind: "invalid_response" });
    await expect(createHttpEvidenceClient("https://x.test", () => null, (async () => Promise.reject(new TypeError("offline"))) as unknown as typeof fetch).investigate(request)).rejects.toMatchObject({ kind: "network" });
  });

  it("refuses an answer in the wrong shape", () => {
    expect(() => asEvidenceResponse(null)).toThrow(ApiError);
    expect(() => asEvidenceResponse({ schema_version: "other/1" })).toThrow(ApiError);
  });
});
