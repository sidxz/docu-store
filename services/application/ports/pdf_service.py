from typing import Protocol

from application.dtos.pdf_dtos import PDFContent


class PDFService(Protocol):
    def parse(self, storage_key: str) -> PDFContent:
        """Load a PDF from blob store and returns its text content."""
        ...
