"""Tests for DTOs."""

from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from application.dtos.artifact_dtos import ArtifactResponse, CreateArtifactRequest
from application.dtos.page_dtos import CreatePageRequest, PageResponse
from domain.value_objects.artifact_type import ArtifactType
from domain.value_objects.mime_type import MimeType


class TestCreateArtifactRequest:
    """Test CreateArtifactRequest DTO."""

    def test_create_artifact_request_valid(self) -> None:
        """Test creating a valid CreateArtifactRequest."""
        request = CreateArtifactRequest(
            source_uri="https://example.com/paper.pdf",
            source_filename="paper.pdf",
            artifact_type=ArtifactType.RESEARCH_ARTICLE,
            mime_type=MimeType.PDF,
            storage_location="/storage/paper.pdf",
        )
        assert request.source_uri == "https://example.com/paper.pdf"
        assert request.source_filename == "paper.pdf"
        assert request.artifact_type == ArtifactType.RESEARCH_ARTICLE
        assert request.mime_type == MimeType.PDF
        assert request.storage_location == "/storage/paper.pdf"

    def test_create_artifact_request_missing_required_field(self) -> None:
        """Test that missing required field raises ValidationError."""
        with pytest.raises(ValidationError):
            CreateArtifactRequest(
                source_uri="https://example.com/paper.pdf",
                source_filename="paper.pdf",
                artifact_type=ArtifactType.RESEARCH_ARTICLE,
                mime_type=MimeType.PDF,
                # storage_location is missing
            )


class TestArtifactResponse:
    """Test ArtifactResponse DTO."""

    def test_artifact_response_creation(self) -> None:
        """Test creating an ArtifactResponse."""
        artifact_id = uuid4()
        response = ArtifactResponse(
            artifact_id=artifact_id,
            source_uri="https://example.com/paper.pdf",
            source_filename="paper.pdf",
            artifact_type=ArtifactType.RESEARCH_ARTICLE,
            mime_type=MimeType.PDF,
            storage_location="/storage/paper.pdf",
        )
        assert response.artifact_id == artifact_id
        assert response.pages == ()
        assert response.tags == []
        assert response.title_mention is None
        assert response.summary_candidate is None


class TestCreatePageRequest:
    """Test CreatePageRequest DTO."""

    def test_create_page_request_valid(self) -> None:
        """Test creating a valid CreatePageRequest."""
        artifact_id = uuid4()
        request = CreatePageRequest(
            artifact_id=artifact_id,
            name="Introduction",
            index=0,
        )
        assert request.artifact_id == artifact_id
        assert request.name == "Introduction"
        assert request.index == 0

    def test_create_page_request_default_index(self) -> None:
        """Test CreatePageRequest with default index."""
        artifact_id = uuid4()
        request = CreatePageRequest(
            artifact_id=artifact_id,
            name="Introduction",
        )
        assert request.index == 0

    def test_create_page_request_missing_required_field(self) -> None:
        """Test that missing required field raises ValidationError."""
        with pytest.raises(ValidationError):
            CreatePageRequest(
                artifact_id=uuid4(),
                # name is missing
            )


class TestPageResponse:
    """Test PageResponse DTO."""

    def test_page_response_creation(self) -> None:
        """Test creating a PageResponse."""
        page_id = uuid4()
        artifact_id = uuid4()
        response = PageResponse(
            page_id=page_id,
            artifact_id=artifact_id,
            name="Introduction",
            index=0,
            compound_mentions=[],
        )
        assert response.page_id == page_id
        assert response.artifact_id == artifact_id
        assert response.name == "Introduction"
        assert response.index == 0
        assert response.compound_mentions == []
        assert response.tag_mentions == []
        assert response.text_mention is None
        assert response.summary_candidate is None
