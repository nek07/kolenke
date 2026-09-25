import { useSyncExternalStore } from "react";

const noop = () => () => {};

/** False on the server and during hydration, true after it: for content that depends on browser-only data. */
export function useHydrated() {
  return useSyncExternalStore(
    noop,
    () => true,
    () => false,
  );
}
