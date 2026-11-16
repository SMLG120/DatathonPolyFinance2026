import { expect, test, type Page } from "@playwright/test";
import { formatFraction } from "../../../frontend/src/lib/format";
import { verdictHeadline } from "../../../frontend/src/lib/verdict";
import { expectReportMatchesJob } from "./report";
import {
  api,
  CODE,
  confirmOfferedRules,
  control,
  go,
  goToGoals,
  goToPurchase,
  mainAlert,
  openAllDetails,
  openAnalysisDetails,
  openApp,
  openPreview,
  percentTokens,
  resetBackend,
  serverLog,
  setPurchase,
  shot,
  startAndOpenVerdict,
  submitCode,
  accessForm,
  storedKeys,
  Traffic,
  unexplainedFigures,
} from "./helpers";

/**
 * Error paths, timing and the model modes, in the browser against the real handlers. Each test sets the switches of
 * local_api.py it needs (control port) and reads what the page received.
 *
 * On the current interface "Check my idea" moves to step 3 ("Your result") by itself: a finished job shows its
 * report there, a running or failed one says so there, and the steps of a job are on the secondary "Analysis
 * details" screen. The cases below read each state on the screen that shows it. Findings F-01 to F-04 of the first
 * run are fixed in the product; their cases were expected failures and are plain assertions now.
 */
const REPORT_TIMEOUT = { timeout: 60_000 };

async function toPurchaseStage(page: Page): Promise<Traffic> {
  const traffic = new Traffic(page);
  await openApp(page);
  await goToGoals(page);
  await confirmOfferedRules(page);
  await goToPurchase(page);
  // Robert's scenario request (NVDA to 25%) is in the form; its preview is in a panel that is closed by default.
  await expect((await openPreview(page)).getByTestId("cash-after")).toBeVisible();
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

    await expect(page.getByTestId("report"), "no report for a request that was not accepted").toHaveCount(0);
    await alert.getByRole("button", { name: "Try again" }).click();
    await expect(page.getByTestId("report")).toBeVisible(REPORT_TIMEOUT);
    const posts = await investigationPosts();
    expect(posts.map((entry) => entry.status)).toEqual([429, 202]);
    expect(posts[1].idempotency_key, "a retry of the same action reuses its key (contracts/api.md section 6)").toBe(posts[0].idempotency_key);
    const state = await control("/state");
    expect(state.invocations.length, "one worker invocation").toBe(1);
  });

  test("a gateway 429 is explained in the page's own words, not with the gateway's body", async ({ page }) => {
    // Finding F-01 of the first run (the page printed "Too Many Requests"), fixed since: a plain assertion now.
    await toPurchaseStage(page);
    await control("/settings", { throttle_post_investigations: 1 });
    await page.getByTestId("start-investigation").click();
    const alert = mainAlert(page).filter({ hasText: "The investigation could not be started" });
    await expect(alert).toBeVisible();
    // contracts/api.md, Errors: a body that is not the error shape comes from API Gateway; "clients then act on the status code alone".
    await expect(alert).toContainText("The service is receiving too many requests. Wait a moment and try again.");
    await expect(page.locator("body")).not.toContainText("Too Many Requests");
  });

  test("503 WORKER_INVOCATION_FAILED: readable, and 'Try again' starts the investigation once the worker can be invoked", async ({ page }) => {
    // Finding F-03 of the first run (the retry replayed the 503 for ever), fixed since: a plain assertion now.
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
    await expect(page.getByTestId("report")).toBeVisible(REPORT_TIMEOUT);
    await expect(page.getByTestId("report")).toHaveAttribute("data-job-id", retried.body.id);
  });

  test("double-click on 'Check my idea' creates one job", async ({ page }) => {
    await toPurchaseStage(page);
    await control("/settings", { worker_delay_s: 1 });
    await expect(page.getByTestId("start-investigation")).toHaveText("Check my idea");
    await page.getByTestId("start-investigation").dblclick();
    await expect(page.getByTestId("report")).toBeVisible(REPORT_TIMEOUT);
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

    await startAndOpenVerdict(page);
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

  test("409 POLICY_VERSION_CONFLICT on confirm is shown with the service's sentence; nothing is confirmed, and no retry of the same request is offered", async ({ page }) => {
    const { traffic, conflict } = await provokeConflict(page);
    expect(conflict.status).toBe(409);
    expect(conflict.body.error.code).toBe("POLICY_VERSION_CONFLICT");
    expect(conflict.requestBody.base_version).toBe(1);
    const alert = mainAlert(page).filter({ hasText: "The rules could not be confirmed" });
    await expect(alert).toBeVisible();
    await expect(alert).toContainText(conflict.body.error.message);
    // On the first run "Try again" sent the same request on the same stale base version and was refused again
    // (finding F-04). The page no longer offers it: the same request can only be refused again.
    await expect(alert.getByRole("button", { name: "Try again" })).toHaveCount(0);
    await expect(alert.getByTestId("policy-conflict")).toContainText("this stage starts again");
    // Nothing is presented as confirmed, and the refused request stored nothing: version 1 (this page) and
    // version 2 (the other tab) are the only policy objects.
    await expect(page.getByTestId("policy-rule-card")).toHaveCount(0);
    const stored = (await control("/state")).s3_keys.filter((key: string) => key.startsWith("policies/"));
    expect(stored.length, JSON.stringify(stored)).toBe(2);
    expect((await traffic.find("POST", /^\/rules\/confirm$/)).map((call) => call.status), "the user's first confirmation, then the refused one; nothing was sent after it").toEqual([201, 409]);
  });

  test("after a 409 the page drops its policy state and starts the rule stage again (contracts/api.md section 4, rule 8)", async ({ page }) => {
    // Finding F-04 of the first run (the stale version stayed shown as in force), fixed since: a plain assertion now.
    const { traffic, v1, conflict } = await provokeConflict(page);
    expect(conflict.status).toBe(409);
    await expect(page.getByTestId("policy-rule-card"), "the stale version is no longer presented as the confirmed policy").toHaveCount(0);
    // Every rule is a proposal again: the one that had been confirmed and the one that was refused.
    await expect(page.getByTestId("rule-card")).toHaveCount(2);
    // Step 2 says there is no confirmed limit, so nothing can be checked against the stale version.
    await goToPurchase(page);
    await expect(page.getByRole("link", { name: "Set my limits" })).toBeVisible();
    await expect(page.getByTestId("start-investigation")).toHaveAttribute("aria-disabled", "true");
    // Confirming again creates a NEW policy at version 1; it does not write on top of the other tab's version 2.
    await page.getByRole("link", { name: "Set my limits" }).click();
    const again = await traffic.after("POST", /^\/rules\/confirm$/, () => page.getByTestId("confirm-rules").click());
    expect(again.status, JSON.stringify(again.body)).toBe(201);
    expect(again.requestBody.policy_id).toBeNull();
    expect(again.requestBody.base_version).toBeNull();
    expect(again.body.policy.version).toBe(1);
    expect(again.body.policy.policy_id).not.toBe(v1.policy_id);
    await expect(page.getByTestId("policy-rule-card")).toHaveCount(again.body.policy.rules.length);
  });

  test("a job that ends FAILED shows the failure and its code, no verdict, and can be run again with a new key", async ({ page }) => {
    const traffic = await toPurchaseStage(page);
    await control("/fail-next-put", { prefix: "results/" });
    await page.getByTestId("start-investigation").click();
    // Step 3 ("Your result") shows no verdict for it.
    const noVerdict = mainAlert(page).filter({ hasText: "This investigation failed, so there is no verdict" });
    await expect(noVerdict).toBeVisible({ timeout: 60_000 });
    const failed = (await traffic.last("GET", /^\/investigations\/inv-[0-9a-f]+$/, (call) => call.body?.status === "FAILED")).body;
    expect(failed.result).toBeNull();
    expect(failed.explanation).toEqual([]);
    await expect(noVerdict).toContainText(failed.failure.message);
    await expect(page.getByTestId("failure-code")).toContainText(failed.failure.code);
    await expect(page.getByTestId("failure-code")).toContainText("A failed run is not a pass and not a fail.");
    await expect(page.getByTestId("report")).toHaveCount(0);
    await expect(page.getByTestId("verdict-headline")).toHaveCount(0);
    await expect(page.getByTestId("rule-result")).toHaveCount(0);
    for (const kind of ["fail", "unknown", "pass"]) await expect(page.getByTestId(`count-${kind}`)).toHaveCount(0);
    await shot(page, "16-job-failed-no-verdict-live-local-backend-real-data");
    // "Analysis details": the failure, its code, and no way to a verdict.
    await openAnalysisDetails(page);
    const alert = mainAlert(page).filter({ hasText: "The investigation failed" });
    await expect(alert).toBeVisible();
    await expect(alert).toContainText(failed.failure.message);
    await expect(alert).toContainText(failed.failure.code);
    await expect(alert).toContainText("No verdict was produced, so none is shown.");
    await expect(page.getByTestId("see-verdict")).toHaveCount(0);
    // Running it again is a new action: a new key, a new job, which succeeds.
    await alert.getByRole("button", { name: "Run the same request again" }).click();
    await expect(page.getByTestId("see-verdict")).toBeVisible({ timeout: 60_000 });
    const posts = await investigationPosts();
    expect(posts.map((entry) => entry.status)).toEqual([202, 202]);
    expect(posts[1].idempotency_key).not.toBe(posts[0].idempotency_key);
    await page.getByTestId("see-verdict").click();
    await expect(page.getByTestId("report")).toBeVisible();
    await expect(page.getByTestId("report")).not.toHaveAttribute("data-job-id", failed.id);
  });

  test("a worker that never runs: the page waits, then shows the server's DEADLINE_EXCEEDED when the job deadline passes", async ({ page }) => {
    const traffic = await toPurchaseStage(page);
    await control("/settings", { worker_never_delivered: true });
    await page.getByTestId("start-investigation").click();
    // Step 3 while nothing has been reported: it says no verdict exists, and shows none.
    await expect(page.getByRole("heading", { level: 1, name: /Your result/ })).toBeVisible();
    await expect(page.getByRole("main").getByText(/No verdict exists yet\./)).toBeVisible();
    await expect(page.getByTestId("report")).toHaveCount(0);
    await openAnalysisDetails(page);
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
    // And step 3 shows the failure, not a verdict.
    await go(page, "verdict");
    await expect(page.getByTestId("failure-code")).toContainText("DEADLINE_EXCEEDED");
    await expect(page.getByTestId("report")).toHaveCount(0);
    await expect(page.getByTestId("verdict-headline")).toHaveCount(0);
  });

  test("a slow job shows its steps as they complete; polls are 1.5 s apart", async ({ page }) => {
    test.setTimeout(180_000);
    const traffic = await toPurchaseStage(page);
    await control("/settings", { bedrock_mode: "benign", bedrock_stepwise: true, bedrock_delay_s: 1.3 });
    await page.getByTestId("start-investigation").click();
    await openAnalysisDetails(page); // the link step 3 offers while the job runs
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
    await openAnalysisDetails(page);
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
    // Step 3 says the same, and shows no verdict.
    await go(page, "verdict");
    const noAnswer = mainAlert(page).filter({ hasText: "No final answer within the time limit" });
    await expect(noAnswer).toBeVisible();
    await expect(noAnswer).toContainText("No verdict is shown, because none was received.");
    await expect(page.getByTestId("report")).toHaveCount(0);
    await expect(page.getByTestId("verdict-headline")).toHaveCount(0);
    await go(page, "investigation");
    await timedOut.getByRole("button", { name: "Keep waiting" }).click();
    await page.clock.runFor(2_000);
    await expect.poll(async () => (await pollsOf(accepted.id)).length).toBeGreaterThan(stopped);
  });

  test("polling survives 429s from the gateway until the job finishes (contracts/api.md section 7, polling rule 4)", async ({ page }) => {
    // Finding F-02 of the first run (the page gave up after three failed polls), fixed since: a plain assertion now.
    const traffic = await toPurchaseStage(page);
    await control("/settings", { worker_delay_s: 9 });
    await page.getByTestId("start-investigation").click();
    await expect.poll(async () => (await traffic.find("GET", /^\/investigations\/inv-/)).length).toBeGreaterThanOrEqual(1);
    await control("/settings", { throttle_all: 4 });
    // The job finishes server-side after 9 s; a page that keeps polling at 1.5 s sees it within about 12 s.
    await expect(page.getByTestId("report")).toBeVisible({ timeout: 25_000 });
    const throttled = await traffic.find("GET", /^\/investigations\/inv-/, (call) => call.status === 429);
    expect(throttled.length, "every injected 429 was a poll the page made, and it went on after each").toBe(4);
  });

  test("what the page shows when polling hits repeated 429s: it says so in its own words, keeps asking, and shows no verdict meanwhile", async ({ page }) => {
    // On the first run this case recorded the defect F-02 (after three 429s: "The status of the investigation could
    // not be fetched", polling stopped, "Check again"). Polling now continues; this is what is on screen while it does.
    const traffic = await toPurchaseStage(page);
    await control("/settings", { worker_delay_s: 9 });
    await page.getByTestId("start-investigation").click();
    await expect.poll(async () => (await traffic.find("GET", /^\/investigations\/inv-/)).length).toBeGreaterThanOrEqual(1);
    await openAnalysisDetails(page);
    await control("/settings", { throttle_all: 4 });
    const retrying = page.getByTestId("polling-retrying");
    await expect(retrying).toBeVisible({ timeout: 20_000 });
    await expect(retrying).toContainText("The service is receiving too many requests. Wait a moment and try again.");
    await expect(retrying).toContainText("It is asked again every 1.5 seconds until the time limit of 180 seconds.");
    await expect(page.locator("body")).not.toContainText("Too Many Requests");
    await expect(mainAlert(page).filter({ hasText: "The status of the investigation could not be fetched" }), "the page has not given up").toHaveCount(0);
    await expect(page.getByTestId("see-verdict"), "no verdict while the status is unknown").toHaveCount(0);
    // The throttling ends by itself (4 requests); the page is still asking, so the finished job arrives without a click.
    await expect(page.getByTestId("see-verdict")).toBeVisible({ timeout: 30_000 });
    await expect(retrying).toHaveCount(0);
    const throttled = await traffic.find("GET", /^\/investigations\/inv-/, (call) => call.status === 429);
    expect(throttled.length, "polls answered 429").toBe(4);
  });

  test("hostile model output: no advice sentence and no uncited claim reaches the page; the verdict is the engine's", async ({ page }) => {
    const traffic = await toPurchaseStage(page);
    await control("/settings", { bedrock_mode: "hostile" });
    await startAndOpenVerdict(page);
    // The steps the job reported ("Analysis details"), read before the report.
    await openAnalysisDetails(page);
    await expect(page.getByTestId("see-verdict")).toBeVisible();
    await expect(page.getByTestId("timeline-step").first()).toBeVisible();
    const stage4 = await page.locator("body").innerText();
    await page.getByTestId("see-verdict").click();
    await expect(page.getByTestId("report")).toBeVisible();
    const job = (await traffic.last("GET", /^\/investigations\/inv-[0-9a-f]+$/, (call) => call.body?.status === "SUCCEEDED")).body;
    expect((await control("/state")).bedrock_calls, "the fake model was really called").toBeGreaterThanOrEqual(2);
    expect(job.agent.mode).toBe("MODEL");
    // In the API response.
    const wire = JSON.stringify(job);
    for (const banned of [/should buy/i, /every rule passes/i, /will rise/i, /is safe/i, /SMUGGLED/]) expect(wire, `API response contains ${banned}`).not.toMatch(banned);
    const evidenceIds = new Set(job.result.evidence.map((record: any) => record.evidence_id));
    for (const statement of job.explanation) {
      for (const id of statement.evidence_ids) expect(evidenceIds.has(id), `statement cites ${id}`).toBe(true);
    }
    // On the page, every section open.
    await openAllDetails(page);
    const text = `${stage4}\n${await page.locator("body").innerText()}`;
    for (const banned of [/should buy/i, /every rule passes/i, /will rise/i, /purchase is safe/i, /SMUGGLED/]) expect(text, `page shows ${banned}`).not.toMatch(banned);
    await expect(page.getByTestId("explanation-statement")).toHaveCount(job.explanation.length);
    expect(job.explanation.map((statement: any) => statement.rendered_by), "no model-written sentence survived").toEqual(job.explanation.map(() => "TEMPLATE"));
    // The verdict is unchanged by the model: two FAILs.
    await expect(page.getByTestId("verdict-headline")).toHaveText(verdictHeadline(job.result.summary).title);
    expect(job.result.summary.counts.fail).toBe(2);
    await expectReportMatchesJob(page, job);
  });

  test("benign model output: the record the model pointed at is shown in a sentence the service wrote, with its evidence, and nothing is labelled as written by a model", async ({ page }) => {
    // When this case was written a validated model sentence was returned (`rendered_by: MODEL_VALIDATED`) and shown
    // as the model's. Since validator finding F-18 the model can only SELECT an evidence record; the service writes
    // the sentence from that record (backend/agents/explain.py). Same intent, on the current design.
    const traffic = await toPurchaseStage(page);
    await control("/settings", { bedrock_mode: "benign" });
    await startAndOpenVerdict(page);
    const job = (await traffic.last("GET", /^\/investigations\/inv-[0-9a-f]+$/, (call) => call.body?.status === "SUCCEEDED")).body;
    expect((await control("/state")).bedrock_calls, "the fake model was really called").toBeGreaterThanOrEqual(2);
    expect(job.agent.mode).toBe("MODEL");
    expect(job.explanation.map((statement: any) => statement.rendered_by), "no model-written sentence is returned").toEqual(job.explanation.map(() => "TEMPLATE"));
    // The one selection of the scripted model became one sentence about one evidence record of the result.
    const selected = job.explanation.filter((statement: any) => statement.text.startsWith("Evidence looked at during the investigation:"));
    expect(selected.length, JSON.stringify(job.explanation.map((statement: any) => statement.text))).toBe(1);
    expect(selected[0].evidence_ids.length).toBe(1);
    const record = job.result.evidence.find((candidate: any) => candidate.evidence_id === selected[0].evidence_ids[0]);
    expect(record, "the sentence cites a record of the result").toBeTruthy();
    expect(percentTokens(selected[0].text).length, `the sentence prints the record's value: ${selected[0].text}`).toBeGreaterThan(0);
    expect(unexplainedFigures(selected[0].text, [record]), "figures of the sentence that its evidence record does not hold").toEqual([]);
    await openAllDetails(page);
    const statements = page.getByTestId("explanation-statement");
    await expect(statements).toHaveCount(job.explanation.length);
    const shown = statements.filter({ hasText: selected[0].text });
    await expect(shown).toHaveCount(1);
    test.info().annotations.push({ type: "observed", description: `selected sentence as shown: ${(await shown.innerText()).replace(/\s+/g, " ")}` });
    await expect(shown).toHaveAttribute("data-rendered-by", "TEMPLATE");
    await expect(shown).toContainText("Built by the service from the figures of the result.");
    await expect(page.getByTestId("explanation")).not.toContainText(/(written|worded|said) by (a|the) model/i);
    await expect(shown.getByRole("button", { name: /Evidence/ })).toBeVisible();
    // Opening it shows that record.
    await shown.getByRole("button", { name: /Evidence/ }).click();
    const drawer = page.getByRole("dialog");
    await expect(drawer.locator(`[data-evidence-id="${record.evidence_id}"]`)).toHaveCount(1);
    await page.keyboard.press("Escape");
    // How the job was run is said, with the model's id.
    await expect(page.locator("#report-about")).toContainText(job.agent.model_id);
    // The verdict is the engine's whatever the model selected.
    await expectReportMatchesJob(page, job);
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
