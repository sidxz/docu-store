import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ExtractionMetadata(BaseModel):
    """Base value object for extraction metadata shared across all mention types.

    This class captures common metadata about the extraction process,
    including confidence scores, extraction timestamps, and model information.
    """

    confidence: float | None = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Confidence score of the extraction (0.0 to 1.0)",
    )
    date_extracted: datetime.datetime | None = Field(
        None,
        description="Timestamp when the content was extracted",
    )
    model_name: str | None = Field(
        None,
        description="Name of the NLP model used for extraction",
    )
    additional_model_params: dict[str, str] | None = Field(
        None,
        description="Additional parameters passed to the extraction model",
    )
    pipeline_run_id: UUID | None = Field(
        None,
        description="Identifier for the pipeline run that produced this extraction",
    )
