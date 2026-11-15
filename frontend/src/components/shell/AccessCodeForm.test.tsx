import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api";
import { LIVE_CONFIG, renderWithApp } from "@/test/render";
import { AccessCodeForm } from "./AccessCodeForm";

const SECRET = "demo-code-7421";
const STORAGE_KEY = "byb.accessCode";

function setup(verifyAccessCode: (code: string) => Promise<void>) {
  const consoleSpies = (["log", "info", "warn", "error", "debug"] as const).map((method) => vi.spyOn(console, method).mockImplementation(() => {}));
  renderWithApp(<AccessCodeForm />, { config: LIVE_CONFIG, verifyAccessCode });
  return { user: userEvent.setup(), field: screen.getByLabelText("Access code"), submit: screen.getByRole("button", { name: "Continue" }), consoleSpies };
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("AccessCodeForm", () => {
  it("hides the code by default and lets the user reveal it", async () => {
    const { field, user } = setup(vi.fn().mockResolvedValue(undefined));
    expect(field).toHaveAttribute("type", "password");
    expect(field).toHaveAttribute("autocomplete", "off");
    await user.click(screen.getByRole("checkbox", { name: "Show the code as I type" }));
    expect(field).toHaveAttribute("type", "text");
  });

  it("asks for a code instead of calling the service with an empty one", async () => {
    const verify = vi.fn().mockResolvedValue(undefined);
    const { field, submit, user } = setup(verify);
    await user.click(submit);
    expect(screen.getByText("Enter the access code you were given.")).toBeInTheDocument();
    expect(field).toHaveFocus();
    expect(field).toHaveAttribute("aria-invalid", "true");
    expect(verify).not.toHaveBeenCalled();
  });

  it("keeps an accepted code in sessionStorage only", async () => {
    const verify = vi.fn().mockResolvedValue(undefined);
    const { field, submit, user, consoleSpies } = setup(verify);
    await user.type(field, `  ${SECRET} `);
    await user.click(submit);

    await waitFor(() => expect(window.sessionStorage.getItem(STORAGE_KEY)).toBe(SECRET));
    expect(verify).toHaveBeenCalledWith(SECRET);
    // Nowhere else: not in localStorage, not in the URL, not in a cookie, not in the console.
    expect(JSON.stringify(window.localStorage)).not.toContain(SECRET);
    expect(window.location.href).not.toContain(SECRET);
    expect(document.cookie).not.toContain(SECRET);
    for (const spy of consoleSpies) {
      expect(JSON.stringify(spy.mock.calls)).not.toContain(SECRET);
    }
  });

  it("does not store a code the service refuses, and says so on the field", async () => {
    const verify = vi.fn().mockRejectedValue(new ApiError("unauthorized", "The access code was not accepted.", { status: 401 }));
    const { field, submit, user } = setup(verify);
    await user.type(field, "wrong-code");
    await user.click(submit);

    expect(await screen.findByText("The service did not accept this code. Check it and try again.")).toBeInTheDocument();
    expect(window.sessionStorage.getItem(STORAGE_KEY)).toBeNull();
    expect(field).toHaveFocus();
    expect(submit).not.toHaveAttribute("aria-disabled");
  });

  it("reports a service that cannot be reached as an error, not as a wrong code", async () => {
    const verify = vi.fn().mockRejectedValue(new ApiError("network", "The service could not be reached. Check your connection and try again."));
    const { field, submit, user } = setup(verify);
    await user.type(field, SECRET);
    await user.click(submit);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("The code could not be checked");
    expect(alert).toHaveTextContent("The service could not be reached");
    expect(alert).toHaveTextContent("Nothing was stored");
    expect(window.sessionStorage.getItem(STORAGE_KEY)).toBeNull();
  });

  it("offers the test-data mode as a way in without a code", () => {
    setup(vi.fn());
    expect(screen.getByRole("link", { name: "Open the simulation with test data" })).toHaveAttribute("href", "?fixtures=1");
  });
});
