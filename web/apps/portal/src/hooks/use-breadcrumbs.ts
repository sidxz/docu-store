"use client";

import { usePathname } from "next/navigation";

interface Breadcrumb {
  label: string;
  href: string;
}

// Human-readable label overrides for known route segments.
// Segments not in this map are auto-formatted by formatSegment().
const LABEL_MAP: Record<string, string> = {
  documents: "Documents",
  search: "Search",
  compounds: "Compounds",
  chat: "Chat",
  settings: "Settings",
  upload: "Upload",
  pages: "Pages",
};

export function useBreadcrumbs(): Breadcrumb[] {
  const pathname = usePathname();
  const segments = pathname.split("/").filter(Boolean);

  if (segments.length <= 1) {
    return [{ label: "Dashboard", href: `/${segments[0] || "default"}` }];
  }

  // segments[0] is the workspace slug ([workspace] dynamic segment).
  // We intentionally skip it — the sidebar already shows the workspace name.
  const workspace = segments[0];
  const crumbs: Breadcrumb[] = [];

  for (let i = 1; i < segments.length; i++) {
    const segment = segments[i];
    const href = `/${segments.slice(0, i + 1).join("/")}`;
    const label = LABEL_MAP[segment] || formatSegment(segment);
    crumbs.push({ label, href });
  }

  return crumbs;
}

function formatSegment(segment: string): string {
  // UUID-like segments get truncated
  if (segment.length > 20) {
    return segment.slice(0, 8) + "...";
  }
  return segment.charAt(0).toUpperCase() + segment.slice(1);
}
