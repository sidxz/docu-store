from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from returns.result import Failure, Result, Success

from application.dtos.errors import AppError
from application.dtos.reconcile_dtos import LabelChange, ReconcileResultDTO
from domain.exceptions import AggregateNotFoundError, ConcurrencyError
from domain.services.compound_label_matcher import reconcile_label

if TYPE_CHECKING:
    from uuid import UUID

    from application.ports.repositories.page_repository import PageRepository

logger = structlog.get_logger()


class ReconcileCompoundLabelsUseCase:
    """Canonicalize CSER compound labels against the document's NER compound names.

    Reuses ``page.update_compound_mentions`` so the emitted ``CompoundMentionsUpdated``
    event re-derives both the Mongo read model and the Qdrant compound vectors.
    Idempotent: emits only when a label actually changes.
    """

    def __init__(self, page_repository: PageRepository) -> None:
        self.page_repository = page_repository

    async def execute(
        self,
        page_id: UUID,
        candidate_names: list[str] | None = None,
        dry_run: bool = False,
    ) -> Result[ReconcileResultDTO, AppError]:
        try:
            page = self.page_repository.get_by_id(page_id)

            if candidate_names is None:
                names = [
                    tm.tag
                    for tm in (page.tag_mentions or [])
                    if tm.entity_type == "compound_name" and tm.tag
                ]
            else:
                names = candidate_names

            mentions = page.compound_mentions or []
            if not mentions or not names:
                return Success(
                    ReconcileResultDTO(
                        page_id=page_id,
                        artifact_id=page.artifact_id,
                        changes=[],
                        applied=False,
                    ),
                )

            changes: list[LabelChange] = []
            new_mentions = []
            for m in mentions:
                target = reconcile_label(m.extracted_id or "", names)
                if target and target != m.extracted_id:
                    changes.append(LabelChange(before=m.extracted_id, after=target))
                    new_mentions.append(m.model_copy(update={"extracted_id": target}))
                else:
                    new_mentions.append(m)

            if not changes or dry_run:
                return Success(
                    ReconcileResultDTO(
                        page_id=page_id,
                        artifact_id=page.artifact_id,
                        changes=changes,
                        applied=False,
                    ),
                )

            # A human has taken over this page's compounds — update_compound_mentions
            # would silently no-op, so report the pending changes honestly as not applied
            # rather than claiming success.
            if "compound_mentions" in page.human_corrections:
                return Success(
                    ReconcileResultDTO(
                        page_id=page_id,
                        artifact_id=page.artifact_id,
                        changes=changes,
                        applied=False,
                    ),
                )

            page.update_compound_mentions(new_mentions)
            self.page_repository.save(page)
            logger.info(
                "compound_labels_reconciled",
                page_id=str(page_id),
                artifact_id=str(page.artifact_id),
                changes=[(c.before, c.after) for c in changes],
            )
            return Success(
                ReconcileResultDTO(
                    page_id=page_id,
                    artifact_id=page.artifact_id,
                    changes=changes,
                    applied=True,
                ),
            )

        except ConcurrencyError:
            # Let Temporal retry — do NOT swallow into a Failure.
            raise
        except AggregateNotFoundError as e:
            logger.warning(
                "reconcile_compound_labels_not_found", page_id=str(page_id), error=str(e)
            )
            return Failure(AppError("not_found", str(e)))
        except Exception as e:
            logger.exception(
                "reconcile_compound_labels_unexpected_error",
                page_id=str(page_id),
                error=str(e),
            )
            return Failure(AppError("internal_error", f"Unexpected error: {e!s}"))
