from typing import Annotated

from pydantic import ConfigDict, Field, field_validator

from domain.value_objects.extraction_metadata import ExtractionMetadata

# Exactly four ints, always [x1, y1, x2, y2]. Constrained here rather than in the
# DTO because every writer — detector adapter and human correction alike — builds
# a CompoundMention, so this is the one place a malformed box can be stopped. A
# 3- or 5-element box unpacks fatally in the export's `yolo_line`, which would take
# down the whole workspace export for one bad row.
BBox = Annotated[list[int], Field(min_length=4, max_length=4)]


class CompoundMention(ExtractionMetadata):
    """Represents a chemical compound_mention extracted from a document using NLP.

    This value object captures the extracted SMILES notation and associated
    compound_mention metadata, including validation status and external identifiers.

    Raises:
        ValueError: If SMILES is blank or empty.

    """

    model_config = ConfigDict(frozen=True)

    smiles: str = Field(..., description="SMILES notation string (required, cannot be blank)")
    canonical_smiles: str | None = Field(None, description="Canonicalized SMILES representation")
    is_smiles_valid: bool | None = Field(
        None,
        description="Indicates whether the SMILES notation is valid",
    )
    internal_id: str | None = Field(
        None,
        description="Internal system identifier for the compound_mention",
    )
    cdd_id: str | None = Field(None, description="Collaborative Drug Discovery (CDD) identifier")
    chembl_id: str | None = Field(None, description="ChEMBL database identifier")
    pdb_id: str | None = Field(None, description="Protein Data Bank identifier")
    other_ids: set[str] | None = Field(None, description="Set of alternative chemical identifiers")
    extracted_id: str | None = Field(
        None,
        description="Primary chemical identifier as extracted from the document",
    )
    structure_bbox: BBox | None = Field(
        None,
        description=(
            "Structure box [x1, y1, x2, y2] in PIXELS of this page's CSER render "
            "(blob artifacts/{artifact_id}/pages/{index}_cser.png). Meaningless "
            "without that image, which is why the image is persisted, never re-derived."
        ),
    )
    label_bbox: BBox | None = Field(
        None,
        description="Label box [x1, y1, x2, y2] in the same pixel space; None for an unlabelled structure",
    )
    structure_confidence: float | None = Field(
        None,
        description="Detector confidence for the structure box, when it came from the detector",
    )
    label_confidence: float | None = Field(
        None,
        description="Detector confidence for the label box, when it came from the detector",
    )

    @field_validator("smiles")
    @classmethod
    def validate_smiles(cls, v: str) -> str:
        """Validate that SMILES is not blank or empty."""
        if not v or not v.strip():
            msg = "SMILES cannot be blank or empty"
            raise ValueError(msg)
        return v

    # Define a comparison method for easier testing and comparisons
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, CompoundMention):
            return NotImplemented

        if not self.canonical_smiles or not other.canonical_smiles:
            return False

        return self.canonical_smiles.strip() == other.canonical_smiles.strip()

    def __hash__(self) -> int:
        if not self.canonical_smiles:
            return 0
        return hash(self.canonical_smiles.strip())
