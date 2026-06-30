from types import SimpleNamespace
from uuid import uuid4

from application.use_cases.storage_keys import render_pdf_key
from domain.value_objects.mime_type import MimeType


def test_render_pdf_key_pdf_returns_source_location():
    art = SimpleNamespace(
        id=uuid4(), mime_type=MimeType.PDF, storage_location="artifacts/x/source.pdf"
    )
    assert render_pdf_key(art) == "artifacts/x/source.pdf"


def test_render_pdf_key_pptx_returns_derived_render_pdf():
    aid = uuid4()
    art = SimpleNamespace(
        id=aid, mime_type=MimeType.PPTX, storage_location="artifacts/x/source.pptx"
    )
    assert render_pdf_key(art) == f"artifacts/{aid}/derived/render.pdf"


def test_render_pdf_key_accepts_read_model_dto_shape():
    # ArtifactResponse (read model / API layer) exposes artifact_id, not id.
    aid = uuid4()
    dto = SimpleNamespace(
        artifact_id=aid, mime_type=MimeType.PPTX, storage_location="artifacts/x/source.pptx"
    )
    assert render_pdf_key(dto) == f"artifacts/{aid}/derived/render.pdf"
