"use client";

import { useEffect, useRef, useState } from "react";
import { BookOpen, Check, ExternalLink, Loader2, Lock, Plus, Quote } from "lucide-react";
import type { LiteratureHit } from "@docu-store/types";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useIngestLiterature } from "@/hooks/use-chat";

/**
 * One paper. Two states that look deliberately different, because they are:
 * a paper whose licence lets this workspace keep a copy, and one that can only
 * ever be read at the publisher.
 *
 * Cards render in the order Europe PMC returned them. Sorting or filtering by
 * whether a paper can be added would push the paywalled med-chem literature to
 * the bottom, and on the queries this corpus exists for that is most of what is
 * worth reading.
 */
export function LiteratureResultCard({
  hit,
  cited = false,
  citationIndex,
  highlighted = false,
}: {
  hit: LiteratureHit;
  cited?: boolean;
  /** The [n] this paper carries in the answer, when it was cited. */
  citationIndex?: number;
  /** The reader just clicked that [n]. */
  highlighted?: boolean;
}) {
  const ingest = useIngestLiterature();
  const [expanded, setExpanded] = useState(false);
  const ref = useRef<HTMLElement>(null);

  // Bring the card to the reader rather than making them find it: the panel
  // routinely holds fifty-odd papers by the time an answer lands.
  useEffect(() => {
    if (highlighted && ref.current) {
      ref.current.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [highlighted]);

  const where = [hit.journal, hit.year].filter(Boolean).join(" · ");
  const added = ingest.isSuccess;

  const add = (visibility: "private" | "workspace") =>
    ingest.mutate({ source: hit.source, external_id: hit.external_id, visibility });

  return (
    <article
      ref={ref}
      className={`rounded-lg border p-3 text-xs transition-colors ${
        cited
          // The answer leaned on this one. Worth marking, because the panel
          // shows every result and only a handful end up mattering.
          ? "border-emerald-500/40 bg-emerald-500/[0.07]"
          : "border-border-default bg-surface-elevated"
      } ${highlighted ? "ring-2 ring-emerald-500/60" : ""}`}
    >
      {cited && (
        <p className="mb-1.5 flex items-center gap-1 text-[0.6875rem] font-medium uppercase tracking-wide text-emerald-700 dark:text-emerald-400">
          {citationIndex != null ? (
            <span className="inline-flex h-4 min-w-4 items-center justify-center rounded bg-emerald-600 px-1 font-semibold text-white">
              {citationIndex}
            </span>
          ) : (
            <Quote className="h-3 w-3" />
          )}
          Cited in the answer
        </p>
      )}
      <a
        href={hit.url}
        target="_blank"
        rel="noopener noreferrer"
        className="group block font-medium text-text-primary hover:text-accent-text"
      >
        {hit.title}
        <ExternalLink className="ml-1 inline h-3 w-3 opacity-0 transition-opacity group-hover:opacity-100" />
      </a>

      {where && <p className="mt-1 text-text-muted">{where}</p>}
      {hit.authors && (
        <p className="truncate text-text-muted" title={hit.authors}>
          {hit.authors}
        </p>
      )}

      {hit.abstract && (
        <>
          <p className={`mt-2 text-text-secondary ${expanded ? "" : "line-clamp-3"}`}>
            {hit.abstract}
          </p>
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            className="mt-1 text-text-muted hover:text-text-primary"
          >
            {expanded ? "Show less" : "Show more"}
          </button>
        </>
      )}

      <div className="mt-3 flex items-center justify-between gap-2">
        {hit.is_ingestable ? (
          <Badge variant="outline" className="gap-1 text-[0.6875rem] uppercase">
            <BookOpen className="h-3 w-3" />
            {hit.licence}
          </Badge>
        ) : (
          // The reason, not just the fact: "no open licence" and "no full text
          // to fetch" are entirely different situations for a reader.
          <Badge
            variant="outline"
            className="gap-1 text-[0.6875rem] text-text-muted"
            title={hit.ingest_blocker ?? undefined}
          >
            <Lock className="h-3 w-3" />
            {hit.licence ?? "no open licence"}
          </Badge>
        )}

        {added ? (
          <span className="flex items-center gap-1 text-emerald-600">
            <Check className="h-3 w-3" />
            Added — parsing
          </span>
        ) : hit.is_ingestable ? (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button size="sm" variant="outline" disabled={ingest.isPending}>
                {ingest.isPending ? (
                  <Loader2 className="h-3 w-3 animate-spin" />
                ) : (
                  <Plus className="h-3 w-3" />
                )}
                Add to library
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={() => add("private")}>
                Private — only you
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => add("workspace")}>
                Workspace — everyone here
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        ) : (
          <a
            href={hit.url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1 text-text-muted hover:text-text-primary"
          >
            View at publisher
            <ExternalLink className="h-3 w-3" />
          </a>
        )}
      </div>

      {ingest.isError && (
        <p className="mt-2 text-[0.6875rem] text-destructive">{ingest.error.message}</p>
      )}
    </article>
  );
}
