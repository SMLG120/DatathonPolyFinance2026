import { act, render, screen, waitFor, type RenderResult } from "@testing-library/react";
import userEvent, { type UserEvent } from "@testing-library/user-event";
import { expect } from "vitest";
import { AppContent } from "@/components/App";
import type { ApiClient } from "@/lib/api";
import { createFixturesClient } from "@/lib/api/fixtures-client";
import type { RuntimeConfig, Timing } from "@/lib/config";
import { RuntimeProvider } from "@/state/runtime";
import { STAGES, type StageId } from "@/state/stage";
import { FAST_TIMING, FIXTURES_CONFIG } from "./render";

export interface RenderAppOptions {
  api?: ApiClient;
  timing?: Timing;
  config?: RuntimeConfig;
}

/** The whole application below the runtime, on the fixtures client unless another client is given. */
export function renderApp(options: RenderAppOptions = {}): RenderResult {
  return render(
    <RuntimeProvider config={options.config ?? FIXTURES_CONFIG} api={options.api ?? createFixturesClient({ latencyMs: 0 })} timing={options.timing ?? FAST_TIMING}>
      <AppContent />
    </RuntimeProvider>,
  );
}

export const stageHeading = () => screen.getByRole("heading", { level: 1 });

/** Moves to a stage the way the browser does: by changing the hash. */
export async function go(stage: StageId): Promise<void> {
  const target = STAGES.find((candidate) => candidate.id === stage);
  act(() => {
    window.location.hash = `#/${stage}`;
  });
  await waitFor(() => expect(stageHeading()).toHaveTextContent(`Step ${target?.number} of 6: ${target?.title}`));
}

/** Stage 1: switches from the default persona to Mateo and waits for his portfolio. */
export async function chooseMateo(user: UserEvent): Promise<void> {
  await user.click(screen.getByRole("button", { name: "Use Mateo’s portfolio" }));
  await waitFor(() => expect(screen.getByTestId("portfolio-table")).toHaveTextContent("Mateo’s fictional portfolio"));
}

/** Stage 2: confirms the rules the scenario offers, with the numbers the scenario gives them. */
export async function confirmScenarioRules(user: UserEvent): Promise<void> {
  await go("goals");
  await screen.findAllByTestId("rule-card");
  await user.click(screen.getByTestId("confirm-rules"));
  await screen.findAllByTestId("policy-rule-card");
}

/** Stages 3 to 5: starts the investigation of the scenario's request and opens its report. */
export async function runInvestigation(user: UserEvent): Promise<HTMLElement> {
  await go("purchase");
  await user.click(screen.getByTestId("start-investigation"));
  await waitFor(() => expect(stageHeading()).toHaveTextContent("Investigation steps"));
  await user.click(await screen.findByTestId("see-verdict", {}, { timeout: 5_000 }));
  return screen.findByTestId("report");
}

/** From the first screen to the report of the persona's scripted request. */
export async function toVerdict(options: RenderAppOptions & { persona?: "robert" | "mateo" } = {}): Promise<UserEvent> {
  const user = userEvent.setup();
  renderApp(options);
  await screen.findByTestId("portfolio-table");
  if (options.persona === "mateo") await chooseMateo(user);
  await confirmScenarioRules(user);
  await runInvestigation(user);
  return user;
}
