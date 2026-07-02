"use client";

import { useEffect, type ReactNode } from "react";

import { useFontScaleStore } from "@/lib/stores/font-scale-store";

/** Applies the persisted font scale as the root font-size (percent of the
 *  browser default). Every rem-based utility scales off this. */
export function FontScaleProvider({ children }: { children: ReactNode }) {
  const scale = useFontScaleStore((s) => s.scale);

  useEffect(() => {
    document.documentElement.style.fontSize = `${scale}%`;
  }, [scale]);

  return <>{children}</>;
}
