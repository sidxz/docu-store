"use client";

import { useState, type ReactNode } from "react";
import Link from "next/link";
import type { components } from "@docu-store/api-client";
import type { Bioactivity } from "@docu-store/types";
import { MoleculeStructure } from "@docu-store/ui";
import { Card } from "@/components/ui/Card";
import { BioactivityTable } from "@/components/ui/BioactivityTable";

type TagMentionItem = NonNullable<
  components["schemas"]["ArtifactResponse"]["tag_mentions"]
>[number];

const ENTITY_STYLE: Record<string, { label: string; dot: string; pill: string }> = {
  compound_name: { label: "Compounds", dot: "bg-emerald-500", pill: "border-emerald-500/30" },
  target: { label: "Targets", dot: "bg-amber-500", pill: "border-amber-500/30" },
  disease: { label: "Diseases", dot: "bg-rose-500", pill: "border-rose-500/30" },
};
const FALLBACK_STYLE = { label: "", dot: "bg-zinc-400", pill: "border-zinc-400/30" };

interface EntityTagPanelProps {
  tagMentions: TagMentionItem[];
  workspace: string;
  artifactId: string;
  compoundMentions?: { extracted_id?: string | null; smiles: string; canonical_smiles?: string | null }[];
  /** hiledit: shown next to the "Entities" heading, e.g. a HumanCorrectedBadge. */
  badge?: ReactNode;
  /** hiledit: inline tag editor (trigger + expanded strip), rendered in/under the heading row. */
  editor?: ReactNode;
}

function groupTags(tagMentions: TagMentionItem[]) {
  const compounds: TagMentionItem[] = [];
  const grouped = new Map<string, TagMentionItem[]>();
  for (const tm of tagMentions) {
    const key = tm.entity_type ?? "other";
    if (key === "compound_name") {
      compounds.push(tm);
    } else {
      const arr = grouped.get(key);
      if (arr) arr.push(tm);
      else grouped.set(key, [tm]);
    }
  }
  return { compounds, grouped };
}

// ── Source badges ──

function SourceBadges({
  sources,
  workspace,
  artifactId,
}: {
  sources: { page_id: string; page_index: number }[] | undefined | null;
  workspace: string;
  artifactId: string;
}) {
  if (!sources || sources.length === 0) return null;
  const sorted = [...sources].sort((a, b) => a.page_index - b.page_index);
  return (
    <span className="inline-flex items-center gap-1">
      {sorted.map((s) => (
        <Link
          key={s.page_id}
          href={`/${workspace}/documents/${artifactId}/pages/${s.page_id}`}
          className="flex h-5 min-w-[20px] items-center justify-center rounded-md bg-surface-sunken px-1.5 text-[10px] font-mono font-medium tabular-nums text-text-muted transition-colors hover:bg-accent-light hover:text-accent-text"
        >
          {s.page_index + 1}
        </Link>
      ))}
    </span>
  );
}

function SourcePillSuffix({
  sources,
  workspace,
  artifactId,
}: {
  sources: { page_id: string; page_index: number }[] | undefined | null;
  workspace: string;
  artifactId: string;
}) {
  if (!sources || sources.length === 0) return null;
  const sorted = [...sources].sort((a, b) => a.page_index - b.page_index);
  return (
    <span className="flex items-center gap-0.5 border-l border-border-subtle py-1 pl-2 pr-2.5">
      {sorted.map((s) => (
        <Link
          key={s.page_id}
          href={`/${workspace}/documents/${artifactId}/pages/${s.page_id}`}
          className="rounded px-1 text-[10px] font-mono font-medium tabular-nums text-text-muted transition-colors hover:text-accent-text"
        >
          {s.page_index + 1}
        </Link>
      ))}
    </span>
  );
}

// ── Entity type section (targets, diseases, etc.) ──

function EntityTypeSection({
  entityType,
  tags,
  workspace,
  artifactId,
}: {
  entityType: string;
  tags: TagMentionItem[];
  workspace: string;
  artifactId: string;
}) {
  const style = ENTITY_STYLE[entityType] ?? FALLBACK_STYLE;
  return (
    <div>
      <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-text-muted">
        <span className={`h-1.5 w-1.5 rounded-full ${style.dot}`} />
        {style.label || entityType.replace(/_/g, " ")}
      </div>
      <div className="flex flex-wrap gap-2">
        {tags.map((tm, i) => {
          const sources = (tm as Record<string, unknown>).sources as
            | { page_id: string; page_index: number }[]
            | undefined;
          const hasSources = sources && sources.length > 0;
          return (
            <span
              key={`${tm.tag}-${i}`}
              className={`inline-flex items-center rounded-md border ${style.pill} bg-surface-elevated text-sm`}
            >
              <span className={`py-1 pl-3 font-medium text-text-primary ${hasSources ? "pr-2" : "pr-3"}`}>
                {tm.tag}
              </span>
              {hasSources && (
                <SourcePillSuffix sources={sources} workspace={workspace} artifactId={artifactId} />
              )}
            </span>
          );
        })}
      </div>
    </div>
  );
}

// A compound merges its aliases under one canonical name, but CSER labelled the
// structure with whichever surface form it read off the page — so fall back to
// the synonyms before giving up on a structure.
function structureFor(tm: TagMentionItem, byLabel: Map<string, string>): string | undefined {
  const params = tm.additional_model_params as Record<string, unknown> | undefined;
  const synonyms = (params?.synonyms as string | undefined)?.split(",") ?? [];
  for (const label of [tm.tag, ...synonyms]) {
    const hit = byLabel.get(label.trim().toLowerCase());
    if (hit) return hit;
  }
  return undefined;
}

// ── Compound card ──

function CompoundCard({
  tagMention,
  expanded,
  workspace,
  artifactId,
  structureSmiles,
}: {
  tagMention: TagMentionItem;
  expanded: boolean;
  workspace: string;
  artifactId: string;
  structureSmiles?: string;
}) {
  const params = tagMention.additional_model_params as Record<string, unknown> | undefined;
  const activities = params?.bioactivities as Bioactivity[] | undefined;
  const synonyms = params?.synonyms as string | undefined;
  const sources = (tagMention as Record<string, unknown>).sources as
    | { page_id: string; page_index: number }[]
    | undefined;

  return (
    <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/[0.03] p-3">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-baseline gap-2 overflow-hidden">
          <span className="text-sm font-semibold text-text-primary">{tagMention.tag}</span>
          {expanded && synonyms && (
            <span className="truncate text-xs text-text-muted">aka {synonyms}</span>
          )}
        </div>
        <SourceBadges sources={sources} workspace={workspace} artifactId={artifactId} />
      </div>
      {expanded && structureSmiles && (
        <div className="mt-2 flex justify-center border-t border-emerald-500/10 pt-2" title="Structure on file">
          <MoleculeStructure smiles={structureSmiles} width={160} height={110} />
        </div>
      )}
      {expanded && activities && activities.length > 0 && (
        <BioactivityTable activities={activities} />
      )}
    </div>
  );
}

// ── Main panel ──

export function EntityTagPanel({
  tagMentions,
  workspace,
  artifactId,
  compoundMentions = [],
  badge,
  editor,
}: EntityTagPanelProps) {
  const { compounds, grouped } = groupTags(tagMentions);
  const [expanded, setExpanded] = useState(false);

  const structureByLabel = new Map<string, string>();
  for (const c of compoundMentions) {
    const key = c.extracted_id?.trim().toLowerCase();
    const smiles = c.canonical_smiles || c.smiles;
    if (key && smiles && !structureByLabel.has(key)) structureByLabel.set(key, smiles);
  }

  const hasDetails = compounds.some((tm) => {
    const params = tm.additional_model_params as Record<string, unknown> | undefined;
    const activities = params?.bioactivities as Bioactivity[] | undefined;
    const synonyms = params?.synonyms as string | undefined;
    return (activities && activities.length > 0) || synonyms;
  });

  return (
    <Card>
      <div className="mb-4">
        <div className="flex items-start justify-between gap-2">
          <h3 className="flex items-center gap-1.5 text-sm font-medium text-text-secondary">
            Entities
            {badge}
          </h3>
        </div>
        {editor}
      </div>
      <div className="space-y-5">
        {tagMentions.length === 0 && (
          <p className="text-sm text-text-muted">—</p>
        )}
        {[...grouped.entries()].map(([entityType, tags]) => (
          <EntityTypeSection
            key={entityType}
            entityType={entityType}
            tags={tags}
            workspace={workspace}
            artifactId={artifactId}
          />
        ))}
        {compounds.length > 0 && (
          <div>
            <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-text-muted">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
              Compounds
              {hasDetails && (
                <button
                  type="button"
                  onClick={() => setExpanded((v) => !v)}
                  aria-expanded={expanded}
                  aria-label={expanded ? "Hide compound activity details" : "Show compound activity details"}
                  className="inline-flex items-center gap-0.5 text-[10px] font-medium normal-case tracking-normal text-text-muted transition-colors hover:text-text-primary"
                >
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    viewBox="0 0 16 16"
                    fill="currentColor"
                    className={`h-3 w-3 transition-transform ${expanded ? "rotate-45" : ""}`}
                  >
                    <path d="M8 2a.75.75 0 0 1 .75.75v4.5h4.5a.75.75 0 0 1 0 1.5h-4.5v4.5a.75.75 0 0 1-1.5 0v-4.5h-4.5a.75.75 0 0 1 0-1.5h4.5v-4.5A.75.75 0 0 1 8 2Z" />
                  </svg>
                  {expanded ? "(hide activity)" : "(show activity)"}
                </button>
              )}
            </div>
            <div className="grid gap-2 sm:grid-cols-2">
              {compounds.map((tm, i) => (
                <CompoundCard
                  key={`${tm.tag}-${i}`}
                  tagMention={tm}
                  expanded={expanded}
                  workspace={workspace}
                  artifactId={artifactId}
                  structureSmiles={structureFor(tm, structureByLabel)}
                />
              ))}
            </div>
          </div>
        )}
      </div>
    </Card>
  );
}
