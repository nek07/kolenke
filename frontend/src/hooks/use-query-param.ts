"use client";

import { usePathname, useSearchParams } from "next/navigation";
import { useCallback } from "react";

/** A filter kept in the URL (?status=applied), so reload and «back» keep it. Updates without a server round trip. */
export function useQueryParam<T extends string>(name: string, fallback: T): [T, (value: T) => void] {
  const params = useSearchParams();
  const pathname = usePathname();
  const value = (params.get(name) as T | null) ?? fallback;
  const set = useCallback(
    (next: T) => {
      const p = new URLSearchParams(params.toString());
      if (next === fallback) p.delete(name);
      else p.set(name, next);
      const query = p.toString();
      window.history.replaceState(null, "", query ? `${pathname}?${query}` : pathname);
    },
    [params, pathname, name, fallback],
  );
  return [value, set];
}
