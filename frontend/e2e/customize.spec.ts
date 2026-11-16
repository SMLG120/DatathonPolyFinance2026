import { expect, test } from "@playwright/test";
import { expectNoAxeViolations, expectPortfolioLoaded, expectVisibleFocusRing, START_URL, tabTo } from "./helpers";

const REASON = "Customization needs the live service: the test data only replays results recorded for the original portfolio.";

/**
 * "Customize this profile" on test data. The fixtures client replays results
 * recorded for the original portfolios and calculates nothing, so the control
 * is shown unavailable, with the reason, for every persona. What the editor
 * does on a live service is covered by the component tests
 * (src/components/portfolio/Customize*.test.tsx) and by
 * acceptance/fullstack/specs/06-customize.spec.ts.
 */
test.describe("Customize this profile, on test data", () => {
  test("is shown unavailable with its explanation for Robert, Mateo and Amira, and opens no editor", async ({ page }) => {
    await page.goto(START_URL);
    await expectPortfolioLoaded(page);

    for (const persona of ["Robert", "Mateo", "Amira"]) {
      if (persona !== "Robert") {
        await page.getByRole("button", { name: `Use ${persona}’s portfolio` }).click();
        await expectPortfolioLoaded(page, persona);
      }
      const panel = page.getByRole("region", { name: "Customize this profile" });
      await expect(panel).toBeVisible();
      await expect(panel).toContainText(`${persona}’s fictional portfolio`);
      const open = page.getByTestId("customize-open");
      await expect(open).toBeVisible();
      await expect(open).toHaveText("Customize this profile");
      await expect(open).toHaveAttribute("aria-disabled", "true");
      // The reason is on screen and is the description of the control, so it is read out with it.
      const reason = page.getByTestId("customize-unavailable");
      await expect(reason).toBeVisible();
      await expect(reason).toHaveText(REASON);
      await expect(open).toHaveAccessibleDescription(REASON);

      // It stays a tab stop, and activating it from the keyboard opens no editor and applies nothing.
      await tabTo(page, open);
      await expectVisibleFocusRing(open);
      await page.keyboard.press("Enter");
      await page.keyboard.press("Space");
      await expect(page.getByTestId("customize-apply")).toHaveCount(0);
      await expect(page.getByTestId("customize-row")).toHaveCount(0);
      await expect(page.getByTestId("customized-badge")).toHaveCount(0);
      await expect(page.getByTestId("customize-reset")).toHaveCount(0);
      await expect(open).toBeFocused();
      await expectNoAxeViolations(page, `customize unavailable on test data, ${persona}`);
    }
  });
});
