import { describe, expect, it, vi } from "vitest";
import {
  browserSupportsWebGL,
  decideRenderMode,
  fallbackReasonText,
  MIN_3D_VIEWPORT_WIDTH,
  resetBrowserWebGLCache,
  supportsWebGL,
  type FallbackReason,
  type RenderEnvironment,
} from "./capability";

const GOOD: RenderEnvironment = { ready: true, webgl: true, forcedColors: false, reducedMotion: false, viewportWidth: 1440, sceneFailure: null };

describe("supportsWebGL", () => {
  it("is true when a webgl2 context can be created", () => {
    const getContext = vi.fn((id: string) => (id === "webgl2" ? {} : null));
    expect(supportsWebGL(() => ({ getContext }))).toBe(true);
    expect(getContext).toHaveBeenCalledTimes(1);
  });

  it("falls back to webgl 1", () => {
    const getContext = vi.fn((id: string) => (id === "webgl" ? {} : null));
    expect(supportsWebGL(() => ({ getContext }))).toBe(true);
    expect(getContext.mock.calls.map(([id]) => id)).toEqual(["webgl2", "webgl"]);
  });

  it("is false when the browser refuses every context", () => {
    expect(supportsWebGL(() => ({ getContext: () => null }))).toBe(false);
  });

  it("is false when creating the canvas or the context throws", () => {
    expect(
      supportsWebGL(() => {
        throw new Error("no canvas");
      }),
    ).toBe(false);
    expect(
      supportsWebGL(() => ({
        getContext: () => {
          throw new Error("blocked");
        },
      })),
    ).toBe(false);
  });

  it("gives the probe context back", () => {
    const loseContext = vi.fn();
    const context = { getExtension: (name: string) => (name === "WEBGL_lose_context" ? { loseContext } : null) };
    expect(supportsWebGL(() => ({ getContext: () => context }))).toBe(true);
    expect(loseContext).toHaveBeenCalledTimes(1);
  });

  it("reports no WebGL in a test DOM, which has none", () => {
    resetBrowserWebGLCache();
    expect(browserSupportsWebGL()).toBe(false);
  });
});

describe("decideRenderMode", () => {
  it("chooses 3D only when everything allows it", () => {
    expect(decideRenderMode(GOOD)).toEqual({ mode: "3D" });
    expect(decideRenderMode({ ...GOOD, viewportWidth: MIN_3D_VIEWPORT_WIDTH })).toEqual({ mode: "3D" });
  });

  it.each<[string, Partial<RenderEnvironment>, FallbackReason]>([
    ["before the browser has been inspected", { ready: false }, "NOT_READY"],
    ["without WebGL", { webgl: false }, "NO_WEBGL"],
    ["in forced-colours mode", { forcedColors: true }, "FORCED_COLORS"],
    ["when the reader asked for reduced motion", { reducedMotion: true }, "REDUCED_MOTION"],
    ["on a viewport narrower than 768 px", { viewportWidth: MIN_3D_VIEWPORT_WIDTH - 1 }, "NARROW_VIEWPORT"],
    ["after the chunk failed to load or the scene threw", { sceneFailure: "LOAD_OR_RENDER_ERROR" }, "LOAD_OR_RENDER_ERROR"],
    ["after the renderer could not start", { sceneFailure: "INIT_FAILED" }, "INIT_FAILED"],
    ["after the graphics context was lost", { sceneFailure: "CONTEXT_LOST" }, "CONTEXT_LOST"],
  ])("uses the fallback %s", (_name, change, reason) => {
    expect(decideRenderMode({ ...GOOD, ...change })).toEqual({ mode: "FALLBACK", reason });
  });

  it("keeps a scene failure even when everything else would allow 3D", () => {
    expect(decideRenderMode({ ...GOOD, sceneFailure: "CONTEXT_LOST" }).mode).toBe("FALLBACK");
  });
});

describe("fallbackReasonText", () => {
  it("explains every reason except the first paint", () => {
    expect(fallbackReasonText("NOT_READY")).toBeNull();
    for (const reason of ["NO_WEBGL", "FORCED_COLORS", "REDUCED_MOTION", "NARROW_VIEWPORT", "LOAD_OR_RENDER_ERROR", "INIT_FAILED", "CONTEXT_LOST"] as const) {
      expect(fallbackReasonText(reason)).toMatch(/shown instead/);
    }
  });
});
