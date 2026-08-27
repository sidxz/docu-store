"""Build a structflo-cser training bundle from human-reviewed pages.

The zip is laid out exactly as ``RelMatchDataset``'s ``data_dir``, so
``sf-train-relmatch --data-dir <unzipped>`` consumes it directly, and a YOLO
``data.yaml`` pointing at ``images/`` + ``labels/`` trains the detector.

Coordinates are copied out exactly as stored. The only arithmetic here is the
YOLO normalization, and it divides by the dimensions of the very PNG shipped
alongside it — there is no second source of truth for the render size.
"""

from __future__ import annotations

import json
import zipfile
from datetime import datetime
from io import BytesIO
from typing import TYPE_CHECKING
from uuid import UUID

from PIL import Image

from application.use_cases.storage_keys import cser_render_key

if TYPE_CHECKING:
    from application.ports.blob_store import BlobStore

STRUCTURE_CLASS = 0
LABEL_CLASS = 1


def yolo_line(class_id: int, box: list[int], width: int, height: int) -> str:
    """One YOLO annotation: ``class cx cy w h``, normalized to 0-1."""
    x1, y1, x2, y2 = box
    return (
        f"{class_id} "
        f"{((x1 + x2) / 2) / width:.6f} "
        f"{((y1 + y2) / 2) / height:.6f} "
        f"{(x2 - x1) / width:.6f} "
        f"{(y2 - y1) / height:.6f}"
    )


def build_cser_export_zip(
    pages: list[dict],
    blob_store: BlobStore,
    workspace_id: UUID,
    exported_at: datetime,
    artifact_filenames: dict[str, str | None] | None = None,
) -> bytes:
    """Assemble the training bundle.

    ``artifact_filenames`` maps ``artifact_id`` (str) -> the artifact's
    ``source_filename``. Page documents don't carry the filename themselves
    (only a display ``name`` like "Page 4"); the caller collects the distinct
    artifact ids from ``pages`` and looks the real filenames up on the
    artifact read model, keeping this function free of repository access.

    ponytail: builds the whole zip in memory. Fine to a few hundred pages; move
    to a Temporal job writing a blob if a workspace outgrows that.
    """
    artifact_filenames = artifact_filenames or {}
    buffer = BytesIO()
    manifest_pages: list[dict] = []
    skipped: list[dict] = []

    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for page in pages:
            page_id = page["page_id"]
            artifact_id = page["artifact_id"]
            render_key = cser_render_key(artifact_id, page["index"])

            if not blob_store.exists(render_key):
                # Extracted before renders were persisted. Re-running compound
                # extraction writes one, even for a human-corrected page.
                skipped.append({"page_id": page_id, "reason": "no CSER render stored"})
                continue

            image_bytes = blob_store.get_bytes(render_key)
            archive.writestr(f"images/{page_id}.png", image_bytes)
            with Image.open(BytesIO(image_bytes)) as image:
                width, height = image.size

            ground_truth: list[dict] = []
            yolo_lines: list[str] = []
            for mention in page.get("compound_mentions") or []:
                structure_box = mention.get("structure_bbox")
                if not structure_box:
                    continue  # extracted before coordinates existed
                label_box = mention.get("label_bbox")
                ground_truth.append(
                    {
                        "struct_bbox": structure_box,
                        "label_bbox": label_box,
                        "label_text": mention.get("extracted_id") or "",
                        "smiles": mention.get("smiles") or "",
                    }
                )
                yolo_lines.append(yolo_line(STRUCTURE_CLASS, structure_box, width, height))
                if label_box:
                    yolo_lines.append(yolo_line(LABEL_CLASS, label_box, width, height))

            # [] is meaningful: a page a human confirmed has no structures.
            archive.writestr(f"ground_truth/{page_id}.json", json.dumps(ground_truth, indent=2))
            if yolo_lines:
                # YOLO convention is no file rather than an empty one.
                archive.writestr(f"labels/{page_id}.txt", "\n".join(yolo_lines) + "\n")

            correction = (page.get("human_corrections") or {}).get("compound_mentions") or {}
            corrected_at = correction.get("corrected_at")
            manifest_pages.append(
                {
                    "page_id": page_id,
                    "artifact_id": artifact_id,
                    "page_index": page["index"],
                    "source_filename": artifact_filenames.get(artifact_id),
                    "corrected_by_id": correction.get("corrected_by_id"),
                    "corrected_by_name": correction.get("corrected_by_name"),
                    "corrected_at": corrected_at.isoformat()
                    if isinstance(corrected_at, datetime)
                    else corrected_at,
                    "pairs": len(ground_truth),
                    "image_size": [width, height],
                }
            )

        archive.writestr(
            "manifest.json",
            json.dumps(
                {
                    "workspace_id": str(workspace_id),
                    "exported_at": exported_at.isoformat(),
                    "format": "structflo-cser relmatch data_dir",
                    "pages": manifest_pages,
                    "skipped": skipped,
                },
                indent=2,
            ),
        )

    return buffer.getvalue()
