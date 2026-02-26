"""Shared test fixtures and configuration."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from domain.aggregates.artifact import Artifact
from domain.aggregates.page import Page
from domain.value_objects.artifact_type import ArtifactType
from domain.value_objects.compound_mention import CompoundMention
from domain.value_objects.mime_type import MimeType
from domain.value_objects.summary_candidate import SummaryCandidate
from domain.value_objects.tag_mention import TagMention
from domain.value_objects.text_mention import TextMention
from domain.value_objects.title_mention import TitleMention


@pytest.fixture
def sample_artifact_id() -> UUID:
    """Return a consistent sample artifact ID."""
    return uuid4()


@pytest.fixture
def sample_page_id() -> UUID:
    """Return a consistent sample page ID."""
    return uuid4()


@pytest.fixture
def sample_artifact() -> Artifact:
    """Create a sample Artifact aggregate for testing."""
    return Artifact.create(
        source_uri="https://example.com/paper.pdf",
        source_filename="research_paper.pdf",
        artifact_type=ArtifactType.RESEARCH_ARTICLE,
        mime_type=MimeType.PDF,
        storage_location="/storage/artifacts/paper123.pdf",
    )


@pytest.fixture
def sample_page(sample_artifact_id: UUID) -> Page:
    """Create a sample Page aggregate for testing."""
    return Page.create(
        name="Introduction",
        artifact_id=sample_artifact_id,
        index=0,
    )


@pytest.fixture
def sample_title_mention() -> TitleMention:
    """Create a sample TitleMention value object."""
    return TitleMention(
        title="Important Research",
        confidence=0.95,
    )


@pytest.fixture
def sample_summary_candidate() -> SummaryCandidate:
    """Create a sample SummaryCandidate value object."""
    return SummaryCandidate(
        summary="This paper discusses...",
        confidence=0.85,
    )


@pytest.fixture
def sample_compound_mention() -> CompoundMention:
    """Create a sample CompoundMention value object."""
    return CompoundMention(
        smiles="C1=CC=CC=C1",
        extracted_id="Benzene",
        confidence=0.92,
    )


@pytest.fixture
def sample_tag_mention() -> TagMention:
    """Create a sample TagMention value object."""
    return TagMention(
        tag="chemistry",
        confidence=0.88,
    )


@pytest.fixture
def sample_text_mention() -> TextMention:
    """Create a sample TextMention value object."""
    return TextMention(
        text="Notable result",
        confidence=0.90,
    )
