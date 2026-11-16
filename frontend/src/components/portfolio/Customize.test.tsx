import { screen, waitFor, within } from "@testing-library/react";
import userEvent, { type UserEvent } from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { ApiClient } from "@/lib/api";
import { ApiError } from "@/lib/api";
import { createFixturesClient } from "@/lib/api/fixtures-client";
import type { CheckRequest, ConfirmRequest, CustomPortfolio, InvestigationCreateRequest, Portfolio } from "@/lib/contracts";
import { TOTAL_MESSAGE } from "@/lib/customize";
import { FIXTURES } from "@/lib/fixtures";
import { chooseMateo, confirmScenarioRules, go, renderApp, runInvestigation } from "@/test/app";

const robert = FIXTURES.portfolioRobert.response;
const scenarioObjective = robert.scenario.objectives[0];
if (!scenarioObjective) throw new Error("Robert's scenario has no objective.");

/** The portfolio id a service gives a customized portfolio. Only its difference from the scenario's id matters here. */
const CUSTOM_ID = "pf-robert-custom-0123456789ab";

/**
 * A stand-in for the live service, for tests of what the page SENDS and of which portfolio a report shows.
 *
 * It is the fixtures client in live mode. It cannot calculate either, so it answers a request on a
 * customized portfolio with the recording made for the same purchase; no test below reads a figure of
 * such an answer. Like the service, it stores the portfolio a job was created with and returns it as
 * `portfolio` of GET /investigations/{id}.
 */
function liveDouble(options: { simulate?: "job-failed" } = {}) {
  const fixtures = createFixturesClient({ latencyMs: 0, simulate: options.simulate });
  const stored = new Map<string, Portfolio>();
  const check = vi.fn<ApiClient["check"]>(async (body, options) => {
    const rest = { ...body };
    delete rest.custom_portfolio;
    return fixtures.check(rest, options);
  });
  const createInvestigation = vi.fn<ApiClient["createInvestigation"]>(async (body, options) => {
    const rest = { ...body };
    delete rest.custom_portfolio;
    const accepted = await fixtures.createInvestigation(rest, options);
    const custom = body.custom_portfolio;
    stored.set(accepted.id, custom ? { ...robert.scenario.portfolio, portfolio_id: CUSTOM_ID, cash_weight: custom.cash_weight, positions: custom.positions } : robert.scenario.portfolio);
    return accepted;
  });
  const getInvestigation = vi.fn<ApiClient["getInvestigation"]>(async (id, options) => ({ ...(await fixtures.getInvestigation(id, options)), portfolio: stored.get(id) }));
  const confirmRules = vi.fn(fixtures.confirmRules);
  const interpretRules = vi.fn(fixtures.interpretRules);
  const api: ApiClient = { ...fixtures, mode: "live", check, createInvestigation, getInvestigation, confirmRules, interpretRules };
  return { api, check, createInvestigation, getInvestigation, confirmRules, interpretRules };
}

const weight = (id: string) => screen.getByTestId(`customize-weight-${id}`);
const rowWeight = (id: string) => {
  const row = within(screen.getByTestId("portfolio-table"))
    .getAllByTestId("portfolio-row")
    .find((candidate) => within(candidate).queryByText(id) !== null);
  if (!row) throw new Error(`The table has no row for ${id}.`);
  return row;
};

async function retype(user: UserEvent, field: HTMLElement, text: string): Promise<void> {
  await user.clear(field);
  if (text !== "") await user.type(field, text);
}

async function openEditor(user: UserEvent): Promise<HTMLElement> {
  await user.click(screen.getByTestId("customize-open"));
  return screen.findByTestId("customize-editor");
}

/** Robert, customized: JNJ removed, NVDA added at 5%, SPY at 15%, cash at 35%. Totals 100%. */
const CUSTOM_A: CustomPortfolio = {
  cash_weight: 0.35,
  positions: [
    { instrument_id: "XBB.TO", weight: 0.3 },
    { instrument_id: "SPY", weight: 0.15 },
    { instrument_id: "XIU.TO", weight: 0.1 },
    { instrument_id: "RY.TO", weight: 0.05 },
    { instrument_id: "NVDA", weight: 0.05 },
  ],
};

async function applyCustomA(user: UserEvent): Promise<void> {
  await openEditor(user);
  await user.click(screen.getByTestId("customize-remove-JNJ"));
  await user.selectOptions(screen.getByTestId("customize-add-select"), "NVDA");
  await user.click(screen.getByTestId("customize-add"));
  await user.type(weight("NVDA"), "5");
  await retype(user, weight("SPY"), "15");
  await retype(user, screen.getByTestId("customize-cash"), "35");
  expect(screen.getByTestId("customize-total")).toHaveTextContent("Total: 100.00%");
  await user.click(screen.getByTestId("customize-apply"));
  await waitFor(() => expect(screen.queryByTestId("customize-editor")).toBeNull());
}

async function start(options: { api?: ApiClient } = {}): Promise<UserEvent> {
  const user = userEvent.setup();
  renderApp(options);
  await screen.findByTestId("portfolio-table");
  return user;
}

const lastCheck = (check: ReturnType<typeof liveDouble>["check"]) => check.mock.calls.at(-1)?.[0] as CheckRequest;

describe("Customize this profile: the editor", () => {
  it("opens from stage 1 with the scenario's weights, cash, total and objective", async () => {
    const { api } = liveDouble();
    const user = await start({ api });
    expect(screen.queryByTestId("customized-badge")).toBeNull();
    const editor = await openEditor(user);
    expect(within(editor).getAllByTestId("customize-row").map((row) => row.getAttribute("data-instrument-id"))).toEqual(["XBB.TO", "SPY", "XIU.TO", "RY.TO", "JNJ"]);
    expect(weight("XBB.TO")).toHaveValue("30");
    expect(weight("SPY")).toHaveValue("20");
    expect(weight("JNJ")).toHaveValue("5");
    expect(screen.getByTestId("customize-cash")).toHaveValue("30");
    expect(screen.getByTestId("customize-total")).toHaveTextContent("Total: 100.00%");
    expect(screen.getByTestId("customize-objective")).toHaveValue(scenarioObjective.original_words);
    expect(screen.getByTestId("customize-apply")).not.toHaveAttribute("aria-disabled");
    expect(screen.queryByTestId("customize-error")).toBeNull();
  });

  it("refuses a total that is not 100%, says why next to the total, and applies nothing", async () => {
    const { api, check } = liveDouble();
    const user = await start({ api });
    await openEditor(user);
    await retype(user, weight("SPY"), "25");
    const total = screen.getByTestId("customize-total");
    expect(total).toHaveTextContent("Total: 105.00%");
    expect(total).toHaveTextContent(TOTAL_MESSAGE);
    expect(total).toHaveAttribute("role", "status");
    expect(screen.getByTestId("customize-apply")).toHaveAttribute("aria-disabled", "true");

    await user.click(screen.getByTestId("customize-apply"));
    const error = screen.getByTestId("customize-error");
    expect(error).toHaveAttribute("role", "alert");
    expect(error).toHaveTextContent(TOTAL_MESSAGE);
    // Still open, nothing applied: the table keeps the scenario's weight and nothing is labelled customized.
    expect(screen.getByTestId("customize-editor")).toBeInTheDocument();
    expect(rowWeight("SPY")).toHaveTextContent("20.0%");
    expect(screen.queryByTestId("customized-badge")).toBeNull();

    await retype(user, weight("SPY"), "15");
    expect(total).toHaveTextContent("Total: 95.00%");
    expect(total).toHaveTextContent(TOTAL_MESSAGE);
    expect(check).not.toHaveBeenCalled();
  });

  it("refuses a negative weight, a zero position and more than 2 decimals, with the message tied to the field", async () => {
    const { api } = liveDouble();
    const user = await start({ api });
    await openEditor(user);
    const spy = weight("SPY");

    const cases: [string, string][] = [
      ["-20", "Shorting is not supported"],
      ["0", "A position's weight must be above 0%"],
      ["20.123", "Use at most 2 decimals"],
      ["abc", "Enter a number such as 25 or 12.5."],
    ];
    for (const [text, message] of cases) {
      await retype(user, spy, text);
      expect(spy).toHaveAttribute("aria-invalid", "true");
      expect(spy).toHaveAccessibleDescription(expect.stringContaining(message));
      expect(screen.getByTestId("customize-error")).toHaveTextContent(message);
      expect(screen.getByTestId("customize-apply")).toHaveAttribute("aria-disabled", "true");
      await user.click(screen.getByTestId("customize-apply"));
      expect(screen.getByTestId("customize-editor")).toBeInTheDocument();
      expect(spy).toHaveFocus();
    }
    expect(screen.queryByTestId("customized-badge")).toBeNull();

    // Cash may be zero, never negative.
    await retype(user, spy, "20");
    await retype(user, screen.getByTestId("customize-cash"), "-30");
    expect(screen.getByTestId("customize-cash")).toHaveAccessibleDescription(expect.stringContaining("Shorting is not supported"));
  });

  it("offers only supported assets that are not already held: no duplicate row and no unsupported asset is possible", async () => {
    const { api } = liveDouble();
    const user = await start({ api });
    await openEditor(user);
    const select = screen.getByTestId("customize-add-select");
    const offered = () => within(select).getAllByRole("option").map((option) => (option as HTMLOptionElement).value).filter((value) => value !== "");
    // Robert holds five of the six purchasable instruments.
    expect(offered()).toEqual(["NVDA"]);
    expect(within(select).getByRole("option", { name: /^NVDA: / })).toHaveTextContent(robert.instruments.NVDA?.name ?? "missing");

    // Nothing chosen: the button explains nothing was added and adds no row.
    await user.click(screen.getByTestId("customize-add"));
    expect(screen.getAllByTestId("customize-row")).toHaveLength(5);

    await user.selectOptions(select, "NVDA");
    await user.click(screen.getByTestId("customize-add"));
    expect(screen.getAllByTestId("customize-row")).toHaveLength(6);
    expect(weight("NVDA")).toHaveFocus();
    expect(offered()).toEqual([]);

    await user.click(screen.getByTestId("customize-remove-SPY"));
    expect(screen.queryByTestId("customize-weight-SPY")).toBeNull();
    expect(offered()).toEqual(["SPY"]);
    for (const id of offered()) expect(robert.purchasable_instrument_ids).toContain(id);
  });

  it("needs an objective that is not empty and at most 2000 characters; Cancel changes nothing", async () => {
    const { api } = liveDouble();
    const user = await start({ api });
    await openEditor(user);
    const objective = screen.getByTestId("customize-objective");
    await user.clear(objective);
    expect(objective).toHaveAttribute("aria-invalid", "true");
    expect(objective).toHaveAccessibleDescription(expect.stringContaining("cannot be empty"));
    expect(screen.getByTestId("customize-apply")).toHaveAttribute("aria-disabled", "true");
    await user.click(objective);
    await user.paste("a".repeat(2001));
    expect(objective).toHaveAccessibleDescription(expect.stringContaining("at most 2000 characters"));

    await retype(user, weight("SPY"), "1");
    await user.click(screen.getByTestId("customize-cancel"));
    expect(screen.queryByTestId("customize-editor")).toBeNull();
    expect(screen.getByTestId("customize-open")).toHaveFocus();
    expect(rowWeight("SPY")).toHaveTextContent("20.0%");
    expect(screen.queryByTestId("customized-badge")).toBeNull();
  });
});

describe("Customize this profile: one portfolio is shown and sent", () => {
  it("after Apply the table shows the custom weights, and the next check and investigation carry exactly them", async () => {
    const { api, check, createInvestigation } = liveDouble();
    const user = await start({ api });
    await applyCustomA(user);

    // Stage 1: the table, the cash fact and the label.
    expect(rowWeight("SPY")).toHaveTextContent("15.0%");
    expect(rowWeight("NVDA")).toHaveTextContent("5.0%");
    expect(within(screen.getByTestId("portfolio-table")).queryByText("JNJ")).toBeNull();
    expect(within(screen.getByTestId("portfolio-table")).getAllByTestId("portfolio-row").at(-1)).toHaveTextContent("35.0%");
    expect(screen.getByText("Cash", { selector: "dt" }).nextElementSibling).toHaveTextContent("35.0% of the portfolio");
    expect(screen.getByTestId("customized-badge")).toHaveTextContent("Customized fictional portfolio");
    expect(screen.getByTestId("simulation-label")).toBeInTheDocument();
    expect(screen.getByTestId("customize-open")).toHaveFocus();

    // Stage 3: the summary of the starting portfolio, and the preview request.
    await confirmScenarioRules(user);
    await go("purchase");
    expect(screen.getByTestId("customized-badge")).toHaveTextContent("Customized fictional portfolio");
    expect(screen.getByTestId("held-now")).toHaveTextContent("Held directly now: 5.0%.");
    await waitFor(() => expect(check).toHaveBeenCalled());
    for (const [body] of check.mock.calls) expect(body.custom_portfolio).toEqual(CUSTOM_A);

    await user.click(screen.getByTestId("start-investigation"));
    const report = await screen.findByTestId("report");
    expect(createInvestigation).toHaveBeenCalledTimes(1);
    const sent = createInvestigation.mock.calls[0]?.[0] as InvestigationCreateRequest;
    expect(sent.custom_portfolio).toEqual(CUSTOM_A);
    expect(sent).toEqual({ ...FIXTURES.investigationAccepted.request, policy_id: sent.policy_id, custom_portfolio: CUSTOM_A });
    // The very same object in both requests: one value in the state feeds the check and the investigation.
    expect(sent.custom_portfolio).toBe(lastCheck(check).custom_portfolio);

    // The report names the portfolio the job stored.
    const block = within(report).getByTestId("report-portfolio");
    expect(block).not.toHaveAttribute("open");
    expect(within(block).getByTestId("report-portfolio-label")).toHaveTextContent("Customized fictional portfolio");
    expect(within(block).getByTestId("portfolio-table")).toHaveTextContent("15.0%");
  });

  it("sends no custom_portfolio member at all in the default flow, for Robert and for Mateo", async () => {
    for (const persona of ["robert", "mateo"] as const) {
      const fixtures = createFixturesClient({ latencyMs: 0 });
      const check = vi.fn(fixtures.check);
      const createInvestigation = vi.fn(fixtures.createInvestigation);
      const user = userEvent.setup();
      const view = renderApp({ api: { ...fixtures, mode: "live", check, createInvestigation } });
      await screen.findByTestId("portfolio-table");
      if (persona === "mateo") await chooseMateo(user);
      await confirmScenarioRules(user);
      // A draft preview in stage 2, the purchase preview in stage 3, then the investigation.
      const field = within(screen.getAllByTestId("policy-rule-card")[0] as HTMLElement).queryByRole("textbox");
      expect(field).toBeNull();
      await go("purchase");
      await waitFor(() => expect(check).toHaveBeenCalled());
      await runInvestigation(user);

      expect(createInvestigation).toHaveBeenCalledTimes(1);
      for (const [body] of [...check.mock.calls, ...createInvestigation.mock.calls]) {
        expect(body.persona_id).toBe(persona);
        expect("custom_portfolio" in body).toBe(false);
        expect(JSON.stringify(body)).not.toContain("custom_portfolio");
      }
      if (persona === "robert") {
        const sent = createInvestigation.mock.calls[0]?.[0] as InvestigationCreateRequest;
        expect(JSON.stringify(sent)).toBe(JSON.stringify({ ...FIXTURES.investigationAccepted.request, policy_id: sent.policy_id }));
      }
      view.unmount();
      window.location.hash = "";
    }
  });

  it("sends no custom_portfolio in a draft preview of the default flow, and the customized one after Apply", async () => {
    const { api, check } = liveDouble();
    const user = await start({ api });
    await go("goals");
    const card = (await screen.findAllByTestId("rule-card"))[0] as HTMLElement;
    const field = within(card).getByRole("textbox");
    await retype(user, field, "12");
    await waitFor(() => expect(check).toHaveBeenCalled());
    const earlier = check.mock.calls.length;
    for (const [body] of check.mock.calls) {
      expect(body.draft_rules).not.toBeNull();
      expect("custom_portfolio" in body).toBe(false);
    }

    await go("persona");
    await applyCustomA(user);
    await go("goals");
    const again = within((await screen.findAllByTestId("rule-card"))[0] as HTMLElement).getByRole("textbox");
    await retype(user, again, "13");
    await waitFor(() => expect(check.mock.calls.length).toBeGreaterThan(earlier));
    for (const [body] of check.mock.calls.slice(earlier)) {
      expect(body.draft_rules).not.toBeNull();
      expect(body.custom_portfolio).toEqual(CUSTOM_A);
    }
  });

  it("Reset restores the scenario weights and objective, and requests leave the member out again", async () => {
    const { api, check, createInvestigation } = liveDouble();
    const user = await start({ api });
    await openEditor(user);
    await retype(user, screen.getByTestId("customize-objective"), "Grow slowly and sleep well.");
    await retype(user, weight("SPY"), "15");
    await retype(user, screen.getByTestId("customize-cash"), "35");
    await user.click(screen.getByTestId("customize-apply"));
    expect(rowWeight("SPY")).toHaveTextContent("15.0%");
    expect(screen.getByTestId("customized-badge")).toBeInTheDocument();
    await go("goals");
    expect(screen.getByTestId("objective")).toHaveTextContent("Grow slowly and sleep well.");

    await go("persona");
    await user.click(screen.getByTestId("customize-reset"));
    expect(rowWeight("SPY")).toHaveTextContent("20.0%");
    expect(within(screen.getByTestId("portfolio-table")).getAllByTestId("portfolio-row").at(-1)).toHaveTextContent("30.0%");
    expect(screen.queryByTestId("customized-badge")).toBeNull();
    expect(screen.queryByTestId("customize-summary")).toBeNull();
    // The editor starts from the scenario again.
    await openEditor(user);
    expect(weight("SPY")).toHaveValue("20");
    expect(screen.getByTestId("customize-objective")).toHaveValue(scenarioObjective.original_words);
    await user.click(screen.getByTestId("customize-cancel"));

    await go("goals");
    expect(screen.getByTestId("objective")).toHaveTextContent(scenarioObjective.original_words);
    expect(screen.getByTestId("objective")).toHaveAttribute("data-objective-source", "FICTIONAL_SCENARIO");
    expect(screen.queryByTestId("objective-edited-note")).toBeNull();

    await confirmScenarioRules(user);
    await go("purchase");
    expect(screen.queryByTestId("customized-badge")).toBeNull();
    await waitFor(() => expect(check).toHaveBeenCalled());
    await runInvestigation(user);
    for (const [body] of [...check.mock.calls, ...createInvestigation.mock.calls]) expect("custom_portfolio" in body).toBe(false);
    expect(within(screen.getByTestId("report-portfolio")).getByTestId("report-portfolio-label")).toHaveTextContent("Robert’s original fictional portfolio");
  });

  it("typing the scenario's own weights back is the scenario portfolio: not labelled customized, nothing sent", async () => {
    const { api, check } = liveDouble();
    const user = await start({ api });
    await applyCustomA(user);
    await openEditor(user);
    await user.click(screen.getByTestId("customize-remove-NVDA"));
    await user.selectOptions(screen.getByTestId("customize-add-select"), "JNJ");
    await user.click(screen.getByTestId("customize-add"));
    await user.type(weight("JNJ"), "5.00");
    await retype(user, weight("SPY"), "20");
    await retype(user, screen.getByTestId("customize-cash"), "30");
    await user.click(screen.getByTestId("customize-apply"));
    expect(screen.queryByTestId("customized-badge")).toBeNull();
    await confirmScenarioRules(user);
    await go("purchase");
    await waitFor(() => expect(check).toHaveBeenCalled());
    expect("custom_portfolio" in lastCheck(check)).toBe(false);
  });

  it("recomputes the purchase preview for the new portfolio, and a retry after an edit never reuses a key with another body", async () => {
    const { api, check, createInvestigation } = liveDouble();
    // The first attempt never reaches the service: its key is kept for a retry of the same body.
    createInvestigation.mockRejectedValueOnce(new ApiError("network", "The service could not be reached. Nothing was changed."));
    const user = await start({ api });
    await confirmScenarioRules(user);
    await go("purchase");
    await waitFor(() => expect(check).toHaveBeenCalled());
    const earlier = check.mock.calls.length;
    for (const [body] of check.mock.calls) expect("custom_portfolio" in body).toBe(false);
    await user.click(screen.getByTestId("start-investigation"));
    await within(screen.getByRole("main")).findByRole("alert");

    await go("persona");
    await applyCustomA(user);
    await go("purchase");
    // The refusal of the earlier request is not shown for the new one, and the preview is asked again.
    expect(within(screen.getByRole("main")).queryByRole("alert")).toBeNull();
    await waitFor(() => expect(check.mock.calls.length).toBeGreaterThan(earlier));
    for (const [body] of check.mock.calls.slice(earlier)) expect(body.custom_portfolio).toEqual(CUSTOM_A);
    await waitFor(() => expect(screen.getByTestId("purchase-preview")).toHaveAttribute("data-preview-status", "ready"));

    await user.click(screen.getByTestId("start-investigation"));
    await screen.findByTestId("report");
    const [first, second] = createInvestigation.mock.calls;
    expect("custom_portfolio" in (first?.[0] ?? {})).toBe(false);
    expect(second?.[0].custom_portfolio).toEqual(CUSTOM_A);
    expect(second?.[1].idempotencyKey).not.toBe(first?.[1].idempotencyKey);
  });
});

describe("Customize this profile: the service is the authority", () => {
  it("shows a 400 from the service on a customized portfolio through the existing error display, and creates nothing", async () => {
    const { api, createInvestigation } = liveDouble();
    createInvestigation.mockRejectedValueOnce(
      new ApiError("validation", "The customized portfolio is not valid.", {
        status: 400,
        code: "VALIDATION_ERROR",
        details: [{ path: "custom_portfolio.positions[4].instrument_id", issue: "NVDA cannot be held by this persona" }],
      }),
    );
    const user = await start({ api });
    await applyCustomA(user);
    await confirmScenarioRules(user);
    await go("purchase");
    await user.click(screen.getByTestId("start-investigation"));
    const alert = await within(screen.getByRole("main")).findByRole("alert");
    expect(alert).toHaveTextContent("The investigation could not be started");
    expect(alert).toHaveTextContent("The customized portfolio is not valid.");
    expect(within(alert).getByTestId("start-issues")).toHaveTextContent("NVDA cannot be held by this persona");
    expect(within(alert).getByTestId("start-refused")).toBeInTheDocument();
    expect(window.location.hash).toBe("#/purchase");
    expect(screen.queryByTestId("report")).toBeNull();
  });
});

describe("Customize this profile: the objective", () => {
  it("changes only the objective: the proposed rules and their numbers are identical, nothing is interpreted or confirmed", async () => {
    const { api, confirmRules, interpretRules, check } = liveDouble();
    const user = await start({ api });
    const proposed = async () => {
      await go("goals");
      return (await screen.findAllByTestId("rule-card")).map((card) => ({
        id: card.getAttribute("data-rule-id"),
        origin: card.getAttribute("data-rule-origin"),
        number: (within(card).getByRole("textbox") as HTMLInputElement).value,
        heading: within(card).getByRole("heading").textContent,
      }));
    };
    const before = await proposed();
    expect(before.length).toBeGreaterThan(0);

    await go("persona");
    await openEditor(user);
    const words = "  Keep what I have, and grow a little.  ";
    await user.clear(screen.getByTestId("customize-objective"));
    await user.type(screen.getByTestId("customize-objective"), words);
    await user.click(screen.getByTestId("customize-apply"));
    // The portfolio was not touched: it is not a customized portfolio.
    expect(screen.queryByTestId("customized-badge")).toBeNull();
    expect(screen.getByTestId("objective-edited-summary")).toHaveTextContent("no rule was created, changed or confirmed");

    expect(await proposed()).toEqual(before);
    expect(screen.queryByTestId("policy-rule-card")).toBeNull();
    expect(interpretRules).not.toHaveBeenCalled();
    expect(confirmRules).not.toHaveBeenCalled();
    expect(check).not.toHaveBeenCalled();

    // Objectives, proposed rules and confirmed rules stay distinct things; the wording is marked as the user's.
    const objective = screen.getByTestId("objective");
    expect(objective).toHaveAttribute("data-objective-source", "USER_STATED");
    expect(objective).toHaveTextContent("Keep what I have, and grow a little.");
    expect(objective).toHaveTextContent("Stated by you");
    expect(within(objective).getByTestId("objective-edited-note")).toHaveTextContent(`The scenario said: “${scenarioObjective.original_words}”`);
    expect(screen.queryByTestId("objective-pending-note")).toBeNull();

    // Confirming is still explicit, and the request carries the user's wording verbatim with the scenario's rules and numbers.
    await user.click(screen.getByTestId("confirm-rules"));
    await screen.findAllByTestId("policy-rule-card");
    expect(confirmRules).toHaveBeenCalledTimes(1);
    const request = confirmRules.mock.calls[0]?.[0] as ConfirmRequest;
    expect(request.objectives).toEqual([{ objective_id: scenarioObjective.objective_id, kind: scenarioObjective.kind, original_words: words, source: "USER_STATED", case_reference: null }]);
    expect(request.confirmations).toEqual(robert.scenario.scenario_rules.map((rule) => ({ rule, threshold: rule.threshold })));
    expect(interpretRules).not.toHaveBeenCalled();
  });

  it("leaves a policy confirmed earlier exactly as it was, and says the wording is stored only if another rule is confirmed", async () => {
    const { api, confirmRules, interpretRules } = liveDouble();
    const user = await start({ api });
    await confirmScenarioRules(user);
    const confirmed = () => screen.getAllByTestId("policy-rule-card").map((card) => card.textContent);
    const before = confirmed();
    expect(confirmRules).toHaveBeenCalledTimes(1);

    await go("persona");
    await openEditor(user);
    await retype(user, screen.getByTestId("customize-objective"), "Only steady income matters to me.");
    await user.click(screen.getByTestId("customize-apply"));
    expect(screen.getByTestId("objective-pending-note")).toHaveTextContent("Policy version 1 is stored exactly as it was confirmed");
    // With every rule already confirmed there is nothing to confirm: the note must not promise that the wording will be stored.
    expect(screen.getByTestId("objective-pending-note")).toHaveTextContent("The new wording is stored only if you confirm another rule");
    expect(screen.getByTestId("objective-pending-note")).toHaveTextContent("Changing the number of a rule from a result keeps the stored wording");
    expect(screen.queryByText(/recorded with the next policy version you confirm/)).toBeNull();

    await go("goals");
    expect(confirmed()).toEqual(before);
    // The stored version still quotes the scenario's words next to its rules; the session's objective is the user's.
    expect(screen.getAllByTestId("policy-rule-card")[0]).toHaveTextContent(scenarioObjective.original_words);
    expect(screen.getByTestId("objective")).toHaveTextContent("Only steady income matters to me.");
    expect(screen.getByTestId("objective-pending-note")).toBeInTheDocument();
    expect(screen.queryByTestId("rule-card")).toBeNull();
    expect(confirmRules).toHaveBeenCalledTimes(1);
    expect(interpretRules).not.toHaveBeenCalled();

    // Reset puts the scenario objective back; the policy is still untouched.
    await go("persona");
    await user.click(screen.getByTestId("customize-reset"));
    await go("goals");
    expect(screen.getByTestId("objective")).toHaveTextContent(scenarioObjective.original_words);
    expect(screen.queryByTestId("objective-pending-note")).toBeNull();
    expect(confirmed()).toEqual(before);
    expect(confirmRules).toHaveBeenCalledTimes(1);
  });
});

describe("Customize this profile: reports keep their own portfolio", () => {
  it("a report keeps showing the portfolio stored with its job after the customization is changed and after it is reset", async () => {
    const { api } = liveDouble();
    const user = await start({ api });
    await applyCustomA(user);
    await confirmScenarioRules(user);
    await runInvestigation(user);
    const stored = () => {
      const block = screen.getByTestId("report-portfolio");
      return { id: block.getAttribute("data-portfolio-id"), label: within(block).getByTestId("report-portfolio-label").textContent, table: within(block).getByTestId("portfolio-table").textContent };
    };
    const first = stored();
    expect(first).toMatchObject({ id: CUSTOM_ID, label: "Customized fictional portfolio" });
    expect(first.table).toContain("15.0%");

    // Edit the customization again: stage 1 follows it, the report does not.
    await go("persona");
    await openEditor(user);
    await retype(user, weight("SPY"), "40");
    await retype(user, screen.getByTestId("customize-cash"), "10");
    await user.click(screen.getByTestId("customize-apply"));
    expect(rowWeight("SPY")).toHaveTextContent("40.0%");
    await go("verdict");
    expect(stored()).toEqual(first);
    // Policies and reports were not cleared by the edit.
    await go("goals");
    expect(screen.getAllByTestId("policy-rule-card").length).toBeGreaterThan(0);

    await go("persona");
    await user.click(screen.getByTestId("customize-reset"));
    expect(rowWeight("SPY")).toHaveTextContent("20.0%");
    await go("verdict");
    expect(stored()).toEqual(first);

    // The challenge stage names the same stored portfolio.
    await go("challenge");
    expect(screen.getByTestId("report-portfolio-label")).toHaveTextContent("Customized fictional portfolio");
  });

  it("shows no portfolio block for a job stored before jobs kept their portfolio", async () => {
    const fixtures = createFixturesClient({ latencyMs: 0 });
    const user = await start({ api: { ...fixtures, mode: "live" } });
    await confirmScenarioRules(user);
    const report = await runInvestigation(user);
    expect(within(report).queryByTestId("report-portfolio")).toBeNull();
  });
});

describe("Customize this profile: running a failed request again", () => {
  const sent = (createInvestigation: ReturnType<typeof liveDouble>["createInvestigation"], index: number) => createInvestigation.mock.calls[index]?.[0] as InvestigationCreateRequest;

  async function failOnce(user: UserEvent): Promise<void> {
    await confirmScenarioRules(user);
    await go("purchase");
    await user.click(screen.getByTestId("start-investigation"));
    await go("investigation");
    expect(await screen.findByText("The investigation failed", {}, { timeout: 5_000 })).toBeInTheDocument();
  }

  it("runs it on the portfolio stored with the failed job, not on the customization applied since", async () => {
    const { api, createInvestigation } = liveDouble({ simulate: "job-failed" });
    const user = await start({ api });
    await applyCustomA(user);
    await failOnce(user);
    expect(sent(createInvestigation, 0).custom_portfolio).toEqual(CUSTOM_A);

    // The user puts the scenario portfolio back, then asks for the SAME request again.
    await go("persona");
    await user.click(screen.getByTestId("customize-reset"));
    await go("investigation");
    await user.click(screen.getByRole("button", { name: "Run the same request again" }));
    await waitFor(() => expect(createInvestigation).toHaveBeenCalledTimes(2));
    expect(sent(createInvestigation, 1).custom_portfolio).toEqual(CUSTOM_A);
    expect(sent(createInvestigation, 1).request).toEqual(sent(createInvestigation, 0).request);
  });

  it("runs a failed request on the scenario portfolio again without the customization applied since", async () => {
    const { api, createInvestigation } = liveDouble({ simulate: "job-failed" });
    const user = await start({ api });
    await failOnce(user);
    expect(sent(createInvestigation, 0)).not.toHaveProperty("custom_portfolio");

    await go("persona");
    await applyCustomA(user);
    await go("investigation");
    await user.click(screen.getByRole("button", { name: "Run the same request again" }));
    await waitFor(() => expect(createInvestigation).toHaveBeenCalledTimes(2));
    expect(sent(createInvestigation, 1)).not.toHaveProperty("custom_portfolio");
  });
});

describe("Customize this profile: fixtures mode", () => {
  it("shows the control disabled, with the reason, and never opens the editor", async () => {
    const user = await start();
    const open = screen.getByTestId("customize-open");
    expect(open).toHaveAttribute("aria-disabled", "true");
    expect(open).toHaveAccessibleDescription("Customization needs the live service: the test data only replays results recorded for the original portfolio.");
    await user.click(open);
    expect(screen.queryByTestId("customize-editor")).toBeNull();
    expect(screen.queryByTestId("customized-badge")).toBeNull();
  });
});
