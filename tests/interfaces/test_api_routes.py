"""Tests for API routes."""

from __future__ import annotations

from uuid import uuid4

import pytest

from domain.value_objects.artifact_type import ArtifactType
from domain.value_objects.mime_type import MimeType


@pytest.fixture
def client():
    """Create a test client for the API."""
    try:
        from fastapi.testclient import TestClient

        from interfaces.api.main import app

        return TestClient(app)
    except ImportError:
        # If FastAPI app not available, return None and skip tests
        return None


class TestArtifactRoutes:
    """Test artifact API routes."""

    @pytest.mark.skip(reason="API not fully implemented yet")
    def test_create_artifact_success(self, client) -> None:
        """Test successfully creating an artifact via API."""
        if client is None:
            pytest.skip("API client not available")

        request_data = {
            "source_uri": "https://example.com/paper.pdf",
            "source_filename": "paper.pdf",
            "artifact_type": ArtifactType.RESEARCH_ARTICLE,
            "mime_type": MimeType.PDF,
            "storage_location": "/storage/paper.pdf",
        }

        response = client.post("/artifacts/", json=request_data)

        assert response.status_code == 201
        data = response.json()
        assert data["source_uri"] == "https://example.com/paper.pdf"
        assert data["source_filename"] == "paper.pdf"
        assert "artifact_id" in data

    @pytest.mark.skip(reason="API not fully implemented yet")
    def test_create_artifact_validation_error(self, client) -> None:
        """Test creating artifact with invalid data."""
        if client is None:
            pytest.skip("API client not available")

        request_data = {
            "source_uri": "",  # Invalid: empty
            "source_filename": "paper.pdf",
            "artifact_type": ArtifactType.RESEARCH_ARTICLE,
            "mime_type": MimeType.PDF,
            "storage_location": "/storage/paper.pdf",
        }

        response = client.post("/artifacts/", json=request_data)

        assert response.status_code == 400

    @pytest.mark.skip(reason="API not fully implemented yet")
    def test_create_artifact_missing_field(self, client) -> None:
        """Test creating artifact with missing required field."""
        if client is None:
            pytest.skip("API client not available")

        request_data = {
            "source_uri": "https://example.com/paper.pdf",
            "source_filename": "paper.pdf",
            # artifact_type is missing
            "mime_type": MimeType.PDF,
            "storage_location": "/storage/paper.pdf",
        }

        response = client.post("/artifacts/", json=request_data)

        assert response.status_code == 422  # Unprocessable Entity

    @pytest.mark.skip(reason="API not fully implemented yet")
    def test_get_artifact_success(self, client) -> None:
        """Test retrieving an artifact."""
        if client is None:
            pytest.skip("API client not available")

        # First create an artifact
        create_request = {
            "source_uri": "https://example.com/paper.pdf",
            "source_filename": "paper.pdf",
            "artifact_type": ArtifactType.RESEARCH_ARTICLE,
            "mime_type": MimeType.PDF,
            "storage_location": "/storage/paper.pdf",
        }
        create_response = client.post("/artifacts/", json=create_request)
        artifact_id = create_response.json()["artifact_id"]

        # Retrieve the artifact
        response = client.get(f"/artifacts/{artifact_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["artifact_id"] == artifact_id
        assert data["source_filename"] == "paper.pdf"

    @pytest.mark.skip(reason="API not fully implemented yet")
    def test_get_artifact_not_found(self, client) -> None:
        """Test retrieving a non-existent artifact."""
        if client is None:
            pytest.skip("API client not available")

        non_existent_id = str(uuid4())
        response = client.get(f"/artifacts/{non_existent_id}")

        assert response.status_code == 404

    @pytest.mark.skip(reason="API not fully implemented yet")
    def test_list_artifacts(self, client) -> None:
        """Test listing artifacts."""
        if client is None:
            pytest.skip("API client not available")

        # Create multiple artifacts
        for i in range(3):
            request_data = {
                "source_uri": f"https://example.com/paper_{i}.pdf",
                "source_filename": f"paper_{i}.pdf",
                "artifact_type": ArtifactType.RESEARCH_ARTICLE,
                "mime_type": MimeType.PDF,
                "storage_location": f"/storage/paper_{i}.pdf",
            }
            client.post("/artifacts/", json=request_data)

        # List artifacts
        response = client.get("/artifacts/?skip=0&limit=10")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 3

    @pytest.mark.skip(reason="API not fully implemented yet")
    def test_list_artifacts_pagination(self, client) -> None:
        """Test pagination when listing artifacts."""
        if client is None:
            pytest.skip("API client not available")

        response = client.get("/artifacts/?skip=0&limit=5")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    @pytest.mark.skip(reason="API not fully implemented yet")
    def test_update_artifact_title_mention(self, client) -> None:
        """Test updating artifact title mention."""
        if client is None:
            pytest.skip("API client not available")

        # Create artifact
        create_request = {
            "source_uri": "https://example.com/paper.pdf",
            "source_filename": "paper.pdf",
            "artifact_type": ArtifactType.RESEARCH_ARTICLE,
            "mime_type": MimeType.PDF,
            "storage_location": "/storage/paper.pdf",
        }
        create_response = client.post("/artifacts/", json=create_request)
        artifact_id = create_response.json()["artifact_id"]

        # Update title mention
        update_request = {
            "mention": "Important Research Paper",
            "page_number": 1,
            "confidence": 0.95,
        }
        response = client.put(
            f"/artifacts/{artifact_id}/title_mention",
            json=update_request,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["title_mention"]["mention"] == "Important Research Paper"

    @pytest.mark.skip(reason="API not fully implemented yet")
    def test_update_artifact_tags(self, client) -> None:
        """Test updating artifact tags."""
        if client is None:
            pytest.skip("API client not available")

        # Create artifact
        create_request = {
            "source_uri": "https://example.com/paper.pdf",
            "source_filename": "paper.pdf",
            "artifact_type": ArtifactType.RESEARCH_ARTICLE,
            "mime_type": MimeType.PDF,
            "storage_location": "/storage/paper.pdf",
        }
        create_response = client.post("/artifacts/", json=create_request)
        artifact_id = create_response.json()["artifact_id"]

        # Update tags
        update_request = {"tags": ["chemistry", "research"]}
        response = client.put(f"/artifacts/{artifact_id}/tags", json=update_request)

        assert response.status_code == 200
        data = response.json()
        assert "chemistry" in data["tags"]
        assert "research" in data["tags"]

    @pytest.mark.skip(reason="API not fully implemented yet")
    def test_delete_artifact(self, client) -> None:
        """Test deleting an artifact."""
        if client is None:
            pytest.skip("API client not available")

        # Create artifact
        create_request = {
            "source_uri": "https://example.com/paper.pdf",
            "source_filename": "paper.pdf",
            "artifact_type": ArtifactType.RESEARCH_ARTICLE,
            "mime_type": MimeType.PDF,
            "storage_location": "/storage/paper.pdf",
        }
        create_response = client.post("/artifacts/", json=create_request)
        artifact_id = create_response.json()["artifact_id"]

        # Delete the artifact
        response = client.delete(f"/artifacts/{artifact_id}")

        assert response.status_code == 204

        # Verify it's deleted
        response = client.get(f"/artifacts/{artifact_id}")
        assert response.status_code == 404


class TestPageRoutes:
    """Test page API routes."""

    @pytest.mark.skip(reason="API not fully implemented yet")
    def test_create_page_success(self, client) -> None:
        """Test successfully creating a page."""
        if client is None:
            pytest.skip("API client not available")

        # First create an artifact
        artifact_request = {
            "source_uri": "https://example.com/paper.pdf",
            "source_filename": "paper.pdf",
            "artifact_type": ArtifactType.RESEARCH_ARTICLE,
            "mime_type": MimeType.PDF,
            "storage_location": "/storage/paper.pdf",
        }
        artifact_response = client.post("/artifacts/", json=artifact_request)
        artifact_id = artifact_response.json()["artifact_id"]

        # Create a page
        page_request = {
            "artifact_id": artifact_id,
            "name": "Introduction",
            "index": 0,
        }
        response = client.post("/pages/", json=page_request)

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Introduction"
        assert data["index"] == 0
        assert "page_id" in data

    @pytest.mark.skip(reason="API not fully implemented yet")
    def test_create_page_missing_artifact(self, client) -> None:
        """Test creating a page for non-existent artifact."""
        if client is None:
            pytest.skip("API client not available")

        page_request = {
            "artifact_id": str(uuid4()),  # Non-existent artifact
            "name": "Introduction",
        }
        response = client.post("/pages/", json=page_request)

        assert response.status_code == 404

    @pytest.mark.skip(reason="API not fully implemented yet")
    def test_get_page_success(self, client) -> None:
        """Test retrieving a page."""
        if client is None:
            pytest.skip("API client not available")

        # Create artifact and page
        artifact_request = {
            "source_uri": "https://example.com/paper.pdf",
            "source_filename": "paper.pdf",
            "artifact_type": ArtifactType.RESEARCH_ARTICLE,
            "mime_type": MimeType.PDF,
            "storage_location": "/storage/paper.pdf",
        }
        artifact_response = client.post("/artifacts/", json=artifact_request)
        artifact_id = artifact_response.json()["artifact_id"]

        page_request = {
            "artifact_id": artifact_id,
            "name": "Introduction",
        }
        page_response = client.post("/pages/", json=page_request)
        page_id = page_response.json()["page_id"]

        # Retrieve the page
        response = client.get(f"/pages/{page_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["page_id"] == page_id
        assert data["name"] == "Introduction"

    @pytest.mark.skip(reason="API not fully implemented yet")
    def test_get_page_not_found(self, client) -> None:
        """Test retrieving a non-existent page."""
        if client is None:
            pytest.skip("API client not available")

        non_existent_id = str(uuid4())
        response = client.get(f"/pages/{non_existent_id}")

        assert response.status_code == 404

    @pytest.mark.skip(reason="API not fully implemented yet")
    def test_update_page_compound_mentions(self, client) -> None:
        """Test updating page compound mentions."""
        if client is None:
            pytest.skip("API client not available")

        # Setup: create artifact and page
        artifact_request = {
            "source_uri": "https://example.com/paper.pdf",
            "source_filename": "paper.pdf",
            "artifact_type": ArtifactType.RESEARCH_ARTICLE,
            "mime_type": MimeType.PDF,
            "storage_location": "/storage/paper.pdf",
        }
        artifact_response = client.post("/artifacts/", json=artifact_request)
        artifact_id = artifact_response.json()["artifact_id"]

        page_request = {
            "artifact_id": artifact_id,
            "name": "Introduction",
        }
        page_response = client.post("/pages/", json=page_request)
        page_id = page_response.json()["page_id"]

        # Update compound mentions
        update_request = {
            "compound_mentions": [
                {
                    "smiles": "C1=CC=CC=C1",
                    "extracted_name": "Benzene",
                    "extraction_metadata": {"page_number": 1, "confidence": 0.92},
                },
            ],
        }
        response = client.put(
            f"/pages/{page_id}/compound_mentions",
            json=update_request,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["compound_mentions"]) > 0

    @pytest.mark.skip(reason="API not fully implemented yet")
    def test_delete_page(self, client) -> None:
        """Test deleting a page."""
        if client is None:
            pytest.skip("API client not available")

        # Create artifact and page
        artifact_request = {
            "source_uri": "https://example.com/paper.pdf",
            "source_filename": "paper.pdf",
            "artifact_type": ArtifactType.RESEARCH_ARTICLE,
            "mime_type": MimeType.PDF,
            "storage_location": "/storage/paper.pdf",
        }
        artifact_response = client.post("/artifacts/", json=artifact_request)
        artifact_id = artifact_response.json()["artifact_id"]

        page_request = {
            "artifact_id": artifact_id,
            "name": "Introduction",
        }
        page_response = client.post("/pages/", json=page_request)
        page_id = page_response.json()["page_id"]

        # Delete the page
        response = client.delete(f"/pages/{page_id}")

        assert response.status_code == 204

        # Verify it's deleted
        response = client.get(f"/pages/{page_id}")
        assert response.status_code == 404


class TestErrorHandling:
    """Test API error handling."""

    @pytest.mark.skip(reason="API not fully implemented yet")
    def test_invalid_artifact_id_format(self, client) -> None:
        """Test that invalid UUID format returns 422."""
        if client is None:
            pytest.skip("API client not available")

        response = client.get("/artifacts/invalid-uuid")

        assert response.status_code == 422

    @pytest.mark.skip(reason="API not fully implemented yet")
    def test_invalid_page_id_format(self, client) -> None:
        """Test that invalid UUID format returns 422."""
        if client is None:
            pytest.skip("API client not available")

        response = client.get("/pages/invalid-uuid")

        assert response.status_code == 422

    @pytest.mark.skip(reason="API not fully implemented yet")
    def test_missing_required_field_in_request(self, client) -> None:
        """Test that missing required field returns 422."""
        if client is None:
            pytest.skip("API client not available")

        request_data = {
            "source_uri": "https://example.com/paper.pdf",
            # source_filename is missing
            "artifact_type": ArtifactType.RESEARCH_ARTICLE,
            "mime_type": MimeType.PDF,
            "storage_location": "/storage/paper.pdf",
        }

        response = client.post("/artifacts/", json=request_data)

        assert response.status_code == 422

    @pytest.mark.skip(reason="API not fully implemented yet")
    def test_invalid_enum_value(self, client) -> None:
        """Test that invalid enum value returns 422."""
        if client is None:
            pytest.skip("API client not available")

        request_data = {
            "source_uri": "https://example.com/paper.pdf",
            "source_filename": "paper.pdf",
            "artifact_type": "INVALID_TYPE",
            "mime_type": MimeType.PDF,
            "storage_location": "/storage/paper.pdf",
        }

        response = client.post("/artifacts/", json=request_data)

        assert response.status_code == 422
