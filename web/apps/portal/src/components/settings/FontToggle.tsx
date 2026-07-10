"use client";
import { useFontFamilyStore } from "@/lib/stores/font-family-store";
import { Button } from "@/components/ui/button";

export function FontToggle() {
  const font = useFontFamilyStore((s) => s.font);
  const setFont = useFontFamilyStore((s) => s.setFont);
  return (
    <div className="flex gap-1">
      <Button size="sm" aria-pressed={font === "plex"} variant={font === "plex" ? "default" : "outline"} onClick={() => setFont("plex")}>IBM Plex</Button>
      <Button size="sm" aria-pressed={font === "inter"} variant={font === "inter" ? "default" : "outline"} onClick={() => setFont("inter")}>Inter</Button>
    </div>
  );
}
