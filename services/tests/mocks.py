"""Mock implementations for testing."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from application.ports.repositories.artifact_repository import ArtifactRepository
from application.ports.repositories.page_repository import PageRepository
from domain.aggregates.artifact import Artifact
from domain.aggregates.page import Page
from domain.exceptions import AggregateNotFoundError


class MockArtifactRepository(ArtifactRepository):
    """Mock implementation of ArtifactRepository for testing."""

    def __init__(self) -> None:
        """Initialize the mock repository."""
        self.artifacts: dict[UUID, Artifact] = {}
        self.save_called = False
        self.get_by_id_called = False

    def save(self, artifact: Artifact) -> None:
        """Save an artifact."""
        self.artifacts[artifact.id] = artifact
        self.save_called = True

    def get_by_id(self, artifact_id: UUID) -> Artifact:
        """Retrieve an artifact by ID."""
        self.get_by_id_called = True
        if artifact_id not in self.artifacts:
            msg = f"Artifact with id {artifact_id} not found"
            raise AggregateNotFoundError(msg)
        return self.artifacts[artifact_id]


class MockPageRepository(PageRepository):
    """Mock implementation of PageRepository for testing."""

    def __init__(self) -> None:
        """Initialize the mock repository."""
        self.pages: dict[UUID, Page] = {}
        self.save_called = False
        self.get_by_id_called = False

    def save(self, page: Page) -> None:
        """Save a page."""
        self.pages[page.id] = page
        self.save_called = True

    def get_by_id(self, page_id: UUID) -> Page:
        """Retrieve a page by ID."""
        self.get_by_id_called = True
        if page_id not in self.pages:
            msg = f"Page with id {page_id} not found"
            raise AggregateNotFoundError(msg)
        return self.pages[page_id]


class MockExternalEventPublisher:
    """Mock implementation of ExternalEventPublisher for testing."""

    def __init__(self) -> None:
        """Initialize the mock publisher."""
        self.artifact_created_called = False
        self.artifact_deleted_called = False
        self.artifact_created_data: Any = None
        self.artifact_deleted_data: Any = None

    async def notify_artifact_created(self, artifact: Any) -> None:
        """Notify that an artifact was created."""
        self.artifact_created_called = True
        self.artifact_created_data = artifact

    async def notify_artifact_deleted(self, artifact_id: UUID) -> None:
        """Notify that an artifact was deleted."""
        self.artifact_deleted_called = True
        self.artifact_deleted_data = artifact_id
