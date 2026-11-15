"use client";

import { useEffect, useRef, useState } from "react";
import { isAbortError, isApiError } from "@/lib/api/errors";

export type PollingPhase =
  /** Nothing to poll. */
  | "idle"
  | "polling"
  /** A terminal value arrived. */
  | "settled"
  /** The deadline passed before a terminal value arrived. */
  | "timed_out"
  /** Polling gave up after repeated or unrecoverable errors. */
  | "failed";

export interface PollingOptions<T> {
  /** Polling runs while this is non-null. A different key starts a fresh poll with a fresh deadline. */
  pollKey: string | null;
  fetcher: (signal: AbortSignal) => Promise<T>;
  isTerminal: (value: T) => boolean;
  /** Called with every value received, terminal or not. */
  onValue: (value: T) => void;
  intervalMs: number;
  deadlineMs: number;
  /** Consecutive failed polls tolerated before giving up. Default 3. */
  maxConsecutiveErrors?: number;
}

export interface PollingState {
  phase: PollingPhase;
  error: unknown;
  /** Completed polls so far. */
  attempts: number;
}

interface KeyedState extends PollingState {
  pollKey: string | null;
}

/** Errors that another attempt cannot fix. */
function isUnrecoverable(error: unknown): boolean {
  return isApiError(error) && (error.kind === "unauthorized" || error.kind === "not_found" || error.kind === "validation");
}

/**
 * Polls until a terminal value, with a hard deadline and a visible failure
 * state (BUILD_BRIEF §7).
 *
 * - One request at a time: the next poll is scheduled only after the previous
 *   one has answered.
 * - The deadline is absolute from the start of the poll. When it passes, the
 *   request in flight is aborted and the phase becomes "timed_out".
 * - Transient errors are retried; `maxConsecutiveErrors` in a row, or an error
 *   a retry cannot fix, end the poll in "failed".
 * - Changing `pollKey` or unmounting cancels everything; late answers are ignored.
 */
export function usePolling<T>(options: PollingOptions<T>): PollingState {
  const { pollKey, intervalMs, deadlineMs } = options;
  const maxConsecutiveErrors = options.maxConsecutiveErrors ?? 3;
  const [state, setState] = useState<KeyedState>({ pollKey: null, phase: "idle", error: null, attempts: 0 });

  const callbacks = useRef({ fetcher: options.fetcher, isTerminal: options.isTerminal, onValue: options.onValue });
  useEffect(() => {
    callbacks.current = { fetcher: options.fetcher, isTerminal: options.isTerminal, onValue: options.onValue };
  });

  useEffect(() => {
    if (pollKey === null) return;

    let finished = false;
    let attempts = 0;
    let consecutiveErrors = 0;
    let nextPoll: ReturnType<typeof setTimeout> | null = null;
    const controller = new AbortController();

    const finish = (phase: PollingPhase, error: unknown = null) => {
      if (finished) return;
      finished = true;
      if (nextPoll !== null) clearTimeout(nextPoll);
      clearTimeout(deadline);
      controller.abort();
      setState({ pollKey, phase, error, attempts });
    };

    const deadline = setTimeout(() => finish("timed_out"), deadlineMs);

    const poll = async () => {
      if (finished) return;
      try {
        const value = await callbacks.current.fetcher(controller.signal);
        if (finished) return;
        attempts += 1;
        consecutiveErrors = 0;
        callbacks.current.onValue(value);
        if (callbacks.current.isTerminal(value)) {
          finish("settled");
          return;
        }
      } catch (error) {
        if (finished || isAbortError(error)) return;
        attempts += 1;
        consecutiveErrors += 1;
        if (isUnrecoverable(error) || consecutiveErrors >= maxConsecutiveErrors) {
          finish("failed", error);
          return;
        }
      }
      setState({ pollKey, phase: "polling", error: null, attempts });
      nextPoll = setTimeout(poll, intervalMs);
    };

    void poll();

    return () => {
      // Cancelled, not finished: no state is written for a poll that was replaced.
      finished = true;
      if (nextPoll !== null) clearTimeout(nextPoll);
      clearTimeout(deadline);
      controller.abort();
    };
  }, [pollKey, intervalMs, deadlineMs, maxConsecutiveErrors]);

  // The state of a previous key is never reported for the current one.
  if (pollKey === null) return { phase: "idle", error: null, attempts: 0 };
  if (state.pollKey !== pollKey) return { phase: "polling", error: null, attempts: 0 };
  return { phase: state.phase, error: state.error, attempts: state.attempts };
}
