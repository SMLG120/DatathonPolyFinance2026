import { expect, test, type Page } from "@playwright/test";
import {
  browserHasWebGL,
  expectNoAxeViolations,
  expectNoHorizontalOverflow,
  expectPersistentLabels,
  expectPortfolioLoaded,
  expectScreen,
  openReport,
  START_URL,
} from "./helpers";

const HEADLINE = "Invest with conviction.Not contradiction.";
const SUBTITLE =
  "Your AI-powered investment decision investigator. Uncover hidden exposure, verify your financial rules, and understand every trade before you commit.";
const TAGLINE = "ETHOS — The AI Agent That Challenges Your Investments Before the Market Does.";

async function expectBrand(page: Page) {
  await expect(page.getByRole("banner").getByText("ETHOS", { exact: true })).toBeVisible();
  await expect(page.getByTestId("brand-headline")).toBeVisible();
  await expect(page.getByTestId("brand-headline")).toHaveText(HEADLINE);
  await expect(page.getByTestId("brand-subtitle")).toHaveText(SUBTITLE);
  await expect(page.getByTestId("brand-tagline")).toHaveText(TAGLINE);
  await expect(page.getByRole("button", { name: "Start with a profile" })).toBeVisible();
  // No call to action jumps ahead from the first screen: it would skip the profile and the limits.
  await expect(page.getByTestId("brand-hero").getByRole("link")).toHaveCount(0);
  // The former product name, in its own capitals. "Before you buy something, …" in the introduction is ordinary prose.
  await expect(page.getByText(/Before You Buy/)).toHaveCount(0);
  await expect(page.getByText(/investra/i)).toHaveCount(0);
  await expectPersistentLabels(page);
}

/** The brand message's call to action, then the 3D explorer in the place it has data to draw: the result. */
async function brandJourney(page: Page, context: string) {
  await page.goto(START_URL);
  await expectPortfolioLoaded(page);
  await expect(page).toHaveTitle("Choose a profile: ETHOS: fictional simulation");
  await expectBrand(page);
  await expectNoHorizontalOverflow(page, `${context}, first screen`);
  await expectNoAxeViolations(page, `${context}, first screen with the brand message`);

  // "Start with a profile" stays on step 1 and moves focus to the persona chooser.
  await page.getByRole("button", { name: "Start with a profile" }).click();
  await expectScreen(page, "persona", { focused: false });
  const chooser = page.getByRole("heading", { name: "Who would you like to try?" });
  await expect(chooser).toBeFocused();
  await expect(chooser).toBeInViewport();

  // The 3D explorer is reached through the journey: it sits in the result's exposure section.
  await openReport(page);
  await page.locator("#report-exposure > summary").click();
  await expect(page.locator("#report-exposure")).toHaveJSProperty("open", true);
  const explorer = page.getByTestId("exposure-explorer");
  await expect(explorer).toBeVisible();
  await expectNoHorizontalOverflow(page, `${context}, explorer opened in the result`);
  return explorer;
}

test.describe("ETHOS brand message and its call to action", () => {
  test("desktop: branding, the call to action, and the explorer in the result", async ({ page }) => {
    test.setTimeout(120_000);
    const explorer = await brandJourney(page, "desktop");
    await expect(explorer).toHaveAttribute("data-status", "READY");
    // The drawing needs WebGL; without it the explorer shows the same values flat. Either is a useful view.
    if (await browserHasWebGL(page)) await expect(explorer.locator("canvas")).toBeVisible({ timeout: 20_000 });
    await expect(explorer.getByTestId("explorer-table")).toBeAttached();
  });

  test.describe("at a phone's width", () => {
    test.use({ viewport: { width: 390, height: 844 } });
    test("mobile: branding, the call to action, and the explorer in the result", async ({ page }) => {
      test.setTimeout(120_000);
      const explorer = await brandJourney(page, "mobile");
      await expect(explorer).toHaveAttribute("data-status", "READY");
    });
  });
});
