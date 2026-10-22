"use client";

/** Хук медиа-запроса: useSyncExternalStore + слушатель matchMedia,
 *  реагирует на resize/поворот экрана, на сервере возвращает false. */

import { useSyncExternalStore } from "react";

export function useMediaQuery(query: string): boolean {
  const subscribe = (cb: () => void) => {
    const mql = window.matchMedia(query);
    mql.addEventListener("change", cb);
    return () => mql.removeEventListener("change", cb);
  };
  return useSyncExternalStore(
    subscribe,
    () => window.matchMedia(query).matches,
    () => false,
  );
}
