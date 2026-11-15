import path from "node:path";
import { expect, type Locator, type Page } from "@playwright/test";

export const API = `http://127.0.0.1:${process.env.BYB_LOCAL_API_PORT ?? 4184}`;
export const SITE = `http://127.0.0.1:${process.env.BYB_LOCAL_SITE_PORT ?? 4185}`;
export const CONTROL = `http://127.0.0.1:${process.env.BYB_LOCAL_CONTROL_PORT ?? 4186}`;
/** Made up by run.sh for this run; the local authorizer's fake SSM holds the same value. */
export const CODE = process.env.BYB_LOCAL_ACCESS_CODE as string;
export const SCREENSHOTS = path.resolve(__dirname, "..", "screenshots");

// ---------------------------------------------------------------------------
// The control port of local_api.py (test-only; the page never calls it)
// ---------------------------------------------------------------------------

export async function control<T = any>(route: string, body?: unknown): Promise<T> {
  const response = await fetch(`${CONTROL}${route}`, body === undefined ? undefined : { method: "POST", body: JSON.stringify(body) });
  const document = await response.json();
  if (!response.ok) throw new Error(`control ${route}: ${JSON.stringify(document)}`);
  return document as T;
}

/** Default switches (Bedrock in `fallback` mode unless overridden), empty request log. */
export async function resetBackend(settings: Record<string, unknown> = {}) {
  await control("/reset", {});
  if (Object.keys(settings).length > 0) await control("/settings", settings);
}

export interface ServerLogEntry {
  seq: number;
  t: number;
  method: string;
  path: string;
  route?: string | null;
  status: number;
  answered_by: string;
  origin: string | null;
  authorization: "missing" | "expected" | "other";
  idempotency_key: string | null;
  cookie: string | null;
  query: string;
  access_control_request_headers?: string | null;
}

export async function serverLog(): Promise<ServerLogEntry[]> {
  return (await control<{ requests: ServerLogEntry[] }>("/log")).requests;
}

/** A direct call to the local API with the run's code, from the test process (not from the page). */
export async function api(method: "GET" | "POST", route: string, body?: unknown, headers: Record<string, string> = {}) {
  const response = await fetch(`${API}${route}`, {
    method,
    headers: { Authorization: `Bearer ${CODE}`, ...(body === undefined ? {} : { "Content-Type": "application/json" }), ...headers },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const text = await response.text();
  return { status: response.status, body: text ? JSON.parse(text) : null };
}

/** `backend.engine.check_rules` run directly on the snapshot's documents by the local server process. */
export async function engineCheck(input: { persona_id: string; policy: unknown; purchase_request: unknown; draft_rules?: unknown }) {
  return control("/engine-check", { draft_rules: null, ...input });
}

// ---------------------------------------------------------------------------
// What the page sent and received
// ---------------------------------------------------------------------------

export interface ApiCall {
  index: number;
  method: string;
  path: string;
  status: number;
  requestHeaders: Record<string, string>;
  requestBody: any;
  body: any;
  at: number;
}

export class Traffic {
  readonly calls: ApiCall[] = [];
  /** Requests to any origin other than the local site and the local API. */
  readonly foreign: string[] = [];
  private pending: Promise<void>[] = [];
  private counter = 0;

  constructor(page: Page) {
    page.on("request", (request) => {
      const url = new URL(request.url());
      if (["data:", "blob:", "about:"].includes(url.protocol)) return;
      if (url.origin !== SITE && url.origin !== API) this.foreign.push(request.url());
    });
    page.on("response", (response) => {
      if (!response.url().startsWith(API)) return;
      const request = response.request();
      const call: ApiCall = {
        index: (this.counter += 1),
        method: request.method(),
        path: response.url().slice(API.length),
        status: response.status(),
        requestHeaders: request.headers(),
        requestBody: null,
        body: null,
        at: Date.now(),
      };
      try {
        call.requestBody = request.postDataJSON();
      } catch {
        call.requestBody = request.postData();
      }
      this.calls.push(call);
      this.pending.push(
        response
          .json()
          .then((body) => {
            call.body = body;
          })
          .catch(() => undefined),
      );
    });
  }

  async settle() {
    await Promise.all(this.pending);
  }

  async find(method: string, pattern: RegExp, predicate: (call: ApiCall) => boolean = () => true): Promise<ApiCall[]> {
    await this.settle();
    return this.calls.filter((call) => call.method === method && pattern.test(call.path) && predicate(call));
  }

  /** The latest matching call; waits up to `timeoutMs` for the first one (a response may still be on its way). */
  async last(method: string, pattern: RegExp, predicate: (call: ApiCall) => boolean = () => true, timeoutMs = 15_000): Promise<ApiCall> {
    const deadline = Date.now() + timeoutMs;
    let found = await this.find(method, pattern, predicate);
    while (found.length === 0 && Date.now() < deadline) {
      await new Promise((resolve) => setTimeout(resolve, 100));
      found = await this.find(method, pattern, predicate);
    }
    expect(found.length, `the page made no ${method} ${pattern} call matching the predicate`).toBeGreaterThan(0);
    return found[found.length - 1];
  }

  /** The matching call that `action` causes: the first one answered after it started. */
  async after(method: string, pattern: RegExp, action: () => Promise<unknown>, timeoutMs = 15_000): Promise<ApiCall> {
    const before = (await this.find(method, pattern)).length;
    await action();
    const deadline = Date.now() + timeoutMs;
    let found = await this.find(method, pattern);
    while (found.length <= before && Date.now() < deadline) {
      await new Promise((resolve) => setTimeout(resolve, 100));
      found = await this.find(method, pattern);
    }
    expect(found.length, `the action caused no ${method} ${pattern} call`).toBeGreaterThan(before);
    return found[before];
  }

  /** Every API call of the page carried the bearer header; nothing went to another host. */
  async expectClean() {
    await this.settle();
    expect(this.foreign, "requests to a host other than the local site and the local API").toEqual([]);
    for (const call of this.calls) {
      expect(call.requestHeaders.authorization, `${call.method} ${call.path} carries the bearer header`).toBe(`Bearer ${CODE}`);
      expect(call.path, "the access code is never in a URL").not.toContain(CODE);
    }
  }
}

// ---------------------------------------------------------------------------
// Driving the interface
// ---------------------------------------------------------------------------

export const accessForm = (page: Page) => ({
  heading: page.getByRole("heading", { level: 1, name: "Enter the access code" }),
  field: page.getByLabel("Access code", { exact: true }),
});

export async function submitCode(page: Page, code: string) {
  const { field } = accessForm(page);
  await field.fill(code);
  await field.press("Enter");
}

export async function storedKeys(page: Page) {
  return page.evaluate(() => ({ session: Object.keys(sessionStorage), local: Object.keys(localStorage), cookie: document.cookie }));
}

/** Open the live site, pass the gate with the run's code, wait for Robert's portfolio. */
export async function openApp(page: Page) {
  await page.goto("/");
  await submitCode(page, CODE);
  await expect(page.getByTestId("portfolio-table")).toBeVisible();
}

export async function choosePersona(page: Page, name: "Robert" | "Mateo") {
  if (name !== "Robert") await page.getByRole("button", { name: `Use ${name}’s portfolio` }).click();
  await expect(page.getByTestId("persona-selected")).toBeVisible();
  await expect(page.getByTestId("portfolio-table")).toBeVisible();
}

export async function goToGoals(page: Page) {
  await page.getByRole("link", { name: "Continue to Goals & rules" }).click();
  await expect(page.getByTestId("rule-card").first()).toBeVisible();
}

export async function confirmOfferedRules(page: Page) {
  await page.getByTestId("confirm-rules").click();
  await expect(page.getByTestId("policy-rule-card").first()).toBeVisible();
}

export async function goToPurchase(page: Page) {
  await page.getByRole("link", { name: "Continue to Proposed purchase" }).click();
  await expect(page.getByTestId("funding-statement")).toBeVisible();
}

export async function setPurchase(page: Page, instrumentId: string, percentText: string) {
  await page.getByLabel("Instrument to buy").selectOption(instrumentId);
  await page.getByLabel("Final direct weight of this position").fill(percentText);
}

export async function startAndOpenVerdict(page: Page) {
  await page.getByTestId("start-investigation").click();
  await page.getByTestId("see-verdict").click({ timeout: 60_000 });
  await expect(page.getByTestId("report")).toBeVisible();
}

/** Open every closed <details> of the page, so text queries see the whole report. */
export async function openAllDetails(page: Page) {
  await page.evaluate(() => document.querySelectorAll("details").forEach((element) => ((element as HTMLDetailsElement).open = true)));
}

/** Live mode never shows a fixtures / test-data marker. */
export async function expectNoTestDataMarkers(page: Page, context: string, options: { wordsToo?: boolean } = {}) {
  await expect(page.getByTestId("fixtures-label"), `fixtures label on: ${context}`).toHaveCount(0);
  await expect(page.getByTestId("test-data-tag"), `"Test data" tag on: ${context}`).toHaveCount(0);
  await expect(page.getByTestId("simulation-label")).toHaveText("Simulation — fictional portfolio, not advice");
  // The access-code form offers "Open the simulation with test data instead": a link, not a label of what is shown.
  if (options.wordsToo === false) return;
  const text = await page.locator("body").innerText();
  expect(text, `the words "test data" on: ${context}`).not.toMatch(/test data/i);
  expect(text, `the word "fixture" on: ${context}`).not.toMatch(/fixtures?\b/i);
}

export async function shot(page: Page, name: string, options: { fullPage?: boolean; locator?: Locator } = {}) {
  const file = path.join(SCREENSHOTS, `${name}.png`);
  if (options.locator) await options.locator.screenshot({ path: file });
  else await page.screenshot({ path: file, fullPage: options.fullPage ?? false });
}

/**
 * The text of a region as a reader gets it, without the tick labels of the chart scales. The scales are geometry
 * chosen by the page (`exposureAxis`, `scaleText`), drawn in `aria-hidden` rows and in the 3D scene; they are not
 * figures of a result.
 */
export async function figureText(region: Locator): Promise<string> {
  return region.evaluate((root) => {
    const hidden = Array.from(root.querySelectorAll<HTMLElement>('[aria-hidden="true"], [data-testid="explorer-scene"]'));
    const before = hidden.map((element) => element.style.display);
    hidden.forEach((element) => (element.style.display = "none"));
    const text = (root as HTMLElement).innerText;
    hidden.forEach((element, index) => (element.style.display = before[index]));
    return text;
  });
}

export const mainAlert = (page: Page) => page.getByRole("main").getByRole("alert");

// ---------------------------------------------------------------------------
// Numbers
// ---------------------------------------------------------------------------

/** Every number anywhere in a JSON document. */
export function numbersIn(document: unknown, into: number[] = []): number[] {
  if (typeof document === "number") into.push(document);
  else if (Array.isArray(document)) document.forEach((item) => numbersIn(item, into));
  else if (document && typeof document === "object") Object.values(document).forEach((item) => numbersIn(item, into));
  return into;
}

/** Every string anywhere in a JSON document, joined (service-written sentences carry their own rounded figures). */
export function stringsIn(document: unknown, into: string[] = []): string[] {
  if (typeof document === "string") into.push(document);
  else if (Array.isArray(document)) document.forEach((item) => stringsIn(item, into));
  else if (document && typeof document === "object") Object.values(document).forEach((item) => stringsIn(item, into));
  return into;
}

export interface Token {
  text: string;
  value: number;
  decimals: number;
}

/** "26.2%", "−17.78%", "16.2 points" in a text, as numbers in percent with their printed precision. */
export function percentTokens(text: string): Token[] {
  const tokens: Token[] = [];
  const pattern = /([−+-]?)(\d+(?:\.(\d+))?)\s?(%|points?\b)/g;
  for (let match = pattern.exec(text); match; match = pattern.exec(text)) {
    const value = Number(match[2]) * (match[1] === "−" || match[1] === "-" ? -1 : 1);
    tokens.push({ text: match[0], value, decimals: (match[3] ?? "").length });
  }
  return tokens;
}

/**
 * The printed figures of `text` that no number of the API documents explains. A printed "26.2%" is explained by an
 * API fraction x when x*100 (or its absolute value: a loss is printed as a positive size, a gap as "points under")
 * is within one unit of the last printed digit — that admits rounding to nearest and rounding down, nothing else —
 * or when the same token appears verbatim in a sentence the service wrote.
 */
export function unexplainedFigures(text: string, documents: unknown[]): string[] {
  const numbers = documents.flatMap((document) => numbersIn(document));
  const sentences = documents.flatMap((document) => stringsIn(document)).join("\n");
  const missing: string[] = [];
  for (const token of percentTokens(text)) {
    const unit = 10 ** -token.decimals;
    const target = Math.abs(token.value);
    const explained = numbers.some((x) => Math.abs(Math.abs(x) * 100 - target) < unit - 1e-9) || sentences.includes(token.text.replace("−", "-")) || sentences.includes(token.text);
    if (!explained) missing.push(token.text);
  }
  return [...new Set(missing)];
}
