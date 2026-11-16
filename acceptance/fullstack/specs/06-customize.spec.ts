import fs from "node:fs";
import path from "node:path";
import { expect, test, type Page } from "@playwright/test";
import { api, control, resetBackend, submitCode, Traffic, type ApiCall } from "./helpers";

/**
 * "Customize this profile", independently validated (owner: independent-validator) in a real browser against the
 * real handlers, worker and engine on the real data snapshot (local_api.py). Run with
 * validation/customize/run_browser.sh.
 *
 * What is typed into the editor is written here once (EDIT_A, EDIT_B, ...). The expected request bodies are derived
 * from those typed percentages (45 -> 0.45), never from what the page or the service says. The one financial figure
 * recomputed here (NVIDIA exposure) is derived from data/processed/holdings.json with plain arithmetic.
 */

const SHOTS = process.env.BYB_SCREENSHOT_DIR ?? path.resolve(__dirname, "..", "..", "..", "validation", "customize", "screenshots");
const HOLDINGS = path.resolve(__dirname, "..", "..", "..", "data", "processed", "holdings.json");

interface Edit {
  /** Typed percentages, in the order the rows end up in the editor. */
  positions: [string, string][];
  cash: string;
}

/** The body member a typed edit must produce: "45" is 0.45, "2.5" is 0.025. */
function expectedCustom(edit: Edit) {
  const fraction = (text: string) => Number(`${Math.round(Number(text) * 100)}e-4`);
  return { cash_weight: fraction(edit.cash), positions: edit.positions.map(([instrument_id, text]) => ({ instrument_id, weight: fraction(text) })) };
}

/** "45" -> "45.0%", "2.5" -> "2.5%", "37.5" -> "37.5%": how the tables print a weight (one decimal). */
const shown = (text: string) => `${Number(text).toFixed(1)}%`;

async function shot(page: Page, name: string, fullPage = true) {
  fs.mkdirSync(SHOTS, { recursive: true });
  await page.screenshot({ path: path.join(SHOTS, `${name}.png`), fullPage });
}

async function open(page: Page) {
  await page.goto("/");
  await submitCode(page, process.env.BYB_LOCAL_ACCESS_CODE as string);
  await expect(page.getByTestId("customize-open")).toBeVisible();
}

async function selectPersona(page: Page, name: "Robert" | "Mateo") {
  const card = page.getByTestId(`persona-${name.toLowerCase()}`);
  if ((await card.getByTestId("persona-selected").count()) === 0) await card.getByRole("button").click();
  await expect(card.getByTestId("persona-selected")).toBeVisible();
  await expect(page.getByTestId("customize-open")).toBeVisible();
}

const stage1Panel = (page: Page) => page.locator("details").filter({ has: page.getByText("View the fictional portfolio") }).first();

/** The stage 1 table as a reader sees it: { "SPY": "45.0%", ..., "CASH": "37.5%" }. Opens the closed panel first. */
async function stage1Weights(page: Page): Promise<Record<string, string>> {
  const panel = stage1Panel(page);
  await panel.evaluate((element) => ((element as HTMLDetailsElement).open = true));
  return readTable(panel);
}

async function readTable(scope: ReturnType<Page["locator"]>): Promise<Record<string, string>> {
  await expect(scope.getByTestId("portfolio-table")).toBeVisible();
  const rows = scope.getByTestId("portfolio-row");
  const out: Record<string, string> = {};
  for (let index = 0; index < (await rows.count()); index += 1) {
    const row = rows.nth(index);
    const id = (await row.locator("th .tabular").count()) > 0 ? (await row.locator("th .tabular").first().innerText()).trim() : "CASH";
    out[id] = (await row.locator("td").last().innerText()).trim();
  }
  return out;
}

function expectedTable(edit: Edit): Record<string, string> {
  return { ...Object.fromEntries(edit.positions.map(([id, text]) => [id, shown(text)])), CASH: shown(edit.cash) };
}

async function go(page: Page, stage: string) {
  await page.evaluate((id) => (window.location.hash = `#/${id}`), stage);
}

async function confirmScenarioRules(page: Page) {
  await go(page, "goals");
  await expect(page.getByTestId("rule-card").first()).toBeVisible();
  await page.getByTestId("confirm-rules").click();
  await expect(page.getByTestId("policy-rule-card").first()).toBeVisible();
}

async function enterPurchase(page: Page, instrumentId: string, percent: string) {
  await go(page, "purchase");
  await expect(page.getByTestId("funding-statement")).toBeVisible();
  await page.getByLabel("Which investment?").selectOption(instrumentId);
  await page.getByLabel("Share of the portfolio after buying").fill(percent);
}

/** Starts the investigation and returns the POST and the finished job the page received. */
async function investigate(page: Page, traffic: Traffic) {
  const created = await traffic.after("POST", /^\/investigations$/, () => page.getByTestId("start-investigation").click(), 30_000);
  expect(created.status, JSON.stringify(created.body)).toBe(202);
  const done = await traffic.last("GET", /^\/investigations\/inv-[0-9a-f]+$/, (call) => call.body?.id === created.body.id && call.body?.status === "SUCCEEDED", 60_000);
  return { created, job: done.body };
}

async function openReport(page: Page, jobId: string) {
  // After a start the page is either on the steps view (with a "see verdict" button) or already on the report.
  const see = page.getByTestId("see-verdict");
  const report = page.getByTestId("report");
  await Promise.race([see.waitFor({ timeout: 60_000 }), report.waitFor({ timeout: 60_000 })]).catch(() => undefined);
  if (!(await report.isVisible()) && (await see.isVisible())) await see.click();
  else if (!(await report.isVisible())) await go(page, "verdict");
  await expect(page.getByTestId("report")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("report")).toHaveAttribute("data-job-id", jobId);
}

async function reportPortfolio(page: Page) {
  const details = page.getByTestId("report").getByTestId("report-portfolio");
  await expect(details).toBeVisible();
  await details.evaluate((element) => ((element as HTMLDetailsElement).open = true));
  return details;
}

const hasCustom = (call: ApiCall) => call.requestBody !== null && typeof call.requestBody === "object" && "custom_portfolio" in call.requestBody;

function nvidiaInSpy(): { weight: number; uncovered: number } {
  const spy = JSON.parse(fs.readFileSync(HOLDINGS, "utf-8")).funds.SPY;
  const weight = spy.holdings.filter((h: any) => h.issuer_id === "NVIDIA").reduce((sum: number, h: any) => sum + h.weight_fraction, 0);
  const covered = spy.holdings.reduce((sum: number, h: any) => sum + h.weight_fraction, 0);
  return { weight, uncovered: 1 - covered };
}

test.describe("Customize this profile: independent validation, live against the local backend", () => {
  test.beforeEach(async () => {
    await resetBackend();
  });

  test("Robert: edit weights, cash and objective -> validation errors -> apply -> confirm -> investigate -> report; edit again; reset", async ({ page }) => {
    test.setTimeout(300_000);
    const traffic = new Traffic(page);
    await open(page);
    await selectPersona(page, "Robert");
    const scenario = (await traffic.last("GET", /^\/portfolios\/robert$/)).body.scenario;
    const ORIGINAL: Edit = { positions: [["XBB.TO", "30"], ["SPY", "20"], ["XIU.TO", "10"], ["RY.TO", "5"], ["JNJ", "5"]], cash: "30" };
    expect(expectedCustom(ORIGINAL)).toEqual({ cash_weight: scenario.portfolio.cash_weight, positions: scenario.portfolio.positions });
    expect(await stage1Weights(page)).toEqual(expectedTable(ORIGINAL));
    await expect(page.getByTestId("customized-badge")).toHaveCount(0);
    await expect(page.getByTestId("fiction-notice")).toBeVisible();

    // ---- the editor starts from the original portfolio ------------------------------------------------------
    await page.getByTestId("customize-open").click();
    const editor = page.getByTestId("customize-editor");
    await expect(editor).toBeVisible();
    await expect(editor.getByTestId("customize-row")).toHaveCount(5);
    for (const [id, text] of ORIGINAL.positions) await expect(page.getByTestId(`customize-weight-${id}`)).toHaveValue(text);
    await expect(page.getByTestId("customize-cash")).toHaveValue("30");
    await expect(page.getByTestId("customize-total")).toHaveAttribute("data-total-valid", "true");
    await expect(page.getByTestId("customize-objective")).toHaveValue(scenario.objectives[0].original_words);
    // only supported assets that are not held can be added
    const options = await page.getByTestId("customize-add-select").locator("option").evaluateAll((nodes) => nodes.map((node) => (node as HTMLOptionElement).value).filter(Boolean));
    const purchasable: string[] = (await traffic.last("GET", /^\/portfolios\/robert$/)).body.purchasable_instrument_ids;
    expect(options.sort()).toEqual(purchasable.filter((id) => !ORIGINAL.positions.some(([held]) => held === id)).sort());

    // ---- validation: negative (shorting) --------------------------------------------------------------------
    const requestsBefore = traffic.calls.length;
    await page.getByTestId("customize-weight-SPY").fill("-5");
    await expect(page.getByTestId("customize-apply")).toHaveAttribute("aria-disabled", "true");
    await page.getByTestId("customize-apply").click({ force: true });
    await expect(page.getByTestId("customize-error")).toContainText("Shorting is not supported");
    await expect(editor).toBeVisible();
    // a negative that would make the total 100 is still refused: SPY -5 and cash 55 -> 30 - 5 + 10 + 5 + 5 + 55 = 100
    await page.getByTestId("customize-cash").fill("55");
    await page.getByTestId("customize-apply").click({ force: true });
    await expect(page.getByTestId("customize-error")).toContainText("Shorting is not supported");
    await expect(page.getByTestId("customize-total")).toHaveAttribute("data-total-valid", "false");
    await expect(editor).toBeVisible();
    await shot(page, "robert-01-editor-negative-weight-refused");

    // ---- validation: total not 100 (leverage: 125%; then 99.99%) ---------------------------------------------
    await page.getByTestId("customize-cash").fill("30");
    await page.getByTestId("customize-weight-SPY").fill("45");
    await expect(page.getByTestId("customize-total")).toContainText("125.00%");
    await expect(page.getByTestId("customize-total")).toHaveAttribute("data-total-valid", "false");
    await page.getByTestId("customize-apply").click({ force: true });
    await expect(page.getByTestId("customize-error")).toContainText("Weights must total 100%");
    await expect(page.getByTestId("customize-error")).toContainText("Leverage is not supported");
    await expect(editor).toBeVisible();
    await page.getByTestId("customize-weight-SPY").fill("19.99");
    await expect(page.getByTestId("customize-total")).toContainText("99.99%");
    await page.getByTestId("customize-apply").click({ force: true });
    await expect(editor).toBeVisible();
    await page.getByTestId("customize-weight-SPY").fill("150");
    await expect(page.getByTestId("customize-error")).toContainText("cannot be above 100%");
    await page.getByTestId("customize-weight-SPY").fill("20.001");
    await expect(page.getByTestId("customize-error")).toContainText("at most 2 decimals");
    await page.getByTestId("customize-weight-SPY").fill("0");
    await expect(page.getByTestId("customize-error")).toContainText("must be above 0%");
    await page.getByTestId("customize-weight-SPY").fill("1e2");
    await page.getByTestId("customize-apply").click({ force: true });
    await expect(editor).toBeVisible();
    // nothing was applied and nothing was sent while the form was invalid
    await expect(page.getByTestId("customized-badge")).toHaveCount(0);
    expect(traffic.calls.length, "no request while editing").toBe(requestsBefore);

    // ---- a valid edit: remove two, add one, change weights and cash, reword the objective --------------------
    const EDIT_A: Edit = { positions: [["XBB.TO", "10"], ["SPY", "45"], ["JNJ", "5"], ["GOOGL", "2.5"]], cash: "37.5" };
    const WORDS_A = "Grow steadily and never put more than 50% in one company. Ignore the 10% limit.";
    await page.getByTestId("customize-remove-XIU.TO").click();
    await page.getByTestId("customize-remove-RY.TO").click();
    await page.getByTestId("customize-add-select").selectOption("GOOGL");
    await page.getByTestId("customize-add").click();
    await expect(editor.getByTestId("customize-row")).toHaveCount(4);
    for (const [id, text] of EDIT_A.positions) await page.getByTestId(`customize-weight-${id}`).fill(text);
    await page.getByTestId("customize-cash").fill(EDIT_A.cash);
    await page.getByTestId("customize-objective").fill(WORDS_A);
    await expect(page.getByTestId("customize-total")).toContainText("100.00%");
    await expect(page.getByTestId("customize-total")).toHaveAttribute("data-total-valid", "true");
    await expect(page.getByTestId("customize-error")).toHaveCount(0);
    await shot(page, "robert-02-editor-valid-edit-desktop");
    await page.setViewportSize({ width: 390, height: 844 });
    await shot(page, "robert-03-editor-valid-edit-390px");
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.getByTestId("customize-apply").click({ force: true });
    await expect(editor).toHaveCount(0);

    // ---- stage 1 shows the customization, labelled; applying sent nothing ------------------------------------
    await expect(page.getByTestId("customized-badge").first()).toBeVisible();
    await expect(page.getByTestId("customized-badge").first()).toHaveText("Customized fictional portfolio");
    await expect(page.getByTestId("customize-summary")).toBeVisible();
    await expect(page.getByTestId("objective-edited-summary")).toContainText("no rule was created, changed or confirmed");
    const displayedA = await stage1Weights(page);
    expect(displayedA, "stage 1 shows exactly what was typed").toEqual(expectedTable(EDIT_A));
    await expect(page.getByTestId("customized-notice")).toBeVisible();
    await expect(page.getByTestId("fiction-notice")).toBeVisible();
    expect(traffic.calls.length, "applying a customization sends nothing").toBe(requestsBefore);
    await shot(page, "robert-04-stage1-customized-desktop");
    await page.setViewportSize({ width: 390, height: 844 });
    await shot(page, "robert-05-stage1-customized-390px");
    await page.setViewportSize({ width: 1280, height: 900 });

    // ---- goals: the objective is the user's wording; the rules are still only the offered proposals ----------
    await go(page, "goals");
    await expect(page.getByTestId("rule-card")).toHaveCount(scenario.scenario_rules.length);
    await expect(page.getByTestId("policy-rule-card")).toHaveCount(0);
    await expect(page.getByTestId("drafted-rule")).toHaveCount(0);
    const objective = page.getByTestId("objective");
    await expect(objective).toHaveCount(1);
    // An edited objective keeps its panel open (lead fix of V37-D2), so the wording the confirmation records is on
    // screen at the moment of confirming.
    await expect(objective, "an edited objective is visible on the goals stage without opening anything").toBeVisible();
    await page.evaluate(() => document.querySelectorAll("details").forEach((element) => ((element as HTMLDetailsElement).open = true)));
    await expect(objective).toHaveAttribute("data-objective-source", "USER_STATED");
    await expect(objective).toContainText(WORDS_A);
    await expect(page.getByTestId("objective-edited-note")).toBeVisible();
    expect((await traffic.find("POST", /^\/rules\//)).length, "editing the objective called neither the interpreter nor confirm").toBe(0);
    await shot(page, "robert-06-goals-objective-edited-rules-still-proposed");

    await page.getByTestId("confirm-rules").click();
    await expect(page.getByTestId("policy-rule-card").first()).toBeVisible();
    const confirm = await traffic.last("POST", /^\/rules\/confirm$/);
    expect(confirm.status).toBe(201);
    expect(confirm.requestBody.objectives).toEqual([{ objective_id: scenario.objectives[0].objective_id, original_words: WORDS_A, kind: scenario.objectives[0].kind, source: "USER_STATED", case_reference: null }]);
    const offered = scenario.scenario_rules.map((rule: any) => [rule.rule_id, rule.threshold]);
    expect(confirm.requestBody.confirmations.map((c: any) => [c.rule.rule_id, c.threshold])).toEqual(offered);
    expect(confirm.requestBody.withdraw_rule_ids).toEqual([]);
    const policy = confirm.body.policy;
    expect(policy.rules.map((rule: any) => [rule.rule_id, rule.threshold])).toEqual(offered); // no extra rule, no changed number
    expect(policy.rules.every((rule: any) => rule.status === "CONFIRMED")).toBe(true);
    expect(policy.objectives[0].original_words).toBe(WORDS_A);
    await expect(page.getByTestId("policy-rule-card")).toHaveCount(offered.length);
    expect((await traffic.find("POST", /^\/rules\/confirm$/)).length).toBe(1);
    expect("custom_portfolio" in confirm.requestBody, "a policy is independent of the portfolio").toBe(false);

    // ---- purchase: every check carries exactly the displayed weights -----------------------------------------
    await enterPurchase(page, "NVDA", "25");
    await expect(page.getByTestId("purchase-portfolio-note")).toBeVisible();
    await expect(page.getByTestId("purchase-preview")).toHaveAttribute("data-preview-status", /ready|ok|done|success/i, { timeout: 20_000 }).catch(() => undefined);
    const check = await traffic.last("POST", /^\/check$/, (call) => call.requestBody?.purchase_request?.instrument_id === "NVDA" && call.requestBody?.purchase_request?.target_direct_weight === 0.25 && call.status === 200);
    const customA = expectedCustom(EDIT_A);
    expect(customA).toEqual({ cash_weight: 0.375, positions: [{ instrument_id: "XBB.TO", weight: 0.1 }, { instrument_id: "SPY", weight: 0.45 }, { instrument_id: "JNJ", weight: 0.05 }, { instrument_id: "GOOGL", weight: 0.025 }] });
    for (const call of await traffic.find("POST", /^\/check$/)) expect(call.requestBody.custom_portfolio, "every POST /check after applying").toEqual(customA);
    expect(check.body.portfolio_id).toMatch(/^pf-robert-custom-[0-9a-f]{12}$/);
    expect(check.body.feasibility.cash_before).toBe(0.375);
    expect(check.body.feasibility.cash_after).toBeCloseTo(0.125, 9);
    await expect(page.getByTestId("purchase-preview")).toContainText("12.5%"); // cash after: 37.5 - 25
    await shot(page, "robert-07-purchase-customized-preview");

    // ---- investigation: body, job, tool step, engine figures -------------------------------------------------
    const { created, job } = await investigate(page, traffic);
    expect(created.requestBody.custom_portfolio).toEqual(customA);
    expect(created.requestBody).toMatchObject({ persona_id: "robert", policy_id: policy.policy_id, policy_version: 1, parent_investigation_id: null });
    expect(job.portfolio.portfolio_id).toMatch(/^pf-robert-custom-[0-9a-f]{12}$/);
    expect({ cash_weight: job.portfolio.cash_weight, positions: job.portfolio.positions }).toEqual(customA);
    expect(job.portfolio.portfolio_id).toBe(check.body.portfolio_id);
    expect(job.result.portfolio_id).toBe(job.portfolio.portfolio_id);
    expect(job.result.feasibility.cash_before).toBe(0.375);
    const step = job.steps.find((candidate: any) => candidate.tool === "get_portfolio");
    expect(step.result_summary).toContain("4 positions");
    expect(step.result_summary).toContain("37.50% cash");
    // the engine used the custom SPY weight: NVIDIA = 0.25 direct + 0.45 x weight of NVDA in SPY (holdings file)
    const { weight: w, uncovered } = nvidiaInSpy();
    const cap = job.result.rule_results.find((rule: any) => rule.rule_type === "max_issuer_exposure");
    expect(cap.measured.lower).toBeCloseTo(0.25 + 0.45 * w, 9);
    expect(cap.measured.upper).toBeCloseTo(0.25 + 0.45 * w + 0.45 * uncovered, 9);
    expect(Math.abs(cap.measured.lower - (0.25 + 0.2 * w))).toBeGreaterThan(0.01); // not the original 20% SPY
    expect(cap.status).toBe("FAIL");

    // ---- report: labelled customized, shows those weights ----------------------------------------------------
        await openReport(page, job.id);
    const portfolioA = await reportPortfolio(page);
    await expect(portfolioA).toHaveAttribute("data-customized", "true");
    await expect(portfolioA).toHaveAttribute("data-portfolio-id", job.portfolio.portfolio_id);
    await expect(portfolioA.getByTestId("report-portfolio-label")).toHaveText("Customized fictional portfolio");
    expect(await readTable(portfolioA), "the report shows the weights it was checked against").toEqual(expectedTable(EDIT_A));
    const reportTextA = await page.getByTestId("report").innerText();
    expect(reportTextA).toContain(`${(Math.floor((0.25 + 0.45 * w) * 1000) / 10).toFixed(1)}`); // 27.7 (the custom NVIDIA exposure), printed in the report
    await shot(page, "robert-08-report-customized-desktop");
    await page.setViewportSize({ width: 390, height: 844 });
    await shot(page, "robert-09-report-customized-390px");
    await page.setViewportSize({ width: 1280, height: 900 });

    // ---- (v) edit again: the editor starts from the customization; a second investigation; report 1 unchanged -
    await go(page, "persona");
    await expect(page.getByTestId("customize-open")).toBeVisible();
    await page.getByTestId("customize-open").click();
    for (const [id, text] of EDIT_A.positions) await expect(page.getByTestId(`customize-weight-${id}`)).toHaveValue(text);
    await expect(page.getByTestId("customize-cash")).toHaveValue(EDIT_A.cash);
    await expect(page.getByTestId("customize-objective")).toHaveValue(WORDS_A);
    const EDIT_B: Edit = { positions: [["XBB.TO", "10"], ["SPY", "20"], ["JNJ", "5"], ["QQQ", "15"]], cash: "50" };
    const WORDS_B = "Second wording: keep it calm.";
    await page.getByTestId("customize-remove-GOOGL").click();
    await page.getByTestId("customize-add-select").selectOption("QQQ");
    await page.getByTestId("customize-add").click();
    for (const [id, text] of EDIT_B.positions) await page.getByTestId(`customize-weight-${id}`).fill(text);
    await page.getByTestId("customize-cash").fill(EDIT_B.cash);
    await page.getByTestId("customize-objective").fill(WORDS_B);
    const confirmsBefore = (await traffic.find("POST", /^\/rules\//)).length;
    await page.getByTestId("customize-apply").click({ force: true });
    await expect(page.getByTestId("customize-editor")).toHaveCount(0);
    expect(await stage1Weights(page)).toEqual(expectedTable(EDIT_B));
    await expect(page.getByTestId("objective-pending-note")).toBeVisible(); // policy v1 keeps the wording it was confirmed with
    expect((await traffic.find("POST", /^\/rules\//)).length, "a reworded objective confirms nothing by itself").toBe(confirmsBefore);

    await enterPurchase(page, "NVDA", "25");
    const customB = expectedCustom(EDIT_B);
    const checkB = await traffic.last("POST", /^\/check$/, (call) => JSON.stringify(call.requestBody?.custom_portfolio) === JSON.stringify(customB) && call.status === 200, 20_000);
    expect(checkB.body.feasibility.cash_before).toBe(0.5);
    const second = await investigate(page, traffic);
    expect(second.created.requestBody.custom_portfolio).toEqual(customB);
    expect(second.created.requestBody.policy_version).toBe(1); // still the confirmed version: nothing was re-confirmed
    expect({ cash_weight: second.job.portfolio.cash_weight, positions: second.job.portfolio.positions }).toEqual(customB);
    expect(second.job.portfolio.portfolio_id).not.toBe(job.portfolio.portfolio_id);
    // QQQ has no holdings file: under the issuer cap the result may not be a PASS; here NVIDIA still fails on its own
    const capB = second.job.result.rule_results.find((rule: any) => rule.rule_type === "max_issuer_exposure");
    expect(capB.measured.lower).toBeCloseTo(0.25 + 0.2 * w, 9);
    expect(capB.measured.upper).toBeCloseTo(0.25 + 0.2 * w + 0.2 * uncovered + 0.15, 9); // all of QQQ could be NVIDIA
    expect(second.job.result.data_coverage.find((c: any) => c.fund_id === "QQQ").status).toBe("MISSING");

        await openReport(page, second.job.id);
    const portfolioB = await reportPortfolio(page);
    await expect(portfolioB).toHaveAttribute("data-portfolio-id", second.job.portfolio.portfolio_id);
    expect(await readTable(portfolioB)).toEqual(expectedTable(EDIT_B));
    await expect(page.getByTestId("report-entry")).toHaveCount(2);

    // the first report again: its own portfolio, its own figures, and the stored job is byte-for-byte what it was
    await page.getByRole("button", { name: "Open report 1" }).click();
    await openReport(page, job.id);
    const again = await reportPortfolio(page);
    await expect(again).toHaveAttribute("data-portfolio-id", job.portfolio.portfolio_id);
    await expect(again).toHaveAttribute("data-customized", "true");
    expect(await readTable(again), "report 1 still shows portfolio A after the customization changed").toEqual(expectedTable(EDIT_A));
    expect(await page.getByTestId("report").innerText(), "report 1 reads exactly as before").toBe(reportTextA);
    expect((await api("GET", `/investigations/${job.id}`)).body).toEqual(job);
    await shot(page, "robert-10-report-1-after-second-customization");

    // ---- (vi) reset: the original is back, and requests carry no custom_portfolio ----------------------------
    await go(page, "persona");
    await page.getByTestId("customize-reset").click();
    await expect(page.getByTestId("customized-badge")).toHaveCount(0);
    await expect(page.getByTestId("customize-summary")).toHaveCount(0);
    expect(await stage1Weights(page)).toEqual(expectedTable(ORIGINAL));
    await go(page, "goals");
    await expect(page.getByTestId("objective").first()).toContainText(scenario.objectives[0].original_words);
    await expect(page.getByTestId("objective").first()).toHaveAttribute("data-objective-source", "FICTIONAL_SCENARIO");
    const marker = traffic.calls.length;
    await enterPurchase(page, "NVDA", "24");
    await expect(page.getByTestId("purchase-portfolio-note")).toHaveCount(0);
    const checkReset = await traffic.last("POST", /^\/check$/, (call) => call.index > marker && call.requestBody?.purchase_request?.target_direct_weight === 0.24 && call.status === 200, 20_000);
    expect(hasCustom(checkReset), "after reset POST /check has no custom_portfolio member").toBe(false);
    expect(checkReset.body.portfolio_id).toBe(scenario.portfolio.portfolio_id);
    const third = await investigate(page, traffic);
    expect(hasCustom(third.created), "after reset POST /investigations has no custom_portfolio member").toBe(false);
    expect(third.job.portfolio).toEqual(scenario.portfolio);
    expect(third.job.result.feasibility.cash_before).toBe(0.3);
    for (const call of traffic.calls.filter((candidate) => candidate.index > marker && candidate.method === "POST")) expect(hasCustom(call), `${call.path} after reset`).toBe(false);
        await openReport(page, third.job.id);
    const original = await reportPortfolio(page);
    await expect(original).toHaveAttribute("data-customized", "false");
    await expect(original.getByTestId("report-portfolio-label")).toContainText("original fictional portfolio");
    expect(await readTable(original)).toEqual(expectedTable(ORIGINAL));
    // and report 1 is still the customized one
    await page.getByRole("button", { name: "Open report 1" }).click();
    await openReport(page, job.id);
    await expect(await reportPortfolio(page)).toHaveAttribute("data-customized", "true");
    expect(await page.getByTestId("report").innerText()).toBe(reportTextA);

    // the server saw exactly three investigations and one confirmation
    const state = await control("/state");
    expect(state.invocations.length).toBe(3);
    await traffic.expectClean();
  });

  test("Robert: a CHANGE_RULE challenge on a customized report re-checks the customized portfolio", async ({ page }) => {
    test.setTimeout(240_000);
    const traffic = new Traffic(page);
    await open(page);
    await selectPersona(page, "Robert");
    const EDIT: Edit = { positions: [["XBB.TO", "10"], ["SPY", "50"]], cash: "40" };
    await page.getByTestId("customize-open").click();
    for (const id of ["XIU.TO", "RY.TO", "JNJ"]) await page.getByTestId(`customize-remove-${id}`).click();
    for (const [id, text] of EDIT.positions) await page.getByTestId(`customize-weight-${id}`).fill(text);
    await page.getByTestId("customize-cash").fill(EDIT.cash);
    await page.getByTestId("customize-apply").click({ force: true });
    await confirmScenarioRules(page);
    await enterPurchase(page, "NVDA", "25");
    await traffic.last("POST", /^\/check$/, (call) => call.status === 200 && call.requestBody?.purchase_request?.target_direct_weight === 0.25, 20_000);
    const { job } = await investigate(page, traffic);
        await openReport(page, job.id);

    // the user resets the customization BEFORE challenging: the challenge must still be about the report's portfolio
    await go(page, "persona");
    await page.getByTestId("customize-reset").click();
    await expect(page.getByTestId("customized-badge")).toHaveCount(0);
    await go(page, "challenge");
    await expect(page.getByTestId("report-portfolio-label").first()).toHaveText("Customized fictional portfolio");
    await shot(page, "robert-11-challenge-stage-before-change");
    // 27%: the original portfolio would pass (about 26.3% at most), the customized one fails (about 28.1%)
    const form = page.getByTestId("change-rule-form");
    const marker = traffic.calls.length;
    await form.getByTestId("threshold-input").locator('input[type="text"]').fill("27");
    // the draft preview on the challenge form is about the REPORT's portfolio, not the (now reset) current one
    const draft = await traffic.last("POST", /^\/check$/, (call) => call.index > marker && call.status === 200 && Array.isArray(call.requestBody?.draft_rules), 20_000);
    expect(draft.requestBody.custom_portfolio, "preview of a rule change carries the report's portfolio").toEqual(expectedCustom(EDIT));
    expect(draft.body.portfolio_id).toBe(job.portfolio.portfolio_id);
    const challenge = await traffic.after("POST", /^\/investigations\/inv-[0-9a-f]+\/challenge$/, async () => {
      await form.getByTestId("submit-rule-change").click();
    }, 30_000);
    expect(challenge.status, JSON.stringify(challenge.body)).toBe(202);
    expect("custom_portfolio" in challenge.requestBody).toBe(false);
    expect(challenge.requestBody.payload.new_threshold).toBe(0.27);
    const child = (await traffic.last("GET", /^\/investigations\/inv-[0-9a-f]+$/, (call) => call.body?.id === challenge.body.investigation.id && call.body?.status === "SUCCEEDED", 60_000)).body;
    expect(child.portfolio).toEqual(job.portfolio);
    expect(child.policy_version).toBe(2);
    const { weight: w } = nvidiaInSpy();
    const cap = child.result.rule_results.find((rule: any) => rule.rule_type === "max_issuer_exposure");
    expect(cap.limit).toBe(0.27);
    expect(cap.measured.lower).toBeCloseTo(0.25 + 0.5 * w, 9);
    expect(cap.status, "checked against the original portfolio it would PASS at 27%").toBe("FAIL");
    await expect(page.getByTestId("comparison-portfolio")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId("comparison-portfolio")).toContainText(/customized/i);
    await shot(page, "robert-12-comparison-after-rule-change");
    expect((await api("GET", `/investigations/${job.id}`)).body).toEqual(job);
  });

  test("Mateo: a customized portfolio with a fund without holdings stays UNKNOWN, at 390 px", async ({ page }) => {
    test.setTimeout(240_000);
    await page.setViewportSize({ width: 390, height: 844 });
    const traffic = new Traffic(page);
    await open(page);
    await selectPersona(page, "Mateo");
    const scenario = (await traffic.last("GET", /^\/portfolios\/mateo$/)).body.scenario;
    // XIU.TO (the only fund with sector labels) out, QQQ (no holdings file) in
    const EDIT: Edit = { positions: [["XBB.TO", "25"], ["ESGV", "15"], ["MSFT", "5"], ["CNR.TO", "5"], ["FTS.TO", "5"], ["QQQ", "20"]], cash: "25" };
    await page.getByTestId("customize-open").click();
    await page.getByTestId("customize-remove-XIU.TO").click();
    await page.getByTestId("customize-add-select").selectOption("QQQ");
    await page.getByTestId("customize-add").click();
    await page.getByTestId("customize-weight-QQQ").fill("20");
    await expect(page.getByTestId("customize-total")).toHaveAttribute("data-total-valid", "true");
    await shot(page, "mateo-01-editor-390px");
    await page.getByTestId("customize-apply").click({ force: true });
    expect(await stage1Weights(page)).toEqual(expectedTable(EDIT));
    await expect(page.getByTestId("customized-badge").first()).toBeVisible();
    await shot(page, "mateo-02-stage1-customized-390px");

    await confirmScenarioRules(page);
    const confirm = await traffic.last("POST", /^\/rules\/confirm$/);
    expect(confirm.requestBody.objectives).toEqual(scenario.objectives); // not edited: the scenario's own objective
    expect(confirm.body.policy.rules.map((rule: any) => rule.rule_id)).toEqual(scenario.scenario_rules.map((rule: any) => rule.rule_id));

    await enterPurchase(page, "MSFT", "10");
    const custom = expectedCustom(EDIT);
    const check = await traffic.last("POST", /^\/check$/, (call) => call.status === 200 && call.requestBody?.purchase_request?.target_direct_weight === 0.1, 20_000);
    expect(check.requestBody.custom_portfolio).toEqual(custom);
    const { created, job } = await investigate(page, traffic);
    expect(created.requestBody.custom_portfolio).toEqual(custom);
    expect(job.portfolio.portfolio_id).toMatch(/^pf-mateo-custom-[0-9a-f]{12}$/);
    expect({ cash_weight: job.portfolio.cash_weight, positions: job.portfolio.positions }).toEqual(custom);
    expect(job.result.feasibility.cash_before).toBe(0.25);
    expect(job.result.feasibility.starting_direct_weight).toBe(0.05);
    expect(job.result.feasibility.cash_after).toBeCloseTo(0.2, 9);
    // ESGV 15% and QQQ 20% have no holdings file: nothing can be proven absent, so no rule may pass
    const statuses = Object.fromEntries(job.result.rule_results.map((rule: any) => [rule.rule_id, rule.status]));
    expect(statuses["mateo-excl-energy-1"]).toBe("UNKNOWN");
    expect(Object.values(statuses)).not.toContain("PASS");
    expect(job.result.summary.counts.pass).toBe(0);

        await openReport(page, job.id);
    const details = await reportPortfolio(page);
    await expect(details).toHaveAttribute("data-customized", "true");
    await expect(details.getByTestId("report-portfolio-label")).toHaveText("Customized fictional portfolio");
    expect(await readTable(details)).toEqual(expectedTable(EDIT));
    const text = await page.getByTestId("report").innerText();
    expect(text).not.toMatch(/all (your )?(limits|rules) (are )?(respected|pass)/i);
    await shot(page, "mateo-03-report-customized-unknown-390px");
    await traffic.expectClean();
  });

  test("Amira (added on origin/main): a customized portfolio holding crypto is investigated as displayed, at 390 px", async ({ page }) => {
    test.setTimeout(240_000);
    await page.setViewportSize({ width: 390, height: 844 });
    const traffic = new Traffic(page);
    await open(page);
    await selectPersona(page, "Amira");
    const scenario = (await traffic.last("GET", /^\/portfolios\/amira$/)).body.scenario;
    // Three persona cards and the customize panel at phone width: nothing may overflow sideways.
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
    // ETH-USD out, BTC-USD down to 10%, the freed 10 points go to cash (10% -> 20%).
    const EDIT: Edit = { positions: [["SPY", "30"], ["XIU.TO", "10"], ["NVDA", "10"], ["MSFT", "10"], ["SHOP.TO", "5"], ["JPM", "5"], ["BTC-USD", "10"]], cash: "20" };
    await page.getByTestId("customize-open").click();
    await page.getByTestId("customize-remove-ETH-USD").click();
    await page.getByTestId("customize-weight-BTC-USD").fill("10");
    await page.getByTestId("customize-cash").fill("20");
    await expect(page.getByTestId("customize-total")).toHaveAttribute("data-total-valid", "true");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
    await shot(page, "amira-01-editor-390px");
    await page.getByTestId("customize-apply").click({ force: true });
    expect(await stage1Weights(page)).toEqual(expectedTable(EDIT));
    await expect(page.getByTestId("customized-badge").first()).toBeVisible();
    await shot(page, "amira-02-stage1-customized-390px");

    await confirmScenarioRules(page);
    const confirm = await traffic.last("POST", /^\/rules\/confirm$/);
    expect(confirm.requestBody.objectives).toEqual(scenario.objectives);
    expect(confirm.body.policy.rules.map((rule: any) => rule.rule_id)).toEqual(scenario.scenario_rules.map((rule: any) => rule.rule_id));

    await enterPurchase(page, "NVDA", "15");
    const custom = expectedCustom(EDIT);
    const check = await traffic.last("POST", /^\/check$/, (call) => call.status === 200 && call.requestBody?.purchase_request?.target_direct_weight === 0.15, 20_000);
    expect(check.requestBody.persona_id).toBe("amira");
    expect(check.requestBody.custom_portfolio).toEqual(custom);
    const { created, job } = await investigate(page, traffic);
    expect(created.requestBody.custom_portfolio).toEqual(custom);
    expect(job.portfolio.portfolio_id).toMatch(/^pf-amira-custom-[0-9a-f]{12}$/);
    expect({ cash_weight: job.portfolio.cash_weight, positions: job.portfolio.positions }).toEqual(custom);
    expect(job.result.portfolio_id).toBe(job.portfolio.portfolio_id);
    expect(job.result.feasibility.cash_before).toBe(0.2);
    expect(job.result.feasibility.starting_direct_weight).toBe(0.1);
    expect(job.result.feasibility.cash_after).toBeCloseTo(0.15, 9);
    // The crypto asset still held is outside the company-exposure rule and is listed as such; the one removed is gone.
    const cap = job.result.rule_results.find((rule: any) => rule.rule_type === "max_issuer_exposure");
    const outOfScope = cap.out_of_scope.map((position: any) => position.instrument_id);
    expect(outOfScope).toContain("BTC-USD");
    expect(outOfScope).not.toContain("ETH-USD");
    // The weights the user typed are labelled as such in the evidence (code review F4).
    const startingCash = job.result.evidence.find((record: any) => record.metric_id === "cash_weight" && record.subject.portfolio_state === "STARTING");
    expect(startingCash.assumptions.join(" ")).toContain("entered by the user in a customized fictional portfolio");

    await openReport(page, job.id);
    const details = await reportPortfolio(page);
    await expect(details).toHaveAttribute("data-customized", "true");
    await expect(details.getByTestId("report-portfolio-label")).toHaveText("Customized fictional portfolio");
    expect(await readTable(details)).toEqual(expectedTable(EDIT));
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
    await shot(page, "amira-03-report-customized-390px");
    await traffic.expectClean();
  });

  for (const [persona, instrument, percent] of [["Robert", "NVDA", "25"], ["Mateo", "SPY", "15"], ["Amira", "NVDA", "15"]] as const) {
    test(`${persona}, default flow: no request carries custom_portfolio and the result is the engine's on the scenario portfolio`, async ({ page }) => {
      test.setTimeout(180_000);
      const traffic = new Traffic(page);
      await open(page);
      await selectPersona(page, persona);
      const id = persona.toLowerCase();
      const scenario = (await traffic.last("GET", new RegExp(`^/portfolios/${id}$`))).body.scenario;
      // opening and cancelling the editor changes nothing
      await page.getByTestId("customize-open").click();
      await page.getByTestId("customize-cash").fill("99");
      await page.getByTestId("customize-cancel").click();
      await expect(page.getByTestId("customize-editor")).toHaveCount(0);
      await expect(page.getByTestId("customized-badge")).toHaveCount(0);
      // applying the scenario's own weights is not a customization
      await page.getByTestId("customize-open").click();
      await page.getByTestId("customize-apply").click({ force: true });
      await expect(page.getByTestId("customize-editor")).toHaveCount(0);
      await expect(page.getByTestId("customized-badge")).toHaveCount(0);

      await confirmScenarioRules(page);
      const confirm = await traffic.last("POST", /^\/rules\/confirm$/);
      expect(confirm.requestBody.objectives).toEqual(scenario.objectives);
      await enterPurchase(page, instrument, percent);
      await expect(page.getByTestId("purchase-portfolio-note")).toHaveCount(0);
      const target = Number(percent) / 100;
      const check = await traffic.last("POST", /^\/check$/, (call) => call.status === 200 && call.requestBody?.purchase_request?.target_direct_weight === target, 20_000);
      const { created, job } = await investigate(page, traffic);
      for (const call of traffic.calls.filter((candidate) => candidate.method === "POST")) expect(hasCustom(call), `${call.method} ${call.path}`).toBe(false);
      expect(Object.keys(created.requestBody).sort()).toEqual(["parent_investigation_id", "persona_id", "policy_id", "policy_version", "request"]);
      expect(job.portfolio).toEqual(scenario.portfolio);
      expect(job.result.portfolio_id).toBe(scenario.portfolio.portfolio_id);
      const direct = await control("/engine-check", { persona_id: id, policy: confirm.body.policy, purchase_request: created.requestBody.request, draft_rules: null });
      expect(job.result, "the job's result is backend.engine.check_rules on the scenario portfolio").toEqual(direct);
      expect(check.body.portfolio_id).toBe(scenario.portfolio.portfolio_id);
            await openReport(page, job.id);
      const details = await reportPortfolio(page);
      await expect(details).toHaveAttribute("data-customized", "false");
      await expect(page.getByTestId("customized-badge")).toHaveCount(0);
      await shot(page, `${id}-default-report`);
    });
  }
});
