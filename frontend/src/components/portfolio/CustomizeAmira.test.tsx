import { screen, waitFor, within } from "@testing-library/react";
import userEvent, { type UserEvent } from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { ApiClient } from "@/lib/api";
import type { CheckRequest, CustomPortfolio, InvestigationCreateRequest } from "@/lib/contracts";
import { fractionToWeightText } from "@/lib/customize";
import { FIXTURES } from "@/lib/fixtures";
import { confirmScenarioRules, go, renderApp } from "@/test/app";
import { liveDouble } from "@/test/live-double";

/**
 * Amira and "Customize this profile" together. Amira is the one persona whose fictional portfolio holds
 * assets that are not shares or funds (two crypto assets).
 *
 * The test data holds no recorded check or investigation for Amira, so the stand-in refuses them the way
 * the fixtures client does. Every assertion about a check or an investigation below is therefore about
 * the REQUEST the page sent, never about a figure.
 */
const amira = FIXTURES.portfolioAmira.response;
const robert = FIXTURES.portfolioRobert.response;
const amiraObjective = amira.scenario.objectives[0];
if (!amiraObjective) throw new Error("Amira's scenario has no objective.");

const weight = (id: string) => screen.getByTestId(`customize-weight-${id}`);
const table = () => screen.getByTestId("portfolio-table");
const tableRow = (id: string) => {
  const row = within(table())
    .getAllByTestId("portfolio-row")
    .find((candidate) => within(candidate).queryByText(id) !== null);
  if (!row) throw new Error(`The table has no row for ${id}.`);
  return row;
};
const offered = () =>
  within(screen.getByTestId("customize-add-select"))
    .getAllByRole("option")
    .map((option) => (option as HTMLOptionElement).value)
    .filter((value) => value !== "");

async function retype(user: UserEvent, field: HTMLElement, text: string): Promise<void> {
  await user.clear(field);
  if (text !== "") await user.type(field, text);
}

async function choose(user: UserEvent, name: "Robert" | "Amira"): Promise<void> {
  await user.click(screen.getByRole("button", { name: `Use ${name}’s portfolio` }));
  await waitFor(() => expect(table()).toHaveTextContent(`${name}’s fictional portfolio`));
}

async function startAsAmira(options: { api?: ApiClient } = {}): Promise<UserEvent> {
  const user = userEvent.setup();
  renderApp(options);
  await screen.findByTestId("portfolio-table");
  await choose(user, "Amira");
  return user;
}

async function openEditor(user: UserEvent): Promise<HTMLElement> {
  await user.click(screen.getByTestId("customize-open"));
  return screen.findByTestId("customize-editor");
}

/** Amira, customized: ETH-USD removed, BTC-USD at 15%, cash at 15%. Totals 100%. */
const CUSTOM_AMIRA: CustomPortfolio = {
  cash_weight: 0.15,
  positions: [
    { instrument_id: "SPY", weight: 0.3 },
    { instrument_id: "XIU.TO", weight: 0.1 },
    { instrument_id: "NVDA", weight: 0.1 },
    { instrument_id: "MSFT", weight: 0.1 },
    { instrument_id: "SHOP.TO", weight: 0.05 },
    { instrument_id: "JPM", weight: 0.05 },
    { instrument_id: "BTC-USD", weight: 0.15 },
  ],
};

async function applyCustomAmira(user: UserEvent): Promise<void> {
  await openEditor(user);
  await user.click(screen.getByTestId("customize-remove-ETH-USD"));
  await retype(user, weight("BTC-USD"), "15");
  await retype(user, screen.getByTestId("customize-cash"), "15");
  expect(screen.getByTestId("customize-total")).toHaveTextContent("Total: 100.00%");
  await user.click(screen.getByTestId("customize-apply"));
  await waitFor(() => expect(screen.queryByTestId("customize-editor")).toBeNull());
}

describe("Customize this profile: Amira", () => {
  it("opens the editor with her recorded weights, cash and objective, crypto assets included", async () => {
    const { api } = liveDouble();
    const user = await startAsAmira({ api });
    const editor = await openEditor(user);
    const { portfolio } = amira.scenario;
    expect(within(editor).getAllByTestId("customize-row").map((row) => row.getAttribute("data-instrument-id"))).toEqual(portfolio.positions.map((position) => position.instrument_id));
    for (const position of portfolio.positions) expect(weight(position.instrument_id)).toHaveValue(fractionToWeightText(position.weight));
    // The two assets that are not shares or funds are rows like any other.
    expect(amira.instruments["BTC-USD"]?.asset_class).toBe("crypto");
    expect(weight("BTC-USD")).toHaveValue("12");
    expect(weight("ETH-USD")).toHaveValue("8");
    expect(screen.getByTestId("customize-remove-BTC-USD")).toBeInTheDocument();
    expect(screen.getByTestId("customize-cash")).toHaveValue("10");
    expect(screen.getByTestId("customize-total")).toHaveTextContent("Total: 100.00%");
    expect(screen.getByTestId("customize-objective")).toHaveValue(amiraObjective.original_words);
    expect(within(editor).getByText(`Cash (${portfolio.base_currency})`)).toBeInTheDocument();
    expect(screen.queryByTestId("customize-error")).toBeNull();
  });

  it("lets a crypto position be edited, removed and added back, and offers only purchasable assets", async () => {
    const { api } = liveDouble();
    const user = await startAsAmira({ api });
    await openEditor(user);
    // Amira holds every purchasable instrument, so nothing can be added at first.
    expect(offered()).toEqual([]);

    await user.click(screen.getByTestId("customize-remove-BTC-USD"));
    expect(screen.queryByTestId("customize-weight-BTC-USD")).toBeNull();
    expect(offered()).toEqual(["BTC-USD"]);
    await user.click(screen.getByTestId("customize-remove-SPY"));
    expect([...offered()].sort()).toEqual(["BTC-USD", "SPY"]);
    for (const id of offered()) expect(amira.purchasable_instrument_ids).toContain(id);
    // Nothing of another persona's universe is offered (XBB.TO is Robert's).
    expect(robert.purchasable_instrument_ids).toContain("XBB.TO");
    expect(offered()).not.toContain("XBB.TO");
    expect(within(screen.getByTestId("customize-add-select")).getByRole("option", { name: /^BTC-USD: / })).toHaveTextContent(amira.instruments["BTC-USD"]?.name ?? "missing");

    await user.selectOptions(screen.getByTestId("customize-add-select"), "BTC-USD");
    await user.click(screen.getByTestId("customize-add"));
    expect(weight("BTC-USD")).toHaveFocus();
    expect(weight("BTC-USD")).toHaveValue("");
    await user.type(weight("BTC-USD"), "42");
    // SPY (30%) is gone and BTC-USD went from 12% to 42%: the form totals 100% again.
    expect(screen.getByTestId("customize-total")).toHaveTextContent("Total: 100.00%");
    expect(screen.getByTestId("customize-apply")).not.toHaveAttribute("aria-disabled");

    await retype(user, weight("ETH-USD"), "-8");
    expect(weight("ETH-USD")).toHaveAccessibleDescription(expect.stringContaining("Shorting is not supported"));
    expect(screen.getByTestId("customize-apply")).toHaveAttribute("aria-disabled", "true");
  });

  it("after Apply shows the custom weights, and the next check and investigation carry exactly them for persona amira", async () => {
    const { api, check, createInvestigation } = liveDouble();
    const user = await startAsAmira({ api });
    await applyCustomAmira(user);

    expect(tableRow("BTC-USD")).toHaveTextContent("15.0%");
    expect(within(table()).queryByText("ETH-USD")).toBeNull();
    expect(within(table()).getAllByTestId("portfolio-row").at(-1)).toHaveTextContent("15.0%");
    expect(screen.getByTestId("customized-badge")).toHaveTextContent("Customized fictional portfolio");
    expect(screen.getByTestId("customized-notice")).toHaveTextContent("Amira’s original fictional portfolio");
    expect(within(screen.getByTestId("persona-amira")).getByTestId("persona-selected")).toBeInTheDocument();

    await confirmScenarioRules(user);
    await go("purchase");
    expect(screen.getByTestId("purchase-portfolio-note")).toHaveTextContent("Amira’s original fictional portfolio");
    await waitFor(() => expect(check).toHaveBeenCalled());
    for (const [body] of check.mock.calls) {
      expect(body.persona_id).toBe("amira");
      expect(body.custom_portfolio).toEqual(CUSTOM_AMIRA);
    }

    await user.click(screen.getByTestId("start-investigation"));
    await waitFor(() => expect(createInvestigation).toHaveBeenCalledTimes(1));
    const sent = createInvestigation.mock.calls[0]?.[0] as InvestigationCreateRequest;
    const scripted = amira.scenario.demo_requests[0]?.purchase_request;
    expect(sent).toEqual({ persona_id: "amira", policy_id: sent.policy_id, policy_version: 1, request: scripted, parent_investigation_id: null, custom_portfolio: CUSTOM_AMIRA });
    // One value in the state feeds both requests.
    expect(sent.custom_portfolio).toBe((check.mock.calls.at(-1)?.[0] as CheckRequest).custom_portfolio);
  });

  it("sends no custom_portfolio member in Amira's default flow", async () => {
    const { api, check, createInvestigation } = liveDouble();
    const user = await startAsAmira({ api });
    await confirmScenarioRules(user);
    await go("purchase");
    expect(screen.queryByTestId("purchase-portfolio-note")).toBeNull();
    await waitFor(() => expect(check).toHaveBeenCalled());
    await user.click(screen.getByTestId("start-investigation"));
    await waitFor(() => expect(createInvestigation).toHaveBeenCalledTimes(1));
    for (const [body] of [...check.mock.calls, ...createInvestigation.mock.calls]) {
      expect(body.persona_id).toBe("amira");
      expect("custom_portfolio" in body).toBe(false);
      expect(JSON.stringify(body)).not.toContain("custom_portfolio");
    }
  });

  it("switching persona (Robert, Amira, Robert) clears the customization and closes the editor each time", async () => {
    const { api, check } = liveDouble();
    const user = userEvent.setup();
    renderApp({ api });
    await screen.findByTestId("portfolio-table");

    // Robert: apply a customization, then leave the editor open with an unapplied edit.
    await openEditor(user);
    await retype(user, weight("SPY"), "15");
    await retype(user, screen.getByTestId("customize-cash"), "35");
    await user.click(screen.getByTestId("customize-apply"));
    expect(screen.getByTestId("customized-badge")).toBeInTheDocument();
    await openEditor(user);
    await retype(user, weight("SPY"), "1");

    await choose(user, "Amira");
    expect(screen.queryByTestId("customize-editor")).toBeNull();
    expect(screen.queryByTestId("customized-badge")).toBeNull();
    expect(screen.queryByTestId("customize-summary")).toBeNull();
    expect(tableRow("SPY")).toHaveTextContent("30.0%");
    expect(tableRow("BTC-USD")).toHaveTextContent("12.0%");
    await openEditor(user);
    expect(weight("SPY")).toHaveValue("30");
    expect(screen.getByTestId("customize-objective")).toHaveValue(amiraObjective.original_words);
    await user.click(screen.getByTestId("customize-cancel"));

    // Amira: apply one, and open the editor again.
    await applyCustomAmira(user);
    expect(screen.getByTestId("customized-badge")).toBeInTheDocument();
    await openEditor(user);

    await choose(user, "Robert");
    expect(screen.queryByTestId("customize-editor")).toBeNull();
    expect(screen.queryByTestId("customized-badge")).toBeNull();
    expect(tableRow("SPY")).toHaveTextContent("20.0%");
    expect(within(table()).queryByText("BTC-USD")).toBeNull();
    await openEditor(user);
    expect(weight("SPY")).toHaveValue("20");
    expect(screen.getByTestId("customize-cash")).toHaveValue("30");
    expect(screen.queryByTestId("customize-weight-BTC-USD")).toBeNull();
    await user.click(screen.getByTestId("customize-cancel"));

    // And what is sent for Robert afterwards carries no customized portfolio.
    await confirmScenarioRules(user);
    await go("purchase");
    await waitFor(() => expect(check).toHaveBeenCalled());
    for (const [body] of check.mock.calls) {
      expect(body.persona_id).toBe("robert");
      expect("custom_portfolio" in body).toBe(false);
    }
  });

  it("shows the control disabled for Amira too in fixtures mode, with the reason", async () => {
    const user = await startAsAmira();
    const open = screen.getByTestId("customize-open");
    expect(open).toHaveAttribute("aria-disabled", "true");
    expect(open).toHaveAccessibleDescription("Customization needs the live service: the test data only replays results recorded for the original portfolio.");
    await user.click(open);
    expect(screen.queryByTestId("customize-editor")).toBeNull();
    expect(screen.queryByTestId("customized-badge")).toBeNull();
  });
});
