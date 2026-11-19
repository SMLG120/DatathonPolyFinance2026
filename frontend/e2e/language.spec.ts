import { expect, test } from "@playwright/test";
import { expectNoAxeViolations, expectPortfolioLoaded, START_URL } from "./helpers";

test.describe("English / French", () => {
  test("the header switches the whole journey to French, keeps it after a reload, and switches back", async ({ page }) => {
    await page.goto(START_URL);
    await expectPortfolioLoaded(page);
    const language = page.getByRole("combobox", { name: "Language" });
    await expect(language).toHaveValue("en");

    await language.selectOption("fr");
    await expect(page.locator("html")).toHaveAttribute("lang", "fr");
    await expect(page.getByRole("heading", { level: 1 })).toContainText("Choisir un profil");
    await expect(page.getByRole("button", { name: /Commencer|profil/i }).first()).toBeVisible();
    await expect(page.getByTestId("simulation-label")).toContainText("pas un conseil");
    await expectNoAxeViolations(page, "first screen in French");

    // The choice is kept for the next visit.
    await page.reload();
    // The shared helper reads English text; after the reload the page is French, so wait on the table itself.
    await expect(page.getByTestId("portfolio-table")).toContainText("Portefeuille fictif de Robert");
    await expect(page.getByRole("combobox", { name: "Langue" })).toHaveValue("fr");
    await expect(page.getByRole("heading", { level: 1 })).toContainText("Choisir un profil");

    await page.getByRole("combobox", { name: "Langue" }).selectOption("en");
    await expect(page.locator("html")).toHaveAttribute("lang", "en");
    await expect(page.getByRole("heading", { level: 1 })).toContainText("Choose a profile");
  });
});
