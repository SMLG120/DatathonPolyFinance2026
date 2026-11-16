import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent, { type UserEvent } from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { ApiClient } from "@/lib/api";
import { ApiError } from "@/lib/api";
import { portfolioMatch } from "@/components/challenge/Comparison";
import { createFixturesClient } from "@/lib/api/fixtures-client";
import type { ChallengeResponse, ConfirmResponse, InvestigationAccepted, Portfolio } from "@/lib/contracts";
import { FIXTURES } from "@/lib/fixtures";
import { chooseMateo, confirmScenarioRules, go, renderApp, runInvestigation, toVerdict } from "@/test/app";
import { deferred } from "@/test/deferred";
import { customPortfolioId, liveDouble } from "@/test/live-double";

const robert = FIXTURES.portfolioRobert.response;
const amira = FIXTURES.portfolioAmira.response;

const CUSTOMIZED = "Customized fictional portfolio";
const ROBERT_ORIGINAL = "Robert’s original fictional portfolio";

const weight = (id: string) => screen.getByTestId(`customize-weight-${id}`);
const main = () => screen.getByRole("main");

async function retype(user: UserEvent, field: HTMLElement, text: string): Promise<void> {
  await user.clear(field);
  if (text !== "") await user.type(field, text);
}

async function start(options: { api?: ApiClient } = {}): Promise<UserEvent> {
  const user = userEvent.setup();
  renderApp(options);
  await screen.findByTestId("portfolio-table");
  return user;
}

/** Robert, customized: SPY at 15% and cash at 35%. Totals 100%. */
async function applyCustom(user: UserEvent): Promise<void> {
  await user.click(screen.getByTestId("customize-open"));
  await retype(user, weight("SPY"), "15");
  await retype(user, screen.getByTestId("customize-cash"), "35");
  await user.click(screen.getByTestId("customize-apply"));
  await waitFor(() => expect(screen.queryByTestId("customize-editor")).toBeNull());
}

async function startAndOpenSteps(user: UserEvent): Promise<void> {
  await confirmScenarioRules(user);
  await go("purchase");
  await user.click(screen.getByTestId("start-investigation"));
  await go("investigation");
}

// ---------------------------------------------------------------------------
// F8.1: which portfolio a job used, wherever a job is shown without its report
// ---------------------------------------------------------------------------

describe("Which portfolio a job used: the investigation stage", () => {
  it("names the customized portfolio of a job that is still running", async () => {
    const { api } = liveDouble({ simulate: "poll-timeout" });
    const user = await start({ api });
    await applyCustom(user);
    await startAndOpenSteps(user);
    const label = await screen.findByTestId("job-portfolio-label");
    expect(label).toHaveTextContent(CUSTOMIZED);
    expect(label).toHaveAttribute("data-portfolio-id", customPortfolioId("robert"));
    // Still running: there is no report that could have said it.
    expect(screen.queryByTestId("see-verdict")).toBeNull();
  });

  it("names the original portfolio of a failed job, and keeps naming it after a customization is applied", async () => {
    const { api } = liveDouble({ simulate: "job-failed" });
    const user = await start({ api });
    await startAndOpenSteps(user);
    expect(await screen.findByText("The investigation failed", {}, { timeout: 5_000 })).toBeInTheDocument();
    expect(screen.getByTestId("job-portfolio-label")).toHaveTextContent(ROBERT_ORIGINAL);

    await go("persona");
    await applyCustom(user);
    await go("investigation");
    expect(screen.getByTestId("job-portfolio-label")).toHaveTextContent(ROBERT_ORIGINAL);
  });

  it("names the customized portfolio of a failed job", async () => {
    const { api } = liveDouble({ simulate: "job-failed" });
    const user = await start({ api });
    await applyCustom(user);
    await startAndOpenSteps(user);
    expect(await screen.findByText("The investigation failed", {}, { timeout: 5_000 })).toBeInTheDocument();
    expect(screen.getByTestId("job-portfolio-label")).toHaveTextContent(CUSTOMIZED);
  });

  it("names the portfolio of a job that stopped to ask a question (Amira)", async () => {
    const clarification = FIXTURES.jobs.amiraClarification.response;
    const custom: Portfolio = { ...amira.scenario.portfolio, portfolio_id: customPortfolioId("amira"), cash_weight: 0.18, positions: amira.scenario.portfolio.positions.filter((position) => position.instrument_id !== "ETH-USD") };
    const fixtures = createFixturesClient({ latencyMs: 0 });
    const api: ApiClient = {
      ...fixtures,
      mode: "live",
      createInvestigation: async () => ({ ...FIXTURES.investigationAccepted.response, id: clarification.id, poll: { ...FIXTURES.investigationAccepted.response.poll, path: `/investigations/${clarification.id}` } }),
      getInvestigation: async () => ({ ...clarification, portfolio: custom }),
    };
    const user = await start({ api });
    await user.click(screen.getByRole("button", { name: "Use Amira’s portfolio" }));
    await waitFor(() => expect(screen.getByTestId("portfolio-table")).toHaveTextContent("Amira’s fictional portfolio"));
    await startAndOpenSteps(user);
    expect(await screen.findByTestId("job-portfolio-label")).toHaveTextContent(CUSTOMIZED);
    await go("verdict");
    expect(screen.getByTestId("job-clarification")).toBeInTheDocument();
    expect(screen.queryByTestId("report")).toBeNull();
  });

  it("says nothing about the portfolio of a job stored without one", async () => {
    const user = await start();
    await startAndOpenSteps(user);
    await screen.findByTestId("see-verdict", {}, { timeout: 5_000 });
    expect(screen.queryByTestId("job-portfolio-label")).toBeNull();
    expect(main()).not.toHaveTextContent("Portfolio checked");
  });
});

/**
 * The fixtures client gives the recorded job of a request the recorded id, so the same request started
 * twice is one job. This stand-in gives every start an id of its own, as the service does.
 */
function everyStartIsAJob() {
  const double = liveDouble();
  const realId = new Map<string, string>();
  const portfolios = new Map<string, Portfolio | undefined>();
  const createInvestigation = vi.fn<ApiClient["createInvestigation"]>(async (body, options) => {
    const accepted = await double.api.createInvestigation(body, options);
    const id = `${accepted.id}-start-${realId.size + 1}`;
    realId.set(id, accepted.id);
    portfolios.set(id, double.stored.get(accepted.id));
    return { ...accepted, id };
  });
  // The job of each start keeps the portfolio it was created with, whatever was started after it.
  const getInvestigation: ApiClient["getInvestigation"] = async (id, options) => {
    const job = await double.api.getInvestigation(realId.get(id) ?? id, options);
    const portfolio = portfolios.get(id);
    return portfolio ? { ...job, id, portfolio } : { ...job, id };
  };
  return { api: { ...double.api, createInvestigation, getInvestigation } satisfies ApiClient, createInvestigation };
}

describe("Which portfolio a job used: the list of reports", () => {
  it("tells apart two reports under one policy version that differ only by portfolio", async () => {
    const { api, createInvestigation } = everyStartIsAJob();
    const user = await start({ api });
    await confirmScenarioRules(user);
    await runInvestigation(user);
    await go("persona");
    await applyCustom(user);
    await runInvestigation(user);
    expect(createInvestigation).toHaveBeenCalledTimes(2);

    const entries = await screen.findAllByTestId("report-entry");
    expect(entries).toHaveLength(2);
    // Same policy version, same request: only the portfolio differs, and each entry says which.
    for (const entry of entries) expect(entry).toHaveTextContent("policy version 1");
    expect(within(entries[0] as HTMLElement).getByTestId("report-entry-portfolio")).toHaveTextContent(ROBERT_ORIGINAL);
    expect(within(entries[1] as HTMLElement).getByTestId("report-entry-portfolio")).toHaveTextContent(CUSTOMIZED);
  });

  it("says nothing in an entry whose job was stored without a portfolio", async () => {
    const user = await toVerdict();
    await go("challenge");
    await user.click(within(screen.getByTestId("change-rule-form")).getByTestId("fill-example-rule"));
    await user.click(screen.getByTestId("submit-rule-change"));
    await within(await screen.findByTestId("rule-change-comparison")).findByTestId("result-comparison", {}, { timeout: 5_000 });
    await go("verdict");
    expect(screen.getAllByTestId("report-entry")).toHaveLength(2);
    expect(screen.queryByTestId("report-entry-portfolio")).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// F8.2: the comparison claims "the same portfolio" only when both jobs say so
// ---------------------------------------------------------------------------

describe("Rule-change comparison: the portfolio of the two reports", () => {
  const SAME_CLAIM = "both reports use the same portfolio";

  async function compare(child: "copied" | "other" | "missing" | "legacy"): Promise<HTMLElement> {
    const double = liveDouble();
    const api: ApiClient =
      child === "legacy"
        ? { ...createFixturesClient({ latencyMs: 0 }), mode: "live" }
        : {
            ...double.api,
            challengeInvestigation: async (id, body, options) => {
              const response = await double.api.challengeInvestigation(id, body, options);
              const childId = response.investigation?.id as string;
              if (child === "other") double.stored.set(childId, robert.scenario.portfolio);
              if (child === "missing") double.stored.delete(childId);
              return response;
            },
          };
    const user = await start({ api });
    if (child !== "legacy") await applyCustom(user);
    await confirmScenarioRules(user);
    await runInvestigation(user);
    await go("challenge");
    await user.click(within(screen.getByTestId("change-rule-form")).getByTestId("fill-example-rule"));
    await user.click(screen.getByTestId("submit-rule-change"));
    const comparison = await screen.findByTestId("rule-change-comparison");
    await within(comparison).findByTestId("result-comparison", {}, { timeout: 5_000 });
    return comparison;
  }

  it("says both reports used the same portfolio when the two jobs carry the same portfolio id", async () => {
    const comparison = await compare("copied");
    const line = within(comparison).getByTestId("comparison-portfolio");
    expect(line).toHaveAttribute("data-portfolio-match", "same");
    expect(line).toHaveTextContent(`Both reports were checked against the portfolio stored with the earlier one: ${CUSTOMIZED}.`);
    expect(within(comparison).getByTestId("comparison-cause")).toHaveTextContent(SAME_CLAIM);
  });

  it("says the portfolios differ, names both, and does not claim sameness, when the ids differ", async () => {
    const comparison = await compare("other");
    const line = within(comparison).getByTestId("comparison-portfolio");
    expect(line).toHaveAttribute("data-portfolio-match", "different");
    expect(line).toHaveTextContent("The two reports were not checked against the same portfolio");
    expect(line).toHaveTextContent(`The earlier report used: ${CUSTOMIZED}.`);
    expect(line).toHaveTextContent(`The new report used: ${ROBERT_ORIGINAL}.`);
    expect(comparison).not.toHaveTextContent(SAME_CLAIM);
    expect(comparison).not.toHaveTextContent("Both reports were checked against");
    expect(within(comparison).getByTestId("comparison-cause")).toHaveTextContent("can come from the portfolio as well as from the rule that was changed");
  });

  it("says it cannot confirm the same portfolio when only one of the two jobs names its portfolio", async () => {
    const comparison = await compare("missing");
    const line = within(comparison).getByTestId("comparison-portfolio");
    expect(line).toHaveAttribute("data-portfolio-match", "unknown");
    expect(line).toHaveTextContent(`The earlier report was checked against: ${CUSTOMIZED}.`);
    expect(line).toHaveTextContent("The service did not say which portfolio the new report was checked against");
    expect(comparison).not.toHaveTextContent(SAME_CLAIM);
    expect(comparison).not.toHaveTextContent("Both reports were checked against");
    expect(within(comparison).getByTestId("comparison-cause")).toHaveTextContent("which this page cannot confirm for these two");
  });

  it("compares the ids the two jobs carry, and nothing else", () => {
    const job = FIXTURES.jobs.robertSucceeded.response;
    const original = robert.scenario.portfolio;
    const custom: Portfolio = { ...original, portfolio_id: customPortfolioId("robert") };
    expect(portfolioMatch({ ...job, portfolio: custom }, { ...job, portfolio: { ...custom } })).toBe("same");
    // The same weights under another id are not called the same: only the service names a portfolio.
    expect(portfolioMatch({ ...job, portfolio: original }, { ...job, portfolio: custom })).toBe("different");
    expect(portfolioMatch({ ...job, portfolio: custom }, job)).toBe("unknown");
    expect(portfolioMatch(job, { ...job, portfolio: custom })).toBe("unknown");
    expect(portfolioMatch(job, job)).toBe("legacy");
    // Before the new job has answered at all, nothing is claimed about it.
    expect(portfolioMatch({ ...job, portfolio: custom }, undefined)).toBe("pending");
    expect(portfolioMatch(job, undefined)).toBe("pending");
    expect(portfolioMatch(undefined, job)).toBe("unknown");
  });

  it("keeps the earlier wording when neither job names a portfolio: both were then checked against the scenario portfolio", async () => {
    const comparison = await compare("legacy");
    expect(within(comparison).queryByTestId("comparison-portfolio")).toBeNull();
    expect(within(comparison).getByTestId("comparison-cause")).toHaveTextContent(SAME_CLAIM);
  });
});

// ---------------------------------------------------------------------------
// F8.3: a preview the service refused
// ---------------------------------------------------------------------------

describe("Purchase preview: an error from the service", () => {
  const preview = () => screen.getByTestId("purchase-preview");

  it("lists what the service refused and offers no retry of a request that would be refused again", async () => {
    const { api, check } = liveDouble();
    check.mockRejectedValue(
      new ApiError("validation", "The customized portfolio is not valid.", {
        status: 400,
        code: "VALIDATION_ERROR",
        details: [
          { path: "custom_portfolio.positions[1].instrument_id", issue: "SPY cannot be held by this persona" },
          { path: "custom_portfolio", issue: "the weights total 0.95, not 1" },
        ],
      }),
    );
    const user = await start({ api });
    await applyCustom(user);
    await confirmScenarioRules(user);
    await go("purchase");

    expect(await screen.findByTestId("purchase-preview-error")).toHaveTextContent("The customized portfolio is not valid.");
    const issues = within(preview()).getByTestId("purchase-preview-issues");
    expect(within(issues).getAllByRole("listitem").map((item) => item.textContent)).toEqual(["SPY cannot be held by this persona", "the weights total 0.95, not 1"]);
    expect(within(preview()).queryByRole("button", { name: "Try again" })).toBeNull();
    expect(within(preview()).getByTestId("purchase-preview-refused")).toHaveTextContent("sending it again unchanged would be refused again");
    // It must not promise that the same request can be started.
    expect(preview()).not.toHaveTextContent("The investigation can still be started");
    expect(screen.queryByTestId("cash-after")).toBeNull();
  });

  it("still offers a retry, and lists nothing, when the service did not answer", async () => {
    const { api, check } = liveDouble();
    check.mockRejectedValueOnce(new ApiError("server", "The check service did not answer.", { status: 503 }));
    const user = await start({ api });
    await confirmScenarioRules(user);
    await go("purchase");
    expect(await screen.findByTestId("purchase-preview-error")).toHaveTextContent("The check service did not answer.");
    expect(within(preview()).queryByTestId("purchase-preview-issues")).toBeNull();
    expect(within(preview()).queryByTestId("purchase-preview-refused")).toBeNull();
    expect(preview()).toHaveTextContent("The investigation can still be started");
    await user.click(within(preview()).getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(preview()).toHaveAttribute("data-preview-status", "ready"));
  });
});

// ---------------------------------------------------------------------------
// F8.4: input typed into the editor and not applied
// ---------------------------------------------------------------------------

describe("Customize this profile: leaving stage 1 with the editor open", () => {
  it("keeps what was typed for the way back, applies none of it, and sends none of it", async () => {
    const { api, check } = liveDouble();
    const user = await start({ api });
    await user.click(screen.getByTestId("customize-open"));
    await retype(user, weight("SPY"), "15");
    await user.click(screen.getByTestId("customize-remove-JNJ"));
    await retype(user, screen.getByTestId("customize-objective"), "Sleep well.");

    // Leave by the Continue control, with the form neither applied nor cancelled.
    await user.click(screen.getByTestId("continue-link"));
    await waitFor(() => expect(window.location.hash).toBe("#/purchase"));
    expect(screen.queryByTestId("customized-badge")).toBeNull();
    await confirmScenarioRules(user);
    expect(screen.getByTestId("objective")).not.toHaveTextContent("Sleep well.");
    await go("purchase");
    await waitFor(() => expect(check).toHaveBeenCalled());
    for (const [body] of check.mock.calls) expect("custom_portfolio" in body).toBe(false);

    // Back on stage 1 the editor is still open with the unapplied input, and the table still shows the applied weights.
    await go("persona");
    expect(screen.getByTestId("customize-editor")).toBeInTheDocument();
    expect(weight("SPY")).toHaveValue("15");
    expect(screen.queryByTestId("customize-weight-JNJ")).toBeNull();
    expect(screen.getByTestId("customize-objective")).toHaveValue("Sleep well.");
    expect(screen.queryByTestId("customized-badge")).toBeNull();
    expect(within(screen.getByTestId("portfolio-table")).getByText("JNJ")).toBeInTheDocument();

    // Cancel still discards it: the editor then starts from the applied portfolio again.
    await user.click(screen.getByTestId("customize-cancel"));
    await go("goals");
    await go("persona");
    expect(screen.queryByTestId("customize-editor")).toBeNull();
    await user.click(screen.getByTestId("customize-open"));
    expect(weight("SPY")).toHaveValue("20");
    expect(weight("JNJ")).toHaveValue("5");
  });
});

// ---------------------------------------------------------------------------
// F9: an answer that arrives after the persona was changed belongs to no session
// ---------------------------------------------------------------------------

describe("An answer that arrives after another persona was chosen", () => {
  async function switchToMateo(user: UserEvent): Promise<void> {
    await go("persona");
    await chooseMateo(user);
  }

  async function expectNoJobAndNoPolicy(): Promise<void> {
    await go("investigation");
    expect(screen.getByText("No investigation has been started")).toBeInTheDocument();
    await go("verdict");
    expect(screen.getByText("There is no result yet")).toBeInTheDocument();
    await go("goals");
    await screen.findAllByTestId("rule-card");
    expect(screen.queryByTestId("policy-rule-card")).toBeNull();
  }

  it("does not attach Robert's accepted investigation to Mateo's session, and does not move to the result", async () => {
    const { api, createInvestigation } = liveDouble();
    const accepted = deferred<InvestigationAccepted>();
    createInvestigation.mockImplementationOnce(() => accepted.promise);
    const user = await start({ api });
    await confirmScenarioRules(user);
    await go("purchase");
    await user.click(screen.getByTestId("start-investigation"));
    await waitFor(() => expect(createInvestigation).toHaveBeenCalledTimes(1));

    await switchToMateo(user);
    await act(async () => {
      accepted.resolve(FIXTURES.investigationAccepted.response);
      await accepted.promise;
    });
    expect(window.location.hash).toBe("#/persona");
    await expectNoJobAndNoPolicy();
  });

  it("does not attach it to a new session of the same persona either (Robert, Mateo, Robert)", async () => {
    const { api, createInvestigation } = liveDouble();
    const accepted = deferred<InvestigationAccepted>();
    createInvestigation.mockImplementationOnce(() => accepted.promise);
    const user = await start({ api });
    await confirmScenarioRules(user);
    await go("purchase");
    await user.click(screen.getByTestId("start-investigation"));
    await waitFor(() => expect(createInvestigation).toHaveBeenCalledTimes(1));

    await switchToMateo(user);
    await user.click(screen.getByRole("button", { name: "Use Robert’s portfolio" }));
    await waitFor(() => expect(screen.getByTestId("portfolio-table")).toHaveTextContent("Robert’s fictional portfolio"));
    await act(async () => {
      accepted.resolve(FIXTURES.investigationAccepted.response);
      await accepted.promise;
    });
    expect(window.location.hash).toBe("#/persona");
    await expectNoJobAndNoPolicy();
  });

  it("does not show Robert's refused start as an error of Mateo's session", async () => {
    const { api, createInvestigation } = liveDouble();
    const accepted = deferred<InvestigationAccepted>();
    createInvestigation.mockImplementationOnce(() => accepted.promise);
    const user = await start({ api });
    await confirmScenarioRules(user);
    await go("purchase");
    await user.click(screen.getByTestId("start-investigation"));
    await waitFor(() => expect(createInvestigation).toHaveBeenCalledTimes(1));

    await switchToMateo(user);
    await act(async () => {
      accepted.reject(new ApiError("server", "The service failed for Robert.", { status: 500 }));
      await accepted.promise.catch(() => undefined);
    });
    await go("purchase");
    expect(main()).not.toHaveTextContent("The service failed for Robert.");
    expect(main()).not.toHaveTextContent("The investigation could not be started");
  });

  it("does not add Robert's confirmed policy to Mateo's session", async () => {
    const { api, confirmRules } = liveDouble();
    const confirmed = deferred<ConfirmResponse>();
    confirmRules.mockImplementationOnce(() => confirmed.promise);
    const user = await start({ api });
    await go("goals");
    await screen.findAllByTestId("rule-card");
    await user.click(screen.getByTestId("confirm-rules"));
    await waitFor(() => expect(confirmRules).toHaveBeenCalledTimes(1));

    await switchToMateo(user);
    await act(async () => {
      confirmed.resolve(FIXTURES.confirmRobertV1.response);
      await confirmed.promise;
    });
    await go("goals");
    const cards = await screen.findAllByTestId("rule-card");
    expect(screen.queryByTestId("policy-rule-card")).toBeNull();
    // Mateo's offers are all still proposals: none was removed as "confirmed".
    expect(cards).toHaveLength(FIXTURES.scenarios.mateo?.scenario_rules.length ?? -1);
    await go("purchase");
    expect(screen.getByRole("link", { name: "Set my limits" })).toBeInTheDocument();
  });

  it("does not add the policy and the job of Robert's rule change to Mateo's session", async () => {
    const { api, challengeInvestigation } = liveDouble();
    const user = await start({ api });
    await confirmScenarioRules(user);
    await runInvestigation(user);
    await go("challenge");
    const changed = deferred<ChallengeResponse>();
    challengeInvestigation.mockImplementationOnce(() => changed.promise);
    await user.click(within(screen.getByTestId("change-rule-form")).getByTestId("fill-example-rule"));
    await user.click(screen.getByTestId("submit-rule-change"));
    await waitFor(() => expect(challengeInvestigation).toHaveBeenCalledTimes(1));

    await switchToMateo(user);
    await act(async () => {
      changed.resolve(FIXTURES.challenges.changeRule.response);
      await changed.promise;
    });
    await expectNoJobAndNoPolicy();
    await go("challenge");
    expect(screen.queryByTestId("rule-change-comparison")).toBeNull();
  });

  it("does not list the drafts of Robert's clarified preference among Mateo's proposals", async () => {
    const { api, challengeInvestigation } = liveDouble();
    const user = await start({ api });
    await confirmScenarioRules(user);
    await runInvestigation(user);
    await go("challenge");
    const answered = deferred<ChallengeResponse>();
    challengeInvestigation.mockImplementationOnce(() => answered.promise);
    await user.click(within(screen.getByTestId("change-rule-form")).getByTestId("fill-example-rule"));
    await user.click(screen.getByTestId("submit-rule-change"));
    await waitFor(() => expect(challengeInvestigation).toHaveBeenCalledTimes(1));

    await switchToMateo(user);
    await go("goals");
    const before = (await screen.findAllByTestId("rule-card")).map((card) => card.getAttribute("data-rule-id"));
    const objectivesBefore = screen.getAllByTestId("objective").map((node) => node.textContent);
    // The page reads the answer by what it carries, so the recorded answer to a clarified preference stands in here.
    await act(async () => {
      answered.resolve(FIXTURES.challenges.clarifyPreference.response);
      await answered.promise;
    });
    expect(screen.getAllByTestId("rule-card").map((card) => card.getAttribute("data-rule-id"))).toEqual(before);
    expect(screen.getAllByTestId("objective").map((node) => node.textContent)).toEqual(objectivesBefore);
  });
});
