from uuid import UUID

from pydantic import BaseModel


class BioactivityDTO(BaseModel):
    """One NER-extracted bioactivity row. Mirrors web Bioactivity type."""

    assay_type: str
    value: str
    unit: str | None = None
    raw_text: str | None = None
    assay: str | None = None
    strain: str | None = None
    target: str | None = None
    combination: str | None = None
    # The page the value was read on (the first one, when a summary slide repeats it).
    artifact_id: UUID | None = None
    page_id: UUID | None = None
    page_index: int | None = None


class CompoundPageRefDTO(BaseModel):
    """A page where the compound was detected."""

    page_id: UUID
    page_index: int
    artifact_id: UUID
    artifact_title: str | None = None


class CompoundProfileDTO(BaseModel):
    """Structure + activity profile for a compound, looked up by name."""

    name: str
    extracted_id: str | None = None
    canonical_smiles: str | None = None
    has_structure: bool = False
    synonyms: list[str] = []
    bioactivities: list[BioactivityDTO] = []
    reference_pages: list[CompoundPageRefDTO] = []
