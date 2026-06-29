from __future__ import annotations

from typing import Protocol

from application.dtos.parsed_document import ParseResult


class DocumentParser(Protocol):
    def parse(self, storage_key: str) -> ParseResult:
        """Parse a blob into a structured ParsedDocument + rendered page images."""
        ...
