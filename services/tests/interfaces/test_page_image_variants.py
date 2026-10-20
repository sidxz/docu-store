"""?size=cser serves the render compound coordinates refer to — or 404s."""

from __future__ import annotations

from uuid import UUID

import pytest
from fastapi import HTTPException

ARTIFACT_ID = UUID("33333333-3333-3333-3333-333333333333")
WS = UUID("44444444-4444-4444-4444-444444444444")
OTHER_WS = UUID("55555555-5555-5555-5555-555555555555")
FOLDER = f"workspaces/{WS}/artifacts/{ARTIFACT_ID}"


class FakeBlobStore:
    def __init__(self, keys: dict[str, bytes]) -> None:
        self.keys = keys

    def exists(self, key: str) -> bool:
        return key in self.keys

    def get_bytes(self, key: str) -> bytes:
        return self.keys[key]


def _resolve(blob_store, size, workspace_id=WS):
    """Mirror of the route's variant selection, exercised directly."""
    from interfaces.api.routes.artifact_routes import resolve_page_image

    return resolve_page_image(blob_store, workspace_id, ARTIFACT_ID, 2, size)


def test_cser_variant_serves_the_cser_render():
    blob = FakeBlobStore(
        {f"{FOLDER}/pages/2_cser.png": b"PNGDATA", f"{FOLDER}/pages/2.png": b"DOCLING"}
    )

    content, media_type = _resolve(blob, "cser")

    assert content == b"PNGDATA"
    assert media_type == "image/png"


def test_cser_variant_404s_rather_than_serving_the_docling_render():
    # Falling back would draw stored boxes on a differently-scaled image.
    blob = FakeBlobStore({f"{FOLDER}/pages/2.png": b"DOCLING"})

    with pytest.raises(HTTPException) as excinfo:
        _resolve(blob, "cser")

    assert excinfo.value.status_code == 404


def test_default_variant_still_serves_the_docling_render():
    blob = FakeBlobStore({f"{FOLDER}/pages/2.png": b"DOCLING"})

    content, media_type = _resolve(blob, None)

    assert content == b"DOCLING"
    assert media_type == "image/png"


def test_thumb_variant_serves_the_thumbnail():
    blob = FakeBlobStore(
        {f"{FOLDER}/pages/2_thumb.jpg": b"JPEG", f"{FOLDER}/pages/2.png": b"DOCLING"}
    )

    content, media_type = _resolve(blob, "thumb")

    assert content == b"JPEG"
    assert media_type == "image/jpeg"


def test_page_image_lookup_uses_the_callers_workspace():
    # The same artifact id under another workspace's folder is not reachable.
    blob = FakeBlobStore({f"{FOLDER}/pages/2.png": b"DOCLING"})

    with pytest.raises(HTTPException) as excinfo:
        _resolve(blob, None, workspace_id=OTHER_WS)

    assert excinfo.value.status_code == 404
