from __future__ import annotations

import hashlib
from typing import BinaryIO

import fsspec

from application.ports.blob_store import BlobStore, StoredBlob


class FsspecBlobStore(BlobStore):
    def __init__(self, base_url: str, *, storage_options: dict | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.storage_options = storage_options or {}

    def _url(self, key: str) -> str:
        return f"{self.base_url}/{key}"

    def put_stream(self, key: str, stream: BinaryIO, *, mime_type: str | None = None) -> StoredBlob:
        url = self._url(key)

        h = hashlib.sha256()
        size = 0

        with fsspec.open(url, "wb", **self.storage_options) as out:
            while True:
                chunk = stream.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)
                h.update(chunk)
                size += len(chunk)

        return StoredBlob(key=key, size_bytes=size, sha256=h.hexdigest(), mime_type=mime_type)

    def get_bytes(self, key: str) -> bytes:
        with fsspec.open(self._url(key), "rb", **self.storage_options) as f:
            return f.read()

    def exists(self, key: str) -> bool:
        fs, path = fsspec.core.url_to_fs(self._url(key), **self.storage_options)
        return fs.exists(path)

    def delete(self, key: str) -> None:
        fs, path = fsspec.core.url_to_fs(self._url(key), **self.storage_options)
        fs.rm(path)
