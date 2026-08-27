"""CserPipelineService: persists the render, returns its pixel coordinates."""

from __future__ import annotations

import contextlib
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest
from PIL import Image

from application.use_cases.storage_keys import cser_render_key
from infrastructure.cser.cser_pipeline_service import CserPipelineService


class FakeBlobStore:
    def __init__(self) -> None:
        self.puts: dict[str, bytes] = {}

    @contextlib.contextmanager
    def get_file(self, key: str):
        yield Path("/tmp/does-not-matter.pdf")

    def put_stream(self, key: str, stream, *, mime_type: str | None = None):
        self.puts[key] = stream.read()
        return SimpleNamespace(key=key, size_bytes=len(self.puts[key]), sha256="", mime_type=mime_type)


def _pair(struct_box, label_box, *, smiles="CCO", label_text="1a"):
    return SimpleNamespace(
        structure=SimpleNamespace(bbox=SimpleNamespace(as_list=lambda: struct_box), conf=0.9123),
        label=SimpleNamespace(bbox=SimpleNamespace(as_list=lambda: label_box), conf=0.7654),
        smiles=smiles,
        label_text=label_text,
        match_confidence=0.88,
    )


def test_render_key_is_deterministic_and_sits_beside_the_page_png():
    artifact_id = UUID("11111111-1111-1111-1111-111111111111")
    assert cser_render_key(artifact_id, 4) == f"artifacts/{artifact_id}/pages/4_cser.png"


def test_extraction_persists_the_render_and_returns_its_pixel_boxes(monkeypatch):
    blob = FakeBlobStore()
    service = CserPipelineService(blob)
    image = Image.new("RGB", (1275, 1650), "white")
    fake_pipeline = SimpleNamespace(
        process_pdf_page=lambda path, index: SimpleNamespace(
            image=image,
            width=1275,
            height=1650,
            pairs=[_pair([10.4, 20.6, 110.2, 220.9], [10.1, 230.0, 60.7, 250.3])],
        )
    )
    service._pipeline = fake_pipeline  # skip the lazy weight load
    monkeypatch.setattr(service, "_ensure_pipeline_loaded", lambda: None)

    results = service.extract_compounds_from_pdf_page(
        storage_key="artifacts/a/source.pdf", page_index=0, render_key="renders/0_cser.png"
    )

    # The render is persisted, and it is a readable PNG of the expected size.
    assert "renders/0_cser.png" in blob.puts
    assert Image.open(BytesIO(blob.puts["renders/0_cser.png"])).size == (1275, 1650)

    # Boxes arrive as integer pixels of that render.
    assert results[0].structure_bbox == [10, 20, 110, 220]
    assert results[0].label_bbox == [10, 230, 60, 250]
    assert results[0].structure_confidence == pytest.approx(0.9123)
    assert results[0].label_confidence == pytest.approx(0.7654)
    assert results[0].smiles == "CCO"
    assert results[0].match_confidence == pytest.approx(0.88)


def test_render_page_only_writes_the_image_without_touching_the_pipeline(monkeypatch):
    blob = FakeBlobStore()
    service = CserPipelineService(blob)

    def explode() -> None:
        raise AssertionError("render_page_only must not load the ML pipeline")

    monkeypatch.setattr(service, "_ensure_pipeline_loaded", explode)
    monkeypatch.setattr(
        "infrastructure.cser.cser_pipeline_service.render_page",
        lambda path, index, **kw: Image.new("RGB", (1275, 1650), "white"),
    )

    service.render_page_only(
        storage_key="artifacts/a/source.pdf", page_index=3, render_key="renders/3_cser.png"
    )

    assert Image.open(BytesIO(blob.puts["renders/3_cser.png"])).size == (1275, 1650)
