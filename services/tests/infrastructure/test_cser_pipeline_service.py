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


# ---------------------------------------------------------------------------
# analyze_boxes — human-drawn boxes, machine-read chemistry
# ---------------------------------------------------------------------------


class RenderBlobStore:
    """Serves one on-disk PNG as the page's CSER render."""

    def __init__(self, path: Path) -> None:
        self._path = path

    @contextlib.contextmanager
    def get_file(self, key: str):
        yield self._path


class RecordingPipeline:
    def __init__(self, smiles="CCO", text="1a") -> None:
        self.smiles_calls: list = []
        self.text_calls: list = []
        self._smiles = smiles
        self._text = text

    def extract_smiles(self, image, pair):
        self.smiles_calls.append(pair)
        return self._smiles

    def extract_text(self, image, pair):
        self.text_calls.append(pair)
        return self._text


def _service(tmp_path, pipeline, monkeypatch):
    render = tmp_path / "render.png"
    Image.new("RGB", (600, 800), "white").save(render)
    service = CserPipelineService(RenderBlobStore(render))
    service._pipeline = pipeline
    loaded = []
    monkeypatch.setattr(service, "_ensure_pipeline_loaded", lambda: loaded.append(True))
    return service, loaded


def test_structure_box_only_runs_ocsr_and_never_ocr(tmp_path, monkeypatch):
    pipeline = RecordingPipeline()
    service, _ = _service(tmp_path, pipeline, monkeypatch)

    smiles, label_text = service.analyze_boxes("k", [10, 20, 110, 220], None)

    assert (smiles, label_text) == ("CCO", None)
    assert len(pipeline.smiles_calls) == 1
    assert pipeline.text_calls == []
    # The box the human drew is what gets cropped.
    assert pipeline.smiles_calls[0].structure.bbox.as_list() == [10, 20, 110, 220]


def test_label_box_only_runs_ocr_and_never_ocsr(tmp_path, monkeypatch):
    pipeline = RecordingPipeline()
    service, _ = _service(tmp_path, pipeline, monkeypatch)

    smiles, label_text = service.analyze_boxes("k", None, [10, 230, 60, 250])

    assert (smiles, label_text) == (None, "1a")
    assert pipeline.smiles_calls == []
    assert pipeline.text_calls[0].label.bbox.as_list() == [10, 230, 60, 250]


def test_both_boxes_run_both_extractors(tmp_path, monkeypatch):
    pipeline = RecordingPipeline()
    service, _ = _service(tmp_path, pipeline, monkeypatch)

    assert service.analyze_boxes("k", [1, 2, 3, 4], [5, 6, 7, 8]) == ("CCO", "1a")
    assert len(pipeline.smiles_calls) == 1
    assert len(pipeline.text_calls) == 1


def test_no_boxes_is_a_warm_up_that_still_loads_the_pipeline(tmp_path, monkeypatch):
    # The client fires this when edit mode opens so the ~94 s DECIMER weight
    # load happens while the user is drawing. Deleting it is not an optimisation.
    pipeline = RecordingPipeline()
    service, loaded = _service(tmp_path, pipeline, monkeypatch)

    assert service.analyze_boxes("k", None, None) == (None, None)
    assert loaded == [True]
    assert pipeline.smiles_calls == []
    assert pipeline.text_calls == []


def test_unreadable_structure_yields_none_rather_than_raising(tmp_path, monkeypatch):
    pipeline = RecordingPipeline(smiles=None)
    service, _ = _service(tmp_path, pipeline, monkeypatch)

    assert service.analyze_boxes("k", [1, 2, 3, 4], None) == (None, None)
