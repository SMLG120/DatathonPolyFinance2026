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
  stepLink,
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
  await expect(page.getByRole("link", { name: "Analyze My Portfolio" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Explore 3D Portfolio" })).toBeVisible();
  await expect(page.getByText("Before You Buy")).toHaveCount(0);
  await expect(page.getByText(/investra/i)).toHaveCount(0);
  await expectPersistentLabels(page);
}

/** The whole path of both calls to action, at the viewport of the surrounding block. */
async function brandJourney(page: Page, context: string) {
  await page.goto(START_URL);
  await expectPortfolioLoaded(page);
  await expect(page).toHaveTitle("Choose a profile: ETHOS: fictional simulation");
  await expectBrand(page);
  await expectNoHorizontalOverflow(page, `${context}, first screen`);
  await expectNoAxeViolations(page, `${context}, first screen with the brand message`);

  // "Analyze My Portfolio" opens the purchase step.
  await page.getByRole("link", { name: "Analyze My Portfolio" }).click();
  await expectScreen(page, "purchase");
  await expect(page.getByRole("main")).not.toBeEmpty();

  // With no result yet, "Explore 3D Portfolio" says so and leads to the same working step, never to an empty page.
  await stepLink(page, 1).click();
  await expectScreen(page, "persona");
  const explore = page.getByRole("link", { name: "Explore 3D Portfolio" });
  await expect(explore).toHaveAttribute("href", "#/purchase");
  await expect(page.getByTestId("brand-cta-note")).toContainText("none has been checked in this session yet");
  await explore.click();
  await expectScreen(page, "purchase");
  await expect(page.getByTestId("start-investigation")).toBeVisible();

  // After an analysis, the same button opens the exposure section of the report, where the explorer is.
  await stepLink(page, 1).click();
  await expectScreen(page, "persona");
  await openReport(page);
  await expect(page.locator("#report-exposure")).toHaveJSProperty("open", false);
  await stepLink(page, 1).click();
  await expectScreen(page, "persona");
  await expect(explore).toHaveAttribute("href", "#/verdict");
  await expect(page.getByTestId("brand-cta-note")).toHaveText("Opens the 3D exposure view of the latest result in this session.");
  await explore.click();
  await expectScreen(page, "verdict", { focused: false });
  await expect(page.locator("#report-exposure")).toHaveJSProperty("open", true);
  const explorer = page.getByTestId("exposure-explorer");
  await expect(explorer).toBeVisible();
  await expect(explorer).toBeInViewport();
  await expect(page.locator("#report-exposure > summary")).toBeFocused();
  await expectNoHorizontalOverflow(page, `${context}, explorer opened from the brand message`);
  return explorer;
}

test.describe("ETHOS brand message and its two calls to action", () => {
  test("desktop: branding, both calls to action, and the explorer after an analysis", async ({ page }) => {
    test.setTimeout(120_000);
    const explorer = await brandJourney(page, "desktop");
    await expect(explorer).toHaveAttribute("data-status", "READY");
    // The drawing needs WebGL; without it the explorer shows the same values flat. Either is a useful view.
    if (await browserHasWebGL(page)) await expect(explorer.locator("canvas")).toBeVisible({ timeout: 20_000 });
    await expect(explorer.getByTestId("explorer-table")).toBeAttached();
  });

  test.describe("at a phone's width", () => {
    test.use({ viewport: { width: 390, height: 844 } });
    test("mobile: branding, both calls to action, and the explorer after an analysis", async ({ page }) => {
      test.setTimeout(120_000);
      const explorer = await brandJourney(page, "mobile");
      await expect(explorer).toHaveAttribute("data-status", "READY");
    });
  });
});
