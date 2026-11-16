import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { renderApp, stageHeading } from "@/test/app";
import { resetLocaleRuntimeForTests } from "@/lib/i18n";
import { formatDate } from "@/lib/format";
import { coverageText, statusText } from "@/lib/verdict";
import { assetClassLabel } from "@/lib/portfolio";
import { toolLabel } from "@/components/timeline/StepTimeline";

describe("language selection", () => {
  it("switches the interface to French and restores the saved language after remount", async () => {
    const user = userEvent.setup();
    const firstRender = renderApp();

    const language = screen.getByRole("combobox", { name: "Language" });
    expect(language).toHaveValue("en");
    await user.selectOptions(language, "fr");

    await waitFor(() => expect(document.documentElement).toHaveAttribute("lang", "fr"));
    expect(screen.getByRole("combobox", { name: "Langue" })).toHaveValue("fr");
    expect(stageHeading()).toHaveTextContent("Choisir un profil");
    expect(screen.getByTestId("simulation-label")).toHaveTextContent(
      "Simulation — portefeuille fictif, pas un conseil financier",
    );
    expect(screen.getByRole("region", { name: "Quel profil souhaitez-vous essayer ?" })).toBeInTheDocument();
    expect(statusText("PASS")).toBe("Respectée");
    expect(coverageText("PARTIAL")).toBe("Partielle");
    expect(assetClassLabel("equity")).toBe("Action");
    expect(toolLabel("get_portfolio")).toBe("Lire le portefeuille");
    expect(formatDate("2026-11-12")).toBe("12 nov. 2026");
    expect(window.localStorage.getItem("byb.locale")).toBe("fr");

    firstRender.unmount();
    // A document reload starts a fresh module state; the preference is read
    // from local storage after the new interface mounts.
    resetLocaleRuntimeForTests();
    const secondRender = renderApp();

    await waitFor(() => expect(screen.getByRole("combobox", { name: "Langue" })).toHaveValue("fr"));
    expect(stageHeading()).toHaveTextContent("Choisir un profil");

    await user.selectOptions(screen.getByRole("combobox", { name: "Langue" }), "en");
    await waitFor(() => expect(screen.getByRole("combobox", { name: "Language" })).toHaveValue("en"));
    expect(stageHeading()).toHaveTextContent("Choose a profile");
    expect(window.localStorage.getItem("byb.locale")).toBe("en");
    secondRender.unmount();
    resetLocaleRuntimeForTests();
  });
});
