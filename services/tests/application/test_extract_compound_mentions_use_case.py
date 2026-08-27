"""ExtractCompoundMentionsUseCase: coordinates through, no inference on corrected pages."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from returns.result import Success

from application.dtos.cser_dtos import CserCompoundResult
from application.use_cases.compound_use_cases import ExtractCompoundMentionsUseCase
from domain.value_objects.mime_type import MimeType


class FakeCser:
    def __init__(self, results=()) -> None:
        self.results = list(results)
        self.extract_calls: list[dict] = []
        self.render_calls: list[dict] = []

    def extract_compounds_from_pdf_page(self, storage_key, page_index, render_key):
        self.extract_calls.append(
            {"storage_key": storage_key, "page_index": page_index, "render_key": render_key}
        )
        return self.results

    def render_page_only(self, storage_key, page_index, render_key) -> None:
        self.render_calls.append(
            {"storage_key": storage_key, "page_index": page_index, "render_key": render_key}
        )


class FakeValidator:
    def validate(self, smiles: str) -> bool:
        return True

    def canonicalize(self, smiles: str) -> str:
        return smiles


class FakePage:
    def __init__(self, artifact_id: UUID, *, corrected: bool = False) -> None:
        self.id = uuid4()
        self.artifact_id = artifact_id
        self.index = 3
        self.human_corrections = {"compound_mentions": {}} if corrected else {}
        self.compound_mentions: list = []
        self.updated_with: list | None = None

    def update_compound_mentions(self, mentions) -> None:
        self.updated_with = mentions
        self.compound_mentions = mentions


class FakeRepo:
    def __init__(self, obj) -> None:
        self.obj = obj
        self.saved = 0

    def get_by_id(self, _id):
        return self.obj

    def save(self, _obj) -> None:
        self.saved += 1


@pytest.fixture
def artifact():
    return SimpleNamespace(
        id=UUID("22222222-2222-2222-2222-222222222222"),
        mime_type=MimeType.PDF,
        storage_location="artifacts/src.pdf",
    )


def _use_case(page, artifact, cser):
    return ExtractCompoundMentionsUseCase(
        page_repository=FakeRepo(page),
        artifact_repository=FakeRepo(artifact),
        cser_service=cser,
        smiles_validator=FakeValidator(),
    )


@pytest.mark.asyncio
async def test_coordinates_reach_the_compound_mention(artifact, monkeypatch):
    page = FakePage(artifact.id)
    cser = FakeCser(
        [
            CserCompoundResult(
                smiles="CCO",
                label_text="1a",
                match_confidence=0.8,
                structure_bbox=[10, 20, 110, 220],
                label_bbox=[10, 230, 60, 250],
                structure_confidence=0.91,
                label_confidence=0.77,
            )
        ]
    )
    monkeypatch.setattr(
        "application.use_cases.compound_use_cases.PageMapper.to_page_response",
        lambda p: SimpleNamespace(artifact_id=p.artifact_id),
    )

    result = await _use_case(page, artifact, cser).execute(page.id)

    assert isinstance(result, Success)
    mention = page.updated_with[0]
    assert mention.structure_bbox == [10, 20, 110, 220]
    assert mention.label_bbox == [10, 230, 60, 250]
    assert mention.structure_confidence == 0.91
    assert mention.label_confidence == 0.77
    # The render lands beside the docling page image, for page index 3.
    assert cser.extract_calls[0]["render_key"] == f"artifacts/{artifact.id}/pages/3_cser.png"


@pytest.mark.asyncio
async def test_human_corrected_page_gets_its_render_but_no_inference(artifact, monkeypatch):
    page = FakePage(artifact.id, corrected=True)
    cser = FakeCser()
    monkeypatch.setattr(
        "application.use_cases.compound_use_cases.PageMapper.to_page_response",
        lambda p: SimpleNamespace(artifact_id=p.artifact_id),
    )

    result = await _use_case(page, artifact, cser).execute(page.id)

    assert isinstance(result, Success)
    assert cser.extract_calls == []  # the expensive part never ran
    assert cser.render_calls[0]["render_key"] == f"artifacts/{artifact.id}/pages/3_cser.png"
    assert page.updated_with is None  # the human's mentions are untouched
