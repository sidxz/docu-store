"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Filter, Plus, Tag, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Command,
  CommandEmpty,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { authFetchJson } from "@/lib/auth-fetch";

interface TagSuggestion {
  tag: string;
  entity_type: string;
}

interface TagFilterProps {
  tags: string[];
  matchMode: "any" | "all";
  onTagsChange: (tags: string[]) => void;
  onMatchModeChange: (mode: "any" | "all") => void;
}

const ENTITY_TYPE_LABELS: Record<string, string> = {
  target: "Target",
  compound_name: "Compound",
  gene_name: "Gene",
  disease: "Disease",
  assay: "Assay",
  author: "Author",
  bioactivity: "Bioactivity",
  mechanism_of_action: "MoA",
  accession_number: "Accession",
  screening_method: "Screen",
  protein_name: "Protein",
};

export function TagFilter({
  tags,
  matchMode,
  onTagsChange,
  onMatchModeChange,
}: TagFilterProps) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [suggestions, setSuggestions] = useState<TagSuggestion[]>([]);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const addTag = useCallback(
    (raw: string) => {
      const tag = raw.trim();
      if (!tag || tags.some((t) => t.toLowerCase() === tag.toLowerCase()))
        return;
      onTagsChange([...tags, tag]);
    },
    [tags, onTagsChange],
  );

  const removeTag = useCallback(
    (tag: string) => {
      onTagsChange(tags.filter((t) => t !== tag));
    },
    [tags, onTagsChange],
  );

  // Debounced server-side tag suggestions — same endpoint/contract as before.
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

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && query && suggestions.length === 0) {
      addTag(query);
      setQuery("");
    } else if (e.key === ",") {
      e.preventDefault();
      addTag(query);
      setQuery("");
    } else if (e.key === "Backspace" && !query && tags.length > 0) {
      onTagsChange(tags.slice(0, -1));
    }
  };

  return (
    <div className="rounded-lg border border-border-default bg-surface-raised p-3">
      <div className="mb-2 flex items-center gap-2">
        <Filter className="h-3.5 w-3.5 text-text-muted" />
        <span className="text-xs font-medium text-text-secondary">
          Tag Filters
        </span>
        {tags.length > 1 && (
          <ToggleGroup
            type="single"
            variant="outline"
            size="sm"
            value={matchMode}
            onValueChange={(nv) => nv && onMatchModeChange(nv as "any" | "all")}
            className="ml-auto"
          >
            <ToggleGroupItem value="any" className="h-6 px-2 text-xs">
              Any
            </ToggleGroupItem>
            <ToggleGroupItem value="all" className="h-6 px-2 text-xs">
              All
            </ToggleGroupItem>
          </ToggleGroup>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-1.5">
        {tags.map((tag) => (
          <Badge
            key={tag}
            variant="secondary"
            className="gap-1 bg-accent-subtle text-accent-text"
          >
            <Tag className="size-3" />
            {tag}
            <button
              type="button"
              onClick={() => removeTag(tag)}
              aria-label={`Remove ${tag}`}
              className="rounded-full hover:opacity-70"
            >
              <X className="size-3" />
            </button>
          </Badge>
        ))}

        <Popover open={open} onOpenChange={setOpen}>
          <PopoverTrigger asChild>
            <Button variant="outline" size="sm" className="h-7 gap-1 text-xs">
              <Plus className="size-3.5" />
              Add tag
            </Button>
          </PopoverTrigger>
          <PopoverContent className="w-64 p-0" align="start">
            <Command shouldFilter={false}>
              <CommandInput
                placeholder="Type to search tags…"
                value={query}
                onValueChange={setQuery}
                onKeyDown={handleKeyDown}
              />
              <CommandList>
                <CommandEmpty>
                  {query.trim()
                    ? `Press Enter to add “${query}”`
                    : "Type to search tags…"}
                </CommandEmpty>
                {suggestions.map((s) => (
                  <CommandItem
                    key={s.tag}
                    value={s.tag}
                    onSelect={() => {
                      addTag(s.tag);
                      setQuery("");
                    }}
                  >
                    <span className="flex-1 truncate">{s.tag}</span>
                    <span className="rounded bg-surface-sunken px-1.5 py-0.5 text-[10px] font-medium text-text-muted">
                      {ENTITY_TYPE_LABELS[s.entity_type] ?? s.entity_type}
                    </span>
                  </CommandItem>
                ))}
              </CommandList>
            </Command>
          </PopoverContent>
        </Popover>
      </div>

      {tags.length > 0 && (
        <button
          type="button"
          onClick={() => onTagsChange([])}
          className="mt-1.5 text-xs text-text-muted hover:text-text-secondary"
        >
          Clear all
        </button>
      )}
    </div>
  );
}
