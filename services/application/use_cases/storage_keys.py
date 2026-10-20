"""Storage-key helpers shared across use cases.

Every file a document produces lives in one folder inside its workspace:
``workspaces/{workspace_id}/artifacts/{artifact_id}/``. A workspace's disk use
is then the size of its folder, and removing a document is one folder delete.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from domain.value_objects.mime_type import MimeType

if TYPE_CHECKING:
    from uuid import UUID

    from domain.aggregates.artifact import Artifact


def workspace_prefix(workspace_id: UUID | str | None) -> str:
    """Folder holding every file of one workspace."""
    if not workspace_id:
        msg = "blob keys need a workspace"
        raise ValueError(msg)
    return f"workspaces/{workspace_id}"


def artifact_prefix(workspace_id: UUID | str | None, artifact_id: UUID | str) -> str:
    """Folder holding every file of one document."""
    return f"{workspace_prefix(workspace_id)}/artifacts/{artifact_id}"


def source_key(workspace_id: UUID | str | None, artifact_id: UUID | str, extension: str) -> str:
    """The uploaded file itself; ``extension`` includes the dot (``".pdf"``)."""
    return f"{artifact_prefix(workspace_id, artifact_id)}/source{extension}"


def page_image_key(
    workspace_id: UUID | str | None, artifact_id: UUID | str, page_index: int
) -> str:
    return f"{artifact_prefix(workspace_id, artifact_id)}/pages/{page_index}.png"


def page_thumb_key(
    workspace_id: UUID | str | None, artifact_id: UUID | str, page_index: int
) -> str:
    return f"{artifact_prefix(workspace_id, artifact_id)}/pages/{page_index}_thumb.jpg"


def parsed_document_key(workspace_id: UUID | str | None, artifact_id: UUID | str) -> str:
    return f"{artifact_prefix(workspace_id, artifact_id)}/parsed/document.json"


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
    return f"{artifact_prefix(artifact.workspace_id, artifact_id)}/derived/render.pdf"


def cser_render_key(
    workspace_id: UUID | str | None, artifact_id: UUID | str, page_index: int
) -> str:
    """Blob key of the image the CSER pipeline saw for this page.

    Sits beside the docling page render (``pages/{i}.png``) and its thumbnail.
    Every stored compound bounding box is in THIS image's pixel coordinates, so
    it is written whenever extraction runs and is never regenerated at a
    different scale.
    """
    return f"{artifact_prefix(workspace_id, artifact_id)}/pages/{page_index}_cser.png"
