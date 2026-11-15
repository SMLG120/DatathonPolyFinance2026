"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { isAbortError } from "@/lib/api/errors";

export type LatestState<T> =
  | { status: "idle"; data: null; error: null }
  | { status: "loading"; data: null; error: null }
  | { status: "success"; data: T; error: null }
  | { status: "error"; data: null; error: unknown };

export interface LatestRequest<TArgs extends unknown[], T> {
  state: LatestState<T>;
  /** Starts a request. Any request still in flight is cancelled and its answer discarded. */
  run: (...args: TArgs) => void;
  /** Cancels the request in flight, if any, and returns to idle. */
  reset: () => void;
}

const IDLE = { status: "idle", data: null, error: null } as const;

/**
 * The stale-response guard.
 *
 * Only the answer to the MOST RECENT `run` can ever reach the state. Two
 * independent mechanisms enforce it:
 *
 *   1. a sequence number — an answer is applied only if no newer request has
 *      started since, whatever order the network delivers answers in;
 *   2. an AbortController — the superseded request is also cancelled so it
 *      stops using the connection.
 *
 * The sequence number is the guarantee; aborting is housekeeping. A request
 * that ignores its signal and answers late is still discarded.
 */
export function useLatestRequest<TArgs extends unknown[], T>(
  request: (signal: AbortSignal, ...args: TArgs) => Promise<T>,
): LatestRequest<TArgs, T> {
  const [state, setState] = useState<LatestState<T>>(IDLE);
  const sequence = useRef(0);
  const controller = useRef<AbortController | null>(null);
  const latestRequest = useRef(request);

  useEffect(() => {
    latestRequest.current = request;
  }, [request]);

  useEffect(
    () => () => {
      // Unmount: nothing may be applied afterwards.
      sequence.current += 1;
      controller.current?.abort();
    },
    [],
  );

  const run = useCallback((...args: TArgs) => {
    controller.current?.abort();
    const current = new AbortController();
    controller.current = current;
    sequence.current += 1;
    const id = sequence.current;
    setState({ status: "loading", data: null, error: null });

    latestRequest.current(current.signal, ...args).then(
      (data) => {
        if (sequence.current !== id) return;
        setState({ status: "success", data, error: null });
      },
      (error: unknown) => {
        if (sequence.current !== id || isAbortError(error)) return;
        setState({ status: "error", data: null, error });
      },
    );
  }, []);

  const reset = useCallback(() => {
    sequence.current += 1;
    controller.current?.abort();
    controller.current = null;
    setState(IDLE);
  }, []);

  return { state, run, reset };
}
