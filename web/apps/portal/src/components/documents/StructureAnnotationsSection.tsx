"use client";

import { useState } from "react";
import { ChevronDown } from "lucide-react";

import { useAuthBlobUrl } from "@/hooks/use-auth-blob-url";
import { Card, CardHeader } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { API_URL } from "@/lib/constants";
import { useCorrectPageCompounds } from "@/hooks/use-pages";
import type { CompoundMention } from "@docu-store/types";

/** A mention we can actually draw: coordinates present. */
type LocatedMention = CompoundMention & { structure_bbox: number[] };

function isLocated(m: CompoundMention): m is LocatedMention {
  return Array.isArray(m.structure_bbox) && m.structure_bbox.length === 4;
}

function BoxOverlay({
  mentions,
  natural,
  activeIndex,
  onHover,
}: {
  mentions: LocatedMention[];
  natural: { w: number; h: number };
  activeIndex: number | null;
  onHover: (i: number | null) => void;
}) {
  return (
    <svg
      className="pointer-events-none absolute inset-0 h-full w-full"
      viewBox={`0 0 ${natural.w} ${natural.h}`}
      preserveAspectRatio="none"
    >
      {mentions.map((m, i) => {
        const [sx1, sy1, sx2, sy2] = m.structure_bbox;
        const label = m.label_bbox;
        const active = activeIndex === i;
        const stroke = Math.max(natural.w, natural.h) / 400;
        return (
          <g
            key={i}
            className="pointer-events-auto cursor-pointer"
            onMouseEnter={() => onHover(i)}
            onMouseLeave={() => onHover(null)}
            opacity={activeIndex === null || active ? 1 : 0.35}
          >
            <rect
              x={sx1}
              y={sy1}
              width={sx2 - sx1}
              height={sy2 - sy1}
              fill="none"
              stroke="#22c55e"
              strokeWidth={active ? stroke * 2 : stroke}
            />
            {label && label.length === 4 && (
              <>
                <rect
                  x={label[0]}
                  y={label[1]}
                  width={label[2] - label[0]}
                  height={label[3] - label[1]}
                  fill="none"
                  stroke="#3b82f6"
                  strokeWidth={active ? stroke * 2 : stroke}
                />
                <line
                  x1={(sx1 + sx2) / 2}
                  y1={(sy1 + sy2) / 2}
                  x2={(label[0] + label[2]) / 2}
                  y2={(label[1] + label[3]) / 2}
                  stroke="#f97316"
                  strokeWidth={stroke}
                  strokeDasharray={`${stroke * 3} ${stroke * 2}`}
                />
              </>
            )}
          </g>
        );
      })}
    </svg>
  );
}

export function StructureAnnotationsSection({
  artifactId,
  pageIndex,
  compounds,
  pageId,
  editable,
}: {
  artifactId: string;
  pageIndex: number;
  compounds: CompoundMention[];
  pageId: string;
  editable: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  const [activeIndex, setActiveIndex] = useState<number | null>(null);
  const [natural, setNatural] = useState<{ w: number; h: number } | null>(null);
  const [editing, setEditing] = useState(false);
  const { blobUrl, error } = useAuthBlobUrl(
    expanded ? `${API_URL}/artifacts/${artifactId}/pages/${pageIndex}/image?size=cser` : "",
  );
  const correct = useCorrectPageCompounds(pageId);

  if (compounds.length === 0) return null;

  const located = compounds.filter(isLocated);
  const missingCoordinates = compounds.length - located.length;

  // Byte-identical round-trip: the server's identity comparison keys on
  // (smiles, extracted_id, internal_id, cdd_id, chembl_id, pdb_id, structure_bbox,
  // label_bbox) — build straight from the loaded mention, no re-derivation.
  const toInput = (m: CompoundMention) => ({
    smiles: m.smiles,
    extracted_id: m.extracted_id ?? null,
    internal_id: m.internal_id ?? null,
    cdd_id: m.cdd_id ?? null,
    chembl_id: m.chembl_id ?? null,
    pdb_id: m.pdb_id ?? null,
    structure_bbox: m.structure_bbox ?? null,
    label_bbox: m.label_bbox ?? null,
  });

  const approve = () => correct.mutateAsync({ compound_mentions: compounds.map(toInput) });

  const markEmpty = () => correct.mutateAsync({ compound_mentions: [] });

  return (
    <Card className="mt-6">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-center justify-between text-left"
      >
        <CardHeader
          title={`Structure annotations · ${located.length} located · ${compounds.length} total`}
        />
        <ChevronDown
          className={`h-4 w-4 shrink-0 text-text-muted transition-transform ${expanded ? "rotate-180" : ""}`}
        />
      </button>

      {expanded && (
        <div className="mt-3 space-y-4">
          {editable && (
            <div className="flex flex-wrap items-center gap-2">
              <Button size="sm" onClick={approve} disabled={correct.isPending}>
                Approve as correct
              </Button>
              <Button size="sm" variant="outline" onClick={() => setEditing((v) => !v)}>
                {editing ? "Cancel editing" : "Edit boxes"}
              </Button>
              <Button size="sm" variant="ghost" onClick={markEmpty} disabled={correct.isPending}>
                No compounds on this page
              </Button>
            </div>
          )}

          {missingCoordinates > 0 && (
            <p className="text-sm text-text-muted">
              {missingCoordinates} compound{missingCoordinates === 1 ? "" : "s"} extracted before
              annotations were recorded — re-run compound extraction to place them.
            </p>
          )}

          {error ? (
            <p className="text-sm text-text-muted">
              No structure render stored for this page — re-run compound extraction.
            </p>
          ) : !blobUrl ? (
            <Skeleton className="h-[600px] w-full rounded-lg bg-surface-elevated" />
          ) : (
            <div className="flex justify-center">
              {/* Shrink-wraps the image, so inset-0 is exactly the image's rect
                  and the SVG viewBox maps stored pixels straight onto it. */}
              <div className="relative inline-block">
                <img
                  src={blobUrl}
                  alt={`Page ${pageIndex + 1} structure annotations`}
                  className="block max-h-[80vh] w-auto rounded-lg border border-border-default"
                  onLoad={(e) =>
                    setNatural({
                      w: e.currentTarget.naturalWidth,
                      h: e.currentTarget.naturalHeight,
                    })
                  }
                />
                {natural && (
                  <BoxOverlay
                    mentions={located}
                    natural={natural}
                    activeIndex={activeIndex}
                    onHover={setActiveIndex}
                  />
                )}
              </div>
            </div>
          )}

          {located.length > 0 && (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {located.map((m, i) => (
                <div
                  key={i}
                  onMouseEnter={() => setActiveIndex(i)}
                  onMouseLeave={() => setActiveIndex(null)}
                  className={`rounded-lg border p-3 transition-colors ${
                    activeIndex === i
                      ? "border-primary/50 bg-surface-elevated"
                      : "border-border-subtle"
                  }`}
                >
                  <div className="text-sm font-medium text-text-primary">
                    {m.extracted_id ?? "unlabelled"}
                  </div>
                  <div className="mt-1 break-all font-mono text-xs text-text-muted">
                    {m.smiles}
                  </div>
                  <div className="mt-2 flex gap-3 text-xs text-text-muted">
                    {m.confidence != null && <span>match {(m.confidence * 100).toFixed(0)}%</span>}
                    {m.structure_confidence != null && (
                      <span>structure {(m.structure_confidence * 100).toFixed(0)}%</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </Card>
  );
}
