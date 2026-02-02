import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Compound(BaseModel):
    """Represents a chemical compound extracted from a document using NLP.

    This value object captures the extracted SMILES notation and associated
    compound metadata, including validation status and external identifiers.

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
    internal_id: str | None = Field(None, description="Internal system identifier for the compound")
    cdd_id: str | None = Field(None, description="Collaborative Drug Discovery (CDD) identifier")
    chembl_id: str | None = Field(None, description="ChEMBL database identifier")
    pdb_id: str | None = Field(None, description="Protein Data Bank identifier")
    names: set[str] | None = Field(None, description="Set of alternative chemical names")
    extracted_name: str | None = Field(
        None,
        description="Primary chemical name as extracted from the document",
    )
    confidence: float | None = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Confidence score of the extraction (0.0 to 1.0)",
    )
    date_extracted: datetime.datetime | None = Field(
        None,
        description="Timestamp when the compound was extracted",
    )
    model_name: str | None = Field(None, description="Name of the NLP model used for extraction")
    additional_model_params: dict[str, str] | None = Field(
        None,
        description="Additional parameters passed to the extraction model",
    )
    pipeline_run_id: UUID | None = Field(
        None,
        description="Identifier for the pipeline run that produced this extraction",
    )

    @field_validator("smiles")
    @classmethod
    def validate_smiles(cls, v: str) -> str:
        """Validate that SMILES is not blank or empty."""
        if not v or not v.strip():
            raise ValueError("SMILES cannot be blank or empty")
        return v
