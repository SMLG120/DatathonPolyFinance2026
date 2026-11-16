import AxeBuilder from "@axe-core/playwright";
import { expect, type Locator, type Page } from "@playwright/test";

/** Every test opens the static build in fixtures mode, whatever the build was configured with. */
export const START_URL = "/?fixtures=1";

/** The three moments of the journey, as the stage navigation names them. */
export const JOURNEY_TITLES = ["Choose a profile", "Test an idea", "Understand the result"] as const;

/**
 * Every screen, by the id in its address (`#/purchase`): the moment of the
 * journey it belongs to and the title of its heading. "Your limits",
 * "Analysis details" and "Review this result" are secondary views of a moment.
 */
export const SCREENS = {
  persona: { step: 1, title: "Choose a profile" },
  goals: { step: 2, title: "Your limits" },
  purchase: { step: 2, title: "Test an idea" },
  investigation: { step: 3, title: "Analysis details" },
  verdict: { step: 3, title: "Your result" },
  challenge: { step: 3, title: "Review this result" },
} as const;
export type ScreenId = keyof typeof SCREENS;

export function stageHeading(page: Page): Locator {
  return page.locator("[data-stage-heading]");
}

/** A link of the stage navigation, by the number of its moment. A finished moment reads "(completed)" after its title. */
export function stepLink(page: Page, step: 1 | 2 | 3): Locator {
  return page.getByRole("navigation", { name: "Stages of the simulation" }).getByRole("link", { name: new RegExp(`^Step ${step} of 3: ${JOURNEY_TITLES[step - 1]}`) });
}

/** The screen is shown and — because a screen change is a page change — its heading has focus. */
export async function expectScreen(page: Page, id: ScreenId, { focused = true }: { focused?: boolean } = {}) {
  const { step, title } = SCREENS[id];
  const heading = stageHeading(page);
  await expect(heading).toHaveText(`Step ${step} of 3: ${title}`);
  if (focused) await expect(heading).toBeFocused();
  await expect(page.getByRole("navigation", { name: "Stages of the simulation" }).getByRole("link")).toHaveCount(3);
  await expect(stepLink(page, step)).toHaveAttribute("aria-current", "step");
  await expect(page.locator('nav[aria-label="Stages of the simulation"] [aria-current]')).toHaveCount(1);
}

/**
 * The labels that must be there on every screen. The simulation label and the
 * test-data label are visible. The valuation date is in the notice as text for
 * assistive technology only (it is visually hidden), so its text is checked,
 * not its visibility.
 */
export async function expectPersistentLabels(page: Page) {
  await expect(page.getByTestId("simulation-label")).toBeVisible();
  await expect(page.getByTestId("simulation-label")).toHaveText("Simulation: fictional portfolio, not advice");
  await expect(page.getByTestId("fixtures-label")).toBeVisible();
  await expect(page.getByTestId("fixtures-label")).toHaveText("Test data: fixtures");
  await expect(page.getByTestId("valuation-date")).toHaveText("Valuation date: 12 Nov 2026");
}

/** The first screen has loaded the persona's portfolio. The table itself is inside a closed panel until it is asked for. */
export async function expectPortfolioLoaded(page: Page, persona = "Robert") {
  await expect(page.getByTestId(`persona-${persona.toLowerCase()}`).getByTestId("persona-selected")).toBeVisible();
  await expect(page.getByTestId("portfolio-table")).toContainText(`${persona}’s fictional portfolio`);
}

/** The summary line of a closed panel, by the panel's title. */
export function panelSummary(page: Page, title: string): Locator {
  return page.getByRole("main").locator("summary").filter({ has: page.getByRole("heading", { name: title, exact: true }) });
}

/** Screen 1 with the pointer: open "View the fictional portfolio" and see the table. */
export async function openPortfolioPanel(page: Page) {
  await expect(page.getByTestId("portfolio-table")).toBeHidden();
  await panelSummary(page, "View the fictional portfolio").click();
  await expect(page.getByTestId("portfolio-table")).toBeVisible();
}

/**
 * Moves focus to `target` with the Tab key only, the way a keyboard user gets
 * there. Fails if the element cannot be reached.
 */
export async function tabTo(page: Page, target: Locator, maxPresses = 120, key: "Tab" | "Shift+Tab" = "Tab") {
  await expect(target).toBeVisible();
  for (let presses = 0; presses < maxPresses; presses += 1) {
    if (await target.evaluate((element) => element === document.activeElement)) return;
    await page.keyboard.press(key);
  }
  await expect(target, `not reachable with ${maxPresses} presses of ${key}`).toBeFocused();
}

/** The same, backwards: for a control that comes before the one that has focus. */
export async function tabBackTo(page: Page, target: Locator, maxPresses = 120) {
  await tabTo(page, target, maxPresses, "Shift+Tab");
}

/** The element that has keyboard focus shows the focus ring: a solid outline at least 2px thick. */
export async function expectVisibleFocusRing(target: Locator) {
  await expect(target).toBeFocused();
  const ring = await target.evaluate((element) => {
    const style = getComputedStyle(element);
    return { style: style.outlineStyle, width: Number.parseFloat(style.outlineWidth), color: style.outlineColor };
  });
  expect(ring.style, "focus ring style").toBe("solid");
  expect(ring.width, "focus ring width in px").toBeGreaterThanOrEqual(2);
  expect(ring.color, "focus ring colour").not.toMatch(/rgba\(.*,\s*0\)$|transparent/);
}

/** Tab to a control and activate it with Enter. */
export async function tabToAndPress(page: Page, target: Locator, key: "Enter" | "Space" = "Enter") {
  await tabTo(page, target);
  await page.keyboard.press(key);
}

/**
 * An error block inside the page content. Next.js adds its own empty
 * `role="alert"` route announcer to every page, so a bare role query is
 * ambiguous; the application's alerts all live inside <main>.
 */
export function mainAlert(page: Page): Locator {
  return page.getByRole("main").getByRole("alert");
}

/**
 * From screen 1 with the pointer: "Test an idea" says the limits come first,
 * "Set my limits" offers the scenario's rules as proposals; confirm them with
 * their numbers.
 */
export async function confirmScenarioRules(page: Page) {
  await page.getByTestId("continue-link").click();
  await expectScreen(page, "purchase");
  await page.getByRole("link", { name: "Set my limits" }).click();
  await expectScreen(page, "goals");
  await expect(page.getByTestId("rule-card").first()).toBeVisible();
  await page.getByTestId("confirm-rules").click();
  await expect(page.getByTestId("policy-rule-card").first()).toBeVisible();
}

/** From "Your limits" to "Test an idea", with the pointer. */
export async function continueToPurchase(page: Page) {
  await page.getByTestId("continue-link").click();
  await expectScreen(page, "purchase");
}

/** The panel of the purchase screen that holds the service's preview is closed until asked for. */
export async function openPurchasePreview(page: Page) {
  await panelSummary(page, "Preview cash and exposures").click();
  await expect(page.getByTestId("purchase-preview")).toBeVisible();
}

/** "Check my idea" leads straight to the result screen, which waits for the investigation and then shows its report. */
export async function checkIdeaAndWaitForReport(page: Page) {
  await page.getByTestId("start-investigation").click();
  await expectScreen(page, "verdict");
  await expect(page.getByTestId("report")).toBeVisible({ timeout: 30_000 });
}

/** The exposure chart and the explorer are inside the closed panel "Explore my exposures" of the report. */
export async function openExposurePanel(page: Page) {
  await panelSummary(page, "Explore my exposures").click();
  await expect(page.locator("#report-exposure")).toHaveJSProperty("open", true);
}

/** Opens every closed section of the page at once, the nested ones included. */
export async function openEverySection(page: Page) {
  await page.evaluate(() => document.querySelectorAll("main details").forEach((details) => ((details as HTMLDetailsElement).open = true)));
}

/** From the first screen to the report of the scenario's scripted request, with the pointer. */
export async function openReport(page: Page) {
  await expectPortfolioLoaded(page);
  await confirmScenarioRules(page);
  await continueToPurchase(page);
  await checkIdeaAndWaitForReport(page);
}

/**
 * Every block of figures on the page carries the visible "Test data" marker.
 * A marker inside a closed section does not count unless it is on the line
 * that stays visible.
 */
export async function expectTestDataMarkers(page: Page, context: string) {
  const blocks = page.getByRole("main").locator('[data-figures="true"]');
  const count = await blocks.count();
  expect(count, `no block of figures found on: ${context}`).toBeGreaterThan(0);
  for (let index = 0; index < count; index += 1) {
    const block = blocks.nth(index);
    if (!(await block.isVisible())) continue;
    const name = await block.evaluate((element) => element.id || element.getAttribute("data-testid") || element.tagName.toLowerCase());
    const tags = block.getByTestId("test-data-tag");
    const visible = await tags.evaluateAll((elements) => elements.filter((element) => (element as HTMLElement).checkVisibility()).length);
    expect(visible, `block "${name}" has no visible "Test data" marker on: ${context}`).toBeGreaterThan(0);
  }
}

/**
 * The chart of every company, placed directly in the exposure panel. The
 * explorer beside it holds its own view of one company (flat when the 3D
 * drawing cannot be used), so a test names the chart it means.
 */
export function overviewChart(page: Page): Locator {
  return page.locator('[data-testid="exposure-views"] > [data-testid="exposure-chart"]');
}

/** True when this browser can create a WebGL context: the 3D drawing of the explorer needs one. */
export async function browserHasWebGL(page: Page): Promise<boolean> {
  return page.evaluate(() => {
    const canvas = document.createElement("canvas");
    return Boolean(canvas.getContext("webgl2") ?? canvas.getContext("webgl"));
  });
}

/** WCAG 2.0, 2.1 and 2.2 at levels A and AA, plus axe's best-practice rules (landmarks, heading order, unique names). */
const AXE_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"];

/** Runs axe-core against the page as it is now and fails on any violation. */
export async function expectNoAxeViolations(page: Page, context: string) {
  const results = await new AxeBuilder({ page }).withTags(AXE_TAGS).analyze();
  const summary = results.violations.map((violation) => ({
    rule: violation.id,
    impact: violation.impact,
    help: violation.help,
    nodes: violation.nodes.slice(0, 5).map((node) => `${node.target.join(" ")}: ${node.failureSummary?.replace(/\s+/g, " ")}`),
  }));
  expect(summary, `axe violations on: ${context}`).toEqual([]);
  // Guard against an empty run passing by accident.
  expect(results.passes.length, `axe ran no rule on: ${context}`).toBeGreaterThan(10);
}

/**
 * Waits until entrance animations have ended, so layout is measured where it
 * comes to rest. (The evidence drawer slides in from 24px to the right of its
 * final place for 160ms.) Animations that never end are not waited for.
 */
export async function waitForAnimationsToEnd(page: Page) {
  await page.evaluate(async () => {
    const finite = document.getAnimations().filter((animation) => Number.isFinite(animation.effect?.getComputedTiming().endTime ?? Infinity));
    await Promise.all(finite.map((animation) => animation.finished.catch(() => undefined)));
  });
}

/** Nothing is wider than the viewport: the page does not scroll sideways. */
export async function expectNoHorizontalOverflow(page: Page, context: string) {
  await waitForAnimationsToEnd(page);
  const overflow = await page.evaluate(() => {
    const root = document.documentElement;
    const offenders: string[] = [];
    for (const element of Array.from(document.querySelectorAll<HTMLElement>("body *"))) {
      const rect = element.getBoundingClientRect();
      if (rect.width === 0 || rect.height === 0) continue;
      // Visually hidden helper text is clipped on purpose.
      if (element.closest(".sr-only")) continue;
      if (rect.right > root.clientWidth + 1 || rect.left < -1) {
        offenders.push(`${element.tagName.toLowerCase()}.${String(element.className).split(" ").slice(0, 3).join(".")} [${Math.round(rect.left)}..${Math.round(rect.right)}]`);
      }
    }
    return { scrollWidth: root.scrollWidth, clientWidth: root.clientWidth, offenders: offenders.slice(0, 8) };
  });
  expect(overflow.offenders, `elements wider than the viewport on: ${context}`).toEqual([]);
  expect(overflow.scrollWidth, `page scrolls sideways on: ${context}`).toBeLessThanOrEqual(overflow.clientWidth);
}
