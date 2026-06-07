import { useEffect, useRef } from "react";

const STALE_MS = 10 * 60 * 1000; // 10 Minuten

/**
 * Ruft `loadFn` auf wenn der Browser-Tab wieder sichtbar wird
 * und die letzte Ladung älter als 10 Minuten ist.
 */
export function useVisibilityRefresh(loadFn) {
  const lastLoadTime = useRef(Date.now());

  // Aufgerufen wenn loadFn ausgeführt wird – Zeit merken
  const wrappedLoad = () => {
    lastLoadTime.current = Date.now();
    return loadFn();
  };

  useEffect(() => {
    if (typeof document === "undefined") return;
    const onVisibilityChange = () => {
      if (document.visibilityState === "visible") {
        const stale = Date.now() - lastLoadTime.current > STALE_MS;
        if (stale) loadFn();
      }
    };
    document.addEventListener("visibilitychange", onVisibilityChange);
    return () => document.removeEventListener("visibilitychange", onVisibilityChange);
  }, [loadFn]);

  return wrappedLoad;
}
