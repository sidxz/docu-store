from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, BinaryIO, Protocol

if TYPE_CHECKING:
    from contextlib import AbstractContextManager
    from pathlib import Path


@dataclass(frozen=True)
class StoredBlob:
    key: str
    size_bytes: int
    sha256: str
    mime_type: str | None


class BlobStore(Protocol):
    def put_stream(
        self,
        key: str,
        stream: BinaryIO,
        *,
        mime_type: str | None = None,
    ) -> StoredBlob: ...
    def get_bytes(self, key: str) -> bytes: ...
    def get_stream(self, key: str) -> BinaryIO: ...
    def get_file(self, key: str) -> AbstractContextManager[Path]:
        """Context manager that provides a local file path for the blob.

        Useful for tools that require a file path. Handles cleanup of temp files.
        Yields a Path that is valid within the context manager.
        """
        ...

    def exists(self, key: str) -> bool: ...
    def delete(self, key: str) -> None: ...
