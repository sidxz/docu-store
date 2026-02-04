"""Policy dispatcher for reacting to domain events."""

from __future__ import annotations

from typing import TYPE_CHECKING

from application.policies.blob_uploaded_policy import BlobUploadedPolicy
from application.ports.workflow_orchestrator import WorkflowOrchestrator
from domain.aggregates.blob import Blob

if TYPE_CHECKING:
    from infrastructure.read_repositories.read_model_materializer import ReadModelMaterializer


class PolicyDispatcher:
    """Route domain events to application-layer policies."""

    def __init__(
        self,
        materializer: ReadModelMaterializer,
        workflow_orchestrator: WorkflowOrchestrator | None,
    ) -> None:
        self._materializer = materializer
        blob_policy = BlobUploadedPolicy(workflow_orchestrator)

        self._handlers = {
            Blob.BlobUploaded: blob_policy.handle,
        }

    def process_event(self, event: object, tracking: object) -> None:
        """Route event to appropriate policy."""
        handler = self._handlers.get(type(event))
        if handler is None:
            return
        handler(event)
        self._materializer.insert_tracking(tracking)

    @property
    def topics(self) -> list[type]:
        """Get all event types handled."""
        return list(self._handlers.keys())
