import { expect, test, type Page } from "@playwright/test";
import { formatFraction } from "../../../frontend/src/lib/format";
import { verdictHeadline } from "../../../frontend/src/lib/verdict";
import { expectReportMatchesJob } from "./report";
import {
  api,
  CODE,
  confirmOfferedRules,
  control,
  goToGoals,
  goToPurchase,
  mainAlert,
  openAllDetails,
  openApp,
  resetBackend,
  serverLog,
  setPurchase,
  shot,
  submitCode,
  accessForm,
  storedKeys,
  Traffic,
} from "./helpers";

/**
 * Error paths, timing and the model modes, in the browser against the real handlers. Each test sets the switches of
 * local_api.py it needs (control port) and reads what the page received.
 */

async function toPurchaseStage(page: Page): Promise<Traffic> {
  const traffic = new Traffic(page);
  await openApp(page);
  await goToGoals(page);
  await confirmOfferedRules(page);
  await goToPurchase(page);
  await expect(page.getByTestId("purchase-preview").getByTestId("cash-after")).toBeVisible();
  return traffic;
}

const investigationPosts = async () => (await serverLog()).filter((entry) => entry.route === "POST /investigations");
const pollsOf = async (id: string) => (await serverLog()).filter((entry) => entry.route === "GET /investigations/{id}" && entry.path.endsWith(id));

test.describe("error paths and timing, live against the local backend", () => {
  test.beforeEach(async () => {
    await resetBackend();
  });

  test("429 from the gateway on POST /investigations: readable, nothing created, the retry reuses the idempotency key and creates one job", async ({ page }) => {
    const traffic = await toPurchaseStage(page);
    await control("/settings", { throttle_post_investigations: 1 });
    await page.getByTestId("start-investigation").click();
    const alert = mainAlert(page).filter({ hasText: "The investigation could not be started" });
    await expect(alert).toBeVisible();
    await expect(alert).toContainText("No investigation was created.");
    const throttled = await traffic.last("POST", /^\/investigations$/);
    expect([throttled.status, throttled.body]).toEqual([429, { message: "Too Many Requests" }]);

    await alert.getByRole("button", { name: "Try again" }).click();
    await expect(page.getByTestId("see-verdict")).toBeVisible({ timeout: 60_000 });
    const posts = await investigationPosts();
    expect(posts.map((entry) => entry.status)).toEqual([429, 202]);
    expect(posts[1].idempotency_key, "a retry of the same action reuses its key (contracts/api.md section 6)").toBe(posts[0].idempotency_key);
    const state = await control("/state");
    expect(state.invocations.length, "one worker invocation").toBe(1);
  });

  test("a gateway 429 is explained in the page's own words, not with the gateway's body", async ({ page }) => {
    test.fail(true, "F-01: the client reads `message` from a gateway body; the page prints \"Too Many Requests\" instead of its own sentence");
    await toPurchaseStage(page);
    await control("/settings", { throttle_post_investigations: 1 });
    await page.getByTestId("start-investigation").click();
    const alert = mainAlert(page).filter({ hasText: "The investigation could not be started" });
    await expect(alert).toBeVisible();
    // contracts/api.md, Errors: a body that is not the error shape comes from API Gateway; "clients then act on the status code alone".
    await expect(alert).toContainText("The service is receiving too many requests. Wait a moment and try again.");
  });

  test("503 WORKER_INVOCATION_FAILED: readable, and 'Try again' starts the investigation once the worker can be invoked", async ({ page }) => {
    test.fail(true, "F-03: the retry reuses the idempotency key of the failed attempt, so the service replays the same 503 for ever");
    const traffic = await toPurchaseStage(page);
    await control("/settings", { invoke_error: true });
    await page.getByTestId("start-investigation").click();
    const alert = mainAlert(page).filter({ hasText: "The investigation could not be started" });
    await expect(alert).toBeVisible();
    const refused = await traffic.last("POST", /^\/investigations$/);
    expect(refused.status).toBe(503);
    expect(refused.body.error.code).toBe("WORKER_INVOCATION_FAILED");
    await expect(alert).toContainText(refused.body.error.message);
    // The cause is gone; contracts/api.md section 6, rule 5: "The client retries with a new key."
    await control("/settings", { invoke_error: false });
    const retried = await traffic.after("POST", /^\/investigations$/, () => alert.getByRole("button", { name: "Try again" }).click());
    test.info().annotations.push({ type: "observed", description: `retry after 503: ${retried.status}, same key: ${retried.requestHeaders["idempotency-key"] === refused.requestHeaders["idempotency-key"]}` });
    expect(retried.requestHeaders["idempotency-key"], "a new key for the retry after a 503").not.toBe(refused.requestHeaders["idempotency-key"]);
    expect(retried.status).toBe(202);
    await expect(page.getByTestId("see-verdict")).toBeVisible({ timeout: 30_000 });
  });

  test("double-click on 'Start the investigation' creates one job", async ({ page }) => {
    await toPurchaseStage(page);
    await control("/settings", { worker_delay_s: 1 });
    await page.getByTestId("start-investigation").dblclick();
    await expect(page.getByTestId("see-verdict")).toBeVisible({ timeout: 60_000 });
    const posts = await investigationPosts();
    expect(posts.length, "POST /investigations requests").toBe(1);
    const state = await control("/state");
    expect(state.invocations.length).toBe(1);
    expect(state.s3_keys.filter((key: string) => key.startsWith("jobs/")).length).toBe(1);
  });

  test("422: a target below the current weight is refused by the preview and by POST /investigations, readably, and no job is stored", async ({ page }) => {
    const traffic = await toPurchaseStage(page);
    const held = (await traffic.last("GET", /^\/portfolios\/robert$/)).body.scenario.portfolio.positions.find((position: any) => position.instrument_id === "RY.TO").weight;
    await setPurchase(page, "RY.TO", "2");
    await expect(page.getByTestId("held-now")).toContainText(formatFraction(held));
    // The preview is the engine's refusal, as a normal 200 answer.
    const check = await traffic.last("POST", /^\/check$/, (call) => call.requestBody?.purchase_request?.instrument_id === "RY.TO");
    expect(check.status).toBe(200);
    expect(check.body.execution.status).toBe("INVALID_REQUEST");
    expect(check.body.rule_results).toEqual([]);
    const preview = page.getByTestId("purchase-preview");
    await expect(preview.getByTestId("execution-message")).toContainText(check.body.execution.message);
    await expect(preview.getByTestId("execution-state")).toContainText(check.body.execution.code);
    await expect(preview.getByTestId("cash-after")).toHaveCount(0);
    // Starting it anyway is answered 422, and nothing is stored.
    const refused = await traffic.after("POST", /^\/investigations$/, () => page.getByTestId("start-investigation").click());
    expect(refused.status).toBe(422);
    expect(refused.body.error.code).toBe("INVALID_PURCHASE_REQUEST");
    expect(refused.body.error.details[0].issue.startsWith(`${check.body.execution.code}: `)).toBe(true);
    const alert = mainAlert(page).filter({ hasText: "The investigation could not be started" });
    await expect(alert).toBeVisible();
    await expect(alert).toContainText(refused.body.error.message);
    await expect(alert).toContainText("No investigation was created.");
    const state = await control("/state");
    expect(state.s3_keys.filter((key: string) => key.startsWith("jobs/")), "no job is stored for a request the engine refuses").toEqual([]);
    expect(state.invocations).toEqual([]);
  });

  test("insufficient cash is reported as feasibility, not as a rule FAIL", async ({ page }) => {
    const traffic = await toPurchaseStage(page);
    const cash = (await traffic.last("GET", /^\/portfolios\/robert$/)).body.scenario.portfolio.cash_weight;
    await setPurchase(page, "NVDA", "40"); // more than the cash the fictional portfolio holds
    expect(0.4).toBeGreaterThan(cash);
    const preview = page.getByTestId("purchase-preview");
    await expect(preview.getByText("Not feasible with cash alone")).toBeVisible();
    const check = await traffic.last("POST", /^\/check$/, (call) => call.requestBody?.purchase_request?.target_direct_weight === 0.4 && call.status === 200);
    expect(check.body.feasibility.status).toBe("INSUFFICIENT_CASH");
    await expect(preview.getByTestId("cash-after")).toHaveText(formatFraction(check.body.feasibility.cash_after));
    await expect(preview).toContainText("This is a feasibility result, reported separately from the rule results.");

    await page.getByTestId("start-investigation").click();
    await page.getByTestId("see-verdict").click({ timeout: 60_000 });
    await expect(page.getByTestId("report")).toBeVisible();
    const job = (await traffic.last("GET", /^\/investigations\/inv-[0-9a-f]+$/, (call) => call.body?.status === "SUCCEEDED")).body;
    const result = job.result;
    expect(result.feasibility.status).toBe("INSUFFICIENT_CASH");
    expect(result.summary.feasibility_status).toBe("INSUFFICIENT_CASH");
    await openAllDetails(page);
    await expectReportMatchesJob(page, job);
    // The counts are the rules' only: the funding problem adds no FAIL.
    await expect(page.getByTestId("count-fail")).toHaveAttribute("data-count", String(result.rule_results.filter((rule: any) => rule.status === "FAIL").length));
    await expect(page.getByTestId("rule-result")).toHaveCount(result.rule_results.length);
    await expect(page.getByTestId("feasibility")).toHaveAttribute("data-feasibility", "INSUFFICIENT_CASH");
    await expect(page.getByTestId("feasibility")).toContainText(/feasibility/i);
    await expect(page.getByTestId("verdict-headline")).toHaveText(verdictHeadline(result.summary).title);
    await shot(page, "14-insufficient-cash-is-feasibility-not-a-rule-fail-live-local-backend-real-data");
  });

  /** One rule confirmed here (version 1), then version 2 created from "another tab", then this tab confirms on top of version 1. */
  async function provokeConflict(page: Page) {
    const traffic = new Traffic(page);
    await openApp(page);
    await goToGoals(page);
    await page.getByTestId("rule-card").nth(1).getByRole("textbox").fill("");
    const first = await traffic.after("POST", /^\/rules\/confirm$/, () => page.getByTestId("confirm-rules").click());
    await expect(page.getByTestId("policy-rule-card")).toHaveCount(1);
    const v1 = first.body.policy;
    const portfolio = (await traffic.last("GET", /^\/portfolios\/robert$/)).body;
    const other = portfolio.scenario.scenario_rules[1];
    const elsewhere = await api("POST", "/rules/confirm", {
      persona_id: "robert", policy_id: v1.policy_id, base_version: 1, objectives: portfolio.scenario.objectives,
      confirmations: [{ rule: { ...other, rule_id: `${other.rule_id}-other-tab` }, threshold: 0.2 }], withdraw_rule_ids: [], change_note: "from another tab",
    });
    expect(elsewhere.status).toBe(201);
    await page.getByTestId("rule-card").first().getByRole("textbox").fill("10");
    const conflict = await traffic.after("POST", /^\/rules\/confirm$/, () => page.getByTestId("confirm-rules").click());
    return { traffic, v1, conflict };
  }

  test("409 POLICY_VERSION_CONFLICT on confirm is shown with the service's sentence; nothing is confirmed", async ({ page }) => {
    const { traffic, conflict } = await provokeConflict(page);
    expect(conflict.status).toBe(409);
    expect(conflict.body.error.code).toBe("POLICY_VERSION_CONFLICT");
    expect(conflict.requestBody.base_version).toBe(1);
    const alert = mainAlert(page).filter({ hasText: "The rules could not be confirmed" });
    await expect(alert).toBeVisible();
    await expect(alert).toContainText(conflict.body.error.message);
    await expect(page.getByTestId("rule-card")).toHaveCount(1); // the rule is still only proposed
    // What "Try again" does: the same request on the same stale base version.
    const again = await traffic.after("POST", /^\/rules\/confirm$/, () => alert.getByRole("button", { name: "Try again" }).click());
    test.info().annotations.push({ type: "observed", description: `"Try again" after the 409: ${again.status}, base_version ${again.requestBody.base_version}` });
    expect(again.status).toBe(409);
  });

  test("after a 409 the page drops its policy state and starts the rule stage again (contracts/api.md section 4, rule 8)", async ({ page }) => {
    test.fail(true, "F-04: the stale policy version stays shown as in force and every further confirmation is refused with the same 409");
    const { conflict } = await provokeConflict(page);
    expect(conflict.status).toBe(409);
    await expect(page.getByTestId("policy-rule-card"), "the stale version is no longer presented as the confirmed policy").toHaveCount(0);
  });

  test("a job that ends FAILED shows the failure and its code, no verdict, and can be run again with a new key", async ({ page }) => {
    const traffic = await toPurchaseStage(page);
    await control("/fail-next-put", { prefix: "results/" });
    await page.getByTestId("start-investigation").click();
    const alert = mainAlert(page).filter({ hasText: "The investigation failed" });
    await expect(alert).toBeVisible({ timeout: 60_000 });
    const failed = (await traffic.last("GET", /^\/investigations\/inv-[0-9a-f]+$/, (call) => call.body?.status === "FAILED")).body;
    expect(failed.result).toBeNull();
    expect(failed.explanation).toEqual([]);
    await expect(alert).toContainText(failed.failure.message);
    await expect(alert).toContainText(failed.failure.code);
    await expect(page.getByTestId("see-verdict")).toHaveCount(0);
    // Stage 5 shows no verdict for it.
    await page.getByRole("link", { name: "Step 5 of 6: Verdict & evidence" }).click();
    await expect(page.getByTestId("failure-code")).toContainText(failed.failure.code);
    await expect(page.getByTestId("report")).toHaveCount(0);
    await expect(page.getByTestId("verdict-headline")).toHaveCount(0);
    await shot(page, "16-job-failed-no-verdict-live-local-backend-real-data");
    // Running it again is a new action: a new key, a new job, which succeeds.
    await page.getByRole("link", { name: "Step 4 of 6: Investigation steps" }).click();
    await mainAlert(page).filter({ hasText: "The investigation failed" }).getByRole("button", { name: "Run the same request again" }).click();
    await expect(page.getByTestId("see-verdict")).toBeVisible({ timeout: 60_000 });
    const posts = await investigationPosts();
    expect(posts.map((entry) => entry.status)).toEqual([202, 202]);
    expect(posts[1].idempotency_key).not.toBe(posts[0].idempotency_key);
  });

  test("a worker that never runs: the page waits, then shows the server's DEADLINE_EXCEEDED when the job deadline passes", async ({ page }) => {
    const traffic = await toPurchaseStage(page);
    await control("/settings", { worker_never_delivered: true });
    await page.getByTestId("start-investigation").click();
    await expect(page.getByTestId("timeline-waiting").or(page.getByText("Waiting for its first status"))).toBeVisible();
    const accepted = (await traffic.last("POST", /^\/investigations$/)).body;
    expect(accepted.status).toBe("QUEUED");
    expect(accepted.poll).toEqual({ path: `/investigations/${accepted.id}`, interval_ms: 1500 });
    expect(Date.parse(accepted.deadline_at) - Date.parse(accepted.created_at), "job deadline is created_at + 150 s").toBe(150_000);
    await expect.poll(async () => (await pollsOf(accepted.id)).length, { timeout: 15_000 }).toBeGreaterThanOrEqual(3);
    await expect(page.getByTestId("see-verdict")).toHaveCount(0);
    // The server's clock passes the job deadline (the offset stands in for 150 s of waiting).
    await control("/advance-clock", { seconds: 151 });
    const alert = mainAlert(page).filter({ hasText: "The investigation failed" });
    await expect(alert).toBeVisible({ timeout: 10_000 });
    const failed = (await traffic.last("GET", /^\/investigations\/inv-[0-9a-f]+$/, (call) => call.body?.status === "FAILED")).body;
    expect(failed.failure.code).toBe("DEADLINE_EXCEEDED");
    await expect(alert).toContainText("DEADLINE_EXCEEDED");
    await expect(alert).toContainText(failed.failure.message);
    // Polling stops on the terminal state.
    const polls = (await pollsOf(accepted.id)).length;
    await page.waitForTimeout(3500);
    expect((await pollsOf(accepted.id)).length).toBe(polls);
  });

  test("a slow job shows its steps as they complete; polls are 1.5 s apart", async ({ page }) => {
    test.setTimeout(180_000);
    const traffic = await toPurchaseStage(page);
    await control("/settings", { bedrock_mode: "benign", bedrock_stepwise: true, bedrock_delay_s: 1.3 });
    await page.getByTestId("start-investigation").click();
    await expect(page.getByTestId("timeline-waiting")).toBeVisible({ timeout: 15_000 });
    const seen: number[] = [];
    await expect(async () => {
      seen.push(await page.getByTestId("timeline-step").count());
      await expect(page.getByTestId("see-verdict")).toBeVisible({ timeout: 100 });
    }).toPass({ timeout: 90_000, intervals: [250] });
    const job = (await traffic.last("GET", /^\/investigations\/inv-[0-9a-f]+$/, (call) => call.body?.status === "SUCCEEDED")).body;
    const distinct = [...new Set(seen)];
    expect(distinct.length, `step counts seen while it ran: ${distinct.join(", ")}`).toBeGreaterThanOrEqual(4);
    expect(seen, "a step that had been shown never went away").toEqual([...seen].sort((a, b) => a - b));
    expect(Math.max(...seen)).toBeLessThanOrEqual(job.steps.length);
    await expect(page.getByTestId("timeline-step")).toHaveCount(job.steps.length);
    // Running jobs the page received were RUNNING with a growing list of steps.
    const running = await traffic.find("GET", /^\/investigations\/inv-[0-9a-f]+$/, (call) => call.body?.status === "RUNNING");
    expect(running.length).toBeGreaterThanOrEqual(3);
    // The model path is labelled as such.
    expect(job.agent.mode).toBe("MODEL");
    await expect(page.getByTestId("agent-mode")).toHaveAttribute("data-agent-mode", "MODEL");
    await expect(page.getByTestId("agent-mode")).toContainText(`Model: ${job.agent.model_id}`);
    // Interval between polls, measured at the server: the page waits 1.5 s after each answer.
    const polls = await pollsOf(job.id);
    const gaps = polls.slice(1).map((entry, index) => entry.t - polls[index].t);
    expect(gaps.length).toBeGreaterThanOrEqual(4);
    for (const gap of gaps) {
      expect(gap, `gap between polls: ${gaps.map((value) => value.toFixed(2)).join(", ")}`).toBeGreaterThanOrEqual(1.45);
      expect(gap).toBeLessThan(2.2);
    }
  });

  test("client deadline: polling stops 180 s after the 202 with a visible failure, and 'Keep waiting' resumes it", async ({ page }) => {
    const traffic = await toPurchaseStage(page);
    // A job the server keeps QUEUED beyond the client's deadline (in production the server's 150 s comes first).
    await control("/settings", { worker_never_delivered: true, job_deadline_seconds: 800 });
    await page.clock.install();
    await page.getByTestId("start-investigation").click();
    await expect(page.getByText("Waiting for its first status").or(page.getByTestId("timeline-waiting"))).toBeVisible();
    const accepted = (await traffic.last("POST", /^\/investigations$/)).body;
    const timedOut = mainAlert(page).filter({ hasText: "No final answer within 180 seconds" });
    // 177 s of page time: still polling, no failure shown.
    for (let second = 0; second < 177; second += 3) {
      await page.clock.runFor(3_000); // 59 x 3 s = 177 s of page time
    }
    await expect(timedOut).toHaveCount(0);
    const before = (await pollsOf(accepted.id)).length;
    expect(before).toBeGreaterThan(3);
    await page.clock.runFor(5_000); // 182 s
    await expect(timedOut).toBeVisible();
    await expect(timedOut).toContainText("No verdict is shown, because none was received.");
    await expect(page.locator("main")).toContainText(accepted.id);
    await expect(page.getByTestId("see-verdict")).toHaveCount(0);
    const stopped = (await pollsOf(accepted.id)).length;
    await page.clock.runFor(10_000);
    expect((await pollsOf(accepted.id)).length, "no poll after the client deadline").toBe(stopped);
    await timedOut.getByRole("button", { name: "Keep waiting" }).click();
    await page.clock.runFor(2_000);
    await expect.poll(async () => (await pollsOf(accepted.id)).length).toBeGreaterThan(stopped);
  });

  test("polling survives 429s from the gateway until the job finishes (contracts/api.md section 7, polling rule 4)", async ({ page }) => {
    test.fail(true, "F-02: the page gives up after three failed polls in a row instead of retrying until its 180 s deadline");
    const traffic = await toPurchaseStage(page);
    await control("/settings", { worker_delay_s: 9 });
    await page.getByTestId("start-investigation").click();
    await expect.poll(async () => (await traffic.find("GET", /^\/investigations\/inv-/)).length).toBeGreaterThanOrEqual(1);
    await control("/settings", { throttle_all: 4 });
    // The job finishes server-side after 9 s; a page that keeps polling at 1.5 s sees it within about 12 s.
    await expect(page.getByTestId("see-verdict")).toBeVisible({ timeout: 25_000 });
  });

  test("what the page shows when polling hits repeated 429s", async ({ page }) => {
    const traffic = await toPurchaseStage(page);
    await control("/settings", { worker_delay_s: 9 });
    await page.getByTestId("start-investigation").click();
    await expect.poll(async () => (await traffic.find("GET", /^\/investigations\/inv-/)).length).toBeGreaterThanOrEqual(1);
    await control("/settings", { throttle_all: 4 });
    const alert = mainAlert(page).filter({ hasText: "The status of the investigation could not be fetched" });
    await expect(alert).toBeVisible({ timeout: 20_000 });
    const throttled = await traffic.find("GET", /^\/investigations\/inv-/, (call) => call.status === 429);
    expect(throttled.length, "polls answered 429 before the page gave up").toBe(3);
    // Not a dead end: "Check again" resumes and the finished job is shown.
    await control("/settings", { throttle_all: 0 });
    await alert.getByRole("button", { name: "Check again" }).click();
    await expect(page.getByTestId("see-verdict")).toBeVisible({ timeout: 30_000 });
  });

  test("hostile model output: no advice sentence and no uncited claim reaches the page; the verdict is the engine's", async ({ page }) => {
    const traffic = await toPurchaseStage(page);
    await control("/settings", { bedrock_mode: "hostile" });
    await page.getByTestId("start-investigation").click();
    await expect(page.getByTestId("see-verdict")).toBeVisible({ timeout: 60_000 });
    const stage4 = await page.locator("body").innerText();
    await page.getByTestId("see-verdict").click();
    await expect(page.getByTestId("report")).toBeVisible();
    const job = (await traffic.last("GET", /^\/investigations\/inv-[0-9a-f]+$/, (call) => call.body?.status === "SUCCEEDED")).body;
    expect((await control("/state")).bedrock_calls, "the fake model was really called").toBeGreaterThanOrEqual(2);
    expect(job.agent.mode).toBe("MODEL");
    // In the API response.
    const wire = JSON.stringify(job);
    for (const banned of [/should buy/i, /every rule passes/i, /will rise/i, /is safe/i]) expect(wire, `API response contains ${banned}`).not.toMatch(banned);
    const evidenceIds = new Set(job.result.evidence.map((record: any) => record.evidence_id));
    for (const statement of job.explanation) {
      for (const id of statement.evidence_ids) expect(evidenceIds.has(id), `statement cites ${id}`).toBe(true);
    }
    // On the page, every section open.
    await openAllDetails(page);
    const text = `${stage4}\n${await page.locator("body").innerText()}`;
    for (const banned of [/should buy/i, /every rule passes/i, /will rise/i, /purchase is safe/i]) expect(text, `page shows ${banned}`).not.toMatch(banned);
    await expect(page.getByTestId("explanation-statement")).toHaveCount(job.explanation.length);
    expect(job.explanation.map((statement: any) => statement.rendered_by), "no model-written sentence survived").toEqual(job.explanation.map(() => "TEMPLATE"));
    // The verdict is unchanged by the model: two FAILs.
    await expect(page.getByTestId("verdict-headline")).toHaveText(verdictHeadline(job.result.summary).title);
    expect(job.result.summary.counts.fail).toBe(2);
    await expectReportMatchesJob(page, job);
  });

  test("benign model output: one cited sentence is shown, labelled as the model's, with its evidence", async ({ page }) => {
    const traffic = await toPurchaseStage(page);
    await control("/settings", { bedrock_mode: "benign" });
    await page.getByTestId("start-investigation").click();
    await page.getByTestId("see-verdict").click({ timeout: 60_000 });
    await expect(page.getByTestId("report")).toBeVisible();
    const job = (await traffic.last("GET", /^\/investigations\/inv-[0-9a-f]+$/, (call) => call.body?.status === "SUCCEEDED")).body;
    expect(job.agent.mode).toBe("MODEL");
    const model = job.explanation.filter((statement: any) => statement.rendered_by !== "TEMPLATE");
    expect(model.length).toBe(1);
    expect(model[0].rendered_by).toBe("MODEL_VALIDATED");
    expect(model[0].evidence_ids.length).toBe(1);
    expect(job.result.evidence.some((record: any) => record.evidence_id === model[0].evidence_ids[0])).toBe(true);
    await openAllDetails(page);
    const statements = page.getByTestId("explanation-statement");
    await expect(statements).toHaveCount(job.explanation.length);
    const shown = statements.filter({ hasText: model[0].text });
    await expect(shown).toHaveCount(1);
    test.info().annotations.push({ type: "observed", description: `model sentence as shown: ${(await shown.innerText()).replace(/\s+/g, " ")}` });
    await expect(shown).toContainText(/model/i);
    await expect(shown.getByRole("button", { name: /Evidence/ })).toBeVisible();
    await expect(page.locator("#report-about")).toContainText(job.agent.model_id);
  });

  test("if the gateway sent its 403 without CORS headers, a wrong code would look like an unreachable service", async ({ page }) => {
    await control("/settings", { gateway_errors_have_cors: false });
    await page.goto("/");
    await submitCode(page, "definitely-not-the-code-0000");
    const alert = mainAlert(page);
    await expect(alert).toContainText("The code could not be checked");
    await expect(accessForm(page).heading).toBeVisible();
    expect(await storedKeys(page)).toEqual({ session: [], local: [], cookie: "" });
    expect(await page.content()).not.toContain(CODE);
  });
});
