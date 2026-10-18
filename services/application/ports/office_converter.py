from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from domain.value_objects.mime_type import MimeType


class OfficeToPdfConverter(Protocol):
    """Converts an Office document (PPTX, DOCX, …) stored in the blob store into a
    PDF rendition, written back to the blob store at ``dest_storage_key``.

    Downstream PDF-readers (Docling parse, CSER, doc-metadata) then operate on that
    PDF, so every format flows through the one PDF pipeline.
    """

    def convert_to_pdf(
        self, source_storage_key: str, dest_storage_key: str, mime_type: MimeType
    ) -> None:
        """mime_type is the upload's verified type; the source is read only as that."""
