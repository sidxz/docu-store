from __future__ import annotations

from dataclasses import dataclass
from typing import BinaryIO, Protocol


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
    def exists(self, key: str) -> bool: ...
    def delete(self, key: str) -> None: ...
