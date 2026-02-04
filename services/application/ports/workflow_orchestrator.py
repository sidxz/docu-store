"""Port for workflow orchestration.

This port defines the interface for triggering and managing workflows.
The application layer depends on this abstraction, while infrastructure
provides concrete implementations (e.g., Temporal, AWS Step Functions, etc.).

This follows the Dependency Inversion Principle and Hexagonal Architecture.
"""

from abc import ABC, abstractmethod


class WorkflowOrchestrator(ABC):
    """Port for orchestrating long-running workflows.

    This abstraction allows the application layer to trigger workflows
    without depending on specific orchestration infrastructure.
    """

    @abstractmethod
    async def trigger_pdf_ingestion(
        self,
        storage_key: str,
        filename: str | None,
        mime_type: str | None,
        source_uri: str,
        artifact_id: str | None = None,
    ) -> str:
        """Trigger a PDF ingestion workflow.

        Args:
            storage_key: Storage key of the uploaded blob
            filename: Original filename
            mime_type: MIME type of the blob
            source_uri: Source URI for the document
            artifact_id: Optional artifact ID (generated if not provided)

        Returns:
            Workflow execution ID

        Raises:
            Exception: If workflow cannot be triggered

        """
        ...
