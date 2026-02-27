from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from application.dtos.workflow_dtos import WorkflowStartedResponse

if TYPE_CHECKING:
    from uuid import UUID

    from application.ports.repositories.artifact_repository import ArtifactRepository
    from application.ports.repositories.page_repository import PageRepository
    from application.ports.workflow_orchestrator import WorkflowOrchestrator

log = structlog.get_logger(__name__)


class TriggerArtifactSummarizationUseCase:
    """Trigger the artifact summarization workflow when all pages are summarized.

    Checks that every page in the artifact has a non-empty summary_candidate before
    starting the workflow.  If any page is still pending this call is a no-op and
    returns None — the next Page.SummaryCandidateUpdated event will re-check.
    """

    def __init__(
        self,
        artifact_repository: ArtifactRepository,
        page_repository: PageRepository,
        workflow_orchestrator: WorkflowOrchestrator,
    ) -> None:
        self.artifact_repository = artifact_repository
        self.page_repository = page_repository
        self.workflow_orchestrator = workflow_orchestrator

    async def execute(self, page_id: UUID) -> WorkflowStartedResponse | None:
        page = self.page_repository.get_by_id(page_id)
        artifact_id = page.artifact_id

        artifact = self.artifact_repository.get_by_id(artifact_id)

        if not artifact.pages:
            log.info(
                "trigger_artifact_summarization.no_pages",
                artifact_id=str(artifact_id),
            )
            return None

        # All pages must have a non-empty summary before we synthesize.
        for pid in artifact.pages:
            p = self.page_repository.get_by_id(pid)
            if not p.summary_candidate or not p.summary_candidate.summary:
                log.debug(
                    "trigger_artifact_summarization.page_not_ready",
                    artifact_id=str(artifact_id),
                    pending_page_id=str(pid),
                )
                return None

        log.info(
            "trigger_artifact_summarization.all_pages_ready",
            artifact_id=str(artifact_id),
            page_count=len(artifact.pages),
        )

        workflow_id = f"artifact-summarization-{artifact_id}"
        await self.workflow_orchestrator.start_artifact_summarization_workflow(
            artifact_id=artifact_id,
        )
        return WorkflowStartedResponse(workflow_id=workflow_id)
