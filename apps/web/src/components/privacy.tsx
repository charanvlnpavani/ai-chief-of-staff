"use client";

import { useSyncExternalStore } from "react";

/*
 * Privacy mode masks personal numbers with one switch (handy when screen-sharing or recording).
 * It is a per-device preference kept in localStorage, read through useSyncExternalStore so the
 * server render (always "visible") and the browser stay consistent and tabs stay in sync.
 */

const STORAGE_KEY = "pos.privacy-mode";
const listeners = new Set<() => void>();
let memoryFallback = false; // used when storage is unavailable (private windows)

function readHidden(): boolean {
  try {
    return window.localStorage.getItem(STORAGE_KEY) === "1";
  } catch {
    return memoryFallback;
  }
}

function subscribe(onChange: () => void): () => void {
  listeners.add(onChange);
  window.addEventListener("storage", onChange);
  return () => {
    listeners.delete(onChange);
    window.removeEventListener("storage", onChange);
  };
}

function writeHidden(hidden: boolean): void {
  memoryFallback = hidden;
  try {
    window.localStorage.setItem(STORAGE_KEY, hidden ? "1" : "0");
  } catch {
    // storage unavailable; the in-memory value still applies to this tab
  }
  for (const listener of listeners) listener();
}

export interface PrivacyState {
  hidden: boolean;
  toggle: () => void;
  setHidden: (hidden: boolean) => void;
}

export function usePrivacy(): PrivacyState {
  const hidden = useSyncExternalStore(subscribe, readHidden, () => false);
  return { hidden, setHidden: writeHidden, toggle: () => writeHidden(!hidden) };
}

/** Kept for API stability: privacy state lives in an external store, so no context is needed. */
export function PrivacyProvider({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}

/** Renders its children, or a mask when privacy mode is on. */
export function Private({ children }: { children: React.ReactNode }) {
  const { hidden } = usePrivacy();
  if (!hidden) return <>{children}</>;
  return (
    <span aria-label="Hidden by privacy mode" className="select-none tracking-widest text-muted-foreground">
      •••
    </span>
  );
}
