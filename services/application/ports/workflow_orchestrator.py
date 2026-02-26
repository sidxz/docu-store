"""Port for workflow orchestration (abstraction from Temporal)."""

from __future__ import annotations

from abc import abstractmethod
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from uuid import UUID


class WorkflowOrchestrator(Protocol):
    """Abstract port for orchestrating long-running workflows.

    This port decouples the domain from the specific orchestration technology
    (Temporal, Celery, etc.). Implementations handle workflow lifecycle,
    retries, and failure handling.
    """

    @abstractmethod
    async def start_artifact_processing_workflow(
        self,
        artifact_id: UUID,
        storage_location: str,
    ) -> None:
        """Start a workflow to process an artifact.

        Args:
            artifact_id: Unique identifier of the artifact to process
            storage_location: Path/location where the artifact is stored

        Raises:
            May raise implementation-specific exceptions on workflow start failure.

        """
        ...

    @abstractmethod
    async def start_embedding_workflow(
        self,
        page_id: UUID,
    ) -> None:
        """Start the embedding generation workflow for a page.

        Args:
            page_id: Unique identifier of the page to generate embeddings for

        Raises:
            May raise implementation-specific exceptions on workflow start failure.

        """
        ...

    @abstractmethod
    async def start_compound_extraction_workflow(
        self,
        page_id: UUID,
    ) -> None:
        """Start the compound extraction workflow for a page.

        Args:
            page_id: Unique identifier of the page to extract compounds from

        Raises:
            May raise implementation-specific exceptions on workflow start failure.

        """
        ...

    @abstractmethod
    async def start_smiles_embedding_workflow(
        self,
        page_id: UUID,
    ) -> None:
        """Start the SMILES embedding workflow for a page.

        Args:
            page_id: Unique identifier of the page whose compounds should be embedded

        Raises:
            May raise implementation-specific exceptions on workflow start failure.

        """
        ...
