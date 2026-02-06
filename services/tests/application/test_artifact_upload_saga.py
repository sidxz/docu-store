"""Tests for ArtifactUploadSaga."""

from __future__ import annotations

from io import BytesIO
from typing import Any
from uuid import uuid4

import pytest
from returns.result import Failure, Success

from application.dtos.artifact_dtos import ArtifactResponse
from application.dtos.blob_dtos import UploadBlobRequest, UploadBlobResponse
from application.dtos.errors import AppError
from application.sagas.artifact_upload_saga import ArtifactUploadSaga
from application.use_cases.artifact_use_cases import CreateArtifactUseCase
from domain.value_objects.artifact_type import ArtifactType
from domain.value_objects.mime_type import MimeType
from tests.mocks import MockArtifactRepository


class MockUploadBlobUseCase:
    """Mock implementation of UploadBlobUseCase for testing."""

    def __init__(self, success: bool = True, response: UploadBlobResponse | None = None) -> None:
        """Initialize the mock use case."""
        self.success = success
        self.response = response
        self.execute_called = False
        self.call_args: Any = None

    def execute(
        self, stream: Any, upload_req: UploadBlobRequest
    ) -> Success[UploadBlobResponse] | Failure[AppError]:
        """Execute blob upload."""
        self.execute_called = True
        self.call_args = (stream, upload_req)

        if self.success and self.response:
            return Success(self.response)

        error = AppError(category="infrastructure", message="Failed to upload blob")
        return Failure(error)


class TestArtifactUploadSaga:
    """Test ArtifactUploadSaga."""

    @pytest.mark.asyncio
    async def test_upload_saga_success(self) -> None:
        """Test successful artifact upload saga execution."""
        artifact_id = uuid4()
        blob_response = UploadBlobResponse(
            artifact_id=artifact_id,
            storage_key="/storage/artifacts/test.pdf",
            sha256="abc123def456",
            size_bytes=1024,
            mime_type="application/pdf",
            filename="test.pdf",
            source_uri="https://example.com/test.pdf",
        )

        # Setup mocks
        upload_blob_use_case = MockUploadBlobUseCase(success=True, response=blob_response)
        artifact_repo = MockArtifactRepository()
        create_artifact_use_case = CreateArtifactUseCase(artifact_repo)

        saga = ArtifactUploadSaga(upload_blob_use_case, create_artifact_use_case)

        # Execute saga
        upload_req = UploadBlobRequest(
            source_uri="https://example.com/test.pdf",
            artifact_type=ArtifactType.RESEARCH_ARTICLE,
            filename="test.pdf",
            mime_type="application/pdf",
        )

        stream = BytesIO(b"test data")
        result = await saga.execute(stream, upload_req)

        # Assertions
        assert isinstance(result, Success)
        response: ArtifactResponse = result.unwrap()
        # Note: The created artifact gets a new UUID, not the one from blob_response
        # because the CreateArtifactUseCase will generate or use its own
        assert response.source_uri == "https://example.com/test.pdf"
        assert response.source_filename == "test.pdf"
        assert response.artifact_type == ArtifactType.RESEARCH_ARTICLE
        assert response.mime_type == MimeType.PDF
        assert response.storage_location == "/storage/artifacts/test.pdf"
        assert upload_blob_use_case.execute_called is True
        assert artifact_repo.save_called is True

    @pytest.mark.asyncio
    async def test_upload_saga_blob_upload_fails(self) -> None:
        """Test saga when blob upload fails."""
        # Setup mocks - blob upload will fail
        upload_blob_use_case = MockUploadBlobUseCase(success=False)
        artifact_repo = MockArtifactRepository()
        create_artifact_use_case = CreateArtifactUseCase(artifact_repo)

        saga = ArtifactUploadSaga(upload_blob_use_case, create_artifact_use_case)

        # Execute saga
        upload_req = UploadBlobRequest(
            source_uri="https://example.com/test.pdf",
            artifact_type=ArtifactType.RESEARCH_ARTICLE,
            filename="test.pdf",
            mime_type="application/pdf",
        )

        stream = BytesIO(b"test data")
        result = await saga.execute(stream, upload_req)

        # Assertions - should fail at blob upload step
        assert isinstance(result, Failure)
        error = result.failure()
        assert error.category == "infrastructure"
        assert upload_blob_use_case.execute_called is True
        # Artifact should not be created since blob upload failed
        assert artifact_repo.save_called is False

    @pytest.mark.asyncio
    async def test_upload_saga_with_minimal_blob_response(self) -> None:
        """Test saga with minimal blob response data."""
        artifact_id = uuid4()
        blob_response = UploadBlobResponse(
            artifact_id=artifact_id,
            storage_key="/storage/artifacts/document",
            sha256="hash123",
            size_bytes=2048,
            mime_type="application/pdf",
            filename=None,  # Optional field
            source_uri=None,  # Optional field
        )

        upload_blob_use_case = MockUploadBlobUseCase(success=True, response=blob_response)
        artifact_repo = MockArtifactRepository()
        create_artifact_use_case = CreateArtifactUseCase(artifact_repo)

        saga = ArtifactUploadSaga(upload_blob_use_case, create_artifact_use_case)

        upload_req = UploadBlobRequest(
            source_uri=None,
            artifact_type=ArtifactType.UNCLASSIFIED,
            filename=None,
            mime_type="application/pdf",
        )

        stream = BytesIO(b"minimal test")
        result = await saga.execute(stream, upload_req)

        assert isinstance(result, Success)
        response: ArtifactResponse = result.unwrap()
        assert response.source_filename is None
        assert response.source_uri is None
        assert response.artifact_type == ArtifactType.UNCLASSIFIED

    @pytest.mark.asyncio
    async def test_upload_saga_preserves_upload_request_metadata(self) -> None:
        """Test that saga preserves metadata from upload request."""
        artifact_id = uuid4()
        blob_response = UploadBlobResponse(
            artifact_id=artifact_id,
            storage_key="/storage/test",
            sha256="hash",
            size_bytes=512,
            mime_type="application/vnd.ms-powerpoint",
            filename="data.ppt",
            source_uri="https://example.com/data.ppt",
        )

        upload_blob_use_case = MockUploadBlobUseCase(success=True, response=blob_response)
        artifact_repo = MockArtifactRepository()
        create_artifact_use_case = CreateArtifactUseCase(artifact_repo)

        saga = ArtifactUploadSaga(upload_blob_use_case, create_artifact_use_case)

        upload_req = UploadBlobRequest(
            source_uri="https://example.com/data.ppt",
            artifact_type=ArtifactType.SCIENTIFIC_PRESENTATION,  # This should be preserved
            filename="data.ppt",
            mime_type="application/vnd.ms-powerpoint",
        )

        stream = BytesIO(b"ppt data")
        result = await saga.execute(stream, upload_req)

        assert isinstance(result, Success)
        response: ArtifactResponse = result.unwrap()
        # The artifact_type from the upload request should be used
        assert response.artifact_type == ArtifactType.SCIENTIFIC_PRESENTATION

    @pytest.mark.asyncio
    async def test_upload_saga_calls_both_use_cases_in_order(self) -> None:
        """Test that saga calls use cases in the correct order."""
        artifact_id = uuid4()
        blob_response = UploadBlobResponse(
            artifact_id=artifact_id,
            storage_key="/storage/sequential.pdf",
            sha256="hash_seq",
            size_bytes=1024,
            mime_type="application/pdf",
            filename="sequential.pdf",
            source_uri="https://example.com/sequential.pdf",
        )

        upload_blob_use_case = MockUploadBlobUseCase(success=True, response=blob_response)
        artifact_repo = MockArtifactRepository()
        create_artifact_use_case = CreateArtifactUseCase(artifact_repo)

        saga = ArtifactUploadSaga(upload_blob_use_case, create_artifact_use_case)

        upload_req = UploadBlobRequest(
            source_uri="https://example.com/sequential.pdf",
            artifact_type=ArtifactType.RESEARCH_ARTICLE,
            filename="sequential.pdf",
            mime_type="application/pdf",
        )

        stream = BytesIO(b"sequential test")
        result = await saga.execute(stream, upload_req)

        assert isinstance(result, Success)
        # Verify blob upload was called with correct arguments
        assert upload_blob_use_case.execute_called is True
        assert upload_blob_use_case.call_args[1] == upload_req
        # Verify artifact was created and saved
        assert artifact_repo.save_called is True
