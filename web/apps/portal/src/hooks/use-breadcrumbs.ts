"use client";

import { usePathname } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@docu-store/api-client";
import { queryKeys } from "@/lib/query-keys";
import { throwApiError } from "@/lib/api-error";

interface Breadcrumb {
  label: string;
  href: string;
}

/** Human-readable label overrides for known route segments. */
const LABEL_MAP: Record<string, string> = {
  documents: "Documents",
  search: "Search",
  compounds: "Compounds",
  chat: "Chat",
  settings: "Settings",
  upload: "Upload",
};

/** Structural URL segments that aren't real pages — skip in breadcrumbs. */
const SKIP_SEGMENTS = new Set(["pages"]);

function isUuidLike(s: string): boolean {
  return s.length > 20 && /^[0-9a-f-]+$/i.test(s);
}

export function useBreadcrumbs(): Breadcrumb[] {
  const pathname = usePathname();
  const segments = pathname.split("/").filter(Boolean);

  // Extract entity IDs from known URL positions so we can resolve titles.
  // /[workspace]/documents/[artifactId]
  // /[workspace]/documents/[artifactId]/pages/[pageId]
  const docIdx = segments.indexOf("documents");
  const artifactId =
    docIdx >= 0 &&
    docIdx + 1 < segments.length &&
    isUuidLike(segments[docIdx + 1])
      ? segments[docIdx + 1]
      : null;

  const pagesIdx = segments.indexOf("pages");
  const pageId =
    pagesIdx >= 0 &&
    pagesIdx + 1 < segments.length &&
    isUuidLike(segments[pagesIdx + 1])
      ? segments[pagesIdx + 1]
      : null;

  // Fetch titles — shares TanStack Query cache with detail page components.
  const { data: artifact } = useQuery({
    queryKey: queryKeys.artifacts.detail(artifactId ?? ""),
    queryFn: async () => {
      const { data, error, response } = await apiClient.GET("/artifacts/{artifact_id}", {
        params: { path: { artifact_id: artifactId! } },
      });
      if (error) throwApiError("Failed to fetch artifact", error, response.status);
      return data;
    },
    enabled: !!artifactId,
    staleTime: 5 * 60_000,
  });

  const { data: page } = useQuery({
    queryKey: queryKeys.pages.detail(pageId ?? ""),
    queryFn: async () => {
      const { data, error, response } = await apiClient.GET("/pages/{page_id}", {
        params: { path: { page_id: pageId! } },
      });
      if (error) throwApiError("Failed to fetch page", error, response.status);
      return data;
    },
    enabled: !!pageId,
    staleTime: 5 * 60_000,
  });

  if (segments.length <= 1) {
    return [{ label: "Dashboard", href: `/${segments[0] || "default"}` }];
  }

  // segments[0] is the workspace slug — the sidebar already shows it.
  const crumbs: Breadcrumb[] = [];

  for (let i = 1; i < segments.length; i++) {
    const segment = segments[i];
    const prevSegment = i > 1 ? segments[i - 1] : null;
    const href = `/${segments.slice(0, i + 1).join("/")}`;

    // Skip structural-only segments (e.g. "pages" between artifact ID and page ID)
    if (SKIP_SEGMENTS.has(segment)) continue;

    if (LABEL_MAP[segment]) {
      crumbs.push({ label: LABEL_MAP[segment], href });
    } else if (isUuidLike(segment)) {
      crumbs.push({ label: resolveLabel(segment, prevSegment), href });
    } else {
      crumbs.push({ label: formatSegment(segment), href });
    }
  }

  return crumbs;

  // --- helpers scoped to this render (close over query data) ---

  function resolveLabel(segment: string, prevSegment: string | null): string {
    if (prevSegment === "documents" && segment === artifactId) {
      const a = artifact as Record<string, unknown> | undefined;
      const title =
        (a?.title_mention as { title?: string } | undefined)?.title ??
        (a?.source_filename as string | undefined);
      return title || "\u2026"; // "…" while loading
    }

    if (prevSegment === "pages" && segment === pageId) {
      const p = page as Record<string, unknown> | undefined;
      if (p?.name) return p.name as string;
      if (p?.index != null) return `Page ${(p.index as number) + 1}`;
      return "\u2026";
    }

    // Fallback for unrecognised UUIDs
    return segment.slice(0, 8) + "\u2026";
  }
}

function formatSegment(segment: string): string {
  return segment.charAt(0).toUpperCase() + segment.slice(1);
}
