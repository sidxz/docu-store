"use client";

import { useState } from "react";
import { toast } from "sonner";
import { Check, Loader2, Pencil, Plus, X } from "lucide-react";

import type { ArtifactResponse } from "@docu-store/types";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Command,
  CommandEmpty,
  CommandGroup,
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

/** hiledit: per-field inline editors. Each saves ONLY its own field via
 * PATCH /artifacts/{id}/metadata (omitted fields stay untouched server-side). */

interface TagChip {
  tag: string;
  entity_type: string | null;
}

/** Entity types a human can assign to a new tag (mirrors backend NER vocabulary). */
const ENTITY_TYPE_OPTIONS: { value: string | null; label: string }[] = [
  { value: null, label: "generic" },
  { value: "compound_name", label: "compound" },
  { value: "target", label: "target" },
  { value: "gene_name", label: "gene" },
  { value: "disease", label: "disease" },
];

/** `PresentationDate.date` is an ISO datetime; <input type="date"> wants just the date part. */
function toDateInputValue(iso: string | null | undefined): string {
  return iso ? iso.slice(0, 10) : "";
}

function useFieldSave(artifactId: string) {
  const mutation = useCorrectArtifactMetadata(artifactId);
  const save = async (body: CorrectArtifactMetadataBody, onDone: () => void) => {
    try {
      await mutation.mutateAsync(body);
      toast.success("Saved");
      onDone();
    } catch (err) {
      toast.error("Failed to save correction", { description: getErrorMessage(err) });
    }
  };
  return { save, isPending: mutation.isPending };
}

function EditActions({
  onSave,
  onCancel,
  isPending,
}: {
  onSave: () => void;
  onCancel: () => void;
  isPending: boolean;
}) {
  return (
    <span className="inline-flex items-center gap-1">
      <Button
        type="button"
        variant="ghost"
        size="icon-sm"
        onClick={onSave}
        disabled={isPending}
        aria-label="Save"
      >
        {isPending ? <Loader2 className="size-3.5 animate-spin" /> : <Check className="size-3.5" />}
      </Button>
      <Button
        type="button"
        variant="ghost"
        size="icon-sm"
        onClick={onCancel}
        disabled={isPending}
        aria-label="Cancel"
      >
        <X className="size-3.5" />
      </Button>
    </span>
  );
}

function PencilButton({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      className="text-text-muted transition-colors hover:text-text-primary"
    >
      <Pencil className="size-3.5" />
    </button>
  );
}

// ── Title (rendered inside PageHeader's <h1>) ──

export function EditableTitle({
  artifact,
  canEdit,
}: {
  artifact: ArtifactResponse;
  canEdit: boolean;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const { save, isPending } = useFieldSave(artifact.artifact_id);

  const current = artifact.title_mention?.title ?? artifact.source_filename ?? "Untitled";

  if (!editing) {
    return (
      <span className="inline-flex items-center gap-2">
        {current}
        {canEdit && (
          <PencilButton
            label="Edit title"
            onClick={() => {
              setDraft(artifact.title_mention?.title ?? "");
              setEditing(true);
            }}
          />
        )}
      </span>
    );
  }

  const submit = () => save({ title: draft.trim() || null }, () => setEditing(false));

  return (
    <span className="flex items-center gap-2">
      <Input
        autoFocus
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") submit();
          if (e.key === "Escape") setEditing(false);
        }}
        placeholder="Untitled"
        aria-label="Title"
        className="h-9 w-96 max-w-full text-lg font-semibold"
      />
      <EditActions onSave={submit} onCancel={() => setEditing(false)} isPending={isPending} />
    </span>
  );
}

// ── Presentation date ──

export function EditableDate({
  artifact,
  canEdit,
}: {
  artifact: ArtifactResponse;
  canEdit: boolean;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const { save, isPending } = useFieldSave(artifact.artifact_id);

  if (!editing) {
    return (
      <span className="inline-flex items-center gap-2">
        {artifact.presentation_date ? (
          // Stored as a UTC-midnight datetime; render in UTC so it shows the
          // picked calendar day regardless of the viewer's timezone.
          new Date(artifact.presentation_date.date).toLocaleDateString(undefined, {
            year: "numeric",
            month: "long",
            day: "numeric",
            timeZone: "UTC",
          })
        ) : (
          <span className="text-text-muted">—</span>
        )}
        {canEdit && (
          <PencilButton
            label="Edit date"
            onClick={() => {
              setDraft(toDateInputValue(artifact.presentation_date?.date));
              setEditing(true);
            }}
          />
        )}
      </span>
    );
  }

  const submit = () => save({ presentation_date: draft || null }, () => setEditing(false));

  return (
    <span className="inline-flex items-center gap-2">
      <Input
        autoFocus
        type="date"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") submit();
          if (e.key === "Escape") setEditing(false);
        }}
        aria-label="Presentation date"
        className="h-8 w-auto"
      />
      {draft && (
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          onClick={() => setDraft("")}
          aria-label="Clear date"
        >
          <X className="size-3.5" />
        </Button>
      )}
      <EditActions onSave={submit} onCancel={() => setEditing(false)} isPending={isPending} />
    </span>
  );
}

// ── Authors ──

function AuthorChipsField({
  authors,
  onChange,
}: {
  authors: string[];
  onChange: (authors: string[]) => void;
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
    <div className="flex min-w-64 flex-wrap items-center gap-1.5 rounded-md border border-input bg-transparent px-2 py-1.5">
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
        autoFocus
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Add author…"
        aria-label="Add author"
        className="min-w-24 flex-1 bg-transparent py-0.5 text-sm outline-none placeholder:text-muted-foreground"
      />
    </div>
  );
}

export function EditableAuthors({
  artifact,
  canEdit,
}: {
  artifact: ArtifactResponse;
  canEdit: boolean;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<string[]>([]);
  const { save, isPending } = useFieldSave(artifact.artifact_id);

  const current = artifact.author_mentions?.map((am) => am.name) ?? [];

  if (!editing) {
    return (
      <div className="mt-1 flex flex-wrap items-center gap-2">
        {current.length > 0 ? (
          current.map((name, i) => (
            <span
              key={`${name}-${i}`}
              className="rounded-md border border-border-default bg-surface-elevated px-2 py-1 text-sm font-medium text-text-primary"
            >
              {name}
            </span>
          ))
        ) : (
          <span className="text-sm text-text-muted">—</span>
        )}
        {canEdit && (
          <PencilButton
            label="Edit authors"
            onClick={() => {
              setDraft(current);
              setEditing(true);
            }}
          />
        )}
      </div>
    );
  }

  return (
    <div className="mt-1 flex flex-wrap items-center gap-2">
      <AuthorChipsField authors={draft} onChange={setDraft} />
      <EditActions
        onSave={() => save({ authors: draft }, () => setEditing(false))}
        onCancel={() => setEditing(false)}
        isPending={isPending}
      />
    </div>
  );
}

// ── Tags (chips + suggestions + explicit entity-type choice for new tags) ──

function TagChipsField({
  tags,
  onChange,
}: {
  tags: TagChip[];
  onChange: (tags: TagChip[]) => void;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const suggestions = useTagSuggestions(query);

  // The same tag text can legitimately appear twice with different entity_type
  // (backend merges on the (entity_type, tag) pair), so identity includes both.
  const addTag = (raw: string, entityType: string | null = null) => {
    const tag = raw.trim();
    if (
      !tag ||
      tags.some(
        (t) => t.entity_type === entityType && t.tag.toLowerCase() === tag.toLowerCase(),
      )
    )
      return;
    onChange([...tags, { tag, entity_type: entityType }]);
    setQuery("");
  };

  const removeTag = (chip: TagChip) => {
    onChange(tags.filter((t) => t.tag !== chip.tag || t.entity_type !== chip.entity_type));
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
            <span className="text-[10px] font-normal text-muted-foreground">{t.entity_type}</span>
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
        <PopoverContent className="w-72 p-0" align="start">
          <Command shouldFilter={false}>
            <CommandInput
              placeholder="Type to search or add…"
              value={query}
              onValueChange={setQuery}
              onKeyDown={(e) => {
                if (e.key === "Backspace" && !query && tags.length > 0) {
                  onChange(tags.slice(0, -1));
                }
              }}
            />
            <CommandList>
              <CommandEmpty>
                {query.trim() ? "Add below, or keep typing…" : "Type to search tags…"}
              </CommandEmpty>
              {suggestions.length > 0 && (
                <CommandGroup heading="Existing tags">
                  {suggestions.map((s) => (
                    <CommandItem
                      key={`${s.entity_type}:${s.tag}`}
                      value={`suggest:${s.entity_type}:${s.tag}`}
                      onSelect={() => addTag(s.tag, s.entity_type)}
                    >
                      <span className="flex-1 truncate">{s.tag}</span>
                      <span className="rounded bg-surface-sunken px-1.5 py-0.5 text-[10px] font-medium text-text-muted">
                        {s.entity_type}
                      </span>
                    </CommandItem>
                  ))}
                </CommandGroup>
              )}
              {query.trim() && (
                <CommandGroup heading={`Add "${query.trim()}" as`}>
                  {ENTITY_TYPE_OPTIONS.map((opt) => (
                    <CommandItem
                      key={`create:${opt.value ?? "generic"}`}
                      value={`create:${opt.value ?? "generic"}:${query}`}
                      onSelect={() => addTag(query, opt.value)}
                    >
                      <Plus className="size-3.5 text-text-muted" />
                      <span className="flex-1 truncate">{query.trim()}</span>
                      <span className="rounded bg-surface-sunken px-1.5 py-0.5 text-[10px] font-medium text-text-muted">
                        {opt.label}
                      </span>
                    </CommandItem>
                  ))}
                </CommandGroup>
              )}
            </CommandList>
          </Command>
        </PopoverContent>
      </Popover>
    </div>
  );
}

export function EditableTags({ artifact }: { artifact: ArtifactResponse }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<TagChip[]>([]);
  const { save, isPending } = useFieldSave(artifact.artifact_id);

  if (!editing) {
    return (
      <Button
        type="button"
        variant="ghost"
        size="sm"
        className="h-7 gap-1.5 text-xs text-text-muted hover:text-text-primary"
        onClick={() => {
          setDraft(
            artifact.tag_mentions.map((tm) => ({ tag: tm.tag, entity_type: tm.entity_type })),
          );
          setEditing(true);
        }}
      >
        <Pencil className="size-3" />
        Edit tags
      </Button>
    );
  }

  return (
    <div className="mt-2 flex flex-wrap items-center gap-2 rounded-md border border-border-subtle bg-surface-sunken/40 p-2">
      <TagChipsField tags={draft} onChange={setDraft} />
      <EditActions
        onSave={() => save({ tags: draft }, () => setEditing(false))}
        onCancel={() => setEditing(false)}
        isPending={isPending}
      />
    </div>
  );
}
