from types import SimpleNamespace
from uuid import uuid4

import pytest

from application.use_cases.storage_keys import (
    artifact_prefix,
    cser_render_key,
    page_image_key,
    page_thumb_key,
    parsed_document_key,
    render_pdf_key,
    source_key,
    workspace_prefix,
)
from domain.value_objects.mime_type import MimeType

WS, AID = uuid4(), uuid4()
BASE = f"workspaces/{WS}/artifacts/{AID}"


def test_artifact_prefix_is_inside_the_workspace_folder():
    assert workspace_prefix(WS) == f"workspaces/{WS}"
    assert artifact_prefix(WS, AID) == BASE


def test_every_derived_key_lives_in_the_artifact_folder():
    assert source_key(WS, AID, ".pdf") == f"{BASE}/source.pdf"
    assert page_image_key(WS, AID, 3) == f"{BASE}/pages/3.png"
    assert page_thumb_key(WS, AID, 3) == f"{BASE}/pages/3_thumb.jpg"
    assert cser_render_key(WS, AID, 3) == f"{BASE}/pages/3_cser.png"
    assert parsed_document_key(WS, AID) == f"{BASE}/parsed/document.json"


def test_render_pdf_key_pdf_returns_source_location():
    art = SimpleNamespace(
        id=AID, workspace_id=WS, mime_type=MimeType.PDF, storage_location=f"{BASE}/source.pdf"
    )
    assert render_pdf_key(art) == f"{BASE}/source.pdf"


def test_render_pdf_key_office_returns_derived_pdf_in_the_folder():
    art = SimpleNamespace(
        id=AID, workspace_id=WS, mime_type=MimeType.PPTX, storage_location=f"{BASE}/source.pptx"
    )
    assert render_pdf_key(art) == f"{BASE}/derived/render.pdf"


def test_render_pdf_key_accepts_read_model_dto_shape():
    # ArtifactResponse (read model / API layer) exposes artifact_id, not id.
    dto = SimpleNamespace(
        artifact_id=AID,
        workspace_id=WS,
        mime_type=MimeType.DOCX,
        storage_location=f"{BASE}/source.docx",
    )
    assert render_pdf_key(dto) == f"{BASE}/derived/render.pdf"


def test_keys_refuse_a_missing_workspace():
    with pytest.raises(ValueError, match="workspace"):
        page_image_key(None, AID, 0)
