from pydantic import ConfigDict, Field, field_validator

from domain.value_objects.extraction_metadata import ExtractionMetadata


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
