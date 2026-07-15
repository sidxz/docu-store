"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Loader2, Plus, X } from "lucide-react";

import type { ArtifactResponse } from "@docu-store/types";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Command,
  CommandEmpty,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { getErrorMessage } from "@/lib/api-error";
import { useTagSuggestions } from "@/hooks/use-tag-suggestions";
import {
  useCorrectArtifactMetadata,
  type CorrectArtifactMetadataBody,
} from "@/hooks/use-artifacts";

interface EditMetadataDialogProps {
  artifact: ArtifactResponse;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

interface TagChip {
  tag: string;
  entity_type: string | null;
}

/** `PresentationDate.date` comes back as an ISO datetime; <input type="date"> wants just the date part. */
function toDateInputValue(iso: string | null | undefined): string {
  return iso ? iso.slice(0, 10) : "";
}

// ── Tags: chips + autocomplete against /browse/tags/suggest (same idiom as TagFilter) ──

function TagChipsField({
  tags,
  onChange,
  inputId,
}: {
  tags: TagChip[];
  onChange: (tags: TagChip[]) => void;
  inputId?: string;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const suggestions = useTagSuggestions(query);

  // The same tag text can legitimately appear twice with different entity_type
  // (e.g. "Rho" as both a target and a gene_name — the backend merges on the
  // (entity_type, tag) pair), so identity here must include entity_type too.
  const addTag = (raw: string, entityType: string | null = null) => {
    const tag = raw.trim();
    if (
      !tag ||
      tags.some(
        (t) => t.entity_type === entityType && t.tag.toLowerCase() === tag.toLowerCase(),
      )
    )
      return;
    // Typed additions carry the suggestion's entity_type; hand-typed chips stay
    // unclassified (precision over guessing) — re-extraction can tag them later.
    onChange([...tags, { tag, entity_type: entityType }]);
  };

  const removeTag = (chip: TagChip) => {
    onChange(tags.filter((t) => t.tag !== chip.tag || t.entity_type !== chip.entity_type));
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && query && suggestions.length === 0) {
      addTag(query);
      setQuery("");
    } else if (e.key === ",") {
      e.preventDefault();
      addTag(query);
      setQuery("");
    } else if (e.key === "Backspace" && !query && tags.length > 0) {
      onChange(tags.slice(0, -1));
    }
  };

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {tags.map((t) => (
        <Badge
          key={`${t.entity_type ?? ""}:${t.tag}`}
          variant="secondary"
          className="bg-accent-subtle text-accent-text"
        >
          {t.tag}
          {t.entity_type && (
            <span className="text-[10px] font-normal text-muted-foreground">
              {t.entity_type}
            </span>
          )}
          <button
            type="button"
            onClick={() => removeTag(t)}
            aria-label={`Remove ${t.tag}`}
            className="rounded-full hover:opacity-70"
          >
            <X className="size-3" />
          </button>
        </Badge>
      ))}

      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button type="button" variant="outline" size="sm" className="h-7 gap-1 text-xs">
            <Plus className="size-3.5" />
            Add tag
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-64 p-0" align="start">
          <Command shouldFilter={false}>
            <CommandInput
              id={inputId}
              placeholder="Type to search tags…"
              value={query}
              onValueChange={setQuery}
              onKeyDown={handleKeyDown}
            />
            <CommandList>
              <CommandEmpty>
                {query.trim() ? `Press Enter to add "${query}"` : "Type to search tags…"}
              </CommandEmpty>
              {suggestions.map((s) => (
                <CommandItem
                  key={`${s.entity_type}:${s.tag}`}
                  value={`${s.entity_type}:${s.tag}`}
                  onSelect={() => {
                    addTag(s.tag, s.entity_type);
                    setQuery("");
                  }}
                >
                  <span className="flex-1 truncate">{s.tag}</span>
                  <span className="rounded bg-surface-sunken px-1.5 py-0.5 text-[10px] font-medium text-text-muted">
                    {s.entity_type}
                  </span>
                </CommandItem>
              ))}
            </CommandList>
          </Command>
        </PopoverContent>
      </Popover>
    </div>
  );
}

// ── Authors: plain string chips, no autocomplete ──

function AuthorChipsField({
  authors,
  onChange,
  inputId,
}: {
  authors: string[];
  onChange: (authors: string[]) => void;
  inputId?: string;
}) {
  const [query, setQuery] = useState("");

  const addAuthor = (raw: string) => {
    const name = raw.trim();
    if (!name || authors.some((a) => a.toLowerCase() === name.toLowerCase())) return;
    onChange([...authors, name]);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault();
      addAuthor(query);
      setQuery("");
    } else if (e.key === "Backspace" && !query && authors.length > 0) {
      onChange(authors.slice(0, -1));
    }
  };

  return (
    <div className="flex flex-wrap items-center gap-1.5 rounded-md border border-input bg-transparent px-2 py-1.5">
      {authors.map((name) => (
        <Badge key={name} variant="secondary">
          {name}
          <button
            type="button"
            onClick={() => onChange(authors.filter((a) => a !== name))}
            aria-label={`Remove ${name}`}
            className="rounded-full hover:opacity-70"
          >
            <X className="size-3" />
          </button>
        </Badge>
      ))}
      <input
        id={inputId}
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Add author…"
        className="min-w-24 flex-1 bg-transparent py-0.5 text-sm outline-none placeholder:text-muted-foreground"
      />
    </div>
  );
}

// ── Main dialog ──

/** hiledit: edit title/date/tags/authors, diffed against `artifact` and sent as a partial correction. */
export function EditMetadataDialog({ artifact, open, onOpenChange }: EditMetadataDialogProps) {
  const correctMetadata = useCorrectArtifactMetadata(artifact.artifact_id);

  const initialTitle = artifact.title_mention?.title ?? "";
  const initialDate = toDateInputValue(artifact.presentation_date?.date);
  const initialTags: TagChip[] = artifact.tag_mentions.map((tm) => ({
    tag: tm.tag,
    entity_type: tm.entity_type,
  }));
  const initialAuthors = artifact.author_mentions.map((am) => am.name);

  const [title, setTitle] = useState(initialTitle);
  const [date, setDate] = useState(initialDate);
  const [tags, setTags] = useState<TagChip[]>(initialTags);
  const [authors, setAuthors] = useState<string[]>(initialAuthors);

  // Reset the form to the artifact's current values each time the dialog opens.
  useEffect(() => {
    if (!open) return;
    setTitle(initialTitle);
    setDate(initialDate);
    setTags(initialTags);
    setAuthors(initialAuthors);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, artifact.artifact_id]);

  const titleChanged = title.trim() !== initialTitle;
  const dateChanged = date !== initialDate;
  const tagsChanged = JSON.stringify(tags) !== JSON.stringify(initialTags);
  const authorsChanged = JSON.stringify(authors) !== JSON.stringify(initialAuthors);
  const hasChanges = titleChanged || dateChanged || tagsChanged || authorsChanged;

  const handleSubmit = async () => {
    if (!hasChanges || correctMetadata.isPending) return;

    // Omitted-vs-null matters server-side: only touch fields that actually changed.
    const body: CorrectArtifactMetadataBody = {};
    if (titleChanged) body.title = title.trim() || null;
    if (dateChanged) body.presentation_date = date || null;
    if (tagsChanged) body.tags = tags;
    if (authorsChanged) body.authors = authors;

    try {
      await correctMetadata.mutateAsync(body);
      toast.success("Metadata updated");
      onOpenChange(false);
    } catch (err) {
      toast.error("Failed to save corrections", {
        description: getErrorMessage(err),
      });
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[480px]">
        <DialogHeader>
          <DialogTitle>Edit metadata</DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="edit-metadata-title">Title</Label>
            <Input
              id="edit-metadata-title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Untitled"
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="edit-metadata-date">Date</Label>
            <div className="flex items-center gap-2">
              <Input
                id="edit-metadata-date"
                type="date"
                value={date}
                onChange={(e) => setDate(e.target.value)}
                className="w-auto"
              />
              {date && (
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-sm"
                  onClick={() => setDate("")}
                  aria-label="Clear date"
                >
                  <X className="size-3.5" />
                </Button>
              )}
            </div>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="edit-metadata-tags">Tags</Label>
            <TagChipsField tags={tags} onChange={setTags} inputId="edit-metadata-tags" />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="edit-metadata-authors">Authors</Label>
            <AuthorChipsField
              authors={authors}
              onChange={setAuthors}
              inputId="edit-metadata-authors"
            />
          </div>
        </div>

        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            type="button"
            onClick={handleSubmit}
            disabled={!hasChanges || correctMetadata.isPending}
          >
            {correctMetadata.isPending && <Loader2 className="size-4 animate-spin" />}
            Save
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
