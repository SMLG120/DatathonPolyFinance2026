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
  /** Polling stopped on an error that another attempt cannot fix. */
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
}

export interface PollingState {
  phase: PollingPhase;
  /**
   * "failed": the error that ended the poll. "polling" and "timed_out": the
   * error of the latest poll if it failed (it is being retried, or was when
   * the deadline passed), null if it answered.
   */
  error: unknown;
  /** Completed polls so far. */
  attempts: number;
}

interface KeyedState extends PollingState {
  pollKey: string | null;
}

/**
 * Errors that another attempt cannot fix. contracts/api.md section 7, polling
 * rule 4: a network error, a 429 or a 5xx is retried at the same interval
 * until the client deadline (a request that got no answer in time counts as a
 * network error). Everything else ends the poll: 401 and 403 (the access code
 * is asked for again), 404 and 410, a request the service rejects, and an
 * answer this page cannot read.
 */
export function isUnrecoverable(error: unknown): boolean {
  if (!isApiError(error)) return true;
  return !(error.kind === "network" || error.kind === "timeout" || error.kind === "rate_limited" || error.kind === "server");
}

/**
 * Polls until a terminal value, with a hard deadline and a visible failure
 * state (BUILD_BRIEF §7).
 *
 * - One request at a time: the next poll is scheduled only after the previous
 *   one has answered.
 * - The deadline is absolute from the start of the poll. When it passes, the
 *   request in flight is aborted and the phase becomes "timed_out".
 * - A transient error (network, 429, 5xx) is retried at the same interval for
 *   as long as the deadline allows, however many there are in a row: the job
 *   runs on the server whether or not its status can be fetched. Only an
 *   error a retry cannot fix ends the poll in "failed".
 * - Changing `pollKey` or unmounting cancels everything; late answers are ignored.
 */
export function usePolling<T>(options: PollingOptions<T>): PollingState {
  const { pollKey, intervalMs, deadlineMs } = options;
  const [state, setState] = useState<KeyedState>({ pollKey: null, phase: "idle", error: null, attempts: 0 });

  const callbacks = useRef({ fetcher: options.fetcher, isTerminal: options.isTerminal, onValue: options.onValue });
  useEffect(() => {
    callbacks.current = { fetcher: options.fetcher, isTerminal: options.isTerminal, onValue: options.onValue };
  });

  useEffect(() => {
    if (pollKey === null) return;

    let finished = false;
    let attempts = 0;
    /** The error of the latest poll, while it is being retried. */
    let lastError: unknown = null;
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

    const deadline = setTimeout(() => finish("timed_out", lastError), deadlineMs);

    const poll = async () => {
      if (finished) return;
      try {
        const value = await callbacks.current.fetcher(controller.signal);
        if (finished) return;
        attempts += 1;
        lastError = null;
        callbacks.current.onValue(value);
        if (callbacks.current.isTerminal(value)) {
          finish("settled");
          return;
        }
      } catch (error) {
        if (finished || isAbortError(error)) return;
        attempts += 1;
        if (isUnrecoverable(error)) {
          finish("failed", error);
          return;
        }
        lastError = error;
      }
      setState({ pollKey, phase: "polling", error: lastError, attempts });
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
  }, [pollKey, intervalMs, deadlineMs]);

  // The state of a previous key is never reported for the current one.
  if (pollKey === null) return { phase: "idle", error: null, attempts: 0 };
  if (state.pollKey !== pollKey) return { phase: "polling", error: null, attempts: 0 };
  return { phase: state.phase, error: state.error, attempts: state.attempts };
}
