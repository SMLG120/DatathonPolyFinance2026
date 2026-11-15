import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { storeAccessCode } from "@/lib/access-code";
import { ApiError } from "@/lib/api";
import { createFixturesClient } from "@/lib/api/fixtures-client";
import type { ApiClient } from "@/lib/api";
import { IDEMPOTENCY_KEY_PATTERN, type ChallengeResponse, type Interpretation, type Rule } from "@/lib/contracts";
import { FIXTURES } from "@/lib/fixtures";
import { STAGES } from "@/state/stage";
import { chooseMateo, confirmScenarioRules, go, renderApp, runInvestigation, stageHeading, toVerdict } from "@/test/app";
import { overviewChart } from "@/test/exposure";
import { probe, recorded } from "@/test/probes";
import { FAST_TIMING, LIVE_CONFIG } from "@/test/render";
import { App } from "./App";

const ROBERT_HEADLINE = "2 of 2 confirmed rules are not respected";
const AFTER_CHANGE_HEADLINE = "1 of 2 confirmed rules is not respected";

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

  it("shows the portfolio and the fiction notice exactly as the service sent them", async () => {
    renderApp();
    const table = await screen.findByTestId("portfolio-table");
    const { scenario } = recorded.robertPortfolio();
    expect(screen.getByTestId("fiction-notice")).toHaveTextContent(scenario.fiction_notice);
    // One row per recorded position, then cash.
    expect(within(table).getAllByTestId("portfolio-row")).toHaveLength(scenario.portfolio.positions.length + 1);
    expect(table).toHaveTextContent("Cash (CAD)");
    expect(table).toHaveTextContent("30.0%");
    expect(table.closest('[data-figures="true"]')).not.toBeNull();
  });
});

describe("Robert: the six stages in fixtures mode", () => {
  it("goes from the portfolio to a verdict that states both failures with their evidence", async () => {
    const user = userEvent.setup();
    renderApp();

    // 1. Persona and portfolio.
    await screen.findByTestId("portfolio-table");
    expect(screen.getByText("These holdings are invented")).toBeInTheDocument();

    // 2. The scenario's rules are offered as proposals; nothing is active until the user confirms.
    await go("goals");
    expect(screen.getByText("No confirmed rule yet")).toBeInTheDocument();
    const cards = await screen.findAllByTestId("rule-card");
    expect(cards.map((card) => card.getAttribute("data-rule-id"))).toEqual(["robert-issuer-cap-1", "robert-loss-budget-1"]);
    for (const card of cards) {
      expect(within(card).getByText("Proposed — inactive")).toBeInTheDocument();
      expect(card).toHaveAttribute("data-rule-origin", "FICTIONAL_SCENARIO");
      expect(within(card).getByRole("textbox")).toHaveValue("10");
    }
    expect(screen.getAllByTestId("objective")).toHaveLength(1);
    expect(screen.getByTestId("confirm-rules")).toHaveTextContent("Confirm these 2 rules with their numbers");

    await user.click(screen.getByTestId("confirm-rules"));
    const confirmed = await screen.findAllByTestId("policy-rule-card");
    expect(confirmed).toHaveLength(2);
    expect(screen.getByRole("heading", { name: "Confirmed policy — version 1" })).toHaveFocus();
    expect(screen.queryAllByTestId("rule-card")).toHaveLength(0);

    // 3. The purchase as a final direct weight, with the funding stated.
    await go("purchase");
    expect(screen.getByLabelText("Final direct weight of this position")).toHaveValue("25");
    expect(screen.getByTestId("funding-statement")).toHaveTextContent("Funded from existing cash; all other positions unchanged; fees and taxes excluded.");
    expect(screen.getByTestId("purchase-policy-rules")).toHaveTextContent("10.0%");

    // 4. Only the steps the job reported.
    await user.click(screen.getByTestId("start-investigation"));
    await waitFor(() => expect(stageHeading()).toHaveTextContent("Investigation steps"));
    await screen.findByTestId("see-verdict", {}, { timeout: 5_000 });
    const recordedSteps = recorded.robertJob().steps;
    const steps = screen.getAllByTestId("timeline-step");
    expect(steps).toHaveLength(recordedSteps.length);
    expect(screen.getByTestId("step-count")).toHaveTextContent(String(recordedSteps.length));
    expect(screen.queryByTestId("timeline-waiting")).toBeNull();
    expect(screen.getByText("Completed", { selector: "[data-job-status] *" })).toBeInTheDocument();
    expect(screen.getByTestId("agent-mode")).toHaveAttribute("data-agent-mode", "MODEL");

    // 5. Verdict and evidence.
    await user.click(screen.getByTestId("see-verdict"));
    const report = await screen.findByTestId("report");
    expect(report).toHaveAttribute("data-job-id", recorded.robertJob().id);
    expect(within(report).getByTestId("verdict-headline")).toHaveTextContent(ROBERT_HEADLINE);
    expect(within(report).getByTestId("count-fail")).toHaveAttribute("data-count", "2");
    expect(within(report).getByTestId("count-unknown")).toHaveAttribute("data-count", "0");
    expect(within(report).getByTestId("count-pass")).toHaveAttribute("data-count", "0");
    expect(within(report).getByTestId("feasibility")).toHaveAttribute("data-feasibility", "FEASIBLE");
    expect(within(report).getByTestId("starting-breaches")).toHaveAttribute("data-count", "0");
    expect(within(report).getAllByTestId("limit-marker").length).toBeGreaterThan(0);
    expect(within(report).getByTestId("scenario-note")).toHaveTextContent("not a forecast");
    expect(within(report).getByTestId("max-compliant")).toHaveAttribute("data-status", "SUPPORTED");
    expect(within(report).getByTestId("goal-context")).toBeInTheDocument();
    expect(within(report).getByTestId("data-coverage")).toBeInTheDocument();
    // The policy the result was checked against is known, so the limit is drawn as a confirmed one.
    expect(overviewChart(report)).toHaveTextContent("Confirmed limit 10.0%");
  });

  it("opens the evidence of a figure in a drawer, formula apart from its values, and returns focus to the figure's button when it closes", async () => {
    const user = await toVerdict();
    const opener = screen.getByRole("button", { name: "Evidence for Maximum exposure to a single company, after the purchase" });
    await user.click(opener);

    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveAccessibleName(/^Evidence: Maximum exposure to a single company/);
    const cap = recorded.robertResult().rule_results[0];
    const records = within(dialog).getAllByTestId("evidence-record");
    expect(records.map((record) => record.getAttribute("data-evidence-id"))).toEqual(cap?.evidence_ids);
    const first = records[0] as HTMLElement;
    for (const heading of ["How it was calculated", "Assumptions", "Sources"]) {
      expect(within(first).getByRole("heading", { name: heading })).toBeInTheDocument();
    }
    for (const label of ["Subject", "Date or period", "Policy version", "Calculation version"]) {
      expect(within(first).getByText(label)).toBeInTheDocument();
    }
    expect(within(first).getByTestId("evidence-formula")).toHaveTextContent("0.25 + 0.012 = 0.262");
    expect(within(first).getAllByTestId("evidence-input")).toHaveLength(2);
    expect(within(dialog).getByTestId("source-details-note")).toHaveTextContent("Only the ids of a figure’s sources are available here");
    // Focus is inside the drawer while it is open.
    expect(dialog.contains(document.activeElement)).toBe(true);

    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(opener).toHaveFocus();
  });

  it("takes a figure from the evidence drawer to “Correct a fact”, with that figure already chosen", async () => {
    const user = await toVerdict();
    await user.click(screen.getByRole("button", { name: "Evidence for Maximum exposure to a single company, after the purchase" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(within(dialog).getAllByTestId("evidence-record")[0] as HTMLElement).getByRole("link", { name: "Challenge this figure" }));

    await waitFor(() => expect(stageHeading()).toHaveTextContent("Challenge"));
    expect(screen.getByRole("tab", { name: "Correct a fact" })).toHaveAttribute("aria-selected", "true");
    expect(within(screen.getByTestId("correct-fact-form")).getByLabelText("Which figure?")).toHaveValue("ev-nvda-lower");
  });

  it("never lets a draft preview replace the confirmed policy or the confirmed result", async () => {
    const fixtures = createFixturesClient({ latencyMs: 0 });
    const confirmRules = vi.fn(fixtures.confirmRules);
    const challengeInvestigation = vi.fn(fixtures.challengeInvestigation);
    const user = await toVerdict({ api: { ...fixtures, confirmRules, challengeInvestigation } });
    expect(confirmRules).toHaveBeenCalledTimes(1);

    await go("challenge");
    // Robert's scenario challenge is a rule change, so that path is the one shown first.
    expect(screen.getByRole("tab", { name: "Change a rule" })).toHaveAttribute("aria-selected", "true");
    const form = screen.getByTestId("change-rule-form");
    await user.type(within(form).getByRole("textbox", { name: /^New value/ }), "20");
    const preview = await within(form).findByTestId("draft-preview-result");
    expect(preview).toHaveTextContent("Preview: Fail");
    expect(preview).toHaveTextContent("draft limit 20.0%");
    expect(within(preview).getByTestId("rule-gap")).toHaveTextContent("6.2 points over the limit");
    expect(within(form).getByTestId("draft-preview")).toHaveTextContent("Preview with draft threshold — not your confirmed policy");

    // Nothing was confirmed or challenged, and the report still says what it said.
    expect(confirmRules).toHaveBeenCalledTimes(1);
    expect(challengeInvestigation).not.toHaveBeenCalled();
    expect(screen.queryByTestId("rule-change-comparison")).toBeNull();
    await go("verdict");
    expect(screen.getByTestId("verdict-headline")).toHaveTextContent(ROBERT_HEADLINE);
    expect(screen.getAllByTestId("rule-limit").map((node) => node.textContent)).toEqual(["10.0%", "10.0%"]);
    await go("goals");
    expect(screen.getByRole("heading", { name: "Confirmed policy — version 1" })).toBeInTheDocument();
    expect(screen.queryByTestId("earlier-versions")).toBeNull();
  });

  it("records a corrected fact as unverified, with the user as its source, beside the unchanged original", async () => {
    const fixtures = createFixturesClient({ latencyMs: 0 });
    const challengeInvestigation = vi.fn(fixtures.challengeInvestigation);
    const user = await toVerdict({ api: { ...fixtures, challengeInvestigation } });
    await go("challenge");
    await user.click(screen.getByRole("tab", { name: "Correct a fact" }));
    const form = screen.getByTestId("correct-fact-form");

    // The recorded exchange: the weight of NVIDIA inside SPY, 6% on record, 8% asserted.
    const exchange = FIXTURES.challenges.correctFact;
    const correction = exchange.response.proposed_correction;
    if (!correction || exchange.request.type !== "CORRECT_FACT") throw new Error("The recording changed.");
    await user.selectOptions(within(form).getByLabelText("Which figure?"), correction.evidence_id);
    const original = within(form).getByTestId("original-evidence");
    expect(original).toHaveTextContent("6.00%");
    const originalText = original.textContent;

    await user.type(within(form).getByLabelText("The value you believe is right, in percent"), "8");
    await user.type(within(form).getByLabelText("Where your value comes from (optional)"), exchange.request.payload.user_source as string);
    await user.type(within(form).getByLabelText("Why you believe the recorded value is wrong"), exchange.request.payload.user_note);
    await user.click(screen.getByTestId("submit-correction"));

    const card = await screen.findByTestId("correction-card");
    // Exactly the recorded request was sent, and the card shows the recorded answer.
    expect(challengeInvestigation).toHaveBeenCalledTimes(1);
    expect(challengeInvestigation.mock.calls[0]?.[0]).toBe(recorded.robertJob().id);
    expect(challengeInvestigation.mock.calls[0]?.[1]).toEqual(exchange.request);
    expect(correction.status).toBe("UNVERIFIED");
    expect(correction.applied_to_calculation).toBe(false);
    expect(card).toHaveTextContent("Proposed correction — unverified");
    expect(within(card).getByTestId("correction-proposed")).toHaveTextContent("8.00%");
    expect(within(card).getByTestId("correction-original")).toHaveTextContent("6.00%");
    expect(card).toHaveTextContent("Asserted by the user on");
    expect(card).toHaveTextContent("No source has confirmed it");
    expect(card).toHaveTextContent("Not used in any calculation");
    expect(card).toHaveTextContent(correction.provenance.user_note);
    expect(screen.getByRole("heading", { name: "Proposed corrections to this report (1)" })).toHaveFocus();
    // The original evidence is still on screen, unchanged.
    expect(within(form).getByTestId("original-evidence").textContent).toBe(originalText);

    // The record's own evidence shows the claim beside the recorded value, never in its place.
    await user.click(within(card).getByRole("button", { name: /^Evidence for the recorded value of/ }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByTestId("evidence-value")).toHaveTextContent("6.00%");
    expect(within(within(dialog).getByTestId("proposed-correction")).getByTestId("correction-asserted")).toHaveTextContent("8.00%");
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());

    await go("verdict");
    expect(screen.getByTestId("verdict-headline")).toHaveTextContent(ROBERT_HEADLINE);
    // A correction creates no new report: there is still only the one, so no list of reports is shown.
    expect(screen.queryByTestId("report-list")).toBeNull();
  });

  it("turns a rule change into policy version 2, re-checks the purchase, and keeps the earlier report openable", async () => {
    const fixtures = createFixturesClient({ latencyMs: 0 });
    const challengeInvestigation = vi.fn(fixtures.challengeInvestigation);
    const user = await toVerdict({ api: { ...fixtures, challengeInvestigation } });
    await go("challenge");
    const form = screen.getByTestId("change-rule-form");
    expect(within(form).getByLabelText("Rule to change")).toHaveDisplayValue("Maximum exposure to a single company — now 10.0%");
    expect(within(form).getByTestId("current-threshold")).toHaveTextContent("Confirmed now: 10.0%");

    // Gated: no change without a different number.
    const field = within(form).getByRole("textbox", { name: /^New value/ });
    expect(screen.getByTestId("submit-rule-change")).toHaveAttribute("aria-disabled", "true");
    await user.type(field, "10");
    expect(within(form).getByText("This is the number already confirmed. Enter a different value to change the rule.")).toBeInTheDocument();
    await user.click(screen.getByTestId("submit-rule-change"));
    expect(challengeInvestigation).not.toHaveBeenCalled();

    // The scenario's own example: raise the limit to 30%. Only the 20% draft has a recorded preview.
    await user.click(within(form).getByTestId("fill-example-rule"));
    expect(field).toHaveValue("30");
    expect(await within(form).findByTestId("draft-preview-not-recorded")).toHaveTextContent("No preview for this draft value in the test data");
    await user.click(screen.getByTestId("submit-rule-change"));

    const comparison = await screen.findByTestId("rule-change-comparison");
    await waitFor(() => expect(screen.getByRole("heading", { level: 2, name: "Version comparison: before and after the rule change" })).toHaveFocus());
    // Exactly the recorded request was sent.
    expect(challengeInvestigation).toHaveBeenCalledTimes(1);
    expect(challengeInvestigation.mock.calls[0]?.[1]).toEqual(FIXTURES.challenges.changeRule.request);

    // Policy v1 against v2.
    const diffRows = within(comparison).getAllByTestId("policy-diff-row");
    const changed = diffRows.filter((row) => row.getAttribute("data-change") === "CHANGED");
    expect(changed).toHaveLength(1);
    expect(changed[0]).toHaveTextContent("Maximum exposure to a single company");
    expect(changed[0]).toHaveTextContent("10.0%");
    expect(changed[0]).toHaveTextContent("30.0%");
    expect(diffRows.filter((row) => row.getAttribute("data-change") === "UNCHANGED")).toHaveLength(1);

    // The result under each version, once the re-check has finished: the engine's headline and counts of each report.
    await within(comparison).findByTestId("result-comparison", {}, { timeout: 5_000 });
    expect(within(comparison).getAllByTestId("comparison-headline").map((node) => node.textContent)).toEqual([ROBERT_HEADLINE, AFTER_CHANGE_HEADLINE]);
    expect(within(comparison).getAllByTestId("comparison-counts").map((node) => node.textContent)).toEqual(["2 fail · 0 unknown · 0 pass", "1 fail · 0 unknown · 1 pass"]);
    const capRow = within(comparison)
      .getAllByTestId("result-comparison-row")
      .find((row) => row.getAttribute("data-change") === "CHANGED") as HTMLElement;
    expect([...capRow.querySelectorAll("[data-status]")].map((badge) => badge.getAttribute("data-status"))).toEqual(["FAIL", "PASS"]);

    // The earlier report is still there, unchanged.
    await user.click(within(comparison).getAllByRole("button", { name: "Open this report" })[0] as HTMLElement);
    await waitFor(() => expect(stageHeading()).toHaveTextContent("Verdict & evidence"));
    expect(screen.getByText("You are reading an earlier report, checked against policy version 1")).toBeInTheDocument();
    expect(screen.getByTestId("verdict-headline")).toHaveTextContent(ROBERT_HEADLINE);
    expect(screen.getAllByTestId("rule-limit").map((node) => node.textContent)).toEqual(["10.0%", "10.0%"]);
    expect(screen.getAllByTestId("report-entry")).toHaveLength(2);

    await user.click(screen.getByRole("button", { name: "Back to the latest" }));
    const latest = screen.getByTestId("report");
    expect(latest).toHaveAttribute("data-job-id", recorded.robertAfterChangeJob().id);
    expect(within(latest).getByTestId("verdict-headline")).toHaveTextContent(AFTER_CHANGE_HEADLINE);
    expect(within(latest).getAllByTestId("rule-limit").map((node) => node.textContent)).toEqual(["30.0%", "10.0%"]);
    // The superseded rule is listed as not evaluated, with the engine's reason.
    expect(within(latest).getByTestId("not-evaluated-count")).toHaveTextContent("1 rule of this policy version was not evaluated");
    expect(within(latest).getByTestId("rules-not-evaluated")).toHaveTextContent("Superseded by robert-issuer-cap-2");
    expect(within(latest).getByTestId("max-final-weight")).toHaveTextContent("10.0%");

    await go("goals");
    expect(screen.getByRole("heading", { name: "Confirmed policy — version 2" })).toBeInTheDocument();
    expect(screen.getByTestId("earlier-versions")).toHaveTextContent("Earlier versions (1)");
  });

  it("keeps the rule-change form and the version comparison apart: separate sections, each under its own heading", async () => {
    const user = await toVerdict();
    await go("challenge");
    await user.click(within(screen.getByTestId("change-rule-form")).getByTestId("fill-example-rule"));
    await user.click(screen.getByTestId("submit-rule-change"));
    const comparison = await screen.findByTestId("rule-change-comparison");
    await within(comparison).findByTestId("result-comparison", {}, { timeout: 5_000 });

    const forms = document.getElementById("challenge-forms") as HTMLElement;
    const section = screen.getByTestId("comparison-section");
    const form = screen.getByTestId("change-rule-form");
    // The form lives in the forms panel; the comparison lives outside it, after it.
    expect(forms.contains(form)).toBe(true);
    expect(forms.contains(comparison)).toBe(false);
    expect(section.contains(form)).toBe(false);
    expect(forms.compareDocumentPosition(section) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();

    // Each has its own level-2 heading, and the comparison says in words that it is not part of the form.
    expect(within(forms).getByRole("heading", { level: 2 })).toHaveTextContent("What do you want to challenge?");
    expect(within(form).getByRole("heading", { level: 3, name: "Change a rule" })).toBeInTheDocument();
    expect(within(section).getByRole("heading", { level: 2 })).toHaveTextContent("Version comparison: before and after the rule change");
    expect(section).toHaveTextContent("Outcome of the rule change — separate from the form above");
    expect(within(comparison).getAllByRole("heading", { level: 3 }).map((heading) => heading.textContent)).toEqual([
      "What changed in the policy",
      "The same purchase under each version",
      "Each rule under the two versions",
    ]);
    // The comparison's figures are marked as test data on their own blocks.
    for (const card of within(comparison).getAllByTestId("comparison-report")) {
      expect(within(card).getByTestId("test-data-tag")).toBeInTheDocument();
    }
  });
});

describe("Idempotency keys", () => {
  it("come from crypto.randomUUID, one per user action: a retry of the same action reuses its key, a new action gets a new one", async () => {
    const randomUUID = vi.spyOn(crypto, "randomUUID");
    const fixtures = createFixturesClient({ latencyMs: 0 });
    const createInvestigation = vi.fn(fixtures.createInvestigation);
    const challengeInvestigation = vi.fn(fixtures.challengeInvestigation);
    // The first attempt to start never reaches the service.
    createInvestigation.mockRejectedValueOnce(new ApiError("network", "The service could not be reached. Nothing was changed."));

    const user = userEvent.setup();
    renderApp({ api: { ...fixtures, createInvestigation, challengeInvestigation } });
    await screen.findByTestId("portfolio-table");
    await confirmScenarioRules(user);
    await go("purchase");
    await user.click(screen.getByTestId("start-investigation"));
    const alert = await within(screen.getByRole("main")).findByRole("alert");
    expect(alert).toHaveTextContent("The investigation could not be started");

    await user.click(within(alert).getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(stageHeading()).toHaveTextContent("Investigation steps"));
    await user.click(await screen.findByTestId("see-verdict", {}, { timeout: 5_000 }));
    await screen.findByTestId("report");

    const generated = () => randomUUID.mock.results.map((result) => result.value as string);
    const startKeys = createInvestigation.mock.calls.map((call) => call[1]?.idempotencyKey);
    expect(startKeys).toHaveLength(2);
    expect(startKeys[0]).toBe(startKeys[1]);
    expect(generated()).toContain(startKeys[0]);
    expect(startKeys[0]).toMatch(IDEMPOTENCY_KEY_PATTERN);
    // A UUID, not a counter or a timestamp.
    expect(startKeys[0]).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);

    // A rule change is a new action: its own key, again from crypto.randomUUID.
    await go("challenge");
    await user.click(within(screen.getByTestId("change-rule-form")).getByTestId("fill-example-rule"));
    await user.click(screen.getByTestId("submit-rule-change"));
    await screen.findByTestId("rule-change-comparison");
    const challengeKey = challengeInvestigation.mock.calls[0]?.[2]?.idempotencyKey;
    expect(challengeKey).toMatch(IDEMPOTENCY_KEY_PATTERN);
    expect(generated()).toContain(challengeKey);
    expect(challengeKey).not.toBe(startKeys[0]);

    // Starting the same request again is another new action.
    await screen.findByTestId("result-comparison", {}, { timeout: 5_000 });
    await go("purchase");
    await user.click(screen.getByTestId("start-investigation"));
    await waitFor(() => expect(createInvestigation).toHaveBeenCalledTimes(3));
    const again = createInvestigation.mock.calls[2]?.[1]?.idempotencyKey;
    expect(generated()).toContain(again);
    expect(again).not.toBe(startKeys[0]);
    expect(again).not.toBe(challengeKey);
  });
});

describe("Idempotency keys after a failure (finding F-03)", () => {
  const workerFailed = () => new ApiError("server", "The investigation worker could not be started.", { status: 503, code: "WORKER_INVOCATION_FAILED" });

  it("starts with a new key after 503 WORKER_INVOCATION_FAILED, and keeps the key after a 429", async () => {
    const fixtures = createFixturesClient({ latencyMs: 0 });
    const createInvestigation = vi.fn(fixtures.createInvestigation);
    createInvestigation
      .mockRejectedValueOnce(new ApiError("rate_limited", "The service is receiving too many requests. Wait a moment and try again.", { status: 429 }))
      .mockRejectedValueOnce(workerFailed());

    const user = userEvent.setup();
    renderApp({ api: { ...fixtures, createInvestigation } });
    await screen.findByTestId("portfolio-table");
    await confirmScenarioRules(user);
    await go("purchase");
    await user.click(screen.getByTestId("start-investigation"));
    const main = within(screen.getByRole("main"));
    expect(await main.findByRole("alert")).toHaveTextContent("The service is receiving too many requests.");

    // The same action again after a 429: the same key, so the service cannot start a second job.
    await user.click(within(main.getByRole("alert")).getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(main.getByRole("alert")).toHaveTextContent("The investigation worker could not be started."));
    expect(createInvestigation).toHaveBeenCalledTimes(2);

    // After the 503 the job stored under that key is FAILED: the retry needs a new key, or the 503 is replayed for ever.
    await user.click(within(main.getByRole("alert")).getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(stageHeading()).toHaveTextContent("Investigation steps"));
    const keys = createInvestigation.mock.calls.map((call) => call[1]?.idempotencyKey);
    expect(keys).toHaveLength(3);
    expect(keys[1]).toBe(keys[0]);
    expect(keys[2]).not.toBe(keys[1]);
    expect(keys[2]).toMatch(IDEMPOTENCY_KEY_PATTERN);
    // The three attempts carried the same request.
    expect(createInvestigation.mock.calls[2]?.[0]).toEqual(createInvestigation.mock.calls[0]?.[0]);
  });

  it("does the same for a rule change: the key is kept after a network error and replaced after the 503", async () => {
    const fixtures = createFixturesClient({ latencyMs: 0 });
    const challengeInvestigation = vi.fn(fixtures.challengeInvestigation);
    challengeInvestigation.mockRejectedValueOnce(new ApiError("network", "The service could not be reached. Check the connection and try again.")).mockRejectedValueOnce(workerFailed());
    const user = await toVerdict({ api: { ...fixtures, challengeInvestigation } });
    await go("challenge");
    await user.click(within(screen.getByTestId("change-rule-form")).getByTestId("fill-example-rule"));

    const main = within(screen.getByRole("main"));
    await user.click(screen.getByTestId("submit-rule-change"));
    expect(await main.findByRole("alert")).toHaveTextContent("The service could not be reached.");
    await user.click(screen.getByTestId("submit-rule-change"));
    await waitFor(() => expect(main.getByRole("alert")).toHaveTextContent("The investigation worker could not be started."));
    await user.click(screen.getByTestId("submit-rule-change"));
    await screen.findByTestId("rule-change-comparison");

    const keys = challengeInvestigation.mock.calls.map((call) => call[2]?.idempotencyKey);
    expect(keys).toHaveLength(3);
    expect(keys[1]).toBe(keys[0]);
    expect(keys[2]).not.toBe(keys[1]);
    expect(challengeInvestigation.mock.calls[2]?.[1]).toEqual(challengeInvestigation.mock.calls[0]?.[1]);
  });
});

describe("A policy version conflict (finding F-04)", () => {
  it("sets the policy it held aside and starts the rule stage again: nothing in force, every rule a proposal, no retry that can only fail", async () => {
    const fixtures = createFixturesClient({ latencyMs: 0 });
    const confirmRules = vi.fn(fixtures.confirmRules);
    const conflict = FIXTURES.errors.policyVersionConflict;
    // The recorded job stands in for an investigation under a version 1 that holds one rule (the test data records none).
    const createInvestigation = vi.fn(async () => FIXTURES.investigationAccepted.response);
    const getInvestigation = vi.fn(async () => recorded.robertJob());
    const user = userEvent.setup();
    renderApp({ api: { ...fixtures, confirmRules, createInvestigation, getInvestigation } });
    await screen.findByTestId("portfolio-table");

    // Version 1 with the first rule only; then a report under it.
    await go("goals");
    const offered = await screen.findAllByTestId("rule-card");
    await user.clear(within(offered[1] as HTMLElement).getByRole("textbox"));
    await user.click(screen.getByTestId("confirm-rules"));
    expect(await screen.findAllByTestId("policy-rule-card")).toHaveLength(1);
    const versionOne = (await confirmRules.mock.results[0]?.value)?.policy;
    const report = await runInvestigation(user);
    const jobId = report.getAttribute("data-job-id");

    // The service now holds a newer version than this page does, and says so with the recorded 409.
    confirmRules.mockRejectedValueOnce(new ApiError("validation", conflict.response.error.message, { status: conflict.status, code: conflict.response.error.code }));
    await go("goals");
    await user.type(within(screen.getByTestId("rule-card")).getByRole("textbox"), "12");
    await user.click(screen.getByTestId("confirm-rules"));

    const alert = await within(screen.getByRole("main")).findByRole("alert");
    expect(conflict.status).toBe(409);
    expect(confirmRules.mock.calls[1]?.[0]).toMatchObject({ policy_id: versionOne?.policy_id, base_version: 1 });
    expect(alert).toHaveTextContent("The rules could not be confirmed");
    expect(alert).toHaveTextContent(conflict.response.error.message);
    expect(within(alert).getByTestId("policy-conflict")).toHaveTextContent("this stage starts again");
    // The same request would be refused again, so it is not offered.
    expect(within(alert).queryByRole("button")).toBeNull();

    // The stale version is no longer presented as the policy in force.
    expect(screen.queryAllByTestId("policy-rule-card")).toHaveLength(0);
    expect(screen.getByText("No confirmed rule yet")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /^Confirmed policy — version/ })).toBeNull();
    // Every rule is a proposal again: the one being confirmed keeps the number typed, the scenario's other rule is offered again.
    const proposals = screen.getAllByTestId("rule-card");
    expect(proposals.map((card) => card.getAttribute("data-rule-id"))).toEqual(["robert-loss-budget-1", "robert-issuer-cap-1"]);
    expect(proposals.map((card) => (within(card).getByRole("textbox") as HTMLInputElement).value)).toEqual(["12", "10"]);
    for (const card of proposals) expect(within(card).getByText("Proposed — inactive")).toBeInTheDocument();

    // Nothing can be checked until a rule is confirmed again.
    await go("purchase");
    expect(screen.getByTestId("start-investigation")).toHaveAttribute("aria-disabled", "true");
    expect(screen.getByText("Needs at least one confirmed rule.")).toBeInTheDocument();
    // The report made under version 1 is still the report it was, with the version it was checked against.
    await go("verdict");
    expect(screen.getByTestId("report")).toHaveAttribute("data-job-id", jobId);
    expect(screen.getByTestId("report")).toHaveTextContent("confirmed policy version 1");
    expect(overviewChart(screen.getByTestId("report"))).toHaveTextContent("Confirmed limit 10.0%");

    // Confirming again creates a new policy: no policy id, no base version.
    await go("goals");
    await user.click(screen.getByTestId("confirm-rules"));
    expect(await screen.findAllByTestId("policy-rule-card")).toHaveLength(2);
    expect(confirmRules).toHaveBeenCalledTimes(3);
    expect(confirmRules.mock.calls[2]?.[0]).toMatchObject({ policy_id: null, base_version: null });
    expect(within(screen.getByRole("main")).queryByRole("alert")).toBeNull();
  });

  it("keeps offering a retry for any other refusal of a confirmation", async () => {
    const fixtures = createFixturesClient({ latencyMs: 0 });
    const confirmRules = vi.fn(fixtures.confirmRules);
    confirmRules.mockRejectedValueOnce(new ApiError("server", "The service reported an internal error. Nothing was changed.", { status: 500 }));
    const user = userEvent.setup();
    renderApp({ api: { ...fixtures, confirmRules } });
    await screen.findByTestId("portfolio-table");
    await go("goals");
    await screen.findAllByTestId("rule-card");
    await user.click(screen.getByTestId("confirm-rules"));
    const alert = await within(screen.getByRole("main")).findByRole("alert");
    expect(within(alert).queryByTestId("policy-conflict")).toBeNull();
    expect(screen.getAllByTestId("rule-card")).toHaveLength(2);
    await user.click(within(alert).getByRole("button", { name: "Try again" }));
    expect(await screen.findAllByTestId("policy-rule-card")).toHaveLength(2);
  });
});

describe("Polling through failed status requests (finding F-02)", () => {
  it("keeps asking through more than three failed polls in a row and shows the report when the job finishes", async () => {
    const fixtures = createFixturesClient({ latencyMs: 0 });
    let polls = 0;
    const getInvestigation = vi.fn(async (...args: Parameters<typeof fixtures.getInvestigation>) => {
      polls += 1;
      // The first poll answers; the next five are throttled by the gateway; then the service answers again.
      if (polls >= 2 && polls <= 6) throw new ApiError("rate_limited", "The service is receiving too many requests. Wait a moment and try again.", { status: 429 });
      return fixtures.getInvestigation(...args);
    });
    const user = userEvent.setup();
    renderApp({ api: { ...fixtures, getInvestigation } });
    await screen.findByTestId("portfolio-table");
    await confirmScenarioRules(user);
    const report = await runInvestigation(user);

    expect(report).toHaveAttribute("data-job-id", recorded.robertJob().id);
    expect(polls).toBeGreaterThan(6);
    expect(within(screen.getByRole("main")).queryByText("The status of the investigation could not be fetched")).toBeNull();
  });

  it("says so while a failed status request is being retried, and stops with the last failure at the time limit", async () => {
    const fixtures = createFixturesClient({ latencyMs: 0 });
    const getInvestigation = vi.fn(async () => {
      throw new ApiError("network", "The service could not be reached. Check the connection and try again.");
    });
    const user = userEvent.setup();
    renderApp({ api: { ...fixtures, getInvestigation }, timing: { ...FAST_TIMING, pollDeadlineMs: 400 } });
    await screen.findByTestId("portfolio-table");
    await confirmScenarioRules(user);
    await go("purchase");
    await user.click(screen.getByTestId("start-investigation"));

    expect(await screen.findByTestId("polling-retrying")).toHaveTextContent("The service could not be reached.");
    const alert = await within(screen.getByRole("main")).findByRole("alert", {}, { timeout: 5_000 });
    expect(alert).toHaveTextContent("No final answer within");
    expect(within(alert).getByTestId("polling-last-error")).toHaveTextContent("The service could not be reached.");
    expect(within(alert).getByRole("button", { name: "Keep waiting" })).toBeInTheDocument();
    expect(getInvestigation.mock.calls.length).toBeGreaterThan(3);
    expect(screen.queryByTestId("polling-retrying")).toBeNull();
    expect(screen.queryByTestId("see-verdict")).toBeNull();
  });
});

describe("A result whose check did not run", () => {
  it("shows the execution state and never a verdict, even when rule results arrive with it", async () => {
    const fixtures = createFixturesClient({ latencyMs: 0 });
    // The recorded job, rule results and all, with the execution block of the recorded invalid request.
    const notExecuted = probe.notExecutedWithRuleResults();
    await toVerdictWithoutReport({
      ...fixtures,
      getInvestigation: async (...args) => {
        const job = await fixtures.getInvestigation(...args);
        return job.status === "SUCCEEDED" ? structuredClone(notExecuted) : job;
      },
    });

    const shown = await screen.findByTestId("report-not-executed");
    const state = within(shown).getByTestId("execution-state");
    expect(state).toHaveAttribute("data-execution-status", "INVALID_REQUEST");
    expect(within(state).getByTestId("execution-message")).toHaveTextContent(recorded.invalidRequest().execution.message as string);
    expect(state).toHaveTextContent("No rule was evaluated, so there is no verdict to show.");

    // Nothing of the result is drawn: no report, no headline, no counts, no pass/fail/unknown badge anywhere in the stage.
    const main = screen.getByRole("main");
    expect(screen.queryByTestId("report")).toBeNull();
    expect(screen.queryByTestId("verdict-summary")).toBeNull();
    expect(screen.queryByTestId("rule-result")).toBeNull();
    expect(main.querySelector("[data-status]")).toBeNull();
    expect(main.querySelector("[data-tone]")).toBeNull();
    for (const word of ["not respected", "are respected", "is respected"]) expect(main).not.toHaveTextContent(word);

    // It cannot be challenged either: there is no report whose checks ran.
    await go("challenge");
    expect(screen.getByText("There is no report to challenge yet")).toBeInTheDocument();
  });

  it("says a result it cannot read is unreadable, and shows no part of it", async () => {
    const fixtures = createFixturesClient({ latencyMs: 0 });
    await toVerdictWithoutReport({
      ...fixtures,
      getInvestigation: async (...args) => {
        const job = await fixtures.getInvestigation(...args);
        // A result object that is not the agreed shape.
        return job.status === "SUCCEEDED" ? ({ ...job, result: { verdict: "PASS" } } as unknown as typeof job) : job;
      },
    });
    expect(await screen.findByTestId("result-unreadable")).toHaveTextContent("not in the agreed format");
    expect(screen.queryByTestId("report")).toBeNull();
    expect(screen.getByRole("main").querySelector("[data-status]")).toBeNull();
  });
});

/** From the first screen to the verdict stage, for a job whose result is not a report. */
async function toVerdictWithoutReport(api: ReturnType<typeof createFixturesClient>) {
  const user = userEvent.setup();
  renderApp({ api });
  await screen.findByTestId("portfolio-table");
  await confirmScenarioRules(user);
  await go("purchase");
  await user.click(screen.getByTestId("start-investigation"));
  await waitFor(() => expect(stageHeading()).toHaveTextContent("Investigation steps"));
  await user.click(await screen.findByTestId("see-verdict", {}, { timeout: 5_000 }));
  await waitFor(() => expect(stageHeading()).toHaveTextContent("Verdict & evidence"));
  return user;
}

describe("Mateo: a preference that needs a definition, and missing data", () => {
  it("asks instead of guessing, lists no check twice, and reports two failures with what was already failing kept apart", async () => {
    const user = userEvent.setup();
    renderApp();
    await screen.findByTestId("portfolio-table");
    await chooseMateo(user);

    await go("goals");
    const cards = await screen.findAllByTestId("rule-card");
    expect(cards.map((card) => card.getAttribute("data-rule-id"))).toEqual(["mateo-excl-energy-1", "mateo-controversy-1"]);
    for (const card of cards) expect(within(card).getByRole("textbox")).toHaveValue("0");

    // His own sentence: ambiguous wording becomes a question, not a rule.
    await user.click(screen.getByTestId("use-scenario-sentence"));
    await user.click(screen.getByTestId("interpret-words"));
    const interpretation = await screen.findByTestId("interpretation");
    const answer = FIXTURES.interpret.mateo.response;
    const question = within(interpretation).getByTestId("clarification-card");
    expect(question).toHaveTextContent(answer.clarifications[0]?.question as string);
    expect(within(question).getByText("No rule written yet")).toBeInTheDocument();
    expect(within(question).getAllByTestId("unsupported-option").length).toBeGreaterThan(0);
    // The drafted controversy rule measures what a listed rule already measures: said so, not listed twice.
    expect(within(interpretation).getByTestId("drafted-rule")).toHaveTextContent("Already listed under “Proposed rules” below");
    expect(screen.getAllByTestId("rule-card")).toHaveLength(2);

    await user.click(within(question).getAllByRole("radio")[0] as HTMLElement);
    await user.click(within(question).getByTestId("choose-definition"));
    expect(await within(question).findByTestId("clarification-outcome")).toHaveTextContent("Already listed under “Proposed rules” below");
    expect(screen.getAllByTestId("rule-card")).toHaveLength(2);

    await user.click(screen.getByTestId("confirm-rules"));
    expect(await screen.findAllByTestId("policy-rule-card")).toHaveLength(2);
    expect(screen.getAllByTestId("policy-rule-threshold").map((node) => node.textContent)).toEqual(["0.0%", "0.0%"]);

    const report = await runInvestigation(user);
    expect(report).toHaveAttribute("data-job-id", recorded.mateoJob().id);
    expect(within(report).getByTestId("verdict-headline")).toHaveTextContent("2 of 2 confirmed rules are not respected");
    expect(within(report).getByTestId("verdict-summary")).toHaveAttribute("data-tone", "fail");
    expect(within(report).getByTestId("count-fail")).toHaveAttribute("data-count", "2");
    expect(within(report).getByTestId("starting-breaches")).toHaveAttribute("data-count", "2");
    expect(within(report).getAllByTestId("starting-finding")).toHaveLength(2);
    expect(within(report).getAllByTestId("purchase-effect").every((effect) => effect.getAttribute("data-resolved") === "false")).toBe(true);
    // No maximum is offered, and no replay figure: the scenario has no replay rule.
    expect(within(report).getByTestId("max-compliant")).toHaveAttribute("data-status", "NO_FEASIBLE_PURCHASE");
    expect(within(report).queryByTestId("max-final-weight")).toBeNull();
    expect(within(report).queryByTestId("scenario-table")).toBeNull();
    // Missing holdings are visible in the coverage section and drawn as a possible range.
    expect(within(report).getAllByTestId("fund-coverage").map((fund) => fund.getAttribute("data-coverage-status"))).toContain("MISSING");
    expect(report.querySelector('[data-seg="possible"]')).not.toBeNull();
    // Exclusion rules set no limit on every company, so the chart draws no limit line.
    expect(within(report).queryAllByTestId("limit-marker")).toHaveLength(0);
  });

  it("records a clarified preference as a draft and changes neither the confirmed policy nor the report", async () => {
    const fixtures = createFixturesClient({ latencyMs: 0 });
    const challengeInvestigation = vi.fn(fixtures.challengeInvestigation);
    const confirmRules = vi.fn(fixtures.confirmRules);
    const user = await toVerdict({ persona: "mateo", api: { ...fixtures, challengeInvestigation, confirmRules } });
    await go("challenge");
    // Mateo's scenario challenge is a clarification, so that path is the one shown first.
    expect(screen.getByRole("tab", { name: "Clarify a preference" })).toHaveAttribute("aria-selected", "true");
    await user.click(screen.getByTestId("fill-example-preference"));
    await user.click(screen.getByTestId("submit-preference"));

    const response = await screen.findByTestId("preference-response");
    const exchange = FIXTURES.challenges.clarifyPreference;
    expect(challengeInvestigation.mock.calls[0]?.[1]).toEqual(exchange.request);
    expect(response).toHaveTextContent("Your clarification was read. No rule was changed.");
    const unsupported = exchange.response.interpretation?.unsupported[0];
    expect(within(response).getByTestId("unsupported-request")).toHaveTextContent(unsupported?.reason as string);
    expect(within(response).getByTestId("clarification-card")).toHaveTextContent(exchange.response.interpretation?.clarifications[0]?.question as string);

    // Nothing was confirmed, no comparison was made, and the report is the same one.
    expect(confirmRules).toHaveBeenCalledTimes(1);
    expect(screen.queryByTestId("rule-change-comparison")).toBeNull();
    await go("verdict");
    expect(screen.getByTestId("report")).toHaveAttribute("data-job-id", recorded.mateoJob().id);
    await go("goals");
    expect(screen.getByRole("heading", { name: "Confirmed policy — version 1" })).toBeInTheDocument();
  });
});

/**
 * The interpreter of the service numbers what it writes from 1 in every answer: its first question is
 * always `clar-1`, its drafts `draft-<kind>-<n>`, its objectives `obj-<n>`. So the answer to "interpret my
 * words" and the answer to a later "clarify a preference" hold a question and a draft with the same ids.
 * These answers are the contract's recorded ones with only that changed, together with what else differs
 * in what the service sends: the words in question are the investor's own word ("oil"), `created_at` has
 * milliseconds, and the clarified preference offers four readings, not two.
 */
const asTheServiceNumbers = {
  rule: (rule: Rule, ruleId: string): Rule => ({ ...rule, rule_id: ruleId, original_words: "oil" }),
  interpretation(): Interpretation {
    const answer = structuredClone(FIXTURES.interpret.mateo.response);
    return {
      ...answer,
      interpretation_id: "int-0a1b2c3d4e5f",
      created_at: "2026-11-14T15:10:00.123Z",
      clarifications: answer.clarifications.map((clarification, index) => ({
        ...clarification,
        clarification_id: `clar-${index + 1}`,
        about_words: "oil",
        options: clarification.options.map((option) => (option.proposed_rule ? { ...option, proposed_rule: this.rule(option.proposed_rule, "draft-excl-1") } : option)),
      })),
      proposed_rules: answer.proposed_rules.map((rule) => ({ ...rule, rule_id: "draft-controversy-2" })),
    };
  },
  clarifiedPreference(): ChallengeResponse {
    const exchange = structuredClone(FIXTURES.challenges.clarifyPreference.response);
    const notCheckable = FIXTURES.interpret.mateo.response.clarifications.flatMap((clarification) => clarification.options.filter((option) => !option.supported));
    if (!exchange.interpretation) throw new Error("The recording changed: no interpretation in the answer to the clarified preference.");
    return {
      ...exchange,
      interpretation: {
        ...exchange.interpretation,
        interpretation_id: "int-9f8e7d6c5b4a",
        created_at: "2026-11-14T15:16:00.456Z",
        clarifications: exchange.interpretation.clarifications.map((clarification, index) => ({
          ...clarification,
          clarification_id: `clar-${index + 1}`,
          about_words: "oil",
          options: [
            ...clarification.options.map((option) => (option.proposed_rule ? { ...option, proposed_rule: this.rule(option.proposed_rule, "draft-excl-1") } : option)),
            ...structuredClone(notCheckable),
          ],
        })),
      },
    };
  },
};

describe("Answers of the interpreter that share ids: it numbers from 1 in every answer", () => {
  it("Mateo's “oil”: the question of a clarified preference is not answered by the choice made in Goals & rules, and neither changes the other", async () => {
    const first = asTheServiceNumbers.interpretation();
    const second = asTheServiceNumbers.clarifiedPreference();
    // What the test relies on: both answers hold a question `clar-1` whose first reading leads to a draft `draft-excl-1`.
    expect(first.clarifications.map((clarification) => clarification.clarification_id)).toEqual(["clar-1"]);
    expect(second.interpretation?.clarifications.map((clarification) => clarification.clarification_id)).toEqual(["clar-1"]);
    expect(second.interpretation?.clarifications[0]?.options).toHaveLength(4);

    const fixtures = createFixturesClient({ latencyMs: 0 });
    const interpretRules = vi.fn<ApiClient["interpretRules"]>().mockResolvedValue(first);
    const challengeInvestigation = vi.fn<ApiClient["challengeInvestigation"]>().mockResolvedValue(second);
    const user = userEvent.setup();
    renderApp({ api: { ...fixtures, interpretRules, challengeInvestigation } });
    await screen.findByTestId("portfolio-table");
    await chooseMateo(user);

    // Goals & rules: the question about "oil", in the investor's own word, with the readings that cannot be checked.
    await go("goals");
    await screen.findAllByTestId("rule-card");
    await user.click(screen.getByTestId("use-scenario-sentence"));
    await user.click(screen.getByTestId("interpret-words"));
    const asked = within(await screen.findByTestId("interpretation")).getByTestId("clarification-card");
    expect(asked).toHaveTextContent(first.clarifications[0]?.question as string);
    expect(within(asked).getByRole("blockquote")).toHaveTextContent("“oil”");
    expect(within(asked).getAllByRole("radio")).toHaveLength(2);
    expect(within(asked).getAllByTestId("unsupported-option")).toHaveLength(2);
    // The first reading (the Energy label) is chosen: its rule is the one the scenario already offers.
    await user.click(within(asked).getAllByRole("radio")[0] as HTMLElement);
    await user.click(within(asked).getByTestId("choose-definition"));
    expect(await within(asked).findByTestId("clarification-outcome")).toHaveTextContent("Already listed under “Proposed rules” below");
    expect(within(asked).getByText("Definition chosen")).toBeInTheDocument();
    expect(screen.getAllByTestId("rule-card")).toHaveLength(2);

    await user.click(screen.getByTestId("confirm-rules"));
    expect(await screen.findAllByTestId("policy-rule-card")).toHaveLength(2);
    await runInvestigation(user);

    // Challenge: the clarified preference comes back with its own question `clar-1`. Nothing in it is answered yet.
    await go("challenge");
    await user.click(screen.getByTestId("fill-example-preference"));
    await user.click(screen.getByTestId("submit-preference"));
    const again = within(await screen.findByTestId("preference-response")).getByTestId("clarification-card");
    expect(again).toHaveTextContent(second.interpretation?.clarifications[0]?.question as string);
    expect(within(again).getByText("No rule written yet")).toBeInTheDocument();
    expect(within(again).queryByText("Definition chosen")).toBeNull();
    expect(within(again).queryByTestId("clarification-outcome")).toBeNull();
    expect(within(again).getAllByRole("radio").filter((radio) => (radio as HTMLInputElement).checked)).toHaveLength(0);
    expect(within(again).getAllByRole("radio")).toHaveLength(2);
    expect(within(again).getAllByTestId("unsupported-option")).toHaveLength(2);

    // Here the other reading is chosen (named companies: no rule comes with it).
    const named = second.interpretation?.clarifications[0]?.options[1];
    expect(named?.proposed_rule).toBeNull();
    await user.click(within(again).getAllByRole("radio")[1] as HTMLElement);
    await user.click(within(again).getByTestId("choose-definition"));
    expect(await within(again).findByTestId("clarification-outcome")).toHaveTextContent(`Recorded. ${named?.description}`);

    // The question in Goals & rules still has the answer given there, and only that one.
    await go("goals");
    const stillAsked = within(screen.getByTestId("interpretation")).getByTestId("clarification-card");
    expect(within(stillAsked).getByText("Definition chosen")).toBeInTheDocument();
    expect(within(stillAsked).getByTestId("clarification-outcome")).toHaveTextContent("Already in force in policy version 1");
    expect(within(stillAsked).getByTestId("clarification-outcome")).not.toHaveTextContent("Recorded.");
    expect(screen.getByRole("heading", { name: "Confirmed policy — version 1" })).toBeInTheDocument();
  });

  it("lists two different rules that arrive under one id as two rules, each with the objective of its own answer, and confirms them under different ids", async () => {
    const energy = FIXTURES.interpret.mateo.response.clarifications.flatMap((clarification) => clarification.options).find((option) => option.proposed_rule)?.proposed_rule;
    if (!energy) throw new Error("The recording changed: no reading of “oil” leads to a rule.");
    const parameters = energy.parameters as { definition: { kind: "fund_reported_sector"; sector: string } };
    const answer = (interpretationId: string, words: string, sector: string): Interpretation => ({
      ...structuredClone(FIXTURES.interpret.mateo.response),
      interpretation_id: interpretationId,
      created_at: "2026-11-14T15:10:00.123Z",
      original_words: words,
      objectives: [{ objective_id: "obj-1", original_words: words, kind: "constraint", source: "USER_STATED", case_reference: null }],
      proposed_rules: [
        {
          ...structuredClone(energy),
          rule_id: "draft-excl-1",
          original_words: words,
          objective_id: "obj-1",
          parameters: { ...parameters, definition: { ...parameters.definition, sector } },
        } as Rule,
      ],
      clarifications: [],
      unsupported: [],
    });
    const fixtures = createFixturesClient({ latencyMs: 0 });
    const interpretRules = vi
      .fn<ApiClient["interpretRules"]>()
      .mockResolvedValueOnce(answer("int-aaaaaaaaaaaa", "Nothing labelled Energy.", parameters.definition.sector))
      .mockResolvedValueOnce(answer("int-bbbbbbbbbbbb", "Nothing labelled Utilities either.", "Utilities"));
    const confirmRules = vi.fn(fixtures.confirmRules);
    const user = userEvent.setup();
    renderApp({ api: { ...fixtures, interpretRules, confirmRules } });
    await screen.findByTestId("portfolio-table");
    await go("goals");
    await screen.findAllByTestId("rule-card");
    const ruleIds = () => screen.getAllByTestId("rule-card").map((card) => card.getAttribute("data-rule-id"));
    const scenarioIds = ruleIds();

    const words = screen.getByLabelText("What should the portfolio respect?");
    await user.type(words, "Nothing labelled Energy.");
    await user.click(screen.getByTestId("interpret-words"));
    await waitFor(() => expect(ruleIds()).toEqual([...scenarioIds, "draft-excl-1"]));
    await user.clear(words);
    await user.type(words, "Nothing labelled Utilities either.");
    await user.click(screen.getByTestId("interpret-words"));
    // The second answer's rule has the first one's id and is another rule: it is listed too, under an id of its own.
    await waitFor(() => expect(ruleIds()).toEqual([...scenarioIds, "draft-excl-1", "draft-excl-1-2"]));
    expect(within(screen.getByTestId("interpretation")).getByTestId("drafted-rule")).toHaveTextContent("Already listed under “Proposed rules” below");

    // Each rule shows the objective of the answer it came from, though both answers call theirs `obj-1`.
    const [, , first, second] = screen.getAllByTestId("rule-card") as [HTMLElement, HTMLElement, HTMLElement, HTMLElement];
    expect(first).toHaveTextContent("“Nothing labelled Energy.”");
    expect(first).not.toHaveTextContent("Utilities");
    expect(second).toHaveTextContent("“Nothing labelled Utilities either.”");
    expect(second).toHaveTextContent("Utilities");
    expect(screen.getAllByTestId("objective").map((objective) => objective.querySelector("blockquote")?.textContent)).toEqual(
      expect.arrayContaining(["“Nothing labelled Energy.”", "“Nothing labelled Utilities either.”"]),
    );

    // Both get a number and are confirmed together: the request names no id twice, and each rule names an objective it carries.
    await user.type(within(first).getByRole("textbox"), "0");
    await user.type(within(second).getByRole("textbox"), "0");
    await user.click(screen.getByTestId("confirm-rules"));
    await waitFor(() => expect(screen.getAllByTestId("policy-rule-card")).toHaveLength(scenarioIds.length + 2));
    const request = confirmRules.mock.calls[0]?.[0];
    if (!request) throw new Error("No confirmation was sent.");
    const sentIds = request.confirmations.map((confirmation) => confirmation.rule.rule_id);
    expect(sentIds).toEqual([...scenarioIds, "draft-excl-1", "draft-excl-1-2"]);
    expect(new Set(sentIds).size).toBe(sentIds.length);
    const objectiveWords = (ruleId: string) => {
      const rule = request.confirmations.find((confirmation) => confirmation.rule.rule_id === ruleId)?.rule;
      return request.objectives.find((objective) => objective.objective_id === rule?.objective_id)?.original_words;
    };
    expect(objectiveWords("draft-excl-1")).toBe("Nothing labelled Energy.");
    expect(objectiveWords("draft-excl-1-2")).toBe("Nothing labelled Utilities either.");
    expect(new Set(request.objectives.map((objective) => objective.objective_id)).size).toBe(request.objectives.length);
  });
});

describe("Requests the test data holds no answer for", () => {
  it("says so calmly when a different purchase is started, and creates no investigation", async () => {
    const user = userEvent.setup();
    renderApp();
    await screen.findByTestId("portfolio-table");
    await confirmScenarioRules(user);
    await go("purchase");
    await user.clear(screen.getByLabelText("Final direct weight of this position"));
    await user.type(screen.getByLabelText("Final direct weight of this position"), "12");
    await user.click(screen.getByTestId("start-investigation"));

    const note = await screen.findByTestId("start-not-recorded");
    expect(note).toHaveTextContent("NVDA at a final direct weight of 12.0%");
    expect(screen.getByText("The test data holds no investigation of this request")).toBeInTheDocument();
    expect(screen.getByText("No investigation was created.")).toBeInTheDocument();
    expect(stageHeading()).toHaveTextContent("Proposed purchase");
    await go("verdict");
    expect(screen.getByText("There is no result yet")).toBeInTheDocument();
  });

  it("says so when words other than the recorded sentence are interpreted, and keeps the offered rules", async () => {
    const user = userEvent.setup();
    renderApp();
    await screen.findByTestId("portfolio-table");
    await go("goals");
    await screen.findAllByTestId("rule-card");
    await user.type(screen.getByLabelText("What should the portfolio respect?"), "No more than 5% in any one company.");
    await user.click(screen.getByTestId("interpret-words"));
    expect(await screen.findByTestId("interpret-not-recorded")).toHaveTextContent("The test data holds no recorded interpretation for this persona");
    expect(screen.queryByTestId("interpretation")).toBeNull();
    expect(screen.getAllByTestId("rule-card")).toHaveLength(2);
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

  it("shows a failed job as failed, with the service's reason and no verdict", async () => {
    const user = userEvent.setup();
    renderApp({ api: createFixturesClient({ latencyMs: 0, simulate: "job-failed" }) });
    await screen.findByTestId("portfolio-table");
    await confirmScenarioRules(user);
    await go("purchase");
    await user.click(screen.getByTestId("start-investigation"));

    const failure = recorded.failedJob().failure;
    expect(await screen.findByText("The investigation failed", {}, { timeout: 5_000 })).toBeInTheDocument();
    expect(screen.getByRole("main")).toHaveTextContent(failure?.message as string);
    expect(screen.getAllByTestId("timeline-step").map((step) => step.getAttribute("data-step-status"))).toEqual(["OK", "ERROR"]);
    expect(screen.queryByTestId("see-verdict")).toBeNull();
    await go("verdict");
    expect(screen.getByText("This investigation failed, so there is no verdict")).toBeInTheDocument();
    expect(screen.getByTestId("failure-code")).toHaveTextContent(failure?.code as string);
    expect(screen.getByTestId("failure-code")).toHaveTextContent("A failed run is not a pass and not a fail.");
    expect(screen.queryByTestId("report")).toBeNull();
    expect(screen.queryByTestId("verdict-headline")).toBeNull();
    expect(screen.getByRole("main").querySelector("[data-status]")).toBeNull();
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

    const alert = await within(screen.getByRole("main")).findByRole("alert", {}, { timeout: 5_000 });
    expect(alert).toHaveTextContent("No final answer within");
    expect(within(alert).getByRole("button", { name: "Keep waiting" })).toBeInTheDocument();
    expect(screen.queryByTestId("see-verdict")).toBeNull();
    await go("verdict");
    expect(screen.queryByTestId("report")).toBeNull();
    expect(within(screen.getByRole("main")).getByRole("alert")).toHaveTextContent("No verdict is shown, because none was received.");
  });
});

describe("live mode", () => {
  it("asks for the access code before any request, then sends it as a bearer token and keeps it in sessionStorage", async () => {
    const portfolio = recorded.robertPortfolio();
    const unauthorized = FIXTURES.errors.unauthorized;
    const requests: { url: string; authorization: string | null }[] = [];
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const authorization = new Headers(init?.headers).get("Authorization");
      requests.push({ url: String(input), authorization });
      if (authorization !== "Bearer right-code") {
        return new Response(JSON.stringify(unauthorized.response), { status: unauthorized.status, headers: { "Content-Type": "application/json" } });
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
    expect(window.localStorage.length).toBe(0);
    expect(requests.every((request) => request.url.startsWith("https://api.example.test/"))).toBe(true);
    expect(requests.at(-1)).toEqual({ url: "https://api.example.test/portfolios/robert", authorization: "Bearer right-code" });
    // The code never travels in a URL.
    expect(requests.some((request) => request.url.includes("right-code") || request.url.includes("wrong-code"))).toBe(false);
  });

  it("after a code is refused mid-session and a new one accepted, says what happened and lets the refused request be made again (finding F-05)", async () => {
    const portfolios = { robert: recorded.robertPortfolio(), mateo: await createFixturesClient({ latencyMs: 0 }).getPortfolio("mateo") };
    let accepted = "first-code";
    const requests: { url: string; authorization: string | null; status: number }[] = [];
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const authorization = new Headers(init?.headers).get("Authorization");
      const persona = String(input).endsWith("/portfolios/mateo") ? "mateo" : "robert";
      const ok = authorization === `Bearer ${accepted}`;
      requests.push({ url: String(input), authorization, status: ok ? 200 : 403 });
      // The gateway's own refusal, as the deployed stage sends it: not the contract's error shape.
      return new Response(JSON.stringify(ok ? portfolios[persona] : { message: "Forbidden" }), { status: ok ? 200 : 403, headers: { "Content-Type": "application/json" } });
    });
    vi.stubGlobal("fetch", fetchMock);
    vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", LIVE_CONFIG.apiBaseUrl ?? "");
    storeAccessCode("first-code");
    const user = userEvent.setup();
    render(<App />);
    await screen.findByTestId("portfolio-table");

    // The code is replaced on the service while the tab is open; the next request is refused.
    accepted = "second-code";
    await user.click(screen.getByRole("button", { name: "Use Mateo’s portfolio" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Enter the access code" })).toBeInTheDocument();
    expect(screen.getByText("The service no longer accepts the code that was in use")).toBeInTheDocument();
    expect(window.sessionStorage.getItem("byb.accessCode")).toBeNull();
    expect(requests.at(-1)).toEqual({ url: "https://api.example.test/portfolios/mateo", authorization: "Bearer first-code", status: 403 });

    await user.type(screen.getByLabelText("Access code"), "second-code");
    await user.click(screen.getByRole("button", { name: "Continue" }));

    // Back where the refused request was made: what happened, in the page's own words, and a way to make it again.
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("The portfolio could not be loaded");
    expect(alert).toHaveTextContent("The service refused the access code that was in use when this was requested.");
    expect(alert).toHaveTextContent("A code has been accepted since, so it can be requested again.");
    expect(alert).not.toHaveTextContent("Forbidden");
    expect(screen.queryByTestId("portfolio-table")).toBeNull();

    await user.click(within(alert).getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(screen.getByTestId("portfolio-table")).toHaveTextContent("Mateo’s fictional portfolio"));
    expect(requests.at(-1)).toEqual({ url: "https://api.example.test/portfolios/mateo", authorization: "Bearer second-code", status: 200 });
    expect(screen.queryByRole("alert")).toBeNull();
    expect(window.sessionStorage.getItem("byb.accessCode")).toBe("second-code");
  });

  it("shows no “Test data” marker and no fixtures label on any stage when the answers come from a service", async () => {
    // Live mode with a code already entered; the recorded bodies stand in for the service's answers.
    storeAccessCode("a-code-typed-by-the-user");
    await toVerdict({ config: LIVE_CONFIG });
    for (const stage of STAGES) {
      await go(stage.id);
      expect(screen.queryAllByTestId("test-data-tag"), stage.id).toHaveLength(0);
      expect(screen.queryByTestId("fixtures-label"), stage.id).toBeNull();
      expect(screen.getByTestId("simulation-label")).toBeInTheDocument();
    }
  });

  it("marks every block of figures as test data on every stage in fixtures mode", async () => {
    await toVerdict();
    for (const stage of STAGES) {
      await go(stage.id);
      const blocks = [...screen.getByRole("main").querySelectorAll('[data-figures="true"]')];
      expect(blocks.length, stage.id).toBeGreaterThan(0);
      for (const block of blocks) {
        expect(within(block as HTMLElement).queryAllByTestId("test-data-tag").length, `${stage.id}: ${block.id || block.getAttribute("data-testid") || block.tagName}`).toBeGreaterThan(0);
      }
    }
  });
});
