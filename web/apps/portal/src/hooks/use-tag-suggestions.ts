"use client";

import { useEffect, useRef, useState } from "react";

import { authFetchJson } from "@/lib/auth-fetch";

export interface TagSuggestion {
  tag: string;
  entity_type: string;
}

/**
 * Debounced server-side tag suggestions from /browse/tags/suggest.
 * 200ms debounce, limit=10, errors swallowed to an empty list.
 * Shared by TagFilter and EditMetadataDialog's tag chips input.
 */
export function useTagSuggestions(query: string): TagSuggestion[] {
  const [suggestions, setSuggestions] = useState<TagSuggestion[]>([]);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    const q = query.trim();
    if (debounceRef.current) clearTimeout(debounceRef.current);

    if (q.length < 1) {
      setSuggestions([]);
      return;
    }

    debounceRef.current = setTimeout(async () => {
      try {
        const results = await authFetchJson<TagSuggestion[]>(
          `/browse/tags/suggest?q=${encodeURIComponent(q)}&limit=10`,
        );
        setSuggestions(results);
      } catch {
        setSuggestions([]);
      }
    }, 200);

    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [query]);

  return suggestions;
}
