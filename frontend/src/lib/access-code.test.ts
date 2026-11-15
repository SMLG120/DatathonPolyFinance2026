import { describe, expect, it, vi } from "vitest";
import { clearAccessCode, readAccessCode, storeAccessCode, subscribeAccessCode } from "./access-code";

describe("access code storage", () => {
  it("keeps the code in sessionStorage and nowhere else", () => {
    storeAccessCode("  demo-code-123  ");

    expect(readAccessCode()).toBe("demo-code-123");
    expect(JSON.stringify(window.sessionStorage)).toContain("demo-code-123");
    expect(JSON.stringify(window.localStorage)).not.toContain("demo-code-123");
    expect(document.cookie).not.toContain("demo-code-123");
    expect(window.location.href).not.toContain("demo-code-123");

    clearAccessCode();
  });

  it("forgets the code when cleared", () => {
    storeAccessCode("demo-code-123");
    clearAccessCode();
    expect(readAccessCode()).toBeNull();
    expect(window.sessionStorage.length).toBe(0);
  });

  it("notifies subscribers when the code changes", () => {
    const listener = vi.fn();
    const unsubscribe = subscribeAccessCode(listener);

    storeAccessCode("a");
    clearAccessCode();
    expect(listener).toHaveBeenCalledTimes(2);

    unsubscribe();
    storeAccessCode("b");
    expect(listener).toHaveBeenCalledTimes(2);
    clearAccessCode();
  });

  it("is never written to the console", () => {
    const spies = (["log", "info", "warn", "error", "debug"] as const).map((method) =>
      vi.spyOn(console, method).mockImplementation(() => {}),
    );
    storeAccessCode("demo-code-123");
    readAccessCode();
    clearAccessCode();
    for (const spy of spies) expect(spy).not.toHaveBeenCalled();
  });
});
