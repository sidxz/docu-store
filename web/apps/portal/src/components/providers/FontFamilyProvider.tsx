"use client";
import { useEffect, type ReactNode } from "react";
import { useFontFamilyStore } from "@/lib/stores/font-family-store";

export function FontFamilyProvider({ children }: { children: ReactNode }) {
  const font = useFontFamilyStore((s) => s.font);
  useEffect(() => {
    document.documentElement.setAttribute("data-font", font);
  }, [font]);
  return <>{children}</>;
}
