import { describe, expect, it } from "vitest";
import { normalizeBaseUrl, resolveRuntimeConfig } from "./config";

describe("resolveRuntimeConfig", () => {
  it("runs on fixtures when no API base URL was configured", () => {
    expect(resolveRuntimeConfig({ apiBaseUrl: undefined, search: "" })).toMatchObject({
      mode: "fixtures",
      apiBaseUrl: null,
      fixturesReason: "no-base-url",
    });
    expect(resolveRuntimeConfig({ apiBaseUrl: "   ", search: "" }).mode).toBe("fixtures");
  });

  it("runs live when a base URL is configured", () => {
    expect(resolveRuntimeConfig({ apiBaseUrl: "https://api.example.test/prod/", search: "" })).toEqual({
      mode: "live",
      apiBaseUrl: "https://api.example.test/prod",
      fixturesReason: null,
      simulate: null,
    });
  });

  it("lets ?fixtures=1 force fixtures even when a base URL is configured", () => {
    const config = resolveRuntimeConfig({ apiBaseUrl: "https://api.example.test", search: "?fixtures=1" });
    expect(config.mode).toBe("fixtures");
    expect(config.fixturesReason).toBe("requested");
  });

  it("only accepts exactly fixtures=1", () => {
    expect(resolveRuntimeConfig({ apiBaseUrl: "https://api.example.test", search: "?fixtures=0" }).mode).toBe("live");
    expect(resolveRuntimeConfig({ apiBaseUrl: "https://api.example.test", search: "?fixtures=true" }).mode).toBe("live");
  });

  it("falls back to fixtures, and says why, when the base URL is not a usable URL", () => {
    expect(resolveRuntimeConfig({ apiBaseUrl: "not a url", search: "" })).toMatchObject({
      mode: "fixtures",
      fixturesReason: "invalid-base-url",
    });
    expect(resolveRuntimeConfig({ apiBaseUrl: "ftp://example.test", search: "" }).fixturesReason).toBe("invalid-base-url");
  });

  it("honours a failure simulation in fixtures mode only", () => {
    expect(resolveRuntimeConfig({ apiBaseUrl: undefined, search: "?simulate=job-failed" }).simulate).toBe("job-failed");
    expect(resolveRuntimeConfig({ apiBaseUrl: undefined, search: "?simulate=nonsense" }).simulate).toBeNull();
    expect(resolveRuntimeConfig({ apiBaseUrl: "https://api.example.test", search: "?simulate=job-failed" }).simulate).toBeNull();
  });
});

describe("normalizeBaseUrl", () => {
  it("removes trailing slashes", () => {
    expect(normalizeBaseUrl("https://api.example.test///")).toEqual({ url: "https://api.example.test", invalid: false });
  });
});
