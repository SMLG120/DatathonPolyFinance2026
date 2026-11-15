import { screen, waitFor, within } from "@testing-library/react";
import userEvent, { type UserEvent } from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { PURCHASE_PREVIEW_LABEL } from "@/components/stages/PurchaseStage";
import { storeAccessCode } from "@/lib/access-code";
import type { ApiClient } from "@/lib/api";
import { ApiError } from "@/lib/api/errors";
import { createFixturesClient } from "@/lib/api/fixtures-client";
import type { CheckResult } from "@/lib/contracts";
import { confirmScenarioRules, go, renderApp } from "@/test/app";
import { probe, recorded, SENTINEL } from "@/test/probes";
import { LIVE_CONFIG } from "@/test/render";

const TARGET_LABEL = "Share of the portfolio after buying";

async function toPurchase(options: { api?: ApiClient; confirm?: boolean; live?: boolean } = {}): Promise<UserEvent> {
  const user = userEvent.setup();
  renderApp({ api: options.api, config: options.live ? LIVE_CONFIG : undefined });
  await screen.findByTestId("portfolio-table");
  if (options.confirm !== false) await confirmScenarioRules(user);
  await go("purchase");
  return user;
}

const preview = () => screen.getByTestId("purchase-preview");
const ready = () => waitFor(() => expect(preview()).toHaveAttribute("data-preview-status", "ready"));

describe("Purchase stage, before any answer from the service", () => {
  it("shows the target the user entered and says the other figures appear after the check", async () => {
    await toPurchase({ confirm: false });
    expect(screen.getByLabelText(TARGET_LABEL)).toHaveValue("25");
    expect(screen.getByTestId("start-investigation")).toHaveTextContent("Check my idea");
    expect(screen.getByTestId("held-now")).toHaveTextContent("Held directly now: nothing.");
    expect(screen.getByRole("link", { name: "Set my limits" })).toBeVisible();
    expect(screen.getByTestId("funding-statement")).toHaveTextContent("Funded from existing cash; all other positions unchanged; fees and taxes excluded.");
  });

  it("works out no cash figure and no amount added of its own: without a confirmed policy there is nothing to ask the service, so none is shown", async () => {
    const fixtures = createFixturesClient({ latencyMs: 0 });
    const check = vi.fn(fixtures.check);
    await toPurchase({ api: { ...fixtures, check }, confirm: false });
    expect(preview()).toHaveTextContent("No preview without a confirmed policy");
    expect(screen.queryByTestId("feasibility-table")).toBeNull();
    expect(screen.queryByTestId("cash-after")).toBeNull();
    expect(screen.queryByTestId("additional-purchase")).toBeNull();
    expect(screen.queryByTestId("purchase-preview-label")).toBeNull();
    expect(check).not.toHaveBeenCalled();
    // The portfolio holds 30.0% cash and the request is 25.0%: the difference appears nowhere on the page.
    expect(screen.getByRole("main").textContent).not.toMatch(/(?<![\d.])5\.0%/);
  });

  it("keeps showing the entered target, and nothing else, while the form changes", async () => {
    const user = await toPurchase({ confirm: false });
    await user.clear(screen.getByLabelText(TARGET_LABEL));
    await user.type(screen.getByLabelText(TARGET_LABEL), "12.5");
    expect(screen.getByLabelText(TARGET_LABEL)).toHaveValue("12.5");
    expect(screen.queryByTestId("cash-after")).toBeNull();
  });
});

describe("Purchase stage, the preview", () => {
  it("is asked from POST /check for the request in the form, on the stored policy, and is labelled a preview", async () => {
    const fixtures = createFixturesClient({ latencyMs: 0 });
    const check = vi.fn(fixtures.check);
    await toPurchase({ api: { ...fixtures, check } });
    await ready();

    const policy = recorded.robertPolicyV1();
    expect(check).toHaveBeenCalled();
    expect(check.mock.calls.at(-1)?.[0]).toEqual({
      persona_id: "robert",
      policy_id: policy.policy_id,
      policy_version: policy.version,
      purchase_request: recorded.robertJob().request,
      draft_rules: null,
    });

    expect(screen.getByTestId("purchase-preview-label")).toHaveTextContent(PURCHASE_PREVIEW_LABEL);
    expect(PURCHASE_PREVIEW_LABEL).toMatch(/^Preview — computed by the service/);
    // The figures are the recorded ones.
    const feasibility = recorded.robertResult().feasibility;
    expect([feasibility?.additional_purchase, feasibility?.cash_before, feasibility?.cash_after]).toEqual([0.25, 0.3, 0.05]);
    const table = within(preview()).getByTestId("feasibility-table");
    expect(within(table).getByTestId("additional-purchase")).toHaveTextContent("+25.0 points");
    expect(within(table).getByTestId("cash-after")).toHaveTextContent("5.0%");
    // A preview of the purchase is not a verdict: no rule status is drawn here.
    expect(preview().querySelector("[data-status]")).toBeNull();
    expect(preview()).toHaveTextContent("Whether it respects your rules is the result of the investigation");
  });

  it("shows the service's figures as sent: figures that no subtraction gives are displayed unchanged", async () => {
    const fixtures = createFixturesClient({ latencyMs: 0 });
    const sentinel = probe.sentinelFigures().result as CheckResult;
    await toPurchase({ api: { ...fixtures, check: async () => structuredClone(sentinel) } });
    await ready();

    const table = within(preview()).getByTestId("feasibility-table");
    expect(SENTINEL.cashBefore - SENTINEL.additionalPurchase).not.toBeCloseTo(SENTINEL.cashAfter);
    expect(within(table).getByTestId("additional-purchase")).toHaveTextContent("+77.7 points");
    expect(within(table).getByTestId("cash-after")).toHaveTextContent("55.5%");
    expect([...(table.querySelector('tr[data-row="cash"]')?.querySelectorAll("td") ?? [])].map((cell) => cell.textContent)).toEqual(["66.6%", "55.5%"]);
    expect([...(table.querySelector('tr[data-row="purchase"]')?.querySelectorAll("td") ?? [])].map((cell) => cell.textContent)).toEqual(["1.1%", "25.0%"]);
    // The user's own entry is still shown as entered.
    expect(screen.getByTestId("start-investigation")).toHaveTextContent("Check my idea");
  });

  it("carries the “Test data” marker in fixtures mode", async () => {
    await toPurchase();
    await ready();
    const panel = preview().closest('[data-figures="true"]') as HTMLElement;
    expect(panel).not.toBeNull();
    expect(within(panel).getAllByTestId("test-data-tag").length).toBeGreaterThan(0);
  });

  it("carries no such marker when the same answers come from a service", async () => {
    // Live mode with an access code already entered; the recorded bodies stand in for the service's answers.
    storeAccessCode("a-code-typed-by-the-user");
    await toPurchase({ live: true });
    await ready();
    expect(within(preview()).getByTestId("cash-after")).toHaveTextContent("5.0%");
    expect(screen.queryAllByTestId("test-data-tag")).toHaveLength(0);
    expect(screen.queryByTestId("fixtures-label")).toBeNull();
  });

  it("says calmly that the test data holds no preview for another request, and shows no figure in its place", async () => {
    const user = await toPurchase();
    await ready();
    await user.clear(screen.getByLabelText(TARGET_LABEL));
    await user.type(screen.getByLabelText(TARGET_LABEL), "12");

    const note = await screen.findByTestId("purchase-preview-not-recorded");
    expect(note).toHaveTextContent("The test data holds no recorded check of NVDA at a final direct weight of 12.0%");
    expect(preview()).toHaveTextContent("No preview for this request in the test data");
    expect(screen.queryByTestId("purchase-preview-error")).toBeNull();
    expect(screen.queryByTestId("feasibility-table")).toBeNull();
    expect(screen.queryByTestId("cash-after")).toBeNull();
    expect(screen.getByLabelText(TARGET_LABEL)).toHaveValue("12");
  });

  it("shows an error with a retry, and no figure, when the service does not answer", async () => {
    const fixtures = createFixturesClient({ latencyMs: 0 });
    const user = userEvent.setup();
    renderApp({ api: { ...fixtures, check: createFixturesClient({ latencyMs: 0, simulate: "check-error" }).check } });
    await screen.findByTestId("portfolio-table");
    await confirmScenarioRules(user);
    await go("purchase");

    expect(await screen.findByTestId("purchase-preview-error")).toHaveTextContent("Simulated failure (test data)");
    expect(within(preview()).getByRole("button", { name: "Try again" })).toBeInTheDocument();
    expect(screen.queryByTestId("cash-after")).toBeNull();
    // The investigation can still be started.
    expect(screen.getByTestId("start-investigation")).not.toHaveAttribute("aria-disabled");
  });
});

describe("Purchase stage, a request the service cannot evaluate (the recorded invalid request)", () => {
  it("shows the execution state the service reported, and nothing styled or worded as a verdict", async () => {
    const user = await toPurchase();
    await ready();
    await user.selectOptions(screen.getByLabelText("Which investment?"), "RY.TO");
    await user.clear(screen.getByLabelText(TARGET_LABEL));
    await user.type(screen.getByLabelText(TARGET_LABEL), "2");

    const execution = recorded.invalidRequest().execution;
    expect(execution.status).toBe("INVALID_REQUEST");
    const state = await screen.findByTestId("execution-state");
    expect(state).toHaveAttribute("data-execution-status", "INVALID_REQUEST");
    expect(within(state).getByTestId("execution-message")).toHaveTextContent(execution.message as string);
    expect(state).toHaveTextContent("TARGET_BELOW_CURRENT_WEIGHT");
    expect(state).toHaveTextContent("No rule was evaluated, so there is no preview to show.");
    expect(preview()).toHaveTextContent("This request cannot be evaluated");

    // No verdict, no figure, no pass/fail/unknown badge or count.
    expect(preview().querySelector("[data-status]")).toBeNull();
    expect(screen.queryByTestId("verdict-summary")).toBeNull();
    expect(screen.queryByTestId("count-pass")).toBeNull();
    expect(screen.queryByTestId("feasibility-table")).toBeNull();
    expect(screen.queryByTestId("purchase-preview-label")).toBeNull();
    expect(screen.getByTestId("held-now")).toHaveTextContent("Held directly now: 5.0%.");
  });

  async function enterTheInvalidRequest(user: UserEvent) {
    await user.selectOptions(screen.getByLabelText("Which investment?"), "RY.TO");
    await user.clear(screen.getByLabelText(TARGET_LABEL));
    await user.type(screen.getByLabelText(TARGET_LABEL), "2");
    await screen.findByTestId("execution-state");
  }

  it("says beside the start button that starting it would be refused, before anything is sent (finding F-08)", async () => {
    const fixtures = createFixturesClient({ latencyMs: 0 });
    const createInvestigation = vi.fn(fixtures.createInvestigation);
    const user = await toPurchase({ api: { ...fixtures, createInvestigation } });
    await ready();
    expect(screen.queryByTestId("start-preview-refusal")).toBeNull();

    await enterTheInvalidRequest(user);
    const hint = await screen.findByTestId("start-preview-refusal");
    expect(hint).toHaveTextContent("The preview above says this request cannot be evaluated (TARGET_BELOW_CURRENT_WEIGHT).");
    expect(hint).toHaveTextContent("no investigation is created");
    expect(hint.closest('[role="status"]')).not.toBeNull();
    expect(createInvestigation).not.toHaveBeenCalled();
    // The button stays usable: the refusal is the service's to give, and it explains itself (next test).
    expect(screen.getByTestId("start-investigation")).not.toHaveAttribute("aria-disabled");

    // The hint belongs to the request it was given for: it goes when the request changes.
    await user.clear(screen.getByLabelText(TARGET_LABEL));
    await waitFor(() => expect(screen.queryByTestId("start-preview-refusal")).toBeNull());
  });

  it("shows what the service refused when the start is answered 422, and offers no retry that could only be refused again (finding F-08)", async () => {
    const execution = recorded.invalidRequest().execution;
    const issue = `${execution.code}: ${execution.message}`;
    const fixtures = createFixturesClient({ latencyMs: 0 });
    // The service's answer to this request (contract section 6, rule 3): 422, with the engine's refusal in details[0].issue.
    const createInvestigation = vi.fn<ApiClient["createInvestigation"]>().mockRejectedValue(
      new ApiError("validation", "The purchase request cannot be evaluated.", {
        status: 422,
        code: "INVALID_PURCHASE_REQUEST",
        details: [{ path: "request", issue }],
        requestId: "req-test-422",
      }),
    );
    const user = await toPurchase({ api: { ...fixtures, createInvestigation } });
    await ready();
    await enterTheInvalidRequest(user);

    await user.click(screen.getByTestId("start-investigation"));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("The investigation could not be started");
    expect(alert).toHaveTextContent("The purchase request cannot be evaluated.");
    expect(within(alert).getByTestId("start-issues")).toHaveTextContent(issue);
    expect(alert).toHaveTextContent("No investigation was created.");
    expect(within(alert).getByTestId("start-refused")).toHaveTextContent("sending it again unchanged would be refused again");
    expect(within(alert).queryByRole("button")).toBeNull();
    expect(createInvestigation).toHaveBeenCalledTimes(1);
    // The page stays on the purchase stage: nothing was started.
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Step 2 of 3: Test an idea");
  });

  it("keeps the retry for a failure that another attempt can get past", async () => {
    const fixtures = createFixturesClient({ latencyMs: 0 });
    const createInvestigation = vi
      .fn<ApiClient["createInvestigation"]>()
      .mockRejectedValue(new ApiError("rate_limited", "The service is receiving too many requests. Wait a moment and try again.", { status: 429 }));
    const user = await toPurchase({ api: { ...fixtures, createInvestigation } });
    await ready();

    await user.click(screen.getByTestId("start-investigation"));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("No investigation was created.");
    expect(within(alert).queryByTestId("start-issues")).toBeNull();
    expect(within(alert).queryByTestId("start-refused")).toBeNull();
    await user.click(within(alert).getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(createInvestigation).toHaveBeenCalledTimes(2));
  });
});
