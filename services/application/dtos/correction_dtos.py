"""DTOs for human-in-the-loop artifact metadata corrections (hiledit)."""

from datetime import date, datetime

from pydantic import BaseModel


class CorrectedTagInput(BaseModel):
    """A single tag as submitted by a human reviewer."""

    tag: str
    entity_type: str | None = None


class CorrectArtifactMetadataRequest(BaseModel):
    """Request DTO for correcting artifact metadata.

    Omitted-vs-null matters: a field left out of the request is untouched,
    while an explicit ``null`` clears it. Callers must check
    ``model_fields_set`` rather than the field values themselves.
    """

    model_config = {"extra": "forbid"}

    title: str | None = None
    presentation_date: date | None = None
    tags: list[CorrectedTagInput] | None = None
    authors: list[str] | None = None


class HumanCorrectionInfo(BaseModel):
    """Provenance for a single corrected field."""

    corrected_by_id: str
    corrected_by_name: str | None = None
    corrected_at: datetime
