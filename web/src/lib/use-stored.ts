"use client";

/** Хук значения из localStorage без setState-в-эффекте: useSyncExternalStore + событие изменения. */

import { useSyncExternalStore } from "react";

export function useStored(key: string, event: string, fallback: string): [string, (v: string) => void] {
  const value = useSyncExternalStore(
    (cb) => {
      window.addEventListener(event, cb);
      return () => window.removeEventListener(event, cb);
    },
    () => localStorage.getItem(key) ?? fallback,
    () => fallback,
  );
  const set = (v: string) => {
    localStorage.setItem(key, v);
    window.dispatchEvent(new Event(event));
  };
  return [value, set];
}
