import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";
import { deferred, type Deferred } from "@/test/deferred";
import { useDebouncedPreview } from "./useDebouncedPreview";

const DELAY = 400;

function controllableRequest() {
  const calls: { input: number; signal: AbortSignal; answer: Deferred<string> }[] = [];
  const request = vi.fn((input: number, signal: AbortSignal) => {
    const answer = deferred<string>();
    calls.push({ input, signal, answer });
    return answer.promise;
  });
  return { request, calls };
}

describe("useDebouncedPreview", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("waits for the debounce delay before calling", () => {
    const { request } = controllableRequest();
    const { result } = renderHook(() => useDebouncedPreview(request, DELAY));

    act(() => result.current.schedule(0.1));
    expect(result.current.status).toBe("waiting");
    act(() => vi.advanceTimersByTime(DELAY - 1));
    expect(request).not.toHaveBeenCalled();

    act(() => vi.advanceTimersByTime(1));
    expect(request).toHaveBeenCalledTimes(1);
    expect(result.current.status).toBe("loading");
  });

  it("sends only the last draft of a burst of changes", () => {
    const { request, calls } = controllableRequest();
    const { result } = renderHook(() => useDebouncedPreview(request, DELAY));

    act(() => result.current.schedule(0.1));
    act(() => vi.advanceTimersByTime(100));
    act(() => result.current.schedule(0.11));
    act(() => vi.advanceTimersByTime(100));
    act(() => result.current.schedule(0.12));
    act(() => vi.advanceTimersByTime(DELAY));

    expect(request).toHaveBeenCalledTimes(1);
    expect(calls[0]?.input).toBe(0.12);
  });

  it("ties the preview on screen to the draft it was calculated for", async () => {
    const { request, calls } = controllableRequest();
    const { result } = renderHook(() => useDebouncedPreview(request, DELAY));

    act(() => result.current.schedule(0.1));
    act(() => vi.advanceTimersByTime(DELAY));
    await act(async () => calls[0]?.answer.resolve("preview for 10%"));
    expect(result.current).toMatchObject({ status: "ready", input: 0.1, result: "preview for 10%" });

    // The draft changes: the old preview must disappear at once, not sit beside the new number.
    act(() => result.current.schedule(0.3));
    expect(result.current).toMatchObject({ status: "waiting", input: 0.3, result: null });
  });

  it("never lets a stale answer replace a newer one", async () => {
    const { request, calls } = controllableRequest();
    const { result } = renderHook(() => useDebouncedPreview(request, DELAY));

    act(() => result.current.schedule(0.1));
    act(() => vi.advanceTimersByTime(DELAY));
    act(() => result.current.schedule(0.3));
    act(() => vi.advanceTimersByTime(DELAY));
    expect(request).toHaveBeenCalledTimes(2);
    expect(calls[0]?.signal.aborted).toBe(true);

    await act(async () => calls[1]?.answer.resolve("preview for 30%"));
    await act(async () => calls[0]?.answer.resolve("preview for 10% (late)"));
    expect(result.current).toMatchObject({ status: "ready", input: 0.3, result: "preview for 30%" });
  });

  it("ignores a stale answer that arrives while the newer draft is still waiting", async () => {
    const { request, calls } = controllableRequest();
    const { result } = renderHook(() => useDebouncedPreview(request, DELAY));

    act(() => result.current.schedule(0.1));
    act(() => vi.advanceTimersByTime(DELAY));
    act(() => result.current.schedule(0.3));
    await act(async () => calls[0]?.answer.resolve("preview for 10% (late)"));

    expect(result.current).toMatchObject({ status: "waiting", input: 0.3, result: null });
  });

  it("reports an error for the current draft only", async () => {
    const { request, calls } = controllableRequest();
    const { result } = renderHook(() => useDebouncedPreview(request, DELAY));
    const failure = new ApiError("server", "preview failed");

    act(() => result.current.schedule(0.1));
    act(() => vi.advanceTimersByTime(DELAY));
    await act(async () => calls[0]?.answer.reject(failure));
    expect(result.current).toMatchObject({ status: "error", input: 0.1, result: null, error: failure });
  });

  it("drops everything on clear", async () => {
    const { request, calls } = controllableRequest();
    const { result } = renderHook(() => useDebouncedPreview(request, DELAY));

    act(() => result.current.schedule(0.1));
    act(() => vi.advanceTimersByTime(DELAY));
    act(() => result.current.clear());
    expect(result.current).toMatchObject({ status: "idle", input: null, result: null });

    await act(async () => calls[0]?.answer.resolve("late"));
    expect(result.current.status).toBe("idle");
  });

  it("makes no call if the draft is cleared before the delay ends", () => {
    const { request } = controllableRequest();
    const { result } = renderHook(() => useDebouncedPreview(request, DELAY));

    act(() => result.current.schedule(0.1));
    act(() => result.current.clear());
    act(() => vi.advanceTimersByTime(DELAY * 2));
    expect(request).not.toHaveBeenCalled();
  });

  it("cancels the pending call on unmount", () => {
    const { request } = controllableRequest();
    const { result, unmount } = renderHook(() => useDebouncedPreview(request, DELAY));

    act(() => result.current.schedule(0.1));
    unmount();
    act(() => vi.advanceTimersByTime(DELAY * 2));
    expect(request).not.toHaveBeenCalled();
  });
});
