import AxeBuilder from "@axe-core/playwright";
import { expect, type Locator, type Page } from "@playwright/test";

/** Every test opens the static build in fixtures mode, whatever the build was configured with. */
export const START_URL = "/?fixtures=1";

export const STAGE_TITLES = ["Persona & portfolio", "Goals & rules", "Proposed purchase", "Investigation steps", "Verdict & evidence", "Challenge"] as const;

export function stageHeading(page: Page): Locator {
  return page.locator("[data-stage-heading]");
}

/** The stage is shown and — because a stage change is a page change — its heading has focus. */
export async function expectStage(page: Page, number: number, { focused = true }: { focused?: boolean } = {}) {
  const heading = stageHeading(page);
  await expect(heading).toHaveText(`Step ${number} of 6: ${STAGE_TITLES[number - 1]}`);
  if (focused) await expect(heading).toBeFocused();
  await expect(page.getByRole("link", { name: new RegExp(`^Step ${number} of 6: `) })).toHaveAttribute("aria-current", "step");
}

/** The labels that must be on screen on every stage. */
export async function expectPersistentLabels(page: Page) {
  await expect(page.getByTestId("simulation-label")).toBeVisible();
  await expect(page.getByTestId("simulation-label")).toHaveText("Simulation — fictional portfolio, not advice");
  await expect(page.getByTestId("fixtures-label")).toBeVisible();
  await expect(page.getByTestId("fixtures-label")).toHaveText("Test data — fixtures");
  await expect(page.getByTestId("valuation-date")).toBeVisible();
  await expect(page.getByTestId("valuation-date")).toHaveText("Valuation date: 12 Nov 2026");
}

/**
 * Moves focus to `target` with the Tab key only, the way a keyboard user gets
 * there. Fails if the element cannot be reached.
 */
export async function tabTo(page: Page, target: Locator, maxPresses = 120) {
  await expect(target).toBeVisible();
  for (let presses = 0; presses < maxPresses; presses += 1) {
    if (await target.evaluate((element) => element === document.activeElement)) return;
    await page.keyboard.press("Tab");
  }
  await expect(target, `not reachable with ${maxPresses} presses of Tab`).toBeFocused();
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

/** WCAG 2.0, 2.1 and 2.2 at levels A and AA, plus axe's best-practice rules (landmarks, heading order, unique names). */
const AXE_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"];

/** Runs axe-core against the page as it is now and fails on any violation. */
export async function expectNoAxeViolations(page: Page, context: string) {
  const results = await new AxeBuilder({ page }).withTags(AXE_TAGS).analyze();
  const summary = results.violations.map((violation) => ({
    rule: violation.id,
    impact: violation.impact,
    help: violation.help,
    nodes: violation.nodes.slice(0, 5).map((node) => `${node.target.join(" ")} — ${node.failureSummary?.replace(/\s+/g, " ")}`),
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
