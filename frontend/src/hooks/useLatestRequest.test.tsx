import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";
import { deferred, type Deferred } from "@/test/deferred";
import { useLatestRequest } from "./useLatestRequest";

/** A request whose answers the test releases by hand, in any order. */
function controllableRequest() {
  const calls: { arg: string; signal: AbortSignal; answer: Deferred<string> }[] = [];
  const request = vi.fn((signal: AbortSignal, arg: string) => {
    const answer = deferred<string>();
    calls.push({ arg, signal, answer });
    return answer.promise;
  });
  return { request, calls };
}

describe("useLatestRequest — stale-response guard", () => {
  it("applies the answer of a single request", async () => {
    const { request, calls } = controllableRequest();
    const { result } = renderHook(() => useLatestRequest(request));

    expect(result.current.state.status).toBe("idle");
    act(() => result.current.run("a"));
    expect(result.current.state.status).toBe("loading");

    await act(async () => calls[0]?.answer.resolve("answer-a"));
    expect(result.current.state).toEqual({ status: "success", data: "answer-a", error: null });
  });

  it("discards an older answer that arrives AFTER a newer one", async () => {
    const { request, calls } = controllableRequest();
    const { result } = renderHook(() => useLatestRequest(request));

    act(() => result.current.run("old"));
    act(() => result.current.run("new"));

    await act(async () => calls[1]?.answer.resolve("answer-new"));
    expect(result.current.state.data).toBe("answer-new");

    // The slow first request finally answers. It must not replace the newer answer.
    await act(async () => calls[0]?.answer.resolve("answer-old"));
    expect(result.current.state).toEqual({ status: "success", data: "answer-new", error: null });
  });

  it("discards an older answer that arrives BEFORE the newer one, and stays loading", async () => {
    const { request, calls } = controllableRequest();
    const { result } = renderHook(() => useLatestRequest(request));

    act(() => result.current.run("old"));
    act(() => result.current.run("new"));

    await act(async () => calls[0]?.answer.resolve("answer-old"));
    expect(result.current.state.status).toBe("loading");
    expect(result.current.state.data).toBeNull();

    await act(async () => calls[1]?.answer.resolve("answer-new"));
    expect(result.current.state.data).toBe("answer-new");
  });

  it("aborts the superseded request", () => {
    const { request, calls } = controllableRequest();
    const { result } = renderHook(() => useLatestRequest(request));

    act(() => result.current.run("old"));
    expect(calls[0]?.signal.aborted).toBe(false);
    act(() => result.current.run("new"));
    expect(calls[0]?.signal.aborted).toBe(true);
    expect(calls[1]?.signal.aborted).toBe(false);
  });

  it("ignores the failure of a superseded request", async () => {
    const { request, calls } = controllableRequest();
    const { result } = renderHook(() => useLatestRequest(request));

    act(() => result.current.run("old"));
    act(() => result.current.run("new"));
    await act(async () => calls[0]?.answer.reject(new ApiError("server", "old request failed")));
    expect(result.current.state.status).toBe("loading");

    await act(async () => calls[1]?.answer.resolve("answer-new"));
    expect(result.current.state).toEqual({ status: "success", data: "answer-new", error: null });
  });

  it("reports the failure of the current request", async () => {
    const { request, calls } = controllableRequest();
    const { result } = renderHook(() => useLatestRequest(request));
    const failure = new ApiError("server", "boom");

    act(() => result.current.run("a"));
    await act(async () => calls[0]?.answer.reject(failure));
    expect(result.current.state).toEqual({ status: "error", data: null, error: failure });
  });

  it("returns to idle on reset and ignores the answer that was in flight", async () => {
    const { request, calls } = controllableRequest();
    const { result } = renderHook(() => useLatestRequest(request));

    act(() => result.current.run("a"));
    act(() => result.current.reset());
    expect(result.current.state.status).toBe("idle");
    expect(calls[0]?.signal.aborted).toBe(true);

    await act(async () => calls[0]?.answer.resolve("late"));
    expect(result.current.state.status).toBe("idle");
  });

  it("applies nothing after unmount", async () => {
    const { request, calls } = controllableRequest();
    const { result, unmount } = renderHook(() => useLatestRequest(request));

    act(() => result.current.run("a"));
    unmount();
    expect(calls[0]?.signal.aborted).toBe(true);
    await act(async () => calls[0]?.answer.resolve("late"));
    expect(result.current.state.status).toBe("loading");
  });
});
