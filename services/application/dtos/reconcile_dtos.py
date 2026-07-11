from uuid import UUID

from pydantic import BaseModel


class LabelChange(BaseModel):
    """One reconciled compound label."""

    before: str
    after: str


class ReconcileResultDTO(BaseModel):
    """Result returned by ReconcileCompoundLabelsUseCase."""

    page_id: UUID
    artifact_id: UUID
    changes: list[LabelChange]
    applied: bool
