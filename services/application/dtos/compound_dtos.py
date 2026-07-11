from uuid import UUID

from pydantic import BaseModel


class BioactivityDTO(BaseModel):
    """One NER-extracted bioactivity row. Mirrors web Bioactivity type."""

    assay_type: str
    value: str
    unit: str | None = None
    raw_text: str | None = None


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
