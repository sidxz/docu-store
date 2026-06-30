"""Storage-key helpers shared across use cases."""

from __future__ import annotations

from typing import TYPE_CHECKING

from domain.value_objects.mime_type import MimeType

if TYPE_CHECKING:
    from domain.aggregates.artifact import Artifact


def render_pdf_key(artifact: Artifact) -> str:
    """Blob key of the PDF representation downstream PDF-readers (parse, CSER,
    doc-metadata) should open.

    Native PDFs render from their source. Office formats (PPTX, …) are converted
    to a derived PDF at a deterministic key during the parse workflow.
    """
    if artifact.mime_type == MimeType.PDF:
        return artifact.storage_location
    # Domain aggregate exposes .id; the read-model / API DTO exposes .artifact_id.
    artifact_id = getattr(artifact, "id", None) or artifact.artifact_id
    return f"artifacts/{artifact_id}/derived/render.pdf"
