import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent, { type UserEvent } from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { ApiClient } from "@/lib/api";
import { createFixturesClient } from "@/lib/api/fixtures-client";
import type { RuntimeConfig, Timing } from "@/lib/config";
import { FIXTURE_SCENARIOS } from "@/lib/fixtures";
import { RuntimeProvider } from "@/state/runtime";
import { STAGES, type StageId } from "@/state/stage";
import { FAST_TIMING, FIXTURES_CONFIG, LIVE_CONFIG } from "@/test/render";
import { App, AppContent } from "./App";

function renderApp(options: { api?: ApiClient; timing?: Timing; config?: RuntimeConfig } = {}) {
  return render(
    <RuntimeProvider config={options.config ?? FIXTURES_CONFIG} api={options.api ?? createFixturesClient({ latencyMs: 0 })} timing={options.timing ?? FAST_TIMING}>
      <AppContent />
    </RuntimeProvider>,
  );
}

const stageHeading = () => screen.getByRole("heading", { level: 1 });

/** Moves to a stage the way the browser does: by changing the hash. */
async function go(stage: StageId) {
  const target = STAGES.find((candidate) => candidate.id === stage);
  act(() => {
    window.location.hash = `#/${stage}`;
  });
  await waitFor(() => expect(stageHeading()).toHaveTextContent(`Step ${target?.number} of 6: ${target?.title}`));
}

async function confirmScenarioRules(user: UserEvent) {
  await go("goals");
  await user.click(screen.getByTestId("propose-rules"));
  await screen.findAllByTestId("rule-card");
  await user.click(screen.getByTestId("confirm-all"));
  await screen.findAllByTestId("policy-rule-card");
}

async function runInvestigation(user: UserEvent) {
  await go("purchase");
  await user.click(screen.getByTestId("start-investigation"));
  await waitFor(() => expect(stageHeading()).toHaveTextContent("Investigation steps"));
  await user.click(await screen.findByTestId("see-verdict", {}, { timeout: 5_000 }));
  await screen.findByTestId("report");
}

async function robertToVerdict() {
  const user = userEvent.setup();
  renderApp();
  await screen.findByTestId("portfolio-table");
  await confirmScenarioRules(user);
  await runInvestigation(user);
  return user;
}

describe("App shell", () => {
  it("keeps the simulation label, the fixtures label and the valuation date on every stage", async () => {
    renderApp();
    await screen.findByTestId("portfolio-table");
    for (const stage of STAGES) {
      await go(stage.id);
      expect(screen.getByTestId("simulation-label")).toHaveTextContent("Simulation — fictional portfolio, not advice");
      expect(screen.getByTestId("fixtures-label")).toHaveTextContent("Test data — fixtures");
      expect(screen.getByTestId("valuation-date")).toHaveTextContent("Valuation date: 12 Nov 2026");
      expect(screen.getByRole("link", { current: "step" })).toHaveAccessibleName(`Step ${stage.number} of 6: ${stage.title}`);
    }
  });

  it("moves focus to the new stage's heading and sets the page title when the stage changes", async () => {
    renderApp();
    await screen.findByTestId("portfolio-table");
    // Arriving on the page does not steal focus.
    expect(stageHeading()).not.toHaveFocus();

    await go("goals");
    expect(stageHeading()).toHaveFocus();
    expect(document.title).toBe("Goals & rules — Before You Buy — fictional simulation");
  });

  it("has one main landmark, one banner notice and one h1", async () => {
    renderApp();
    await screen.findByTestId("portfolio-table");
    expect(screen.getAllByRole("main")).toHaveLength(1);
    expect(screen.getByRole("region", { name: "Simulation notice" })).toBeInTheDocument();
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getByRole("link", { name: "Skip to main content" })).toBeInTheDocument();
  });

  it("explains what each later stage needs instead of locking it", async () => {
    renderApp();
    await screen.findByTestId("portfolio-table");
    await go("investigation");
    expect(screen.getByText("No investigation has been started")).toBeInTheDocument();
    await go("verdict");
    expect(screen.getByText("There is no result yet")).toBeInTheDocument();
    await go("challenge");
    expect(screen.getByText("There is no report to challenge yet")).toBeInTheDocument();
    await go("purchase");
    expect(screen.getByTestId("start-investigation")).toHaveAttribute("aria-disabled", "true");
    expect(screen.getByText("Needs at least one confirmed rule.")).toBeInTheDocument();
  });

  it("marks Amira as coming after core and offers no way to select her", async () => {
    renderApp();
    await screen.findByTestId("portfolio-table");
    const amira = screen.getByTestId("persona-amira");
    expect(amira).toHaveTextContent("Coming after core");
    expect(within(amira).queryByRole("button")).toBeNull();
    expect(within(screen.getByTestId("persona-robert")).getByTestId("persona-selected")).toBeInTheDocument();
    expect(within(screen.getByTestId("persona-mateo")).getByRole("button", { name: "Use Mateo’s portfolio" })).toBeInTheDocument();
  });
});

describe("Robert: the six stages in fixtures mode", () => {
  it("goes from the portfolio to a verdict that states both failures with their evidence", async () => {
    const user = userEvent.setup();
    renderApp();

    // 1. Persona and portfolio.
    const table = await screen.findByTestId("portfolio-table");
    expect(table).toHaveTextContent("Cash (CAD)");
    expect(table).toHaveTextContent("100.0%");
    expect(screen.getByText("These holdings are invented")).toBeInTheDocument();

    // 2. Goal -> proposed rules -> explicit confirmation.
    await go("goals");
    expect(screen.getByText("No confirmed rule yet")).toBeInTheDocument();
    await user.click(screen.getByTestId("propose-rules"));
    const cards = await screen.findAllByTestId("rule-card");
    expect(cards).toHaveLength(2);
    for (const card of cards) expect(within(card).getByText("Proposed — inactive")).toBeInTheDocument();
    expect(screen.getAllByTestId("objective")).toHaveLength(1);

    await user.click(screen.getByTestId("confirm-all"));
    const confirmed = await screen.findAllByTestId("policy-rule-card");
    expect(confirmed).toHaveLength(2);
    expect(screen.getByRole("heading", { name: "Confirmed policy — version 1" })).toHaveFocus();
    expect(screen.queryAllByTestId("rule-card")).toHaveLength(0);

    // 3. The purchase as a final direct weight, with the funding stated.
    await go("purchase");
    expect(screen.getByLabelText("Final direct weight of this position")).toHaveValue("25");
    expect(screen.getByTestId("funding-statement")).toHaveTextContent("Funded from existing cash; all other positions unchanged; fees and taxes excluded.");
    expect(screen.getByTestId("cash-after")).toHaveTextContent("5.0%");
    const changed = within(screen.getByTestId("before-after-table"))
      .getAllByRole("row")
      .filter((row) => row.getAttribute("data-changed") === "true");
    expect(changed.map((row) => row.textContent)).toEqual([expect.stringContaining("NVDA"), expect.stringContaining("Cash (CAD)")]);

    // 4. Only the steps the job reported.
    await user.click(screen.getByTestId("start-investigation"));
    await waitFor(() => expect(stageHeading()).toHaveTextContent("Investigation steps"));
    await screen.findByTestId("see-verdict", {}, { timeout: 5_000 });
    const steps = screen.getAllByTestId("timeline-step");
    expect(steps.length).toBeGreaterThan(0);
    expect(screen.getByTestId("step-count")).toHaveTextContent(String(steps.length));
    expect(screen.queryByTestId("timeline-waiting")).toBeNull();
    expect(screen.getByText("Completed", { selector: "[data-job-status] *" })).toBeInTheDocument();

    // 5. Verdict and evidence.
    await user.click(screen.getByTestId("see-verdict"));
    const report = await screen.findByTestId("report");
    expect(within(report).getByTestId("verdict-headline")).toHaveTextContent("2 of 2 confirmed rules are not respected");
    expect(within(report).getByTestId("count-fail")).toHaveAttribute("data-count", "2");
    expect(within(report).getByTestId("count-unknown")).toHaveAttribute("data-count", "0");
    expect(within(report).getByTestId("count-pass")).toHaveAttribute("data-count", "0");
    expect(within(report).getByTestId("feasibility")).toHaveAttribute("data-feasibility", "FEASIBLE");
    expect(within(report).getByTestId("starting-clear")).toBeInTheDocument();
    expect(within(report).getAllByTestId("limit-marker").length).toBeGreaterThan(0);
    expect(within(report).getByTestId("scenario-panel")).toHaveTextContent("Replay of an assumed allocation through 2022 — not a forecast");
    expect(within(report).getByTestId("max-compliant")).toHaveAttribute("data-status", "SUPPORTED");
    expect(within(report).getByTestId("goal-context")).toBeInTheDocument();
    expect(within(report).getByTestId("data-coverage")).toBeInTheDocument();
  });

  it("opens the evidence of a figure in a drawer and returns focus to the figure's button when it closes", async () => {
    const user = await robertToVerdict();
    const opener = screen.getByRole("button", { name: "Evidence for Maximum exposure to a single company, after the purchase" });
    await user.click(opener);

    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveAccessibleName(/^Evidence: Maximum exposure to a single company/);
    const record = within(dialog).getAllByTestId("evidence-record")[0] as HTMLElement;
    for (const heading of ["Calculation path", "Assumptions", "Sources"]) {
      expect(within(record).getByRole("heading", { name: heading })).toBeInTheDocument();
    }
    for (const label of ["Subject", "Period", "Data coverage", "Policy version", "Calculation version"]) {
      expect(within(record).getByText(label)).toBeInTheDocument();
    }
    expect(within(record).getAllByText("Retrieved").length).toBeGreaterThan(0);
    // Focus is inside the drawer while it is open.
    expect(dialog.contains(document.activeElement)).toBe(true);

    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(opener).toHaveFocus();
  });

  it("never lets a draft preview replace the confirmed policy or the confirmed result", async () => {
    const fixtures = createFixturesClient({ latencyMs: 0 });
    const confirmRules = vi.fn(fixtures.confirmRules);
    const user = userEvent.setup();
    renderApp({ api: { ...fixtures, confirmRules } });
    await screen.findByTestId("portfolio-table");
    await confirmScenarioRules(user);
    await runInvestigation(user);
    expect(confirmRules).toHaveBeenCalledTimes(1);

    await go("challenge");
    await user.click(screen.getByRole("tab", { name: "Change a rule" }));
    const form = screen.getByTestId("change-rule-form");
    await user.type(within(form).getByRole("textbox"), "30");
    const preview = await within(form).findByTestId("draft-preview-result");
    expect(preview).toHaveTextContent("Preview: Pass");
    expect(within(form).getByTestId("draft-preview")).toHaveTextContent("Preview with draft threshold — not your confirmed policy");

    // Nothing was confirmed, and the report still says what it said.
    expect(confirmRules).toHaveBeenCalledTimes(1);
    expect(screen.queryByTestId("rule-change-comparison")).toBeNull();
    await go("verdict");
    expect(screen.getByTestId("verdict-headline")).toHaveTextContent("2 of 2 confirmed rules are not respected");
    expect(screen.getAllByTestId("rule-limit").map((node) => node.textContent)).toEqual(["10.0%", "10.0%"]);
    await go("goals");
    expect(screen.getByRole("heading", { name: "Confirmed policy — version 1" })).toBeInTheDocument();
    expect(screen.queryByTestId("earlier-versions")).toBeNull();
  });

  it("records a corrected fact as unverified, with the user as its source, beside the unchanged original", async () => {
    const user = await robertToVerdict();
    await go("challenge");
    const form = screen.getByTestId("correct-fact-form");
    const figure = within(form).getByLabelText("Which figure?");
    const firstOption = within(figure).getAllByRole("option")[1] as HTMLOptionElement;
    await user.selectOptions(figure, firstOption);
    const original = within(form).getByTestId("original-evidence").textContent;

    await user.type(within(form).getByLabelText("The value you believe is right"), "24%");
    await user.type(within(form).getByLabelText("Why, or where it comes from"), "Brokerage statement of 10 November.");
    await user.click(screen.getByTestId("submit-correction"));

    const card = await screen.findByTestId("correction-card");
    expect(card).toHaveTextContent("Proposed correction — unverified");
    expect(within(card).getByTestId("correction-proposed")).toHaveTextContent("24%");
    expect(card).toHaveTextContent("Asserted by you on");
    expect(card).toHaveTextContent("Not used in any calculation");
    // The original evidence is still on screen, unchanged.
    expect(within(form).getByTestId("original-evidence").textContent).toBe(original);
    expect(within(card).getByTestId("correction-original")).toHaveTextContent(firstOption.textContent?.split(" — ")[0] ?? "");

    await go("verdict");
    expect(screen.getByTestId("verdict-headline")).toHaveTextContent("2 of 2 confirmed rules are not respected");
  });

  it("turns a rule change into policy version 2, re-checks the purchase, and keeps the earlier report openable", async () => {
    const user = await robertToVerdict();
    await go("challenge");
    await user.click(screen.getByRole("tab", { name: "Change a rule" }));
    const form = screen.getByTestId("change-rule-form");
    expect(within(form).getByLabelText("Rule to change")).toHaveDisplayValue("Maximum exposure to a single company — now 10.0%");

    // Gated: no change without a different number.
    expect(screen.getByTestId("submit-rule-change")).toHaveAttribute("aria-disabled", "true");
    await user.type(within(form).getByRole("textbox"), "10");
    expect(within(form).getByText("This is the threshold already confirmed. Enter a different value to change the rule.")).toBeInTheDocument();
    await user.clear(within(form).getByRole("textbox"));
    await user.type(within(form).getByRole("textbox"), "30");
    await user.click(screen.getByTestId("submit-rule-change"));

    const comparison = await screen.findByTestId("rule-change-comparison");
    await waitFor(() => expect(screen.getByRole("heading", { name: "Before and after your rule change" })).toHaveFocus());

    // Policy v1 vs v2.
    const diffRows = within(comparison).getAllByTestId("policy-diff-row");
    const changed = diffRows.filter((row) => row.getAttribute("data-change") === "CHANGED");
    expect(changed).toHaveLength(1);
    expect(changed[0]).toHaveTextContent("Maximum exposure to a single company");
    expect(changed[0]).toHaveTextContent("10.0%");
    expect(changed[0]).toHaveTextContent("30.0%");
    expect(diffRows.filter((row) => row.getAttribute("data-change") === "UNCHANGED")).toHaveLength(1);

    // Result v1 vs v2, once the re-check has finished.
    await within(comparison).findByTestId("result-comparison", {}, { timeout: 5_000 });
    const headlines = within(comparison)
      .getAllByTestId("comparison-headline")
      .map((node) => node.textContent);
    expect(headlines).toEqual(["2 of 2 confirmed rules are not respected", "1 of 2 confirmed rules is not respected"]);

    // The earlier report is still there, unchanged.
    await user.click(within(comparison).getAllByRole("button", { name: "Open this report" })[0] as HTMLElement);
    await waitFor(() => expect(stageHeading()).toHaveTextContent("Verdict & evidence"));
    expect(screen.getByText("You are reading an earlier report, checked against policy version 1")).toBeInTheDocument();
    expect(screen.getByTestId("verdict-headline")).toHaveTextContent("2 of 2 confirmed rules are not respected");
    expect(screen.getAllByTestId("rule-limit").map((node) => node.textContent)).toEqual(["10.0%", "10.0%"]);
    expect(screen.getAllByTestId("report-entry")).toHaveLength(2);

    await user.click(screen.getByRole("button", { name: "Back to the latest" }));
    expect(screen.getByTestId("verdict-headline")).toHaveTextContent("1 of 2 confirmed rules is not respected");

    await go("goals");
    expect(screen.getByRole("heading", { name: "Confirmed policy — version 2" })).toBeInTheDocument();
    expect(screen.getByTestId("earlier-versions")).toHaveTextContent("Earlier versions (1)");
  });
});

describe("Mateo: a preference that needs a definition, and missing data", () => {
  it("asks instead of guessing, starts system-proposed thresholds empty, and never reports a pass over unknown data", async () => {
    const user = userEvent.setup();
    renderApp();
    await screen.findByTestId("portfolio-table");
    await user.click(screen.getByRole("button", { name: "Use Mateo’s portfolio" }));
    await waitFor(() => expect(screen.getByTestId("portfolio-table")).toHaveTextContent("Mateo’s fictional portfolio"));

    await go("goals");
    await user.click(screen.getByTestId("propose-rules"));

    // Ambiguous wording becomes a question, not a rule.
    const question = await screen.findByTestId("clarification-card");
    expect(within(question).getByText("No rule written yet")).toBeInTheDocument();
    expect(within(question).getAllByTestId("unsupported-option").length).toBeGreaterThan(0);
    const firstCards = screen.getAllByTestId("rule-card");
    expect(firstCards).toHaveLength(1);

    // The system-proposed rule has no number until the user gives one.
    const first = firstCards[0] as HTMLElement;
    expect(first).toHaveAttribute("data-rule-origin", "SYSTEM_PROPOSED");
    expect(within(first).getByRole("textbox")).toHaveValue("");
    expect(within(first).getByTestId("confirm-rule")).toHaveAttribute("aria-disabled", "true");

    await user.click(within(question).getAllByRole("radio")[0] as HTMLElement);
    await user.click(within(question).getByRole("button", { name: "Use this definition" }));
    await waitFor(() => expect(screen.getAllByTestId("rule-card")).toHaveLength(2));
    expect(screen.queryByTestId("clarification-card")).toBeNull();

    for (const card of screen.getAllByTestId("rule-card")) {
      expect(within(card).getByRole("textbox")).toHaveValue("");
      await user.type(within(card).getByRole("textbox"), "0");
    }
    await user.click(screen.getByTestId("confirm-all"));
    await screen.findAllByTestId("policy-rule-card");

    await runInvestigation(user);
    const report = screen.getByTestId("report");
    const unknown = Number(within(report).getByTestId("count-unknown").getAttribute("data-count"));
    const fail = Number(within(report).getByTestId("count-fail").getAttribute("data-count"));
    expect(unknown).toBeGreaterThan(0);
    // Whatever else it says, the headline is not one of the two "respected" headlines.
    expect(within(report).getByTestId("verdict-headline").textContent).not.toMatch(/^All \d+ confirmed rules are respected$|^The one confirmed rule is respected$/);
    expect(within(report).getByTestId("verdict-summary")).not.toHaveAttribute("data-tone", "pass");
    expect(fail + unknown).toBe(2);

    // Unknown is shown as unknown on its rule, with a range rather than a zero.
    const unknownRow = within(report)
      .getAllByTestId("rule-result")
      .find((row) => row.getAttribute("data-status") === "UNKNOWN") as HTMLElement;
    expect(unknownRow).toHaveTextContent("Unknown is not a pass.");
    expect(within(unknownRow).getByTestId("rule-measured").textContent).toMatch(/ to /);
    expect(within(unknownRow).getByTestId("rule-gap")).toHaveTextContent("Cannot be determined");

    // Missing holdings are visible in the coverage section and drawn as a possible range.
    expect(within(report).getByTestId("data-coverage")).not.toHaveAttribute("data-coverage-status", "COVERED");
    expect(report.querySelector('[data-seg="possible"]')).not.toBeNull();
    // No maximum is offered when it cannot be supported.
    expect(within(report).getByTestId("max-compliant")).not.toHaveAttribute("data-status", "SUPPORTED");
    expect(within(report).queryByTestId("max-final-weight")).toBeNull();
    // This scenario has no replay rule: the panel says so instead of showing a number.
    expect(within(report).getByText("No scenario budget was checked")).toBeInTheDocument();
  });
});

describe("failure states", () => {
  it("shows a failed portfolio load with a retry, and no figures", async () => {
    renderApp({ api: createFixturesClient({ latencyMs: 0, simulate: "portfolio-error" }) });
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("The portfolio could not be loaded");
    expect(within(alert).getByRole("button", { name: "Try again" })).toBeInTheDocument();
    expect(screen.queryByTestId("portfolio-table")).toBeNull();
    expect(screen.getByTestId("valuation-date")).toHaveTextContent("Valuation date: unavailable");
  });

  it("shows a failed job as failed, with no verdict", async () => {
    const user = userEvent.setup();
    renderApp({ api: createFixturesClient({ latencyMs: 0, simulate: "job-failed" }) });
    await screen.findByTestId("portfolio-table");
    await confirmScenarioRules(user);
    await go("purchase");
    await user.click(screen.getByTestId("start-investigation"));

    expect(await screen.findByText("The investigation failed", {}, { timeout: 5_000 })).toBeInTheDocument();
    expect(screen.queryByTestId("see-verdict")).toBeNull();
    await go("verdict");
    expect(screen.getByText("This investigation failed, so there is no verdict")).toBeInTheDocument();
    expect(screen.queryByTestId("report")).toBeNull();
    expect(screen.queryByTestId("verdict-headline")).toBeNull();
  });

  it("stops polling at the deadline and says no result was received", async () => {
    const user = userEvent.setup();
    renderApp({
      api: createFixturesClient({ latencyMs: 0, simulate: "poll-timeout" }),
      timing: { ...FAST_TIMING, pollDeadlineMs: 120 },
    });
    await screen.findByTestId("portfolio-table");
    await confirmScenarioRules(user);
    await go("purchase");
    await user.click(screen.getByTestId("start-investigation"));

    const alert = await screen.findByRole("alert", {}, { timeout: 5_000 });
    expect(alert).toHaveTextContent("No final answer within");
    expect(within(alert).getByRole("button", { name: "Keep waiting" })).toBeInTheDocument();
    expect(screen.queryByTestId("see-verdict")).toBeNull();
    await go("verdict");
    expect(screen.queryByTestId("report")).toBeNull();
    expect(screen.getByRole("alert")).toHaveTextContent("No verdict is shown, because none was received.");
  });
});

describe("live mode", () => {
  it("asks for the access code before any request, then sends it as a bearer token and keeps it in sessionStorage", async () => {
    const portfolio = FIXTURE_SCENARIOS.robert?.portfolio_response;
    const requests: { url: string; authorization: string | null }[] = [];
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const authorization = new Headers(init?.headers).get("Authorization");
      requests.push({ url: String(input), authorization });
      if (authorization !== "Bearer right-code") {
        return new Response(JSON.stringify({ error: { code: "UNAUTHORIZED", message: "Access code not accepted." } }), { status: 401, headers: { "Content-Type": "application/json" } });
      }
      return new Response(JSON.stringify(portfolio), { status: 200, headers: { "Content-Type": "application/json" } });
    });
    vi.stubGlobal("fetch", fetchMock);
    vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", LIVE_CONFIG.apiBaseUrl ?? "");
    const user = userEvent.setup();
    render(<App />);

    expect(await screen.findByRole("heading", { level: 1, name: "Enter the access code" })).toBeInTheDocument();
    expect(screen.queryByTestId("fixtures-label")).toBeNull();
    expect(screen.getByTestId("simulation-label")).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "Stages of the simulation" })).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();

    await user.type(screen.getByLabelText("Access code"), "wrong-code");
    await user.click(screen.getByRole("button", { name: "Continue" }));
    expect(await screen.findByText("The service did not accept this code. Check it and try again.")).toBeInTheDocument();
    expect(window.sessionStorage.getItem("byb.accessCode")).toBeNull();

    await user.clear(screen.getByLabelText("Access code"));
    await user.type(screen.getByLabelText("Access code"), "right-code");
    await user.click(screen.getByRole("button", { name: "Continue" }));

    await screen.findByTestId("portfolio-table");
    expect(window.sessionStorage.getItem("byb.accessCode")).toBe("right-code");
    expect(requests.every((request) => request.url.startsWith("https://api.example.test/"))).toBe(true);
    expect(requests.at(-1)).toEqual({ url: "https://api.example.test/portfolios/robert", authorization: "Bearer right-code" });
    // The code never travels in a URL.
    expect(requests.some((request) => request.url.includes("right-code") || request.url.includes("wrong-code"))).toBe(false);
  });
});
