"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { isAbortError } from "@/lib/api/errors";

export type PreviewStatus = "idle" | "waiting" | "loading" | "ready" | "error";

export interface PreviewState<TInput, TResult> {
  status: PreviewStatus;
  /** The draft this state belongs to. */
  input: TInput | null;
  /** Non-null only when `status` is "ready", and then it is the answer for `input`. */
  result: TResult | null;
  error: unknown;
}

export interface DebouncedPreview<TInput, TResult> extends PreviewState<TInput, TResult> {
  /** Call on every change of the draft. Earlier drafts are dropped. */
  schedule: (input: TInput) => void;
  /** Drops the draft, the pending call and any preview on screen. */
  clear: () => void;
}

const IDLE = { status: "idle", input: null, result: null, error: null } as const;

/**
 * Debounced preview of a DRAFT value (BUILD_BRIEF §7).
 *
 * - Changes are debounced: only the draft that is still current after
 *   `delayMs` is sent.
 * - Stale answers never replace newer ones: a sequence number decides which
 *   answer may be applied, and the superseded request is aborted as well.
 * - A preview on screen always belongs to the draft on screen: as soon as the
 *   draft changes the old preview is removed, not left next to a new number.
 *
 * The hook owns its result. It has no access to the confirmed policy or the
 * confirmed result, so a preview cannot overwrite either of them.
 */
export function useDebouncedPreview<TInput, TResult>(
  request: (input: TInput, signal: AbortSignal) => Promise<TResult>,
  delayMs: number,
): DebouncedPreview<TInput, TResult> {
  const [state, setState] = useState<PreviewState<TInput, TResult>>(IDLE);
  const sequence = useRef(0);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const controller = useRef<AbortController | null>(null);
  const latestRequest = useRef(request);

  useEffect(() => {
    latestRequest.current = request;
  }, [request]);

  const cancelPending = useCallback(() => {
    sequence.current += 1;
    if (timer.current !== null) clearTimeout(timer.current);
    timer.current = null;
    controller.current?.abort();
    controller.current = null;
  }, []);

  useEffect(() => cancelPending, [cancelPending]);

  const schedule = useCallback(
    (input: TInput) => {
      cancelPending();
      const id = sequence.current;
      setState({ status: "waiting", input, result: null, error: null });

      timer.current = setTimeout(() => {
        timer.current = null;
        if (sequence.current !== id) return;
        const current = new AbortController();
        controller.current = current;
        setState({ status: "loading", input, result: null, error: null });

        latestRequest.current(input, current.signal).then(
          (result) => {
            if (sequence.current !== id) return;
            setState({ status: "ready", input, result, error: null });
          },
          (error: unknown) => {
            if (sequence.current !== id || isAbortError(error)) return;
            setState({ status: "error", input, result: null, error });
          },
        );
      }, delayMs);
    },
    [cancelPending, delayMs],
  );

  const clear = useCallback(() => {
    cancelPending();
    setState(IDLE);
  }, [cancelPending]);

  return { ...state, schedule, clear };
}
