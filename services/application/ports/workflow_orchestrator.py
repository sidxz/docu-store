"""Port for workflow orchestration (abstraction from Temporal)."""

from __future__ import annotations

from abc import abstractmethod
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from uuid import UUID

    from application.dtos.workflow_dtos import TemporalWorkflowInfo


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

    @abstractmethod
    async def start_page_summarization_workflow(
        self,
        page_id: UUID,
    ) -> None:
        """Start the LLM summarization workflow for a page.

        Args:
            page_id: Unique identifier of the page to summarize

        Raises:
            May raise implementation-specific exceptions on workflow start failure.

        """
        ...

    @abstractmethod
    async def start_artifact_summarization_workflow(
        self,
        artifact_id: UUID,
    ) -> None:
        """Start the sliding-window LLM summarization workflow for an artifact.

        Should only be called after all pages of the artifact are summarized.
        Uses ALLOW_DUPLICATE id-reuse policy so the workflow re-runs when triggered
        again (e.g. after a page is re-summarized).

        Args:
            artifact_id: Unique identifier of the artifact to summarize

        Raises:
            May raise implementation-specific exceptions on workflow start failure.

        """
        ...

    @abstractmethod
    async def start_page_summary_embedding_workflow(
        self,
        page_id: UUID,
    ) -> None:
        """Start the page summary embedding workflow.

        Args:
            page_id: Unique identifier of the page whose summary should be embedded.

        """
        ...

    @abstractmethod
    async def start_artifact_summary_embedding_workflow(
        self,
        artifact_id: UUID,
    ) -> None:
        """Start the artifact summary embedding workflow.

        Args:
            artifact_id: Unique identifier of the artifact whose summary should be embedded.

        """
        ...

    @abstractmethod
    async def get_page_workflow_statuses(
        self,
        page_id: UUID,
    ) -> dict[str, TemporalWorkflowInfo]:
        """Query Temporal for the status of all workflows associated with a page."""
        ...

    @abstractmethod
    async def get_artifact_workflow_statuses(
        self,
        artifact_id: UUID,
    ) -> dict[str, TemporalWorkflowInfo]:
        """Query Temporal for the status of all workflows associated with an artifact."""
        ...
