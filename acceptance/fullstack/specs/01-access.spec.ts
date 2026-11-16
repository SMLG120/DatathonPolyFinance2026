import { expect, test } from "@playwright/test";
import { accessForm, API, CODE, expectNoTestDataMarkers, expectProfileLoaded, mainAlert, openPortfolioPanel, resetBackend, serverLog, shot, storedKeys, submitCode, Traffic } from "./helpers";

/**
 * The access-code gate against the real authorizer handler behind the emulated gateway. The gateway answers a
 * missing header with 401 {"message":"Unauthorized"} and a refused code with 403 {"message":"Forbidden"}: bodies
 * that are NOT the contract's error shape, so the page must act on the status alone.
 */
const REFUSED = "The service did not accept this code. Check it and try again.";

test.describe("access gate, live against the local authorizer", () => {
  test.beforeEach(async () => {
    await resetBackend();
  });

  test("nothing is requested before a code is typed, and live mode carries no test-data label", async ({ page }) => {
    const traffic = new Traffic(page);
    await page.goto("/");
    await expect(accessForm(page).heading).toBeVisible();
    await expect(accessForm(page).field).toHaveAttribute("type", "password");
    await page.waitForLoadState("networkidle");
    expect(await serverLog(), "no request reaches the API before a code is typed").toEqual([]);
    await expectNoTestDataMarkers(page, "access-code form", { wordsToo: false });
    await expect(page.getByRole("link", { name: /test data/i }), "the only mention of test data is the offer to switch to it").toHaveCount(1);
    await traffic.expectClean();
  });

  test("a wrong code: the gateway's 403 {message} body gives a readable error and nothing is stored", async ({ page }) => {
    const traffic = new Traffic(page);
    await page.goto("/");
    await submitCode(page, "definitely-not-the-code-0000");
    await expect(page.getByText(REFUSED)).toBeVisible();
    await expect(accessForm(page).heading).toBeVisible();
    expect(await storedKeys(page)).toEqual({ session: [], local: [], cookie: "" });
    const refused = await traffic.last("GET", /^\/portfolios\/robert$/);
    expect(refused.status).toBe(403);
    expect(refused.body).toEqual({ message: "Forbidden" });
    const log = (await serverLog()).filter((entry) => entry.method === "GET");
    expect(log.map((entry) => [entry.status, entry.answered_by, entry.authorization])).toEqual([[403, "gateway", "other"]]);
    await shot(page, "09-access-gate-wrong-code-403-live-local-backend-real-data");
  });

  test("the right code proceeds; it lives in sessionStorage only, never in localStorage, a cookie, the URL or the console", async ({ page, context }) => {
    const traffic = new Traffic(page);
    const consoleText: string[] = [];
    page.on("console", (message) => consoleText.push(message.text()));
    await page.goto("/");
    await submitCode(page, CODE);
    await expectProfileLoaded(page, "Robert");
    await openPortfolioPanel(page);
    await page.waitForLoadState("networkidle");

    const stored = await page.evaluate(() => ({
      session: Object.fromEntries(Object.entries(sessionStorage)),
      local: Object.fromEntries(Object.entries(localStorage)),
      cookie: document.cookie,
    }));
    expect(Object.keys(stored.session)).toEqual(["byb.accessCode"]);
    expect(stored.session["byb.accessCode"]).toBe(CODE);
    expect(stored.local).toEqual({});
    expect(stored.cookie).toBe("");
    expect(await context.cookies()).toEqual([]);
    expect(page.url()).not.toContain(CODE);
    expect(consoleText.join("\n")).not.toContain(CODE);
    expect(await page.content(), "the code is not written into the document").not.toContain(CODE);

    await traffic.expectClean();
    const log = await serverLog();
    const calls = log.filter((entry) => entry.method !== "OPTIONS");
    expect(calls.length).toBeGreaterThan(0);
    for (const call of calls) {
      expect(call.authorization, `${call.method} ${call.path}`).toBe("expected");
      expect(call.cookie).toBeNull();
      expect(call.path).not.toContain(CODE);
      expect(call.status).toBe(200);
    }
    // The browser really preflighted the Authorization header, and the gateway answered without the authorizer.
    const preflights = log.filter((entry) => entry.method === "OPTIONS");
    expect(preflights.length).toBeGreaterThan(0);
    expect(preflights.every((entry) => entry.authorization === "missing" && entry.status === 204)).toBe(true);
    expect(preflights.some((entry) => /authorization/i.test(entry.access_control_request_headers ?? ""))).toBe(true);

    // The code belongs to this tab: a reload keeps it, another tab asks again.
    await page.reload();
    await expectProfileLoaded(page, "Robert");
    await openPortfolioPanel(page);
    const other = await context.newPage();
    await other.goto("/");
    await expect(accessForm(other).heading).toBeVisible();
    await other.close();
    await expectNoTestDataMarkers(page, "stage 1 after the gate");
  });

  test("a code refused later (gateway 403) and a request without the header (gateway 401) both bring the form back and forget the code", async ({ page }) => {
    const traffic = new Traffic(page);
    await page.goto("/");
    await submitCode(page, CODE);
    await expectProfileLoaded(page, "Robert");

    // 403: stand-in for a code that was rotated while the tab was open.
    await page.evaluate(() => sessionStorage.setItem("byb.accessCode", "rotated-away-0000000000"));
    await page.getByRole("button", { name: "Use Mateo’s portfolio" }).click();
    await expect(accessForm(page).heading).toBeVisible();
    await expect(page.getByText("The service no longer accepts the code that was in use")).toBeVisible();
    expect(await storedKeys(page)).toEqual({ session: [], local: [], cookie: "" });
    expect((await traffic.last("GET", /^\/portfolios\/mateo$/)).body).toEqual({ message: "Forbidden" });

    // Back in with the right code: the request that was refused is offered again ("Try again"), and then works.
    await submitCode(page, CODE);
    const failed = mainAlert(page).filter({ hasText: "The portfolio could not be loaded" });
    await expect(failed).toBeVisible();
    await failed.getByRole("button", { name: "Try again" }).click();
    await expectProfileLoaded(page, "Mateo");
    await openPortfolioPanel(page);

    // 401: the header is removed on the way (a proxy that strips it), so the gateway never calls the authorizer.
    await page.route(`${API}/portfolios/robert`, async (route) => {
      const headers = { ...route.request().headers() };
      delete headers.authorization;
      await route.continue({ headers });
    });
    await page.getByRole("button", { name: "Use Robert’s portfolio" }).click();
    await expect(accessForm(page).heading).toBeVisible();
    await expect(page.getByText("The service no longer accepts the code that was in use")).toBeVisible();
    expect(await storedKeys(page)).toEqual({ session: [], local: [], cookie: "" });
    const unauthorized = await traffic.last("GET", /^\/portfolios\/robert$/);
    expect([unauthorized.status, unauthorized.body]).toEqual([401, { message: "Unauthorized" }]);
  });

  test("after a refused code is replaced, the page does not print the gateway's body", async ({ page }) => {
    // Finding F-01 of the first run (the page printed "Forbidden"), fixed since: this is now a plain assertion.
    await page.goto("/");
    await submitCode(page, CODE);
    await expectProfileLoaded(page, "Robert");
    await page.evaluate(() => sessionStorage.setItem("byb.accessCode", "rotated-away-0000000000"));
    await page.getByRole("button", { name: "Use Mateo’s portfolio" }).click();
    await expect(accessForm(page).heading).toBeVisible();
    await submitCode(page, CODE);
    const failed = mainAlert(page).filter({ hasText: "The portfolio could not be loaded" });
    await expect(failed).toBeVisible();
    // contracts/api.md, Authentication: "Clients treat 401 and 403 alike: ... do not read the body."
    await expect(failed).not.toContainText("Forbidden");
    await expect(page.locator("body")).not.toContainText(/Forbidden|Unauthorized/);
    // Not a dead end: the request that was refused can be made again, and then works.
    await failed.getByRole("button", { name: "Try again" }).click();
    await expectProfileLoaded(page, "Mateo");
  });

  test("an unknown route is the gateway's 404 {message}, with or without a code (there is no $default route)", async () => {
    const response = await fetch(`${API}/policies/pol-x`, { headers: { Authorization: `Bearer ${CODE}` } });
    expect([response.status, await response.json()]).toEqual([404, { message: "Not Found" }]);
    const bare = await fetch(`${API}/portfolios/robert`);
    expect([bare.status, await bare.json()]).toEqual([401, { message: "Unauthorized" }]);
    const preflight = await fetch(`${API}/check`, { method: "OPTIONS", headers: { Origin: "http://127.0.0.1:9", "Access-Control-Request-Method": "POST" } });
    expect(preflight.status).toBe(204);
    expect(preflight.headers.get("access-control-allow-origin"), "another origin gets no CORS grant").toBeNull();
  });
});
