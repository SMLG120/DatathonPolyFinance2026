/**
 * The demo access code (LEAD_DECISIONS D8).
 *
 * It is typed by the user at runtime and kept in `sessionStorage` only: it is
 * gone when the tab closes, it is never written to `localStorage`, never put
 * in a URL, never logged and never part of the bundle. It is demo-grade access
 * control, not a user identity.
 */

const STORAGE_KEY = "byb.accessCode";

type Listener = () => void;
const listeners = new Set<Listener>();

function storage(): Storage | null {
  try {
    return typeof window === "undefined" ? null : window.sessionStorage;
  } catch {
    // Storage can be blocked (private mode, strict settings). The code then
    // lives only in memory for this page.
    return null;
  }
}

let memoryFallback: string | null = null;

export function readAccessCode(): string | null {
  const store = storage();
  if (!store) return memoryFallback;
  try {
    return store.getItem(STORAGE_KEY);
  } catch {
    return memoryFallback;
  }
}

export function storeAccessCode(code: string): void {
  const trimmed = code.trim();
  memoryFallback = trimmed;
  try {
    storage()?.setItem(STORAGE_KEY, trimmed);
  } catch {
    // Kept in memory only.
  }
  listeners.forEach((listener) => listener());
}

export function clearAccessCode(): void {
  memoryFallback = null;
  try {
    storage()?.removeItem(STORAGE_KEY);
  } catch {
    // Nothing to remove.
  }
  listeners.forEach((listener) => listener());
}

export function subscribeAccessCode(listener: Listener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}
