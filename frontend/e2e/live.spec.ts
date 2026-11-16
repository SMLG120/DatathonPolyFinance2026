import { createServer, type Server } from "node:http";
import { expect, test, type Page } from "@playwright/test";
import { createFixturesClient } from "../src/lib/api/fixtures-client";
import { FIXTURES } from "../src/lib/fixtures";
import { confirmScenarioRules, continueToPurchase, expectNoAxeViolations, expectPortfolioLoaded, expectScreen, openPurchasePreview, tabTo } from "./helpers";

/**
 * The access-code gate of a LIVE build (`out-live/`, see scripts/build-e2e.mjs),
 * in a real browser, against a mock service started here. No real service and
 * no real access code are involved: the codes below are made-up strings that
 * only this mock knows.
 *
 * The mock is a real HTTP server on another origin, so the browser applies
 * its real cross-origin rules (preflight for the Authorization header).
 */
const LIVE_API = "http://127.0.0.1:4174"; // must match scripts/build-e2e.mjs
const LIVE_SITE = "http://127.0.0.1:4175"; // must match playwright.config.ts
const ACCEPTED_CODE = "e2e-accepted-code";
const FORBIDDEN_CODE = "e2e-forbidden-code";
const APP_NAME = "ETHOS: fictional simulation";

interface SeenRequest {
  method: string;
  url: string;
  authorization: string | null;
  cookie: string | null;
  preflightHeaders: string | null;
}

let server: Server;
let seen: SeenRequest[] = [];

// One mock for the file: the tests run one after another in a single worker.
test.describe.configure({ mode: "default" });

test.beforeAll(async () => {
  const fixtures = createFixturesClient();
  const portfolios: Record<string, string> = {
    "/portfolios/robert": JSON.stringify(await fixtures.getPortfolio("robert")),
    "/portfolios/mateo": JSON.stringify(await fixtures.getPortfolio("mateo")),
    "/portfolios/amira": JSON.stringify(await fixtures.getPortfolio("amira")),
  };
  const cors = {
    "Access-Control-Allow-Origin": LIVE_SITE,
    "Access-Control-Allow-Headers": "authorization, content-type, idempotency-key",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  };
  const json = { ...cors, "Content-Type": "application/json" };

  server = createServer((request, response) => {
    const authorization = request.headers.authorization ?? null;
    seen.push({
      method: request.method ?? "",
      url: request.url ?? "",
      authorization,
      cookie: request.headers.cookie ?? null,
      preflightHeaders: (request.headers["access-control-request-headers"] as string | undefined) ?? null,
    });
    if (request.method === "OPTIONS") {
      response.writeHead(204, cors).end();
    } else if (authorization === `Bearer ${FORBIDDEN_CODE}`) {
      // What a gateway in front of the service answers: not the contract's error body.
      response.writeHead(403, json).end(JSON.stringify({ message: "Forbidden" }));
    } else if (authorization !== `Bearer ${ACCEPTED_CODE}`) {
      // The recorded 401 of the contract.
      response.writeHead(FIXTURES.errors.unauthorized.status, json).end(JSON.stringify(FIXTURES.errors.unauthorized.response));
    } else if (request.method === "GET" && request.url && portfolios[request.url]) {
      response.writeHead(200, json).end(portfolios[request.url]);
    } else {
      // The recorded 404 of the contract.
      response.writeHead(FIXTURES.errors.notFound.status, json).end(JSON.stringify(FIXTURES.errors.notFound.response));
    }
  });
  await new Promise<void>((resolve, reject) => {
    server.once("error", reject);
    server.listen(4174, "127.0.0.1", resolve);
  });
});

test.afterAll(async () => {
  await new Promise<void>((resolve) => server.close(() => resolve()));
});

test.beforeEach(() => {
  seen = [];
});

const form = (page: Page) => ({
  heading: page.getByRole("heading", { level: 1, name: "Enter the access code" }),
  field: page.getByLabel("Access code", { exact: true }),
});

const storedKeys = (page: Page) =>
  page.evaluate(() => ({ session: Object.keys(sessionStorage), local: Object.keys(localStorage), cookie: document.cookie }));

/** The title, read once the page has settled: a title that is written and then overwritten must not pass. */
async function settledTitle(page: Page): Promise<string> {
  await page.waitForLoadState("networkidle");
  expect(await page.locator("title").count(), "the page has exactly one <title>").toBe(1);
  return page.title();
}

/** Type a code and submit it, keyboard only. */
async function submitCode(page: Page, code: string) {
  const { field } = form(page);
  await tabTo(page, field);
  await page.keyboard.press("ControlOrMeta+a");
  await page.keyboard.type(code);
  await page.keyboard.press("Enter");
}

test.describe("live build: the access-code gate", () => {
  test("asks for the code before anything else, with a title, and fetches nothing", async ({ page }) => {
    await page.goto("/");
    await expect(form(page).heading).toBeVisible();
    expect(await settledTitle(page)).toBe(`Access code: ${APP_NAME}`);
    await expect(page.getByTestId("simulation-label")).toHaveText("Simulation: fictional portfolio, not advice");
    await expect(page.getByTestId("fixtures-label")).toHaveCount(0);
    // Nothing of the simulation is offered before the code: no stage navigation.
    await expect(page.getByRole("navigation", { name: "Stages of the simulation" })).toHaveCount(0);
    await expect(page.getByRole("link", { name: /^Step \d of \d/ })).toHaveCount(0);
    await expect(form(page).field).toHaveAttribute("type", "password");
    expect(seen, "no request before a code is typed").toEqual([]);
    await expectNoAxeViolations(page, "access-code form");
  });

  test("an empty submit sends nothing; a refused code (401 or 403) stores nothing", async ({ page }) => {
    await page.goto("/");
    const { field } = form(page);
    await tabTo(page, field);
    await page.keyboard.press("Enter");
    await expect(page.getByText("Enter the access code you were given.")).toBeVisible();
    await expect(field).toBeFocused();
    await expect(field).toHaveAttribute("aria-invalid", "true");
    expect(seen).toEqual([]);

    for (const refused of ["some-wrong-code", FORBIDDEN_CODE]) {
      await submitCode(page, refused);
      await expect(page.getByText("The service did not accept this code. Check it and try again.")).toBeVisible();
      await expect(field).toBeFocused();
      expect(await storedKeys(page)).toEqual({ session: [], local: [], cookie: "" });
      await expect(form(page).heading).toBeVisible();
      // Clearing the field clears the message, so the next round starts clean.
      await page.keyboard.press("ControlOrMeta+a");
      await page.keyboard.press("Backspace");
      await expect(page.getByText("The service did not accept this code. Check it and try again.")).toHaveCount(0);
    }
    expect(seen.filter((request) => request.method === "GET").map((request) => request.authorization)).toEqual([
      "Bearer some-wrong-code",
      `Bearer ${FORBIDDEN_CODE}`,
    ]);

    await submitCode(page, "some-wrong-code");
    await expect(page.getByText("The service did not accept this code. Check it and try again.")).toBeVisible();
    await expectNoAxeViolations(page, "access-code form with a refused code");
  });

  test("a service that cannot be reached is reported, and nothing is stored", async ({ page }) => {
    await page.route(`${LIVE_API}/**`, (route) => route.abort("connectionrefused"));
    await page.goto("/");
    await submitCode(page, ACCEPTED_CODE);
    const alert = page.getByRole("main").getByRole("alert");
    await expect(alert).toContainText("The code could not be checked");
    await expect(alert).toContainText("Nothing was stored. You can try again.");
    expect(await storedKeys(page)).toEqual({ session: [], local: [], cookie: "" });
    await expect(form(page).heading).toBeVisible();
  });

  test("an accepted code opens the simulation and lives in sessionStorage only", async ({ page, context }) => {
    const consoleText: string[] = [];
    page.on("console", (message) => consoleText.push(message.text()));
    await page.goto("/");
    await submitCode(page, ACCEPTED_CODE);

    await expectPortfolioLoaded(page);
    await expectScreen(page, "persona", { focused: false });
    await expect(page.getByRole("button", { name: "Use Mateo’s portfolio" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Use Amira’s portfolio" })).toBeVisible();
    expect(await settledTitle(page)).toBe(`Choose a profile: ${APP_NAME}`);
    await expect(page.getByTestId("fixtures-label")).toHaveCount(0);
    // Answers that come from a service carry no "Test data" marker.
    await expect(page.getByTestId("test-data-tag")).toHaveCount(0);
    await expect(page.getByTestId("simulation-label")).toBeVisible();
    // In the notice as text for assistive technology (visually hidden), read from the portfolio the service sent.
    await expect(page.getByTestId("valuation-date")).toHaveText("Valuation date: 12 Nov 2026");

    expect(await storedKeys(page)).toEqual({ session: ["byb.accessCode"], local: [], cookie: "" });
    expect(page.url()).not.toContain(ACCEPTED_CODE);
    expect(consoleText.join("\n")).not.toContain(ACCEPTED_CODE);

    const calls = seen.filter((request) => request.method !== "OPTIONS");
    expect(calls.length).toBeGreaterThan(0);
    for (const call of calls) {
      expect(call.authorization, `${call.method} ${call.url}`).toBe(`Bearer ${ACCEPTED_CODE}`);
      expect(call.cookie, "no cookie is sent to the service").toBeNull();
      expect(call.url, "the code is never in a URL").not.toContain(ACCEPTED_CODE);
    }
    // What the real service must allow: this origin, and the Authorization header.
    expect(seen.some((request) => request.method === "OPTIONS" && /authorization/i.test(request.preflightHeaders ?? ""))).toBe(true);

    // The code belongs to this tab: a reload keeps it, another tab asks again.
    await page.reload();
    await expectPortfolioLoaded(page);
    const otherTab = await context.newPage();
    await otherTab.goto("/");
    await expect(form(otherTab).heading).toBeVisible();
    await otherTab.close();

    // "Forget the access code" removes it.
    await page.getByRole("button", { name: "Forget the access code" }).click();
    await expect(form(page).heading).toBeVisible();
    expect(await storedKeys(page)).toEqual({ session: [], local: [], cookie: "" });
    expect(await settledTitle(page)).toBe(`Access code: ${APP_NAME}`);
  });

  test("a code the service stops accepting is removed, and the form says why", async ({ page }) => {
    await page.goto("/");
    await submitCode(page, ACCEPTED_CODE);
    await expectPortfolioLoaded(page);

    // Stand-in for a code that was revoked while the tab was open.
    await page.evaluate(() => sessionStorage.setItem("byb.accessCode", "revoked-since"));
    await page.getByRole("button", { name: "Use Mateo’s portfolio" }).click();

    await expect(form(page).heading).toBeVisible();
    await expect(page.getByText("The service no longer accepts the code that was in use")).toBeVisible();
    expect(await storedKeys(page)).toEqual({ session: [], local: [], cookie: "" });
    await expectNoAxeViolations(page, "access-code form after the code was refused mid-session");
  });

  test("?fixtures=1 on a live build uses test data, is labelled, and sends nothing", async ({ page }) => {
    await page.goto("/?fixtures=1");
    await expectPortfolioLoaded(page);
    await expect(page.getByTestId("fixtures-label")).toHaveText("Test data: fixtures");
    await expect(form(page).heading).toHaveCount(0);
    await confirmScenarioRules(page);
    await continueToPurchase(page);
    await openPurchasePreview(page);
    await expect(page.getByTestId("purchase-preview").getByTestId("cash-after")).toHaveText("5.0%");
    await expect(page.getByTestId("purchase-preview").locator("xpath=ancestor::*[@data-figures='true']").getByTestId("test-data-tag").first()).toBeVisible();
    expect(seen, "fixtures mode never calls the service").toEqual([]);
  });
});
