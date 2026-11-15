"use client";

import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from "react";

type Announce = (message: string) => void;

const AnnouncerContext = createContext<Announce>(() => {});

/**
 * One polite live region for the whole app.
 *
 * Async changes that a sighted user sees at a glance — a stage change, a step
 * that completed, a result that arrived — are announced here so a screen
 * reader user hears them without hunting for what changed. Messages are
 * polite: they wait for the current speech to finish and never steal focus.
 */
export function AnnouncerProvider({ children }: { children: ReactNode }) {
  const [message, setMessage] = useState("");
  const toggle = useRef(false);

  const announce = useCallback<Announce>((next) => {
    // The same sentence twice in a row must still be announced: alternate an
    // invisible suffix so the text node always changes.
    toggle.current = !toggle.current;
    setMessage(toggle.current ? next : `${next} `);
  }, []);

  const value = useMemo(() => announce, [announce]);

  return (
    <AnnouncerContext.Provider value={value}>
      {children}
      <div role="status" aria-live="polite" aria-atomic="true" className="sr-only" data-testid="announcer">
        {message}
      </div>
    </AnnouncerContext.Provider>
  );
}

export function useAnnounce(): Announce {
  return useContext(AnnouncerContext);
}
