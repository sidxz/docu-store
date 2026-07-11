"use client";

import { useState } from "react";
import Link from "next/link";
import { ChevronDown, Loader2 } from "lucide-react";
import { MoleculeStructure } from "@docu-store/ui";
import type { CompoundSearchResultDTO } from "@docu-store/types";
import { Card } from "@/components/ui/Card";
import { ScoreBadge } from "@/components/ui/ScoreBadge";
import { CopySmiles } from "@/components/ui/CopySmiles";
import { BioactivityTable } from "@/components/ui/BioactivityTable";
import { useCompoundProfile } from "@/hooks/use-compound-profile";

export function CompoundResultCard({ r, workspace }: { r: CompoundSearchResultDTO; workspace: string }) {
  const [open, setOpen] = useState(false);
  const profile = useCompoundProfile(open ? r.extracted_id : null);

  return (
    <Card>
      <div className="flex justify-center border-b border-border-subtle pb-3 mb-3">
        <MoleculeStructure smiles={r.smiles} width={200} height={140} />
      </div>
      <div className="space-y-2 text-xs">
        <div className="flex items-center justify-between">
          <span className="text-text-muted">Similarity</span>
          <ScoreBadge score={r.similarity_score} variant="pill" />
        </div>
        <CopySmiles smiles={r.smiles} maxWidth="max-w-[160px]" />
        {r.extracted_id && (
          <div className="flex items-center justify-between">
            <span className="text-text-muted">ID</span>
            <span className="font-mono font-medium text-text-primary">{r.extracted_id}</span>
          </div>
        )}
        {r.confidence != null && (
          <div className="flex items-center justify-between">
            <span className="text-text-muted">Confidence</span>
            <ScoreBadge score={r.confidence} variant="pill" />
          </div>
        )}
        <div className="flex items-center justify-between pt-1 border-t border-border-subtle">
          <Link href={`/${workspace}/documents/${r.artifact_id}`} className="text-accent-text hover:underline">
            {r.artifact_name ?? "Document"}
          </Link>
          <Link href={`/${workspace}/documents/${r.artifact_id}/pages/${r.page_id}`} className="text-text-muted hover:text-text-secondary">
            Page {r.page_index}
          </Link>
        </div>

        {r.extracted_id && (
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            aria-expanded={open}
            className="mt-1 flex w-full items-center justify-center gap-1 border-t border-border-subtle pt-2 text-[11px] font-medium text-text-muted transition-colors hover:text-text-primary"
          >
            <ChevronDown className={`size-3 transition-transform ${open ? "rotate-180" : ""}`} />
            {open ? "Hide activity" : "Show activity & sources"}
          </button>
        )}

        {open && (
          <div className="pt-1">
            {profile.isPending && <Loader2 className="mx-auto size-4 animate-spin text-text-muted" />}
            {profile.data && (
              <>
                {profile.data.synonyms.length > 0 && (
                  <p className="mb-1 truncate text-[11px] text-text-muted" title={profile.data.synonyms.join(", ")}>
                    aka {profile.data.synonyms.join(", ")}
                  </p>
                )}
                {profile.data.bioactivities.length > 0 ? (
                  <BioactivityTable activities={profile.data.bioactivities} />
                ) : (
                  <p className="text-[11px] text-text-muted">No activity data on file.</p>
                )}
                {profile.data.reference_pages.length > 0 && (
                  <div className="mt-2">
                    <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-text-muted">Appears on</p>
                    <div className="flex flex-wrap gap-1">
                      {profile.data.reference_pages.map((p) => (
                        <Link
                          key={p.page_id}
                          href={`/${workspace}/documents/${p.artifact_id}/pages/${p.page_id}`}
                          className="rounded bg-surface-sunken px-1.5 py-0.5 text-[10px] text-text-muted hover:text-accent-text"
                          title={p.artifact_title ?? undefined}
                        >
                          p.{p.page_index}
                        </Link>
                      ))}
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        )}
      </div>
    </Card>
  );
}
