"""DTOs for human-in-the-loop corrections to artifact metadata and page compound mentions (hiledit)."""

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


class CorrectedCompoundInput(BaseModel):
    """A single compound mention as submitted by a human reviewer."""

    model_config = {"extra": "forbid"}

    smiles: str
    extracted_id: str | None = None
    internal_id: str | None = None
    cdd_id: str | None = None
    chembl_id: str | None = None
    pdb_id: str | None = None


class CorrectPageCompoundMentionsRequest(BaseModel):
    """Request DTO for correcting a page's compound mentions.

    Full-replace semantics: the submitted list becomes the page's entire
    ``compound_mentions``. An empty list is allowed and clears all mentions.
    """

    model_config = {"extra": "forbid"}

    compound_mentions: list[CorrectedCompoundInput]


class HumanCorrectionInfo(BaseModel):
    """Provenance for a single corrected field."""

    corrected_by_id: str
    corrected_by_name: str | None = None
    corrected_at: datetime
