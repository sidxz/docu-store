"use client";

import { useRef, useState } from "react";
import { ChevronDown, Loader2, X } from "lucide-react";
import { toast } from "sonner";

import { useAuthBlobUrl } from "@/hooks/use-auth-blob-url";
import { Card, CardHeader } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { API_URL } from "@/lib/constants";
import { getErrorMessage } from "@/lib/api-error";
import {
  useAnalyzeBox,
  useCorrectPageCompounds,
  useRerunPageWorkflow,
  type CorrectedCompoundInput,
} from "@/hooks/use-pages";
import { EditCompoundDialog } from "@/components/documents/EditCompoundDialog";
import { HumanCorrectedBadge } from "@/components/documents/HumanCorrectedBadge";
import type { CompoundMention, HumanCorrectionInfo } from "@docu-store/types";

/** A mention plus draft-only bookkeeping. Both flags are client-side and never leave the
 *  browser — `toInput` names every field it sends, so they cannot leak into a correction. */
type DraftMention = CompoundMention & {
  /** A human typed these values in the dialog. Analyse must not stomp them behind their back. */
  __human?: boolean;
  /** Analysed, and DECIMER read no structure. Unsaveable until a human fixes or deletes it. */
  __unreadable?: boolean;
};

/** A mention we can actually draw: coordinates present. */
type WithBbox = DraftMention & { structure_bbox: number[] };
/** ...plus its index in the working/source array, so edits write back to the right slot. */
type LocatedMention = WithBbox & { __srcIndex: number };

function isLocated(m: DraftMention): m is WithBbox {
  return Array.isArray(m.structure_bbox) && m.structure_bbox.length === 4;
}

/** A pair that would be silently dropped, or worse, saved blank: the human drew a box and
 *  no SMILES was ever established for it. The one thing Save must never quietly discard. */
const isUnsaveable = (m: CompoundMention) => !m.smiles?.trim();

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

/** Which of a pair's two boxes a gesture is acting on — YOLO class 0 vs class 1. */
type BoxKind = "structure" | "label";
/** null = not drawing; otherwise the class of box the next drag creates. */
type DrawMode = BoxKind | null;

const STRUCTURE_COLOR = "#22c55e";
const LABEL_COLOR = "#3b82f6";
/** Drawn but not analysed yet (amber) / analysed and unreadable (red). Same cue as the card,
 *  so "which of these boxes still has no SMILES" is answerable from the image alone. */
const PENDING_COLOR = "#f59e0b";
const UNREADABLE_COLOR = "#ef4444";

const structureColor = (m: DraftMention) =>
  m.smiles?.trim() ? STRUCTURE_COLOR : m.__unreadable ? UNREADABLE_COLOR : PENDING_COLOR;

type DragState =
  | {
      kind: "move";
      srcIndex: number;
      box: BoxKind;
      startX: number;
      startY: number;
      startBbox: number[];
      moved: boolean;
    }
  | { kind: "resize"; srcIndex: number; box: BoxKind; startBbox: number[] };

function BoxOverlay({
  mentions,
  natural,
  activeIndex,
  onHover,
  editing,
  drawMode,
  pairSource,
  onStructureChange,
  onLabelChange,
  onStructureClick,
  onLabelClick,
  onDraw,
}: {
  mentions: LocatedMention[];
  natural: { w: number; h: number };
  activeIndex: number | null;
  onHover: (i: number | null) => void;
  editing: boolean;
  drawMode: DrawMode;
  pairSource: number | null;
  onStructureChange: (srcIndex: number, bbox: number[]) => void;
  onLabelChange: (srcIndex: number, bbox: number[]) => void;
  onStructureClick: (srcIndex: number) => void;
  onLabelClick: (srcIndex: number) => void;
  onDraw: (bbox: number[]) => void;
}) {
  const dragRef = useRef<DragState | null>(null);
  const drawStartRef = useRef<{ x: number; y: number } | null>(null);
  const [drawBox, setDrawBox] = useState<number[] | null>(null);

  /** Both box classes share one drag machine; `box` only picks which setter commits. */
  const startBoxDrag = (
    e: React.PointerEvent<SVGRectElement>,
    srcIndex: number,
    box: BoxKind,
    bbox: number[],
  ) => {
    if (!editing || drawMode !== null) return;
    e.preventDefault();
    const svg = e.currentTarget.ownerSVGElement;
    const p = svg && toRenderPixels(e, svg);
    if (!p) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    dragRef.current = {
      kind: "move",
      srcIndex,
      box,
      startX: p.x,
      startY: p.y,
      startBbox: bbox,
      moved: false,
    };
  };

  const startResizeDrag = (
    e: React.PointerEvent<SVGRectElement>,
    srcIndex: number,
    box: BoxKind,
    bbox: number[],
  ) => {
    if (!editing || drawMode !== null) return;
    e.preventDefault();
    e.currentTarget.setPointerCapture(e.pointerId);
    dragRef.current = { kind: "resize", srcIndex, box, startBbox: bbox };
  };

  const handleRectPointerMove = (e: React.PointerEvent<SVGRectElement>) => {
    const drag = dragRef.current;
    if (!drag) return;
    const svg = e.currentTarget.ownerSVGElement;
    const p = svg && toRenderPixels(e, svg);
    if (!p) return;
    const commit = drag.box === "label" ? onLabelChange : onStructureChange;
    if (drag.kind === "move") {
      const dx = p.x - drag.startX;
      const dy = p.y - drag.startY;
      if (Math.abs(dx) > 2 || Math.abs(dy) > 2) drag.moved = true;
      const [x1, y1, x2, y2] = drag.startBbox;
      commit(drag.srcIndex, clampToImage([x1 + dx, y1 + dy, x2 + dx, y2 + dy], natural.w, natural.h));
    } else {
      const [x1, y1] = drag.startBbox;
      commit(drag.srcIndex, clampToImage([x1, y1, p.x, p.y], natural.w, natural.h));
    }
  };

  /** A press that never travelled more than the 2px slop is a click, not a drag — that is
   *  the ONLY place either click fires. Label boxes deliberately carry no `onClick`: routing
   *  their click-to-re-pair through this same gate is what stops a label drag from arming or
   *  committing a re-pair on the way past. */
  const handleRectPointerUp = (e: React.PointerEvent<SVGRectElement>) => {
    const drag = dragRef.current;
    dragRef.current = null;
    if (e.currentTarget.hasPointerCapture(e.pointerId)) {
      e.currentTarget.releasePointerCapture(e.pointerId);
    }
    if (drag?.kind === "move" && !drag.moved) {
      (drag.box === "label" ? onLabelClick : onStructureClick)(drag.srcIndex);
    }
  };

  const handleBackgroundPointerDown = (e: React.PointerEvent<SVGRectElement>) => {
    if (!editing || drawMode === null) return;
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
        style={{ pointerEvents: editing && drawMode !== null ? "auto" : "none", cursor: "crosshair" }}
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
        const boxColor = structureColor(m);
        return (
          <g
            key={i}
            className="cursor-pointer"
            style={{ pointerEvents: editing && drawMode !== null ? "none" : "auto" }}
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
              stroke={boxColor}
              strokeWidth={active ? stroke * 2 : stroke}
              strokeDasharray={isPairSource ? `${stroke * 2} ${stroke}` : undefined}
              style={{ cursor: editing ? "move" : "pointer" }}
              onPointerDown={(e) => startBoxDrag(e, m.__srcIndex, "structure", [sx1, sy1, sx2, sy2])}
              onPointerMove={handleRectPointerMove}
              onPointerUp={handleRectPointerUp}
            />
            {editing && (
              <rect
                x={sx2 - handleSize / 2}
                y={sy2 - handleSize / 2}
                width={handleSize}
                height={handleSize}
                fill={boxColor}
                style={{ cursor: "nwse-resize" }}
                onPointerDown={(e) => startResizeDrag(e, m.__srcIndex, "structure", [sx1, sy1, sx2, sy2])}
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
                  stroke={LABEL_COLOR}
                  strokeWidth={active ? stroke * 2 : stroke}
                  style={{ cursor: editing ? "move" : "default" }}
                  onPointerDown={(e) =>
                    startBoxDrag(e, m.__srcIndex, "label", [label[0], label[1], label[2], label[3]])
                  }
                  onPointerMove={handleRectPointerMove}
                  onPointerUp={handleRectPointerUp}
                />
                {editing && (
                  <rect
                    x={label[2] - handleSize / 2}
                    y={label[3] - handleSize / 2}
                    width={handleSize}
                    height={handleSize}
                    fill={LABEL_COLOR}
                    style={{ cursor: "nwse-resize" }}
                    onPointerDown={(e) =>
                      startResizeDrag(e, m.__srcIndex, "label", [
                        label[0],
                        label[1],
                        label[2],
                        label[3],
                      ])
                    }
                    onPointerMove={handleRectPointerMove}
                    onPointerUp={handleRectPointerUp}
                  />
                )}
                <line
                  x1={(sx1 + sx2) / 2}
                  y1={(sy1 + sy2) / 2}
                  x2={(label[0] + label[2]) / 2}
                  y2={(label[1] + label[3]) / 2}
                  stroke="#f97316"
                  strokeWidth={stroke}
                  strokeDasharray={`${stroke * 3} ${stroke * 2}`}
                  /* Decorative: never let the connector swallow a press meant for a box handle. */
                  style={{ pointerEvents: "none" }}
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
          fill={drawMode === "label" ? "rgba(59,130,246,0.15)" : "rgba(34,197,94,0.15)"}
          stroke={drawMode === "label" ? LABEL_COLOR : STRUCTURE_COLOR}
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
  humanCorrection,
}: {
  artifactId: string;
  pageIndex: number;
  compounds: CompoundMention[];
  pageId: string;
  editable: boolean;
  /** Set once a human has signed these mentions off — same provenance CompoundGrid badges. */
  humanCorrection?: HumanCorrectionInfo | null;
}) {
  const [expanded, setExpanded] = useState(false);
  const [activeIndex, setActiveIndex] = useState<number | null>(null);
  const [natural, setNatural] = useState<{ w: number; h: number } | null>(null);
  const [editing, setEditing] = useState(false);
  const [working, setWorking] = useState<DraftMention[] | null>(null);
  const [drawMode, setDrawMode] = useState<DrawMode>(null);
  const [pairSource, setPairSource] = useState<number | null>(null);
  /** srcIndex open in the verify/correct dialog — SMILES and label text of one pair. */
  const [editIndex, setEditIndex] = useState<number | null>(null);
  /** The structure box currently being read by the models, as JSON — NOT an index. A cold
   *  call runs ~95s, in which a delete can shift every later index and move the spinner onto
   *  someone else's card; the box identifies the pair no matter how the array moves. One at a
   *  time: the first call in a server process loads DECIMER, and queueing five behind it
   *  helps nobody. */
  const [analyzingBox, setAnalyzingBox] = useState<string | null>(null);
  /** srcIndex whose Analyse button is armed to overwrite hand-typed values (second click). */
  const [confirmIndex, setConfirmIndex] = useState<number | null>(null);
  /** Bumped on every entry to and exit from edit mode. An in-flight analyse is never
   *  cancelled — leaving edit mode only nulls state — and `working` is rebuilt from the same
   *  `compounds` prop on re-entry, so the same index can hold the same box again with a
   *  hand-typed correction in it. Without a session identity that stale answer would pass the
   *  box check and overwrite the correction with no arm/confirm step. */
  const editSession = useRef(0);
  const { blobUrl, error } = useAuthBlobUrl(
    expanded ? `${API_URL}/artifacts/${artifactId}/pages/${pageIndex}/image?size=cser` : "",
  );
  const correct = useCorrectPageCompounds(pageId);
  const rerun = useRerunPageWorkflow(pageId);
  const analyze = useAnalyzeBox(pageId);

  // A page with no detections is the commonest — and most valuable — negative, so
  // a reviewer must still be able to open it and mark it reviewed-empty (or draw a
  // box the detector missed). Only the read-only view has nothing to show.
  if (compounds.length === 0 && !editable) return null;

  // While editing, the draft (`working`) is the source of truth for both the overlay
  // and the card grid below it; otherwise it's the loaded `compounds` as-is.
  const source: DraftMention[] = editing && working ? working : compounds;
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

  // Every correction here is a HUMAN assertion about what is printed on the page, and it
  // is only truthful about a page the human can actually see. With no render there is
  // nothing to see, so all FOUR write paths — approve, markEmpty, save, and entering edit
  // mode at all — are blind, and the empty one is a trap: "No compounds on this page" (or
  // a draft emptied card-by-card and saved, which is byte-identical) on a never-analysed
  // page exports that page as a confirmed negative — a sheet full of molecules teaching
  // the detector there is nothing there — and sets `human_corrections.compound_mentions`,
  // after which the extraction guard means a re-run can only re-render, never re-detect.
  // Blocked until the image is on screen; stated as text because browsers swallow `title`
  // on a disabled button.
  const blindReason = error
    ? "No page render — run compound extraction first; you can't confirm what you can't see."
    : !blobUrl
      ? "Waiting for the page render…"
      : null;

  /** All three write paths go through here purely so the panel says something afterwards.
   *  Approving is how machine output becomes ground truth and the only visible effect used to
   *  be a badge in a different component further up the page — indistinguishable from a dead
   *  button. Failures were just as silent, which is worse. Returns whether it stuck. */
  const submit = async (mentions: CorrectedCompoundInput[], done: string) => {
    try {
      await correct.mutateAsync({ compound_mentions: mentions });
      toast.success(done);
      return true;
    } catch (err) {
      toast.error("Could not save your review", { description: getErrorMessage(err) });
      return false;
    }
  };

  /** Which of the two out-of-edit-mode writes is in flight — readable from the body being
   *  sent, so the spinner lands on the button that was actually clicked with no extra state.
   *  (Approve is only rendered when there is something to approve, so an empty body is
   *  unambiguously "No compounds on this page".) */
  const markingEmpty = correct.isPending && correct.variables?.compound_mentions.length === 0;

  // Still the `compounds` prop, verbatim: the server's unchanged-vs-edited identity tuple
  // includes both boxes, and re-deriving it from the draft would discard detector provenance.
  const approve = () =>
    submit(compounds.map(toInput), "Approved — these annotations are now ground truth");

  const markEmpty = () =>
    submit([], "Recorded — this page is confirmed to have no compounds");

  const resetDraft = () => {
    setWorking(null);
    setDrawMode(null);
    setPairSource(null);
    setEditIndex(null);
    setAnalyzingBox(null);
    setConfirmIndex(null);
  };

  const toggleEditing = () => {
    editSession.current += 1;
    if (editing) {
      setEditing(false);
      resetDraft();
    } else {
      setEditing(true);
      setWorking(compounds.map((m) => ({ ...m })));
      // Warm the model while the human draws. Both boxes null loads DECIMER and returns
      // nulls; the first call in a server process costs ~94s and every later one ~0.5s, so
      // paying it now is what stops the first real Analyse from looking hung. Same blind
      // gate as every other server call here — no render, nothing to read, don't ask.
      if (!blindReason) analyze.mutate({ structure_bbox: null, label_bbox: null });
    }
  };

  /** Pairs the human drew (or re-analysed) that still have no SMILES. The user's rule is that
   *  a structure whose SMILES cannot be read is not stored at all — but "not stored" must
   *  never mean "quietly dropped on save", so these BLOCK the save instead of being filtered
   *  out of it. Blocking is the only option that cannot lose a drawn box without the human
   *  seeing it happen; the two ways out are both one click away on the card (type the SMILES,
   *  or delete the pair). */
  const unsaveable = working ? working.filter(isUnsaveable).length : 0;
  // Saving mid-analyse ends the editing session while a ~95s answer is still coming, which is
  // half of what makes a stale write-back reachable at all. Cheaper to just wait for it.
  const saveBlockedReason = analyzingBox
    ? "Reading a box with the models — Save unlocks when it finishes."
    : unsaveable
      ? `${unsaveable} drawn ${unsaveable === 1 ? "box has" : "boxes have"} no SMILES yet. Analyse ${unsaveable === 1 ? "it" : "them"}, type the SMILES in by hand, or delete ${unsaveable === 1 ? "it" : "them"} — nothing is saved until then, so no box is dropped behind your back.`
      : null;

  const save = async () => {
    // Guarded by the button's disabled state; re-checked because the render can disappear
    // while a draft lives on. `editing`/`working` are plain state and nothing resets them:
    // collapsing the card sets the blob URL argument to "" and drops `blobUrl` to null,
    // re-expanding does not unmount, and the per-card delete X is driven by `working`
    // alone — so a draft can be emptied and saved with no image on screen, which is the
    // same permanent false negative `markEmpty` is blocked from writing.
    // The unsaveable re-check is the same kind of guard: a pair can become SMILES-less
    // after the button was last rendered (a re-analyse that came back empty), and a blank
    // `smiles` would either be rejected by the server or stored as a compound that is not one.
    if (!working || blindReason || analyzingBox || working.some(isUnsaveable)) return;
    const n = working.length;
    const saved = await submit(
      working.map(toInput),
      `Saved — ${n} ${n === 1 ? "annotation is" : "annotations are"} now ground truth`,
    );
    // Keep the draft on failure: it is the only copy of the human's boxes.
    if (!saved) return;
    editSession.current += 1;
    setEditing(false);
    resetDraft();
  };

  /** Every committed box lands here, and only here, already normalised + clamped by
   *  `clampToImage` at the gesture end that produced it. */
  const setBox = (srcIndex: number, key: "structure_bbox" | "label_bbox", bbox: number[]) =>
    setWorking((prev) => prev && prev.map((m, i) => (i === srcIndex ? { ...m, [key]: bbox } : m)));

  const handleStructureChange = (srcIndex: number, bbox: number[]) =>
    setBox(srcIndex, "structure_bbox", bbox);

  const handleLabelChange = (srcIndex: number, bbox: number[]) =>
    setBox(srcIndex, "label_bbox", bbox);

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
    setEditIndex(null);
    setConfirmIndex(null);
  };

  /** Drop only the caption, keep the structure: `label_bbox: null` is a first-class
   *  annotation the training format allows, and a structure whose caption genuinely
   *  isn't printed on the page must be expressible without deleting the pair.
   *  The text goes with the box for the same reason the re-pair swap carries it —
   *  `extracted_id` is exported as `label_text`, the words inside that rectangle, so
   *  keeping it would ship a caption that owns no box. */
  const handleDeleteLabel = (srcIndex: number) =>
    setWorking(
      (prev) =>
        prev &&
        prev.map((m, i) => (i === srcIndex ? { ...m, label_bbox: null, extracted_id: null } : m)),
    );

  /** Drawing commits a box and nothing else — no dialog either way. The human's job is the
   *  geometry and the pairing; the SMILES comes from DECIMER and the label text from OCR,
   *  via Analyse. (Demanding a hand-typed SMILES at draw time asked for something nobody can
   *  do by eye for a real scaffold, which is what made drawing a structure unusable.) */
  const handleDraw = (bbox: number[]) => {
    if (drawMode === "label") {
      // Guarded by the button's disabled state; re-checked because state could have
      // moved between arming the mode and finishing the drag.
      if (pairSource !== null) setBox(pairSource, "label_bbox", bbox);
    } else {
      // Select the new pair as well, so "Add label" attaches to the box just drawn.
      const index = (working ?? []).length;
      setWorking((prev) => [...(prev ?? []), blankMention(bbox)]);
      setPairSource(index);
    }
    setDrawMode(null);
  };

  /**
   * Read one pair's boxes with the models. Fills `smiles` (DECIMER) and `extracted_id`
   * (OCR — exported as `label_text`), i.e. exactly the two things a human should verify
   * rather than transcribe.
   *
   * Hand-typed values are never overwritten on the first click: a pair the human corrected
   * arms the button instead, and only a second, explicit click re-runs. Silently replacing a
   * human correction with a machine guess would quietly undo the whole point of this screen,
   * and silently *keeping* it would strand a wrong hand-typed SMILES with no way back to the
   * model's answer.
   */
  const runAnalyse = async (srcIndex: number) => {
    const target = working?.[srcIndex];
    // Same gate as every other server call on this screen: no render, nothing to read.
    if (!target?.structure_bbox || blindReason || analyzingBox !== null) return;
    if (target.__human && confirmIndex !== srcIndex) {
      setConfirmIndex(srcIndex);
      return;
    }
    setConfirmIndex(null);
    const sent = target.structure_bbox;
    const sentLabel = target.label_bbox ?? null;
    const session = editSession.current;
    setAnalyzingBox(JSON.stringify(sent));
    try {
      const result = await analyze.mutateAsync({
        structure_bbox: sent,
        label_bbox: sentLabel,
      });
      // The draft this answer was asked for is gone (Cancel, or a Save that closed edit mode),
      // and the one on screen only looks identical. Drop it.
      if (session !== editSession.current) return;
      const smiles = result.smiles?.trim() ?? "";
      const labelText = result.label_text?.trim() || null;
      setWorking((prev) => {
        if (!prev) return prev;
        const current = prev[srcIndex];
        // A cold call runs ~95s; in that time the pair can be deleted (which shifts every
        // later index), re-drawn, or have either box dragged. Write back only if this slot
        // still holds BOTH boxes we asked about — a machine SMILES on the wrong molecule, or
        // OCR from the label box's old position, is worse than no answer.
        if (
          !current ||
          JSON.stringify(current.structure_bbox) !== JSON.stringify(sent) ||
          JSON.stringify(current.label_bbox ?? null) !== JSON.stringify(sentLabel)
        ) {
          return prev;
        }
        return prev.map((m, i) =>
          i === srcIndex
            ? {
                ...m,
                // Whatever was here described the box as it was; the answer for the box as
                // it is now is this one, empty or not. An empty one marks the pair
                // unsaveable rather than leaving a stale SMILES attached to moved corners.
                smiles,
                // Text belongs to the rectangle: no label box, no label text.
                extracted_id: m.label_bbox ? labelText : m.extracted_id,
                __human: false,
                __unreadable: !smiles,
              }
            : m,
        );
      });
    } catch (err) {
      // Same session test: a failure the reviewer already walked away from is not news, and
      // clearing the spinner would clear it for whatever the NEXT session has in flight.
      if (session === editSession.current) {
        toast.error("Could not analyse this box", { description: getErrorMessage(err) });
      }
    } finally {
      if (session === editSession.current) setAnalyzingBox(null);
    }
  };

  // "Add label" attaches to a selection, so it has two ways of being unavailable. Both
  // are rendered as text next to the button — a greyed-out button with no stated reason
  // reads as broken.
  const labelDrawBlocked =
    pairSource === null
      ? "Click a structure box first — the new label attaches to it."
      : source[pairSource]?.label_bbox
        ? "That structure already has a label box. Remove it first, or drag the existing one."
        : null;

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
            action={
              humanCorrection ? (
                <span className="ml-3 inline-flex items-center gap-1 text-xs text-text-muted">
                  <HumanCorrectedBadge info={humanCorrection} />
                  Reviewed
                </span>
              ) : undefined
            }
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
                      <Button
                        size="sm"
                        onClick={approve}
                        disabled={correct.isPending || blindReason !== null}
                      >
                        {correct.isPending && !markingEmpty && (
                          <Loader2 className="animate-spin" />
                        )}
                        {correct.isPending && !markingEmpty ? "Approving…" : "Approve as correct"}
                      </Button>
                    )}
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={toggleEditing}
                      disabled={blindReason !== null}
                    >
                      Edit boxes
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={markEmpty}
                      disabled={correct.isPending || blindReason !== null}
                    >
                      {markingEmpty && <Loader2 className="animate-spin" />}
                      {markingEmpty ? "Recording…" : "No compounds on this page"}
                    </Button>
                    {blindReason && (
                      <span className="text-xs text-text-muted">{blindReason}</span>
                    )}
                  </>
                ) : (
                  <>
                    <Button
                      size="sm"
                      onClick={save}
                      disabled={
                        correct.isPending || blindReason !== null || saveBlockedReason !== null
                      }
                    >
                      {correct.isPending && <Loader2 className="animate-spin" />}
                      {correct.isPending ? "Saving…" : "Save changes"}
                    </Button>
                    <Button
                      size="sm"
                      variant={drawMode === "structure" ? "default" : "outline"}
                      onClick={() => setDrawMode((v) => (v === "structure" ? null : "structure"))}
                      title="Drag a box around a structure — then click Analyse on its card to read the SMILES"
                    >
                      {drawMode === "structure" ? "Drawing structure — drag on image" : "Add structure"}
                    </Button>
                    <Button
                      size="sm"
                      variant={drawMode === "label" ? "default" : "outline"}
                      onClick={() => setDrawMode((v) => (v === "label" ? null : "label"))}
                      disabled={labelDrawBlocked !== null}
                      title={
                        labelDrawBlocked ??
                        "Drag the caption box for the selected structure — Analyse reads its text"
                      }
                    >
                      {drawMode === "label" ? "Drawing label — drag on image" : "Add label"}
                    </Button>
                    <Button size="sm" variant="ghost" onClick={toggleEditing} disabled={correct.isPending}>
                      Cancel editing
                    </Button>
                    {blindReason && (
                      <span className="text-xs text-text-muted">
                        {blindReason} Your edits are still here — nothing is lost.
                      </span>
                    )}
                    {labelDrawBlocked && (
                      <span className="text-xs text-text-muted">{labelDrawBlocked}</span>
                    )}
                    {saveBlockedReason && (
                      <span className={`text-xs ${unsaveable ? "text-ds-error" : "text-text-muted"}`}>
                        {saveBlockedReason}
                      </span>
                    )}
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
              /* The render is written by compound extraction (even when it finds nothing),
                 so "no render" means extraction never ran here. Telling the reviewer to
                 re-run it while the only control lives in a section they can't see from
                 here is a dead end — same mutation, same workflow name, put in reach. */
              <div className="space-y-2">
                <p className="text-sm text-text-muted">
                  No structure render stored for this page — compound extraction has not run
                  here yet.
                </p>
                <div className="flex flex-wrap items-center gap-2">
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => rerun.mutate("compound_extraction")}
                    disabled={rerun.isPending || rerun.isSuccess}
                  >
                    {rerun.isPending ? "Starting…" : "Run compound extraction"}
                  </Button>
                  <span className="text-xs text-text-muted">
                    {rerun.isSuccess
                      ? "Started. It runs in the background — reload this page in a minute to see the render."
                      : rerun.isError
                        ? "Could not start it. Try again from the Workflows section below."
                        : "Runs in the background; reload this page once it finishes."}
                  </span>
                </div>
              </div>
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
                      onLabelChange={handleLabelChange}
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
                {located.map((m, i) => {
                  const analysing = analyzingBox === JSON.stringify(m.structure_bbox);
                  const blocked = editing && isUnsaveable(m);
                  return (
                    <div
                      key={i}
                      onMouseEnter={() => setActiveIndex(i)}
                      onMouseLeave={() => setActiveIndex(null)}
                      className={`group/ann relative rounded-lg border p-3 transition-colors ${
                        blocked
                          ? "border-ds-error/60"
                          : activeIndex === i
                            ? "border-primary/50 bg-surface-elevated"
                            : "border-border-subtle"
                      }`}
                    >
                      {editing && (
                        <button
                          type="button"
                          aria-label="Delete this whole pair — structure and label"
                          title="Delete this whole pair — structure and label"
                          onClick={() => handleDelete(m.__srcIndex)}
                          className="absolute right-2 top-2 rounded-sm p-0.5 text-text-muted opacity-0 transition-opacity hover:text-ds-error group-hover/ann:opacity-100"
                        >
                          <X className="size-3.5" />
                        </button>
                      )}
                      {/* Only a pair that HAS a label box can have label text: the words belong to
                          the rectangle, so no rectangle means nothing to type. This is also the way
                          back in if the dialog was dismissed right after drawing the box. */}
                      {editing && m.label_bbox ? (
                        <button
                          type="button"
                          onClick={() => setEditIndex(m.__srcIndex)}
                          title="Verify or correct the words printed inside the label box"
                          className="text-left text-sm font-medium text-text-primary underline decoration-dotted underline-offset-4 hover:text-primary"
                        >
                          {m.extracted_id ?? "unlabelled"}
                        </button>
                      ) : (
                        <div className="text-sm font-medium text-text-primary">
                          {m.extracted_id ?? "unlabelled"}
                        </div>
                      )}
                      {/* In edit mode the SMILES is a way back into the dialog: the models read
                          it, the human verifies it, and correcting a misread is one click. */}
                      {editing ? (
                        <button
                          type="button"
                          onClick={() => setEditIndex(m.__srcIndex)}
                          title="Verify or correct the SMILES"
                          className={`mt-1 block break-all text-left font-mono text-xs underline decoration-dotted underline-offset-4 hover:text-primary ${
                            m.smiles ? "text-text-muted" : "text-ds-error"
                          }`}
                        >
                          {m.smiles || "no SMILES yet"}
                        </button>
                      ) : (
                        <div className="mt-1 break-all font-mono text-xs text-text-muted">
                          {m.smiles}
                        </div>
                      )}
                      <div className="mt-2 flex gap-3 text-xs text-text-muted">
                        {m.confidence != null && <span>match {(m.confidence * 100).toFixed(0)}%</span>}
                        {m.structure_confidence != null && (
                          <span>structure {(m.structure_confidence * 100).toFixed(0)}%</span>
                        )}
                        {m.label_confidence != null && (
                          <span>label {(m.label_confidence * 100).toFixed(0)}%</span>
                        )}
                      </div>
                      {editing && (
                        <div className="mt-2 flex flex-wrap items-center gap-2">
                          <Button
                            size="xs"
                            variant={m.smiles ? "ghost" : "outline"}
                            className={m.smiles ? "-ml-2 text-text-muted" : undefined}
                            onClick={() => runAnalyse(m.__srcIndex)}
                            disabled={analyzingBox !== null || blindReason !== null}
                            title={
                              blindReason ??
                              (analyzingBox !== null && !analysing
                                ? "Another box is being read — one at a time"
                                : m.__human
                                  ? "Re-read these boxes with the models, replacing what you typed"
                                  : "Read the SMILES (DECIMER) and the label text (OCR) out of these boxes")
                            }
                          >
                            {analysing && <Loader2 className="animate-spin" />}
                            {analysing
                              ? "Analysing…"
                              : confirmIndex === m.__srcIndex
                                ? "Discard your edits?"
                                : m.smiles
                                  ? "Re-analyse"
                                  : "Analyse"}
                          </Button>
                          {analysing && (
                            <span className="text-xs text-text-muted">
                              First one in a while can take ~90s — the model is loading.
                            </span>
                          )}
                          {!m.smiles && (
                            <Button
                              size="xs"
                              variant="ghost"
                              className="-ml-1 text-text-muted"
                              onClick={() => setEditIndex(m.__srcIndex)}
                              title="Type the SMILES yourself"
                            >
                              Enter SMILES by hand
                            </Button>
                          )}
                        </div>
                      )}
                      {/* The two states a drawn box can be stuck in, both said out loud at the
                          moment they happen rather than as a surprise at save time. */}
                      {editing && m.__unreadable && (
                        <p className="mt-2 text-xs text-ds-error">
                          No structure could be read here, so this pair cannot be saved — a
                          compound with no SMILES is not stored at all. Adjust the box and
                          re-analyse, type the SMILES by hand, or delete the pair (×, top right).
                        </p>
                      )}
                      {editing && !m.smiles && !m.__unreadable && (
                        <p className="mt-2 text-xs text-text-muted">
                          Not analysed yet — click Analyse to read the SMILES and label text.
                        </p>
                      )}
                      {editing && confirmIndex === m.__srcIndex && (
                        <p className="mt-2 text-xs text-ds-error">
                          You typed these values in by hand. Click again to replace them with what
                          the models read.
                        </p>
                      )}
                      {editing && m.label_bbox && !m.extracted_id && (
                        <p className="mt-2 text-xs text-ds-error">
                          Label box has no text — the relation matcher needs the words.
                        </p>
                      )}
                      {editing && m.label_bbox && (
                        <Button
                          size="xs"
                          variant="ghost"
                          className="mt-2 -ml-2 text-text-muted hover:text-ds-error"
                          onClick={() => handleDeleteLabel(m.__srcIndex)}
                          title="This structure has no printed caption — drop the label box, keep the structure"
                        >
                          Remove label box
                        </Button>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}
      </Card>

      {/* Verification, not data entry: drawing never opens this. It is where a human fixes
          what DECIMER or the OCR got wrong, and the only way to give a SMILES to a structure
          the models cannot read. `extracted_id` is its "Label" field and the exported
          `label_text`, so one editor covers both fields of a pair. */}
      {editable && (
        <EditCompoundDialog
          open={editIndex !== null}
          onOpenChange={(open) => {
            if (!open) setEditIndex(null);
          }}
          compound={editIndex !== null ? (working?.[editIndex] ?? null) : null}
          onSave={async (item) => {
            if (editIndex === null) return;
            const srcIndex = editIndex;
            setWorking(
              (prev) =>
                prev &&
                prev.map((m, i) =>
                  i === srcIndex
                    ? {
                        ...m,
                        smiles: item.smiles,
                        extracted_id: item.extracted_id ?? null,
                        internal_id: item.internal_id ?? null,
                        cdd_id: item.cdd_id ?? null,
                        chembl_id: item.chembl_id ?? null,
                        pdb_id: item.pdb_id ?? null,
                        // Typed by a human: Analyse now needs a second click to replace it,
                        // and the dialog cannot save an empty SMILES, so this clears the block.
                        __human: true,
                        __unreadable: false,
                      }
                    : m,
                ),
            );
            setEditIndex(null);
          }}
        />
      )}
    </>
  );
}
