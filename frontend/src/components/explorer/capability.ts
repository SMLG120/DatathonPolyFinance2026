/**
 * Decides whether the 3D scene may be shown or the caller's fallback is used.
 *
 * Pure functions with injectable inputs, so the decision is unit-tested without
 * a browser. Nothing here touches financial data.
 */

/** Below this viewport width the fallback is used: the scene needs room for two columns and their labels. */
export const MIN_3D_VIEWPORT_WIDTH = 768;

export const WIDE_VIEWPORT_QUERY = `(min-width: ${MIN_3D_VIEWPORT_WIDTH}px)`;
export const FORCED_COLORS_QUERY = "(forced-colors: active)";
export const REDUCED_MOTION_QUERY = "(prefers-reduced-motion: reduce)";

/** Why the scene stopped after it had been chosen. */
export type SceneFailure = "LOAD_OR_RENDER_ERROR" | "INIT_FAILED" | "CONTEXT_LOST";

export type FallbackReason = "NOT_READY" | "NO_WEBGL" | "FORCED_COLORS" | "NARROW_VIEWPORT" | SceneFailure;

export interface RenderEnvironment {
  /** False until the component has run in a browser (static export, first paint). */
  ready: boolean;
  webgl: boolean;
  forcedColors: boolean;
  viewportWidth: number;
  sceneFailure: SceneFailure | null;
}

export type RenderDecision = { mode: "3D" } | { mode: "FALLBACK"; reason: FallbackReason };

/** The first reason that applies wins; a scene failure is permanent for the mounted component. */
export function decideRenderMode(environment: RenderEnvironment): RenderDecision {
  if (!environment.ready) return { mode: "FALLBACK", reason: "NOT_READY" };
  if (environment.sceneFailure) return { mode: "FALLBACK", reason: environment.sceneFailure };
  if (!environment.webgl) return { mode: "FALLBACK", reason: "NO_WEBGL" };
  if (environment.forcedColors) return { mode: "FALLBACK", reason: "FORCED_COLORS" };
  if (environment.viewportWidth < MIN_3D_VIEWPORT_WIDTH) return { mode: "FALLBACK", reason: "NARROW_VIEWPORT" };
  return { mode: "3D" };
}

/** The part of a canvas this check needs. */
export interface CanvasLike {
  getContext(contextId: string): unknown;
}

interface LoseContext {
  loseContext(): void;
}

function releaseContext(context: unknown): void {
  // The probe context is given back at once so it does not count against the browser's context limit.
  const extension = (context as { getExtension?: (name: string) => LoseContext | null }).getExtension?.("WEBGL_lose_context");
  extension?.loseContext();
}

/**
 * True when a WebGL context can actually be created. A browser can expose the
 * API and still refuse a context (blocked GPU, too many contexts), so the check
 * creates one instead of testing for a global.
 */
export function supportsWebGL(createCanvas: () => CanvasLike): boolean {
  try {
    const canvas = createCanvas();
    for (const contextId of ["webgl2", "webgl"]) {
      const context = canvas.getContext(contextId);
      if (context) {
        releaseContext(context);
        return true;
      }
    }
    return false;
  } catch {
    return false;
  }
}

let cachedBrowserWebGL: boolean | null = null;

/** The browser check, run once per page. False outside a browser and where WebGL types do not exist (jsdom). */
export function browserSupportsWebGL(): boolean {
  if (cachedBrowserWebGL === null) {
    cachedBrowserWebGL =
      typeof document !== "undefined" && typeof WebGLRenderingContext !== "undefined" && supportsWebGL(() => document.createElement("canvas"));
  }
  return cachedBrowserWebGL;
}

/** For tests only: forget the cached browser check. */
export function resetBrowserWebGLCache(): void {
  cachedBrowserWebGL = null;
}

/** The sentence shown next to the fallback; null while nothing needs explaining. */
export function fallbackReasonText(reason: FallbackReason): string | null {
  switch (reason) {
    case "NOT_READY":
      return null;
    case "NO_WEBGL":
      return "The 3D view is not available in this browser, so the flat chart and the table are shown instead. They carry the same values.";
    case "FORCED_COLORS":
      return "High-contrast mode is on, so the flat chart and the table are shown instead of the 3D view. They carry the same values.";
    case "NARROW_VIEWPORT":
      return "On a narrow screen the flat chart and the table are shown instead of the 3D view. They carry the same values.";
    case "LOAD_OR_RENDER_ERROR":
    case "INIT_FAILED":
      return "The 3D view could not be started, so the flat chart and the table are shown instead. They carry the same values.";
    case "CONTEXT_LOST":
      return "The 3D view stopped (the browser took back its graphics context), so the flat chart and the table are shown instead. They carry the same values.";
  }
}
