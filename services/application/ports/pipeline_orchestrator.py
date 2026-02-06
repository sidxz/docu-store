"""Port for pipeline orchestration (abstraction from Temporal)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from uuid import UUID


class PipelineOrchestrator(ABC):
    """Abstract port for orchestrating long-running pipelines.

    This port decouples the domain from the specific orchestration technology
    (Temporal, Celery, etc.). Implementations handle workflow lifecycle,
    retries, and failure handling.
    """

    @abstractmethod
    async def start_artifact_processing_pipeline(
        self,
        artifact_id: UUID,
        storage_location: str,
    ) -> None:
        """Start a pipeline to process an artifact.

        Args:
            artifact_id: Unique identifier of the artifact to process
            storage_location: Path/location where the artifact is stored

        Raises:
            May raise implementation-specific exceptions on workflow start failure.

        """
        ...
