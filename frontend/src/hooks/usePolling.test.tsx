import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";
import { usePolling, type PollingOptions } from "./usePolling";

interface Job {
  status: "RUNNING" | "SUCCEEDED" | "FAILED";
  steps: number;
}

const INTERVAL = 1_000;
const DEADLINE = 10_000;

function setup(fetcher: (signal: AbortSignal) => Promise<Job>, overrides: Partial<PollingOptions<Job>> = {}) {
  const onValue = vi.fn();
  const view = renderHook(
    (props: { pollKey: string | null }) =>
      usePolling<Job>({
        pollKey: props.pollKey,
        fetcher,
        isTerminal: (job) => job.status !== "RUNNING",
        onValue,
        intervalMs: INTERVAL,
        deadlineMs: DEADLINE,
        ...overrides,
      }),
    { initialProps: { pollKey: "job-1" as string | null } },
  );
  return { ...view, onValue };
}

/** Lets pending promise callbacks run without moving the clock. */
const flush = () => act(async () => vi.advanceTimersByTimeAsync(0));
const advance = (ms: number) => act(async () => vi.advanceTimersByTimeAsync(ms));

describe("usePolling", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("is idle when there is nothing to poll", () => {
    const fetcher = vi.fn();
    const { result } = renderHook(() =>
      usePolling<Job>({ pollKey: null, fetcher, isTerminal: () => true, onValue: () => {}, intervalMs: INTERVAL, deadlineMs: DEADLINE }),
    );
    expect(result.current.phase).toBe("idle");
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("polls at the interval until a terminal value arrives, then stops", async () => {
    const answers: Job[] = [
      { status: "RUNNING", steps: 1 },
      { status: "RUNNING", steps: 2 },
      { status: "SUCCEEDED", steps: 3 },
    ];
    const fetcher = vi.fn(async () => answers.shift() as Job);
    const { result, onValue } = setup(fetcher);

    await flush();
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(result.current.phase).toBe("polling");

    await advance(INTERVAL);
    expect(fetcher).toHaveBeenCalledTimes(2);
    await advance(INTERVAL);
    expect(fetcher).toHaveBeenCalledTimes(3);
    expect(result.current.phase).toBe("settled");
    expect(onValue.mock.calls.map(([job]) => job.steps)).toEqual([1, 2, 3]);

    await advance(INTERVAL * 5);
    expect(fetcher).toHaveBeenCalledTimes(3);
  });

  it("treats a FAILED job as a terminal value, not as a polling error", async () => {
    const fetcher = vi.fn(async (): Promise<Job> => ({ status: "FAILED", steps: 2 }));
    const { result, onValue } = setup(fetcher);

    await flush();
    expect(result.current.phase).toBe("settled");
    expect(onValue).toHaveBeenCalledWith({ status: "FAILED", steps: 2 });
  });

  it("stops with a visible timed-out phase when the deadline passes", async () => {
    const fetcher = vi.fn(async (): Promise<Job> => ({ status: "RUNNING", steps: 1 }));
    const { result } = setup(fetcher);

    await advance(DEADLINE - 1);
    expect(result.current.phase).toBe("polling");
    await advance(1);
    expect(result.current.phase).toBe("timed_out");

    const callsAtDeadline = fetcher.mock.calls.length;
    await advance(INTERVAL * 5);
    expect(fetcher).toHaveBeenCalledTimes(callsAtDeadline);
  });

  it("aborts a request that is still in flight at the deadline", async () => {
    let seen: AbortSignal | undefined;
    const fetcher = vi.fn((signal: AbortSignal) => {
      seen = signal;
      return new Promise<Job>(() => {}); // never answers
    });
    const { result } = setup(fetcher);

    await advance(DEADLINE);
    expect(result.current.phase).toBe("timed_out");
    expect(seen?.aborted).toBe(true);
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it("never runs two requests at once", async () => {
    let inFlight = 0;
    let maxInFlight = 0;
    const fetcher = vi.fn(async (): Promise<Job> => {
      inFlight += 1;
      maxInFlight = Math.max(maxInFlight, inFlight);
      await new Promise((resolve) => setTimeout(resolve, INTERVAL * 3)); // slower than the interval
      inFlight -= 1;
      return { status: "RUNNING", steps: 1 };
    });
    setup(fetcher);

    await advance(DEADLINE - 1);
    expect(maxInFlight).toBe(1);
  });

  it("retries a transient error and recovers", async () => {
    const fetcher = vi
      .fn<(signal: AbortSignal) => Promise<Job>>()
      .mockRejectedValueOnce(new ApiError("network", "offline"))
      .mockResolvedValueOnce({ status: "SUCCEEDED", steps: 3 });
    const { result } = setup(fetcher);

    await flush();
    expect(result.current.phase).toBe("polling");
    await advance(INTERVAL);
    expect(result.current.phase).toBe("settled");
  });

  it("fails visibly after three consecutive errors", async () => {
    const failure = new ApiError("network", "offline");
    const fetcher = vi.fn<(signal: AbortSignal) => Promise<Job>>().mockRejectedValue(failure);
    const { result } = setup(fetcher);

    await flush();
    await advance(INTERVAL);
    expect(result.current.phase).toBe("polling");
    await advance(INTERVAL);
    expect(result.current.phase).toBe("failed");
    expect(result.current.error).toBe(failure);
    expect(fetcher).toHaveBeenCalledTimes(3);

    await advance(INTERVAL * 5);
    expect(fetcher).toHaveBeenCalledTimes(3);
  });

  it("does not retry an error that another attempt cannot fix", async () => {
    const failure = new ApiError("unauthorized", "access code rejected", { status: 401 });
    const fetcher = vi.fn<(signal: AbortSignal) => Promise<Job>>().mockRejectedValue(failure);
    const { result } = setup(fetcher);

    await flush();
    expect(result.current.phase).toBe("failed");
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it("starts a fresh poll with a fresh deadline when the key changes", async () => {
    const fetcher = vi.fn(async (): Promise<Job> => ({ status: "RUNNING", steps: 1 }));
    const { result, rerender } = setup(fetcher);

    await advance(DEADLINE);
    expect(result.current.phase).toBe("timed_out");

    rerender({ pollKey: "job-1:retry" });
    expect(result.current.phase).toBe("polling");
    await advance(DEADLINE - 1);
    expect(result.current.phase).toBe("polling");
    await advance(1);
    expect(result.current.phase).toBe("timed_out");
  });

  it("stops and ignores late answers when unmounted", async () => {
    const fetcher = vi.fn(async (): Promise<Job> => ({ status: "RUNNING", steps: 1 }));
    const { unmount, onValue } = setup(fetcher);

    await flush();
    const callsBefore = fetcher.mock.calls.length;
    const valuesBefore = onValue.mock.calls.length;
    unmount();
    await advance(INTERVAL * 5);
    expect(fetcher).toHaveBeenCalledTimes(callsBefore);
    expect(onValue).toHaveBeenCalledTimes(valuesBefore);
  });
});
