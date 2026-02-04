"""Domain service for handling artifact deletion with cascading page deletions."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from domain.aggregates.artifact import Artifact
    from domain.aggregates.page import Page


class ArtifactDeletionService:
    """Service that orchestrates the deletion of an artifact and all its pages.

    This service enforces the business rule that when an artifact is deleted,
    all pages associated with it must also be deleted.
    """

    @staticmethod
    def delete_artifact_with_pages(artifact: Artifact, pages: list[Page]) -> None:
        """Delete an artifact and all its associated pages.

        This is a pure domain operation that works with aggregates directly.
        The application layer is responsible for fetching the aggregates
        and persisting them.

        Args:
            artifact: The Artifact aggregate to delete
            pages: The list of Page aggregates associated with the artifact

        Raises:
            ValueError: If the artifact is already deleted

        """
        # Delete all pages
        for page in pages:
            page.delete()

        # Delete the artifact itself
        artifact.delete()
