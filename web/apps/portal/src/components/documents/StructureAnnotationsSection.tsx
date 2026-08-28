"use client";

import { useRef, useState } from "react";
import { ChevronDown, X } from "lucide-react";

import { useAuthBlobUrl } from "@/hooks/use-auth-blob-url";
import { Card, CardHeader } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { API_URL } from "@/lib/constants";
import { useCorrectPageCompounds, type CorrectedCompoundInput } from "@/hooks/use-pages";
import { EditCompoundDialog } from "@/components/documents/EditCompoundDialog";
import type { CompoundMention } from "@docu-store/types";

/** A mention we can actually draw: coordinates present. */
type WithBbox = CompoundMention & { structure_bbox: number[] };
/** ...plus its index in the working/source array, so edits write back to the right slot. */
type LocatedMention = WithBbox & { __srcIndex: number };

function isLocated(m: CompoundMention): m is WithBbox {
  return Array.isArray(m.structure_bbox) && m.structure_bbox.length === 4;
}

/** A freshly human-drawn mention, before its SMILES is known. */
function blankMention(bbox: number[]): CompoundMention {
  return {
    confidence: null,
    date_extracted: null,
    model_name: null,
    additional_model_params: null,
    pipeline_run_id: null,
    smiles: "",
    canonical_smiles: null,
    is_smiles_valid: null,
    internal_id: null,
    cdd_id: null,
    chembl_id: null,
    pdb_id: null,
    other_ids: null,
    extracted_id: null,
    structure_bbox: bbox,
    label_bbox: null,
    structure_confidence: null,
    label_confidence: null,
  };
}

/** Pointer position → SVG viewBox coordinates, i.e. render pixels — no scale factor needed. */
function toRenderPixels(evt: React.PointerEvent, svg: SVGSVGElement) {
  const point = svg.createSVGPoint();
  point.x = evt.clientX;
  point.y = evt.clientY;
  const ctm = svg.getScreenCTM();
  if (!ctm) return null;
  const local = point.matrixTransform(ctm.inverse());
  return { x: Math.round(local.x), y: Math.round(local.y) };
}

/** Normalise + round + clamp a [x1,y1,x2,y2] box to the image bounds. Normalising first
 *  means a resize dragged past its own opposite corner (x2 < x1 or y2 < y1 — every
 *  coordinate individually in bounds, but the box degenerate) still commits a valid
 *  box instead of writing an inverted one verbatim into exported training data. */
function clampToImage(bbox: number[], w: number, h: number): number[] {
  const clamp = (v: number, max: number) => Math.max(0, Math.min(max, Math.round(v)));
  const [x1, y1, x2, y2] = bbox;
  return [
    clamp(Math.min(x1, x2), w),
    clamp(Math.min(y1, y2), h),
    clamp(Math.max(x1, x2), w),
    clamp(Math.max(y1, y2), h),
  ];
}

type DragState =
  | { kind: "move"; srcIndex: number; startX: number; startY: number; startBbox: number[]; moved: boolean }
  | { kind: "resize"; srcIndex: number; startBbox: number[] };

function BoxOverlay({
  mentions,
  natural,
  activeIndex,
  onHover,
  editing,
  drawMode,
  pairSource,
  onStructureChange,
  onStructureClick,
  onLabelClick,
  onDraw,
}: {
  mentions: LocatedMention[];
  natural: { w: number; h: number };
  activeIndex: number | null;
  onHover: (i: number | null) => void;
  editing: boolean;
  drawMode: boolean;
  pairSource: number | null;
  onStructureChange: (srcIndex: number, bbox: number[]) => void;
  onStructureClick: (srcIndex: number) => void;
  onLabelClick: (srcIndex: number) => void;
  onDraw: (bbox: number[]) => void;
}) {
  const dragRef = useRef<DragState | null>(null);
  const drawStartRef = useRef<{ x: number; y: number } | null>(null);
  const [drawBox, setDrawBox] = useState<number[] | null>(null);

  const startStructureDrag = (
    e: React.PointerEvent<SVGRectElement>,
    srcIndex: number,
    bbox: number[],
  ) => {
    if (!editing || drawMode) return;
    e.preventDefault();
    const svg = e.currentTarget.ownerSVGElement;
    const p = svg && toRenderPixels(e, svg);
    if (!p) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    dragRef.current = { kind: "move", srcIndex, startX: p.x, startY: p.y, startBbox: bbox, moved: false };
  };

  const startResizeDrag = (
    e: React.PointerEvent<SVGRectElement>,
    srcIndex: number,
    bbox: number[],
  ) => {
    if (!editing || drawMode) return;
    e.preventDefault();
    e.currentTarget.setPointerCapture(e.pointerId);
    dragRef.current = { kind: "resize", srcIndex, startBbox: bbox };
  };

  const handleRectPointerMove = (e: React.PointerEvent<SVGRectElement>) => {
    const drag = dragRef.current;
    if (!drag) return;
    const svg = e.currentTarget.ownerSVGElement;
    const p = svg && toRenderPixels(e, svg);
    if (!p) return;
    if (drag.kind === "move") {
      const dx = p.x - drag.startX;
      const dy = p.y - drag.startY;
      if (Math.abs(dx) > 2 || Math.abs(dy) > 2) drag.moved = true;
      const [x1, y1, x2, y2] = drag.startBbox;
      onStructureChange(
        drag.srcIndex,
        clampToImage([x1 + dx, y1 + dy, x2 + dx, y2 + dy], natural.w, natural.h),
      );
    } else {
      const [x1, y1] = drag.startBbox;
      onStructureChange(drag.srcIndex, clampToImage([x1, y1, p.x, p.y], natural.w, natural.h));
    }
  };

  const handleRectPointerUp = (e: React.PointerEvent<SVGRectElement>) => {
    const drag = dragRef.current;
    dragRef.current = null;
    if (e.currentTarget.hasPointerCapture(e.pointerId)) {
      e.currentTarget.releasePointerCapture(e.pointerId);
    }
    if (drag?.kind === "move" && !drag.moved) onStructureClick(drag.srcIndex);
  };

  const handleBackgroundPointerDown = (e: React.PointerEvent<SVGRectElement>) => {
    if (!editing || !drawMode) return;
    e.preventDefault();
    const svg = e.currentTarget.ownerSVGElement;
    const p = svg && toRenderPixels(e, svg);
    if (!p) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    drawStartRef.current = p;
    setDrawBox([p.x, p.y, p.x, p.y]);
  };

  const handleBackgroundPointerMove = (e: React.PointerEvent<SVGRectElement>) => {
    const start = drawStartRef.current;
    if (!start) return;
    const svg = e.currentTarget.ownerSVGElement;
    const p = svg && toRenderPixels(e, svg);
    if (!p) return;
    setDrawBox([
      Math.min(start.x, p.x),
      Math.min(start.y, p.y),
      Math.max(start.x, p.x),
      Math.max(start.y, p.y),
    ]);
  };

  const handleBackgroundPointerUp = (e: React.PointerEvent<SVGRectElement>) => {
    const start = drawStartRef.current;
    drawStartRef.current = null;
    if (e.currentTarget.hasPointerCapture(e.pointerId)) {
      e.currentTarget.releasePointerCapture(e.pointerId);
    }
    const box = drawBox;
    setDrawBox(null);
    if (!start || !box) return;
    const [x1, y1, x2, y2] = box;
    if (x2 - x1 < 6 || y2 - y1 < 6) return; // too small to be intentional
    onDraw(clampToImage(box, natural.w, natural.h));
  };

  return (
    <svg
      className="absolute inset-0 h-full w-full"
      viewBox={`0 0 ${natural.w} ${natural.h}`}
      preserveAspectRatio="none"
      style={{ pointerEvents: editing ? "auto" : "none" }}
    >
      <rect
        x={0}
        y={0}
        width={natural.w}
        height={natural.h}
        fill="transparent"
        style={{ pointerEvents: editing && drawMode ? "auto" : "none", cursor: "crosshair" }}
        onPointerDown={handleBackgroundPointerDown}
        onPointerMove={handleBackgroundPointerMove}
        onPointerUp={handleBackgroundPointerUp}
      />

      {mentions.map((m, i) => {
        const [sx1, sy1, sx2, sy2] = m.structure_bbox;
        const label = m.label_bbox;
        const active = activeIndex === i;
        const stroke = Math.max(natural.w, natural.h) / 400;
        const handleSize = stroke * 4;
        const isPairSource = pairSource === m.__srcIndex;
        return (
          <g
            key={i}
            className="cursor-pointer"
            style={{ pointerEvents: editing && drawMode ? "none" : "auto" }}
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
              strokeDasharray={isPairSource ? `${stroke * 2} ${stroke}` : undefined}
              style={{ cursor: editing ? "move" : "pointer" }}
              onPointerDown={(e) => startStructureDrag(e, m.__srcIndex, [sx1, sy1, sx2, sy2])}
              onPointerMove={handleRectPointerMove}
              onPointerUp={handleRectPointerUp}
            />
            {editing && (
              <rect
                x={sx2 - handleSize / 2}
                y={sy2 - handleSize / 2}
                width={handleSize}
                height={handleSize}
                fill="#22c55e"
                style={{ cursor: "nwse-resize" }}
                onPointerDown={(e) => startResizeDrag(e, m.__srcIndex, [sx1, sy1, sx2, sy2])}
                onPointerMove={handleRectPointerMove}
                onPointerUp={handleRectPointerUp}
              />
            )}
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
                  style={{ cursor: editing && !drawMode ? "pointer" : "default" }}
                  onClick={() => editing && !drawMode && onLabelClick(m.__srcIndex)}
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

      {drawBox && (
        <rect
          x={drawBox[0]}
          y={drawBox[1]}
          width={drawBox[2] - drawBox[0]}
          height={drawBox[3] - drawBox[1]}
          fill="rgba(34,197,94,0.15)"
          stroke="#22c55e"
          strokeDasharray="4 3"
        />
      )}
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
  const [working, setWorking] = useState<CompoundMention[] | null>(null);
  const [drawMode, setDrawMode] = useState(false);
  const [pairSource, setPairSource] = useState<number | null>(null);
  const [pendingDrawBbox, setPendingDrawBbox] = useState<number[] | null>(null);
  const { blobUrl, error } = useAuthBlobUrl(
    expanded ? `${API_URL}/artifacts/${artifactId}/pages/${pageIndex}/image?size=cser` : "",
  );
  const correct = useCorrectPageCompounds(pageId);

  // A page with no detections is the commonest — and most valuable — negative, so
  // a reviewer must still be able to open it and mark it reviewed-empty (or draw a
  // box the detector missed). Only the read-only view has nothing to show.
  if (compounds.length === 0 && !editable) return null;

  // While editing, the draft (`working`) is the source of truth for both the overlay
  // and the card grid below it; otherwise it's the loaded `compounds` as-is.
  const source = editing && working ? working : compounds;
  const located: LocatedMention[] = [];
  source.forEach((m, i) => {
    if (isLocated(m)) located.push({ ...m, __srcIndex: i });
  });
  const missingCoordinates = source.length - located.length;

  // Byte-identical round-trip: the server's identity comparison keys on
  // (smiles, extracted_id, internal_id, cdd_id, chembl_id, pdb_id, structure_bbox,
  // label_bbox) — build straight from the loaded mention, no re-derivation.
  const toInput = (m: CompoundMention): CorrectedCompoundInput => ({
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

  const resetDraft = () => {
    setWorking(null);
    setDrawMode(false);
    setPairSource(null);
    setPendingDrawBbox(null);
  };

  const toggleEditing = () => {
    if (editing) {
      setEditing(false);
      resetDraft();
    } else {
      setEditing(true);
      setWorking(compounds.map((m) => ({ ...m })));
    }
  };

  const save = async () => {
    if (!working) return;
    await correct.mutateAsync({ compound_mentions: working.map(toInput) });
    setEditing(false);
    resetDraft();
  };

  const handleStructureChange = (srcIndex: number, bbox: number[]) =>
    setWorking((prev) => prev && prev.map((m, i) => (i === srcIndex ? { ...m, structure_bbox: bbox } : m)));

  const handleStructureClick = (srcIndex: number) =>
    setPairSource((prev) => (prev === srcIndex ? null : srcIndex));

  /** Re-pair: the clicked label box (on `srcIndex`) belongs to the structure picked
   *  first (`target`). This SWAPS the label box and its text between the two, never
   *  copies: one box on two mentions would export twice and claim two owners. The
   *  text travels with the box because `extracted_id` becomes the exported
   *  `label_text` — the words physically inside that rectangle — so leaving it
   *  behind would ship a box captioned with someone else's label. Swapping (rather
   *  than clearing the source) fixes the usual cause in one gesture — two structures
   *  holding each other's labels — and destroys nothing: when the target is
   *  unlabelled it hands back null, which is exactly a move. */
  const handleLabelClick = (srcIndex: number) => {
    if (pairSource === null || pairSource === srcIndex) return;
    const target = pairSource;
    setWorking((prev) => {
      if (!prev) return prev;
      const from = prev[srcIndex];
      const to = prev[target];
      const label = from?.label_bbox;
      if (!from || !to || !label) return prev;
      return prev.map((m, i) => {
        if (i === target) {
          return { ...m, label_bbox: [...label], extracted_id: from.extracted_id ?? null };
        }
        if (i === srcIndex) {
          return {
            ...m,
            label_bbox: to.label_bbox ? [...to.label_bbox] : null,
            extracted_id: to.extracted_id ?? null,
          };
        }
        return m;
      });
    });
    setPairSource(null);
  };

  const handleDelete = (srcIndex: number) => {
    setWorking((prev) => prev && prev.filter((_, i) => i !== srcIndex));
    setPairSource(null);
  };

  const handleDraw = (bbox: number[]) => {
    setPendingDrawBbox(bbox);
    setDrawMode(false);
  };

  return (
    <>
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
                {!editing ? (
                  <>
                    {compounds.length > 0 && (
                      <Button size="sm" onClick={approve} disabled={correct.isPending}>
                        Approve as correct
                      </Button>
                    )}
                    <Button size="sm" variant="outline" onClick={toggleEditing}>
                      Edit boxes
                    </Button>
                    <Button size="sm" variant="ghost" onClick={markEmpty} disabled={correct.isPending}>
                      No compounds on this page
                    </Button>
                  </>
                ) : (
                  <>
                    <Button size="sm" onClick={save} disabled={correct.isPending}>
                      Save changes
                    </Button>
                    <Button
                      size="sm"
                      variant={drawMode ? "default" : "outline"}
                      onClick={() => setDrawMode((v) => !v)}
                    >
                      {drawMode ? "Drawing — drag on image" : "Add pair"}
                    </Button>
                    <Button size="sm" variant="ghost" onClick={toggleEditing} disabled={correct.isPending}>
                      Cancel editing
                    </Button>
                  </>
                )}
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
                      editing={editing}
                      drawMode={drawMode}
                      pairSource={pairSource}
                      onStructureChange={handleStructureChange}
                      onStructureClick={handleStructureClick}
                      onLabelClick={handleLabelClick}
                      onDraw={handleDraw}
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
                    className={`group/ann relative rounded-lg border p-3 transition-colors ${
                      activeIndex === i
                        ? "border-primary/50 bg-surface-elevated"
                        : "border-border-subtle"
                    }`}
                  >
                    {editing && (
                      <button
                        type="button"
                        aria-label="Delete pair"
                        onClick={() => handleDelete(m.__srcIndex)}
                        className="absolute right-2 top-2 rounded-sm p-0.5 text-text-muted opacity-0 transition-opacity hover:text-ds-error group-hover/ann:opacity-100"
                      >
                        <X className="size-3.5" />
                      </button>
                    )}
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

      {editable && (
        <EditCompoundDialog
          open={pendingDrawBbox !== null}
          onOpenChange={(open) => !open && setPendingDrawBbox(null)}
          compound={null}
          onSave={async (item) => {
            if (!pendingDrawBbox) return;
            const bbox = pendingDrawBbox;
            setWorking((prev) => [
              ...(prev ?? []),
              {
                ...blankMention(bbox),
                smiles: item.smiles,
                extracted_id: item.extracted_id ?? null,
                internal_id: item.internal_id ?? null,
                cdd_id: item.cdd_id ?? null,
                chembl_id: item.chembl_id ?? null,
                pdb_id: item.pdb_id ?? null,
              },
            ]);
            setPendingDrawBbox(null);
          }}
        />
      )}
    </>
  );
}
